"""Tests for REALIZE: the host backend (file materialization) and the sdk backend."""

import importlib.util

import pytest
from skill.base import Skill, SkillMeta

from coact import (
    AgentDefinition,
    ReturnContract,
    RunnableAgent,
    realize,
    realize_host,
)
from coact.realize import coerce_agents

_HAS_SDK = importlib.util.find_spec("claude_agent_sdk") is not None


def _agent(name="ux", skills=("ux",), **kw):
    return AgentDefinition(
        name=name,
        description="Analyze.",
        prompt="You are the ux agent.",
        skills=list(skills),
        **kw,
    )


# ---------------------------------------------------------------------------
# target coercion
# ---------------------------------------------------------------------------


def test_coerce_agent_definition_passthrough():
    ad = _agent()
    assert coerce_agents(ad) == [ad]


def test_coerce_skill_completes_it():
    s = Skill(
        meta=SkillMeta(name="auditor", description="Audit the bundle."), body="steps"
    )
    out = coerce_agents(s)
    assert len(out) == 1 and out[0].name == "auditor"


def test_coerce_list_flattens():
    out = coerce_agents([_agent("a"), _agent("b")])
    assert [a.name for a in out] == ["a", "b"]


def test_coerce_agent_md_file(tmp_path):
    from coact import emit_agent

    p = emit_agent(_agent("written"), "claude-agents-md", dest=tmp_path)
    out = coerce_agents(p)
    assert out[0].name == "written"


# ---------------------------------------------------------------------------
# host backend — materialize + verify
# ---------------------------------------------------------------------------


def test_host_writes_agent_files(tmp_path):
    res = realize_host(_agent("ux"), dest=tmp_path / "agents", link=False)
    assert (tmp_path / "agents" / "ux.md").exists()
    assert res.agents["ux"].name == "ux.md"
    assert res.warnings == []


def test_host_links_referenced_skill(tmp_path):
    # a real skill on disk that the agent references
    skills_src = tmp_path / "src_skills" / "ux"
    skills_src.mkdir(parents=True)
    (skills_src / "SKILL.md").write_text(
        "---\nname: ux\ndescription: UX.\n---\n# ux\nbody\n"
    )
    agents_out = tmp_path / "proj" / ".claude" / "agents"

    # complete the on-disk skill, then realize pointing at where its skill lives
    from coact import complete

    ad = complete(skills_src)
    res = realize_host(
        ad, dest=agents_out, link=True, skills_source=tmp_path / "src_skills"
    )
    linked = agents_out.parent / "skills" / "ux"
    assert linked.is_symlink()
    assert linked.resolve() == skills_src.resolve()
    assert res.skills["ux"] == linked
    assert res.warnings == []


def test_host_warns_on_unresolvable_skill(tmp_path):
    ad = _agent("x", skills=["does-not-exist-skill-xyz"])
    res = realize_host(ad, dest=tmp_path / "agents", link=True)
    assert any("could not be resolved" in w for w in res.warnings)


def test_realize_dispatch_unknown_backend_raises():
    with pytest.raises(ValueError, match="Unknown realize backend"):
        realize(_agent(), backend="nope")


# ---------------------------------------------------------------------------
# sdk backend — aw.AgenticStep-compatible, runner injected (no live API)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _HAS_SDK, reason="claude_agent_sdk not installed")
def test_sdk_realize_returns_runnable_agent():
    runnable = realize(_agent(model="haiku"), backend="sdk")
    assert isinstance(runnable, RunnableAgent)
    # structurally satisfies aw.AgenticStep: execute(input_data, context) -> tuple
    assert hasattr(runnable, "execute")


@pytest.mark.skipif(not _HAS_SDK, reason="claude_agent_sdk not installed")
def test_sdk_build_options_maps_fields():
    ad = _agent(
        model="sonnet",
        tools=["Read", "Grep"],
        returns=ReturnContract(json_schema={"type": "object"}),
    )
    opts = realize(ad, backend="sdk").build_options()
    assert opts.system_prompt == ad.prompt
    assert opts.allowed_tools == ["Read", "Grep"]
    assert opts.model == "sonnet"
    # output_format must be the SDK's json_schema wrapper, not a bare schema.
    assert opts.output_format == {"type": "json_schema", "schema": {"type": "object"}}


