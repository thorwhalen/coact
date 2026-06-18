---
name: ai-assistant-agent-runtime
description: Use this skill whenever the user wants to add, refactor, or audit the agent runtime — the loop that drives multi-step tool-using LLM conversations, optionally with durable execution for long-running, resumable agents. Triggers include "add an agent loop", "make my agent multi-step", "stop the agent from looping forever", "resume an agent after a crash", "run an agent in the background", "agent handoff to sub-agent", "add Pydantic AI / LangGraph / OpenAI Agents SDK", "wrap my agent in Temporal / DBOS / Inngest / Restate", "stream agent state to the UI", "cancel a running agent", "human-in-the-loop approval mid-run", or any task on the agent orchestration or durable execution layers. Read BEFORE writing a custom agent loop.
last-updated: 2026-05-18
maintained-by: Thor Whalen
freshness-note: Pydantic AI is on weekly release cadence. LangGraph v1.2.0 shipped 2026-05-11; Cloudflare Workflows V2 shipped 2026-04-15; Microsoft Agent Framework 1.0 GA 2026-04-03. Re-verify quarterly.
---

# AI Assistant — Agent Runtime & Durable Execution (Layers 2–3)

The runtime that drives the multi-step tool-using loop, plus the durability layer that makes long agent runs survive crashes, deploys, and human pauses.

## The decision in one sentence

**Pydantic AI (Python, multi-provider, MIT) for L3 orchestration + DBOS (Postgres-only durability, MIT) for L2 — emitting AI SDK UI Message Stream Protocol events to the frontend via Pydantic AI's `VercelAIAdapter`. Streaming, cancellation, and human-pause are first-class. Multi-provider from day one (OpenAI, Anthropic, Gemini, Bedrock, Ollama, ~25 providers).**

For TypeScript-only stacks: **Mastra** (Apache-2.0, TS-only) substitutes for Pydantic AI at L3.

## Audit: what to look for

```bash
# Existing agent framework
grep -rE "from pydantic_ai|from langgraph|from agents|from claude_agent_sdk|from mastra" .
grep -rE "import pydantic_ai|import langgraph|import openai_agents" .

# Custom agent loops (FLAG — almost always wrong)
grep -rE "while.*tool_calls|for.*step in range|recursion|max_steps" backend/

# Durable execution
grep -rE "from dbos|from temporalio|from inngest|from restate_sdk|durable_objects" .

# Wire-protocol adapter
grep -rE "VercelAIAdapter|assistant_stream|ag_ui|RunController" .
```

Audit verdicts:

- **No agent framework + custom while-loop driving tool calls.** REFACTOR. Hand-rolled loops miss step budgets, retries, cancellation, sub-agent isolation, tracing. Pick Pydantic AI.
- **Anthropic SDK direct (no agent framework).** Works for single-shot. For multi-step + tool calls, wrap in Pydantic AI or accept the manual orchestration cost.
- **LangGraph + LangChain.** Fine. Stay. LangGraph v1.2.0 is excellent. Just verify it's usable WITHOUT pulling in LangChain (it is, as of v1.x).
- **OpenAI Agents SDK or Claude Agent SDK.** Provider-locked. Acceptable for prototypes; migrate to Pydantic AI for production unless the lock-in is intentional.
- **Mastra.** TS-only. Stay.
- **Custom durable execution (e.g., your own retry/checkpoint logic).** REFACTOR. Use DBOS or Temporal.
- **Pydantic AI + no durability.** Acceptable until agents exceed ~5 minutes or need to survive deploys. Then add DBOS.

## Why Pydantic AI (and not the others)

