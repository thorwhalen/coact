# DECISIONS.md — `coact` design decisions

> The §11 decision log. Each entry: the decision, and the *why*. Append as the
> build proceeds; never silently reverse a recorded decision.

## D1 — `coact:` frontmatter: one namespaced key, snake_case interior

A single additive top-level `coact:` key in SKILL.md frontmatter (so a skill
carrying it is still a valid plain SKILL.md, ignored by other tools). Interior
keys are **snake_case** (Python-friendly, matches the rest of the ecosystem):

```yaml
coact:
  tools: [Read, Grep, Glob]      # allowlist hint; policy may narrow further
  disallowed_tools: []           # denylist hint
  model: sonnet                  # policy hint (sonnet|opus|haiku|inherit)
  memory: project                # user|project|local
  permission_mode: default       # optional
  skills: []                     # extra skill refs beyond the source skill
  mcp:                           # python tools to expose via py2mcp
    - module: ov.analyzers
      functions: [score_contrast, find_tap_targets]
  returns:                       # the return contract
    schema_ref: ov.schemas:UxFindings   # OR inline `json_schema: {...}`
    description: "Usability findings for the captured bundle"
  consumes: evidence_bundle      # optional input contract
  persona: |                     # optional: pin the system prompt (else synthesized)
    You are a meticulous UX analyst...
```

**Why snake_case interior but camelCase on emit:** the `coact:` block is authored
by humans/Python and read by `coact`; the *emitted* `.claude/agents/*.md`
frontmatter uses the host's exact field names (`disallowedTools`, `mcpServers`,
`permissionMode`) because Claude Code parses those. `coact` owns the mapping.

## D2 — `AgentDefinition` is independent, with adapters (NOT an SDK subclass)

`coact.base.AgentDefinition` is its own `@dataclass`, a **lossless superset** of
the host/SDK schema: `name, description, prompt, tools, disallowed_tools, model,
skills, memory, mcp_servers, permission_mode, returns, consumes` (+ provenance).

Confirmed necessary by inspection: the **installed** `claude_agent_sdk` 0.1.10
`AgentDefinition` exposes only `description, prompt, tools, model` — a moving,
lossy projection. Subclassing it would couple `coact` core to a volatile,
incomplete type and force a hard SDK dependency. Instead:

- `emit_agent(ad, 'sdk-agent-dict')` builds the SDK `AgentDefinition` by passing
  **only the fields the installed dataclass accepts** (introspected via
  `dataclasses.fields`), returning the remainder (skills, memory, mcpServers) as
  separate `query()` options. The SDK is imported **lazily**, only in that
  adapter and the `sdk` realize backend.
- core (`base`, `complete`, `emit` of the md target) has **no** SDK import.

## D3 — Tool narrowing: declared-or-heuristic + always report provenance

Precedence: (1) `coact: tools` if present → use as the allowlist seed; (2) else
heuristic from the skill's resource manifest — `scripts/` present ⇒ `Bash`;
mention of writing/editing in the body ⇒ `Write`/`Edit`; default analysis set
`{Read, Grep, Glob}`. Then **narrow** to least-privilege per policy. Static
import scanning of scripts is deferred (over-engineering for v1). Every inferred
field records *why* in `AgentPlan.provenance` and `plan_completion` prints it —
never silently guesses.

## D4 — Default model-routing policy table

| Model | When |
|---|---|
| `haiku` | read-only / explore: effective tools ⊆ `{Read, Grep, Glob, WebFetch, WebSearch}` |
| `opus` | orchestration / architecture: description matches `orchestrat|architect|plan|coordinat|design|review` **or** the agent references ≥3 skills |
| `sonnet` | default worker: anything with `Write`/`Edit`/`Bash` not matched above |

Injected and overridable per-skill (`coact: model`) or globally
(`CompletionPolicy`). The table is data, not code branches — extensible.

## D5 — `host` backend writes project scope by default (mirrors `skill.scope`)

`realize(..., backend='host', scope='project')` writes `.claude/agents/<name>.md`
into the project and links the source skills into the project
`.claude/skills/` (via `skill.link_skills`). `scope='global'` targets
`~/.claude/`. Mirrors `skill`'s `scope` argument exactly. Default `project`
(least surprising, repo-local, reviewable in git).

## D6 — Return contract: JSON Schema is canonical; refs resolve to it

`ReturnContract` holds a canonical **JSON Schema** dict plus an optional source
`ref` and a human `description`. Authors may supply either `schema_ref`
(`module:Name`, resolving a Pydantic model / dataclass / TypedDict to JSON
Schema) or inline `json_schema`. Realization mapping:

- `sdk`: pass the JSON Schema to the Agent SDK structured-output option when
  available; otherwise inject a "return exactly this schema" instruction plus a
  forced `return_result` tool whose `input_schema` is the JSON Schema.
- `claude-agents-md`: render the schema into the persona body as the explicit
  **Return contract** section (subagents return free text → the schema tells the
  manager how to parse it).

JSON Schema chosen over Pydantic-in-core to avoid a hard pydantic dependency and
to stay portable across the realization backends (§interop research).

## D7 — Validator registered into `skill.create.validators` (+ entry point)

`coact` registers `coact_frontmatter` into `skill`'s validator registry at
import, and declares a `skill.validators` entry point in `pyproject.toml` so it
is discoverable without importing `coact`. The validator is also runnable
standalone (`coact.frontmatter.validate_coact_block`). Additive — a skill with
no `coact:` block passes trivially.

## D8 — Topology stays out (scaffold only)

`coact` emits agent definitions + tool/MCP wiring and stops. Multi-agent
topology (graphs, conditional edges, cycles) is **not** serialized. For fan-out
the `sdk` backend can *scaffold* a starter shim (a Python file wiring N realized
agents under an `aw` coordinator), clearly marked as user-owned. `coact` is not
LangGraph. Documented in the README boundary section.

## D9 — Cost gate is surfaced, cheap path is default

`realize` defaults to `backend='host'` (the host agent runs the skills — no 15×
fan-out multiplier). `coact estimate <agent-set>` reports the implied fan-out
token multiplier and flags interdependent sets where multi-agent is a poor fit,
per the interop research. Spawning a fleet is opt-in, never implicit.

## D10 — No LLM on any mechanical path

COMPLETE's mechanical path (read `coact:` + policy defaults), all emitters, the
`host` backend, and analysis utilities run with **zero** LLM. The LLM is used
*only* for optional persona/return-contract drafting (§5.5) and is always
injected through `coact.llm` (wrapping `skill.ai.chat` or an `aw` `StepConfig`
llm or any `callable(str)->str`). Absent an LLM, synthesis produces a sound
template. No hard provider dependency anywhere.