@pytest.mark.skipif(not _HAS_SDK, reason="claude_agent_sdk not installed")
def test_sdk_execute_with_injected_runner_no_api():
    captured = {}

    def fake_runner(prompt, options):
        captured["prompt"] = prompt
        captured["system_prompt"] = options.system_prompt
        return "the structured result"

    runnable = realize(_agent(), backend="sdk", runner=fake_runner)
    artifact, info = runnable.execute("analyze this bundle", context={})
    assert artifact == "the structured result"
    assert info["agent"] == "ux"
    assert info["backend"] == "sdk"
    assert captured["prompt"] == "analyze this bundle"


@pytest.mark.skipif(not _HAS_SDK, reason="claude_agent_sdk not installed")
def test_sdk_satisfies_aw_agentic_step_duck_type():
    # aw.AgenticStep is a Protocol; verify our object is usable where one is
    # expected by exercising the (input_data, context) -> (artifact, info) shape.
    runnable = realize(_agent(), backend="sdk", runner=lambda p, o: "ok")
    result = runnable.execute("x", {})
    assert isinstance(result, tuple) and len(result) == 2
    artifact, info = result
    assert isinstance(info, dict)


def test_sdk_rejects_multiple_agents():
    with pytest.raises(ValueError, match="exactly one agent"):
        realize([_agent("a"), _agent("b")], backend="sdk")


# ---------------------------------------------------------------------------
# D6 return contract — tool fallback (forced return_result tool)
# ---------------------------------------------------------------------------


def _msg(*blocks):
    """A minimal stand-in for an SDK AssistantMessage carrying tool-use blocks."""
    from types import SimpleNamespace

    return SimpleNamespace(content=list(blocks))


def _tool_block(name, payload):
    from types import SimpleNamespace

    return SimpleNamespace(name=name, input=payload)


def test_auto_return_mode_prefers_output_format_then_tool():
    from coact.realize import auto_return_mode

    assert auto_return_mode({"system_prompt", "output_format"}) == "output_format"
    assert auto_return_mode({"system_prompt", "model"}) == "tool"


def test_as_object_schema_passes_object_through_and_wraps_others():
    from coact.realize import as_object_schema

    obj = {"type": "object", "properties": {"score": {"type": "number"}}}
    assert as_object_schema(obj) == (obj, None)
    wrapped, key = as_object_schema({"type": "array", "items": {"type": "string"}})
    assert key == "result"
    assert wrapped["properties"]["result"] == {
        "type": "array",
        "items": {"type": "string"},
    }
    assert wrapped["required"] == ["result"]


@pytest.mark.skipif(not _HAS_SDK, reason="claude_agent_sdk not installed")
def test_sdk_tool_fallback_wires_return_tool_and_instruction():
    from coact.realize import RETURN_TOOL_FULLNAME, RETURN_TOOL_SERVER

    schema = {"type": "object", "properties": {"score": {"type": "number"}}}
    ad = _agent(returns=ReturnContract(json_schema=schema, description="a score"))
    runnable = realize(ad, backend="sdk", return_mode="tool")
    opts = runnable.build_options()

    assert RETURN_TOOL_SERVER in opts.mcp_servers
    assert RETURN_TOOL_FULLNAME in opts.allowed_tools
    # the instruction names the tool and embeds the schema; no output_format used
    assert "return_result" in opts.system_prompt
    assert "score" in opts.system_prompt
    assert getattr(opts, "output_format", None) is None


@pytest.mark.skipif(not _HAS_SDK, reason="claude_agent_sdk not installed")
def test_sdk_tool_fallback_extracts_structured_result():
    from coact.realize import RETURN_TOOL_FULLNAME

    schema = {"type": "object", "properties": {"score": {"type": "number"}}}
    ad = _agent(returns=ReturnContract(json_schema=schema))
    payload = {"score": 0.9}

    def fake_runner(prompt, options):
        # the model "calls" the forced return tool; that input is the result
        return [_msg(_tool_block(RETURN_TOOL_FULLNAME, payload))]

    runnable = realize(ad, backend="sdk", runner=fake_runner, return_mode="tool")
    artifact, info = runnable.execute("analyze", {})
    assert artifact == payload
    assert info["return_mode"] == "tool"


