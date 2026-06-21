---
name: coact-realize
description: Use when turning a coact agent definition (or a skill) into something that actually runs — i.e. REALIZE. Triggers on "realize this agent", "run a coact agent", "materialize an agent for Claude Code", "make an aw/Agent-SDK runnable from a skill", "run a definition through LiteLLM/LangGraph/CrewAI", "expose a skill's tools as an MCP server", or choosing between the host/sdk/litellm/langgraph/crewai/mcp backends and their cost. Covers realize(), the backends, install extras, and the fan-out cost gate.
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
| `litellm` | a `RunnableLLMAgent` (also `aw.AgenticStep`) running the **same** definition against any LiteLLM provider (OpenAI, Anthropic, Gemini, Ollama, …) | in-process | `pip install coact[litellm]` |
| `langgraph` | a `RunnableLLMGraphAgent` (also `aw.AgenticStep`) backed by a LangGraph `CompiledStateGraph`; the graph is **exposed** (`.agent`) to compose into *your own* `StateGraph` | in-process | `pip install coact[langgraph]` |
| `crewai` | a `RunnableCrewAIAgent` (also `aw.AgenticStep`) backed by a single `crewai.Agent` (`Agent.kickoff`); the `Agent` is **exposed** (`.agent`) for *your own* `Crew` | in-process | `pip install coact[crewai]` |
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

Look before you leap — `dry_run=True` previews exactly what would be written and
linked, touching nothing on disk (the returned `RealizedHost` has `dry_run=True`):

```python
preview = realize(agent, backend="host", dry_run=True)
preview.agents     # {name: Path that WOULD be written}
preview.skills     # {name: Path that WOULD be linked}
preview.warnings   # e.g. a referenced skill that can't be resolved
```

```bash
coact realize .claude/skills/ux-analyst --backend host --dry-run
```

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

## litellm / langgraph / crewai (one definition, three more runtimes)

The same `AgentDefinition` realizes against three more in-process runtimes, each an
`aw.AgenticStep` runnable (`execute(input, context) -> (artifact, info)`):

```python
step = realize(agent, backend="litellm", model_map={"sonnet": "openai/gpt-4o"})
artifact, info = step.execute(task)                 # any LiteLLM provider

graph_step = realize(agent, backend="langgraph")    # graph_step.agent: a CompiledStateGraph
crew_step  = realize(agent, backend="crewai")       # crew_step.agent: a crewai.Agent
```

`langgraph` and `crewai` realize **one** definition into a framework-native object and
**expose** it (`.agent`) so you compose it into *your own* `StateGraph` / `Crew` — coact
builds no graph or crew of its own (DECISIONS D8/D16). They differ from `litellm` in two
ways worth knowing:

- **Tools are opt-in.** coact tools are host-resolved *names*; these frameworks want Python
  callables, so pass `tools_map={name: callable}` to bind them for a real tool-use loop.
  Unbound names surface in `info["unbound_tools"]` (langgraph) / `info["warnings"]` (crewai).
- **Model-string form differs:** `langgraph` uses langchain **colon** form
  (`"anthropic:claude-sonnet-4-5"`) and needs the provider's `langchain-<provider>` package;
  `litellm`/`crewai` use **slash** form (`"anthropic/claude-..."`). Override via `model_map=`.

The return contract (D6) is honored natively where each framework allows and always via the
in-prompt instruction as a fallback — so structured output degrades gracefully.

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

## If you do fan out: scaffold a starter (you own it)

When a running fleet genuinely pays off, `scaffold_fleet` emits a **starter**
Python shim wiring the realized `sdk` agents under an `aw` coordinator — a thin
**sequential** hand-off with `TODO` markers you reshape into the real control flow:

```python
from coact import scaffold_fleet

scaffold_fleet([agent_a, agent_b])                 # -> the shim source (str)
scaffold_fleet([agent_a, agent_b], dest="fleet.py")  # -> writes it, returns the Path
```

```bash
coact scaffold .claude/agents/a.md .claude/agents/b.md   # prints the shim
```

This is the **one** topology-adjacent thing coact emits (DECISIONS D8): it renders
source and stops — no LLM, no runtime, no graph. coact writes the starter once and
never runs it; the topology (branches, fan-out, retries) is yours to own, against
`aw.orchestration` or the Agent SDK. coact is not LangGraph — though the `langgraph`
backend *can* realize a single definition into a node you wire into your own graph.

## Boundaries

- **Topology is out of scope.** A subagent definition can't express graphs,
  conditional edges, or cycles, and subagents can't spawn subagents. coact emits
  *definitions + tool/MCP wiring* and stops — orchestration is the host manager's
  job (or a thin shim you own against `aw` / the Agent SDK). coact is not
  LangGraph. The `langgraph`/`crewai` backends realize a *single* definition into a
  composable node/Agent; they still build no graph or crew of their own (D8/D16).

## Related

- `coact-complete` — produce the definition you're realizing.
- `coact-analyze` — `estimate` (cost) and `inventory` (what's realizable).
