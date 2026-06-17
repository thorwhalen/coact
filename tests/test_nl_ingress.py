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


def test_model_string_llm_threads_model():
    reply = _reply([{"name": "t", "description": "d", "input_schema": {}, "handler": None}])
    captured = {}

    def fake(prompt, **kwargs):
        captured.update(kwargs)
        return reply

    # a str llm is a model name -> threaded as model=... to the backend
    integration_spec_from_description("x", llm=fake, model="claude-sonnet-4")
    assert captured.get("model") == "claude-sonnet-4"


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
