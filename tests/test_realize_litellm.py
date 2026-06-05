"""Tests for the LiteLLM realization backend (provider-agnostic; injected completion).

All tests run with **no API key and no litellm install required** — the completion
callable is injected, and ``execute`` only checks for litellm on the default path.
"""

import importlib.util

import pytest

from coact import (
    AgentDefinition,
    ReturnContract,
    RunnableLLMAgent,
    realize,
    realization_backends,
    realize_litellm,
)
from coact.realize_litellm import (
    DEFAULT_MODEL,
    _extract_litellm_artifact,
    _litellm_content,
    _try_json,
)


def _resp(content):
    """A minimal OpenAI-style ModelResponse stand-in."""
    from types import SimpleNamespace

    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
    )


def _agent(name="ux", *, schema=None, **kw):
    returns = ReturnContract(json_schema=schema) if schema else ReturnContract()
    return AgentDefinition(
        name=name, description="Analyze.", prompt="You are X.", returns=returns, **kw
    )


# --- registration / dispatch ------------------------------------------------


def test_litellm_registered_open_closed():
    assert "litellm" in realization_backends


def test_realize_dispatches_to_litellm():
    r = realize(_agent(), backend="litellm", completion=lambda **k: _resp("hi"))
    assert isinstance(r, RunnableLLMAgent)


def test_litellm_rejects_multiple_agents():
    with pytest.raises(ValueError, match="exactly one agent"):
        realize([_agent("a"), _agent("b")], backend="litellm")


# --- model mapping (portability) --------------------------------------------


def test_model_selector_maps_to_litellm_string():
    assert RunnableLLMAgent(_agent(model="sonnet")).resolve_model() == "anthropic/claude-sonnet-4-5"
    assert RunnableLLMAgent(_agent(model="opus")).resolve_model() == "anthropic/claude-opus-4-1"


def test_explicit_litellm_model_string_used_verbatim():
    assert RunnableLLMAgent(_agent(model="gemini/gemini-1.5-pro")).resolve_model() == "gemini/gemini-1.5-pro"


def test_no_model_falls_back_to_default():
    assert RunnableLLMAgent(_agent()).resolve_model() == DEFAULT_MODEL


def test_custom_model_map_targets_any_provider():
    r = realize_litellm(
        _agent(model="sonnet"),
        model_map={"sonnet": "openai/gpt-4o"},
        completion=lambda **k: _resp("x"),
    )
    assert r.resolve_model() == "openai/gpt-4o"


# --- message + kwargs construction ------------------------------------------


def test_build_messages_carries_persona_and_schema_instruction():
    schema = {"type": "object", "properties": {"a": {"type": "string"}}}
    msgs = RunnableLLMAgent(_agent(schema=schema)).build_messages("the task")
    assert msgs[0]["role"] == "system" and "You are X." in msgs[0]["content"]
    assert "Return contract" in msgs[0]["content"] and '"a"' in msgs[0]["content"]
    assert msgs[-1] == {"role": "user", "content": "the task"}


def test_build_kwargs_sets_response_format_when_schema_present():
    schema = {"type": "object", "properties": {"a": {"type": "string"}}}
    kwargs = RunnableLLMAgent(_agent(schema=schema)).build_kwargs("t")
    assert kwargs["response_format"]["type"] == "json_schema"
    assert kwargs["response_format"]["json_schema"]["schema"] == schema


def test_build_kwargs_omits_response_format_without_schema():
    assert "response_format" not in RunnableLLMAgent(_agent()).build_kwargs("t")


def test_use_response_format_false_keeps_prompt_instruction_only():
    schema = {"type": "object", "properties": {"a": {"type": "string"}}}
    r = RunnableLLMAgent(_agent(schema=schema), use_response_format=False)
    kwargs = r.build_kwargs("t")
    assert "response_format" not in kwargs
    # the schema is still requested via the system prompt (portable fallback)
    assert "Return contract" in kwargs["messages"][0]["content"]


# --- execute (aw.AgenticStep shape) -----------------------------------------


def test_execute_parses_structured_json():
    schema = {"type": "object", "properties": {"a": {"type": "string"}}}
    r = realize(_agent(schema=schema), backend="litellm", completion=lambda **k: _resp('{"a": "hi"}'))
    artifact, info = r.execute("task", context={})
    assert artifact == {"a": "hi"}
    assert info["backend"] == "litellm" and info["structured"] is True
    assert info["model"] == DEFAULT_MODEL


