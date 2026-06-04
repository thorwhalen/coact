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
from coact.realize import _coerce_agents

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
    assert _coerce_agents(ad) == [ad]


def test_coerce_skill_completes_it():
    s = Skill(meta=SkillMeta(name="auditor", description="Audit the bundle."), body="steps")
    out = _coerce_agents(s)
    assert len(out) == 1 and out[0].name == "auditor"


def test_coerce_list_flattens():
    out = _coerce_agents([_agent("a"), _agent("b")])
    assert [a.name for a in out] == ["a", "b"]


def test_coerce_agent_md_file(tmp_path):
    from coact import emit_agent

    p = emit_agent(_agent("written"), "claude-agents-md", dest=tmp_path)
    out = _coerce_agents(p)
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
