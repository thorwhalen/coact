"""Tests for COMPLETE: the skill→agent lift, policy routing, and dry-run provenance."""

from pathlib import Path

import pytest
from skill.base import Skill, SkillMeta

from coact import (
    AgentDefinition,
    CompletionPolicy,
    complete,
    plan_completion,
)
from coact.complete import _resolve_skill


def _skill(name="ux-analyst", description="Analyze UX bundles for issues.", body="Do the steps.", **kw):
    return Skill(meta=SkillMeta(name=name, description=description, **kw), body=body)


# ---------------------------------------------------------------------------
# mechanical completion + point-don't-copy
# ---------------------------------------------------------------------------


def test_complete_basic_fields():
    ad = complete(_skill())
    assert isinstance(ad, AgentDefinition)
    assert ad.name == "ux-analyst"
    assert ad.description == "Analyze UX bundles for issues."
    assert ad.skills == ["ux-analyst"]  # references the source skill by name
    assert not ad.returns.is_empty()  # a return contract is always synthesized


def test_persona_points_at_skill_does_not_copy_body():
    secret_body = "STEP-ONE-PROPRIETARY-PROCEDURE"
    ad = complete(_skill(body=secret_body))
    assert "ux-analyst" in ad.prompt
    assert "Return contract" in ad.prompt
    # point-don't-copy: the skill body is NOT inlined into the persona
    assert secret_body not in ad.prompt


def test_return_contract_is_present_in_prompt_and_object():
    ad = complete(_skill())
    assert ad.returns.json_schema  # structured form on the object
    assert "```json" in ad.prompt  # human/model-facing form in the persona


# ---------------------------------------------------------------------------
# policy routing (DECISIONS D4)
# ---------------------------------------------------------------------------


def test_model_routing_haiku_for_readonly():
    # default tools are Read/Grep/Glob -> read-only -> haiku
    ad = complete(_skill(description="Audit the bundle and report."))
    assert ad.model == "haiku"


def test_model_routing_opus_for_orchestration():
    ad = complete(_skill(description="Orchestrate the multi-step review."))
    assert ad.model == "opus"


def test_model_routing_sonnet_for_writer():
    ad = complete(_skill(description="Build the report file.", body="Write the output."))
    assert ad.model == "sonnet"  # Write/Edit inferred -> not read-only -> worker


def test_policy_override_changes_default_model():
    policy = CompletionPolicy().override(default_model="opus", default_tools=("Read", "Write"))
    ad = complete(_skill(description="Build a thing.", body="Write output."), policy=policy)
    assert ad.model == "opus"


# ---------------------------------------------------------------------------
# coact: frontmatter pins always win
# ---------------------------------------------------------------------------


def test_coact_block_pins_win(tmp_path):
    skill_dir = tmp_path / "ux-analyst"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        """---
name: ux-analyst
description: Analyze UX bundles.
coact:
  tools: [Read]
  model: opus
  memory: project
  persona: |
    You are a pinned persona.
  returns:
    json_schema:
      type: object
      properties:
        score: {type: number}
    description: a score
---
# ux-analyst
body
"""
    )
    plan = plan_completion(skill_dir)
    ad = plan.agent
    assert ad.tools == ["Read"]
    assert ad.model == "opus"  # pinned, not routed
    assert ad.memory == "project"
    assert ad.prompt.strip() == "You are a pinned persona."
    assert ad.returns.json_schema["properties"]["score"] == {"type": "number"}
    # provenance records the pins
    by_field = {p.field: p for p in plan.provenance}
    assert by_field["model"].source == "coact-frontmatter"
    assert by_field["prompt"].source == "coact-frontmatter"


# ---------------------------------------------------------------------------
# plan_completion provenance / warnings (inspectable before writing)
# ---------------------------------------------------------------------------


def test_plan_reports_inferred_tools_warning():
    plan = plan_completion(_skill())
    assert any("tools not declared" in w for w in plan.warnings)
    rendered = plan.render()
    assert "tools" in rendered and "inferred" in rendered


def test_plan_warns_about_declared_mcp_tools(tmp_path):
    skill_dir = tmp_path / "tooled"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        """---
name: tooled
description: Has python tools.
coact:
  mcp:
    - module: ov.analyzers
      functions: [a, b]
---
# tooled
body
"""
    )
    plan = plan_completion(skill_dir)
    assert any("realize-time" in w for w in plan.warnings)


# ---------------------------------------------------------------------------
# skill resolution
# ---------------------------------------------------------------------------


def test_resolve_skill_from_dir(tmp_path):
    skill_dir = tmp_path / "auditor"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\nname: auditor\ndescription: Audit.\n---\n# auditor\nbody\n"
    )
    s = _resolve_skill(skill_dir)
    assert s.meta.name == "auditor"
    assert _resolve_skill(skill_dir / "SKILL.md").meta.name == "auditor"


def test_resolve_skill_unresolvable_raises():
    with pytest.raises(FileNotFoundError, match="Could not resolve skill"):
        _resolve_skill("definitely-not-a-real-skill-xyz")


def test_complete_then_emit_roundtrips(tmp_path):
    from coact import emit_agent, from_claude_agent_md

    ad = complete(_skill())
    md = emit_agent(ad)  # claude-agents-md string
    back = from_claude_agent_md(md)
    assert back.name == ad.name
    assert back.skills == ad.skills
    assert back.returns.json_schema == ad.returns.json_schema