| Requirement | Pydantic AI | LangGraph | OpenAI Agents SDK | Claude Agent SDK | Mastra |
|---|---|---|---|---|---|
| Multi-provider | ✅ ~25 | ✅ via LangChain | ⚠️ OpenAI-first | ❌ Claude only | ✅ |
| MIT/Apache | ✅ MIT | ✅ MIT | ✅ MIT | ✅ MIT | ✅ Apache-2.0 |
| Native AI SDK adapter | ✅ `VercelAIAdapter` | via helper | ❌ | ❌ | ✅ |
| Native AG-UI adapter | ✅ | via helper | ❌ | ❌ | ✅ |
| OpenTelemetry GenAI | ✅ (Logfire) | ✅ | ✅ (`agents[otel]`) | ✅ (`[otel]`) | ✅ |
| Temporal/DBOS adapter | ✅ Both, native | ✅ Temporal | ✅ Temporal | manual | manual |
| Language | Python | Python (+JS) | Python + TS | Python + TS | TS only |
| Learning curve | Low | Medium-High | Low-Medium | Low | Low |
| Lock-in | Low | Medium (platform) | Medium-High | Very High | Low |

**Pydantic AI is the strongest Python-first choice for Thor's constraints.** LangGraph is the strongest enterprise alternative. Mastra is the strongest TS-only alternative.

## Minimal agent (Day 1)

```python
# agent.py
from pydantic_ai import Agent
from pydantic_ai.providers import AnthropicProvider, OpenAIProvider

# Provider chosen via env var; LiteLLM-style facade for free
agent = Agent(
    model="anthropic:claude-sonnet-4-5",     # or "openai:gpt-4", or "groq:..." etc.
    system_prompt="You are a helpful assistant for {workspace}.",
    deps_type=AppDeps,                         # typed dependencies for tools
)

@agent.tool
async def search_orders(ctx, customer_id: str) -> list[dict]:
    """Look up recent orders for a customer."""
    return await ctx.deps.db.fetch_orders(customer_id)
```

Connecting to FastAPI + assistant-ui via the AI SDK protocol:

```python
# api/chat.py
from fastapi import FastAPI
from pydantic_ai.ui.vercel_ai import VercelAIAdapter
from agent import agent

app = FastAPI()

@app.post("/api/chat")
async def chat(body: dict):
    adapter = VercelAIAdapter(agent)
    return adapter.fastapi_response(messages=body["messages"], deps=AppDeps(...))
```

That's the full Day-1 wire-up. ~15 lines from FastAPI route to streaming assistant-ui chat with tool calls rendered.

## Adding MCP tools to the agent

Per `ai-assistant-command-mcp`, the FastMCP server is emitted from the command registry. The agent connects to it:

```python
from pydantic_ai.mcp import MCPServerHTTP

# Local: emit FastMCP server in-process and pass it directly
# Remote: point at the Streamable HTTP endpoint
agent = Agent(
    model="anthropic:claude-sonnet-4-5",
    mcp_servers=[MCPServerHTTP(url="http://localhost:8000/mcp")],
)
```

The agent will call `tools/list`, filter by scopes (if OAuth is wired), and route LLM tool calls to MCP. Native — no glue code.

## Adding durable execution (when needed)

### Trigger: when to add durability

