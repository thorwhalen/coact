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
established release cadence. `coact` is new (only `0.0.3` on PyPI, hand-published);
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
(D8): one definition → one runnable. (The LangGraph/CrewAI *realizers*, deferred here,
followed in **D16** — still single-agent, topology still out.)

## D13 — The §6.4 fleet-scaffold shim is implemented (the one topology-adjacent emit)

`coact.scaffold.scaffold_fleet(target, *, dest=None, agents_dir=…)` realizes the
single capability D8 reserves: for a multi-agent run it **emits a starter Python
file** wiring N realized `sdk` agents under an `aw` coordinator, "clearly marked as
a starting point the user owns." It is a pure **string/file emitter** — it runs no
LLM and stands up no runtime; the emitted shim defers all execution to
`realize(..., backend='sdk')` and *all topology to the human who owns it*.

This does **not** soften D8. coact still serializes no graph: the shim is a
deliberately thin **sequential** hand-off with `TODO(you)` markers and an embedded
cost-gate + ownership notice, not a topology engine. The boundary is "coact writes
the starter once and never runs it." Exposed as `scaffold_fleet` in `__all__` and
the `coact scaffold <agents…>` CLI verb. The §6.4 promise (previously documented as
deferred) is now kept; LangGraph/CrewAI orchestration stays the user's to own.

## D14 — Hardening pass: version-from-metadata, module decomposition, realize dry-run

A round of robustness + clean-up that changed no public contract:

- **`__version__` is sourced from `importlib.metadata.version("coact")`** (with a
  `0.0.0+unknown` sentinel for an uninstalled tree), not a second hand-edited
  literal. The SSOT is `pyproject.toml` (what wads bumps on release); deriving the
  attribute from installed metadata makes drift structurally impossible (it had
  drifted to `0.0.2` while pyproject was `0.0.3`).
- **Two cohesive subsystems were extracted** from the largest modules, with the
  old import paths preserved (re-export) so nothing downstream broke:
  `coact.schema` (the `resolve_schema_ref` typed JSON-Schema resolver, out of
  `base.py` — leaving it a pure data model) and `coact.return_contract` (the
  backend-agnostic D6 helpers — `ReturnPlan`, mode selection, `as_object_schema`,
  the two instruction renderers, tool-use extraction — out of `realize.py`, which
  keeps only the SDK-specific wiring). The two return-instruction builders that
  `realize`/`realize_litellm` had duplicated now share one home (DRY).
- **`_resolve_skill`/`_coerce_agents` became public** (`resolve_skill`/
  `coerce_agents`): they are imported across modules, and the house rule is that
  cross-module helpers carry no leading underscore.
- **`realize(..., backend='host', dry_run=True)`** previews the files/links that
  *would* be written without touching the filesystem (a `RealizedHost` with
  `dry_run=True`), extending `plan_completion`'s look-before-you-leap contract to
  the one backend that mutates disk (progressive disclosure, COACT_SPEC §8). Also
  on the CLI as `coact realize … --dry-run`.
- **Robustness fixes:** `llm._extract_json` no longer crashes on a `None` LLM reply
  (D10 "no crash"); the `litellm` `response_format` fallback now **surfaces** the
  error that forced the retry in `info['response_format_error']` (graceful
  degradation that is no longer silent); `check_requirements` reports which deps are
  already present alongside what is missing.

Test depth grew with the surface: dedicated suites for the CLI, the LLM facade, the
frontmatter validator, `util`, `stores`, `policy`, and the two new modules
(`schema`, `return_contract`, `scaffold`) — ~120 new tests, coverage 88% → 95%
(the residual is the live Agent-SDK runner, exercised only by the opt-in `real_llm`
tests).

## D15 — Second review pass: filesystem boundary is now traversal-safe, JSON extraction is balanced

