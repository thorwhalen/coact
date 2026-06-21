---
name: ai-assistant-chat-ui
description: Use this skill whenever the user wants to add, modify, or audit the chat UI / streaming / wire-protocol layer of an embedded AI assistant. Triggers include "build a chat UI", "add streaming responses", "render tool calls in the chat", "add thread CRUD", "show markdown in the assistant", "branch conversations", "make the AI response copyable", "switch from polling to streaming", "embed Claude into my React app", "set up assistant-ui", "use Vercel AI SDK in my app", "expose chat over SSE from FastAPI", or any task on the frontend chat layer of a React + Vite + shadcn application. Read this skill BEFORE writing any new chat component, runtime hook, or SSE endpoint.
last-updated: 2026-05-18
maintained-by: Thor Whalen
freshness-note: assistant-ui ships daily. AI SDK is on weekly release cadence (6.x as of May 2026). Re-verify versions and the SSE protocol header before declaring this skill current.
---

# AI Assistant — Chat UI & Wire Protocol (Layers 4–6)

Frontend chat layer plus the wire protocol that connects it to a Python backend. This skill covers the *chat surface* only. For prompts, MCP tools, and the agent loop, see the sibling skills.

## The decision in one sentence

**Use `assistant-ui` (MIT, shadcn-style) as the UI runtime, configured with `useChatRuntime` speaking the AI SDK UI Message Stream Protocol over SSE, to a FastAPI backend.** Do not use the Vercel AI SDK as a framework — use it as a wire protocol.

## Why this stack (rationale you can cite)

