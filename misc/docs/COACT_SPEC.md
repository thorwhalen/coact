# `coact` — Specification & Build Brief

**Author:** Thor Whalen
**Status:** Specification for implementation (hand to a Claude Code agent)
**Audience:** A Claude Code agent that will develop the `coact` Python package, plus the human reviewing it.

---

## 0. How to read this document

This is a **build brief**, not finished design. It fixes the *what* and the *why* (the conceptual model, the seams, the reuse boundaries, the public interface shape), and deliberately leaves most of the *how* to you. Where it names functions, treat the **names and signatures as proposals to honor unless you find a concrete reason not to** — they are chosen to match the conventions of the surrounding ecosystem (`skill`, `aw`, `py2mcp`). Where it says "decide", decide, then record the decision (see §11).

Before writing any code, do §1 (the reuse audit). A large fraction of what `coact` might naively build **already exists** in `skill`, `aw`, and `py2mcp`. The single biggest way to get this wrong is to reimplement their registries, validators, or MCP wiring. `coact`'s job is the *layer between* skills and running agents — it is glue and lift, not a new framework.

---

## 1. First task: reuse audit (do this before designing)

Study these three packages locally and write a short `REUSE.md` (in `coact/misc/docs/`) recording what `coact` will reuse, extend, or deliberately not touch. Do not skip this.