A second deep-review pass (7 read-only finder dimensions → per-finding adversarial
verification; 11 confirmed, 9 refuted). The refuted set was correctly intended-by-
design and **not** actioned: the `__all__`/D14 re-export trio (the D14 re-exports are
*module-level* old-import-path shims and `resolve_skill`/`coerce_agents` are
submodule-public cross-module helpers — neither was ever promised in
`coact.__init__.__all__`), and the `schema_ref` "arbitrary code execution" pair
(`schema_ref` is **author-pinned, trusted** input per D6, guarded by
`isinstance(obj, type)` and yielding `None` on anything unrecognized — a supply-chain
threat model, not a coact defect). The confirmed defects, all fixed with no public-
contract or prior-decision change:

- **Path traversal at the filesystem boundary (CWE-22).** An agent `name` becomes a
  `<name>.md` file; a crafted name (`../../x`) escaped `.claude/agents/` on **write
  *and* read** at two sites (`emit.emit_agent`, `stores.AgentStore._path`). Fix: one
  `util.agent_filename(name)` validator (rejects path separators / `..` / empty /
  null), applied at every write boundary (`emit_agent`, `AgentStore._path`,
  `realize_host`). **Validation lives at the boundary, not on `AgentDefinition`** — an
  in-memory definition with any name is legal; only *materializing* it to disk is
  constrained. `AgentStore.__contains__` swallows the `ValueError` to stay a total
  membership test (an unsafe key is simply not a member).

- **`_try_json` extraction was unbalanced.** The litellm last-resort used independent
  `find('{')`/`rfind('}')` (and a separate `[`/`]` pass), which mismatched
  openers/closers: `{found: [1,2,3]}` (an invalid object) wrongly returned the nested
  `[1,2,3]`, and a trailing stray `}` made a valid object unparseable. Fix: a shared
  `util.first_balanced_span(s, opener, closer)` (depth-tracking, string-aware) now
  backs **both** JSON extractors; `_try_json` takes the *earliest top-level* balanced
  span and parses only that (a nested fragment from an unparseable span would violate
  the return contract). `llm._first_balanced_object` became a thin object-only wrapper
  over the shared primitive — the two extractors keep their distinct contracts
  (dict-only vs. any) but share the one matcher (so a blind "merge them" was rejected).

- **mcp validator** now requires a non-empty `functions` list per entry (D1/§4 pair
  `module`+`functions`); a lone `module` previously passed validation then silently
  exposed zero tools.

- **`realize_host` no longer leaves partial output.** It renders every agent up-front
  (pure, validating each name) and writes only after all render, so a predictable
  failure aborts before any file lands. Not full dir-rename atomicity (D5 promises no
  rollback), but the realistic partial-write is gone.

