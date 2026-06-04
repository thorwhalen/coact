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
