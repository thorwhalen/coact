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
  a local MCP server", "wrap my tools as a Claude Desktop extension". For REMOTE
  claude.ai connectors (HTTPS + OAuth) this is the wrong target — that surface is
  not built yet (see Limitations).
metadata:
  version: 0.1.0
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

Python API:

```python
from coact import publish, integration_spec_from

publish(["mypkg.tools:summarize", "mypkg.tools:translate"],
        name="text-tools", dest="dist", author="Me")
```

Install the result: Claude Desktop → Settings → Extensions → Install Extension…
(or double-click the `.mcpb`). The extension runs **on the user's machine** and
needs a Python with `py2mcp` + `fastmcp` importable.

## Key distinctions (don't conflate)

- **Local `.mcpb` (this target):** stdio, no OAuth, runs on the user's machine.
- **Remote claude.ai connector (NOT this target):** a remote MCP server reached
  from Anthropic's cloud over HTTPS + OAuth — a different surface, not yet built.
- A `.mcpb` is *connectivity* (tools). A **Skill** (`SKILL.md`) is *procedural
  knowledge*. They are complementary; this skill packages the former.

## Limitations (current)

- Only `claude-local-mcpb`. Remote connectors, Claude Code plugins, ChatGPT
  Apps, and Gemini are planned targets (the registry is open-closed).
- The bundle references tools by `module:function`; the **functions must be
  importable** in the Python that Claude Desktop runs (full dependency vendoring
  into the bundle is a future refinement).
- Background: `misc/docs/CHATBOT_INTEGRATION_LANDSCAPE.md`.
