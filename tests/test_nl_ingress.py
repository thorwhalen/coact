"""Tests for the opt-in NL ingress (NL description -> draft IntegrationSpec).

All offline: the LLM backend is injected as a fake ``callable(prompt, **kw) -> str``
so no provider is called. They verify the backend is genuinely injectable
(D10/route-through-aix), the draft shape, schema inference fallback, and that a
handler-less draft is rejected by the runnable .mcpb path while a bound one builds.
"""

import json

import pytest

from coact import (
    IntegrationSpec,
    ToolSpec,
    integration_spec_from_description,
    publish,
    publish_mcpb,
)


def _reply(tools, *, name="wx", description="weather things"):
    return json.dumps(
        {"name": name, "description": description, "tools": tools,
         "resources": [], "prompts": []}
    )


def _fixed(reply):
    """A fake backend that always returns ``reply`` (records calls)."""
    calls = []

    def fake(prompt, **kwargs):
        calls.append((prompt, kwargs))
        return reply

    fake.calls = calls
    return fake


# --- happy path: proposed tools with inline schemas --------------------------


def test_draft_from_description_with_inline_schemas():
    reply = _reply(
        [
            {
                "name": "get_weather",
                "description": "look up current weather for a city",
                "input_schema": {
                    "type": "object",
                    "properties": {"city": {"type": "string"}},
                    "required": ["city"],
                },
                "handler": None,
            }
        ]
    )
    spec = integration_spec_from_description("a weather lookup tool", llm=_fixed(reply))
    assert isinstance(spec, IntegrationSpec)
    assert spec.name == "wx"
    assert spec.source == "nl-description"
    assert [t.name for t in spec.tool_specs] == ["get_weather"]
    ts = spec.tool_specs[0]
    assert ts.is_bound() is False
    assert ts.input_schema["properties"]["city"]["type"] == "string"
    # a pure draft has no runnable refs and is not empty
    assert spec.runnable_refs() == []
    assert spec.is_empty() is False


def test_name_override_is_kebabbed():
    reply = _reply([{"name": "t", "description": "d", "input_schema": {}, "handler": None}])
    spec = integration_spec_from_description("x", llm=_fixed(reply), name="My Cool Connector")
    assert spec.name == "my-cool-connector"


# --- backend injection (route-through-aix honesty) ---------------------------


def test_backend_is_injected_not_openai():
    reply = _reply([{"name": "t", "description": "d", "input_schema": {}, "handler": None}])
    fake = _fixed(reply)
    integration_spec_from_description("x", llm=fake)
    assert fake.calls, "the injected backend must actually be called"
    # the rendered prompt carries the description (the single template placeholder)
    assert "x" in fake.calls[0][0]


def test_callable_llm_threads_explicit_model():
    reply = _reply([{"name": "t", "description": "d", "input_schema": {}, "handler": None}])
    captured = {}

    def fake(prompt, **kwargs):
        captured.update(kwargs)
        return reply

    integration_spec_from_description("x", llm=fake, model="claude-sonnet-4")
    assert captured.get("model") == "claude-sonnet-4"


def test_str_llm_is_treated_as_model_name(monkeypatch):
    """A str llm is a model name routed to the default aix.chat backend (D18)."""
    from coact import nl_ingress

    reply = _reply([{"name": "t", "description": "d", "input_schema": {}, "handler": None}])
    captured = {}

    def fake_chat(prompt, **kwargs):
        captured.update(kwargs)
        return reply

    monkeypatch.setattr(nl_ingress, "_aix_chat", lambda: fake_chat)
    integration_spec_from_description("x", llm="claude-sonnet-4")
    assert captured.get("model") == "claude-sonnet-4"


def test_explicit_model_overrides_str_llm(monkeypatch):
    from coact import nl_ingress

    reply = _reply([{"name": "t", "description": "d", "input_schema": {}, "handler": None}])
    captured = {}
    monkeypatch.setattr(
        nl_ingress, "_aix_chat", lambda: (lambda p, **k: captured.update(k) or reply)
    )
    integration_spec_from_description("x", llm="model-a", model="model-b")
    assert captured.get("model") == "model-b"  # explicit model wins over str llm


# --- per-tool schema inference fallback --------------------------------------


