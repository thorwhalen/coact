---
name: coact-dev
description: Use when developing, debugging, reviewing, or extending the coact package itself (this repo) — adding emit targets or realize backends, touching COMPLETE/REALIZE, the additive coact frontmatter, the policy, or the LLM/synthesis paths. Covers the architecture, the invariants that must not be broken, the open-closed extension points, and the testing/tooling gotchas specific to this repo.
---

# Developing coact

`coact` ("co-act") owns the two transitions the rest of the agent-stack
ecosystem doesn't:

```
python functions/scripts  →  .claude/skills/  →  .claude/agents/  →  running agents
        (py2mcp, aw)            (skill pkg)        COMPLETE (coact)    REALIZE (coact)
```

- **COMPLETE** — `.claude/skills/<skill>` → an `AgentDefinition` (add the
  agent-only "extras envelope": persona, return contract, tools, model, memory).
- **REALIZE** — an `AgentDefinition` → something that runs (host / sdk / mcp).

It is **glue, not a framework**: it builds on `skill` (data model + registries),
`aw` (the `AgenticStep` runtime + translators), and `py2mcp` (Python→MCP). When a
job belongs to one of those, delegate — don't reimplement.

## Module map

| Module | Responsibility |
|---|---|
| `base.py` | SSOT data model: `AgentDefinition`, `ReturnContract`, `AgentPlan`, `FieldProvenance`, `resolve_schema_ref`. **SDK-independent.** |
| `frontmatter.py` | The additive `coact:` SKILL.md block (`CoactMeta`) + its validator. Reads **raw** frontmatter (see gotcha below). |
| `policy.py` | `CompletionPolicy` — data-driven tool/model/memory routing. No hardcoded magic in callers. |
| `synthesis.py` | `synthesize_persona` / `synthesize_return_contract` — templates by default; LLM only if `llm=` passed. |
| `complete.py` | COMPLETE: `complete()` / `plan_completion()`. Mechanical, no-LLM. Records per-field provenance. |
| `emit.py` | `AgentDefinition` → serializations. Open-closed `emitters` registry (`claude-agents-md`, `sdk-agent-dict`, …). |
| `realize.py` | REALIZE: `realize()` + the open-closed `backends` registry (`host`, `sdk`, `mcp`). The biggest, hairiest module. |
| `llm.py` | Thin LLM facade (`resolve_llm`, `structured`). Provider-agnostic; never imported on a mechanical path. |
| `analysis.py` | `diff` / `estimate` / `inventory` / `back` — tooling to see and move between the layers. |
| `stores.py` | `AgentStore` (a `dol`-style mapping over `.claude/agents/`), `agents_dir`. |
| `util.py` | `check_requirements` and small shared helpers. |
| `__main__.py` | argh CLI — thin wrappers over the same core functions. |

The public facade is `coact/__init__.py` (its `__all__` is the supported API).
Decisions are logged in `misc/docs/DECISIONS.md`; the build brief is
`misc/docs/COACT_SPEC.md`; the reuse rationale is `misc/docs/REUSE.md`.

## Invariants — breaking these is a bug, not a style choice

1. **No LLM on any mechanical path** (DECISIONS D10). COMPLETE, emit, the
   templates — none may call a model. Persona drafting fires **only** when `llm=`
   is *explicitly* passed to `complete()` / `synthesize_persona()`.
   `resolve_llm(None)` may *discover* an ambient provider but synthesis must never
   invoke it implicitly. (An early version made a live API call on the no-LLM
   path — that regression is exactly what this guards against, and this env has an
   `ANTHROPIC_API_KEY`, so a slip would silently bill.)
2. **Point-don't-copy** (D8 / §3.3). An agent *references* its skill by name; a
   skill body is **never** inlined into a persona. The skill on disk stays SSOT.
3. **Lazy SDK import** (D2). `claude_agent_sdk` is imported **inside** functions
   (emit/realize), never at module import. Core stays SDK-free so `import coact`
   works without the `[sdk]` extra. `to_sdk_agent_dict` **introspects** the
   installed SDK dataclass and routes leftover fields to options — don't hardcode
   the SDK's field list.
4. **Return contract = canonical JSON Schema** (D6). The SDK's `output_format`
   must be `{"type": "json_schema", "schema": <schema>}` — a bare schema is
   silently ignored. Resolve `schema_ref` at completion time, or record a warning;
   never crash a mechanical path on an unresolvable ref.
5. **Open-closed registries.** Add an emit target → register into
   `coact.emit.emitters`. Add a realize backend → register into
   `coact.realize.backends`. Add routing → extend `policy` data. **Never** edit a
   dispatch `if/elif` chain in core to add a variant.
6. **Every module needs a top-level docstring** (auto-extracted for docs). ruff
   `D100` enforces this; keep them rich, not stubs.

## Extending — the open-closed way

```python
# A new emit target:
from coact.emit import emitters
@emitters.register("my-target")
def _emit_my_target(ad): ...

# A new realize backend:
from coact.realize import backends
@backends.register("my-backend")
def realize_my_backend(target, **kw): ...
```

`realize(target, backend="my-backend")` and `emit_agent(ad, "my-target")` pick
them up with no core change. Topology (graphs/edges/cycles) is **out of scope**
(D8) — coact emits definitions + tool wiring and stops. Don't add a LangGraph/
CrewAI *realizer* that encodes a graph.

## Testing & tooling gotchas (this repo specifically)

- **pyenv switches Python by directory.** The repo dir uses the `p12` env (where
  coact + the editable ecosystem live). `cd /tmp` switches envs and imports break.
  Run tooling from the repo root.
- **Doctests are NOT collected by `pytest tests/`** (`testpaths = tests`). Run
  them separately and treat them as part of the suite:
  ```bash
  python -m pytest tests/ -q                 # unit tests
  python -m pytest --doctest-modules coact/ -q   # doctests (don't skip these)
  python -m ruff check coact/                # D100 + format
  ```
- **ruff only enforces `D100`** here (`select = ["D100"]`). It will **not** catch
  unused imports or undefined names — the test suite (which imports every module)
  is your real safety net there. Don't rely on ruff for correctness.
- **`skill.SkillMeta` drops the `coact:` key on parse.** Read it from the raw
  frontmatter via `parse_coact_meta()` (which re-reads `skill.source_path`), never
  from `Skill.meta`.
- **The coact validator self-registers two ways** — eager `register_validator()`
  on `import coact` *and* a `skill.validators` entry point. Idempotent by design;
  not a bug.

## Workflow

Branch from `main`, one PR per milestone, merge on green. Reference issues
(`Closes #N`). CI runs Validation on 3.10/3.12 + Windows; the `Publish` step is
gated behind a `[publish]` commit marker (`[tool.wads.ci.publish]`) so routine
merges don't attempt PyPI.

## Related

- `coact-complete` — the consumer view of COMPLETE.
- `coact-realize` — the consumer view of REALIZE and the backends.
- `coact-analyze` — `diff` / `estimate` / `inventory` / `back`.
