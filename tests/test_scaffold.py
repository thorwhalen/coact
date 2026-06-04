"""Tests for ``coact.scaffold`` — the starter multi-agent fleet shim emitter.

The shim is a *user-owned starter* coact emits once (DECISIONS D8): it runs no
LLM and stands up no runtime, only renders source. These tests confirm the
emitted file is valid, self-explanatory Python that names the right agents.
"""

from __future__ import annotations

import ast

import pytest

from coact import AgentDefinition, scaffold_fleet


def _agents():
    return [
        AgentDefinition(name="collector", description="Collect evidence."),
        AgentDefinition(name="summarizer", description="Summarize findings."),
    ]


def test_scaffold_returns_source_string():
    shim = scaffold_fleet(_agents())
    assert isinstance(shim, str)
    assert 'AGENTS = ["collector", "summarizer"]' in shim
    assert "YOU OWN THIS FILE" in shim and 'backend="sdk"' in shim


def test_scaffold_emits_valid_python():
    shim = scaffold_fleet(_agents())
    ast.parse(shim)  # raises SyntaxError if malformed
    compile(shim, "<fleet>", "exec")


def test_scaffold_states_the_cost_gate_and_d8_boundary():
    shim = scaffold_fleet(_agents())
    assert "coact estimate" in shim
    assert "DECISIONS D8" in shim and "not" in shim  # "it is not LangGraph"


def test_scaffold_honors_agents_dir():
    shim = scaffold_fleet(_agents(), agents_dir="custom/agents")
    assert 'AGENTS_DIR = "custom/agents"' in shim


def test_scaffold_writes_file_when_dest_is_path(tmp_path):
    dest = tmp_path / "fleet.py"
    out = scaffold_fleet(_agents(), dest=dest)
    assert out == dest and dest.exists()
    compile(dest.read_text(), str(dest), "exec")


def test_scaffold_writes_default_name_when_dest_is_dir(tmp_path):
    out = scaffold_fleet(_agents(), dest=tmp_path)
    assert out == tmp_path / "fleet.py" and out.exists()


def test_scaffold_from_agent_md_files(tmp_path):
    from coact import emit_agent

    md = emit_agent(_agents()[0], "claude-agents-md", dest=tmp_path)
    shim = scaffold_fleet([str(md)])
    assert 'AGENTS = ["collector"]' in shim


def test_scaffold_empty_target_raises():
    with pytest.raises(ValueError, match="at least one agent"):
        scaffold_fleet([])
