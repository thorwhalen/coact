---
name: ai-assistant-command-mcp
description: Use this skill whenever the user wants to expose application operations to an AI assistant via tools/function-calling/MCP. Triggers include "make my app operable by AI", "expose my commands to Claude/GPT", "build an MCP server for my app", "bridge command dispatch to MCP", "annotate tools for AI", "add tool approval flow", "scope tools per user", "stop the AI from calling destructive operations without confirmation", "compose multiple MCP servers", "use py2mcp", "use FastMCP", "use the MCP TypeScript SDK", or any task that wires application operations to the agent's tool surface. Look for command dispatch (any of: @command decorator, CommandSpec, acture, wrapex, py2mcp, a registry of typed handlers). If absent, prefer adding one first.
last-updated: 2026-05-18
maintained-by: Thor Whalen
freshness-note: MCP spec is on a regular revision cadence (2025-06-18, 2026-03-26 most recent at writing). Tool Search Tool went GA February 2026. Re-verify transport choice (SSE deprecated → Streamable HTTP) and annotation taxonomy quarterly.
---

# AI Assistant — Command Dispatch → MCP Bridge (Layer 1)

The bridge from application operations (commands) to the agent's tool surface (MCP, multi-provider tool calls, OpenAPI, CLI). The unique value of this layer: **one annotation pass, many surfaces, no drift.**

## The decision in one sentence

**Treat the command dispatch registry as the single source of truth. Emit FastMCP (Python) or `@modelcontextprotocol/sdk` (TS) tool servers from it. Annotate every command with side-effect class, scopes, idempotency, and approval policy. JSON Schema is the universal pivot.**

## Audit: what to look for

```bash
# Existing command dispatch (any variant)
grep -rE "@command\(|class.*CommandSpec|register_command|@app\.tool" .
grep -rE "from acture|from wrapex|import py2mcp" .
ls commands/ command_registry/ src/commands/ 2>/dev/null

# Existing MCP server
grep -rE "from fastmcp|FastMCP\(|@modelcontextprotocol/sdk" .
ls mcp/ mcp_server/ 2>/dev/null

# Frontend command palette (cmdk/kbar) — also signal of command dispatch
grep -rE "cmdk|kbar|useCommand|registerCommand" .

# OpenAPI / FastAPI routes — could be the source if no command registry exists
grep -rE "@app\.(get|post|put|delete)" .
```

Audit verdicts:

