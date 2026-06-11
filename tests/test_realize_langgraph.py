"""Tests for the LangGraph realization backend (injected factory; no key, no install).

All tests run with **no API key and no langchain/langgraph required** — the graph
``factory`` (and optionally the ``runner``) is injected, and ``build_agent`` only
imports the frameworks on the default path. The one test that builds a real
``ToolStrategy`` ``importorskip``\\s ``langchain`` (installed in dev, skipped in bare CI).
"""

from types import SimpleNamespace

import pytest

from coact import (
    AgentDefinition,
    ReturnContract,
    RunnableLLMGraphAgent,
    realize,
    realization_backends,
    realize_langgraph,
)
from coact.realize_langgraph import DEFAULT_MODEL

_ABSENT = object()


def _msg(content):
    return SimpleNamespace(content=content)


def _result(text=None, structured=_ABSENT):
    """A minimal LangGraph result dict (optionally carrying structured_response)."""
    r = {"messages": [_msg(text)]}
    if structured is not _ABSENT:
        r["structured_response"] = structured
    return r


def _graph_returning(result, record=None):
    """A fake factory returning a fake graph whose .invoke returns ``result``."""

    class _Graph:
        def invoke(self, state):
            if record is not None:
                record["state"] = state
            return result

    def factory(**kwargs):
        if record is not None:
            record["factory_kwargs"] = kwargs
            record["calls"] = record.get("calls", 0) + 1
        return _Graph()

    return factory


def _agent(name="ux", *, schema=None, **kw):
    returns = ReturnContract(json_schema=schema) if schema else ReturnContract()
    return AgentDefinition(
        name=name, description="Analyze.", prompt="You are X.", returns=returns, **kw
    )


_SCHEMA = {"type": "object", "properties": {"a": {"type": "string"}}}


# --- registration / dispatch ------------------------------------------------


def test_langgraph_registered_open_closed():
    assert "langgraph" in realization_backends


def test_realize_dispatches_to_langgraph():
    r = realize(_agent(), backend="langgraph", factory=_graph_returning(_result("hi")))
    assert isinstance(r, RunnableLLMGraphAgent)


def test_langgraph_rejects_multiple_agents():
    with pytest.raises(ValueError, match="exactly one agent"):
        realize([_agent("a"), _agent("b")], backend="langgraph")


def test_langgraph_d8_message_cites_the_decision():
    with pytest.raises(ValueError, match="D8"):
        realize([_agent("a"), _agent("b")], backend="langgraph")


# --- model mapping (colon form) ---------------------------------------------


def test_model_selector_maps_to_colon_form():
    assert (
        RunnableLLMGraphAgent(_agent(model="sonnet")).resolve_model()
        == "anthropic:claude-sonnet-4-5"
    )
    assert (
        RunnableLLMGraphAgent(_agent(model="opus")).resolve_model()
        == "anthropic:claude-opus-4-1"
    )


def test_explicit_model_string_used_verbatim():
    assert (
        RunnableLLMGraphAgent(_agent(model="openai:gpt-4o")).resolve_model()
        == "openai:gpt-4o"
    )


def test_no_model_falls_back_to_default():
    assert RunnableLLMGraphAgent(_agent()).resolve_model() == DEFAULT_MODEL


def test_custom_model_map_targets_any_provider():
    r = realize_langgraph(_agent(model="sonnet"), model_map={"sonnet": "groq:llama"})
    assert r.resolve_model() == "groq:llama"


def test_resolve_model_honors_none_key_else_default():
    assert RunnableLLMGraphAgent(_agent(model=None)).resolve_model() == DEFAULT_MODEL
    mapped = RunnableLLMGraphAgent(_agent(model=None), model_map={None: "ollama:llama3"})
    assert mapped.resolve_model() == "ollama:llama3"


def test_model_map_copied_on_construction():
    external = {"sonnet": "openai:gpt-4o"}
    r = RunnableLLMGraphAgent(_agent(model="sonnet"), model_map=external)
    external["sonnet"] = "mutated"
    assert r.resolve_model() == "openai:gpt-4o"
    r.model_map["sonnet"] = "internal"
    assert external["sonnet"] == "mutated"  # no leak back to caller


