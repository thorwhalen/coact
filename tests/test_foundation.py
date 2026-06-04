"""Tests for the coact foundation: SSOT model, emitters, frontmatter, stores."""

import importlib.util

import pytest

_HAS_SDK = importlib.util.find_spec("claude_agent_sdk") is not None

from coact import (
    AgentDefinition,
    AgentPlan,
    AgentStore,
    FieldProvenance,
    ReturnContract,
    emit_agent,
    emitters,
    from_claude_agent_md,
    parse_coact_meta,
    to_claude_agent_md,
    validate_coact_block,
)


# ---------------------------------------------------------------------------
# base
# ---------------------------------------------------------------------------


def test_return_contract_roundtrip_dict():
    rc = ReturnContract(json_schema={"type": "object"}, description="out")
    assert ReturnContract.from_dict(rc.to_dict()).json_schema == {"type": "object"}
    assert ReturnContract.from_dict({"schema_ref": "m:N"}).ref == "m:N"
    assert ReturnContract().is_empty()


def test_agent_definition_defaults():
    ad = AgentDefinition(name="x", description="y")
    assert ad.tools is None  # None means "inherit all"
    assert ad.disallowed_tools == []
    assert ad.returns.is_empty()


def test_agent_plan_render_shows_provenance():
    plan = AgentPlan(
        agent=AgentDefinition(name="x", description="y"),
        provenance=[
            FieldProvenance("model", "sonnet", "policy", "default worker"),
            FieldProvenance("tools", ["Read"], "inferred", "from scripts/"),
        ],
        warnings=["guessed model"],
    )
    out = plan.render()
    assert "model" in out and "policy" in out
    assert "tools" in out and "inferred" in out
    assert "guessed model" in out


# ---------------------------------------------------------------------------
# emit — round-trip is the load-bearing property
# ---------------------------------------------------------------------------


def _sample_agent():
    return AgentDefinition(
        name="ux-analyst",
        description="Analyze a captured UX evidence bundle for usability issues.",
        prompt="You are a meticulous UX analyst.\n\nReturn findings as specified.",
        tools=["Read", "Grep", "Glob"],
        disallowed_tools=["Bash"],
        model="sonnet",
        skills=["ux-analyst"],
        memory="project",
        permission_mode="default",
        returns=ReturnContract(
            json_schema={"type": "object", "properties": {"issues": {"type": "array"}}},
            description="Usability findings",
        ),
        consumes="evidence_bundle",
        source_skill="_local/ux-analyst",
    )


def test_claude_md_roundtrip_is_lossless():
    ad = _sample_agent()
    md = to_claude_agent_md(ad)
    back = from_claude_agent_md(md)
    assert back == ad  # full dataclass equality across all coact fields


def test_claude_md_uses_host_field_names():
    md = to_claude_agent_md(_sample_agent())
    assert "disallowedTools" in md
    assert "permissionMode" in md
    # coact-specific fields live under the additive coact: sub-block
    assert "coact:" in md
    assert "returns:" in md


def test_emit_agent_writes_file(tmp_path):
    ad = _sample_agent()
    out = emit_agent(ad, "claude-agents-md", dest=tmp_path)
    assert out == tmp_path / "ux-analyst.md"
    assert out.read_text() == to_claude_agent_md(ad)


def test_emit_agent_unknown_target_raises():
    with pytest.raises(ValueError, match="Unknown emit target"):
        emit_agent(_sample_agent(), "nope")


def test_emitters_is_registry_and_extensible():
    assert "claude-agents-md" in emitters
    assert "sdk-agent-dict" in emitters
    emitters.register("dummy", lambda ad: f"<{ad.name}>")
    assert emit_agent(_sample_agent(), "dummy") == "<ux-analyst>"
    del emitters["dummy"]