- **assistant-ui** has the lowest lock-in of the three majors (CopilotKit, LobeChat, assistant-ui). Components land in *your* repo via the CLI (shadcn-style); the runtime is one of ~8 swappable implementations; primitives are headless. Lock-in lives only in `useChatRuntime` — replacing it is one import change.
- **AI SDK UI Message Stream Protocol** is the de facto wire-format standard (over 20M monthly downloads of the `ai` package as of May 2026). Two React clients exist (`useChat` and assistant-ui's `react-ai-sdk` runtime). The protocol is SSE with header `x-vercel-ai-ui-message-stream: v1`.
- **FastAPI on the backend** because Thor's Python skill is the leverage. Anything that emits SSE works; `py-ai-datastream` provides helpers, or hand-roll ~40 lines.
- **Do not put CopilotKit in the critical path** unless `useCopilotReadable`/`useCopilotAction` ("agent reads my app state") is the headline feature. It is excellent at that one thing but pulls toward AG-UI + CopilotCloud.

## Audit: what to look for in the current repo

```bash
# Frontend
grep -r "@assistant-ui" package.json    # already on the stack
grep -r "@ai-sdk" package.json          # already on the stack (partially)
grep -r "@copilotkit" package.json      # FLAG — review intent
grep -r "useChat\|useChatRuntime" src/  # existing chat hooks

# Backend
grep -r "ai_data_stream\|text-delta\|x-vercel-ai-ui-message-stream" .  # already speaking the protocol
grep -r "EventSourceResponse\|StreamingResponse" .  # SSE present
```

Audit verdicts:

- **Nothing chat-related present.** Greenfield — follow "Day 1" in the install section.
- **CopilotKit present.** Decide: keep (if agent-reads-state is the value) or migrate to assistant-ui (default).
- **`useChat` from AI SDK directly with custom UI.** Replace UI with assistant-ui Thread; keep the runtime. Two-line change.
- **Hand-rolled chat UI with polling.** Replace with assistant-ui + streaming. Bigger lift but no functionality regression.
- **assistant-ui present, but `react-ai-sdk` runtime version mismatched with React 18.** Pin `@assistant-ui/react-ai-sdk` to `0.10.x`, OR upgrade React to 19. Issue #2490.

## Install (Day 1 — Hello World)

```bash
# Frontend (Vite + React 19 required for assistant-ui ≥ 0.11.x)
npx assistant-ui@latest init           # shadcn-style: copies Thread.tsx, Message.tsx, etc. INTO your src/
pnpm add @assistant-ui/react @assistant-ui/react-ai-sdk ai
```

Minimal `src/App.tsx`:

```tsx
import { AssistantRuntimeProvider, useChatRuntime } from "@assistant-ui/react";
import { Thread } from "./components/assistant-ui/thread";

export default function App() {
  const runtime = useChatRuntime({ api: "http://localhost:8000/api/chat" });
  return (
    <AssistantRuntimeProvider runtime={runtime}>
      <Thread />
    </AssistantRuntimeProvider>
  );
}
```

Minimal FastAPI backend (`api/chat.py`):

```python
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
import asyncio, json

app = FastAPI()

@app.post("/api/chat")
async def chat(body: dict):
    messages = body["messages"]
    async def gen():
        # AI SDK UI Message Stream Protocol — minimal: emit text-delta parts
        # Each part is a JSON line prefixed by its type
        yield 'data: {"type":"start"}\n\n'
        for tok in ["Hello", " ", "world"]:
            payload = json.dumps({"type": "text-delta", "delta": tok})
            yield f"data: {payload}\n\n"
            await asyncio.sleep(0.05)
        yield 'data: {"type":"finish"}\n\n'
    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"x-vercel-ai-ui-message-stream": "v1"},
    )
```

For real responses, replace the `gen()` body with a call into the agent runtime (see `ai-assistant-agent-runtime`).

**Recommended helper:** `pip install py-ai-datastream` — provides typed emitters for `text-delta`, `tool-input-start/delta/available`, `tool-output-available`, `data-*`, `error`, `finish`. Saves ~40 LOC and avoids subtle SSE framing bugs.

## Progressive disclosure path

| Phase | Add | Why |
|---|---|---|
| Day 1 | `useChatRuntime` + `text-delta` parts | Streaming chatbot, ~80 LOC total. |
| Week 1 | `tool-input-*` / `tool-output-available` parts; register tool-name components | Tool calls render automatically in the UI. |
| Month 1 | `useRemoteThreadListRuntime` with REST CRUD on `/threads` | Thread CRUD, rename, delete, branch. |
| Quarter 1 | Streaming `data-*` parts with stable IDs; `@assistant-ui/tool-ui` | Generative UI / artifacts (code editor, doc canvas). |
| Optional | Mount `<CopilotKit>` provider + `useAgUiRuntime` adapter on top | Agent-reads-app-state, if needed. |

## Features the stack gives you for free (with citations to library docs)

- **Markdown** — `@assistant-ui/react-markdown` included by default; `remark-gfm` for tables; opt-in `react-shiki` for syntax highlighting.
- **LaTeX, Mermaid, reasoning ("thinking") blocks** — built-in primitives under `/docs/ui/`.
- **Branching** — automatic. Edit a message → new branch tracked; `BranchPickerPrimitive` renders the picker. No special API for `LocalRuntime`.
- **Edit / regenerate / cancel / resume** — built-in hooks.
- **Multi-thread CRUD** — via `useRemoteThreadListRuntime` (you supply CRUD callbacks).
- **File attachments** — `AttachmentAdapter` interface; `CompositeAttachmentAdapter` + `SimpleImageAttachmentAdapter` is the recipe.
- **Generative UI / tool UI** — render React components keyed by tool name or `data-*` part type. `@assistant-ui/tool-ui` provides the "interactive with receipts" pattern.
- **Markdown / Rich text toggle** — easy: render `<MessagePrimitive.Content>` for rich, or use a copy of the raw markdown in a `<pre>` for "raw" view. Toggle state in a Zustand store.
- **Copy** — `MessagePrimitive.Copy` ships out of the box.

## Conversation CRUD (the user's explicit requirement)

The user wants: all conversations persisted, can be renamed, deleted, "relaunched" (= forked/branched).

Implementation:

```tsx
const runtime = useRemoteThreadListRuntime({
  runtimeHook: useChatRuntime,
  adapter: {
    list: async () => { /* GET /threads */ },
    initialize: async (threadId) => { /* POST /threads */ },
    rename: async (threadId, newTitle) => { /* PATCH /threads/{id} */ },
    archive: async (threadId) => { /* DELETE /threads/{id} */ },
    // "Relaunch" = duplicate up to message N and set as active:
    // Use the BranchPicker / fork-from-message hooks already in assistant-ui.
  },
});
```

Backend: a 30-LOC FastAPI router with `threads` table (id, user_id, title, archived_at) and `messages` table (id, thread_id, role, parts JSONB, created_at). Branches are encoded as a `parent_message_id` on the `messages` table.

## Multi-tenant note

Persist threads keyed by `(workspace_id, user_id, thread_id)`. Filter the `list` and `initialize` callbacks by the authenticated user's workspace. The thread-list runtime is workspace-agnostic — the boundary lives in your FastAPI route handlers.

## Provider-agnostic posture

The frontend NEVER knows which provider the backend is using. The FastAPI route is the seam. Behind it, use **LiteLLM** (Python) for cross-provider routing, OR the **Pydantic AI** agent's provider abstraction. Frontend code never imports an Anthropic/OpenAI SDK.

## Common pitfalls

- **React 18 + `@assistant-ui/react-ai-sdk` ≥ 1.1.0** → `TypeError: render2 is not a function`. Pin to `0.10.x` or upgrade React.
- **Forgetting the `x-vercel-ai-ui-message-stream: v1` response header.** assistant-ui's runtime will reject the stream silently.
- **Sending tool results as text.** They must be `tool-output-available` parts, with the same `toolCallId` as the corresponding `tool-input-available`.
- **Buffering at a reverse proxy.** Nginx default buffers SSE. Set `X-Accel-Buffering: no` response header. Same for Cloudflare with `Cache-Control: no-transform`.
- **Putting CopilotKit at L6 by default.** It is a different mental model (state-bound copilot, not chat). Use only if the assistant primarily *operates the UI*, not *converses with the user*.

## Migration: from CopilotKit to assistant-ui

If the user has CopilotKit and wants out:

1. Keep the AG-UI server on the backend; assistant-ui has `useAgUiRuntime`. No backend changes needed Day 1.
2. Replace `<CopilotChat />` with `<Thread />` (assistant-ui).
3. Migrate `useCopilotReadable`/`useCopilotAction` calls to `useAssistantToolUI` and tool-name components.
4. Drop CopilotCloud if used for thread persistence; switch to `useRemoteThreadListRuntime` against your own backend.

## Anti-pattern: hand-rolling a chat UI

Do not. The set of features in assistant-ui (branching, attachments, generative UI, copy, edit, regenerate, multi-thread, runtime-swappable) is 3+ months of integration work to replicate. The shadcn-style install means the code is yours — so the only failure mode is upstream going away, which is mitigated by having the code in your repo already.

## Versions known good as of 2026-05-18

- `@assistant-ui/react@0.11.x`
- `@assistant-ui/react-ai-sdk@1.1.x`
- `ai@6.0.184`
- `@ai-sdk/react@2.x`
- React 19
- FastAPI ≥ 0.115
- `py-ai-datastream` (community helper)

## Freshness check

- Verify the AI SDK UI Message Stream Protocol header is still `x-vercel-ai-ui-message-stream: v1` (would change with a v2 of the protocol).
- Verify assistant-ui's `useRemoteThreadListRuntime` API (it's evolved). Check `/docs/runtimes/` on assistant-ui's site.
- Check whether `react-ai-sdk@1.1.x` still gates React 19.
- AG-UI now has 16 event types per the canonical spec; if it grows, assistant-ui's `useAgUiRuntime` should auto-handle but verify.

## Related skills

- `ai-assistant-architect` — overall architecture and routing
- `ai-assistant-agent-runtime` — what's behind the FastAPI route (the agent)
- `ai-assistant-command-mcp` — how tool calls in the UI map to MCP tools

## Source reports (in Thor's project knowledge)

- `Embedding_AI_Chat_into_React_Vite_Apps__A_Lock-In-Averse_Architecture_Guide.md` (primary source for this skill)
- `Agent_Orchestration_Runtimes_and_Durable_Execution_for_Long-Running_AI_Agents__2026_Survey.md` (Part 3 of the report covers wire-protocol adapters)
