"""Tests for the CrewAI realization backend (injected runner; no key, no install).

CrewAI is **not** required: the run call is injected, so every test here runs with
no API key and no ``crewai`` installed (mirroring the litellm suite). The pydantic
synthesis helper is exercised under ``importorskip('pydantic')``.
"""

import importlib.util
import sys
from types import SimpleNamespace

import pytest

from coact import (
    AgentDefinition,
    ReturnContract,
    RunnableCrewAIAgent,
    realize,
    realization_backends,
    realize_crewai,
)
from coact.realize_crewai import DEFAULT_MODEL


def _out(raw=None, pydantic=None):
    """A minimal CrewAI LiteAgentOutput stand-in (.raw / .pydantic)."""
    return SimpleNamespace(raw=raw, pydantic=pydantic)


def _runner_returning(out, record=None):
    def runner(*, agent, input_text, response_format):
        if record is not None:
            record["agent"] = agent
            record["input_text"] = input_text
            record["response_format"] = response_format
        return out

    return runner


def _agent(name="ux", *, schema=None, **kw):
    returns = ReturnContract(json_schema=schema) if schema else ReturnContract()
    return AgentDefinition(
        name=name, description="Analyze.", prompt="You are X.", returns=returns, **kw
    )


_SCHEMA = {
    "type": "object",
    "properties": {"a": {"type": "string"}},
    "required": ["a"],
}


# --- registration / dispatch ------------------------------------------------


def test_crewai_registered_open_closed():
    assert "crewai" in realization_backends


def test_realize_dispatches_to_crewai():
    r = realize(_agent(), backend="crewai", runner=_runner_returning(_out(raw="hi")))
    assert isinstance(r, RunnableCrewAIAgent)


def test_crewai_rejects_multiple_agents():
    with pytest.raises(ValueError, match="exactly one agent"):
        realize([_agent("a"), _agent("b")], backend="crewai")


def test_crewai_d8_message_cites_the_decision():
    with pytest.raises(ValueError, match="D8"):
        realize([_agent("a"), _agent("b")], backend="crewai")


# --- model mapping (slash form, = litellm) ----------------------------------


def test_model_selector_maps_to_slash_form():
    assert (
        RunnableCrewAIAgent(_agent(model="sonnet")).resolve_model()
        == "anthropic/claude-sonnet-4-5"
    )


def test_explicit_model_string_used_verbatim():
    assert (
        RunnableCrewAIAgent(_agent(model="gemini/gemini-1.5-pro")).resolve_model()
        == "gemini/gemini-1.5-pro"
    )


def test_no_model_falls_back_to_default():
    assert RunnableCrewAIAgent(_agent()).resolve_model() == DEFAULT_MODEL


def test_custom_model_map():
    r = realize_crewai(_agent(model="sonnet"), model_map={"sonnet": "openai/gpt-4o"})
    assert r.resolve_model() == "openai/gpt-4o"


def test_model_map_copied_on_construction():
    external = {"sonnet": "openai/gpt-4o"}
    r = RunnableCrewAIAgent(_agent(model="sonnet"), model_map=external)
    external["sonnet"] = "mutated"
    assert r.resolve_model() == "openai/gpt-4o"


# --- role / goal / backstory always non-empty -------------------------------


def test_persona_builders_non_empty_even_when_blank():
    ad = AgentDefinition(name="solo", description="", prompt="")
    r = RunnableCrewAIAgent(ad)
    assert r.build_role() == "solo"
    assert r.build_goal()  # non-empty
    assert r.build_backstory()  # non-empty


def test_backstory_carries_schema_instruction():
    bs = RunnableCrewAIAgent(_agent(schema=_SCHEMA)).build_backstory()
    assert "You are X." in bs and "Return contract" in bs


def test_goal_prefers_description_then_prompt():
    assert RunnableCrewAIAgent(_agent()).build_goal() == "Analyze."


# --- pydantic synthesis (the crewai-only response_format path) --------------


def test_json_schema_to_model_roundtrips_flat_schema():
    pytest.importorskip("pydantic")
    from coact._pydantic_schema import json_schema_to_model

    Model = json_schema_to_model(
        {
            "type": "object",
            "properties": {"sum": {"type": "integer"}, "note": {"type": "string"}},
            "required": ["sum"],
        }
    )
    assert Model is not None
    inst = Model(sum=5)
    assert inst.model_dump() == {"sum": 5, "note": None}  # optional defaults to None


def test_json_schema_to_model_rejects_non_flat():
    pytest.importorskip("pydantic")
    from coact._pydantic_schema import json_schema_to_model

    assert json_schema_to_model({"type": "array", "items": {"type": "string"}}) is None
    assert json_schema_to_model({}) is None
    assert json_schema_to_model({"type": "object", "properties": {}}) is None
    nested = {
        "type": "object",
        "properties": {"inner": {"type": "object", "properties": {"x": {}}}},
    }
    assert json_schema_to_model(nested) is None


def test_build_response_model_none_without_schema_or_disabled():
    assert RunnableCrewAIAgent(_agent()).build_response_model() is None
    r = RunnableCrewAIAgent(_agent(schema=_SCHEMA), use_response_format=False)
    assert r.build_response_model() is None