def test_tools_none_vs_empty_distinction_preserved():
    inherit = AgentDefinition(name="a", description="d", tools=None)
    none_allowed = AgentDefinition(name="b", description="d", tools=[])
    assert from_claude_agent_md(to_claude_agent_md(inherit)).tools is None
    # empty allowlist round-trips (omitted -> parsed as None is acceptable only
    # if we never wrote it). We DO omit when None; empty list is written:
    md = to_claude_agent_md(none_allowed)
    assert "tools: []" in md
    assert from_claude_agent_md(md).tools == []


@pytest.mark.skipif(not _HAS_SDK, reason="claude_agent_sdk not installed")
def test_sdk_agent_dict_filters_to_installed_fields():
    result = emit_agent(_sample_agent(), "sdk-agent-dict")
    assert result["name"] == "ux-analyst"
    kwargs = result["agent_kwargs"]
    assert kwargs["description"] and kwargs["prompt"]
    # whatever the installed SDK can't express lands in options
    import dataclasses

    from claude_agent_sdk import AgentDefinition as SDK

    accepted = {f.name for f in dataclasses.fields(SDK)}
    for k in kwargs:
        assert k in accepted


# ---------------------------------------------------------------------------
# frontmatter — the coact: convention
# ---------------------------------------------------------------------------

_SKILL_WITH_COACT = """---
name: ux-analyst
description: Analyze UX bundles.
coact:
  tools: [Read, Grep, Glob]
  model: sonnet
  memory: project
  mcp:
    - module: ov.analyzers
      functions: [score_contrast]
  returns:
    schema_ref: ov.schemas:UxFindings
    description: findings
  consumes: evidence_bundle
---
# ux-analyst

Body.
"""


def test_parse_coact_meta_from_text():
    m = parse_coact_meta(_SKILL_WITH_COACT)
    assert m.tools == ["Read", "Grep", "Glob"]
    assert m.model == "sonnet"
    assert m.memory == "project"
    assert m.mcp == [{"module": "ov.analyzers", "functions": ["score_contrast"]}]
    assert m.return_contract().ref == "ov.schemas:UxFindings"
    assert not m.is_empty()


def test_parse_coact_meta_absent_is_empty():
    assert parse_coact_meta("---\nname: x\ndescription: y\n---\nbody").is_empty()


def test_parse_coact_meta_from_skill_dir(tmp_path):
    skill_dir = tmp_path / "ux-analyst"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(_SKILL_WITH_COACT)
    m = parse_coact_meta(skill_dir)
    assert m.model == "sonnet"


def test_validate_coact_block_catches_errors():
    assert validate_coact_block({"coact": {"model": "gpt-4"}}) == [
        "coact.model: 'gpt-4' is not one of sonnet, opus, haiku, inherit"
    ]
    assert validate_coact_block({"coact": {"memory": "team"}})
    assert validate_coact_block({"coact": {"mcp": [{"functions": ["f"]}]}}) == [
        "coact.mcp[0]: missing required 'module'"
    ]
    assert validate_coact_block(
        {"coact": {"returns": {"schema_ref": "m:N", "json_schema": {"type": "object"}}}}
    )
    assert validate_coact_block({"coact": {"bogus_key": 1}})


def test_validate_coact_block_absent_passes():
    assert validate_coact_block({"name": "x"}) == []
    assert validate_coact_block({"coact": {"model": "opus"}}) == []


def test_validator_registered_into_skill():
    from skill.create import validators

    assert "coact_frontmatter" in validators


# ---------------------------------------------------------------------------
# stores
# ---------------------------------------------------------------------------


def test_agent_store_crud(tmp_path):
    store = AgentStore(root=tmp_path)
    assert len(store) == 0
    ad = _sample_agent()
    store[ad.name] = ad
    assert ad.name in store
    assert list(store) == ["ux-analyst"]
    assert store[ad.name] == ad
    del store[ad.name]
    assert len(store) == 0
    with pytest.raises(KeyError):
        store["missing"]


def test_agent_store_mapping_for_py2mcp_shape(tmp_path):
    # AgentStore is a plain MutableMapping (so mk_mcp_from_store works on it).
    from collections.abc import MutableMapping

    store = AgentStore(root=tmp_path)
    assert isinstance(store, MutableMapping)