- **Command dispatch present + MCP absent.** Build the MCP emitter (Section: Emitter A below). Easiest path.
- **Command dispatch present + MCP present + duplicated definitions.** REFACTOR: drive MCP from the registry; delete the duplicates.
- **No command dispatch + ad-hoc `@mcp.tool` decorators.** Acceptable for ≤ 10 tools. Annotate them with the metadata taxonomy below so migration to a command registry later is mechanical.
- **No command dispatch + > 10 tools or > 1 surface (CLI + MCP, MCP + REST).** Add a command registry. Strangler-fig pattern: wrap existing handlers without rewriting them.
- **`py2mcp` present.** This is Thor's Python→MCP generator. Prefer it where it covers the annotation taxonomy; supplement with FastMCP for anything it doesn't yet handle. Do NOT bypass py2mcp by hand-rolling FastMCP code in parallel — extend py2mcp instead.
- **OpenAPI present (FastAPI app)** but no command registry. Use `FastMCP.from_openapi()` for a prototype, but plan to migrate to a command registry — auto-generated MCP servers from OpenAPI underperform hand-curated ones on complex APIs (FastMCP's own docs caution this).

## The minimum-viable command (canonical form)

```python
# commands/data.py
from pydantic import BaseModel, Field
from typing import Literal
from command_registry.core import command


class ApplyFilterParams(BaseModel):
    """Filter the active dataset by a column condition."""
    column: str = Field(description="Column name to filter on")
    operator: Literal["=", "!=", ">", "<", ">=", "<="]
    value: str | float


@command(
    id="app.data.applyFilter",
    summary="Apply Filter",
    schema=ApplyFilterParams,
    side_effect="additive",          # query | additive | destructive
    idempotent=True,
    open_world=False,
    requires_confirmation=False,
    scopes=("data:read", "data:write"),
    tags=("data",),
    keywords=("filter", "where", "query", "predicate"),
    examples=({"column": "country", "operator": "=", "value": "France"},),
)
def apply_filter(params: ApplyFilterParams) -> dict:
    """Filter the active dataset by a column condition.

    Use when the user wants to narrow visible rows by a single column predicate.
    For multi-column or compound predicates, use applyFilters instead.
    """
    # ... implementation ...
    return {"ok": True, "rowsRemaining": 12_345}
```

The `CommandSpec` carries everything every emitter needs.

## The full annotation taxonomy

| Field | Type | Purpose | Used by |
|---|---|---|---|
| `id` | str (`app.module.verb`) | Stable identifier | every surface |
| `summary` | str | Palette-friendly label | palette, CLI help |
| `description` | str (from docstring) | LLM-facing prose | MCP, AI tools |
| `schema` | Pydantic | Input schema | every surface |
| `side_effect` | `query \| additive \| destructive` | Maps to MCP `readOnlyHint`/`destructiveHint` | MCP, approval UI |
| `idempotent` | bool | Safe to retry | retries, undo |
| `open_world` | bool | Touches external state | safety policies |
| `requires_confirmation` | bool | UI must confirm before call | chat UI, MCP host |
| `can_elicit` | bool | May ask user for mid-flight input | MCP elicitation |
| `scopes` | tuple[str, ...] | OAuth scopes required | `tools/list` filter + handler check |
| `tags` | tuple[str, ...] | Domain grouping | palette categories, namespacing |
| `surfaces` | tuple[`palette` \| `cli` \| `mcp` \| `openapi`, ...] | Which emitters expose this | each emitter |
| `keywords` | tuple[str, ...] | Tool-search synonyms | Anthropic Tool Search Tool |
| `examples` | tuple[dict, ...] | Few-shot for the model | LLM tool description |
| `defer_loading` | bool | Hide from initial context | Tool Search Tool |

This taxonomy is intentionally compatible with the **Anthropic Skills frontmatter** (see `ai-assistant-prompts-skills`). A command with `surfaces=("mcp", "palette")` and a frontmatter-bearing `COMMAND.md` doc file is one git-tracked artifact serving every surface.

## Emitter A: MCP server (FastMCP)

```python
# emitters/mcp_emitter.py
from fastmcp import FastMCP
from mcp.types import ToolAnnotations
from command_registry.core import registry


def build_mcp_server(name: str = "AppMCP") -> FastMCP:
    mcp = FastMCP(name)
    for spec in registry().values():
        if "mcp" not in spec.surfaces:
            continue
        annotations = ToolAnnotations(
            title=spec.summary,
            readOnlyHint=(spec.side_effect == "query"),
            destructiveHint=(spec.side_effect == "destructive"),
            idempotentHint=spec.idempotent,
            openWorldHint=spec.open_world,
        )
        @mcp.tool(
            name=spec.id,
            description=spec.description,
            annotations=annotations,
            meta={
                "x-side-effect": spec.side_effect,
                "x-requires-confirmation": spec.requires_confirmation,
                "x-can-elicit": spec.can_elicit,
                "x-scopes": list(spec.scopes),
                "x-tags": list(spec.tags),
                "x-keywords": list(spec.keywords),
                "x-examples": list(spec.examples),
            },
        )
        def _tool(params: spec.schema, _spec=spec):
            return _spec.handler(params)
    return mcp


if __name__ == "__main__":
    import commands.data  # triggers registration
    build_mcp_server().run(transport="streamable-http", host="0.0.0.0", port=8000)
```

**Transport choice (2026):** `streamable-http` for production. SSE was deprecated in MCP spec revision 2026-03-26. `stdio` only for local subprocesses.

## Emitter B: Zod schemas for the frontend (Pydantic → JSON Schema → Zod)

```python
# emitters/json_schema_emitter.py
import json
from command_registry.core import registry

def emit_json_schemas(output_path: str) -> None:
    bundle = {
        spec.id: {
            "title": spec.summary,
            "description": spec.description,
            "inputSchema": spec.schema.model_json_schema(),
            "x-side-effect": spec.side_effect,
            "x-idempotent": spec.idempotent,
            "x-requires-confirmation": spec.requires_confirmation,
            "x-scopes": list(spec.scopes),
            "x-tags": list(spec.tags),
            "x-keywords": list(spec.keywords),
        }
        for spec in registry().values()
        if "palette" in spec.surfaces or "mcp" in spec.surfaces
    }
    with open(output_path, "w") as f:
        json.dump(bundle, f, indent=2)
```

Frontend build step (in `package.json`):
```json
"build:schemas": "json-schema-to-zod -i ../schemas/commands.json -o src/commands.gen.ts"
```

## Emitter C: CLI (argh / Click)

Follow Thor's `python-package-architecture` skill conventions. The dispatch table is `{spec.id: spec.handler}`.

## Emitter D: OpenAPI (FastAPI)

Mount each command as a route. `FastMCP.from_fastapi()` can then re-emit an MCP server from the OpenAPI doc — useful if you want both surfaces from one source.

## Emitter E: Multi-provider tool catalogues

```python
def to_openai_tool(spec):
    return {"type": "function", "function": {
        "name": spec.id,
        "description": spec.description,
        "parameters": spec.schema.model_json_schema(),
    }}

def to_anthropic_tool(spec):
    return {
        "name": spec.id,
        "description": spec.description,
        "input_schema": spec.schema.model_json_schema(),
    }

def to_gemini_tool(spec):
    return {
        "name": spec.id,
        "description": spec.description,
        "parameters": spec.schema.model_json_schema(),
    }
```

Or hand the JSON Schema to **LiteLLM** (Python) / **AI SDK** (TS) and let them do the envelope translation.

## Per-user permission scoping (TWO-LAYER enforcement)

Always enforce both:

1. **Filter `tools/list` by the authenticated user's JWT scopes:**

```python
# emitters/scope_middleware.py
from fastmcp.server.middleware import ListToolsMiddleware

class ScopeFilteringMiddleware(ListToolsMiddleware):
    async def on_list_tools(self, context, tools):
        user_scopes = set(context.auth_info.scopes)
        return [t for t in tools if set(t.meta.get("x-scopes", ())).issubset(user_scopes)]
```

2. **Re-check scopes inside each tool handler** so direct calls bypassing `tools/list` are still rejected. This is the Atlassian MCP Server pattern — inherit permissions from the underlying product rather than granting any of its own.

## Multi-server composition (namespacing to avoid collisions)

Three patterns:

- **Compose in the server.** `FastMCP.mount()` attaches a server prefix (`weather_get_forecast`).
- **Compose in the client.** mcp-use's `MCPClient.from_config_file()` + `MCPAgent(use_server_manager=True)` routes per step.
- **Gateway.** Stacklok MCP Optimizer / MCP Manager / Apigene / Higress between many clients and many servers — multi-tenant production pattern.

For a single-codebase SSOT, mounting is the default. Each domain (`commands/data/`, `commands/files/`, `commands/admin/`) gets its own sub-server.

## Tool Search Tool (large catalogues)

Beyond ~50 tools, context overflow degrades selection accuracy. Anthropic's Tool Search Tool (GA Feb 2026):

- Mark long-tail commands with `defer_loading=True`.
- Keep frequently-used commands `defer_loading=False`.
- Anthropic's benchmarks: ~85% reduction in tool-definition tokens; Opus 4 from 49% → 74% MCP-eval accuracy.
- Real cap: ~60% retrieval accuracy on 4000+ tools (third-party Arcade.dev test). Don't over-defer.

For non-Anthropic providers, Pydantic AI issue #3590 tracks universal deferred loading; mcp-use's Server Manager is the client-side equivalent today.

## Approval flows (human-in-the-loop)

Three escalation levels mapped to `side_effect`:

| side_effect | Default UX |
|---|---|
| `query` | Auto-execute, no prompt |
| `additive` | Auto-execute, log; "Undo" button |
| `destructive` | **Always confirm** (chat UI shows a modal with the parsed params + outcome preview) |

`requires_confirmation=True` overrides the default. Cloudflare Agents and Mastra both have first-class approval patterns to reference.

## OAuth (when MCP server is remote)

For Streamable HTTP transports: **OAuth 2.1 + PKCE + Protected Resource Metadata (RFC 9728)**. Scopes from the JWT drive the `tools/list` filter. Use a gateway (Stacklok MCP Optimizer, Apigene) for multi-tenant production.

## Anti-patterns

- **Authoring MCP tools and command-palette entries separately.** They are the same idea. Pick the registry as SSOT.
- **Skipping `description` quality.** Tool descriptions are the rate-limiting factor for agent reliability. Write them like API docs for an intern.
- **Using `passthrough()` Zod schemas on the TS side.** They let extra fields slip through validation. Use `mcp-types` (community fork without passthrough).
- **Authoring per-provider tool definitions by hand.** JSON Schema → LiteLLM/AI SDK normalization is one line.
- **MCP at the chat-UI layer.** MCP is a tool/resource protocol, not a UI streaming protocol. Use AI SDK UI Message Stream Protocol (see `ai-assistant-chat-ui`) on the wire; MCP behind FastAPI for tools.

## Tool description style (the lint)

A tool description should answer:

1. **What does it do?** (one sentence)
2. **When should the agent reach for it?** (situations / triggers)
3. **When should it NOT?** (disambiguation from similar tools)
4. **What does the output look like?** (so the agent can plan downstream calls)

Lint rule (CI): every command's docstring is ≥ 3 sentences, contains the word "use when" or "Use this when", and references at least one related command if any exist with similar `tags`.

## Versions known good as of 2026-05-18

- **FastMCP** 3.x (2.x folded into official Python SDK; 3.x adds `AggregateProvider`, `Transform`)
- **MCP Python SDK** matching spec rev 2026-03-26
- **`@modelcontextprotocol/sdk`** (TS) with Standard Schema support
- **MCP spec rev 2026-03-26** — SSE deprecated, Streamable HTTP default
- **Tool Search Tool** — GA Feb 2026, beta header `advanced-tool-use-2025-11-20` no longer required for GA
- **OAuth 2.1 + PKCE + RFC 9728** for remote MCP

## Freshness check

- MCP spec revision — check for new annotation vocabulary (the working SEPs on `reads_private_data`, `sees_untrusted_content`, `can_exfiltrate` could land).
- SEP-1382 (description-vs-schema convention) — if it graduates to normative, update the description style lint above.
- Pydantic AI #3590 (universal deferred loading) — when shipped, remove the Anthropic-only caveat on Tool Search Tool.
- `py2mcp` capabilities — if it grows to cover the full annotation taxonomy, deprecate the FastMCP emitter in this skill in favor of py2mcp.

## Related skills

- `ai-assistant-architect` — overall architecture
- `ai-assistant-prompts-skills` — frontmatter taxonomy is compatible; the same git repo holds commands + skills + prompts
- `ai-assistant-agent-runtime` — how the agent calls these tools

## Source reports (in Thor's project knowledge)

- `Command_Dispatch_to_MCP_Bridge.md` (primary)
- `command_dispatch_journal_article.md` (philosophical foundation — rule of three, strangler fig migration)
