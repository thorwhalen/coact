---
name: coact
description: Start here for coact — the package that turns your .claude/skills/ into .claude/agents/ definitions (COMPLETE) and those into running agents (REALIZE), plus tooling to see and move between the layers (diff/estimate/inventory/back) and scaffold a starter fleet. Use when someone asks "how do I use coact", "what can coact do", "turn my skills into agents", "reuse my AI stuff across the agent stack", or isn't sure which coact capability they need. Routes to the focused coact-complete / coact-realize / coact-analyze skills.
---

# coact — reuse your AI stuff across the agent stack

`coact` ("co-act") owns the two transitions the rest of the agent-stack ecosystem
doesn't, and adds thin tooling around them:

```
python functions/scripts  →  .claude/skills/  →  .claude/agents/  →  running agents
        (py2mcp, aw)            (skill pkg)        COMPLETE (coact)    REALIZE (coact)
```

- **COMPLETE** — lift a `.claude/skills/` skill into an `AgentDefinition` by adding
  the agent-only "extras envelope": persona, return contract, tools, model, memory.
  Mechanical and **no-LLM** by default. The skill on disk stays the single source of
  truth; the agent *references* it (never copies it).
- **REALIZE** — turn a definition into something that runs, choosing a backend:
  `host` (cheapest — the host agent runs it), `sdk` / `litellm` (in-process
  `aw.AgenticStep` runnables), or `mcp` (expose a skill's Python tools as a server).

The one-liner:

```python
from coact import complete, emit_agent, realize
agent = complete(".claude/skills/ux-analyst")   # Skill -> AgentDefinition (no LLM)
print(emit_agent(agent, "claude-agents-md"))     # the .claude/agents/*.md
realize(agent, backend="host")                   # materialize so Claude Code runs it
```

Everything that writes or spawns has a **dry-run** first (progressive disclosure):
`plan_completion(skill)` previews COMPLETE with per-field provenance, and
`realize(..., backend="host", dry_run=True)` previews what REALIZE would write.

## Which skill do I want?

| You want to… | Use the skill | Key calls |
|---|---|---|
| Turn a skill into an agent definition (COMPLETE) | **`coact-complete`** | `plan_completion`, `complete`, the `coact:` frontmatter block |
| Make a definition actually run (REALIZE) | **`coact-realize`** | `realize(backend=host\|sdk\|mcp\|litellm)`, `dry_run`, `scaffold_fleet` |
| See/move between the layers | **`coact-analyze`** | `diff`, `estimate`, `inventory`, `back` |
| Develop coact itself | **`coact-dev`** | architecture, invariants, extension points |

## Two boundaries worth knowing up front

- **Topology is out of scope.** coact emits *definitions + tool/MCP wiring* and
  stops — it doesn't serialize graphs/edges/cycles. For a multi-agent run it can
  *scaffold* a starter shim you own (`scaffold_fleet`), but it is not LangGraph.
- **A running fleet is an optimization, not a default.** Multi-agent fan-out costs
  ~an order of magnitude more tokens (worst on interdependent tasks), so
  `backend="host"` is the default and `estimate` shows the trade-off before you
  spend. See `coact-analyze`.

## More

- A complete, runnable, no-API-key walkthrough: `python examples/walkthrough.py`.
- CLI mirror of every verb: `coact plan|complete|emit|realize|diff|estimate|inventory|back|scaffold`.
- Design rationale: `misc/docs/DECISIONS.md`; reuse boundaries: `misc/docs/REUSE.md`.
