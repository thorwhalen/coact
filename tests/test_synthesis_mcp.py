"""Tests for the LLM facade, LLM-assisted persona synthesis, and the mcp backend."""

import importlib.util

import pytest
from skill.base import Skill, SkillMeta

from coact import (
    complete,
    realize,
    resolve_llm,
    structured,
    synthesize_persona,
)
from coact.base import ReturnContract

_HAS_PY2MCP = importlib.util.find_spec("py2mcp") is not None


def _skill(name="ux", description="Analyze UX bundles.", body="steps"):
    return Skill(meta=SkillMeta(name=name, description=description), body=body)


# ---------------------------------------------------------------------------
# llm facade
# ---------------------------------------------------------------------------


def test_resolve_llm_passthrough_callable():
    fn = resolve_llm(lambda p: "echo:" + p)
    assert fn("hi") == "echo:hi"


def test_resolve_llm_aw_stepconfig_shape():
    class FakeStepConfig:
        def resolve_llm(self):
            return lambda p: "cfg:" + p

    fn = resolve_llm(FakeStepConfig())
    assert fn("x") == "cfg:x"


def test_resolve_llm_none_degrades_gracefully():
    # With no provider configured/injected, returns either None or a callable;
    # crucially it does not raise.
    result = resolve_llm(None)
    assert result is None or callable(result)


def test_structured_with_injected_llm():
    fn = lambda p: '```json\n{"score": 7}\n```'
    out = structured("rate it", {"type": "object"}, llm=fn)
    assert out == {"score": 7}


def test_structured_returns_none_without_llm():
    # an llm that yields non-JSON, retried, still fails -> None
    out = structured("x", {"type": "object"}, llm=lambda p: "not json at all", retries=1)
    assert out is None


# ---------------------------------------------------------------------------
# LLM-assisted persona (optional; template otherwise)
# ---------------------------------------------------------------------------


def test_persona_template_without_llm():
    persona, src = synthesize_persona(
        _skill(), return_contract=ReturnContract(json_schema={"type": "object"})
    )
    assert src == "synthesized-template"
    assert "You are the **ux** agent" in persona


def test_persona_llm_drafts_identity_but_keeps_contract_deterministic():
    drafted = "You are a sharp ux agent. Follow the `ux` skill as your source of truth."
    persona, src = synthesize_persona(
        _skill(),
        return_contract=ReturnContract(json_schema={"type": "object"}, description="d"),
        tools=["Read"],
        llm=lambda prompt: drafted,
    )
    assert src == "synthesized-llm"
    assert drafted in persona
    # invariants + return contract still appended deterministically
    assert "Operating invariants" in persona
    assert "Return contract" in persona


def test_complete_threads_llm_through():
    drafted = "You are the ux agent, grounded in the `ux` skill."
    ad = complete(_skill(), llm=lambda p: drafted)
    assert drafted in ad.prompt


def test_complete_llm_failure_falls_back_to_template():
    def broken_llm(prompt):
        raise RuntimeError("provider down")

    ad = complete(_skill(), llm=broken_llm)
    assert "You are the **ux** agent" in ad.prompt  # template fallback


# ---------------------------------------------------------------------------
# mcp backend (via py2mcp)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _HAS_PY2MCP, reason="py2mcp not installed")
def test_mcp_backend_exposes_declared_tools(tmp_path):
    skill_dir = tmp_path / "pather"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        """---
name: pather
description: Path helpers exposed as tools.
coact:
  mcp:
    - module: os.path
      functions: [basename, dirname]
---
# pather
body
"""
    )
    server = realize(skill_dir, backend="mcp")
    assert server.name == "pather-tools"
    import asyncio

    tool = asyncio.run(server.get_tool("basename"))
    assert tool.name == "basename"


@pytest.mark.skipif(not _HAS_PY2MCP, reason="py2mcp not installed")
def test_mcp_backend_errors_without_declared_tools():
    s = _skill()  # in-memory skill, no coact: mcp block
    with pytest.raises(ValueError) as exc:
        realize(s, backend="mcp")
    msg = str(exc.value)
    # pin both the headline AND the actionable guidance pointing at the block
    assert "No Python tools to expose" in msg and "coact: mcp:" in msg
