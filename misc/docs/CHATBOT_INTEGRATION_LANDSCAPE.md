> **coact context.** This is the companion research to
> [`The agent-definition interop landscape`](./The%20agent-definition%20interop%20landscape%20—%20what%20a%20skill→agent→runtime%20toolkit%20must%20target%20in%202026.md).
> That doc covers coact's existing axis — *skill → agent definition → running
> agent* across **agent frameworks** (host / Claude Agent SDK / MCP / LiteLLM /
> LangGraph / CrewAI). **This** doc covers the orthogonal **publish/deploy axis**:
> turning a capability (a skill, or Python functions, or a refined
> natural-language description) into a **deployed chatbot integration** —
> Claude **Connectors**, **Agent Skills**, **Desktop Extensions (MCPB)**, and
> **Claude Code Plugins** first; ChatGPT and Gemini as future targets. It is the
> background research for adding a publish/deploy emit-target + realize-backend
> family to coact (see the hosting decision discussion that accompanied this
> doc). Produced by a 43-agent research workflow with an adversarial
> verification pass; see the **Verification notes** appendix for corrections to
> fast-moving claims. Accurate as of **mid-2026**.

---

# Building Creator-Facing AI Chatbot Integrations: The Extensibility Landscape and a Target-Neutral Architecture

> A deep-research reference for an agent-driven toolkit that creates, modifies, deploys, and updates integrations ("connectors", skills, plugins, apps) for AI chatbots — **Claude first**, architected so Claude is one pluggable target among future ones (ChatGPT, Gemini).
>
> Status note: This space moves quarterly. Dates and product names are accurate as of **mid-2026**; sections flagged *(fast-moving)* should be re-verified before they drive a commitment. URLs reflect the mid-2026 Anthropic domain migration (`claude.com` / `support.claude.com` / `code.claude.com` / `platform.claude.com`).

---

## 1. Executive summary

The single most important fact for our toolkit is that the industry has **converged on the Model Context Protocol (MCP)** as the cross-vendor substrate for tool/context integration. Anthropic created it; OpenAI's Apps SDK is built on it; Google's Gemini SDKs ship a built-in MCP client and Google adopted MCP across its own cloud services in late 2025 [1][8][16]. This means a correctly-built **MCP server is reusable, essentially unchanged, as the core artifact for Claude, ChatGPT, and Gemini** — making an MCP-first, Claude-first strategy the lowest "painting-into-a-corner" risk available [16].

But "an integration" is not one thing. There are **three orthogonal axes** that the industry (and most blog posts) routinely conflate, and getting them straight is the central contribution of this report [9][20]:

1. **Connectivity / capability** — *what the model can do*: MCP **tools**, **resources**, **prompts**; surfaced to end users as **Connectors** (Claude) / **Apps** (ChatGPT). Mnemonic: **verbs**.
2. **Procedural knowledge** — *how to do a task well*: Anthropic **Agent Skills** (`SKILL.md` folders, progressive disclosure). These are *instructions*, not connectivity. Mnemonic: **how-to**.
3. **Packaging / distribution** — *how it ships*: **Claude Code Plugins** (bundle skills + commands + MCP refs + hooks), **MCPB / `.mcpb`** Desktop-Extension bundles (one-click local MCP install), marketplaces, the unified Customize directory.

A fourth, deployment-shaped distinction cuts across all of this: **local (stdio) vs remote (Streamable HTTP)** servers. Crucially, a **claude.ai "custom connector" is always a *remote* MCP server reached from Anthropic's cloud — even on Desktop** — so it must be a publicly-reachable HTTPS endpoint with OAuth 2.1; this is *not* interchangeable with a local stdio server installed on Claude Desktop [3][10].

**Design recommendation (elaborated in §9):** build a **target-neutral core spec model** plus **per-target adapters**. The canonical emitted artifact is an MCP server (Streamable HTTP for remote, stdio for local). On top sit thin adapters: an MCPB packer for one-click local install, a Skill emitter for procedural know-how, a Plugin/marketplace packer for distribution, and — for future neutrality — a slim OpenAPI 3.x facade (GPT Actions + Gemini function-calling) and optionally an A2A AgentCard (agent-to-agent). **Do not reinvent transports, OAuth, schema generation, or proxying** — wrap **FastMCP (standalone)** as the emit backend [7]. Our own `py2mcp` keeps its unique value (function→MCP via `i2` introspection; `MutableMapping`/store→MCP) and delegates the commodity machinery [7].

The hard-won lessons (§8): ChatGPT Plugins died of bad discovery, non-composability, and walled-garden lock-in [16][20]; **over-tooling** collapses tool-selection accuracy (>90% → ~13%) and burns 100k–200k tokens before the first user turn [20]; **tool naming/description quality** dominates reliability and cannot be fixed by prompting [20]; and **security (prompt injection, tool poisoning, OAuth RCE) was retrofitted**, so we must design it in from day one [2][20].

---

## 2. The extensibility landscape — the full map

Chatbots are extended along several surfaces. The table below maps every surface to its mechanism, runtime artifact, and current status. Read it as the territory; §3 gives the precise glossary, §5–§6 the per-vendor detail.

### How each vendor lets you extend the assistant

| Vendor | Surface | What it actually is | Runtime artifact | Status (mid-2026) |
|---|---|---|---|---|
| **Claude** | **Custom Connector** | Remote MCP server added by URL + OAuth, reached from Anthropic cloud | Public HTTPS Streamable-HTTP MCP server | Live (beta); Free=1 connector [3] |
| **Claude** | **Local MCP server** | On-device stdio server (Desktop/Code) | stdio MCP server (config/CLI) | Live [3][10] |
| **Claude** | **Desktop Extension (MCPB)** | One-click-installable local MCP bundle | `.mcpb` zip (manifest + server + deps) | Live; `.dxt` legacy alias [4] |
| **Claude** | **Agent Skill** | Procedural know-how (`SKILL.md` + scripts) | Skill folder | Live (Oct 2025); org-wide mgmt Dec 2025 [5] |
| **Claude** | **Claude Code Plugin** | Distribution bundle (skills+commands+MCP refs+hooks) | Plugin dir + marketplace | Live [6] |
| **ChatGPT** | **GPT Action** | OpenAPI 3.x REST call embedded in a Custom GPT | OpenAPI schema (no server logic) | Live (lightweight) [9][16] |
| **ChatGPT** | **App (Apps SDK)** | MCP server + optional embedded UI | MCP server (+ MCP Apps iframe UI) | Preview→ submission/directory opened Dec 17 2025 [9][*correction*] |
| **ChatGPT** | **Plugin** | Hosted `ai-plugin.json` + OpenAPI, discovered by ChatGPT | — | **Deprecated/shut down Apr 2024** [9][16] |
| **Gemini** | **Gem** | Saved custom-instruction persona | — (no tool artifact) | Live — *not an integration surface* [8] |
| **Gemini** | **Consumer Extension / Workspace app** | First-party Google connector | — (not a public SDK) | Live (first-party only) [8] |
| **Gemini** | **API function calling / MCP client** | Model calls your functions / MCP server | OpenAPI-subset fn decls or MCP server | Live [8] |
| **Gemini** | **Gemini CLI Extension** | Packaged MCP server + context for the CLI | MCP server bundle | Live [8] |
| **Cross-vendor** | **MCP server** | The convergence substrate (tools/resources/prompts) | MCP server | Live — *the core artifact* [1][16] |
| **Cross-vendor** | **A2A** | Agent-to-agent interop (peer to MCP, not a tool layer) | AgentCard + JSON-RPC/SSE endpoint | Live; LF project, v1.0 in 2026 [8] |

