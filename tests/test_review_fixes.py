"""Regression tests for the adversarial-review findings (PR F).

Each test pins a specific confirmed defect so it cannot silently return.
"""

import importlib.util
import os

import pytest
from skill.base import Skill, SkillMeta

from coact import AgentDefinition, ReturnContract, complete, plan_completion, realize
from coact.base import resolve_schema_ref
from coact.emit import to_sdk_agent_dict
from coact.llm import _extract_json
from coact.policy import CompletionPolicy
from coact.realize import _link_skill

_HAS_SDK = importlib.util.find_spec("claude_agent_sdk") is not None


# --- tools=[] vs None in the SDK emit -------------------------------------


@pytest.mark.skipif(not _HAS_SDK, reason="claude_agent_sdk not installed")
def test_sdk_dict_preserves_empty_tools_vs_none():
    no_tools = to_sdk_agent_dict(AgentDefinition(name="a", description="d", tools=[]))
    inherit = to_sdk_agent_dict(AgentDefinition(name="b", description="d", tools=None))
    assert no_tools["agent_kwargs"].get("tools") == []  # explicit lockdown survives
    assert "tools" not in inherit["agent_kwargs"]  # None = inherit all = omit


# --- schema_ref resolution (D6) -------------------------------------------


def test_resolve_schema_ref_dataclass_and_bad():
    schema = resolve_schema_ref("coact.base:ReturnContract")
    assert schema["type"] == "object" and "properties" in schema
    assert resolve_schema_ref("nope.nope:Nothing") is None


def test_return_contract_schema_resolves_ref():
    rc = ReturnContract(ref="coact.base:AgentDefinition")
    assert "properties" in rc.schema()
    assert ReturnContract(json_schema={"type": "object"}).schema() == {"type": "object"}


def test_complete_resolves_schema_ref_into_json_schema(tmp_path):
    skill_dir = tmp_path / "ref-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\nname: ref-skill\ndescription: Uses a schema ref.\n"
        "coact:\n  returns:\n    schema_ref: coact.base:ReturnContract\n---\n# x\nbody\n"
    )
    ad = complete(skill_dir)
    assert ad.returns.ref == "coact.base:ReturnContract"
    assert ad.returns.json_schema.get("type") == "object"  # resolved, not empty


def test_complete_warns_on_unresolvable_schema_ref(tmp_path):
    skill_dir = tmp_path / "bad-ref"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\nname: bad-ref\ndescription: Bad ref.\n"
        "coact:\n  returns:\n    schema_ref: nope.nope:Nothing\n---\n# x\nbody\n"
    )
    plan = plan_completion(skill_dir)
    assert any("could not be resolved" in w for w in plan.warnings)


@pytest.mark.skipif(not _HAS_SDK, reason="claude_agent_sdk not installed")
def test_build_options_wraps_and_resolves_ref():
    ad = AgentDefinition(
        name="r", description="d", returns=ReturnContract(ref="coact.base:ReturnContract")
    )
    opts = realize(ad, backend="sdk").build_options()
    assert opts.output_format["type"] == "json_schema"
    assert "properties" in opts.output_format["schema"]


# --- _link_skill safety ----------------------------------------------------


def test_link_skill_force_does_not_destroy_when_unresolvable(tmp_path):
    target = tmp_path / "skills"
    target.mkdir()
    # a coact-style symlink pointing somewhere valid
    real = tmp_path / "real-ux"
    real.mkdir()
    (real / "SKILL.md").write_text("---\nname: ux\ndescription: d.\n---\n# ux\nb\n")
    os.symlink(real, target / "ux")
    # force re-link, but the skill name can't be resolved from any source
    result = _link_skill("ux", target, sources=[], force=True)
    # the existing working link must NOT have been destroyed
    assert (target / "ux").exists()
    assert result == target / "ux"


def test_link_skill_relinks_broken_symlink(tmp_path):
    target = tmp_path / "skills"
    target.mkdir()
    # dangling symlink
    os.symlink(tmp_path / "gone", target / "ux")
    assert (target / "ux").is_symlink() and not (target / "ux").exists()
    # a real source exists in a sources dir
    src = tmp_path / "src"
    (src / "ux").mkdir(parents=True)
    (src / "ux" / "SKILL.md").write_text("---\nname: ux\ndescription: d.\n---\n# ux\nb\n")
    result = _link_skill("ux", target, sources=[src])
    assert result is not None
    assert (target / "ux").exists()  # now resolves
    assert (target / "ux").resolve() == (src / "ux").resolve()


def test_link_skill_never_touches_real_in_place_dir(tmp_path):
    target = tmp_path / "skills"
    (target / "ux").mkdir(parents=True)
    (target / "ux" / "SKILL.md").write_text("---\nname: ux\ndescription: d.\n---\n# ux\nb\n")
    result = _link_skill("ux", target, sources=[], force=True)
    assert result == target / "ux"
    assert (target / "ux").is_dir() and not (target / "ux").is_symlink()


# --- policy opus keyword matching ------------------------------------------


def test_opus_routing_plan_punctuation_matches():
    p = CompletionPolicy()
    assert p.choose_model(tools=["Read"], description="Planning phase.", n_skills=1)[0] == "opus"
    assert p.choose_model(tools=["Read"], description="Make a plan.", n_skills=1)[0] == "opus"


def test_opus_routing_no_false_positive_on_designer_designate():
    p = CompletionPolicy()
    # read-only tools, 'designer'/'designate' must NOT trigger opus -> haiku
    assert p.choose_model(tools=["Read"], description="A designer of widgets.", n_skills=1)[0] == "haiku"
    assert p.choose_model(tools=["Read"], description="Designate the owner.", n_skills=1)[0] == "haiku"
    # but a real 'design' word does route to opus
    assert p.choose_model(tools=["Read"], description="Design the schema.", n_skills=1)[0] == "opus"


# --- _extract_json balanced braces -----------------------------------------


def test_extract_json_handles_trailing_brace_prose():
    assert _extract_json('Result: {"a": 1}. Note: use {braces} carefully.') == {"a": 1}
    assert _extract_json('```json\n{"b": 2}\n```') == {"b": 2}
    assert _extract_json('{"nested": {"x": 1}} and more {junk}') == {"nested": {"x": 1}}


# --- inventory missing module guard ----------------------------------------


def test_inventory_skips_mcp_entry_without_module(tmp_path):
    from coact import inventory

    skills = tmp_path / ".claude" / "skills" / "broken"
    skills.mkdir(parents=True)
    (skills / "SKILL.md").write_text(
        "---\nname: broken\ndescription: d.\n"
        "coact:\n  mcp:\n    - functions: [do_thing]\n---\n# x\nb\n"
    )
    inv = inventory(tmp_path)
    assert inv.mcp_tools == []  # no 'broken: None:do_thing'


def _skill():
    return Skill(meta=SkillMeta(name="ux", description="Analyze."), body="steps")
