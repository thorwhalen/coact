---
name: coact-publish
description: >-
  Publish a Python capability as a deployable AI-chatbot integration with coact —
  package tools (module:function refs, live functions, or a skill's coact: mcp
  block) into a Claude Desktop one-click .mcpb extension (a local stdio MCP
  server). Use when the user wants to create, build, package, or deploy a Claude
  connector / plugin / MCP server / .mcpb / Desktop Extension / "integration"
  from existing Python code or a skill — e.g. "make an mcpb", "package these
  functions for Claude", "turn this into a Claude extension/connector", "publish
  a local MCP server", "wrap my tools as a Claude Desktop extension". Also use to
  draft an integration from a natural-language description ("describe an
  integration", "I want a Claude connector that can…") via `coact describe`. Also
  covers REMOTE claude.ai connectors (a hosted Streamable-HTTP MCP server + OAuth
  2.1) via the `claude-remote-connector` target — use when the user wants a
  cloud-reachable connector, not a local install.
metadata:
  version: 0.3.0
---

# coact publish — Python capability → Claude integration

`coact publish` ships a capability to a chatbot host. Today it has one target,
`claude-local-mcpb`: a **Claude Desktop `.mcpb` Desktop Extension** that runs a
**local stdio MCP server**. The MCP server itself is built by `py2mcp`; coact
writes the packaging.

## When to use

- The user has **Python functions** (or a skill carrying a `coact: mcp:` block)
  and wants them usable inside Claude as tools.
- They ask to "make / build / package / deploy" a Claude **connector**,
  **plugin**, **extension**, **`.mcpb`**, or **MCP server** from local code.

## How

Always preview first (writes nothing):

```bash
coact publish my.package.module:my_func another.module:other_func --dry-run
```

Then build the bundle:

```bash
coact publish my.package.module:my_func --name my-tools --dest ~/Downloads
# → ~/Downloads/my-tools.mcpb
```

Sources accepted (mix freely): `module:function` refs, a skill directory /
`SKILL.md` (its `coact: mcp:` block supplies the refs), or — from Python — live
callables and a prebuilt `IntegrationSpec`.

## From a natural-language description (opt-in LLM)

To go from an English description to a *draft* integration (proposed tools with
inferred input schemas), use `coact describe` — the **only** LLM-using path here
(the `module:function` → `.mcpb` path stays LLM-free). Generation routes through
`aix` (multi-provider) by default; `--llm` picks a model.

```bash
coact describe "a connector that looks up the weather for a city and converts currencies"
# → renders a draft IntegrationSpec: proposed tools, each marked "proposed (no handler)"
```

```python
from coact import integration_spec_from_description, publish

spec = integration_spec_from_description(
    "expose os.path.basename and os.path.dirname as tools", name="paths"
)
# tools the description bound to existing code become runnable refs:
publish(spec, name="paths", dest="dist")   # works iff spec.runnable_refs()
```

The draft is a **design artifact**: tools are *proposed* (no importable handler)
unless the description named existing code. **Bind** each proposed tool to a real
`module:function` handler (write the code, or point at existing functions) before
`publish` can build a runnable `.mcpb` — coact writes the design, you own the
code. Needs `coact[nl]` (`oa`, `aix`), imported lazily only on this path.

Python API:

```python
from coact import publish, integration_spec_from

publish(["mypkg.tools:summarize", "mypkg.tools:translate"],
        name="text-tools", dest="dist", author="Me")
```

Install the result: Claude Desktop → Settings → Extensions → Install Extension…
(or double-click the `.mcpb`). The extension runs **on the user's machine** and
needs a Python with `py2mcp` + `fastmcp` importable.

## Remote claude.ai connector (Streamable-HTTP + OAuth 2.1)

A claude.ai **custom connector** is a *remote* MCP server reached from Anthropic's
cloud over HTTPS + OAuth — a different surface from the local `.mcpb`. Scaffold one
(a hosted service you deploy) with the `claude-remote-connector` target:

```bash
coact publish mypkg.tools:summarize --target claude-remote-connector \
  --name my-conn --dest ./out \
  --connector-url https://my-conn.example.com --idp-issuer https://my-idp.example.com
# → ./out/my-conn-connector/  (server/app.py, connector_config.json, requirements.txt,
#                              DEPLOY.md, Dockerfile)
```

```python
from coact import publish_remote
publish_remote(["mypkg.tools:summarize"], name="my-conn", dest="out",
               connector_url="https://my-conn.example.com",
               idp_issuer="https://my-idp.example.com",
               required_scopes=["mcp:read"])
```

It scaffolds an OAuth 2.1 **resource server** (validates a managed IdP's JWTs via
`py2mcp.http.mk_http_app`; never issues tokens; audience-bound per RFC 8707). Omit
`--connector-url`/`--idp-issuer` to scaffold with **fill-in placeholders + a loud
warning**. Then follow the generated `DEPLOY.md`: set your IdP, run behind TLS
(`uvicorn server.app:app`), and add the HTTPS URL as a custom connector in claude.ai.
Needs `py2mcp>=0.1.4` + `fastmcp` + `uvicorn` where the service runs.

## Key distinctions (don't conflate)

- **Local `.mcpb` (`claude-local-mcpb`):** stdio, no OAuth, runs on the user's machine.
- **Remote connector (`claude-remote-connector`):** a hosted MCP server reached from
  Anthropic's cloud over HTTPS + OAuth — public, multi-user, you deploy it.
- A connector is *connectivity* (tools). A **Skill** (`SKILL.md`) is *procedural
  knowledge*. They are complementary.

## Limitations (current)

- Targets: `claude-local-mcpb` and `claude-remote-connector`. Claude Code plugins,
  ChatGPT Apps, and Gemini are planned (the registry is open-closed).
- Tools are referenced by `module:function`; the **functions must be importable**
  where the server runs (dependency vendoring is a future refinement).
- Background: `misc/docs/CHATBOT_INTEGRATION_LANDSCAPE.md`.
