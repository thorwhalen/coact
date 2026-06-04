"""End-to-end coact walkthrough: a real skill → COMPLETE → REALIZE → analyze.

Runs with **core coact only** (no LLM, no API call). The optional ``sdk`` step is
guarded so the script still completes if ``coact[sdk]`` isn't installed.

Run it::

    python examples/walkthrough.py

Each step prints what it did. ``main(dest=...)`` returns a small result dict so the
flow can also be exercised by a test (see ``tests/test_examples.py``).
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from coact import (
    complete,
    emit_agent,
    estimate,
    from_claude_agent_md,
    inventory,
    plan_completion,
    realize,
)

HERE = Path(__file__).resolve().parent
SKILLS_DIR = HERE / "skills"
UX_ANALYST = SKILLS_DIR / "ux-analyst"


def _rule(title: str) -> None:
    print(f"\n{'=' * 4} {title} {'=' * (72 - len(title))}")


def main(dest: Path | str | None = None) -> dict:
    """Walk a skill through complete → emit → realize(host) → realize(sdk) → analyze.

    ``dest`` is where ``realize(backend='host')`` materializes files; a temp dir is
    used when omitted. Returns a dict summarizing each stage (handy for tests).
    """
    out_dir = Path(dest) if dest is not None else Path(tempfile.mkdtemp(prefix="coact-ex-"))
    result: dict = {}

    # 1. DRY RUN — look before you leap: every synthesized field + where it came from.
    _rule("1. plan_completion (dry-run with provenance)")
    plan = plan_completion(UX_ANALYST)
    print(plan.render())
    result["provenance_sources"] = sorted({p.source for p in plan.provenance})

    # 2. COMPLETE — Skill -> AgentDefinition (mechanical, no LLM).
    _rule("2. complete (Skill -> AgentDefinition)")
    agent = complete(UX_ANALYST)
    print(f"  name={agent.name!r}  model={agent.model!r}  tools={agent.tools}")
    print(f"  memory={agent.memory!r}  return-schema props={list(agent.returns.schema().get('properties', {}))}")
    result["agent_name"] = agent.name
    result["return_props"] = sorted(agent.returns.schema().get("properties", {}))

    # 3. EMIT — the canonical .claude/agents/*.md serialization.
    _rule("3. emit_agent (claude-agents-md)")
    md = emit_agent(agent, "claude-agents-md")
    print(md[: md.find("\n", md.find("coact:"))] if "coact:" in md else md[:500])
    print("  ... (return contract carried in the coact: block)")
    result["emitted_md_len"] = len(md)

    # 3b. ROUND-TRIP — parse the emitted .md back to an AgentDefinition (lossless).
    reparsed = from_claude_agent_md(md)
    assert reparsed.name == agent.name and reparsed.returns.schema() == agent.returns.schema()
    print("  round-trip from_claude_agent_md(md) -> AgentDefinition: OK (name + return contract preserved)")

    # 4. REALIZE (host) — the cheap default: materialize files the host agent runs,
    #    linking the referenced skill into a sibling .claude/skills/.
    _rule("4. realize(backend='host')")
    realized = realize(
        agent,
        backend="host",
        dest=out_dir / ".claude" / "agents",
        skills_source=SKILLS_DIR,
    )
    for name, path in realized.agents.items():
        print(f"  agent: {name} -> {path}")
    for name, path in realized.skills.items():
        print(f"  linked skill: {name} -> {path}")
    if realized.warnings:
        print("  warnings:", realized.warnings)
    result["host_agent_files"] = [p.name for p in realized.agents.values()]
    result["host_linked_skills"] = sorted(realized.skills)

    # 5. REALIZE (sdk) — an aw.AgenticStep-compatible runnable. Optional extra; the
    #    build is offline (no API call). We only construct options, never execute.
    _rule("5. realize(backend='sdk')  [optional — needs coact[sdk]]")
    try:
        runnable = realize(agent, backend="sdk")
        options = runnable.build_options()
        plan_ = runnable._resolved_return()
        print(f"  RunnableAgent built; return_mode resolved to {plan_.mode!r}")
        print(f"  allowed_tools={list(getattr(options, 'allowed_tools', []))}")
        result["sdk_return_mode"] = plan_.mode
    except Exception as exc:  # ImportError via check_requirements, or no SDK
        print(f"  skipped (sdk extra not available): {type(exc).__name__}")
        result["sdk_return_mode"] = None

    # 6. ANALYZE — the cost gate + an inventory of what's discoverable.
    _rule("6. analyze (estimate + inventory)")
    est = estimate([agent])
    print(est.render())
    inv = inventory(out_dir)
    print(inv.render())
    result["inventory_agents"] = len(inv.agents)
    result["estimate_rendered"] = bool(est.render())

    _rule("done")
    print(f"  materialized under: {out_dir}")
    return result


if __name__ == "__main__":
    main()
