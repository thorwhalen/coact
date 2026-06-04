# coact examples

A concrete, runnable walk through the two transitions coact owns — **COMPLETE**
(`skill → agent definition`) and **REALIZE** (`definition → running agent`).

```bash
python examples/walkthrough.py
```

Runs with **core coact only** — no LLM, no API call. (The optional `sdk` step is
guarded, so it prints a note instead of failing if `coact[sdk]` isn't installed.)

## What's here

| path | what it is |
|---|---|
| [`skills/ux-analyst/SKILL.md`](skills/ux-analyst/SKILL.md) | a real, self-contained skill carrying a `coact:` block (tool allowlist, model, memory, an **inline** return-contract schema, and a pinned persona) |
| [`walkthrough.py`](walkthrough.py) | the end-to-end script below |

## The walk

The script takes `skills/ux-analyst` through six stages, printing each:

1. **`plan_completion`** — a dry run. Prints every field of the proposed agent and
   *where it came from* (`skill`, `coact-frontmatter`, `policy`, `inferred`, …), so
   you can look before you leap.
2. **`complete`** — the mechanical lift, `Skill → AgentDefinition` (no LLM). The
   `coact:` block wins over policy; absent it, coact infers and reports.
3. **`emit_agent(..., "claude-agents-md")`** — the canonical `.claude/agents/*.md`
   serialization, then a **round-trip** back via `from_claude_agent_md` to show the
   name and return contract survive.
4. **`realize(backend="host")`** — the cheap default: materialize the agent `.md`
   into `.claude/agents/` and symlink the referenced skill into the sibling
   `.claude/skills/`, so the host agent (Claude Code) discovers and runs it.
5. **`realize(backend="sdk")`** *(optional)* — build an `aw.AgenticStep`-compatible
   `RunnableAgent`. The build is offline; it shows the return contract resolving to
   a realization mode (`output_format` on a modern SDK, else the forced
   `return_result` tool — see DECISIONS **D6**). It never makes an API call here.
6. **`estimate` + `inventory`** — the fan-out cost gate (one agent ≈ 4× a chat, a
   fleet ≈ 15×) and an inventory of skills / agents / MCP tools discovered.

## Make it your own

- Drop the `coact:` block from the SKILL.md and re-run `plan_completion`: watch the
  provenance flip from `coact-frontmatter` to `policy`/`inferred` as coact fills the
  gaps and tells you what it guessed.
- Swap the inline `returns.json_schema` for `returns.schema_ref: yourmod:YourModel`
  (a Pydantic model / dataclass / TypedDict) to resolve the contract from code.
- To actually *run* the sdk agent, install `coact[sdk]` and call
  `runnable.execute(task, context)` — it returns `(artifact, info)`.