# --- system prompt / response_format ----------------------------------------


def test_build_system_prompt_carries_persona_and_schema_instruction():
    sp = RunnableLLMGraphAgent(_agent(schema=_SCHEMA)).build_system_prompt()
    assert "You are X." in sp and "Return contract" in sp and '"a"' in sp


def test_build_system_prompt_omits_instruction_without_schema():
    assert "Return contract" not in RunnableLLMGraphAgent(_agent()).build_system_prompt()


def test_build_system_prompt_omits_on_unresolvable_schema_ref():
    ad = AgentDefinition(
        name="x", description="d", prompt="P", returns=ReturnContract(ref="nope.not:Real")
    )
    assert "Return contract" not in RunnableLLMGraphAgent(ad).build_system_prompt()


def test_build_response_format_none_without_schema_or_when_disabled():
    assert RunnableLLMGraphAgent(_agent()).build_response_format() is None
    r = RunnableLLMGraphAgent(_agent(schema=_SCHEMA), use_response_format=False)
    assert r.build_response_format() is None


def test_build_response_format_degrades_to_raw_dict_without_langchain(monkeypatch):
    # Simulate langchain absent: the import inside build_response_format fails ->
    # the raw schema dict is returned (offline/test path stays framework-free).
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *a, **k):
        if name.startswith("langchain"):
            raise ImportError("no langchain")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    rf = RunnableLLMGraphAgent(_agent(schema=_SCHEMA)).build_response_format()
    assert rf == _SCHEMA


def test_build_response_format_is_toolstrategy_with_raw_dict():
    pytest.importorskip("langchain")
    from langchain.agents.structured_output import ProviderStrategy, ToolStrategy

    ts = RunnableLLMGraphAgent(_agent(schema=_SCHEMA)).build_response_format()
    assert isinstance(ts, ToolStrategy) and ts.schema == _SCHEMA
    ps = RunnableLLMGraphAgent(
        _agent(schema=_SCHEMA), structured_strategy="provider"
    ).build_response_format()
    assert isinstance(ps, ProviderStrategy) and ps.schema == _SCHEMA


def test_invalid_structured_strategy_rejected():
    with pytest.raises(ValueError, match="structured_strategy"):
        RunnableLLMGraphAgent(_agent(), structured_strategy="bogus")


# --- execute (aw.AgenticStep shape) -----------------------------------------


def test_execute_uses_native_structured_response_dict():
    r = realize(
        _agent(schema=_SCHEMA),
        backend="langgraph",
        factory=_graph_returning(_result(structured={"a": "hi"})),
    )
    artifact, info = r.execute("task", context={})
    assert artifact == {"a": "hi"}
    assert info["backend"] == "langgraph" and info["structured_response_used"] is True


def test_execute_dumps_pydantic_like_structured_response():
    structured = SimpleNamespace(model_dump=lambda: {"a": "dumped"})
    r = realize(
        _agent(schema=_SCHEMA),
        backend="langgraph",
        factory=_graph_returning(_result(structured=structured)),
    )
    artifact, _ = r.execute("task")
    assert artifact == {"a": "dumped"}


def test_execute_falls_back_to_json_in_final_text():
    r = realize(
        _agent(schema=_SCHEMA),
        backend="langgraph",
        factory=_graph_returning(_result(text='{"a": "x"}')),
    )
    artifact, info = r.execute("task")
    assert artifact == {"a": "x"} and info["structured_response_used"] is False


def test_execute_graceful_text_when_structured_parse_fails():
    r = realize(
        _agent(schema=_SCHEMA),
        backend="langgraph",
        factory=_graph_returning(_result(text="not json")),
    )
    artifact, _ = r.execute("task")
    assert artifact == "not json"


def test_execute_returns_text_when_no_schema():
    r = realize(
        _agent(), backend="langgraph", factory=_graph_returning(_result(text="prose"))
    )
    artifact, info = r.execute("task")
    assert artifact == "prose" and info["structured"] is False


def test_execute_returns_raw_on_unexpected_shape():
    sentinel = ["not", "a", "dict"]
    r = realize(_agent(), backend="langgraph", factory=_graph_returning(sentinel))
    artifact, _ = r.execute("task")
    assert artifact is sentinel