Add DBOS (or Temporal) when ANY of:
- Agent runs > 60 seconds (assistant-ui's default streaming timeout)
- Agent must survive backend deploys
- Agent needs human-pause for hours/days
- Agent runs in background outliving the browser session
- Multi-step plans with > 5 LLM calls (so retry doesn't restart from scratch)

### DBOS (recommended default — Postgres-only, no new infra)

```python
from dbos import DBOS
from pydantic_ai import Agent

DBOS()  # initialize, reads from your existing Postgres

@DBOS.workflow()
async def run_agent_workflow(prompt: str, thread_id: str) -> str:
    @DBOS.step(retries=3)
    async def llm_step(messages):
        return await agent.run(messages)
    result = await llm_step(prompt)
    return result.output
```

`@DBOS.step()` checkpoints into Postgres. Crash mid-run → restart → resume from last successful step. Exactly-once via Postgres transactions, not just at-least-once. **Lowest lock-in of any durable platform** — pure library + Postgres.

**Pydantic AI caveat (per docs):** `Agent.run_stream()` is NOT supported inside DBOS workflows. Use `event_stream_handler` on the Agent for streaming inside durability.

### Temporal (when cross-language or established Temporal expertise)

```python
from temporalio import workflow, activity

@activity.defn
async def llm_activity(prompt: str) -> str:
    return (await agent.run(prompt)).output

@workflow.defn
class AgentWorkflow:
    @workflow.run
    async def run(self, prompt: str) -> str:
        return await workflow.execute_activity(llm_activity, prompt, ...)
```

Pydantic AI ships a `TemporalAgent` wrapper since GA March 23, 2026.

### Choose between

- **DBOS** if: Python, Postgres in stack, want zero new infrastructure. Default.
- **Temporal** if: cross-language, cross-region, established Temporal use, very long workflows (days/weeks).
- **Restate** if: you want virtual-object durability with a small footprint. Free tier 50k actions/mo.
- **Inngest** if: TypeScript-first, serverless deployment.
- **Cloudflare Workflows V2 + Durable Objects** if: already on Cloudflare. 50k concurrent instances per account.

## Streaming agent state to the UI

Per the architecture in `ai-assistant-chat-ui`, the wire format is AI SDK UI Message Stream Protocol. The adapter sits between agent events and SSE:

```python
# Option 1: native Pydantic AI VercelAIAdapter (~15 lines of FastAPI)
from pydantic_ai.ui.vercel_ai import VercelAIAdapter

# Option 2: assistant-stream (Python, MIT, by assistant-ui team)
from assistant_stream import RunController, run_in_response
async with RunController() as ctrl:
    await ctrl.append_text("Hello")           # text-delta
    await ctrl.tool_call(...)                  # tool-input-start/delta/available
    await ctrl.tool_result(...)                # tool-output-available
```

`assistant-stream` exposes `ReadOnlyCancellationSignal` — cancellation back-propagates from the UI's "Stop" button to the agent.

## Cancellation, step budgets, infinite-loop detection

Pydantic AI primitives:

- `Agent.usage_limits=UsageLimits(request_limit=20, total_tokens_limit=100_000)` — hard cap on steps and tokens
- `Agent.run(..., usage_limits=...)` — per-run override
- `result.cancel()` for cooperative cancellation
- `model_settings={"timeout": 60.0}` on the underlying LLM call

For runaway-loop detection beyond `request_limit`, observe with OpenTelemetry and alert on `> 95th percentile` step counts per agent type.

## Human-in-the-loop (mid-run pause for approval)

Two patterns:

**Pattern A — Pydantic AI native interrupts.** `@agent.tool` with `Tool(requires_confirmation=True)` raises an `InterruptForApproval` event that the wire protocol surfaces to the UI. UI shows a modal; user approves/rejects; agent resumes with the response. Maps cleanly to MCP's `requires_confirmation` annotation (see `ai-assistant-command-mcp`).

**Pattern B — Durable pause.** Inside a DBOS workflow, `DBOS.recv()` blocks until an external `DBOS.send(workflow_id, payload)` resumes it. Use when approval may take hours/days (outlives browser session). Temporal's `awakeable()` / Restate's `promise()` are equivalents.

## Sub-agents and handoffs

Pydantic AI: each sub-agent is its own `Agent` instance; the parent calls a child via a tool whose handler invokes `child_agent.run()`. Provides clean isolation (separate system prompts, tool subsets, token budgets).

OpenAI Agents SDK has `Handoff` as a first-class primitive; same result. Anthropic Claude Agent SDK has subagents + Skills.

**Anti-pattern**: deeply nested handoffs that share the same conversation. Always pass a typed handoff message between agents, not the raw history.

## Observability (one continuous trace, end to end)

Layer in OpenTelemetry GenAI semantic conventions:

- **L3 (agent):** Pydantic AI emits OTel spans natively. LangGraph via LangChain OTel exporter. OpenAI Agents SDK via `agents[otel]`.
- **L2 (durable):** DBOS emits per workflow/step. Temporal native OTel.
- **L0 (provider):** Anthropic / OpenAI / Bedrock support W3C trace-context propagation.
- **Sink:** Pydantic Logfire (natural for Pydantic AI). Otherwise any OTel collector → Langfuse / Tempo / Jaeger / Honeycomb / Datadog.

Result: one trace ID from React click → SSE event → FastAPI → workflow → activity → LLM HTTP call. Bug reports become tractable.

## Architecture diagram (compact)

```
React (assistant-ui)  ◄── SSE: text/event-stream ──┐
                                                    │
FastAPI route  /api/chat                            │
  └── VercelAIAdapter(agent).fastapi_response(...) ─┘   (Layer 5/4)
        │
        ▼
Pydantic AI Agent                                    (Layer 3)
  ├── tools/* registered as MCP via FastMCP server   (Layer 1)
  └── wrapped in DBOS workflow if durable            (Layer 2)
        │
        ▼
LiteLLM / native provider client                     (Layer 0)
  → Anthropic / OpenAI / Gemini / Bedrock / etc.
```

## Anti-patterns

- **Hand-rolled while-loop driving tool calls.** Almost always missing step budgets, retries, cancellation, or tracing. Use Pydantic AI.
- **Picking LangChain for the agent runtime in a new project.** LangChain is a heavy dependency. LangGraph alone (without LangChain) is fine; Pydantic AI is lighter.
- **Custom retry/checkpoint logic.** Use DBOS or Temporal. Both are tiny additions for what they buy you.
- **Streaming inside DBOS workflows via `Agent.run_stream()`.** Not supported (per docs). Use `event_stream_handler` instead.
- **Mixing wire protocols (AI SDK + AG-UI + LangGraph stream).** Pick one for the SSE surface; if multiple agents on the backend, normalize at the adapter layer.
- **Returning raw conversation history when handing off to a sub-agent.** Pass a typed handoff message.

## Versions known good as of 2026-05-18

- **Pydantic AI** weekly releases; check for `VercelAIAdapter` API stability
- **LangGraph** v1.2.0 (2026-05-11) — Postgres checkpoints, time-travel, HIL interrupts
- **OpenAI Agents SDK** v0.17.x (Sandbox Agents, `needs_approval`, Temporal GA March 23, 2026)
- **Claude Agent SDK** v0.1.80+ — Skills system uses agentskills.io spec; **starting June 15, 2026**, usage draws from separate monthly credit on Claude Pro/Max plans
- **Mastra** v1.0 (Jan 2026), Apache-2.0, ~22k stars, ~300k weekly downloads
- **DBOS** MIT — Postgres-only, library form, optional Conductor SaaS
- **Temporal** Pydantic AI integration GA March 23, 2026
- **Restate** Cloud free tier 50k actions/month (no credit card)
- **Cloudflare Workflows V2** shipped April 15, 2026
- **Microsoft Agent Framework 1.0** GA April 3, 2026 (Semantic Kernel + AutoGen unified)
- **OpenAI Swarm** **DEPRECATED** — succeeded by OpenAI Agents SDK

## Freshness check

- Pydantic AI's `Agent.run_stream()` inside DBOS — currently unsupported; track for native support.
- Pydantic AI issue #3590 (universal deferred tool loading) — when shipped, multi-provider Tool Search Tool equivalence.
- LangGraph cross-process stream — currently in-process only; check release notes.
- Anthropic Claude Agent SDK billing (June 15, 2026 transition to separate credit pool) — affects cost forecasting.
- Mastra's Apache-2.0 vs `ee/` Enterprise License split — verify which directories remain free.

## Related skills

- `ai-assistant-architect` — overall architecture
- `ai-assistant-chat-ui` — the wire protocol the agent emits
- `ai-assistant-command-mcp` — the tool surface the agent consumes
- `ai-assistant-prompts-skills` — the instructions the agent loads

## Source reports (in Thor's project knowledge)

- `Agent_Orchestration_Runtimes_and_Durable_Execution_for_Long-Running_AI_Agents__2026_Survey.md` (primary)
- `Embedding_AI_Chat_into_React_Vite_Apps__A_Lock-In-Averse_Architecture_Guide.md` (wire protocol context)
