"""Tests for the additive ``coact:`` frontmatter block + its validator.

Exercises every issue branch of :func:`coact.frontmatter.validate_coact_block`
(additive: a skill with no block, or a valid one, passes trivially) plus
``CoactMeta`` / ``parse_coact_meta`` parsing.
"""

from __future__ import annotations

import pytest

from coact.frontmatter import (
    CoactMeta,
    parse_coact_meta,
    validate_coact_block,
)


# --- parsing ----------------------------------------------------------------


def test_parse_coact_meta_from_text():
    meta = parse_coact_meta("---\nname: x\ncoact:\n  model: haiku\n---\nbody")
    assert meta.model == "haiku" and not meta.is_empty()


def test_parse_coact_meta_idempotent_on_coactmeta():
    m = CoactMeta(model="opus")
    assert parse_coact_meta(m) is m


def test_parse_coact_meta_from_dict():
    m = parse_coact_meta({"coact": {"tools": ["Read"], "consumes": "bundle"}})
    assert m.tools == ["Read"] and m.consumes == "bundle"


def test_coact_meta_non_dict_block_is_empty():
    assert CoactMeta.from_frontmatter({"coact": "not-a-mapping"}).is_empty()


def test_coact_meta_return_contract_helper():
    m = CoactMeta(returns={"schema_ref": "m:N", "description": "d"})
    rc = m.return_contract()
    assert rc.ref == "m:N" and rc.description == "d"


# --- validator: absent / valid pass ----------------------------------------


def test_validate_absent_block_passes():
    assert validate_coact_block({"name": "ok"}) == []


def test_validate_valid_block_passes():
    block = {
        "coact": {
            "tools": ["Read", "Grep"],
            "model": "sonnet",
            "memory": "project",
            "mcp": [{"module": "m", "functions": ["f"]}],
            "returns": {"json_schema": {"type": "object"}},
        }
    }
    assert validate_coact_block(block) == []


# --- validator: each issue branch ------------------------------------------


def test_validate_block_not_a_mapping():
    issues = validate_coact_block({"coact": "scalar"})
    assert any("must be a mapping" in i for i in issues)


def test_validate_unknown_key():
    issues = validate_coact_block({"coact": {"toolz": ["Read"]}})
    assert any("unknown key" in i for i in issues)


def test_validate_bad_model():
    issues = validate_coact_block({"coact": {"model": "gpt-4"}})
    assert issues == ["coact.model: 'gpt-4' is not one of sonnet, opus, haiku, inherit"]


def test_validate_bad_memory():
    issues = validate_coact_block({"coact": {"memory": "cloud"}})
    assert any("memory" in i and "user, project, local" in i for i in issues)


@pytest.mark.parametrize("key", ["tools", "disallowed_tools", "skills"])
def test_validate_list_keys_must_be_list_of_str(key):
    issues = validate_coact_block({"coact": {key: "Read"}})
    assert any(f"coact.{key}: must be a list of strings" == i for i in issues)


def test_validate_mcp_not_a_list():
    issues = validate_coact_block({"coact": {"mcp": "nope"}})
    assert any("coact.mcp: must be a list" in i for i in issues)


def test_validate_mcp_entry_not_a_mapping():
    issues = validate_coact_block({"coact": {"mcp": ["bad"]}})
    assert any("coact.mcp[0]: must be a mapping" in i for i in issues)


def test_validate_mcp_missing_module():
    issues = validate_coact_block({"coact": {"mcp": [{"functions": ["f"]}]}})
    assert issues == ["coact.mcp[0]: missing required 'module'"]


def test_validate_returns_not_a_mapping():
    issues = validate_coact_block({"coact": {"returns": "schema"}})
    assert any("coact.returns: must be a mapping" in i for i in issues)


def test_validate_returns_both_ref_and_inline():
    issues = validate_coact_block(
        {"coact": {"returns": {"schema_ref": "m:N", "json_schema": {"type": "object"}}}}
    )
    assert any("provide only one" in i for i in issues)


def test_validate_returns_neither_ref_nor_inline():
    issues = validate_coact_block({"coact": {"returns": {"description": "only desc"}}})
    assert any("needs one of" in i for i in issues)
