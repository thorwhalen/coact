"""Tests for the analysis utilities, the aw-bridged emitters, and the CLI."""

import importlib.util
import subprocess
import sys

from skill.base import Skill, SkillMeta

from coact import (
    AgentDefinition,
    back,
    complete,
    diff,
    emit_agent,
    emitters,
    estimate,
    inventory,
)

_HAS_AW = importlib.util.find_spec("aw") is not None


def _skill(name="ux", description="Analyze UX bundles.", body="steps"):
    return Skill(meta=SkillMeta(name=name, description=description), body=body)


# ---------------------------------------------------------------------------
# diff
# ---------------------------------------------------------------------------


def test_diff_classifies_extras():
    s = _skill()
    d = diff(s, complete(s))
    by_field = {f: cls for f, cls, _ in d.rows}
    assert by_field["name"] == "from skill"
    assert by_field["description"] == "from skill"
    assert by_field["skills"] == "from skill"
    assert by_field["prompt"].startswith("extra")
    assert by_field["returns"].startswith("extra")
    assert "ux" in d.render()


# ---------------------------------------------------------------------------
# estimate — the cost gate
# ---------------------------------------------------------------------------


def test_estimate_single_agent_cheap():
    est = estimate(AgentDefinition(name="a", description="x"))
    assert est.n_agents == 1
    assert est.token_multiplier_vs_chat == 4.0
    assert not est.interdependent
    assert "host" in est.recommendation


def test_estimate_flags_interdependent_shared_skill():
    a = AgentDefinition(name="a", description="x", skills=["shared", "a"])
    b = AgentDefinition(name="b", description="y", skills=["shared", "b"])
    est = estimate([a, b])
    assert est.interdependent
    assert est.shared_skills == ["shared"]
    assert "POOR fit" in est.render()


def test_estimate_independent_fleet():
    a = AgentDefinition(name="a", description="x", skills=["a"])
    b = AgentDefinition(name="b", description="y", skills=["b"])
    est = estimate([a, b])
    assert not est.interdependent
    assert est.token_multiplier_vs_chat == 8.0


def test_estimate_consumes_marks_interdependent():
    a = AgentDefinition(name="a", description="x", consumes="bundle")
    assert estimate([a, AgentDefinition(name="b", description="y")]).interdependent


# ---------------------------------------------------------------------------
# inventory
# ---------------------------------------------------------------------------


def test_inventory_enumerates_skills_agents_mcp(tmp_path):
    skills = tmp_path / ".claude" / "skills"
    (skills / "ux").mkdir(parents=True)
    (skills / "ux" / "SKILL.md").write_text(
        """---
name: ux
description: UX.
coact:
  mcp:
    - module: os.path
      functions: [basename]
---
# ux
body
"""
    )
    agents = tmp_path / ".claude" / "agents"
    emit_agent(complete(_skill()), "claude-agents-md", dest=agents)

    inv = inventory(tmp_path)
    assert inv.skills == ["ux"]
    assert inv.agents == ["ux"]
    assert inv.mcp_tools == ["ux: os.path:basename"]
    assert "skills (1)" in inv.render()


# ---------------------------------------------------------------------------
# back — lossy
# ---------------------------------------------------------------------------


def test_back_extracts_lossy_skill_stub():
    ad = AgentDefinition(name="ux", description="Analyze.", skills=["ux", "shared"])
    sk = back(ad)
    assert sk.meta.name == "ux"
    assert "lossy" in sk.body.lower()
    assert "shared" in sk.body  # referenced skills noted


# ---------------------------------------------------------------------------
# aw-bridged emitters (reuse aw's *_from_spec renderers)
# ---------------------------------------------------------------------------


def test_aw_emitters_registered_when_aw_present():
    if not _HAS_AW:
        return
    assert "crewai" in emitters
    assert "openai-tools" in emitters
    ad = complete(_skill())
    crew = emit_agent(ad, "crewai")
    assert "ux" in crew
    tools = emit_agent(ad, "openai-tools")
    assert isinstance(tools, list)


# ---------------------------------------------------------------------------
# CLI smoke (exercises argh dispatch end-to-end)
# ---------------------------------------------------------------------------


def _run_cli(*args, cwd=None):
    return subprocess.run(
        [sys.executable, "-m", "coact", *args],
        capture_output=True,
        text=True,
        cwd=cwd,
    )


def test_cli_plan_and_complete(tmp_path):
    skill_dir = tmp_path / "ux"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\nname: ux\ndescription: Analyze bundles.\n---\n# ux\nbody\n"
    )
    out = _run_cli("plan", str(skill_dir))
    assert out.returncode == 0, out.stderr
    assert "AgentPlan for 'ux'" in out.stdout

    out = _run_cli("complete", str(skill_dir))
    assert out.returncode == 0, out.stderr
    assert out.stdout.startswith("---")
    assert "name: ux" in out.stdout


def test_cli_inventory(tmp_path):
    out = _run_cli("inventory", str(tmp_path))
    assert out.returncode == 0, out.stderr
    assert "inventory:" in out.stdout
