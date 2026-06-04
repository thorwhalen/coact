# coact

**Reuse your "AI stuff" across the layers of the modern agent stack.** `coact`
("co-act" — skills and agents acting as one reusable substrate) turns the skills
you already have into agent definitions, and turns those definitions into
agents that actually run.

```
python functions/scripts  →  .claude/skills/  →  .claude/agents/  →  running agents
        (py2mcp, aw)            (skill pkg)        COMPLETE (coact)    REALIZE (coact)
```

`coact` owns the two transitions the rest of the ecosystem doesn't:

- **COMPLETE** — start from a `.claude/skills/` skill and *complete* it into a
  `.claude/agents/` definition: add the agent-only extras (persona, return
  contract, tool allowlist, model, memory) that a skill doesn't carry.
- **REALIZE** — take a completed definition and produce something that runs,
  choosing the right backend (the host agent, the Claude Agent SDK, or
  MCP-exposed tools for a foreign host).

It is glue, not a new framework: it builds on [`skill`](https://github.com/thorwhalen/skill)
(skill data model + registries), [`aw`](https://github.com/thorwhalen/aw)
(the `AgenticStep` runtime), and [`py2mcp`](https://github.com/i2mint/py2mcp)
(Python → MCP). See [`misc/docs/REUSE.md`](misc/docs/REUSE.md).

## Install

```bash
pip install coact            # core: COMPLETE + host realize + analysis (no LLM needed)
pip install coact[sdk]       # + the Claude Agent SDK realize backend (and aw)
pip install coact[mcp]       # + the py2mcp/FastMCP realize backend
pip install coact[litellm]   # + the provider-agnostic LiteLLM realize backend
```

## Quick start

```python
from coact import complete, emit_agent, realize

# 1. Complete a skill into an agent definition (mechanical — no LLM).
agent = complete(".claude/skills/ux-analyst")

# 2. See it: a valid .claude/agents/ markdown file.
print(emit_agent(agent, "claude-agents-md"))

# 3. Realize it the cheap way: materialize files so Claude Code runs it.
realize(agent, backend="host")
```

Prefer to look before you leap? Everything has a dry-run:

```python
from coact import plan_completion

plan = plan_completion(".claude/skills/ux-analyst")
print(plan.render())   # every synthesized field + WHERE it came from + warnings
```

A complete, runnable walk through all of this — a real skill → `complete` →
`emit` → `realize(host)` → `realize(sdk)` → `estimate`/`inventory` — lives in
[`examples/`](examples/) (no LLM, no API key needed):

```bash
python examples/walkthrough.py
```

### CLI

```bash
coact plan      .claude/skills/ux-analyst                 # dry-run with provenance
coact complete  .claude/skills/ux-analyst --dest .claude/agents
coact realize   .claude/skills/ux-analyst --backend host
coact diff      .claude/skills/ux-analyst .claude/agents/ux-analyst.md
coact estimate  .claude/agents/a.md .claude/agents/b.md   # the cost gate
coact inventory .                                         # skills + agents + MCP tools
```

## The model in one minute

A `SKILL.md` is *procedural knowledge injected into the caller's turn*; a subagent
is *a separate worker with its own context, persona, tools, model, and a defined
return value*. They overlap heavily — **an agent is mostly a skill plus a thin
"extras" envelope.** COMPLETE synthesizes that envelope; the two extras that
actually matter are:

1. the **persona** (system prompt / identity), and
2. the **return contract** (a schema so a manager can consume the agent's output).

`coact` keeps the **skill on disk as the single source of truth** and makes the
agent *reference* it by name — it never copies a skill body into an agent. One
`AgentDefinition` object serializes to both the filesystem `.claude/agents/*.md`
and the Agent SDK form.

### The `coact:` frontmatter (optional)

To make the lift reproducible, a skill may carry an additive `coact:` block
(ignored by every other tool). When present it wins over policy; when absent
`coact` infers + reports what it guessed.

```yaml
---
name: ux-analyst
description: Analyze a captured UX evidence bundle for usability issues.
coact:
  tools: [Read, Grep, Glob]
  model: sonnet
  memory: project
  returns:
    schema_ref: ov.schemas:UxFindings
  mcp:
    - module: ov.analyzers
      functions: [score_contrast, find_tap_targets]
---
```

## Realization backends

| backend | what "running" means | cost |
|---|---|---|
| `host` (default) | materialize `.claude/agents/*.md` + link skills; the **host agent** (Claude Code) executes | cheapest — no fan-out |
| `sdk` | a `RunnableAgent` backed by the Claude Agent SDK that **satisfies `aw.AgenticStep`** (`execute(input, context) -> (artifact, info)`), so it drops into `aw` workflows | in-process |
| `mcp` | expose a skill's declared Python tools as a FastMCP server (via `py2mcp`) for any MCP client | tool server |
| `litellm` | a `RunnableLLMAgent` (also `aw.AgenticStep`) backed by **LiteLLM** — realize the *same* definition against any provider (OpenAI, Gemini, Mistral, Ollama, …); proof the definition isn't Anthropic-specific | in-process |

```python
agent_step = realize(agent, backend="sdk")          # aw-compatible runnable
artifact, info = agent_step.execute(task, context={})

server = realize(".claude/skills/ux-analyst", backend="mcp")   # FastMCP handle

# same definition, a different provider — map model selectors however you like
llm_step = realize(agent, backend="litellm", model_map={"sonnet": "openai/gpt-4o"})
artifact, info = llm_step.execute(task)             # info["backend"] == "litellm"
```

## Two boundaries to know

- **Topology is out of scope.** A subagent definition can't express graphs,
  conditional edges, or cycles, and subagents can't spawn subagents. `coact`
  emits *definitions + tool/MCP wiring* and stops. Multi-agent orchestration is
  left to the host's manager or a thin shim you own (against the Agent SDK or
  `aw`'s workflow chaining) — `coact` is not LangGraph.
- **A running fleet is an optimization, not a default.** Multi-agent fan-out
  costs roughly an order of magnitude more tokens, and the premium is worst on
  *interdependent* tasks. So `backend="host"` (one agent runs the skills) is the
  default, and `coact estimate` shows the tradeoff before you spawn a fleet:

  ```python
  from coact import estimate
  print(estimate([agent_a, agent_b]).render())
  ```

## Design notes

- No LLM on any mechanical path; persona drafting is *optional* and injected
  (`complete(skill, llm=...)`), never a hard provider dependency.
- Open-closed registries for emit targets and realization backends — register
  your own without touching core.
- Decisions are recorded in [`misc/docs/DECISIONS.md`](misc/docs/DECISIONS.md);
  the build brief is [`misc/docs/COACT_SPEC.md`](misc/docs/COACT_SPEC.md).
