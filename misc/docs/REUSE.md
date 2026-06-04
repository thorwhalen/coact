# REUSE.md — what `coact` reuses, extends, or leaves alone

> Output of COACT_SPEC §1 (the reuse audit). This is the boundary contract:
> the symbols `coact` imports, and the functionality it deliberately does
> **not** build because it already exists in `skill`, `aw`, or `py2mcp`.

`coact` is *glue and lift*, not a new framework. It owns exactly two transitions
the other packages don't — **COMPLETE** (`.claude/skills/` → `.claude/agents/`
definitions) and **REALIZE** (agent definition → running agent). Everything
under those two arcs is delegated.

---

## `skill` — the foundation

`coact` builds directly on `skill`'s data model and its registry/plugin
architecture. **Reused symbols:**

| Symbol | Module | How `coact` uses it |
|---|---|---|
| `Registry` | `skill.registry` | The plugin registry pattern (entry-point discovery under `coact.<name>` group). `coact`'s emitter / realization-backend / policy registries are `Registry` instances. **Not reimplemented.** |
| `Skill`, `SkillMeta`, `SkillInfo` | `skill.base` | Reading a skill (frontmatter + body + resource manifest). `coact.complete` ingests a `Skill`. |
| `parse_frontmatter`, `render_frontmatter`, `parse_skill_md` | `skill.base` | Frontmatter (de)serialization for both SKILL.md and the `coact:` block. **Not reimplemented.** |
| `LocalSkillStore` | `skill.stores` | `MutableMapping[str, Skill]` facade. `coact.stores.AgentStore` mirrors its shape for `.claude/agents/`. |
| `validators` (Registry) | `skill.create` | `coact` **registers** a `coact_frontmatter` validator here (additive), rather than building a parallel validation path. |
| `link_skills`, `install`, `AgentTarget`, `agent_targets` | `skill.install` | The `host` realization backend calls `link_skills` to symlink a project's skills into the host target. `AgentTarget` is the model `coact`'s agents-target mirrors. SSOT/"point-don't-copy" philosophy extended to agents. |
| `ParsedKey`, `find_project_root`, `atomic_write` | `skill.util` | Key normalization, project-root detection, safe writes. |
| `chat`, `is_ai_available` | `skill.ai` | Provider-agnostic LLM facade (aisuite→anthropic→openai, lazy, degrades gracefully). `coact.llm` wraps this as one option for the *optional* persona-synthesis path. |
| `load_config`, `data_dir`, `skills_dir` | `skill.config` | platformdirs-based config; `coact.config` mirrors the pattern for policy defaults. |
| argh `dispatch_commands` + `cli_format` pattern | `skill.__main__` | `coact.__main__` mirrors the dispatch-to-interface CLI shape so the two packages feel like one toolkit. |

**`coact` does NOT build:** a skill parser, a skills store, a plugin-registry
mechanism, a validation framework, a config system, a cross-agent installer,
or shell-completion machinery. All of that is `skill`.

## `aw` — the runtime substrate

When `coact` produces a *runnable in-process agent* (the `sdk` backend), it
plugs into `aw`'s protocols instead of inventing an agent loop.

| Symbol | Module | How `coact` uses it |
|---|---|---|
| `AgenticStep` (Protocol) | `aw.base` | The `sdk` backend's `RunnableAgent` **satisfies** `execute(input_data, context) -> (artifact, info_dict)` so `coact`-realized agents drop straight into `aw` workflows. |
| `StepConfig`, `GlobalConfig` | `aw.base` | DI'd LLM + cascading defaults. `coact.policy` reuses the `GlobalConfig.override(**) -> StepConfig` cascade pattern rather than a new config system. `StepConfig.resolve_llm()` powers the sdk backend's optional LLM. |
| `Context` | `aw.base` | `MutableMapping` shared state passed to `RunnableAgent.execute`. |
| `AgentSpec`, `ToolSpec`, `ValidatorSpec` | `aw.translators` | The existing *aw-agent → skill/crewai/openai* IR. `coact` provides an **adapter** `AgentDefinition ↔ aw.AgentSpec` so `aw`'s CrewAI/OpenAI renderers become *free* `coact` emit targets. (See ecosystem enhancement below.) |
| `AgenticWorkflow`, `InteractiveWorkflow` | `aw.orchestration` | Referenced by the *scaffolded* multi-agent shim `coact` may emit (a starter the user owns — `coact` is **not** a topology engine). |

**`coact` does NOT build:** an agent execution loop, retry/validation
machinery, an LLM-injection config, or a workflow-chaining engine. All of that
is `aw`. `coact`'s `sdk` backend is a thin Agent-SDK-backed object that *speaks*
`AgenticStep`.

**Note on direction:** `aw.translators` goes *aw-agent (live Python object) →
SKILL.md*. `coact` goes *SKILL.md (on disk) → Claude agent definition → running
agent*. They are complementary, not duplicative — `aw` introspects a class;
`coact` lifts a file. The shared seam is the capability core (name / prompt /
model / tools / structured-output), which both represent.

## `py2mcp` — the tool-exposure backend

| Symbol | Module | How `coact` uses it |
|---|---|---|
| `mk_mcp_server(funcs, *, name, input_trans)` | `py2mcp` | The `mcp` realization backend turns a skill's declared Python tools (`coact: mcp:` frontmatter) into a FastMCP server. `coact` does **not** write MCP plumbing. |
| `mk_mcp_from_store(store, ...)` | `py2mcp` | Exposing a `MutableMapping` (e.g. an `AgentStore` or skills store) as CRUD-over-MCP for foreign hosts. |
| `mk_input_trans` | `py2mcp` | Input shaping when a tool's MCP signature needs adapting. |

**`coact` does NOT build:** any FastMCP server code. The `mcp` backend is a
call into `py2mcp` plus reference-resolution glue.

---

## Ecosystem enhancements `coact` motivates (cross-repo, non-breaking)

The user explicitly invited enhancing the upstream packages to make `coact`
cleaner. These are additive and preserve each package's public API:

1. **`aw.translators`: split extraction from rendering.** Today
   `to_crewai_yaml(agent)` / `to_openai_tools(agent)` / `to_claude_skill(agent)`
   each call `extract_agent_spec(agent)` internally, so the renderers can only
   be driven by a *live aw agent*. Add `*_from_spec(spec: AgentSpec, ...)` cores
   and make the existing functions thin wrappers. This lets `coact` build an
   `AgentSpec` from its `AgentDefinition` and reuse `aw`'s CrewAI/OpenAI
   renderers directly. (Tracked as an `aw` issue/PR.)
2. **`py2mcp`: reference-resolution helper.** Add `mk_mcp_from_refs([
   'module:function', ...])` (and a small public `import_object`) so building a
   server from config strings — exactly what `coact: mcp:` declares — is a one
   call instead of bespoke `importlib` in every consumer. (Tracked as a
   `py2mcp` issue/PR.)
3. **`skill`: no change required.** `coact` registers its validator into
   `skill.create.validators` from the `coact` side (and via a `skill.validators`
   entry point), and reaches the install/link machinery through the existing
   public API. If a genuine "resolve skill by name across project+global" need
   surfaces during REALIZE, it will be added to `skill` rather than `coact`.

---

## One-line summary

`coact` imports `skill`'s registry+data model, plugs into `aw`'s `AgenticStep`,
and calls `py2mcp` for MCP. It writes only the two missing transforms
(COMPLETE, REALIZE) and the small analysis tooling around them.