@pytest.mark.skipif(not _HAS_SDK, reason="claude_agent_sdk not installed")
def test_sdk_tool_fallback_unwraps_non_object_schema():
    # a top-level array return type is wrapped under `result` and unwrapped back
    ad = _agent(
        returns=ReturnContract(
            json_schema={"type": "array", "items": {"type": "string"}}
        )
    )

    def fake_runner(prompt, options):
        from coact.realize import RETURN_TOOL_FULLNAME

        return [_msg(_tool_block(RETURN_TOOL_FULLNAME, {"result": ["a", "b"]}))]

    runnable = realize(ad, backend="sdk", runner=fake_runner, return_mode="tool")
    artifact, _ = runnable.execute("go", {})
    assert artifact == ["a", "b"]


@pytest.mark.skipif(not _HAS_SDK, reason="claude_agent_sdk not installed")
def test_sdk_tool_fallback_ignores_other_tool_calls():
    from coact.realize import RETURN_TOOL_FULLNAME

    ad = _agent(
        returns=ReturnContract(json_schema={"type": "object", "properties": {}})
    )

    def fake_runner(prompt, options):
        return [
            _msg(_tool_block("Read", {"path": "x"})),
            _msg(_tool_block(RETURN_TOOL_FULLNAME, {"ok": True})),
        ]

    runnable = realize(ad, backend="sdk", runner=fake_runner, return_mode="tool")
    artifact, _ = runnable.execute("go", {})
    assert artifact == {"ok": True}


@pytest.mark.skipif(not _HAS_SDK, reason="claude_agent_sdk not installed")
def test_sdk_return_mode_output_format_does_not_wrap():
    # explicit output_format keeps the schema verbatim (no result-wrapping)
    schema = {"type": "object", "properties": {"a": {"type": "string"}}}
    ad = _agent(returns=ReturnContract(json_schema=schema))
    opts = realize(ad, backend="sdk", return_mode="output_format").build_options()
    assert opts.output_format == {"type": "json_schema", "schema": schema}


@pytest.mark.skipif(not _HAS_SDK, reason="claude_agent_sdk not installed")
def test_sdk_unknown_return_mode_raises():
    ad = _agent(
        returns=ReturnContract(json_schema={"type": "object", "properties": {}})
    )
    with pytest.raises(ValueError, match="Unknown return_mode"):
        realize(ad, backend="sdk", return_mode="bogus").build_options()


# --- review fixes: helpers, naming, edge cases ------------------------------


def test_as_object_schema_does_not_wrap_free_form_object():
    # {'type':'object'} with no properties is passed through (with an empty
    # properties key), NOT wrapped — so a model's {'result': ...} can't collapse.
    from coact.realize import as_object_schema

    coerced, key = as_object_schema({"type": "object"})
    assert key is None
    assert coerced == {"type": "object", "properties": {}}


def test_is_return_tool_is_server_scoped():
    from coact.return_contract import is_return_tool

    assert is_return_tool("mcp__coact_return__return_result")
    assert not is_return_tool("mcp__other_server__return_result")
    assert not is_return_tool("return_result")  # bare name on no server
    assert not is_return_tool("Read")


def test_coerce_mcp_servers_forms():
    from coact.realize import _coerce_mcp_servers

    assert _coerce_mcp_servers([]) == ({}, [])
    assert _coerce_mcp_servers({"s": {"type": "sdk"}}) == ({"s": {"type": "sdk"}}, [])
    # inline config dict keyed by its name field
    d, w = _coerce_mcp_servers([{"name": "weather", "type": "stdio"}])
    assert d == {"weather": {"name": "weather", "type": "stdio"}} and w == []
    # bare name -> reported, not silently dropped
    d, w = _coerce_mcp_servers(["bare"])
    assert d == {} and any("bare" in m for m in w)


def test_extract_return_tool_input_last_wins_direct():
    from coact.realize import RETURN_TOOL_FULLNAME, extract_return_tool_input

    msgs = [
        _msg(_tool_block(RETURN_TOOL_FULLNAME, {"v": 1})),
        _msg(_tool_block(RETURN_TOOL_FULLNAME, {"v": 2})),
    ]
    assert extract_return_tool_input(msgs, None) == {"v": 2}


def test_extract_does_not_unwrap_when_extra_keys_present():
    from coact.realize import extract_return_tool_input

    block = _tool_block(
        "mcp__coact_return__return_result", {"result": ["a"], "extra": 1}
    )
    # the strict guard only unwraps a dict that is EXACTLY {result: ...}
    assert extract_return_tool_input([_msg(block)], "result") == {
        "result": ["a"],
        "extra": 1,
    }


# --- review fixes: behavior through the real RunnableAgent ------------------