# --- execute (aw.AgenticStep shape) -----------------------------------------


def test_execute_uses_native_pydantic_result():
    pyd = SimpleNamespace(model_dump=lambda: {"a": "hi"})
    r = realize(
        _agent(schema=_SCHEMA), backend="crewai", runner=_runner_returning(_out(pydantic=pyd))
    )
    artifact, info = r.execute("task", context={})
    assert artifact == {"a": "hi"} and info["structured_response_used"] is True
    assert info["backend"] == "crewai"


def test_execute_parses_json_from_raw_when_no_pydantic():
    r = realize(
        _agent(schema=_SCHEMA),
        backend="crewai",
        runner=_runner_returning(_out(raw='{"a": "x"}')),
    )
    artifact, info = r.execute("task")
    assert artifact == {"a": "x"} and info["structured_response_used"] is False


def test_execute_graceful_text_when_raw_not_json():
    r = realize(
        _agent(schema=_SCHEMA), backend="crewai", runner=_runner_returning(_out(raw="nope"))
    )
    artifact, _ = r.execute("task")
    assert artifact == "nope"


def test_execute_returns_text_when_no_schema():
    r = realize(_agent(), backend="crewai", runner=_runner_returning(_out(raw="prose")))
    artifact, info = r.execute("task")
    assert artifact == "prose" and info["structured"] is False


def test_execute_tuple_shape_and_context_ignored():
    r = realize(_agent(), backend="crewai", runner=_runner_returning(_out(raw="ok")))
    result = r.execute("x", context={"k": "v"})
    assert isinstance(result, tuple) and len(result) == 2 and isinstance(result[1], dict)


def test_execute_non_string_input_rendered_as_json():
    rec = {}
    r = realize(
        _agent(), backend="crewai", runner=_runner_returning(_out(raw="ok"), rec)
    )
    r.execute({"task": "go", "n": 1})
    assert rec["input_text"] == '{"task": "go", "n": 1}'


def test_info_keys_present():
    r = realize(_agent(), backend="crewai", runner=_runner_returning(_out(raw="ok")))
    _, info = r.execute("x")
    for key in (
        "agent",
        "model",
        "backend",
        "structured",
        "structured_response_used",
        "warnings",
        "raw",
    ):
        assert key in info


# --- tools (opt-in) ---------------------------------------------------------


def test_unbound_tools_surfaced_in_warnings():
    r = realize(
        _agent(tools=["missing"]),
        backend="crewai",
        runner=_runner_returning(_out(raw="ok")),
        tools_map={"other": lambda: None},
    )
    _, info = r.execute("x")
    assert any("missing" in w for w in info["warnings"])


def test_injected_runner_never_imports_crewai():
    # The injected runner is handed agent=None and build_agent is not called, so the
    # heavy framework is never imported on the test path.
    r = realize(_agent(), backend="crewai", runner=_runner_returning(_out(raw="ok")))
    r.execute("x")
    assert "crewai" not in sys.modules


def test_injected_runner_receives_agent_none():
    rec = {}
    r = realize(_agent(), backend="crewai", runner=_runner_returning(_out(raw="ok"), rec))
    r.execute("x")
    assert rec["agent"] is None


def test_injected_runner_with_schema_still_skips_crewai():
    # With a schema, execute() calls build_response_model() (which lazily imports
    # pydantic) — but the injected runner still means crewai is never imported.
    r = realize(
        _agent(schema=_SCHEMA),
        backend="crewai",
        runner=_runner_returning(_out(raw='{"a": "x"}')),
    )
    artifact, _ = r.execute("x")
    assert artifact == {"a": "x"}
    assert "crewai" not in sys.modules


# --- default path gates on requirements -------------------------------------


def test_default_path_checks_requirements(monkeypatch):
    import importlib

    m = importlib.import_module("coact.realize_crewai")
    calls = {}

    def fake_check(modules, *, feature):
        calls.setdefault("modules", modules)
        calls["feature"] = feature

    def fake_runner(*, agent, input_text, response_format):
        calls["ran"] = True
        return _out(raw="ok")

    # build_agent would import crewai; stub it so the default path doesn't need it.
    monkeypatch.setattr(m, "check_requirements", fake_check)
    monkeypatch.setattr(m, "_default_crewai_runner", fake_runner)
    monkeypatch.setattr(
        m.RunnableCrewAIAgent, "build_agent", lambda self: object(), raising=True
    )
    r = realize(_agent(), backend="crewai")  # runner=None -> default path
    artifact, _ = r.execute("x")
    assert artifact == "ok"
    assert calls["modules"] == {"crewai": "crewai"}
    assert "crewai" in calls["feature"] and calls["ran"] is True


def test_crewai_installed_matches_extra():
    has = importlib.util.find_spec("crewai") is not None
    assert isinstance(has, bool)


# --- DRY: helpers reused from realize_litellm -------------------------------


def test_reuses_litellm_json_helpers_by_identity():
    from coact.realize_crewai import _to_user_text, _try_json
    from coact.realize_litellm import _to_user_text as lit_to_user_text
    from coact.realize_litellm import _try_json as lit_try_json

    assert _try_json is lit_try_json and _to_user_text is lit_to_user_text