def test_execute_tuple_shape_and_context_ignored():
    rec = {}
    r = realize(
        _agent(), backend="langgraph", factory=_graph_returning(_result(text="ok"), rec)
    )
    result = r.execute("x", context={"k": "v"})
    assert isinstance(result, tuple) and len(result) == 2 and isinstance(result[1], dict)


def test_execute_builds_state_as_user_message():
    rec = {}
    r = realize(
        _agent(), backend="langgraph", factory=_graph_returning(_result(text="ok"), rec)
    )
    r.execute("the task")
    assert rec["state"] == {"messages": [{"role": "user", "content": "the task"}]}


def test_non_string_input_rendered_as_json():
    rec = {}
    r = realize(
        _agent(), backend="langgraph", factory=_graph_returning(_result(text="ok"), rec)
    )
    r.execute({"task": "go", "n": 1})
    assert rec["state"]["messages"][0]["content"] == '{"task": "go", "n": 1}'


def test_info_keys_present():
    r = realize(
        _agent(), backend="langgraph", factory=_graph_returning(_result(text="ok"))
    )
    _, info = r.execute("x")
    for key in (
        "agent",
        "model",
        "backend",
        "structured",
        "structured_response_used",
        "unbound_tools",
        "raw",
    ):
        assert key in info


# --- tools (opt-in; names are not callables — D12) --------------------------


def test_tools_map_binds_known_names_and_surfaces_unbound():
    rec = {}

    def my_tool():
        return "x"

    r = realize(
        _agent(tools=["my_tool", "missing"]),
        backend="langgraph",
        factory=_graph_returning(_result(text="ok"), rec),
        tools_map={"my_tool": my_tool},
    )
    _, info = r.execute("x")
    assert rec["factory_kwargs"]["tools"] == [my_tool]
    assert info["unbound_tools"] == ["missing"]


def test_no_tools_map_passes_empty_tools():
    rec = {}
    r = realize(
        _agent(tools=["a", "b"]),
        backend="langgraph",
        factory=_graph_returning(_result(text="ok"), rec),
    )
    _, info = r.execute("x")
    assert rec["factory_kwargs"]["tools"] == [] and info["unbound_tools"] == []


# --- build_agent caches; default path gates on requirements -----------------


def test_build_agent_caches_across_calls():
    rec = {}
    r = realize(
        _agent(), backend="langgraph", factory=_graph_returning(_result(text="ok"), rec)
    )
    r.execute("x")
    r.execute("y")
    r.build_agent()
    assert rec["calls"] == 1  # factory invoked exactly once


def test_default_path_checks_requirements_then_uses_default_factory(monkeypatch):
    import importlib

    m = importlib.import_module("coact.realize_langgraph")
    calls = {}

    def fake_check(modules, *, feature):
        calls["modules"] = modules
        calls["feature"] = feature

    def fake_factory(**kwargs):
        calls["factory"] = True

        class _G:
            def invoke(self, state):
                return _result(text="ok")

        return _G()

    monkeypatch.setattr(m, "check_requirements", fake_check)
    monkeypatch.setattr(m, "_default_langgraph_factory", fake_factory)
    r = realize(_agent(), backend="langgraph")  # factory=None -> default path
    artifact, _ = r.execute("x")
    assert artifact == "ok"
    assert calls["modules"] == {"langchain": "langchain", "langgraph": "langgraph"}
    assert "langgraph" in calls["feature"] and calls["factory"] is True


# --- DRY: helpers reused from realize_litellm, not re-implemented -----------


def test_reuses_litellm_json_helpers_by_identity():
    from coact.realize_langgraph import _to_user_text, _try_json
    from coact.realize_litellm import _to_user_text as lit_to_user_text
    from coact.realize_litellm import _try_json as lit_try_json

    assert _try_json is lit_try_json and _to_user_text is lit_to_user_text


def test_agent_property_exposes_native_object():
    graph = object()

    def factory(**kwargs):
        return graph

    r = realize(_agent(), backend="langgraph", factory=factory)
    assert r.agent is graph  # the compiled graph, for user composition