def _sdk_without_output_format(monkeypatch):
    """Make the installed ClaudeAgentOptions appear to lack the output_format field."""
    import dataclasses as _dc
    import importlib

    realize_mod = importlib.import_module("coact.realize")
    from claude_agent_sdk import ClaudeAgentOptions

    real_fields = _dc.fields

    def fake_fields(cls):
        flds = real_fields(cls)
        if getattr(cls, "__name__", "") == "ClaudeAgentOptions":
            return tuple(f for f in flds if f.name != "output_format")
        return flds

    monkeypatch.setattr(realize_mod.dataclasses, "fields", fake_fields)
    return ClaudeAgentOptions


@pytest.mark.skipif(not _HAS_SDK, reason="claude_agent_sdk not installed")
def test_sdk_auto_falls_back_to_tool_when_sdk_lacks_output_format(monkeypatch):
    from coact.realize import RETURN_TOOL_FULLNAME, RETURN_TOOL_SERVER

    _sdk_without_output_format(monkeypatch)
    schema = {"type": "object", "properties": {"score": {"type": "number"}}}
    runnable = realize(
        _agent(returns=ReturnContract(json_schema=schema)), backend="sdk"
    )  # return_mode defaults to 'auto'
    assert runnable._resolved_return().mode == "tool"
    opts = runnable.build_options()
    assert getattr(opts, "output_format", None) is None
    assert RETURN_TOOL_SERVER in opts.mcp_servers
    assert RETURN_TOOL_FULLNAME in opts.allowed_tools


@pytest.mark.skipif(not _HAS_SDK, reason="claude_agent_sdk not installed")
def test_sdk_explicit_output_format_raises_when_sdk_lacks_field(monkeypatch):
    _sdk_without_output_format(monkeypatch)
    ad = _agent(
        returns=ReturnContract(json_schema={"type": "object", "properties": {}})
    )
    with pytest.raises(ValueError, match="no output_format option"):
        realize(ad, backend="sdk", return_mode="output_format").build_options()


@pytest.mark.skipif(not _HAS_SDK, reason="claude_agent_sdk not installed")
def test_sdk_auto_wrap_round_trip_on_old_sdk(monkeypatch):
    # the real fallback: 'auto' on an SDK without output_format, top-level array
    _sdk_without_output_format(monkeypatch)
    from coact.realize import RETURN_TOOL_FULLNAME

    ad = _agent(
        returns=ReturnContract(
            json_schema={"type": "array", "items": {"type": "string"}}
        )
    )

    def fake_runner(prompt, options):
        return [_msg(_tool_block(RETURN_TOOL_FULLNAME, {"result": ["x", "y"]}))]

    artifact, info = realize(ad, backend="sdk", runner=fake_runner).execute("go", {})
    assert artifact == ["x", "y"]
    assert info["return_mode"] == "tool"


@pytest.mark.skipif(not _HAS_SDK, reason="claude_agent_sdk not installed")
def test_sdk_unresolvable_schema_ref_raises_not_silently_dropped():
    ad = _agent(returns=ReturnContract(ref="definitely.not:Real"))
    with pytest.raises(ValueError, match="could not be resolved"):
        realize(ad, backend="sdk", return_mode="tool").build_options()


@pytest.mark.skipif(not _HAS_SDK, reason="claude_agent_sdk not installed")
def test_sdk_tool_fallback_preserves_agents_own_mcp_servers():
    from coact.realize import RETURN_TOOL_SERVER

    ad = _agent(
        mcp_servers=[{"name": "weather", "type": "stdio"}],
        returns=ReturnContract(json_schema={"type": "object", "properties": {"a": {}}}),
    )
    opts = realize(ad, backend="sdk", return_mode="tool").build_options()
    assert "weather" in opts.mcp_servers  # not clobbered by the return tool
    assert RETURN_TOOL_SERVER in opts.mcp_servers


@pytest.mark.skipif(not _HAS_SDK, reason="claude_agent_sdk not installed")
def test_sdk_return_tool_removed_from_disallowed():
    from coact.realize import RETURN_TOOL_FULLNAME

    ad = _agent(
        disallowed_tools=[RETURN_TOOL_FULLNAME],
        returns=ReturnContract(json_schema={"type": "object", "properties": {"a": {}}}),
    )
    opts = realize(ad, backend="sdk", return_mode="tool").build_options()
    assert RETURN_TOOL_FULLNAME in opts.allowed_tools
    assert RETURN_TOOL_FULLNAME not in (getattr(opts, "disallowed_tools", []) or [])