- **Housekeeping:** removed dead `emit._HOST_TO_SNAKE`; closed three test gaps (the SDK
  `.result` extraction fallback, the `output_format` raw-dict artifact value, and the
  mcp-no-tools error message's `coact: mcp:` guidance) plus regression tests for every
  fix above. `+24` tests / `+2` doctests; suite stays green, ruff `D100`+`F` clean.

## D16 — LangGraph & CrewAI single-agent realizers (D8 upheld)

Two new realization backends, `langgraph` and `crewai`, realize the **same**
canonical `AgentDefinition` against two more runtimes — extending the portability
thesis (D12) past LiteLLM. Each realizes **exactly one** definition into one runnable
and **raises** on more than one ("topology is out of scope — DECISIONS D8"), exactly
like `sdk`/`litellm`. This **supersedes only the "LangGraph/CrewAI realizers remain
deferred" clause of D12**; it does **not** soften D8:

- **Single agent, not a graph.** The frameworks are used as *execution engines for one
  agent*. coact serializes no nodes/edges/tasks/process. A multi-agent run still uses
  `scaffold_fleet` (D13).
- **The framework-native object is exposed, not owned.** `langgraph` returns a
  `CompiledStateGraph` (built via `langchain.agents.create_agent`, its `name` = the
  agent's name); `crewai` returns a `crewai.Agent` (run via the lightweight
  `Agent.kickoff`, **not** `Crew`/`Task`, which would invent topology). Both are reachable
  via `build_agent()` / the `.agent` property precisely so the *user* composes them into
  *their own* `StateGraph` / `Crew`. coact realizes the agent; the user owns the topology
  it joins. This is the §3.4 "leave room for a future LangGraph node … without … topology"
  seam, finally filled.
- **Same shape as litellm (open-closed, DI, lazy).** Both are `aw.AgenticStep` runnables
  (`execute -> (artifact, info)`), self-register into `realize.backends` on import, take a
  data-driven defensively-copied `model_map` (langchain **colon**-form `provider:model`
  for langgraph; LiteLLM **slash**-form for crewai), import their framework **lazily**
  behind `check_requirements`, and are unit-testable with an injected `factory`/`runner`
  (no API key, no install — `import coact` pulls in none of langchain/langgraph/crewai).
- **Return contract (D6), belt-and-suspenders.** langgraph passes the canonical JSON
  Schema dict to `ToolStrategy`/`ProviderStrategy` (both accept a raw dict — **no pydantic
  synthesis**) *and* embeds the in-prompt instruction, JSON-parsing the final message text
  when the native `structured_response` is absent (langchain can omit it without error).
  crewai's `kickoff(response_format=)` is class-only, so a *flat* schema is synthesized to
  a pydantic model (`coact._pydantic_schema.json_schema_to_model`, returning `None` →
  prompt-only for non-flat schemas) — the one langgraph-vs-crewai asymmetry (langgraph
  enforces deep schemas natively; crewai falls back to the prompt).
- **Tools are opt-in (D12).** coact tools are host-resolved *name strings* and both
  frameworks want Python callables, so bare names are never passed. A `tools_map={name:
  callable}` binds them for a real tool-use loop; unbound names surface in
  `info['unbound_tools']` (langgraph) / `info['warnings']` (crewai), never dropped.
- **Packaging.** In-repo modules (`coact/realize_langgraph.py`, `coact/realize_crewai.py`)
  + optional extras `coact[langgraph]` / `coact[crewai]`. `[langgraph]` ships
  `langchain-openai` so the openai-prefixed default model works out of the box; an
  `anthropic:` model additionally needs `langchain-anthropic`. crewai requires Python
  `<3.14`; coact does not tighten its own `>=3.10` pin for one optional backend.

Verified against the installed langchain/langgraph 1.0.1 (`create_agent`,
`ToolStrategy(dict)`, `ProviderStrategy(dict)`); the crewai path is research-verified and
fully `getattr`-guarded — its unit suite is injected-runner-only (asserts crewai never
enters `sys.modules`) and its live test is opt-in (`real_llm`) and `importorskip`-ped.

---

## D17 — PUBLISH: a third axis (ship a capability to a chatbot host)

COMPLETE and REALIZE answer "turn a skill into an agent" and "run that agent". A
distinct need — *take a capability and ship it to an end-user chatbot* (a Claude
**connector**/**plugin**/**Desktop Extension**, later ChatGPT/Gemini) — is the
**PUBLISH** axis (`coact.publish` + `coact.integration` + per-target modules).
Decision and its rationale (background research:
`misc/docs/CHATBOT_INTEGRATION_LANDSCAPE.md`):

- **A separate `IntegrationSpec`, not an extended `AgentDefinition`.** An
  integration is MCP-server-shaped (tools/resources/prompts + auth + deployment),
  not persona-shaped. Overloading `AgentDefinition` (D2) would muddy the "an agent
  is a skill + extras" thesis, so PUBLISH gets its own pure-data SSOT. Only
  `tools` (`'module:function'` refs) is consumed today; `resources`/`prompts` and
  the `auth`/`deployment` hints are declared now (open-closed) for later targets.
- **Same registry shape as REALIZE/emit (open-closed, self-registering).**
  `publish(source, target=...)` dispatches through a `skill.registry.Registry`;
  targets call `targets.register(...)` at import (like D12/D16 backends). A new
  host = a new module, **no edit to `publish.py`**. Claude is deliberately *one*
  target among future ones (target-neutral).
- **coact writes packaging, not MCP plumbing (mirrors §6.1.3 / the `mcp` backend).**
  The canonical artifact is an MCP server built by **`py2mcp`**; the
  `claude-local-mcpb` target only assembles the `.mcpb` bundle (manifest + a
  `server/` shim that launches `py2mcp.serve` over stdio). Building a bundle is
  pure stdlib (`json` + `zipfile`); `py2mcp`/`fastmcp` are needed only in the
  Python that *runs* the installed extension, so a missing runtime dep is a
  **warning**, not a build error (no hard `check_requirements` gate on the build
  path — it would wrongly block bundling on a machine that only authors).
- **Local first; the local/remote split is load-bearing (§9.3).** `claude-local-mcpb`
  is the LOCAL surface — stdio, no OAuth, runs on the user's machine. It is **not**
  a claude.ai remote *connector* (a remote MCP server reached from Anthropic's
  cloud over HTTPS + OAuth); that is a future target with its own deploy/auth
  story (and will lean on `aw_agents` adapters). The CLI/skill state this so the
  two surfaces are never conflated.
- **dry-run, name safety, D8.** `publish(..., dry_run=True)` returns the
  would-write members without touching disk (mirrors `realize(host, dry_run=True)`);
  bundle filenames route through `util.safe_filename` (the D15 path-traversal
  guard, generalized from `agent_filename`). A bundle packages a *capability set*,
  not a topology — D8 holds.
- **py2mcp's role (upstream, first customer = coact).** py2mcp already emits a
  standalone-`fastmcp` server; PUBLISH only needed a thin **stdio runner**
  (`py2mcp.serve` + `python -m py2mcp` + a `py2mcp` console script) so a bundle can
  launch it. Built in py2mcp, not inlined here (cross-package policy).
- **Packaging.** `coact/integration.py` + `coact/publish.py` + per-target
  `coact/publish_mcpb.py` (self-registers `claude-local-mcpb`); optional extra
  `coact[mcpb]`; CLI verb `coact publish`; skill `.claude/skills/coact-publish`.

Verified end-to-end: `coact publish os.path:basename --name demo --dest <dir>`
writes a valid `.mcpb` (ZIP) with a `manifest_version: "0.3"` manifest
(`server.type: python`, `${__dirname}/server/main.py`), docstring-introspected
`tools` metadata, and a `py2mcp_config.json` the shim feeds to `py2mcp.serve`.

## D18 — PUBLISH ingress, part 2: NL-description → IntegrationSpec (the opt-in LLM path)

D17 shipped the *mechanical* PUBLISH ingress (`integration_spec_from`: refs /
callables / skills → spec, zero LLM). This adds the **second input arm** from the
landscape doc §9.2 — a **natural-language description** → a *draft*
`IntegrationSpec` — as a deliberately separate, opt-in LLM path
(`coact.nl_ingress.integration_spec_from_description`). Decision and rationale:

- **A separate entry point, not an overload of `integration_spec_from`.** A
  `module:function` ref and an NL description are both `str`; routing them through
  one function would make the mechanical path's behavior depend on an LLM (a clean
  D10 violation, and ambiguous to boot). So `integration_spec_from` stays LLM-free
  and `integration_spec_from_description` is the *named* opt-in LLM path. D10 holds
  structurally: nothing on a mechanical path imports `nl_ingress`, and `oa`/`aix`
  are imported **lazily inside** the entry function (so `import coact` pulls in
  neither; a missing backend is an actionable `ImportError`, not a hard dep).

