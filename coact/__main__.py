# PYTHON_ARGCOMPLETE_OK
"""CLI entry point for coact — the verbs are both Python functions and subcommands.

Mirrors ``skill``'s dispatch-to-interface pattern (CLI wrappers call the same
core functions and format for the terminal), so the two packages feel like one
toolkit. The verbs are ``plan``, ``complete``, ``emit``, ``realize``, ``diff``,
``estimate``, ``inventory``, ``back``, and ``scaffold``. Usage::

    python -m coact plan .claude/skills/ux-analyst
    python -m coact complete .claude/skills/ux-analyst --dest .claude/agents
    python -m coact emit .claude/skills/ux-analyst --target sdk-agent-dict
    python -m coact realize .claude/skills/ux-analyst --backend host --dry-run
    python -m coact realize .claude/skills/ux-analyst --backend litellm
    python -m coact diff .claude/skills/ux-analyst .claude/agents/ux-analyst.md
    python -m coact estimate .claude/agents/a.md .claude/agents/b.md
    python -m coact inventory .
    python -m coact back .claude/agents/ux-analyst.md
    python -m coact scaffold .claude/agents/a.md .claude/agents/b.md
"""

from __future__ import annotations

import argh

from coact import complete as _complete
from coact import emit_agent as _emit
from coact import plan_completion as _plan
from coact import realize as _realize
from coact import scaffold_fleet as _scaffold_fleet
from coact.analysis import back as _back
from coact.analysis import diff as _diff
from coact.analysis import estimate as _estimate
from coact.analysis import inventory as _inventory


def plan(skill: str) -> str:
    """Dry-run the skill→agent completion: show each field + its provenance."""
    return _plan(skill).render()


def complete(skill: str, *, dest: str | None = None, plan: bool = False) -> str:
    """Complete a skill into an agent definition (print the .md, or write to --dest)."""
    if plan:
        return _plan(skill).render()
    agent = _complete(skill)
    if dest:
        return f"Wrote {_emit(agent, 'claude-agents-md', dest=dest)}"
    return _emit(agent, "claude-agents-md")


def emit(
    skill: str, *, target: str = "claude-agents-md", dest: str | None = None
) -> str:
    """Complete a skill and emit it to a target (claude-agents-md, sdk-agent-dict, ...)."""
    agent = _complete(skill)
    result = _emit(agent, target, dest=dest)
    return str(result)


def realize(
    target: str,
    *,
    backend: str = "host",
    dest: str | None = None,
    scope: str = "project",
    skills_source: str | None = None,
    dry_run: bool = False,
) -> str:
    """Realize an agent/skill via a backend (host materializes files; sdk/mcp build runnables).

    ``--dry-run`` (host only) previews the files that *would* be written/linked
    without touching the filesystem.
    """
    if backend == "host":
        res = _realize(
            target,
            backend="host",
            dest=dest,
            scope=scope,
            skills_source=skills_source,
            dry_run=dry_run,
        )
        head = "Would realize (host, dry-run)" if res.dry_run else "Realized (host)"
        lines = [f"{head} into {res.agents_dir}:"]
        lines += [f"  agent: {p}" for p in res.agents.values()]
        lines += [f"  skill: {p}" for p in res.skills.values()]
        lines += [f"  ! {w}" for w in res.warnings]
        return "\n".join(lines)
    if backend == "sdk":
        runnable = _realize(target, backend="sdk")
        return (
            f"Realized (sdk) RunnableAgent for {runnable.agent_def.name!r} "
            "(aw.AgenticStep-compatible: .execute(input, context) -> (artifact, info))."
        )
    if backend == "mcp":
        server = _realize(target, backend="mcp")
        return f"Realized (mcp) server {server.name!r}. Call .run() to serve it."
    return str(_realize(target, backend=backend))


def diff(skill: str, agent: str) -> str:
    """Show what extras an agent adds over its source skill (the §3.2 table)."""
    return _diff(skill, agent).render()


def estimate(*agents: str) -> str:
    """Surface the fan-out token multiplier for an agent set (the cost gate)."""
    if not agents:
        return "Pass one or more agent .md files or skill sources."
    return _estimate(list(agents)).render()


@argh.arg("project", nargs="?", default=".", help="Project root (default: current dir)")
def inventory(project: str) -> str:
    """Enumerate a project's skills, derived agents, and MCP-exposed tools."""
    return _inventory(project).render()


def back(agent: str) -> str:
    """Best-effort, LOSSY agent→skill extraction (prints a SKILL.md stub)."""
    return _back(agent).to_string()


@argh.arg("agents", nargs="+", help="Agent .md files / skill sources to wire")
def scaffold(
    agents: list, *, dest: str | None = None, agents_dir: str = ".claude/agents"
) -> str:
    """Emit a STARTER multi-agent fleet shim you own (sequential; D8 — not a topology engine)."""
    result = _scaffold_fleet(list(agents), dest=dest, agents_dir=agents_dir)
    if dest:
        return f"Wrote starter fleet shim: {result}"
    return str(result)


def main() -> None:
    """Dispatch the coact CLI."""
    argh.dispatch_commands(
        [plan, complete, emit, realize, diff, estimate, inventory, back, scaffold]
    )


if __name__ == "__main__":
    main()