def test_schema_inference_fallback_invoked_when_missing():
    """A tool without input_schema triggers oa.infer_schema_from_verbal_description."""
    primary = _reply(
        [{"name": "t", "description": "does a thing with a count", "handler": None}]
    )
    schema_reply = json.dumps(
        {"name": "t_in", "properties": {"count": {"type": "integer"}}, "type": "object"}
    )

    def dispatch(prompt, **kwargs):
        # the authoring prompt mentions "architect"; the schema prompt mentions "JSON Schema"
        return primary if "architect" in prompt else schema_reply

    spec = integration_spec_from_description("x", llm=dispatch, infer_tool_schemas=True)
    ts = spec.tool_specs[0]
    assert ts.input_schema == {"type": "object", "properties": {"count": {"type": "integer"}}}


def test_schema_inference_can_be_disabled():
    primary = _reply([{"name": "t", "description": "d", "handler": None}])
    spec = integration_spec_from_description(
        "x", llm=_fixed(primary), infer_tool_schemas=False
    )
    assert spec.tool_specs[0].input_schema is None


def test_schema_inference_degrades_on_bad_reply():
    """If schema inference returns junk, the tool keeps input_schema=None (no crash)."""
    primary = _reply([{"name": "t", "description": "d", "handler": None}])

    def dispatch(prompt, **kwargs):
        return primary if "architect" in prompt else "not json at all"

    spec = integration_spec_from_description("x", llm=dispatch, infer_tool_schemas=True)
    assert spec.tool_specs[0].input_schema is None


# --- bound handlers become runnable refs -> publishable ----------------------


def test_bound_handler_becomes_runnable_and_publishes(tmp_path):
    reply = _reply(
        [
            {
                "name": "basename",
                "description": "basename of a path",
                "input_schema": {"type": "object", "properties": {}},
                "handler": "os.path:basename",
            }
        ]
    )
    spec = integration_spec_from_description("expose os.path.basename", llm=_fixed(reply))
    assert spec.runnable_refs() == ["os.path:basename"]
    res = publish(spec, name="paths", dest=str(tmp_path))
    assert res.artifact is not None and res.artifact.exists()


def test_pure_draft_publish_rejected():
    reply = _reply([{"name": "t", "description": "d", "input_schema": {}, "handler": None}])
    spec = integration_spec_from_description("x", llm=_fixed(reply))
    with pytest.raises(ValueError, match="design draft"):
        publish_mcpb(spec)


# --- manifest visibility for proposed tools ----------------------------------


def test_proposed_tools_listed_in_manifest_with_warning(tmp_path):
    # a bound tool (publishable) plus an unbound proposed tool
    spec = IntegrationSpec(
        name="mix",
        tool_specs=[
            ToolSpec(name="basename", handler="os.path:basename"),
            ToolSpec(name="future_tool", description="not built yet"),
        ],
    )
    res = publish(spec, dest=str(tmp_path), dry_run=True)
    assert any("future_tool" in w for w in res.warnings)


# --- guards ------------------------------------------------------------------


def test_empty_description_rejected():
    with pytest.raises(ValueError):
        integration_spec_from_description("   ", llm=_fixed("{}"))


def test_unparseable_reply_rejected():
    with pytest.raises(ValueError, match="could not parse"):
        integration_spec_from_description("x", llm=_fixed("sorry, I cannot help"))


# --- robustness against untrusted LLM output (review hardening) --------------


def test_non_string_fields_do_not_crash():
    """Numbers/objects where strings were asked for are coerced, not crashed on."""
    reply = json.dumps(
        {
            "name": 2025,  # number where a string was expected
            "description": ["a", "list"],
            "tools": [
                {"name": 42, "description": {"k": "v"}, "input_schema": {}, "handler": None}
            ],
            "resources": [],
            "prompts": [],
        }
    )
    spec = integration_spec_from_description("x", llm=_fixed(reply))
    assert spec.name == "2025"  # coerced + kebabbed, not a crash
    assert spec.tool_specs[0].name == "42"


def test_single_string_resources_not_exploded():
    """A bare-string resources/prompts is wrapped, not iterated char-by-char."""
    reply = json.dumps(
        {
            "name": "wx",
            "description": "d",
            "tools": [{"name": "t", "description": "d", "input_schema": {}, "handler": None}],
            "resources": "the_only_resource",  # a string, not a list
            "prompts": "the_only_prompt",
        }
    )
    spec = integration_spec_from_description("x", llm=_fixed(reply))
    assert spec.resources == ["the_only_resource"]
    assert spec.prompts == ["the_only_prompt"]