- **Generation routes through `aix` (provider-agnostic), via `oa`.** Per the
  route-through-aix policy, the default backend is `aix.chat` (multi-provider) —
  *not* oa's OpenAI default — so the multi-target promise stays honest. The
  prompt-as-function machinery is `oa`'s (`prompt_function` for the structured
  extraction; the now backend-injectable `oa.infer_schema_from_verbal_description`
  for per-tool input-schema inference when a tool lacks one). `oa` was the missing
  seam: `infer_schema_from_verbal_description` was hardwired to oa's `chat`; it was
  made backend-injectable upstream (first customer = coact, cross-package policy).
  The backend is injectable (`llm=` accepts a callable / model-name / `None`), so
  the whole path is unit-testable offline with a fake — no provider call.

- **The result is a *draft*; tools grow a richer descriptor (`ToolSpec`).** The
  landscape doc §9.1 always modeled a tool as *(name, description, input schema,
  handler ref)*; the D17 P1 simplification (`tools: list[str]` refs) was a
  code-path shortcut. NL tools have **no importable handler yet**, so the spec gains
  `tool_specs: list[ToolSpec]` (name / description / input_schema / optional
  handler) **alongside** the unchanged `tools` refs (non-breaking — refs still
  compare equal). A `ToolSpec` *with* a handler is *bound* (its ref joins
  `runnable_refs()`); *without*, it is a *proposed* tool — a design draft to bind
  before it can run. `is_empty()` now also counts `tool_specs`.

