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
pip install coact[langgraph] # + the LangGraph realize backend (langchain+langgraph >= 1.0; bundles langchain-openai)
pip install coact[crewai]    # + the CrewAI realize backend
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

That extends to the one backend that touches disk:
`realize(agent, backend="host", dry_run=True)` returns the agent files and skill
links it *would* write — without creating any of them.

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
coact emit      .claude/skills/ux-analyst --target sdk-agent-dict   # a non-default emit target
coact realize   .claude/skills/ux-analyst --backend host
coact realize   .claude/skills/ux-analyst --backend host --dry-run   # preview; writes nothing
coact diff      .claude/skills/ux-analyst .claude/agents/ux-analyst.md
coact estimate  .claude/agents/a.md .claude/agents/b.md   # the cost gate
coact inventory .                                         # skills + agents + MCP tools
coact back      .claude/agents/ux-analyst.md              # lossy agent → skill stub
coact scaffold  .claude/agents/a.md .claude/agents/b.md   # a starter fleet shim (you own it)
coact publish   mypkg.tools:summarize --name my-tools --dry-run   # → a Claude .mcpb (preview)
coact describe  "a tool that looks up the weather for a city"     # NL → a draft IntegrationSpec
```

## Publish — ship a capability to a chatbot host

Beyond COMPLETE/REALIZE, the **PUBLISH** axis packages a capability (Python
tools) as a deployable chatbot integration. The first target,
`claude-local-mcpb`, builds a **Claude Desktop `.mcpb` Desktop Extension** — a
one-click *local* (stdio) MCP server, built by [`py2mcp`](https://github.com/i2mint/py2mcp):

```python
from coact import publish

publish(["mypkg.tools:summarize", "mypkg.tools:translate"],
        name="text-tools", dest="dist")          # → dist/text-tools.mcpb
```

Sources can be `module:function` refs, live callables, or a skill carrying a
`coact: mcp:` block. `dry_run=True` (or `--dry-run`) previews the bundle without
writing it. This is the **local** surface (stdio, no OAuth); remote claude.ai
*connectors* (HTTPS + OAuth), Claude Code plugins, ChatGPT Apps, and Gemini are
planned targets on the same open-closed registry. Background:
[`misc/docs/CHATBOT_INTEGRATION_LANDSCAPE.md`](misc/docs/CHATBOT_INTEGRATION_LANDSCAPE.md).
Install: `pip install coact[mcpb]`.

There are two ways to get an `IntegrationSpec`. The **mechanical** ingress above
(refs / callables / skills) uses **no LLM**. The **opt-in** ingress refines a
natural-language description into a *draft* spec — proposed tools with inferred
input schemas — routing generation through [`aix`](https://github.com/thorwhalen/aix)
(multi-provider) via [`oa`](https://github.com/thorwhalen/oa):

```python
from coact import integration_spec_from_description

spec = integration_spec_from_description("expose os.path.basename as a tool")
print(spec.render())   # tools the description bound to code become runnable refs
```

The draft is a **design artifact**: tools without a `module:function` handler are
*proposed* (won't run until you bind them to real code). The LLM touches **only**
this path — the code → `.mcpb` path stays LLM-free (`DECISIONS.md` D10/D18).
Install: `pip install coact[nl]`.

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
| `langgraph` | a `RunnableLLMGraphAgent` (also `aw.AgenticStep`) backed by a LangGraph `CompiledStateGraph` (`langchain.agents.create_agent`); the graph is **exposed** (`.agent`) to drop as a node into *your own* `StateGraph` | in-process |
| `crewai` | a `RunnableCrewAIAgent` (also `aw.AgenticStep`) backed by a single `crewai.Agent` (`Agent.kickoff`); the `Agent` is **exposed** (`.agent`) for *your own* `Crew` | in-process |

```python
agent_step = realize(agent, backend="sdk")          # aw-compatible runnable
artifact, info = agent_step.execute(task, context={})

server = realize(".claude/skills/ux-analyst", backend="mcp")   # FastMCP handle

# same definition, a different provider — map model selectors however you like
llm_step = realize(agent, backend="litellm", model_map={"sonnet": "openai/gpt-4o"})
artifact, info = llm_step.execute(task)             # info["backend"] == "litellm"

# one definition → a LangGraph node / CrewAI Agent you compose into your own topology
graph_step = realize(agent, backend="langgraph")    # graph_step.agent is a CompiledStateGraph
crew_step  = realize(agent, backend="crewai")       # crew_step.agent is a crewai.Agent
```

## Two boundaries to know

- **Topology is out of scope.** A subagent definition can't express graphs,
  conditional edges, or cycles, and subagents can't spawn subagents. `coact`
  emits *definitions + tool/MCP wiring* and stops. Multi-agent orchestration is
  left to the host's manager or a thin shim you own (against the Agent SDK or
  `aw`'s workflow chaining) — `coact` is not LangGraph. It *can* realize a single
  definition **into** a LangGraph node or a CrewAI `Agent` (the `langgraph`/`crewai`
  backends above), but it builds no graph or crew of its own — you compose the
  exposed `.agent` into *your* topology.
- **A running fleet is an optimization, not a default.** Multi-agent fan-out
  costs roughly an order of magnitude more tokens, and the premium is worst on
  *interdependent* tasks. So `backend="host"` (one agent runs the skills) is the
  default, and `coact estimate` shows the tradeoff before you spawn a fleet:

  ```python
  from coact import estimate
  print(estimate([agent_a, agent_b]).render())
  ```

  If you do decide to fan out, `scaffold_fleet` emits a **starter** Python shim
  wiring the realized agents under an `aw` coordinator — a sequential hand-off you
  then reshape. It's the one topology-adjacent thing `coact` writes, and only a
  starter: `coact` emits it once and never runs it (the topology stays yours).

  ```python
  from coact import scaffold_fleet
  scaffold_fleet([agent_a, agent_b], dest="fleet.py")   # a runnable starter you own
  ```

## Design notes

- No LLM on any mechanical path; persona drafting is *optional* and injected
  (`complete(skill, llm=...)`), never a hard provider dependency.
- Open-closed registries for emit targets (`claude-agents-md`, `sdk-agent-dict`,
  plus `crewai` / `openai-tools` auto-registered when [`aw`](https://github.com/thorwhalen/aw)
  is installed) and realization backends — register your own without touching core.
- Decisions are recorded in [`misc/docs/DECISIONS.md`](misc/docs/DECISIONS.md);
  the build brief is [`misc/docs/COACT_SPEC.md`](misc/docs/COACT_SPEC.md).
