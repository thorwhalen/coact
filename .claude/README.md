# `.claude/` — agent toolkit for the coact repo

This directory configures AI coding agents (Claude Code et al.) working in this
repo. It is fittingly meta: `coact` is the package that turns skills into agents,
and here it grows its own.

## Skills (`.claude/skills/`)

Procedural knowledge injected into an agent's turn when a task matches the
skill's `description` trigger.

| Skill | Audience | Use it when… |
|---|---|---|
| [`coact`](skills/coact/SKILL.md) | consumers (**start here**) | unsure which capability you need — a thin overview that routes to the three below |
| [`coact-dev`](skills/coact-dev/SKILL.md) | **developers of coact** | working on this package — architecture, invariants, open-closed extension points, testing/tooling gotchas |
| [`coact-complete`](skills/coact-complete/SKILL.md) | consumers | turning a `.claude/skills/` skill into an agent definition (COMPLETE) |
| [`coact-realize`](skills/coact-realize/SKILL.md) | consumers | turning a definition into something that runs (REALIZE: host/sdk/mcp/litellm), preview with `--dry-run`, or `scaffold` a starter fleet |
| [`coact-analyze`](skills/coact-analyze/SKILL.md) | consumers | `diff` / `estimate` / `inventory` / `back` — see and move between the layers |

## Agents (`.claude/agents/`)

Subagent definitions the host can dispatch as separate workers with their own
context and a defined job.

| Agent | Use it when… |
|---|---|
| [`coact-reviewer`](agents/coact-reviewer.md) | reviewing a change/PR to coact against its invariants before it lands |
| [`coact-docs-checker`](agents/coact-docs-checker.md) | checking that README / docstrings / DECISIONS still match the code |

## Dogfooding

coact consumes `.claude/skills/` and produces `.claude/agents/`, so this repo is
its own first end-to-end example:

```bash
coact inventory .                                   # lists these skills + agents
coact plan .claude/skills/coact-analyze             # dry-run: skill → agent, with provenance
coact complete .claude/skills/coact-analyze --dest /tmp/agents   # actually produce one
```

`.claude/handoffs/` and `.claude/scratch/` are gitignored (session-local).
