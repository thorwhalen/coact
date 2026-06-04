---
name: coact-complete
description: Use when turning an existing .claude/skills/ skill into a .claude/agents/ agent definition with coact — i.e. COMPLETE. Triggers on "complete a skill into an agent", "make an agent from this skill", "what extras would coact add", "fill in the coact frontmatter block", or wanting a dry-run/provenance preview before generating an agent. Covers complete(), plan_completion(), the additive coact frontmatter, and the no-LLM default.
---

# COMPLETE a skill into an agent definition

A `SKILL.md` is *procedural knowledge injected into the caller's turn*. A subagent
is *a separate worker with its own context, persona, tools, model, and a defined
return value*. **An agent is mostly a skill plus a thin "extras" envelope.**
COMPLETE synthesizes that envelope — mechanically, **no LLM needed**.

The two extras that actually matter:

1. the **persona** (system prompt / identity), and
2. the **return contract** (a JSON Schema so a manager can consume the output).

coact keeps the **skill on disk as the single source of truth** — the agent
*references* the skill by name and never copies its body.

## Look before you leap: plan first

`plan_completion` is a dry-run. It returns the proposed agent **plus per-field
provenance and warnings** — every synthesized field and *where it came from*:

```python
from coact import plan_completion

plan = plan_completion(".claude/skills/ux-analyst")
print(plan.render())     # name←skill, tools←inferred/coact:, model←policy, ...
plan.agent               # the AgentDefinition it would produce
plan.warnings            # e.g. "tools not declared; inferred from ..."
```

```bash
coact plan .claude/skills/ux-analyst      # same dry-run, in the terminal
```

When you're happy:

```python
from coact import complete, emit_agent

agent = complete(".claude/skills/ux-analyst")          # -> AgentDefinition
print(emit_agent(agent, "claude-agents-md"))           # the .md, as text
emit_agent(agent, "claude-agents-md", dest=".claude/agents/")   # write it
```

```bash
coact complete .claude/skills/ux-analyst --dest .claude/agents
```

`source` accepts a `Skill`, a path to a skill dir / `SKILL.md`, or a key/name
resolvable in the local store or `.claude/skills/`.

## Make the lift reproducible: the `coact:` block

The standard `name` / `description` frontmatter doesn't carry tools, model, MCP,
or a return contract. Add an **additive, optional** `coact:` block (every other
tool ignores it). When present it **wins over policy**; when absent coact infers
and *reports what it guessed*.

```yaml
---
name: ux-analyst
description: Analyze a captured UX evidence bundle for usability issues.
coact:
  tools: [Read, Grep, Glob]        # else inferred from the skill (a warning is recorded)
  disallowed_tools: [Bash]         # narrow the allowlist
  model: sonnet                    # sonnet | opus | haiku | inherit  (else policy routes)
  memory: project                  # user | project | local  (opt-in)
  permission_mode: default
  skills: [shared-evidence]        # extra skills the agent references (point-don't-copy)
  consumes: evidence_bundle        # input contract name (signals interdependence)
  returns:
    schema_ref: ov.schemas:UxFindings   # XOR json_schema — resolved to canonical JSON Schema now
    description: Usability findings for the bundle
  mcp:
    - module: ov.analyzers              # python tools, exposed at REALIZE-time (backend='mcp')
      functions: [score_contrast, find_tap_targets]
  persona: |
    You are a meticulous UX analyst...  # else a template persona is synthesized
---
```

Validate it (also runs under `skill validate` once coact is imported):

```python
from coact import validate_coact_block, parse_coact_meta
validate_coact_block(skill_frontmatter_dict)   # [] = valid/absent
parse_coact_meta(".claude/skills/ux-analyst")  # -> CoactMeta
```

## Key behaviors to remember

- **No LLM by default.** The whole path is mechanical. To *draft* a richer
  persona, opt in explicitly: `complete(skill, llm=...)` (a `callable(str)->str`,
  an `aw` `StepConfig`, or a model name). Without `llm=`, nothing calls a model.
- **Defaults are sensible & reported.** Tools/model/memory come from the `coact:`
  block if declared, else from the injected `CompletionPolicy`
  (`from coact import default_policy`) — and provenance tells you which.
- **schema_ref is resolved at completion time** to a canonical JSON Schema; an
  unresolvable ref is recorded as a warning, never a crash.
- **mcp tools are not embedded** in the definition — they're exposed at
  realize-time (`backend="mcp"`); `plan` warns you when a skill declares them.

## Next

- `coact-realize` — turn the completed definition into something that runs.
- `coact-analyze` — `diff` a skill against its agent to audit the extras.
