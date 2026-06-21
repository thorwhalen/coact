---
name: ai-assistant-prompts-skills
description: Use this skill whenever the user wants to add, refactor, manage, or audit system prompts, user-editable prompts, or "skills" (Anthropic-style) in an AI assistant. Triggers include "set up a prompt registry", "version my system prompts", "add a skill to my assistant", "make prompts editable by non-engineers", "auto-select the right skill", "write a SKILL.md", "integrate Langfuse for prompt management", "add prompt evals to CI", "manage prompt versions", "load context dynamically per request", "store prompts in git", or any task involving the SSOT for instructions an LLM consumes. Read this skill BEFORE creating any prompts/ or skills/ directory or wiring up a prompt store.
last-updated: 2026-05-18
maintained-by: Thor Whalen
freshness-note: Anthropic Skills spec (agentskills.io) released 2025-12-18 is still young and the MCP "Skills Over MCP" SEP-2640 working group may change the loading mechanism. Re-verify quarterly.
---

# AI Assistant — Prompts & Skills SSOT (Layer 0)

The instruction layer: system prompts, user prompts, and skills (Anthropic-style folders with `SKILL.md` and optional `scripts/`, `references/`, `assets/`).

## The decision in one sentence

**Filesystem-first, Anthropic-Skills-spec-compatible, Git-versioned, indexed by SQLite, optionally mirrored to Langfuse for non-engineer editing.** A single Python `PromptStore` exposes the same artifacts to runtime, CI, IDE, MCP, and humans.

## Why this stack

