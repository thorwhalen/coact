---
name: coact-analyze
description: Use when inspecting or moving between the skill/agent layers with coact — auditing what extras an agent adds over its skill, estimating the token cost of fanning out a fleet before you spend it, enumerating a project's reusable AI assets, or harvesting an agent back into a skill. Triggers on "diff this skill and agent", "what does this agent add", "how much will a fleet cost", "is multi-agent worth it here", "list the skills/agents/tools in this project", "inventory", or "turn this agent back into a skill".
---

# Analyze: see and move between the layers

Four small tools wrap the two transforms. All have a `.render()` for the
terminal and a structured object for code.

## `diff` — what extras an agent adds over its skill

Audit drift between the SSOT skill and a derived agent (the §3.2 extras table):

```python
from coact import diff
print(diff(".claude/skills/ux-analyst", ".claude/agents/ux-analyst.md").render())
# rows tagged [from skill] (name/description/skills) vs [extra (agent-only)]
# (tools/model/memory/persona/returns/...)
```

```bash
coact diff .claude/skills/ux-analyst .claude/agents/ux-analyst.md
```

`agent` may be an `AgentDefinition`, an agent `*.md` path, or a skill source
(completed first). Use it to confirm an agent didn't silently drift from its
skill, or to see exactly which envelope fields COMPLETE synthesized.

## `estimate` — the fan-out cost gate (use before you spawn)

A running fleet costs ~an order of magnitude more tokens than one agent, and the
premium is **worst on interdependent tasks**. `estimate` surfaces the tradeoff so
you don't pay it blindly:

```python
from coact import estimate
est = estimate([agent_a, agent_b])
est.token_multiplier_vs_chat   # ~4× one agent, ceiling ~15× a fleet
est.interdependent             # True if they share skills or declare a `consumes` contract
est.shared_skills
print(est.recommendation)      # often: "prefer one host agent (backend='host')"
```

```bash
coact estimate .claude/agents/a.md .claude/agents/b.md
```

Heuristic: shared skills **or** any declared input contract ⇒ interdependent ⇒
multi-agent is a poor fit (isolation buys you nothing; context is shared anyway),
so it steers you to `backend="host"`. An independent, breadth-first set is the
case where a fleet *can* pay off — if the task value justifies the spend.

## `inventory` — a project's reusable AI assets

```python
from coact import inventory
inv = inventory(".")
inv.skills, inv.agents, inv.mcp_tools
print(inv.render())
```

```bash
coact inventory .
```

Enumerates `.claude/skills/` skills, `.claude/agents/` derived agents, and the
MCP tools declared in skills' `coact: mcp` blocks (`skill: module:function`).
Reuses `skill` discovery and adds the agent + MCP dimensions.

## `back` — lossy agent → skill extraction

Harvest an ad-hoc agent back into reusable procedural knowledge. **Lossy by
design**: it strips the persona / return-contract envelope to a skill *stub*
(name + description + a pointer to the skills the agent referenced). The actual
procedure usually lives in those referenced skills, so this is a starting point
you flesh out — not a faithful inverse of COMPLETE.

```python
from coact import back
skill_stub = back(".claude/agents/ad-hoc.md")
print(skill_stub.to_string())
```

```bash
coact back .claude/agents/ad-hoc.md
```

## Related

- `coact-complete` — produce the agents `diff`/`estimate`/`inventory` inspect.
- `coact-realize` — `estimate` decides the backend; `realize` materializes it.
