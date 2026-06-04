---
name: coact-realize
description: Use when turning a coact agent definition (or a skill) into something that actually runs — i.e. REALIZE. Triggers on "realize this agent", "run a coact agent", "materialize an agent for Claude Code", "make an aw/Agent-SDK runnable from a skill", "expose a skill's tools as an MCP server", or choosing between the host/sdk/mcp backends and their cost. Covers realize(), the three backends, install extras, and the fan-out cost gate.
---

# REALIZE a definition into a running agent

"Running" means different things for different hosts, so `coact` puts a small set
of **backends** behind one `realize(...)` interface (an open-closed registry —
register your own without touching core).

```python
from coact import realize
realize(target, backend="host")     # target: AgentDefinition | skill source | agent .md | list
```

| backend | what "running" means | cost | install |
|---|---|---|---|
| `host` (default) | materialize `.claude/agents/*.md` + link referenced skills; the **host agent** (Claude Code) executes | cheapest — no fan-out | `pip install coact` |
| `sdk` | a `RunnableAgent` backed by the Claude Agent SDK that **satisfies `aw.AgenticStep`** (`execute(input, context) -> (artifact, info)`) — drops into `aw` workflows | in-process | `pip install coact[sdk]` |
| `mcp` | expose a skill's declared Python tools as a FastMCP server (via `py2mcp`) for any MCP client | tool server | `pip install coact[mcp]` |

## host (the default, cheapest)

Materializes files the host will discover, and links the skills the agent
references (point-don't-copy stays intact):

```python
res = realize(agent, backend="host")          # -> RealizedHost
res.agents      # {name: Path} written under .claude/agents/
res.skills      # {name: Path} linked under .claude/skills/
res.warnings    # anything that couldn't be wired
```

```bash
coact realize .claude/skills/ux-analyst --backend host --dest .claude/agents
```

Useful kwargs: `scope="project"` (vs user), `dest=`, `skills_source=`,
`link=True`. Realizing here is "materialize files + verify discovery" — it does
**not** stand up a new runtime, which is why it's the default.

## sdk (an aw-compatible runnable)

```python
step = realize(agent, backend="sdk")          # -> RunnableAgent (aw.AgenticStep)
artifact, info = step.execute(task, context={})
```

The return contract is honored by the SDK: when the SDK exposes `output_format`
the structured result comes back natively; otherwise coact falls back to a forced
`return_result` tool whose `input_schema` **is** the return JSON Schema, and
recovers the result from the tool call. Control it with
`realize_sdk(..., return_mode="auto"|"output_format"|"tool")` (`auto` is right
almost always). `info` carries warnings (e.g. an mcp server declared as a bare
name the sdk backend can't resolve — use `host` for those).

## mcp (a tool server)

```python
server = realize(".claude/skills/ux-analyst", backend="mcp")   # FastMCP handle
server.run()
```

Exposes the skill's `coact: mcp` Python tools (`module:function`) over MCP via
`py2mcp`. The skill's procedure stays in the skill; this serves only the tools.

## Decide before you fan out: the cost gate

A running fleet costs roughly an **order of magnitude** more tokens than one
agent, and the premium is worst on *interdependent* tasks — so `host` (one agent
runs the skills) is the default for a reason. Check first:

```python
from coact import estimate
print(estimate([agent_a, agent_b]).render())   # multiplier + interdependence + recommendation
```

```bash
coact estimate .claude/agents/a.md .claude/agents/b.md
```

If the set shares skills or declares an input contract, `estimate` flags it as
interdependent and steers you back to `backend="host"`. See `coact-analyze`.

## Boundaries

- **Topology is out of scope.** A subagent definition can't express graphs,
  conditional edges, or cycles, and subagents can't spawn subagents. coact emits
  *definitions + tool/MCP wiring* and stops — orchestration is the host manager's
  job (or a thin shim you own against `aw` / the Agent SDK). coact is not
  LangGraph.

## Related

- `coact-complete` — produce the definition you're realizing.
- `coact-analyze` — `estimate` (cost) and `inventory` (what's realizable).