- **Git is the source of truth.** Auditability (blame, PR review, signed commits, branch protection), free rollback, IDE-native editing, concurrent edits via merge — for free. Vendor-hosted registries become parallel systems that drift.
- **Anthropic Skills spec** (released as open standard 2025-12-18, adopted within 48 hours by Microsoft/OpenAI; 32 tools by March 2026 including JetBrains, AWS Kiro, ByteDance TRAE, Mistral). The format is intentionally tiny: a folder with `SKILL.md` (frontmatter: `name` ≤ 64 chars, `description` ≤ 1024 chars), optional bundled scripts/references/assets. Progressive disclosure in 3 levels: metadata → body → bundled file.
- **Prompty-compatible frontmatter** (Microsoft's `.prompty` file format) means the same file runs in VS Code under the Prompty extension. Cheap superset.
- **Langfuse as optional UI** for non-engineers — read-only from UI, write via Git PR. Protected `production` labels prevent unauthorized promotion.

## Audit: what to look for

```bash
# Filesystem signals
find . -name "SKILL.md" -o -name "PROMPT.md" -o -name "*.prompty"  # already on skill-spec
ls prompts/ skills/ instructions/ system_prompts/ 2>/dev/null      # custom directories

# Code signals
grep -r "PromptStore\|load_prompt\|get_prompt" .                   # existing loader
grep -r "langfuse\|promptlayer\|helicone\|mlflow.gateway" .         # hosted registries
grep -r "system_prompt = \"\"\"\|SYSTEM_PROMPT = " .                # hardcoded prompts (FLAG)
```

Audit verdicts:

- **Hardcoded prompts in Python strings.** Migrate: extract to `prompts/<name>/PROMPT.md`, replace string with `store.get("<name>").compile(...)`.
- **Existing `prompts/` dir but no frontmatter / version metadata.** Add YAML frontmatter (`name`, `description`, `metadata.version`, `metadata.labels`) without changing filenames. Backwards-compatible.
- **Langfuse-only (no Git source).** Reverse: dump Langfuse → Git, point Langfuse at the Git repo as cache only.
- **No `description` field on prompt frontmatter.** Required for skill-spec compatibility and for routing. Add now even if used as plain prompts; future you will thank you.

## File layout (the canonical version)

```
prompts/
  README.md
  registry.toml                     # global config (default provider, labels in use, etc.)
  skills/                           # Anthropic-spec-compatible skills (instructions + bundled assets)
    pdf-processing/
      SKILL.md                      # frontmatter + body
      scripts/
        extract.py
      references/
        forms.md
      assets/
        sample.pdf
  prompts/                          # plain text/chat prompts (not skills)
    customer_support/
      PROMPT.md                     # frontmatter + body
      tests.yaml                    # promptfoo-compatible eval set
      examples/
        good_outputs.jsonl
  shared/                           # reusable fragments
    persona.md
    safety_rules.md
.github/workflows/
  prompts.yml                       # promptfoo --changed-only + CODEOWNERS gate
```

## Frontmatter (the canonical superset)

```yaml
---
# Required (skill-spec compatible)
name: customer-support              # ≤ 64 chars, kebab-case
description: |                      # ≤ 1024 chars; this is what auto-routing matches on
  Handle inbound customer queries about refunds, shipping, and complaints.
  Use when the user mentions order issues, returns, delivery, or product complaints.

# Type (our addition; values: prompt | chat-prompt | skill)
type: chat-prompt

# Prompty-compatible model block (so VS Code Prompty extension works)
model:
  id: claude-sonnet-4-5
  parameters:
    temperature: 0.2
    max_tokens: 2000

# Prompty-compatible inputs block
inputs:
  - {name: user_query,    kind: string, required: true}
  - {name: order_history, kind: object, required: false}

# Our metadata (versioning + deploy state)
metadata:
  version: "2.3.1"                  # semver
  owner: support-team
  labels: [production]              # current deploy state
  audience: [human, agent]          # who consumes this

# Anthropic Skill spec experimental field
allowed-tools: [search_orders, read_kb]
---

You are a customer-support agent for {{company_name}}.

When the user mentions {{user_query}}, follow these steps:
...
```

**The `description` field is load-bearing.** It's how auto-routing decides which skill to load. Treat it as the "elevator pitch" of the skill — what it does and the situations it's for. Anthropic recommends specific trigger phrases in the description (e.g., "Use when the user mentions X, Y, or Z").

## The `PromptStore` Python class (canonical access API)

```python
# prompts_lib/store.py
from prompts_lib import PromptStore

store = PromptStore.from_git(repo="git@github.com:org/prompts.git", ref="main")

# By label (default 'production'), explicit version, or label
prompt = store.get("customer-support")                          # latest production
prompt = store.get("customer-support", version="2.3.0")         # pinned version
prompt = store.get("customer-support", label="staging")         # latest staging

text = prompt.compile(user_query="Where is my order?", order_history={...})

# Progressive disclosure helpers (for skill-style use)
manifest = store.manifest(kind="skill")          # all skill metadata, for system-prompt injection
body     = store.load_skill("pdf-processing")    # full SKILL.md body (level 2)
file     = store.read_skill_file("pdf-processing", "scripts/extract.py")  # level 3

# Auto-routing via embedding similarity
matches = store.semantic_search("how do I refund a customer?", k=3)
```

Internally:

- `PromptStore.from_git()` clones (or pulls) the repo, parses all frontmatter via `python-frontmatter`, indexes into SQLite.
- `prompt.compile(**inputs)` runs the body through Jinja2 (or a small custom templater) with the inputs.
- `semantic_search` uses an in-memory FAISS / sqlite-vec index over the `description` field of each prompt/skill.

The same store is the SSOT for:

- **Runtime** (agent loads system prompt via `store.get(...)`).
- **CI** (`prompts lint`, `prompts evals run` — delegates to Promptfoo).
- **IDE** (VS Code Prompty extension reads the same files).
- **Agent** (`store.manifest()` and `store.load_skill()` exposed as MCP tools — see `ai-assistant-command-mcp`).
- **Humans** (`prompts ls`, `prompts show name@label`, PR reviews).

## Stage progression (when to add what)

**Stage 1 (Week 1) — Adopt the format.**
- Make `prompts/` directory in your repo (or repo-of-repos).
- Convert every hardcoded system-prompt string to a `PROMPT.md` / `SKILL.md`.
- Write the ~60-line `PromptStore` (or copy from Thor's `prompts_lib` if present).
- Use `python-frontmatter`, SQLite index, rebuild on `git pull`.

**Threshold to Stage 2:** > 2 non-engineers want to edit, OR > 20 artifacts.

**Stage 2 (Month 1–2) — Add evals and an editing UI.**
- Add **Promptfoo** for CI evals (it speaks Langfuse URIs natively).
- Mirror to **Langfuse Cloud** or self-host as a read-only-from-UI registry.
- Every LLM call records `prompt_name`, `prompt_version`, `prompt_label` (Langfuse handles this).
- Lock `production` label behind GitHub branch protection + CODEOWNERS.

**Threshold to Stage 3:** agent workflows with > 10 procedures, OR packaging executable code alongside instructions.

**Stage 3 (Month 3–6) — Become skill-native.**
- Promote folder-with-scripts/references/assets layout. Now artifacts ARE skills.
- Stand up the MCP server that exposes skills to any MCP host (Claude Code, Cursor, VS Code, Codex CLI). See `ai-assistant-command-mcp`.
- For the Claude API path, upload via `client.beta.skills.upload(zip)` and use through `container.skills`.
- Use Anthropic's `skill-creator` skill to bootstrap new skills with evals.

**Threshold to Stage 4:** > 50 skills OR accuracy degrades when too many are loaded.

**Stage 4 (Month 6+) — Hybrid routing at scale.**
- Embedding-based routing: shortlist top-k skills by description embedding, inject only those metadata blocks.
- Skill-router eval set in Promptfoo to measure routing accuracy.
- Watch MCP "Skills Over MCP" SEP-2640 — replace custom loader with spec-compliant when stable.

## What NOT to do

- **Hosted registry as SSOT.** Vendor migration becomes painful; Git is forever.
- **BAML by default.** Excellent for typed-extraction prompts; adds a build step and a new language. Use for specific high-value prompts, not as the default.
- **Skipping the `description` field.** It's load-bearing for auto-routing AND skill-spec compliance. Even on plain prompts, write one.
- **One giant `system_prompt.txt`.** Decompose into named skills. Compose at runtime via `store.manifest()` + the model's progressive disclosure.
- **Forking the skill format.** Stay strict-superset compatible so Anthropic's `client.beta.skills.upload()` works without translation.

## User-editable prompts (the "user system prompt" pattern)

The user asked specifically about "user system prompts" — prompts editable by the end user of the app.

Pattern: store user-editable prompts in the application DB, NOT in Git. Compose at runtime:

```python
def build_system_prompt(workspace_id: str, user_id: str) -> str:
    parts = [
        store.get("internal-base").compile(),               # from Git (canonical)
        db.get_workspace_prompt(workspace_id) or "",        # from DB (editable)
        db.get_user_prompt(user_id) or "",                  # from DB (editable, per-user)
    ]
    return "\n\n".join(p for p in parts if p)
```

Order matters: internal canonical first (immutable from the user's perspective), then workspace, then user. Last-write-wins on conflicts within the same layer.

The user-editable parts go through the same content moderation gate as user input — they CAN contain prompt injection. Either restrict their tool access ("user-prompt-mode" has a narrower tool set) or pass them through a guard model.

## Skills vs prompts vs MCP tools (the three are complementary)

Anthropic's framing: *"MCP is like having access to the aisles. Skills are like an employee's expertise."*

- **MCP tools** = capabilities (verbs the agent can invoke).
- **Skills** = procedures (how to do a job; may bundle scripts/references; loaded via progressive disclosure).
- **Prompts** = persona + instructions for a specific role/task (loaded as system or user message).

For Thor's apps: a `customer-support` *skill* loaded into context can call `search_orders` *MCP tool* using procedures defined in `SKILL.md`. The two layers compose.

## Versions known good as of 2026-05-18

- Anthropic Skills spec at `agentskills.io` (revision date in spec body)
- `python-frontmatter` ≥ 1.1
- `promptfoo` ≥ 0.x (rapidly evolving)
- Langfuse SDK Python ≥ 2.x; cache TTL default 60s
- Microsoft Prompty (VS Code extension) ≥ recent

## Freshness check

- Anthropic Skills spec — check for breaking changes at agentskills.io.
- MCP "Skills Over MCP" SEP-2640 — if stabilized, the loader pattern in this skill should swap to spec-compliant; deprecate the custom MCP server in `ai-assistant-command-mcp`.
- Anthropic API `/v1/skills` endpoint — verify `client.beta.skills.upload()` is still the upload path.
- Promptfoo's Langfuse/Helicone URI scheme — used in CI; verify still works.

## Related skills

- `ai-assistant-architect` — overall architecture
- `ai-assistant-command-mcp` — exposing skills as MCP tools (`list_skills`, `load_skill`)
- `ai-assistant-agent-runtime` — how the agent loads system prompts at run time

## Source reports (in Thor's project knowledge)

- `Production_Patterns_for_Prompts__Skills__and_System_Prompt_Management_in_AI_Applications.md` (primary)
- `Command_Dispatch_to_MCP_Bridge.md` (Section 10 — annotation taxonomy compatibility)
