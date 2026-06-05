"""Tests for ``coact.stores`` — ``agents_dir`` resolution and the AgentStore mapping."""

from __future__ import annotations

import pytest

from coact.base import AgentDefinition
from coact.stores import AgentStore, agents_dir


def _agent(name="ux"):
    return AgentDefinition(name=name, description="Analyze.", prompt="You are...")


def test_agents_dir_global():
    p = agents_dir(scope="global")
    assert p.as_posix().endswith(".claude/agents")
    assert str(p).startswith(str(__import__("pathlib").Path.home()))


def test_agents_dir_project_custom_dir(tmp_path):
    p = agents_dir(scope="project", project_dir=tmp_path)
    assert p == tmp_path / ".claude" / "agents"


def test_store_set_get_roundtrip(tmp_path):
    store = AgentStore(root=tmp_path)
    store["ux"] = _agent("ux")
    assert store["ux"].description == "Analyze."
    assert (tmp_path / "ux.md").exists()


def test_store_len_and_iter(tmp_path):
    store = AgentStore(root=tmp_path)
    assert len(store) == 0
    store["a"] = _agent("a")
    store["b"] = _agent("b")
    assert len(store) == 2
    assert sorted(store) == ["a", "b"]


def test_store_contains_and_delete(tmp_path):
    store = AgentStore(root=tmp_path)
    store["x"] = _agent("x")
    assert "x" in store and 123 not in store
    del store["x"]
    assert "x" not in store and len(store) == 0


def test_store_getitem_missing_raises_keyerror(tmp_path):
    with pytest.raises(KeyError):
        AgentStore(root=tmp_path)["nope"]


def test_store_delitem_missing_raises_keyerror(tmp_path):
    with pytest.raises(KeyError):
        del AgentStore(root=tmp_path)["nope"]


def test_store_rejects_path_traversal_on_write(tmp_path):
    # A crafted key must not escape the store root (CWE-22). The write raises and
    # no file lands outside root.
    store = AgentStore(root=tmp_path / "agents")
    with pytest.raises(ValueError, match="unsafe agent name"):
        store["../escape"] = _agent("escape")
    assert not (tmp_path / "escape.md").exists()


def test_store_rejects_path_traversal_on_read_and_delete(tmp_path):
    store = AgentStore(root=tmp_path / "agents")
    with pytest.raises(ValueError, match="unsafe agent name"):
        _ = store["../../secret"]
    with pytest.raises(ValueError, match="unsafe agent name"):
        del store["../../secret"]


def test_store_contains_is_total_for_unsafe_keys(tmp_path):
    # ``in`` must stay total — an unsafe key is simply not a member, not a raise.
    store = AgentStore(root=tmp_path / "agents")
    assert "../escape" not in store


def test_store_repr(tmp_path):
    # Use repr(root) for the path so the assertion is separator-independent:
    # on Windows repr(WindowsPath) renders with forward slashes, unlike str(path).
    store = AgentStore(root=tmp_path)
    r = repr(store)
    assert "AgentStore" in r and "root=" in r and repr(store.root) in r