**The convergence story.** The right way to read this table is *vertical*: the bottom two rows are the cross-vendor layer, and the per-vendor rows above them are increasingly thin shells over MCP. ChatGPT Apps *are* MCP servers; Gemini *consumes* MCP servers; Claude Connectors *are* remote MCP servers. Where surfaces diverge is in **distribution** (each vendor has its own directory/store or none) and in **UI** (ChatGPT's Apps SDK adds embedded iframe components via the **MCP Apps** extension) [9][16].

---

## 3. Terminology & taxonomy

This section is the load-bearing one: it lets us *use words correctly*. Industry blog posts collide on at least three pairs of terms ("plugin", "extension", "connector"); we adopt the precise senses below and use them consistently throughout.

### 3.1 Glossary

**MCP & protocol**
- **MCP (Model Context Protocol)** — Open, JSON-RPC 2.0 protocol (modeled on the Language Server Protocol) connecting LLM apps to external context/capabilities. Stateful, capability-negotiated. Spec is a date-versioned TypeScript schema; current published revision **2025-11-25** [1][19].
- **Host** — The LLM application (Claude Desktop, Claude Code, VS Code, ChatGPT) that initiates connections and embeds clients [1].
- **Client** — A connector *inside* the host; one 1:1 stateful connection per server [1].
- **Server** — The service exposing tools/resources/prompts over a transport. "Local" = stdio; "remote" = Streamable HTTP [1].
- **Tool** — A **model-controlled** function the model can invoke (JSON-Schema input); `tools/list`, `tools/call`. The universal unit of model-invoked action [1][20].
- **Resource** — **App-controlled** readable data/context; supports `subscribe`/`listChanged` [1].
- **Prompt** — **User-controlled** templated message/workflow [1].
- **Sampling / Elicitation / Roots** — **Client** capabilities a server may *request* if negotiated: sampling = ask the host LLM for a completion; elicitation = ask the *user* for structured input; roots = filesystem/URI boundaries. Servers must degrade gracefully when absent [1].
- **Capability negotiation** — The `initialize` exchange declaring which optional features are active for the session [1].
- **Streamable HTTP** — Current remote transport: one endpoint, POST + GET, optional SSE upgrade, `Mcp-Session-Id` sessions. Replaced HTTP+SSE in 2025-03-26 [1][10].
- **HTTP+SSE transport (deprecated)** — The 2024-11-05 two-endpoint transport with an `endpoint` SSE event; superseded [1][10].
- **stdio transport** — Local subprocess transport; newline-delimited JSON-RPC over stdin/stdout (stderr = logs). No OAuth; creds from env [1][10].
- **server.json** — Metadata format of the official MCP Registry [1].
- **MCP Registry** — Canonical open catalog/API (registry.modelcontextprotocol.io, preview Sep 2025); federates sub-registries (e.g. GitHub MCP Registry) [1].
- **Tasks (experimental)** — 2025-11-25 utility for durable long-running requests with polling [1].

**Claude-specific**
- **Connector** — Anthropic's *user-facing* name for an integration (usually a remote MCP server) that lets Claude access apps/services. Umbrella term including Anthropic-built/verified and **custom connectors** [3].
- **Custom connector** — A *remote* MCP server a user/admin adds by URL (optional OAuth). **Reached from Anthropic's cloud, not the device — even on Desktop** [3].
- **Agent Skill** — Folder with `SKILL.md` (+ `scripts/`, `references/`, `assets/`) teaching Claude *how* to do a task; loaded via progressive disclosure. Procedural knowledge, **not** connectivity [5].
- **Desktop Extension / MCPB (`.mcpb`)** — One-click-installable bundle (zip: `manifest.json` + local MCP server + deps) for Claude Desktop. **Current** name; `.dxt` is the legacy alias [4].
- **Claude Code Plugin** — Self-contained dir bundling skills, agents, hooks, MCP/LSP server refs, monitors, output styles, bin, settings; distributed via marketplaces. **Distinct from the deprecated ChatGPT Plugin** [6].
- **Plugin marketplace** — A git repo (or URL/local) with `.claude-plugin/marketplace.json` listing plugins [6].

**ChatGPT-specific**
- **GPT Action** — OpenAPI 3.x schema embedded in a Custom GPT; declarative REST, no server logic [9][16].
- **App (Apps SDK)** — MCP server + optional embedded UI; ChatGPT's forward extensibility path [9].
- **MCP Apps** — Official MCP *extension* (`io.modelcontextprotocol/ui`, SEP-1865) for embedded iframe UIs via `ui/*` JSON-RPC over `postMessage`. Co-authored by Anthropic + OpenAI + MCP-UI community; **a standalone extension, not core MCP** [*correction*].
- **ChatGPT Plugin (deprecated)** — 2023 model (`ai-plugin.json` + OpenAPI); shut down Apr 2024 [9][16].

**Gemini / cross-agent**
- **Gem** — Saved custom-instruction persona (system prompt + optional files). **Not** a tool/integration surface [8].
- **Gemini Extension** — Two senses: (a) consumer Workspace connectors (first-party only); (b) **Gemini CLI Extensions** (packaged MCP servers + context) [8].
- **A2A (Agent2Agent)** — Open agent-to-agent protocol (HTTP + SSE + JSON-RPC 2.0; **AgentCard** discovery). Google → Linux Foundation. **Complementary to MCP** (agent↔agent vs agent↔tool) [8].
- **AgentCard** — A2A's `/.well-known/agent-card.json` capability descriptor [8].

### 3.2 Cross-system equivalence table

| Concept | Claude | ChatGPT | Gemini | Cross-vendor |
|---|---|---|---|---|
| Model-invoked action | MCP **tool** | function / GPT Action op | function declaration | **MCP tool** |
| Readable context | MCP **resource** | (data via tool result) | (data via tool result) | MCP resource |
| Templated workflow | MCP **prompt** | — (GPT instructions) | — | MCP prompt |
| User-facing integration | **Connector** | **App** (was Plugin/connector) | Extension (first-party) | remote MCP server |
| Local one-click install | **MCPB** (`.mcpb`) | — | — | (MCP bundle) |
| Procedural know-how | **Agent Skill** (`SKILL.md`) | (GPT instructions/files) | **Gem** instructions | Agent Skills open std [5] |
| Configured-assistant persona | Project / Skill-ish | **Custom GPT** | **Gem** | — |
| Distribution bundle | **Claude Code Plugin** | — | Gemini CLI Extension | — |
| Embedded UI | (via Apps SDK on shared MCP) | **Apps SDK + MCP Apps** | — | MCP Apps extension |
| Discovery catalog | Customize directory / Connectors Directory / `claude.com/plugins` | ChatGPT app directory | (none third-party) | **MCP Registry** |
| Agent-to-agent | — | — | — | **A2A** (AgentCard) |

**Terminology hazards to encode in our tooling** (each a documented source of confusion) [3][6][9][20]:
- "**Plugin**" means *two unrelated things*: a Claude Code Plugin (a 2025 bundle) vs the deprecated ChatGPT Plugin. Never use the bare word in design docs.
- "**Connector**" (Claude's product view of a remote MCP server) ≠ "**plugin**" (a broader Claude Code bundle that can *reference* an MCP server by URL).
- "**Extension**" splits three ways: Claude **Desktop Extension** (MCPB), Gemini **consumer Extension** (Workspace connector), Gemini **CLI Extension** (MCP bundle).
- "**DXT**" is the *old* name; the current packaging format is **MCPB / `.mcpb`**.
- "**Gems**" and "**Custom GPTs**" are *configured-assistant personas*, not connectivity primitives.

---

## 4. MCP deep-dive

MCP is the protocol our core artifact speaks. This section is precise because every per-target adapter inherits from it.

### 4.1 Architecture & primitives

MCP is **JSON-RPC 2.0** over **stateful** connections among three roles — **Host → Client → Server** — explicitly modeled on the Language Server Protocol [1]. The capability set splits into:

- **Server primitives** — **tools** (model-callable), **resources** (readable; sub-capabilities `subscribe`, `listChanged`), **prompts** (`listChanged`). Plus utilities: logging, completions [1].
- **Client primitives** — **sampling** (server-initiated LLM completion; 2025-11-25 adds tool-calling within sampling), **roots** (filesystem/URI boundaries), **elicitation** (server-initiated user-input requests; 2025-11-25 adds URL-mode + richer enum schemas) [1].

The **control-ownership** distinction matters for clean design: tools are *model-controlled*, resources are *app-controlled*, prompts are *user-controlled* [20]. Don't smuggle data retrieval into a tool when a resource fits.

A `MutableMapping`/store maps naturally onto **resources + resource templates** (with mutation operations as **tools**) — directly relevant to `py2mcp`'s `mk_mcp_from_store` [1][7].

### 4.2 Lifecycle & version negotiation

Three phases [1]:
1. **Initialization** — client sends `initialize` (`protocolVersion` + capabilities + `clientInfo`); server responds (capabilities + `serverInfo` + optional `instructions`); client sends `notifications/initialized`.
2. **Operation** — only negotiated capabilities may be used.
3. **Shutdown** — *no protocol message*; signaled by closing the transport (stdin close/SIGTERM for stdio; closing the HTTP connection).

**Version is a date string** (e.g. `2025-11-25`), not semver. Lineage: `2024-11-05` → `2025-03-26` (introduced Streamable HTTP) → `2025-06-18` (OAuth resource-server rework) → `2025-11-25` (current). Negotiation: client sends its latest; server echoes if supported, else returns its own latest; client disconnects if it can't comply (JSON-RPC error `-32602` "Unsupported protocol version" with `data.supported`). The TypeScript `schema.ts` is authoritative; **JSON Schema 2020-12** is now the default dialect (SEP-1613) [1][19].

### 4.3 Transports

| | **stdio** | **Streamable HTTP** | **HTTP+SSE (deprecated)** |
|---|---|---|---|
| Shape | subprocess, JSON-RPC over stdin/stdout | single endpoint, POST + GET, optional SSE | separate SSE + POST endpoints, `endpoint` event |
| Use | local/desktop (spec-preferred default) | remote/hosted | legacy backwards-compat only |
| Auth | env/config (no OAuth) | OAuth 2.1 | — |
| Sessions | per-process | `Mcp-Session-Id` header | — |
| Status | current | **current** | **deprecated since 2025-03-26** [1][10] |

Streamable HTTP specifics [1][10]: POST returns either `application/json` (single) or `text/event-stream` (SSE). Server **MAY** return `Mcp-Session-Id` on `InitializeResult`; clients **MUST** echo it (missing → 400; terminated → 404 → re-initialize). Clients **MUST** send `MCP-Protocol-Version` on all post-init HTTP requests (else server assumes `2025-03-26`). Resumability via SSE `id` + `Last-Event-ID`. **Security defaults:** validate `Origin` (HTTP 403 on mismatch — DNS-rebinding defense), bind to `127.0.0.1` when local, authenticate connections.

The deprecated **HTTP+SSE** transport (two endpoints + `endpoint` event) survives only for backwards-compat; many old tutorials still describe it — **do not build new servers on it** [10].

### 4.4 Authorization (OAuth 2.1)

Remote MCP auth applies **only to HTTP transports** (stdio uses env creds). The MCP server is an **OAuth 2.1 resource server — never the authorization server** (an early anti-pattern explicitly rejected in spec issue #205) [2][10].

The discovery + token chain [2][10]:
1. Unauthenticated request → **401** with `WWW-Authenticate: ... resource_metadata=...`.
2. Client fetches `/.well-known/oauth-protected-resource` (**RFC 9728** Protected Resource Metadata) → `authorization_servers`.
3. Client fetches AS metadata (RFC 8414 / OpenID Connect Discovery).
4. OAuth 2.1 + **PKCE (S256 mandatory)**, no implicit grant, exact redirect-URI matching.
5. Token request includes **RFC 8707 `resource` indicator** binding the token's audience to *this* server.
6. Calls carry `Authorization: Bearer` (never in the query string).

**Client registration priority (2025-11-25):** pre-registered creds → **Client ID Metadata Documents (CIMD)** (HTTPS-URL-as-`client_id`, now *preferred* for parties with no prior relationship) → **Dynamic Client Registration (RFC 7591)** (now a *fallback*) → prompt user [2][10].

**Hard rules:** servers **MUST** validate the token *audience* and **MUST NOT** accept tokens issued for other resources or **forward the inbound token upstream** ("token passthrough" is forbidden — it creates the **confused-deputy** vulnerability). Upstream calls use a *separate* token (the server acts as a fresh OAuth client). Mitigate **SSRF** in discovery URLs (block private ranges, enforce TLS, egress proxy). Minimize scopes via step-up rather than wildcards [2].

### 4.5 The MCP Registry

The official **MCP Registry** (registry.modelcontextprotocol.io) launched in preview **2025-09-08** as the canonical open catalog/API, using the **server.json** metadata format (aligned with its OpenAPI spec) and supporting **federation**: public sub-registries (e.g. the GitHub MCP Registry) and private/enterprise sub-registries enrich the upstream data. Maintained by a working group spanning Anthropic, GitHub, Block, PulseMCP [1]. If we want discoverability, publishing a `server.json` doubles as canonical install/connection metadata and feeds downstream client marketplaces.

---

## 5. Claude targets in detail

Four distinct Claude surfaces — easy to conflate, very different runtimes, install paths, and plan rules. Be explicit about *which is which*.

### 5.1 Custom Connectors (claude.ai + Desktop) = remote MCP + OAuth

A **custom connector is a remote MCP server added by URL** under *Customize/Settings → Connectors → "+" → Add custom connector* (OAuth Client ID/Secret optional under Advanced) [3]. The architecturally decisive fact:

> "When you add a custom connector, Claude connects to your remote MCP server **from Anthropic's cloud infrastructure**, rather than from your local device." [3]

So even on **Desktop**, a custom connector is a *remote* connection requiring a publicly-reachable HTTPS endpoint. Firewalled/VPN/private-network servers will **not** connect; you must allowlist Anthropic's IP ranges and the OAuth callback. This is the core distinction from **local MCP** (stdio, on-device, configured via files or `claude mcp add`) and from packaged **Desktop Extensions** [3][10].

- **Transport:** Streamable HTTP (current) or legacy HTTP+SSE (deprecated).
- **Auth:** OAuth 2.1 + PKCE (S256); Claude supports DCR, CIMD, static client IDs held by Anthropic, or user-supplied creds. Callback URL `https://claude.ai/api/mcp/auth_callback` (may migrate to `claude.com`); Claude Code uses a **loopback** redirect [3].
- **Limits:** tool result ~150,000 chars (claude.ai/Desktop), 25,000 tokens (configurable) on Claude Code; **300 s** request timeout (claude.ai/Desktop) [3].
- **Plans:** Free (1 connector), Pro, Max, Team, Enterprise — labeled **beta** [3].
- **Org controls (Team/Enterprise):** enable org-wide; per-action permissions **Always allow / Needs approval / Blocked**; restrict verified-domain connectors [3].
- **Connectors Directory:** browsable catalog of Anthropic-verified connectors; developers submit remote MCP servers via an admin submission portal (requires reviewer test accounts + full access docs) [3].

### 5.2 Agent Skills (`SKILL.md`)

A **Skill** is a directory whose entry point is **`SKILL.md`** (YAML frontmatter + Markdown body), optionally bundling `scripts/`, `references/`, `assets/`. Skills are *procedural knowledge*, complementary to MCP/Connectors (connectivity); a Skill can *call* MCP tools [5].

**Progressive disclosure** (the central design) [5]:
- **L1** — name + description metadata (~100 tokens/skill), always in context.
- **L2** — the `SKILL.md` body, loaded only on trigger (recommended **<5k tokens / <500 lines**).
- **L3** — bundled files/scripts, read or executed via bash on demand; **script code never enters context, only its output**.

The frontmatter is an **open standard** (agentskills.io) adopted broadly (Cursor, Copilot/VS Code, Gemini CLI, OpenAI Codex, Goose, OpenHands) [5]. Required: `name` (≤64 chars, lowercase/digits/hyphens, **must equal the parent directory name**) and `description` (≤1024 chars, "what + when", keyword-rich). Optional: `license`, `compatibility` (≤500), `metadata` (string map), experimental `allowed-tools`. **There is no standard `version` field** — version goes inside `metadata` [5].

**Four surfaces, different mechanics, NO cross-sync** [5]:
- **claude.ai** — upload ZIP via Settings → Capabilities; Pro/Max/Team/Enterprise; per-user (but see the org-management correction below).
- **Claude API** — upload via `/v1/skills`; referenced by `skill_id` in `container.skills` (≤8/request) alongside the `code_execution` tool; behind beta headers `code-execution-2025-08-25`, `skills-2025-10-02`, `files-api-2025-04-14`. **Workspace-shared.** Runtime has **no network access and no runtime pip installs** (pre-installed packages only); not ZDR-eligible.
- **Claude Code** — pure filesystem (`~/.claude/skills/`, `.claude/skills/`, plugins). Extends the open standard with `disable-model-invocation`, `context: fork`, `allowed-tools`, `paths`, `` !`cmd` `` injection, etc. Full network/local access. Custom commands are merged into skills (`/foo` from either `commands/foo.md` or `skills/foo/SKILL.md`).
- **Agent SDK** — same filesystem skills, but you must set `setting_sources` / `settingSources` (the SDK doesn't load filesystem settings by default).

**Pre-built Anthropic Skills** are exactly the **four document skills**: PowerPoint (`pptx`), Excel (`xlsx`), Word (`docx`), PDF (`pdf`) — on claude.ai, the API, Claude on AWS, and Microsoft Foundry [*correction*]. The **Claude API skill is *not* a pre-built Agent Skill** — docs list it under a separate *Open-source Skills* category (bundled with Claude Code, installable from `anthropics/skills`). The `anthropics/skills` repo publishes many *other* first-party open-source/example skills beyond these [*correction*].

**Organization-wide Skills management** *(corrected; supersedes "strictly per-user")*: on **2025-12-18** Anthropic shipped org-wide Skills management for **Team and Enterprise** plans. Admins centrally provision/distribute custom (and partner) Skills from *Organization settings → Skills*: uploaded skills are immediately provisioned to all members (enabled by default, per-user opt-out), can be scoped to groups by bundling into a plugin, and are managed/audited from a central console (sharing tracked as `role_assignment` audit events). On **Free/Pro** plans, custom Skills remain **per-user** with no centralized distribution [*correction*].

### 5.3 Claude Code Plugins

A **plugin** is a self-contained directory bundling **skills** (`/plugin-name:skill`), **agents/subagents**, **hooks**, **MCP servers** (`.mcp.json`), **LSP servers** (`.lsp.json`), background **monitors**, output styles, `bin/`, and default `settings.json`. The only required file is `.claude-plugin/plugin.json`, whose only required field is `name` [6].

**Critical layout gotcha** (official docs' "Common mistake"): **only `plugin.json` goes inside `.claude-plugin/`** — all component directories (`skills/`, `agents/`, `hooks/`, etc.) live at the **plugin root**. Putting them inside `.claude-plugin/` breaks the plugin [6].

**Marketplaces:** a git repo (or local path / hosted URL) with `.claude-plugin/marketplace.json` at root, declaring `name`, `owner`, and a `plugins[]` array (each with a `source`: relative `./path`, `github`, `url`, `git-subdir`, or `npm`) [6]. Install flow: `/plugin marketplace add owner/repo` → `/plugin install plugin@marketplace` (copies into `~/.claude/plugins/cache`) → `/reload-plugins`. Teams auto-provision via `extraKnownMarketplaces`/`enabledPlugins` in `.claude/settings.json` [6].

**Versioning:** set `version` in `plugin.json` to pin (users update only on a bump); omit it and Claude Code falls back to the git commit SHA (every commit = a new version) [6]. **Caching gotcha:** plugins are copied to cache, so a plugin **cannot reference files outside its own dir** (`../shared` fails); use symlinks. `${CLAUDE_PLUGIN_ROOT}` (and `${CLAUDE_PROJECT_DIR}`, `${user_config.*}`) resolves paths inside hook/MCP/LSP commands [6].

**Skills-directory plugins (`@skills-dir`):** a folder under a skills dir containing `.claude-plugin/plugin.json` auto-loads (no marketplace/install step) — the bridge between standalone `.claude/` config and full marketplace plugins [6].

**Unified directory** *(corrected)*: Anthropic *did* unify Skills, Connectors, and Plugins into a single browsable **"Customize" directory** — but **not** at `claude.ai/directory` (that returns 403). The support article points to **`claude.ai/customize/skills`**; the plugins catalog is at **`claude.com/plugins`**. The consolidation tracks to the Enterprise Agents event (Feb 24 2026); plugins launched in Cowork (~Jan 30 2026). The widely-cited **"2026-03-31" date is unverified** — it appears only in AI-generated summaries, not in any primary Anthropic page [*correction*].

### 5.4 Desktop Extensions / MCPB

**Desktop Extensions** (launched 2025-06-26 as `.dxt`, renamed **MCPB / `.mcpb`** on 2025-09-11, donated to `modelcontextprotocol/mcpb` ~2025-11-20) make **local** MCP servers installable in Claude Desktop with **one click, no terminal**. A bundle is a **ZIP** containing a required **`manifest.json`** + server code + bundled deps [4].

- **Manifest** (`manifest_version` — *not* the old `dxt_version`): `name`, `version`, `description`, `author`, `server`; optional `tools`, `prompts`, `user_config`, `compatibility`, `icon` [4].
- **`server.type`:** `node` (Claude Desktop ships Node — least friction), `python`, `uv` (host-managed Python deps — preferred for Python tooling), or `binary` [4].
- **`user_config`:** typed settings (`string`/`number`/`boolean`/`directory`/`file`) auto-generate a settings UI; `sensitive: true` strings go to the **OS keychain** [4].
- **Template interpolation:** `${user_config.KEY}`, `${__dirname}`, `${HOME}`, `${pathSeparator}` injected into `mcp_config` command/args/env at launch [4].
- **CLI** (`npm i -g @anthropic-ai/mcpb`): `init`, `validate`, `pack`, `sign`/`verify`/`unsign`, `info`. **Signing** = detached PKCS#7/X.509 (`--self-signed` for dev; CA-issued for production) [4].
- **Enterprise:** Group Policy (Windows) / MDM (macOS) to pre-install, blocklist, or disable [4].

**Gotcha:** `mcpb pack` deliberately excludes dev artifacts — run `npm install --production` (Node) or vendor into `server/lib/` first, or runtime deps will be missing [4].

---

## 6. Cross-system targets (for future neutrality)

We build Claude-first, but the architecture must not preclude ChatGPT and Gemini. The good news: **MCP is the convergence point**, so a single MCP server is reusable across all three [16].

### 6.1 ChatGPT — Apps SDK + GPT Actions

ChatGPT offers **two live surfaces** (and one dead one) [9][16]:

- **GPT Actions** — an **OpenAPI 3.x schema embedded in a Custom GPT** (auth None/API-key/OAuth). No server logic, no hosted manifest, no UI. The lightweight "declarative REST" option.
- **Apps SDK** — the forward path. The deployable artifact is an **MCP server** implementing list/call tools and optionally returning **embedded UI** (an iframe). OpenAI's SDKs reuse the official MCP Python/TypeScript SDKs [9].
- **ChatGPT Plugins** — **dead**: new conversations ceased ~Mar 19 2024, all plugin chats shut down ~Apr 9 2024 [9][16].

**MCP Apps** (embedded UI): UIs run in a **sandboxed iframe** and talk to the host via **`ui/*` JSON-RPC over `postMessage`** (`ui/open-link`, `ui/message`, `ui/request-display-mode`, `ui/update-model-context`, `ui/notifications/*`). ChatGPT-specific extras (checkout, file handling, modals) layer on via `window.openai` — gate these behind capability checks to keep UI portable [9][*correction*].

*Correction on status (fast-moving):* MCP Apps (**SEP-1865**, extension ID `io.modelcontextprotocol/ui`) is **NOT being upstreamed into core MCP** — by design it is a standalone **official extension** in `modelcontextprotocol/ext-apps`, negotiated via the extension-capabilities mechanism and versioned independently. The 2026-07-28 spec RC formalized an "Extensions Become First-Class" model listing MCP Apps and Tasks as the two official extensions, explicitly distinct from core. It is a *single cross-vendor extension* (Anthropic + OpenAI + MCP-UI community), not a "ChatGPT vs core" split [*correction*].

*Correction on distribution (fast-moving):* On **Nov 13 2025** OpenAI made apps/Apps SDK available only in **PREVIEW** (incl. a Business/Enterprise/Edu preview; logged-in Free/Go/Plus/Pro outside EEA/Switzerland/UK) — **not GA**, and the **submission flow + directory did not yet exist**. The **submission flow and ChatGPT app directory opened Dec 17 2025** (directory rolled out to Plus/Team/Enterprise Dec 17–18), via the OpenAI Developer Platform, with approved apps "rolling out starting early 2026." The accurate part of older claims: **'connectors' were renamed to 'apps' on Dec 17 2025.** **Verify plan-by-plan GA before committing to a distribution plan** [*correction*].

### 6.2 Gemini — Gems, Extensions, function calling, MCP

- **Gems** are saved custom-instruction **personas** — *not* an integration surface. Targeting them for tool calls is a category error [8].
- **Consumer Extensions / Workspace apps** (Gmail, Drive, Docs, etc.) are **first-party Google connectors**, not a public third-party SDK [8].
- **Real third-party surfaces:** (a) **Gemini API function calling** (OpenAPI-subset JSON-schema declarations; the model emits structured calls); (b) **built-in MCP client support** in the Gemini SDKs (pass an MCP client session → automatic tool calling); (c) **Gemini CLI Extensions** (packaged MCP servers + context) [8].
- Google **adopted MCP across its services** (Maps, BigQuery, Compute Engine, GKE managed remote MCP servers) in **December 2025** [8].

There is **no open third-party app store in the consumer Gemini app** comparable to ChatGPT's — so plan **distribution per-target even when the runtime artifact (MCP server) is shared** [8].

### 6.3 A2A — the agent-mesh layer

**A2A (Agent2Agent)** is Google-originated (announced Apr 2025, donated to the Linux Foundation Jun 2025, Apache-2.0, reached **v1.0 in 2026**, 150+ orgs). Transport: **HTTP + SSE + JSON-RPC 2.0**; discovery via an **AgentCard** (`/.well-known/agent-card.json`); security OAuth2/API-key/mTLS. It is **explicitly complementary to MCP**: **MCP = agent↔tools; A2A = agent↔agent.** It is *not* a tool-integration competitor; picking one "instead of" the other is a misread [8].

For us: A2A is the **only non-MCP standard worth a future adapter**, and it sits at the agent-mesh layer, not the tool layer. Out of scope for a tool/extension artifact unless multi-agent interop becomes a requirement [8].

---

## 7. Build on, don't reinvent — Python MCP frameworks

There are three layers worth building on rather than re-implementing transports, OAuth, schema generation, or proxying [7].

### 7.1 The three layers

1. **Official `modelcontextprotocol/python-sdk`** (Anthropic, MIT) — the protocol reference. Two tiers: low-level `mcp.server.lowlevel.Server` (full control) and the high-level **`FastMCP`** class (decorator API — `@mcp.tool`, `@mcp.resource`, `@mcp.prompt`; this is **FastMCP 1.0**, merged into the SDK in 2024). Transports: stdio, SSE (legacy), Streamable HTTP. OAuth 2.1 resource-server auth (RFC 9728). **No OpenAPI/FastAPI generation.** SDK **v1.x is current/maintenance**; **v2 is in ALPHA** (`2.0.0aN` on PyPI, beta targeted **2026-06-30**) [7].

2. **FastMCP (standalone, jlowin → PrefectHQ, Apache-2.0)** — the de-facto-standard **superset**, now on the **v3.x** line (v3.4.2, 2026-06-06; "v2" is the historical post-merge name). Adds **enterprise auth** (WorkOS AuthKit provider, OAuth proxy, `TokenVerifier`, full DCR; shipped 2.11, 2025-08-01), **`FastMCP.from_openapi()`** and **`FastMCP.from_fastapi()`** generation with `RouteMap` customization, server proxying, composition (mount/import), a full client, and deployment (Prefect Horizon gateway) [7].
   *(The widely-quoted "powers ~70% of MCP servers across all languages" is an **unverified self-reported figure** from FastMCP's own materials — "some version of FastMCP" folds in the SDK's incorporated high-level API. Treat as a directional vendor claim, not a measured statistic. FastMCP is **plausibly the dominant Python MCP framework**, but the exact share is unconfirmable [*correction*].)*

3. **Dedicated OpenAPI→MCP generators** — AWS Labs `awslabs.openapi-mcp-server` (Python, **runtime-dynamic**, multi-auth, production-hardened); cnoe-io `openapi-mcp-codegen` (Python **codegen** → standalone packages); Speakeasy (TypeScript codegen) [7].

**Caveat to surface to users:** FastMCP itself warns that **auto-converted OpenAPI/FastAPI servers are prototyping-grade, not production** — "LLMs achieve significantly better performance with well-designed and curated MCP servers than with auto-converted OpenAPI servers." Curated tools win [7][20].

### 7.2 How our local packages relate

- **`py2mcp`** — its differentiators are (i) **Python-function→MCP via `i2`-style signature introspection** and (ii) **`MutableMapping`/store→MCP** (`mk_mcp_from_store`) — *neither* the official SDK nor the OpenAPI generators target these. The transport/auth/schema/proxy machinery is **commodity**. **Recommendation:** make `py2mcp` **emit a FastMCP (standalone) server object** under the hood (register introspected functions as `@mcp.tool` equivalents), inheriting Streamable HTTP, WorkOS AuthKit/DCR auth, and FastMCP Cloud/Horizon deployment for free. Frame `py2mcp` as **curated, high-quality tool surfacing** — exactly what FastMCP says beats auto-conversion [7].
- **`skill`** — owns the **procedural-knowledge axis**: author/search/validate/manage `SKILL.md` skills across hosts, and the pip-distribution mechanics (`{pkg}/data/skills/` + `.claude/skills/` symlink bridge). This is the natural home for our **Skill-emitter adapter** [5].
- **`aikb`** — dict-like CRUD + git-style **sync** for AI knowledge bases (Claude Projects, Gemini Gems, local files). Relevant for the *configured-assistant-persona* axis (Gems/Projects), distinct from connectivity [8].
- **`coact`** — the orchestrator hosting this work: its `emit`/`realize` open-closed registries are the extension points for the new connector/plugin/MCPB emit-targets and deploy backends; it already delegates real MCP-server construction to `py2mcp` (the `mcp` realize backend) and integrates `skill` as its SSOT.

For any "OpenAPI/FastAPI → MCP" need, **delegate to `FastMCP.from_openapi`/`from_fastapi`** (in-process, Pythonic, `RouteMap`-customizable) rather than writing a parser. Reserve AWS Labs for a runtime/no-build deployment story and cnoe-io/Speakeasy codegen only if standalone distributable artifacts are required [7].

---

## 8. Pitfalls, security & lessons learned

### 8.1 Why ChatGPT Plugins were deprecated

The plugin model (hosted `ai-plugin.json` + OpenAPI, discovered/installed by ChatGPT) failed on **poor discovery** (manual store browsing), **inconsistent UX/reliability**, **trust/safety friction**, a **single-vendor walled garden**, and a **one-plugin-at-a-time, non-composable** model. The replacement trajectory — Plugins → GPTs/Actions → MCP-based Apps — *is itself the lesson*: a proprietary, non-composable, manually-discovered extension model loses to an **open, composable, model-discoverable** one [9][16][20]. **Design for openness and composability.**

### 8.2 MCP over-tooling / context bloat

Loading many tools **collapses selection accuracy** (cited **>90% with few tools → ~13% with many**). A 93-tool GitHub MCP server is ~55k tokens at init; a typical enterprise stack burns **100k–200k tokens before the first user message**; tool schemas can consume **40–50% of the context window**, amplified by "lost in the middle" [20]. Documented mitigations: **retrieval-gated tool exposure** (RAG-MCP: >3× accuracy, >50% token cut), **namespacing**, lazy/on-demand schema loading, and schema dedup (`$ref`) — see spec issue **SEP-1576** [20]. **Treat the context window as a budget; measure tokens-at-init per server.**

### 8.3 Tool-description quality

Per Anthropic's *Writing tools for agents*: **poor/ambiguous schemas cannot be fixed by prompting alone.** Prefer **task-boundary-aligned names** (`query_database` + `update_database` over `execute_database_operation`) to cut ambiguity *and* schema surface; descriptions should include **examples, edge cases, boundaries**; namespacing (prefix vs suffix) has model-dependent effects — **choose by eval**. Make naming/descriptions a **first-class deliverable** with an eval harness [20].

### 8.4 Versioning

MCP negotiates `protocolVersion` at `initialize` and uses capability negotiation + `listChanged` notifications, but **breaking-change discipline across server tool versions is immature** [20]. **Build versioning in from day one:** negotiate protocol/capability versions, emit `listChanged`, and adopt a deprecation policy for tool signatures so consumers don't break silently. (Mirror this in our artifacts: pin plugin `version`; date-version the MCP protocol; track Skill versions via `metadata`.)

### 8.5 Security — retrofitted, so design it in

Security was **bolted on after adoption** [2][20]:
- **Prompt injection** (indirect, via fetched content).
- **Tool poisoning** — malicious directives in tool/server metadata read at boot, indistinguishable from legitimate context (**CVE-2025-54136 "MCPoison"**, CVE-2025-54135 "CurXecute"); **rug pulls** mutate a tool after install.
- **OAuth proxy RCE** in `mcp-remote` (**CVE-2025-6514**); hundreds of servers found exposed without auth.
- **Confused deputy** — token passthrough / missing audience validation.
- **SSRF** via discovery URLs; **data exfiltration via tool chaining** (which audience checks don't prevent).

**Defaults to enforce in our generated artifacts** [2][10][20]:
- OAuth 2.1 + least-privilege scopes for remote servers; MCP server as **resource server**, never AS.
- **Validate token audience** (RFC 8707/9068); **never passthrough**; mint separate upstream tokens.
- Validate `Origin` (403), bind local to `127.0.0.1`, block private IP ranges (SSRF).
- Treat **all server-supplied tool/resource metadata as untrusted**.
- Secrets via OS keychain (`user_config.sensitive` in MCPB) or short-lived OAuth tokens — **never bake credentials into env/manifest/SKILL.md**.
- Human approval for write/destructive tools (`require_approval` / Anthropic `mcp_toolset` configs; Claude org "Needs approval").
- Audit any OAuth-proxy dependency for known CVEs.

### 8.6 Deployment & transport pitfalls

- Don't build on the **deprecated standalone SSE transport** — only "SSE *within* Streamable HTTP" is current [10].
- Multiple **stateful** Streamable-HTTP instances behind a load balancer **break** with default in-memory sessions (sticky sessions are unreliable with MCP clients) — set `stateless_http=True` or externalize session state [10].
- A **VPN/firewalled/private** server **cannot** be a claude.ai or ChatGPT connector — vendor clouds connect from their own public IPs [3][10].
- Reverse-proxy SSE specifics: disable `proxy_buffering`, raise timeouts (300 s+) [10].
- On **stdio**, stray `print`/logging to stdout **corrupts the stream** — logs to stderr only [1].
- The Anthropic MCP connector is **not ZDR-eligible**; remote MCP servers operate under their own data policies [10].

### 8.7 Skills & plugins as a supply chain

Skills and plugins **execute arbitrary code with user privileges**; Anthropic does **not** vet third-party plugin contents [5][6]. Use only trusted sources; audit bundled files; never embed secrets/local paths in committed `SKILL.md`/scripts; project-level `allowed-tools` activate only after the workspace trust dialog (consider `disableSkillShellExecution`/managed settings to neutralize `` !`cmd` `` injection in shared repos) [5].

---

## 9. Implications for our design

### 9.1 Target-neutral architecture: core spec model + per-target adapters

Adopt a **Single Source of Truth (SSOT) IntegrationSpec** describing the integration *independent of any target*, then **per-target adapters** that emit concrete artifacts. This is a clean **Strategy + Facade** layering and keeps Claude as "one pluggable target."

```
                       ┌─────────────────────────────────────────────┐
  INPUT                │            CORE (target-neutral)            │
  ─────                │                                             │
  NL description ─┐    │   IntegrationSpec (SSOT):                   │
                  ├──▶ │     • tools[]  (name, desc, JSON-Schema,    │
  Existing code ──┘    │        handler ref, control-tier, scopes)   │
   (functions /        │     • resources[]  (store / read-only data) │
    stores /           │     • prompts[]    (templated workflows)    │
    FastAPI app)       │     • skills[]     (procedural know-how)    │
                       │     • auth model   (none | oauth2.1 | env)  │
                       │     • deployment   (local-stdio | remote)   │
                       └───────────────────┬─────────────────────────┘
                                            │  (adapters / Strategy)
        ┌───────────────┬───────────────┬──┴────────────┬───────────────┬──────────────┐
        ▼               ▼               ▼               ▼               ▼              ▼
   MCP server      MCPB packer     Skill emitter   Plugin/market-   OpenAPI 3.x    A2A AgentCard
  (FastMCP:        (.mcpb, one-    (SKILL.md +     place packer     facade         (future,
   stdio +          click local     scripts/refs)  (.claude-plugin) (GPT Actions   agent-mesh)
   Streamable        install)                                        + Gemini fn)
   HTTP, OAuth)
        │               │               │               │               │
        ▼               ▼               ▼               ▼               ▼
   Claude Connector  Claude Desktop  Claude/agents   Claude Code     ChatGPT GPT /
   ChatGPT App       (local MCP)     (all surfaces)  + Cowork        Gemini API/CLI
   Gemini MCP client
```

**Design rules (per the user's principles — functional core, facades, SSOT, DI, keyword-only beyond the 3rd arg):**
- The **MCP server adapter is primary**; everything else is derived. It emits a **FastMCP (standalone)** server (DI the framework so we can swap), giving Streamable HTTP + OAuth + deployment for free [7].
- **Tool handlers are transport-agnostic** behind a thin adapter so the *same* handler is exposed as (a) an MCP tool and (b) an OpenAPI 3.x REST endpoint — OpenAPI is the **secondary lingua franca** for GPT Actions + REST-style Gemini function calling [8][16].
- **Keep the three axes separate in the spec** (`tools/resources/prompts` = connectivity; `skills` = procedural; packaging = an emit concern), naming each unambiguously to dodge the industry's terminology collisions [20].
- **Curate, don't auto-dump.** Default to hand-selected tools; offer `from_openapi`/`from_fastapi` only as a *bootstrap* with a loud "prototype-grade" flag, plus a curation/selection pass (`py2mcp`'s input-transform layer) [7][20].

### 9.2 The build pipeline: description-or-code → spec → artifact → deploy → register/update

```
  (1) INGEST            (2) SYNTHESIZE        (3) EMIT             (4) DEPLOY            (5) REGISTER / UPDATE
  ─────────             ──────────────        ────────             ─────────             ────────────────────
  NL description  ─┐                          MCP server  ─┐       local: .mcpb pack     server.json → MCP Registry
   (LLM → spec)    ├─▶  IntegrationSpec  ─▶   MCPB bundle  ├─▶     remote: ASGI under  ─▶ Connectors Directory submit
  Python code   ───┘    (validate, eval       Skill pack   │       uvicorn + reverse      Plugin marketplace.json
   (i2 introspect)      tool names/descr)      Plugin pkg  ─┘       proxy / serverless      ChatGPT app submission
                                               OpenAPI facade                              version bump + listChanged
```

- **(1) Ingest.** NL → spec via an LLM step (our `oa`/`aix`/`pyrompt` stack); code → spec via `i2` signature introspection (functions) or `FastMCP.from_fastapi` (existing app) [7]. Stores → resources via `py2mcp.mk_mcp_from_store` [7].
- **(2) Synthesize.** Produce the validated `IntegrationSpec`. **Run a tool-quality eval gate** here (names, descriptions, schema size, token-at-init budget) — §8.2/§8.3 [20].
- **(3) Emit.** Adapters render artifacts. Align our object model on FastMCP's (Tool/Resource/ResourceTemplate/Prompt) and on **Streamable HTTP** as the production transport (stdio = local case) [7][10].
- **(4) Deploy.** Branch on web-service vs not (§9.3).
- **(5) Register/update.** Publish `server.json` to the MCP Registry; submit to the relevant directory; for plugins, manage `marketplace.json` + `version`; **on update, bump versions and emit `listChanged`** so clients don't break silently [1][6][20].

### 9.3 Where web-service vs no-web-service integrations diverge

This is the single most consequential branch in the pipeline [3][10].

| | **No web service (local)** | **Web service (remote)** |
|---|---|---|
| Transport | **stdio** | **Streamable HTTP** |
| Artifact | **`.mcpb` bundle** (one-click install) | public **HTTPS** endpoint |
| Auth | env / OS-keychain (`user_config.sensitive`); **no OAuth** | **OAuth 2.1 + PKCE**, resource-server, audience-bound tokens, no passthrough |
| Hosting | none — runs on the user's machine | self-host (FastMCP `http_app()` ASGI under uvicorn + nginx/Caddy TLS, systemd) **or** serverless (Cloudflare Workers `McpAgent` + Durable Objects + `workers-oauth-provider`; Vercel) |
| Reach | private, per-machine, single-tenant | public — **required** to be a claude.ai/ChatGPT connector; multi-tenant via per-token audience+scope isolation |
| Scaling | per-process | `stateless_http=True` for horizontal scale, or externalize sessions; avoid sticky sessions |
| State / session features | full (local) | sampling/elicitation need session affinity or externalized state |
| Tenancy & secrets | per-user process; secrets in keychain | user-delegated OAuth tokens (short-lived, refresh-rotated); **never** shared API keys passed through |
| Provider-API caller (Anthropic/OpenAI) | n/a | **your orchestrator** runs the OAuth flow, stores + refreshes the bearer token, passes it per-request (OpenAI doesn't persist it; Anthropic takes `authorization_token` per call) — a good fit for a centralized service/facade with `cached_property` + persisted cache |

**Decision rule for the toolkit:**
- **Single-user + touches local resources** (filesystem, local DBs/processes) → ship a **stdio server as `.mcpb`**. Cheapest, most private, spec-recommended default; no hosting, no OAuth [10].
- **Many users, or must be reachable by Claude.ai/ChatGPT cloud** → **host a public Streamable HTTP endpoint over HTTPS with OAuth 2.1**. A VPN-only/private server **cannot** be a hosted connector [3][10].
- **Lowest ops burden** → serverless (Cloudflare `McpAgent` handles sessions + OAuth largely for you), accepting cold starts / platform limits. **Full control / heavy/long-running tools** → self-host behind a reverse proxy; use the **Tasks** utility for long operations instead of holding SSE streams open [1][10].

**Net guidance:** make the **MCP server the canonical artifact**, FastMCP the wrap target, the `.mcpb` packer and Skill/Plugin emitters thin adapters, and the OpenAPI facade + A2A AgentCard optional future neutrality layers. Keep the three conceptual axes (connectivity / procedural-knowledge / packaging) and the two deployment archetypes (local-stdio / remote-HTTP) explicit in both the code and the docs — that discipline is the durable advantage, because it is precisely where the rest of the industry gets confused.

---

## 10. References

1. [Specification & changelog — Model Context Protocol (rev 2025-06-18 / 2025-11-25)](https://modelcontextprotocol.io/specification/2025-11-25/changelog) — primitives, lifecycle, transports, registry, Tasks; TypeScript `schema.ts` as SSOT.
2. [Authorization & Security Best Practices — Model Context Protocol (2025-11-25)](https://modelcontextprotocol.io/specification/2025-11-25/basic/authorization) — OAuth 2.1 resource-server model, RFC 9728/8707, CIMD vs DCR, confused-deputy, token passthrough.
3. [Get started with custom connectors using remote MCP — Claude Help Center](https://support.claude.com/en/articles/11175166-get-started-with-custom-connectors-using-remote-mcp) — custom connector = cloud-reached remote MCP; plans; org controls; OAuth callback.
4. [Desktop Extensions / MCPB — `modelcontextprotocol/mcpb` (MANIFEST.md, CLI.md)](https://github.com/modelcontextprotocol/mcpb) — `.mcpb` format, manifest schema, `server.type`, `user_config`/keychain, signing.
5. [Agent Skills (Overview) — Claude Platform Docs](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview) and [Agent Skills Specification — agentskills.io](https://agentskills.io/specification) — `SKILL.md`, progressive disclosure, open standard, four pre-built doc skills, surfaces, org-wide mgmt.
6. [Create plugins / plugin marketplaces — Claude Code Docs](https://code.claude.com/docs/en/plugins) — plugin layout, `marketplace.json`, sources, versioning, `${CLAUDE_PLUGIN_ROOT}`, `@skills-dir`.
7. [The official Python SDK for MCP](https://github.com/modelcontextprotocol/python-sdk) and [jlowin/fastmcp (standalone FastMCP)](https://github.com/jlowin/fastmcp) — low-level vs FastMCP; `from_openapi`/`from_fastapi`; AuthKit/DCR; deployment.
8. [Cross-system: ChatGPT Apps SDK](https://developers.openai.com/apps-sdk), [Gemini function calling + MCP](https://ai.google.dev/gemini-api/docs/function-calling), [A2A protocol](https://a2a-protocol.org/latest/) — MCP convergence; Gems vs Extensions; AgentCard.
9. [Introducing apps in ChatGPT and the new Apps SDK — OpenAI](https://openai.com/index/introducing-apps-in-chatgpt/) and [MCP Apps compatibility in ChatGPT — OpenAI Developers](https://developers.openai.com/apps-sdk/mcp-apps-in-chatgpt) — Apps = MCP + UI; GPT Actions; `ui/*` over postMessage; plugin deprecation.
10. [Transports (2025-11-25)](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports), [FastMCP HTTP Deployment](https://gofastmcp.com/deployment/http), [Cloudflare remote MCP servers](https://developers.cloudflare.com/agents/guides/remote-mcp-server/), [MCP connector — Claude API](https://platform.claude.com/docs/en/agents-and-tools/mcp-connector) — stdio vs Streamable HTTP; self-host vs serverless; statelessness; provider-API callers.
11. [Architecture overview — Model Context Protocol](https://modelcontextprotocol.io/docs/learn/architecture) — host/client/server roles; control-ownership of tools/resources/prompts.
12. [Introducing the MCP Registry — MCP Blog](https://blog.modelcontextprotocol.io/posts/2025-09-08-mcp-registry-preview/) and [Official MCP Registry](https://registry.modelcontextprotocol.io/) — `server.json`, federation, sub-registries.
13. [Claude Desktop Extensions: One-click MCP server installation — Anthropic Engineering](https://www.anthropic.com/engineering/desktop-extensions) — `.dxt`→`.mcpb` rationale; bundling; runtime model.
14. [Introducing Agent Skills — Anthropic](https://claude.com/blog/skills) and [Skills explained — Anthropic](https://claude.com/blog/skills-explained) — Skills vs MCP/Connectors/Projects/subagents; progressive disclosure.
15. [Provision and manage Skills for your organization — Claude Help Center](https://support.claude.com/en/articles/13119606-provision-and-manage-skills-for-your-organization) — Dec 18 2025 org-wide Skills management (Team/Enterprise); per-user opt-out; audit events.
16. [ChatGPT plugins (2023) — OpenAI](https://openai.com/index/chatgpt-plugins/), [Deprecations — OpenAI](https://developers.openai.com/api/docs/deprecations), [Developers can now submit apps to ChatGPT — OpenAI](https://openai.com/index/developers-can-now-submit-apps-to-chatgpt/) — plugin death; submission/directory opened Dec 17 2025.
17. [Browse skills, connectors, and plugins in one directory — Claude Help Center](https://support.claude.com/en/articles/14328846-browse-skills-connectors-and-plugins-in-one-directory) — unified "Customize" directory (`claude.ai/customize/skills`; plugins at `claude.com/plugins`).
18. [MCP Apps extension — `modelcontextprotocol/ext-apps` (SEP-1865, `io.modelcontextprotocol/ui`)](https://github.com/modelcontextprotocol/ext-apps/blob/main/specification/2026-01-26/apps.mdx) — official standalone extension (not core); `ui/*` JSON-RPC over postMessage.
19. [MCP `schema.ts` (2025-11-25)](https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/schema/2025-11-25/schema.ts) and [JSON-RPC 2.0](https://www.jsonrpc.org/specification) — authoritative protocol definition; JSON Schema 2020-12 default dialect.
20. [Writing effective tools for agents — Anthropic Engineering](https://www.anthropic.com/engineering/writing-tools-for-agents), [SEP-1576: Mitigating Token Bloat in MCP](https://github.com/modelcontextprotocol/modelcontextprotocol/issues/1576), [RAG-MCP — Writer Engineering](https://writer.com/engineering/rag-mcp/), [A Timeline of MCP Security Breaches — AuthZed](https://authzed.com/blog/timeline-mcp-breaches), [MCP prompt injection — Simon Willison](https://simonwillison.net/2025/Apr/9/mcp-prompt-injection/) — over-tooling, tool-description quality, versioning, security/CVEs, lessons from ChatGPT Plugins.

---

## Appendix — Verification notes (corrections to fast-moving claims)

These were independently fact-checked against primary sources during research; the corrected statements are woven into the body above (marked `[*correction*]`).

1. **claude.ai Skills org management** — *Outdated→corrected.* Not "strictly per-user": Anthropic shipped **org-wide Skills management for Team/Enterprise on 2025-12-18** (central provisioning, per-user opt-out, plugin-scoped groups, audit events). Free/Pro remain per-user. [15]
2. **Pre-built Anthropic Skills** — *Refuted→corrected.* The pre-built set is exactly the **four document skills** (pptx/xlsx/docx/pdf). The **Claude API skill is *open-source*, not pre-built**; `anthropics/skills` publishes many more first-party open-source skills. [5]
3. **Unified directory** — *Refuted→corrected.* The unification is real, but the URL is **`claude.ai/customize/skills`** (not `claude.ai/directory`, which 403s) with plugins at **`claude.com/plugins`**; the consolidation tracks to **Feb 24 2026** (Enterprise Agents event), not the widely-echoed "2026-03-31" (unverified, AI-summary contamination). [17]
4. **FastMCP "70% of all MCP servers"** — *Uncertain.* An **unverified self-reported** vendor figure ("some version of FastMCP", folding in the SDK's incorporated high-level API). FastMCP is plausibly the dominant *Python* framework, but the cross-language share is unconfirmable. [7]
5. **ChatGPT Apps SDK distribution** — *Refuted→corrected.* Nov 13 2025 was **preview, not GA**, with **no submission flow/directory yet**; the **submission flow + app directory opened Dec 17 2025**; the only accurate Nov-vs-Dec detail is the **connectors→apps rename (Dec 17 2025)**. Re-verify plan-by-plan GA before committing. [16]
6. **MCP Apps (`ui/*`)** — *Refuted→corrected.* **Not** being upstreamed into core MCP; it is a deliberate **standalone official extension** (SEP-1865, `io.modelcontextprotocol/ui`, repo `modelcontextprotocol/ext-apps`), versioned independently, co-authored by Anthropic+OpenAI+MCP-UI. [18]