| Package | Local path | What it already provides (from its README) | `coact`'s relationship to it |
|---|---|---|---|
| `skill` (`thorwhalen/skill`) | `$PP/t/skill` | SKILL.md search/create/validate/install/**link**; a **registry-based plugin architecture with four extension points**: `agent_targets`, `translators`, `backends`, `validators`. Cross-agent management (Claude Code, Cursor, Copilot, Windsurf). `link_skills` symlinks a project's skills into a target. | **Foundation.** `coact` builds on `skill`'s registries. Reuse its `validators` and `agent_targets`. The skill→agent transform is a *new kind of translator/emitter* that should fit `skill`'s plugin model where possible, not a parallel system. |
| `aw` (`thorwhalen/aw`) | `$PP/t/aw` | `AgenticStep` protocol (`execute(input_data, context) -> (artifact, info_dict)`); ReAct loop with retries; **three validation flavors** (schema / info-dict / functional); `Context` as `MutableMapping`; `StepConfig`/`GlobalConfig` with cascading defaults & dependency-injected `llm`; `CodeInterpreterTool`; orchestration/workflow chaining; human-in-loop. | **Runtime substrate.** When `coact` produces a *runnable in-process agent* (the §6 "thin runtime"), it should produce something that satisfies / plugs into `aw`'s `AgenticStep` protocol and reuse `aw`'s `StepConfig` LLM injection and validators rather than inventing a new agent loop. |
| `py2mcp` (`i2mint/py2mcp`) | `$PP/i/py2mcp` | `mk_mcp_server([funcs])`, `mk_input_trans`, `mk_mcp_from_store` (CRUD over a `MutableMapping`). Built on FastMCP. | **Tool-exposure backend.** When `coact` needs to expose a skill's bundled tools/scripts as MCP for a non-Claude-Code host, it calls `py2mcp`. `coact` does not write MCP server code itself. |

Also relevant (the user will point you at these; check before duplicating): `ov` issue #4 (the in-package agent productization spec — `coact` is the *generic, cross-project* version of that same skill→agent lift), and any existing "skills→agents transform" package the user mentions having written (find it, and either absorb or wrap it).

**Output of this step:** `REUSE.md` listing, per package, the exact symbols `coact` will import and the functionality `coact` will *not* build because it already exists.

---

## 2. What `coact` is (one paragraph)

`coact` helps developers **reuse their "AI stuff" across the layers of the modern agent stack** — concretely, it provides tools (some Python, but mostly *operated by skills and agents built on top of those tools*) to move along this chain:

```
python functions/scripts  →  .claude/skills/  →  .claude/agents/ (definitions)  →  running agents (runtime/executor)
        (py2mcp, aw)            (skill pkg)            (coact: COMPLETE)              (coact: REALIZE)
```

`coact` owns the **two transitions the other packages don't**:
1. **COMPLETE** — start from `.claude/skills/` and *complete* them into `.claude/agents/` definitions that reference those skills and add the agent-only "extras" (persona, return contract, tool allowlist, model, memory).
2. **REALIZE** — take a (near-)full agent definition (the `.claude/agents/` file + its supporting skills) and produce an *actually running agent* — with a real runtime/executor — choosing the appropriate execution backend (host agent, Agent SDK, or MCP-exposed for foreign hosts).

The name `coact` = "act together" (co-act): skills and agents acting as one reusable substrate; also a nod to the host+package *co*operation model where Claude Code and `coact` share the work.

---

## 3. The conceptual model `coact` encodes (read carefully — this is the spec's spine)

These are the load-bearing ideas. The implementation should make them legible in the code.

### 3.1 Skills and agent-definitions are two serializations of the same procedural knowledge over the same tools
A `SKILL.md` (+ bundled scripts/resources) is *injected procedural knowledge that runs inside the caller's turn and returns nothing*. A subagent definition is *a separate worker with its own context, system prompt, tool allowlist, model, and a defined return value*. The information overlaps heavily; an agent is mostly **a skill plus a thin "extras" envelope**. `coact`'s COMPLETE step is the function that adds that envelope.

### 3.2 The skill→agent "delta" (the extras COMPLETE must synthesize)
Given a skill, an agent definition needs these fields. The table is the contract for the COMPLETE transform:

| Agent field | Source | COMPLETE must… |
|---|---|---|
| `name` | skill name | derive (mechanical) |
| `description` (when to delegate) | skill `description` | reuse, lightly adapt to delegation phrasing |
| `prompt` (system prompt / persona) | **not in skill** — skill body is procedural, not a persona | **synthesize**: wrap intent as "You are an agent that…" + invariants + the return contract |
| `skills` (names it may load) | the skill itself + skills it references | resolve the reference graph (mechanical) |
| `tools` (allowlist) | skill's scripts imply needed tools; skill frontmatter may not declare them | **derive then narrow** for least-privilege; see §4 frontmatter convention |
| `model` | **not in skill** | **choose** by policy (Haiku=read-only/explore, Sonnet=worker, Opus=orchestration/arch) |
| `memory` (`user`/`project`/`local`) | **not in skill** | **choose** by policy |
| `mcpServers` | implied if procedure needs external services | **wire** explicitly (via `py2mcp` when the service is the skill's own Python tools) |
| **return contract** | **not in skill** (skills return nothing) | **synthesize** — the single most important extra: define the agent's final-message schema so a manager can consume it |

The two extras that actually turn a skill into an agent are **the system prompt (persona/identity)** and **the return contract (consumable output)**. Everything else is policy you stamp on. Make these two first-class in the code, not afterthoughts.

### 3.3 Point, don't copy
A subagent does **not** inherit skills automatically — skills are available to a subagent only if listed in its `skills` field. Therefore the right factoring is: **the skill stays the single source of truth on disk; the agent definition *references* it by name.** `coact` must never copy skill bodies into agent files. Multiple agents may reference the same skill with different personas / tool restrictions / models. This matches your SSOT principle and `skill`'s `link_skills` (symlink, don't copy) philosophy — extend that philosophy to agents.

### 3.4 The seam `coact` should NOT cross: topology
A subagent definition cannot express multi-agent topology (graphs, conditional edges, cycles), and subagents cannot spawn subagents (flat, one-level delegation). That orchestration/control-flow logic is **not** information that lives in skill or agent files. `coact` generates **agent definitions + tool/MCP wiring** and stops there. Topology is left to either (a) the host agent's manager (Claude Code following an orchestration skill), or (b) a *thin orchestration shim* the user writes against the Agent SDK / `aw`'s workflow chaining. `coact` may *scaffold* such a shim (emit a starter) but must not try to be a topology engine like LangGraph. State this boundary in the README so users aren't surprised. (The `langgraph`/`crewai` realization backends added in DECISIONS D16 sit *inside* this seam: each realizes a **single** definition into a framework-native runnable it **exposes** for the user to compose, and serializes no graph/crew of its own — they do not cross the topology line.)

### 3.5 The cost gate (a value `coact` should surface, not just respect)
Multi-agent fan-out costs roughly an order of magnitude more tokens than a single agent, and the premium is worst on *interdependent* tasks (where workers need each other's outputs and the isolation benefit evaporates). So **realizing skills as a fleet of running agents is an optimization, not a default.** `coact` should make the cheap path (host agent runs the skills directly) the obvious default, and treat REALIZE-to-running-agents as opt-in, triggered by a real throughput/isolation need. Where practical, `coact` should help the user *see* the cost tradeoff (e.g. a `coact estimate` that reports the fan-out multiplier implied by an agent set) rather than silently spawning fleets.

---

## 4. A small new convention `coact` introduces: skill self-declaration frontmatter

The standard SKILL.md frontmatter (`name`, `description`) does not carry the information COMPLETE needs to derive tools, model, MCP, or a return contract. Rather than guess every time, `coact` defines an **optional, additive frontmatter block** that a skill author (or `coact` itself, semi-automatically) can fill in so the skill→agent lift becomes mechanical and reproducible (SSOT for the extras).

Proposed (decide exact key names; keep them namespaced to avoid colliding with the open SKILL.md standard, e.g. under a single `coact:` key):

```yaml
---
name: ux-analyst
description: Analyzes a captured UX evidence bundle for usability issues.
coact:
  tools: [Read, Grep, Glob]          # allowlist hint; COMPLETE may narrow further
  model: sonnet                       # policy hint
  memory: project
  mcp:                                # python tools to expose via py2mcp, if any
    - module: ov.analyzers
      functions: [score_contrast, find_tap_targets]
  returns:                            # the return contract (→ structured output schema)
    schema_ref: ov.schemas:UxFindings # or an inline JSON schema
  consumes: evidence_bundle           # optional: declares input contract
---
```

Rules:
- The block is **optional**. If absent, COMPLETE falls back to inference + policy defaults and *reports what it guessed* (never silently).
- It is **additive and ignored by other tools** — a skill with a `coact:` block is still a valid plain SKILL.md.
- COMPLETE reads it; REALIZE consumes the same block (esp. `mcp` and `returns`) so the two steps share one source of truth.
- Prefer this over a separate sidecar file, so the SKILL.md stays the SSOT.

If `skill`'s validator registry can be extended to validate this block, register a `coact` validator there rather than building a separate validation path (reuse §1).

---

## 5. COMPLETE — skills → agent definitions

**Goal:** from one or more skills, emit `.claude/agents/<name>.md` definitions (and/or in-memory equivalents) that reference the skills and add the §3.2 extras.

### 5.1 Public interface (proposed)
Mirror `skill`'s verb-style API (`create`, `validate`, `install`, `link`) so the two packages feel like one toolkit:

```python
from coact import complete, plan_completion, emit_agent

# Inspect what COMPLETE would synthesize, without writing files (progressive disclosure: dry-run first)
plan = plan_completion('.claude/skills/ux-analyst', policy=...)   # -> AgentPlan (the filled §3.2 table + provenance of each field)

# Produce an agent definition object from a skill (or skill dir / skill name)
agent_def = complete('.claude/skills/ux-analyst', policy=...)     # -> AgentDefinition

# Serialize to the two known targets (filesystem md, and programmatic SDK dict)
emit_agent(agent_def, target='claude-agents-md', dest='.claude/agents/')   # writes ux-analyst.md
emit_agent(agent_def, target='sdk-agent-dict')                              # returns the AgentDefinition kwargs for the Agent SDK
```

### 5.2 `AgentDefinition` (the SSOT object)
One in-memory representation that can serialize to *both* the filesystem `.claude/agents/*.md` format **and** the Agent SDK `AgentDefinition` (programmatic `agents={...}` kwargs). Fields mirror the SDK schema (`description`, `prompt`, `tools`, `model`, `skills`, `memory`, `mcpServers`) plus `coact`-specific `returns`/`consumes`. This is the bijective-where-possible core: one object, two serializations — exactly the §3.1 idea made concrete.

### 5.3 Emitters (open-closed; register, don't hardcode)
Make emit targets a registry (follow `skill.translate.translators` style). Ship at least:
- `claude-agents-md` — the `.claude/agents/<name>.md` (YAML frontmatter + persona body).
- `sdk-agent-dict` — kwargs for `claude_agent_sdk.AgentDefinition` / the `agents=` param.

Leave room for future emitters (CrewAI, LangGraph node, etc.) without touching core. **Do not** emit topology (§3.4).

### 5.4 Policy (dependency-injected, like `aw`'s `StepConfig`)
The model/memory/tool-narrowing choices are **policy**, injected, with cascading defaults (reuse `aw`'s `GlobalConfig`/`StepConfig` cascade pattern rather than a new config system). A default policy implements the §3.2 heuristics (Haiku/Sonnet/Opus routing, least-privilege tool narrowing). Users override per-skill or globally.

### 5.5 Persona & return-contract synthesis (the hard, valuable part)
These two fields are not mechanical. Design the synthesis so it is:
- **Inspectable** — `plan_completion` shows the proposed persona and return schema before writing.
- **Overridable** — author can pin them in the `coact:` frontmatter (§4) and synthesis must defer to that.
- **LLM-assisted but not LLM-required** — synthesis may *optionally* use an injected LLM (via `aw`'s `llm`) to draft a persona from the skill body; without an LLM it produces a sound template. Never hard-depend on a provider (no lock-in — mirror `ov` issue #4's `llm.py` facade requirement and `aw`'s injectable `llm`).

---

## 6. REALIZE — agent definitions → running agents

**Goal:** turn a completed agent definition (+ its skills) into something that actually runs, picking the right executor. This is the "how? via MCP? see about that" question — the answer is **plural**: `coact` offers a small set of realization backends behind one interface, because "running agent" means different things for different hosts.

### 6.1 The three realization backends (ship at least the first two)

1. **`host` (default, cheapest, recommended)** — Do **not** stand up a new runtime. Install/link the skills (via `skill.install` / `link_skills`) and write the agent `.md` into `.claude/agents/`, so the *host* agent (Claude Code) becomes the executor and its manager does the delegation. "Realize" here = correctly materialize files so the host picks them up. This is the §3.5 cheap default. `coact realize --backend host` should essentially be: emit agents + link skills + verify discovery.

2. **`sdk` (in-process / programmatic)** — Produce a runnable Python object backed by the **Claude Agent SDK**: build the `agents={...}` map (from `emit_agent(..., 'sdk-agent-dict')`), wire `query()` options (allowed tools incl. `Agent`, the skills, mcpServers), and return a callable/`AgenticStep`-compatible object. **Make the returned thing satisfy `aw`'s `AgenticStep` protocol** (`execute(input_data, context) -> (artifact, info_dict)`) so `coact`-realized agents drop straight into `aw` workflows and reuse `aw`'s retry/validation/human-in-loop. This is where `coact` and `aw` meet.

3. **`mcp` (foreign-host / interop)** — For non-Claude-Code hosts (or to expose a skill's tools to *any* MCP client): use **`py2mcp`** to stand up an MCP server from the skill's bundled Python tools (the `coact: mcp:` frontmatter declares which functions), so the capability is reachable as MCP. `coact` does not write MCP plumbing — it calls `py2mcp.mk_mcp_server` / `mk_mcp_from_store`. (This is the optional `py2mcp` server mentioned in `ov` #4, generalized.)

### 6.2 Public interface (proposed)
```python
from coact import realize

# host backend: materialize files so Claude Code runs it
realize(agent_def_or_dir, backend='host', dest='.')

# sdk backend: get a runnable, aw-compatible object
agent = realize(agent_def, backend='sdk', llm=...)   # -> RunnableAgent (AgenticStep-compatible)
artifact, info = agent.execute(task_input, context)

# mcp backend: expose the skill's tools as an MCP server (delegates to py2mcp)
server = realize(agent_def, backend='mcp')           # -> py2mcp server handle
server.run()
```

### 6.3 The realization interface is a registry (open-closed)
`backend=` selects a registered `RealizationBackend`. Ship `host`, `sdk`, `mcp`; let users register more (e.g. a remote/containerized executor) without modifying core. Each backend declares what it needs (e.g. `sdk` needs the Agent SDK installed; degrade gracefully with an informative error per your package-UX conventions if a backend's optional deps are missing — follow `check_requirements` pattern).

### 6.4 What REALIZE explicitly does not do
No topology/orchestration engine (§3.4). For multi-agent runs it may **scaffold** a starter shim (a small Python file wiring N realized `sdk` agents under a coordinator using `aw` orchestration), clearly marked as a starting point the user owns. It does not become a long-running multi-agent platform.

---

## 7. Round-trip & analysis utilities (the "navigate the layers" tooling)

Beyond the two transforms, `coact` provides small tools that help developers *see and move between* layers. Keep these thin.

- `coact diff <skill> <agent>` — show what extras an agent adds over its source skill (renders the §3.2 table with provenance). Helps audit drift between SSOT skill and derived agent.
- `coact estimate <agent-set>` — surface the §3.5 cost tradeoff: report the implied fan-out token multiplier and flag interdependent sets where multi-agent is a poor fit.
- `coact inventory <project>` — enumerate skills, derived agents, exposed MCP tools across a project (reuse `skill`'s discovery; add the agent + MCP dimensions). One picture of a project's reusable AI assets.
- (Optional) `coact back` — best-effort *agent → skill* extraction (strip the persona/return-contract envelope back down to reusable procedural knowledge), for harvesting an ad-hoc agent into a reusable skill. Lossy by nature; mark as such.

---

## 8. Architecture, conventions, and non-negotiables

Follow the user's two loaded skills (`python-coding-standards`, `python-package-architecture`) as the authority on style; highlights that matter here:

- **Functional > OOP; composition > inheritance; declarative > imperative** (without dogma). Transforms are functions; configuration/policy is injected data, not subclassing.
- **Registries / plugin architecture / open-closed** for: emit targets (§5.3), realization backends (§6.3), and completion policies (§5.4). Where a registry already exists in `skill` (validators, agent_targets, translators), **register into it** instead of creating a parallel one.
- **SSOT**: the skill on disk is the source of truth for procedural knowledge; the `coact:` frontmatter is the source of truth for the extras; the `AgentDefinition` object is the single in-memory representation with multiple serializations. No duplication of skill bodies.
- **Dependency injection / no provider lock-in**: any LLM use goes through an injected facade (reuse `aw`'s `llm` / `StepConfig`; honor `ov` #4's provider-agnostic `structured(prompt, schema)->model` shape). `coact` must run its mechanical paths with **no LLM at all**.
- **Mapping interfaces**: prefer `Mapping`/`MutableMapping` facades (a skills store, an agents store) consistent with `dol`/`py2mcp` idioms; this also makes `py2mcp.mk_mcp_from_store` reuse natural.
- **Progressive disclosure**: simple things simple (`complete(skill)` one-liner with good defaults), complex things possible (full policy injection, custom emitters/backends). Always offer a dry-run/plan before a writing/spawning action.
- **CLI via `argh`**, dispatch-to-interface pattern (CLI / http via `qh` / programmatic share one core), package structure per `python-package-architecture` (`__init__.py` curated exports, `base.py`, `util.py`, `__main__.py`). The verbs (`complete`, `realize`, `diff`, `estimate`, `inventory`) are both Python functions and CLI subcommands.
- **Informative errors & `check_requirements`** for optional backends/deps (Agent SDK, FastMCP/`py2mcp`, an LLM provider).

---

## 9. Proposed package layout (adjust to conventions)

```
coact/
├── __init__.py          # curated exports: complete, realize, plan_completion, emit_agent, diff, estimate, inventory
├── base.py              # AgentDefinition (SSOT object), AgentPlan, protocols, the coact: frontmatter model
├── complete.py          # COMPLETE transform + persona/return-contract synthesis
├── emit.py              # emitter registry (claude-agents-md, sdk-agent-dict) — reuse skill.translate where possible
├── realize.py           # realization backend registry (host, sdk, mcp)
├── policy.py            # completion policy (model/memory/tool routing); reuse aw StepConfig cascade
├── frontmatter.py       # parse/validate the coact: block; register validator into skill.create.validators
├── analysis.py          # diff, estimate, inventory
├── llm.py               # provider-agnostic LLM facade (thin; prefer importing aw's; only add structured() helper if absent)
├── util.py
└── __main__.py          # argh CLI dispatch
misc/docs/
└── REUSE.md             # output of §1
```

If `complete.py`/`realize.py` grow, split into subpackages with their own registries. Keep `__init__.py` curated (don't dump everything).

---

## 10. Build order (suggested milestones)

1. **Reuse audit** (§1) → `REUSE.md`. Import the real symbols from `skill`/`aw`/`py2mcp`; confirm signatures. Find the user's existing skills→agents package.
2. **`AgentDefinition` + two emitters** (§5.2–5.3): one object → `claude-agents-md` and `sdk-agent-dict`. Round-trip tests (load an emitted md back into an equivalent object).
3. **COMPLETE, mechanical path only** (§5.1, §5.4, §4): no LLM. Reads `coact:` frontmatter + policy defaults; `plan_completion` dry-run shows provenance. This alone delivers real value.
4. **`coact: ` frontmatter convention + validator** (§4), registered into `skill`'s validator registry.
5. **REALIZE `host` backend** (§6.1.1): emit agents + link skills + verify discovery. The cheap default working end-to-end with Claude Code.
6. **REALIZE `sdk` backend** (§6.1.2): runnable, `aw.AgenticStep`-compatible object. Integration test that an `sdk`-realized agent runs in an `aw` workflow.
7. **Persona/return-contract synthesis with optional injected LLM** (§5.5).
8. **REALIZE `mcp` backend via `py2mcp`** (§6.1.3).
9. **Analysis utilities** (§7): `diff`, `estimate`, `inventory`.
10. **CLI** (`argh`, §8) wrapping the verbs; completion via the same pattern `skill` uses.

Each milestone should be independently useful and shippable (progressive disclosure applies to the *roadmap* too).

---

## 11. Decisions to record (write these into `misc/docs/DECISIONS.md` as you go)

- Exact `coact:` frontmatter key names & whether to register validation into `skill`.
- Whether `AgentDefinition` subclasses/wraps the SDK's type or is independent with adapters (lean independent + adapters, to avoid hard SDK dependency in core).
- How `tools` narrowing infers required tools from a skill's scripts (static import scan? declared-only? hybrid?).
- The default model-routing policy table.
- Whether `host` backend writes into the project `.claude/` or a user-scope dir by default (mirror `skill`'s `scope` argument).
- The return-contract representation (JSON Schema vs Pydantic ref vs both) and how `sdk` realization maps it to Agent SDK structured outputs.

---

## 12. Definition of done (for the first useful release)

- `complete()` turns a skill (with or without a `coact:` block) into an `AgentDefinition`, and `emit_agent()` writes a valid `.claude/agents/*.md` that Claude Code discovers and that references (does not copy) the source skill.
- `realize(..., backend='host')` makes that agent actually usable by Claude Code end-to-end.
- `realize(..., backend='sdk')` returns an object that runs and satisfies `aw.AgenticStep`.
- Nothing in `skill`/`aw`/`py2mcp` is reimplemented; `REUSE.md` documents the boundaries.
- No hard LLM/provider dependency on any mechanical path; topology is explicitly out of scope and documented as such.