def test_execute_returns_text_when_no_schema():
    r = realize(_agent(), backend="litellm", completion=lambda **k: _resp("just prose"))
    artifact, info = r.execute("task")
    assert artifact == "just prose" and info["structured"] is False


def test_execute_tolerates_fenced_json():
    schema = {"type": "object", "properties": {"a": {"type": "string"}}}
    fenced = '```json\n{"a": "x"}\n```'
    r = realize(_agent(schema=schema), backend="litellm", completion=lambda **k: _resp(fenced))
    artifact, _ = r.execute("task")
    assert artifact == {"a": "x"}


def test_execute_falls_back_to_text_when_structured_parse_fails():
    schema = {"type": "object", "properties": {"a": {"type": "string"}}}
    r = realize(_agent(schema=schema), backend="litellm", completion=lambda **k: _resp("not json"))
    artifact, _ = r.execute("task")
    assert artifact == "not json"  # graceful: surface the prose rather than crash


def test_execute_satisfies_aw_agentic_step_tuple_shape():
    r = realize(_agent(), backend="litellm", completion=lambda **k: _resp("ok"))
    result = r.execute("x", {})
    assert isinstance(result, tuple) and len(result) == 2 and isinstance(result[1], dict)


# --- extraction helpers (dict and object responses) -------------------------


def test_litellm_content_handles_dict_response():
    raw = {"choices": [{"message": {"content": "from dict"}}]}
    assert _litellm_content(raw) == "from dict"


def test_extract_artifact_returns_raw_when_no_content():
    sentinel = object()
    assert _extract_litellm_artifact(sentinel, has_schema=True) is sentinel


def test_try_json_variants():
    assert _try_json('{"a": 1}') == {"a": 1}
    assert _try_json("[1, 2]") == [1, 2]
    assert _try_json("not json") is None
    assert _try_json('```json\n{"a": 1}\n```') == {"a": 1}


def test_litellm_installed_matches_extra():
    # documents that the backend's real path needs the optional extra
    has = importlib.util.find_spec("litellm") is not None
    assert isinstance(has, bool)


# --- review fixes -----------------------------------------------------------


def test_response_format_falls_back_to_prompt_on_provider_error():
    # a provider that rejects json_schema response_format -> retry once without it
    schema = {"type": "object", "properties": {"a": {"type": "string"}}}
    seen = []

    def flaky(**kwargs):
        seen.append("response_format" in kwargs)
        if "response_format" in kwargs:
            raise RuntimeError("this model does not support response_format")
        return _resp('{"a": "ok"}')

    r = realize(_agent(schema=schema), backend="litellm", completion=flaky)
    artifact, info = r.execute("task")
    assert artifact == {"a": "ok"}
    assert seen == [True, False]  # tried with response_format, then without
    assert info["response_format_used"] is False


def test_response_format_used_flag_true_on_success():
    schema = {"type": "object", "properties": {"a": {"type": "string"}}}
    r = realize(_agent(schema=schema), backend="litellm", completion=lambda **k: _resp('{"a":"x"}'))
    _, info = r.execute("task")
    assert info["response_format_used"] is True


def test_runnable_llm_agent_copies_model_map_on_construction():
    external = {"sonnet": "openai/gpt-4o"}
    r = RunnableLLMAgent(_agent(model="sonnet"), model_map=external)
    external["sonnet"] = "mutated-externally"  # must NOT affect the agent
    assert r.resolve_model() == "openai/gpt-4o"
    r.model_map["sonnet"] = "internal"  # must NOT leak back to the caller's dict
    assert external["sonnet"] == "mutated-externally"


def test_resolve_model_honors_none_key_in_map_else_default():
    assert RunnableLLMAgent(_agent(model=None)).resolve_model() == DEFAULT_MODEL
    mapped = RunnableLLMAgent(_agent(model=None), model_map={None: "ollama/llama3"})
    assert mapped.resolve_model() == "ollama/llama3"


def test_non_string_input_rendered_as_json_not_repr():
    msgs = RunnableLLMAgent(_agent()).build_messages({"task": "go", "n": 1})
    assert msgs[-1]["content"] == '{"task": "go", "n": 1}'


def test_try_json_robust_variants():
    from coact.realize_litellm import _try_json

    assert _try_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert _try_json('```json{"a": 1}```') == {"a": 1}  # no newline after lang tag
    assert _try_json('here is the result: {"a": 1} done') == {"a": 1}  # span extraction
    assert _try_json(None) is None
    assert _try_json(123) is None


