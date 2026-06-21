# AI Assistant Skills — Starter Suite

*Author: Thor Whalen — Last updated: 2026-05-18*

A starter set of Claude Code skills for adding genuinely agentic, multi-provider, lock-in-averse AI assistants to existing React + Python apps. These are the seed for the future `create-ai-assistant-app` package.

## What's in this folder

Five focused skills covering the architectural layers identified in the four prior research reports (Embedding AI Chat / Prompts & Skills SSOT / Command Dispatch → MCP / Agent Orchestration 2026 Survey):

```
ai-assistant-architect/      ← entry point: audit + route to the others
  SKILL.md
ai-assistant-chat-ui/        ← L4–L6 (frontend, wire protocol, FastAPI route)
  SKILL.md
ai-assistant-prompts-skills/ ← L0 (prompt/skill SSOT, PromptStore)
  SKILL.md
ai-assistant-command-mcp/    ← L1 (command dispatch → MCP bridge)
  SKILL.md
ai-assistant-agent-runtime/  ← L2–L3 (agent orchestration + durable execution)
  SKILL.md
```

## How to use

1. **Drop the folders into your Claude Code skills directory** (typically `~/.claude/skills/` or `<repo>/.claude/skills/` for project-scoped skills). The folder name must match the `name` in each `SKILL.md`'s frontmatter.

2. **Point Claude Code at a codebase** that has (or should have) an AI assistant integration. Trigger phrases that fire the architect skill:
   - "Audit the AI assistant integration in this repo"
   - "Add an AI assistant to this app"
   - "What should I add next for the AI assistant?"
   - "Set up the chat UI / prompts / MCP / agent runtime for this app"

3. **The architect skill audits first, then routes.** It identifies which layers exist, which are missing, and invokes the focused skills for the relevant work.

## What each skill does

| Skill | When it fires | Outputs |
|---|---|---|
| `ai-assistant-architect` | Multi-layer task, audit request, or unclear scope | Phased plan, layer-by-layer audit, routing to sub-skills |
| `ai-assistant-chat-ui` | Chat UI, streaming, tool rendering, thread CRUD, branch/regenerate | assistant-ui + AI SDK protocol + FastAPI SSE wire-up |
| `ai-assistant-prompts-skills` | System prompts, user prompts, skills, versioning, registry | Filesystem-first SSOT + `PromptStore` Python class |
| `ai-assistant-command-mcp` | Make commands AI-callable, MCP server, tool annotations, scoping | FastMCP emitter from `@command` registry; multi-surface |
| `ai-assistant-agent-runtime` | Agent loop, durable execution, sub-agents, cancellation, resume | Pydantic AI + DBOS (or LangGraph, or Mastra for TS) |

## Detection of Thor-specific tooling

The skills look for and prefer Thor's existing packages when present:

- **`acture`** / **`wrapex`** / a `@command` decorator → treated as the command dispatch SSOT
- **`py2mcp`** → preferred over hand-rolling FastMCP, where its capabilities cover the annotation taxonomy
- **`PromptStore`** / a `prompts/` directory with frontmatter → recognized as the existing prompts SSOT

If absent, the skills suggest adding the canonical form (with the strangler-fig migration path for existing apps).

## Architectural baseline (cross-skill)

All five skills assume and reinforce this stack:

```
Frontend:    React 19 + Vite + Tailwind + shadcn + assistant-ui
Wire:        AI SDK UI Message Stream Protocol (SSE)
Backend:     FastAPI + Pydantic AI VercelAIAdapter
Agent:       Pydantic AI (Python) or Mastra (TS-only stacks)
Durable:     DBOS (Postgres) — default; Temporal for cross-language
Tools:       FastMCP server emitted from command dispatch registry
Prompts:     Git-versioned SKILL.md files + PromptStore loader
Provider:    Multi-provider via LiteLLM (Py) or AI SDK (TS)
```

Each layer is swappable. Lock-in lives only in the seams (mainly the AI SDK UI Message Stream Protocol on the wire — and that's the most stable choice available).

## Freshness

Every `SKILL.md` carries a `last-updated:` field in its frontmatter, currently `2026-05-18`. The architect skill includes a quarterly freshness checklist covering:

- Anthropic Skills spec stability
- AI SDK UI Message Stream Protocol version
- FastMCP / MCP spec transport changes (SSE deprecated, Streamable HTTP default since spec rev 2026-03-26)
- MCP "Skills Over MCP" working group (SEP-2640)
- Pydantic AI universal Tool Search Tool (issue #3590)

Bump `last-updated:` on any skill you edit. The architect skill's freshness check should grep across all five.

## What's NOT in this starter

Reserved for later skills as the research catches up:

- **Observability + pricing + cost pass-through** (Prompt 4 — pending)
- **Knowledge / RAG / code-as-knowledge** (Prompt 5 — pending)
- **Safety & prompt-injection defense for agentic systems** (Prompt 6 — pending)
- **Multi-tenancy + identity + keys + credit billing** (Prompt 8 — pending)

Each will become its own focused skill following the same pattern.

## Source reports (Thor's project knowledge)

- `Embedding_AI_Chat_into_React_Vite_Apps__A_Lock-In-Averse_Architecture_Guide.md`
- `Production_Patterns_for_Prompts__Skills__and_System_Prompt_Management_in_AI_Applications.md`
- `Command_Dispatch_to_MCP_Bridge.md`
- `Agent_Orchestration_Runtimes_and_Durable_Execution_for_Long-Running_AI_Agents__2026_Survey.md`
- `command_dispatch_journal_article.md`

## License

These skills encode architectural recommendations derived from public OSS documentation and Thor's own working papers. Use, fork, and adapt freely.