@pytest.mark.skipif(not _HAS_SDK, reason="claude_agent_sdk not installed")
def test_sdk_execute_reports_return_mode_none_and_output_format():
    # 'none': empty contract, prose result surfaces and return_mode == 'none'
    artifact, info = realize(_agent(), backend="sdk", runner=lambda p, o: "x").execute(
        "t", {}
    )
    assert artifact == "x" and info["return_mode"] == "none"
    # 'output_format': info reports the mode (structured result via injected runner)
    ad = _agent(
        returns=ReturnContract(json_schema={"type": "object", "properties": {}})
    )
    _, info2 = realize(
        ad, backend="sdk", return_mode="output_format", runner=lambda p, o: {"a": 1}
    ).execute("t", {})
    assert info2["return_mode"] == "output_format"


@pytest.mark.skipif(not _HAS_SDK, reason="claude_agent_sdk not installed")
def test_sdk_output_format_extracts_structured_output_from_result_message():
    # output_format mode: the structured result rides on ResultMessage.structured_output
    from types import SimpleNamespace

    ad = _agent(
        returns=ReturnContract(json_schema={"type": "object", "properties": {}})
    )
    payload = {"a": 1, "b": 2}

    def fake_runner(prompt, options):
        result_msg = SimpleNamespace(
            structured_output=payload, result=None, content=None
        )
        return [_msg(_tool_block(None, None)), result_msg]

    artifact, info = realize(
        ad, backend="sdk", return_mode="output_format", runner=fake_runner
    ).execute("t", {})
    assert artifact == payload
    assert info["return_mode"] == "output_format"


@pytest.mark.skipif(not _HAS_SDK, reason="claude_agent_sdk not installed")
def test_sdk_tool_mode_falls_back_to_text_when_tool_not_called():
    # model ignores the forced tool and answers in prose -> surface the text
    ad = _agent(
        returns=ReturnContract(json_schema={"type": "object", "properties": {}})
    )

    def fake_runner(prompt, options):
        from types import SimpleNamespace

        text = SimpleNamespace(name=None, input=None, text="part1")
        text2 = SimpleNamespace(name=None, input=None, text="part2")
        return [_msg(text), _msg(text2)]

    artifact, info = realize(
        ad, backend="sdk", runner=fake_runner, return_mode="tool"
    ).execute("t", {})
    assert artifact == "part1\npart2"
    assert info["return_mode"] == "tool"


# ---------------------------------------------------------------------------
# host backend — dry_run preview (progressive disclosure)
# ---------------------------------------------------------------------------


def test_host_dry_run_previews_without_writing(tmp_path):
    dest = tmp_path / "proj" / ".claude" / "agents"
    res = realize_host(_agent("ux"), dest=dest, link=False, dry_run=True)
    assert res.dry_run is True
    assert res.agents["ux"] == dest / "ux.md"  # the path that WOULD be written
    assert not dest.exists()  # nothing materialized
    assert res.warnings == []


def test_host_dry_run_previews_skill_link(tmp_path):
    skills_src = tmp_path / "src_skills" / "ux"
    skills_src.mkdir(parents=True)
    (skills_src / "SKILL.md").write_text("---\nname: ux\ndescription: UX.\n---\n# ux\nb\n")
    agents_out = tmp_path / "proj" / ".claude" / "agents"
    from coact import complete

    res = realize_host(
        complete(skills_src),
        dest=agents_out,
        link=True,
        skills_source=tmp_path / "src_skills",
        dry_run=True,
    )
    would_link = agents_out.parent / "skills" / "ux"
    assert res.skills["ux"] == would_link  # predicted link path
    assert not would_link.exists()  # but no symlink created
    assert res.warnings == []


def test_host_dry_run_still_warns_on_unresolvable_skill(tmp_path):
    res = realize_host(
        _agent("x", skills=["nope-skill-xyz"]),
        dest=tmp_path / "agents",
        link=True,
        dry_run=True,
    )
    assert any("could not be resolved" in w for w in res.warnings)
    assert not (tmp_path / "agents").exists()


def test_realize_dispatch_passes_dry_run_through(tmp_path):
    dest = tmp_path / "a"
    res = realize(_agent("ux"), backend="host", dest=dest, link=False, dry_run=True)
    assert res.dry_run is True and not dest.exists()