def test_try_json_balanced_span_regressions():
    # Regression: naive find/rfind mismatched openers/closers (issue #29).
    from coact.realize_litellm import _try_json

    # A valid object followed by stray closing braces in prose: the balanced
    # matcher stops at the first depth-0 '}', so the object still parses (the old
    # rfind('}') over-captured and returned None).
    assert _try_json('result: {"a": 1} } } extra') == {"a": 1}
    # An *invalid* object that merely contains a valid nested array must NOT yield
    # the nested array (the old code returned [1, 2, 3], violating the contract).
    assert _try_json("The result is {found: [1,2,3]}") is None
    # A genuine top-level array still extracts.
    assert _try_json("prose [1, 2, 3] tail") == [1, 2, 3]


def test_execute_uses_default_completion_and_checks_requirements(monkeypatch):
    import importlib

    # NB: `coact.realize_litellm` the attribute is the *function* (re-exported in
    # coact/__init__), so import the module explicitly to patch its globals.
    m = importlib.import_module("coact.realize_litellm")

    calls = {}

    def fake_check(modules, *, feature):
        calls["modules"] = modules
        calls["feature"] = feature

    def fake_default(**kwargs):
        calls["completion"] = True
        return _resp("ok")

    monkeypatch.setattr(m, "check_requirements", fake_check)
    monkeypatch.setattr(m, "_default_litellm_completion", fake_default)
    r = realize(_agent(), backend="litellm")  # completion=None -> default path
    artifact, _ = r.execute("x")
    assert artifact == "ok"
    assert calls["modules"] == {"litellm": "litellm"}
    assert "litellm" in calls["feature"]
    assert calls["completion"] is True


def test_schema_ref_resolves_into_messages():
    ad = AgentDefinition(
        name="x", description="d", prompt="P",
        returns=ReturnContract(ref="coact.base:ReturnContract"),
    )
    msgs = RunnableLLMAgent(ad).build_messages("t")
    assert "Return contract" in msgs[0]["content"]


def test_unresolvable_schema_ref_omits_instruction():
    ad = AgentDefinition(
        name="x", description="d", prompt="P",
        returns=ReturnContract(ref="nope.not:Real"),
    )
    msgs = RunnableLLMAgent(ad).build_messages("t")
    assert "Return contract" not in msgs[0]["content"]


def test_no_instruction_when_no_return_contract():
    msgs = RunnableLLMAgent(_agent()).build_messages("t")
    assert all("Return contract" not in m["content"] for m in msgs)


def test_realize_litellm_passes_through_agent_definition():
    ad = _agent()
    r = realize(ad, backend="litellm", completion=lambda **k: _resp("x"))
    assert r.agent_def is ad


def test_litellm_content_malformed_returns_none():
    from types import SimpleNamespace

    assert _litellm_content(SimpleNamespace(choices=[])) is None
    assert _litellm_content(SimpleNamespace(choices=[SimpleNamespace(message=None)])) is None
    assert _litellm_content({"choices": [{}]}) is None


def test_extract_returns_already_parsed_structured_content():
    from types import SimpleNamespace

    raw = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content={"a": 1}))])
    assert _extract_litellm_artifact(raw, has_schema=True) == {"a": 1}


def test_execute_accepts_and_ignores_context():
    captured = {}

    def comp(**kwargs):
        captured.update(kwargs)
        return _resp("ok")

    r = realize(_agent(), backend="litellm", completion=comp)
    artifact, _ = r.execute("t", context={"k": "v"})
    assert artifact == "ok" and "context" not in captured


# --- fallback observability + non-string input (gap coverage) ---------------


def test_response_format_error_recorded_in_info():
    # the swallowed error that forced the no-response_format retry is surfaced.
    schema = {"type": "object", "properties": {"a": {"type": "string"}}}

    def flaky(**kwargs):
        if "response_format" in kwargs:
            raise RuntimeError("provider rejects response_format")
        return _resp('{"a": "ok"}')

    r = realize(_agent(schema=schema), backend="litellm", completion=flaky)
    _, info = r.execute("task")
    assert "response_format_error" in info
    assert "provider rejects response_format" in info["response_format_error"]


def test_no_response_format_error_on_clean_success():
    schema = {"type": "object", "properties": {"a": {"type": "string"}}}
    r = realize(_agent(schema=schema), backend="litellm", completion=lambda **k: _resp('{"a":"x"}'))
    _, info = r.execute("task")
    assert "response_format_error" not in info


def test_to_user_text_repr_fallback_for_unserializable():
    from coact.realize_litellm import _to_user_text

    class _NotJson:
        def __repr__(self):
            return "<weird>"

    assert _to_user_text(_NotJson()) == "<weird>"
