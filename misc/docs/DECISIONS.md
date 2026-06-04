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

**Implementation notes (both `sdk` paths now wired).** `RunnableAgent.return_mode`
= `auto | output_format | tool`. `auto` uses the native `output_format` when the
installed `ClaudeAgentOptions` exposes the field, else the forced-tool fallback.
Non-obvious gotchas that the build surfaced (recorded so they aren't re-discovered):

- **The forced `return_result` tool requires SDK *streaming* mode.** In-process SDK
  MCP servers are wired over the control protocol, which `query()` initializes
  **only** when the prompt is *not* a plain string. So `_default_sdk_runner` uses
  `ClaudeSDKClient` (always streaming) — a one-shot `query(prompt=<str>)` would
  leave the return tool unreachable.
- **`mcp_servers` is normalized to the SDK's `dict[name→config]` on every path.**
  coact's model stores it as a list of names/inline-dicts; handing the SDK a bare
  list is invalid and the fallback must merge (not clobber) the agent's own servers.
  Bare names can't become SDK configs and are reported in `info["warnings"]`.
- **A non-object return schema is wrapped under a `result` key** (the SDK passes a
  dict `input_schema` through unchanged only when it has both `type` and
  `properties`); a *free-form* object (`{type: object}` w/o `properties`) is given
  an empty `properties` and passed through **unwrapped**, to avoid colliding with a
  model's own `{result: …}` output. Extraction unwraps only an exact `{result}` dict.
- A declared-but-unresolvable `schema_ref` **raises** at realize time rather than
  silently dropping the contract; an explicit `output_format` on an SDK lacking the
  field also raises (only `auto` silently degrades to `tool`).
- `resolve_schema_ref` now produces **typed** properties for dataclasses / TypedDicts
  (`_annotation_to_schema`: primitives, `Optional`/union→`anyOf`, `list[X]`→typed
  `items`, nested objects one level) plus a `required` list — not just permissive
  `{}` placeholders. Pydantic still wins via `model_json_schema`; unknown
  annotations fall back to `{}` so resolution never crashes.

**Live tests are opt-in.** A `real_llm` pytest marker gates the end-to-end smoke
tests (`tests/test_live_realize.py`); `tests/conftest.py` skips them unless
`COACT_RUN_REAL_LLM=1` is set, so the default suite stays offline and CI spends no
tokens. Both the `sdk` and `litellm` backends were verified live this way (the
streaming-runner fix above is confirmed end-to-end, not just unit-tested).

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

## D11 — PyPI publishing is marker-gated, not automatic

`[tool.wads.ci.publish].enabled = false`. In the wads CI model the publish job's
`if` condition is `publish-enabled == 'true' || contains(commit_message,
publish-marker)`. With `enabled = false`, routine pushes to `main` **skip** the
publish job entirely (so `main` stays green), and a release happens **only** when
a commit message contains the `publish_marker` (`"[publish]"`).

**Why not `enabled = true` like the sibling repos (`skill`/`aw`/`py2mcp`):** those
publish on every main push because they have a `PYPI_PASSWORD` secret and an
established release cadence. `coact` is new (only `0.0.2` on PyPI, hand-published);
the repo has **no** `PYPI_PASSWORD` secret, so an `enabled = true` posture made
every main push fail at `uv publish` with a 403 (empty token). Releasing a *new*
public package version is a deliberate, owner-initiated act — gating it behind an
explicit `[publish]` marker keeps CI honest (green when it should be) and makes the
release moment intentional. To ship: set the `PYPI_PASSWORD` repo secret, then land
a commit whose message contains `[publish]`.

> **Footgun, learned the hard way:** once the `PYPI_PASSWORD` secret exists, the
> gate is satisfied by the literal substring `[publish]` appearing **anywhere** in a
> main-bound commit message — including a commit that merely *documents* the marker.
> Never put the literal marker in a commit subject/body or a squash-merged PR body
> unless you intend to release. (`0.0.3` published exactly this way: the secret was
> added mid-session, and a CI-gating commit whose message explained the marker
> tripped it. The artifact was the clean pre-D6 foundation, so no harm — but the
> lesson stands.) File content (this file, the pyproject comment) is safe; only
> commit/PR **messages** feed the gate.

## D12 — A LiteLLM realization backend proves the definition is provider-portable

The `host`/`sdk` backends realize against the Anthropic stack. To make good on the
core thesis — *one canonical `AgentDefinition`, portable across the agent stack* —
a `litellm` backend realizes the **same** definition against **any** provider
LiteLLM speaks (OpenAI, Anthropic, Gemini, Mistral, Ollama, …). The mapping:

- persona (`prompt`) → system message;
- return contract → LiteLLM `response_format` (`json_schema`) **and** a system-prompt
  instruction (belt-and-suspenders, since provider support for structured output
  varies — mirrors the D6 fallback philosophy);
- model selector (`sonnet`/`opus`/`haiku`) → a LiteLLM model string via an
  **open-closed, data-driven** `model_map` (override per call to target any provider);
  an explicit LiteLLM string in `model` is used verbatim.

It is an `aw.AgenticStep`-compatible `RunnableLLMAgent` (like the `sdk` backend), the
completion call is **injectable** (unit-testable with no API key), and it
**self-registers** into `coact.realize.backends` on import — *no core change*, the
open-closed extension point working as designed.

**Why LiteLLM over the OpenAI-Agents SDK:** the OpenAI-Agents SDK models tools as
Python callables, but a coact definition carries tool *names* (host-resolved), which
don't map cleanly; LiteLLM's chat-completion-with-structured-output maps exactly onto
what a definition actually carries (persona + return contract). Topology stays out
(D8): one definition → one runnable. LangGraph/CrewAI *realizers* remain deferred.