- **Publishing a draft is honest about runnability (no silent dead bundle).**
  `publish_mcpb` builds the server config from `runnable_refs()` (bare refs +
  bound-ToolSpec handlers). A pure draft (no runnable ref) **raises** with guidance
  rather than writing a `.mcpb` that runs nothing; proposed tools are still listed
  in the manifest for design visibility, with a warning that they will not run
  until bound. This mirrors the D8/D13 "coact writes the design, the user owns the
  code" stance — the draft is a design artifact, not a runnable lie.

- **Authoring prompts: SSOT in coact, injectable, pyrompt as the iteration home.**
  The per-target authoring prompt(s) live in coact (`DFLT_AUTHORING_PROMPTS`, one
  entry per target — extend as targets land) so behavior is committed and
  reproducible with no hard `pyrompt` dependency. `prompt_template=` lets a caller
  inject an alternative (e.g. one *managed/iterated* in `pyrompt`), which is the
  right home for prompt curation without duplicating the SSOT into uncommitted
  machine-state. (A future `pyrompt`-sync helper can register these for management.)

- **Packaging.** `coact/nl_ingress.py`; exports `ToolSpec` +
  `integration_spec_from_description`; optional extra `coact[nl]` (`oa`, `aix`); CLI
  verb `coact describe "<NL>"` (renders the draft); skill updated. Offline tests
  inject a fake backend (no provider call); the `oa` injection has its own upstream
  test + PR.

- **Review hardening (adversarial multi-agent pass, 9 confirmed findings, all
  fixed).** The NL output is *untrusted*, so every extracted field is coerced
  (non-string name/description → `str`; a bare-string `resources`/`prompts` is
  wrapped, not iterated per-char) and the JSON parse tries the whole reply, a fenced
  body, then *each* top-level balanced `{…}` span (brace-bearing prose before the
  JSON no longer defeats it). `integration_spec_from` now carries a spec's
  `tool_specs`/`resources`/`prompts` through the **list** branch (a draft mixed into
  a list previously lost its bound handlers silently). `check_requirements` is
  path-aware (an injected callable needs neither `aix` installed nor a provider
  call — honoring the "offline when injected" contract). The `.mcpb` draft guard
  distinguishes a *design draft* (proposed tools) from a *tools-less* spec
  (resources/prompts only) in its message. The manifest keeps the bound function's
  own name/docstring (what `py2mcp` actually serves — no manifest↔runtime desync); a
  curated ToolSpec description only *fills an empty* one.