def test_parse_recovers_json_after_brace_bearing_prose():
    """A reply whose JSON is preceded by prose containing braces still parses."""
    reply = (
        'For example {x, y} are inputs. Here is the spec: '
        + _reply([{"name": "t", "description": "d", "input_schema": {}, "handler": None}])
    )
    spec = integration_spec_from_description("x", llm=_fixed(reply))
    assert spec.name == "wx" and spec.tool_specs[0].name == "t"


def test_parse_recovers_fenced_json():
    reply = "```json\n" + _reply(
        [{"name": "t", "description": "d", "input_schema": {}, "handler": None}]
    ) + "\n```"
    spec = integration_spec_from_description("x", llm=_fixed(reply))
    assert spec.name == "wx"


def test_injected_callable_does_not_require_aix(monkeypatch):
    """With an injected callable backend, aix need not be importable (D18)."""
    import builtins

    real_import = builtins.__import__

    def no_aix(name, *args, **kwargs):
        if name == "aix" or name.startswith("aix."):
            raise ImportError("aix blocked for test")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_aix)
    reply = _reply([{"name": "t", "description": "d", "input_schema": {}, "handler": None}])
    spec = integration_spec_from_description("x", llm=_fixed(reply))  # must not raise
    assert spec.name == "wx"


# --- integration_spec_from preserves drafts through the list branch (#5) ------


def test_spec_in_list_preserves_bound_handlers():
    from coact import integration_spec_from

    draft = IntegrationSpec(name="wx", tool_specs=[ToolSpec(name="dn", handler="os.path:dirname")])
    out = integration_spec_from([draft, "os.path:basename"])
    assert "os.path:dirname" in out.runnable_refs()
    assert "os.path:basename" in out.runnable_refs()


def test_pure_bound_draft_in_list_publishes(tmp_path):
    from coact import integration_spec_from

    draft = IntegrationSpec(name="wx", tool_specs=[ToolSpec(name="bn", handler="os.path:basename")])
    out = integration_spec_from([draft])
    assert out.runnable_refs() == ["os.path:basename"]
    res = publish(out, dest=str(tmp_path))
    assert res.artifact is not None and res.artifact.exists()


# --- manifest fidelity + clearer guards (#4, #7) -----------------------------


def test_bound_toolspec_fills_empty_manifest_description(monkeypatch):
    """A bound tool whose docstring is empty gets its manifest desc from the ToolSpec."""
    import importlib

    pm = importlib.import_module("coact.publish_mcpb")

    monkeypatch.setattr(
        pm, "_introspect_tools", lambda refs: ([{"name": "basename", "description": ""}], [])
    )
    spec = IntegrationSpec(
        name="mix",
        tool_specs=[ToolSpec(name="x", description="curated", handler="os.path:basename")],
    )
    manifest, _ = pm.build_manifest(spec)
    tool = next(t for t in manifest["tools"] if t["name"] == "basename")
    assert tool["description"] == "curated"  # empty introspected desc filled in


def test_bound_toolspec_does_not_clobber_introspected_description(monkeypatch):
    """Runtime truth (the function's own docstring) wins — never desync manifest vs server."""
    import importlib

    pm = importlib.import_module("coact.publish_mcpb")

    monkeypatch.setattr(
        pm,
        "_introspect_tools",
        lambda refs: ([{"name": "basename", "description": "real docstring"}], []),
    )
    spec = IntegrationSpec(
        name="mix",
        tool_specs=[ToolSpec(name="x", description="curated", handler="os.path:basename")],
    )
    manifest, _ = pm.build_manifest(spec)
    tool = next(t for t in manifest["tools"] if t["name"] == "basename")
    assert tool["description"] == "real docstring"


def test_resources_only_spec_rejected_with_clear_message():
    with pytest.raises(ValueError, match="resource"):
        publish_mcpb(IntegrationSpec(name="r", resources=["data1"]))


def test_import_coact_is_provider_free():
    """D10/D18: `import coact` must not pull in oa/aix/litellm (lazy provider deps).

    Run in a subprocess because the test session imports oa/aix elsewhere.
    """
    import subprocess
    import sys

    code = (
        "import sys, coact; "
        "leaked=[m for m in ('oa','aix','litellm','openai') if m in sys.modules]; "
        "assert not leaked, leaked; print('ok')"
    )
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True
    )
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "ok"
