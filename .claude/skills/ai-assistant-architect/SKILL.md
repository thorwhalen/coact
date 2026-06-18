---
name: ai-assistant-architect
description: Use this skill whenever the user wants to add, audit, refactor, or maintain an embedded AI assistant (chat + agentic) inside their own application. Triggers include phrases like "add an AI assistant to my app", "wire up a chatbot", "embed Claude/GPT into my UI", "make my app operable by AI", "audit my AI assistant integration", "what should I add next for my AI assistant", or any task that touches multiple of {chat UI, system prompts, skills, MCP tools, agent runtime, command dispatch → MCP, multi-tenancy, observability, billing} together. This is the entry-point skill — it audits the codebase, identifies the layer in question, and routes to the focused sub-skills (ai-assistant-chat-ui, ai-assistant-prompts-skills, ai-assistant-command-mcp, ai-assistant-agent-runtime).
last-updated: 2026-05-18
maintained-by: Thor Whalen
freshness-note: Validate this skill quarterly. Layers move fast — assistant-ui, AI SDK, Pydantic AI, FastMCP, and the Anthropic Skills spec have weekly releases. Check the per-layer skills' last-updated dates.
---

# AI Assistant Architect (Entry Skill)

This is the **entry skill** for adding or maintaining an embedded AI assistant in an application owned by Thor Whalen (or following Thor's conventions). It encodes the architecture from four prior research reports (Embedding AI Chat in React/Vite, Production Patterns for Prompts/Skills, Command Dispatch → MCP Bridge, Agent Orchestration Runtimes 2026 Survey) and routes to focused skills for each layer.

## The architecture (one picture)

```
┌────────────────────────────────────────────────────────────────────┐
│ L6  Browser: React 19 + Vite + Tailwind + shadcn + assistant-ui    │
│     useChatRuntime( AI SDK UI Message Stream Protocol )            │
├────────────────────────────────────────────────────────────────────┤
│ L5  Wire protocol: AI SDK UI Message Stream Protocol (SSE)         │
│     Adapter: Pydantic AI VercelAIAdapter OR assistant-stream       │
├────────────────────────────────────────────────────────────────────┤
│ L4  HTTP / session: FastAPI                                        │
│     POST /threads/{id}/runs ; GET /threads/{id}/runs/{run_id}/stream│
├────────────────────────────────────────────────────────────────────┤
│ L3  Agent runtime: Pydantic AI (multi-provider, MIT)               │
│     Alt: LangGraph; OpenAI Agents SDK; Anthropic Claude Agent SDK  │
├────────────────────────────────────────────────────────────────────┤
│ L2  Durable execution: DBOS (Postgres-only) OR Temporal            │
│     Provides resumability, step budgets, human-pause, retries      │
├────────────────────────────────────────────────────────────────────┤
│ L1  Tool surface: FastMCP server emitted from command-dispatch SSOT│
│     Annotations: side_effect, idempotent, scopes, defer_loading    │
├────────────────────────────────────────────────────────────────────┤
│ L0  Prompts/Skills SSOT: filesystem-first, Anthropic skill spec    │
│     PromptStore (Python), Git-versioned, SQLite-indexed            │
└────────────────────────────────────────────────────────────────────┘
```

Each layer is **swappable** behind a thin facade. Lock-in lives in the *seams*, not the components.

## What to do first: audit

When invoked, **always start with an audit** unless the user has explicitly scoped the task to one layer. The audit is a short scan of the repo to determine which layers exist, which are missing, and which need refactoring.

### Audit checklist

Run this once at the top of any session:

```bash
# Mandatory directories/files to check (use view or bash):
.                                  # README, package.json, pyproject.toml
src/ app/ frontend/ web/           # frontend code
backend/ server/ api/              # backend code
prompts/ skills/                   # SSOT for prompts/skills (L0)
commands/ command_registry/        # command dispatch (L1 source)
mcp/ mcp_server/                   # MCP emitter (L1 surface)
agents/ runtime/                   # agent runtime (L3)
```

For each, record the presence/absence of these signals:

| Layer | Signal of presence | If missing |
|---|---|---|
| L6 chat UI | `@assistant-ui/react`, `@ai-sdk/react`, `@copilotkit/react-core`, or any chat component | Route to **ai-assistant-chat-ui** |
| L5 wire protocol | SSE endpoint emitting `x-vercel-ai-ui-message-stream: v1`, AG-UI events, or a custom JSON event stream | Route to **ai-assistant-chat-ui** |
| L4 HTTP | FastAPI app with `/chat`, `/threads`, `/runs` routes | Route to **ai-assistant-chat-ui** |
| L3 agent runtime | `pydantic-ai`, `langgraph`, `openai-agents`, `claude-agent-sdk`, `mastra`, or a hand-rolled loop | Route to **ai-assistant-agent-runtime** |
| L2 durable execution | `dbos`, `temporalio`, `inngest`, `restate-sdk` | Route to **ai-assistant-agent-runtime** |
| L1 command dispatch (SOURCE) | `@command` decorator, `CommandSpec`, `acture`, `wrapex`, `commands/` registry, or any palette/keyboard-shortcut + handler-registry pattern | If present, route to **ai-assistant-command-mcp** to bridge it. If absent, see "No command dispatch" below |
| L1 MCP emitter | `fastmcp`, `@modelcontextprotocol/sdk`, `py2mcp`, or a `tools/list` server | Route to **ai-assistant-command-mcp** |
| L0 prompts/skills SSOT | `prompts/`, `skills/`, `SKILL.md` files, `PromptStore`, Langfuse client, Promptfoo | Route to **ai-assistant-prompts-skills** |
| Observability | `langfuse`, `langsmith`, `helicone`, OTel GenAI conventions | (Future skill — flag as gap) |
| Multi-tenancy | per-workspace partitioning of threads/skills/keys | (Future skill — flag as gap) |
| Billing/credits | `stripe`, `openmeter`, `lago`, `orb` | (Future skill — flag as gap) |

### Detection: command dispatch family

Look for any of these — they're all the same idea under different names:

- **`@command`-decorated functions** with a `CommandSpec` or similar dataclass that carries `id`, `summary`, `description`, `schema`, and side-effect metadata.
- **`acture`** package (Thor's command dispatch — Python).
- **`wrapex`** package (Thor's wrapping/expression-of-functions — Python).
- **`py2mcp`** package (Thor's Python→MCP generator). If present, **prefer it over hand-rolling a FastMCP server** unless its current capabilities don't cover the annotation taxonomy below.
- **VS-Code-style command registries**: a dict of `{id: handler}` with metadata, even if not formally typed.
- **Frontend command palettes**: `cmdk`, `kbar`, or a `useCommand`/`registerCommand` hook.

If any of these exist, **the command dispatch IS the source of truth for the MCP tool surface**. Do not author tools separately. Route to `ai-assistant-command-mcp`.

## No command dispatch present?

This is the most architecturally consequential branch. Two paths:

**Path A — Add command dispatch first (preferred for apps with > ~10 operations).** This is Thor's strong preference. Justify with: the command dispatch is the SSOT that feeds command palette, keyboard shortcuts, AI tool calling, MCP, tests, macros, telemetry, undo/redo, and extensions. Rule of three applies: if an operation will be triggered from ≥3 surfaces (and AI counts as one), formalize it as a command. The migration strategy is the strangler fig pattern — wrap existing handlers without rewriting them. See the `command_dispatch_journal_article.md` reference for the full case.

**Path B — Skip command dispatch, register tools directly (acceptable for < ~10 operations, or for a quick spike).** Register tools directly with `@mcp.tool` decorators (FastMCP) or AI SDK `tool({...})`. **Annotate them with the same metadata** the command dispatch would carry (side-effect, scopes, idempotent, etc.) — this preserves the migration path to Path A later.

Always default to Path A unless the user objects or the app is genuinely tiny.

## Routing rules (when to invoke a sub-skill)

| Task | Skill |
|---|---|
| Add/refactor chat UI; streaming; tool-call rendering; thread CRUD; markdown rendering | `ai-assistant-chat-ui` |
| Add/refactor system prompts; user-editable prompts; skill files; prompt versioning; auto-skill selection | `ai-assistant-prompts-skills` |
| Add/refactor MCP server; expose commands to AI; tool annotations; per-user tool scoping; multi-provider tool formats | `ai-assistant-command-mcp` |
| Add/refactor agent loop; durable execution; long-running agents; sub-agents/handoffs; resume across sessions | `ai-assistant-agent-runtime` |
| User unsure; multi-layer task; "make my app AI-operable" with no constraints | This skill (architect) — produce a phased plan, then invoke sub-skills in sequence |

## Decision shortcuts (when speed matters)

- **TypeScript-only stack?** Mastra (TS-only agent framework) replaces Pydantic AI as L3; everything else stays the same. assistant-ui at L6 is unchanged.
- **Pure chat, no tools, no agent?** Skip L1–L3. Use AI SDK `useChat` directly against a FastAPI route that calls Anthropic/OpenAI through LiteLLM.
- **Already on Cloudflare Workers?** Workers V2 + Durable Objects at L2; otherwise the stack is unchanged.
- **Single-tenant, single-user pilot?** Skip multi-tenancy concerns; conversation persistence to local SQLite is fine.
- **Claude-only acceptable?** The Anthropic Claude Agent SDK collapses L1+L2+L3 into one with native MCP, Skills, hooks. Highest lock-in, lowest integration cost. Recommend only for prototypes.

## Phased plan (for greenfield "add AI assistant" requests)

Use this as the default plan to propose:

1. **Day 1.** L0 (Pick the prompt directory layout, write first `SKILL.md`) + L6 (assistant-ui shadcn-style install pointed at a stub FastAPI route emitting `text-delta` parts) + L3 minimal (Pydantic AI agent with one provider).
2. **Week 1.** L1 (Pick 5–10 commands in the existing app, decorate them; emit FastMCP server) + L3 (wire those tools into the Pydantic AI agent).
3. **Month 1.** L4 conversation persistence (thread CRUD against Postgres) + L0 expansion (add prompt versioning via Promptfoo evals in CI).
4. **Quarter 1.** L2 (durable execution — DBOS by default) + observability (Langfuse self-host or OTel collector).
5. **Pre-pilot.** Multi-tenancy + billing + safety guardrails (future skills).

State the phase explicitly in any response that proposes new work, so the user can adjust pacing.

## Anti-patterns to flag immediately

- **CopilotKit at the chat-UI layer** unless `useCopilotReadable`/`useCopilotAction` ("agent reads my app state") is the *primary* value. CopilotKit pulls toward AG-UI + CopilotCloud and is the most opinionated of the three majors. Use assistant-ui by default.
- **Authoring MCP tools separately from existing commands.** If command dispatch exists, the duplication will drift.
- **Hosted vendor as SSOT for prompts/skills.** Git is the source of truth. Hosted registry (Langfuse, etc.) is a cache/UI only.
- **Plain `requests`/`fetch` loops calling LLM APIs.** Use a provider abstraction (LiteLLM in Python; AI SDK in TS) from day one so multi-provider is one config change.
- **SSE for MCP transport.** Deprecated in MCP spec 2026-03-26. Use **Streamable HTTP** (or stdio for local subprocesses).
- **Hand-rolling agent loops with infinite recursion guards.** Use Pydantic AI / LangGraph / OpenAI Agents SDK. They handle this. Even prototypes.

## Freshness check

This skill encodes architecture stable as of **May 2026**. Quarterly, verify:

- **Anthropic Skills spec** (agentskills.io) hasn't broken backwards compat
- **AI SDK UI Message Stream Protocol** still v1 or has stable migration path
- **FastMCP** still the Python default; check for protocol-level changes (the SSE→Streamable HTTP move is a recent example)
- **MCP "Skills Over MCP" working group (SEP-2640)** — when it stabilizes, the loader pattern in `ai-assistant-prompts-skills` should swap to spec-compliant
- **Pydantic AI's Tool Search Tool equivalent (issue #3590)** — when it lands, multi-provider deferred-loading becomes uniform

If any of the above has shifted, update the affected sub-skill's `last-updated` and add a migration note to its body.

## Related skills

- `ai-assistant-chat-ui` — L4–L6
- `ai-assistant-prompts-skills` — L0
- `ai-assistant-command-mcp` — L1
- `ai-assistant-agent-runtime` — L2–L3

## References for further reading (in Thor's project knowledge)

- `Embedding_AI_Chat_into_React_Vite_Apps__A_Lock-In-Averse_Architecture_Guide.md`
- `Production_Patterns_for_Prompts__Skills__and_System_Prompt_Management_in_AI_Applications.md`
- `Command_Dispatch_to_MCP_Bridge.md`
- `Agent_Orchestration_Runtimes_and_Durable_Execution_for_Long-Running_AI_Agents__2026_Survey.md`
- `command_dispatch_journal_article.md`
