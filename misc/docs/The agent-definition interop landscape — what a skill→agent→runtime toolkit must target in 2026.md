# The agent-definition interop landscape — what a skill→agent→runtime toolkit must target in 2026

*By Thor Whalen — June 4, 2026*

## TL;DR

- **Target three serializations first**: (1) the Anthropic Agent Skills `SKILL.md` open standard (adopted by 32 tools as of March 2026 [27]), (2) the Claude `AgentDefinition`/`.claude/agents/*.md` subagent schema, and (3) MCP server definitions for tools — and realize them on two backends first: the Claude Agent SDK (Python) and a generic OpenAI-Agents-SDK/LiteLLM path, with MCP as the shared tool substrate.
- **Skills, subagents, and MCP are three different primitives**: skills inject progressively-disclosed instructions/scripts into a context window; subagents are separate context windows with their own tools; MCP servers are external tool providers. A `coact`-style toolkit must keep these layers distinct and map them, not conflate them.
- **Multi-agent fan-out costs ~15× the tokens of a single chat** (Anthropic's own figure [21]) and only pays off for high-value, breadth-first, parallelizable work; for tightly-coupled pipelines a single host agent running skills sequentially is both cheaper and more reliable.

## Key Findings

1. Anthropic's subagent surface is now precisely documented and largely stable, but has subtle non-inheritance rules (skills are NOT inherited; tools ARE by default) and a flat topology (subagents cannot spawn subagents) [1].
2. The filesystem (`.claude/agents/*.md`) and programmatic (`AgentDefinition`) forms are near-1:1 but not identical — the programmatic form omits some CLI-only frontmatter fields [1][2].
3. Structured output finally has a native Claude API feature (constrained decoding via `output_format`/strict tools) in addition to the long-standing forced-tool-use pattern; provider-agnostic libraries (instructor, BAML, Outlines, PydanticAI) remain necessary for portability [7][8][28].
4. Every major framework converges on the same minimal agent definition (name + instructions + model + tools) but diverges sharply on orchestration — that divergence is the framework-specific part [9][10][12][13][15].
5. MCP is the genuine lingua franca for tools in 2026 with broad adoption (~97 million monthly SDK downloads by March 2026) and mature adapters across frameworks, though context-cost ergonomics remain a real gap [17][19][20].
6. Skill→agent conversion tooling is immature: format-to-format skill converters exist, but no mature transpiler compiles SKILL.md/subagent defs into LangGraph/CrewAI/ADK runtimes [24][25].

## Details

### 1. Anthropic's agent-definition surface, precisely

**Subagent frontmatter (file-based `.claude/agents/*.md` and `--agents` JSON).** The full set of frontmatter fields is: `description`, `prompt`, `tools`, `disallowedTools`, `model`, `permissionMode`, `mcpServers`, `hooks`, `maxTurns`, `skills`, `initialPrompt`, `memory`, `effort`, `background`, `isolation`, and `color` [1]. Only `name` and `description` are required; `prompt` corresponds to the markdown body in file-based definitions. The `tools` field is an *allowlist* — specify it and the subagent can use only those tools; omit it and it inherits all tools. `disallowedTools` is a denylist subtracted from whatever the subagent would otherwise have [1].

**Programmatic `AgentDefinition` (Agent SDK).** In Python the dataclass is:

```python
@dataclass
class AgentDefinition:
    description: str
    prompt: str
    tools: list[str] | None = None
    model: Literal["sonnet", "opus", "haiku", "inherit"] | None = None
    skills: list[str] | None = None
    memory: Literal["user", "project", "local"] | None = None
    mcpServers: list[str | dict[str, Any]] | None = None
```

The TypeScript type is:

```typescript
type AgentDefinition = {
  description: string;
  tools?: string[];
  disallowedTools?: string[];
  prompt: string;
  model?: "sonnet" | "opus" | "haiku" | "inherit";
  mcpServers?: AgentMcpServerSpec[];
  skills?: string[];
  maxTurns?: number;
  criticalSystemReminder_EXPERIMENTAL?: string;
};
```

Note the camelCase convention in `AgentDefinition` (`disallowedTools`, `mcpServers`) maps directly to the TypeScript wire format, and differs from `ClaudeAgentOptions`, which uses Python snake_case (`disallowed_tools`, `mcp_servers`). Passing a snake_case keyword to `AgentDefinition` raises a TypeError [2].

**File vs. programmatic — not quite 1:1.** The filesystem frontmatter is a superset: it carries CLI-runtime fields like `permissionMode`, `hooks`, `initialPrompt`, `effort`, `background`, `isolation`, and `color` that the minimal programmatic `AgentDefinition` does not expose [1][2]. Plugin subagents specifically do NOT support `hooks`, `mcpServers`, or `permissionMode` [1]. So a converter should treat the file frontmatter as the richer source format and the `AgentDefinition` dataclass as a lossy projection.

**Inheritance rules (critical for a converter).** A subagent runs in its own fresh context window with its own system prompt. It inherits **tools** by default (restrictable via `tools`/`disallowedTools`). It does **NOT** inherit **skills** — these must be declared explicitly in the `skills` frontmatter field, whereupon the *full content* of each named skill is injected into the subagent's context at startup ("preloaded skills") [1]. **Memory** is opt-in via the `memory` field. There is a documented bug where the frontmatter `model:` field is sometimes ignored and the subagent inherits the parent model unless the model is explicitly passed on the Agent tool call.

**Topology and limits.** Subagents are flat: a subagent **cannot spawn other subagents** (the Task tool returns nothing inside a subagent) — this is by design [1]. Parallelism caps at around 10 concurrent tasks, executing in batches (additional tasks queue; the next batch starts only after the current batch completes); on lower API tiers concurrency is effectively lower (~5). Agent Teams (experimental, gated behind `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS`) and a fork mode (`CLAUDE_CODE_FORK_SUBAGENT=1`) extend these patterns [1]. Running ten agents in parallel uses quota roughly ten times as fast.

**Agent Skills loading mechanics.** A skill is a directory with a `SKILL.md` file: YAML frontmatter (required `name` ≤64 chars lowercase+hyphens; required `description` ≤1024 chars; optional `license`, `compatibility`, `metadata`, and experimental `allowed-tools`) plus a Markdown body [4][6]. Loading is three-tier progressive disclosure: (1) at startup only name+description of every skill load into the system prompt (~100 tokens/skill); (2) when a skill is judged relevant, the full SKILL.md body loads (recommended <500 lines / <5k tokens); (3) bundled files in `scripts/`, `references/`, `assets/` load only when referenced, and scripts can be executed via Bash without their contents entering context [4][6]. Released as an open standard on December 18, 2025 (published at agentskills.io), it had been **adopted by 32 tools as of March 2026 — including Anthropic (Claude Code), OpenAI (Codex, ChatGPT), Microsoft (VS Code/Copilot), Google (Gemini CLI), JetBrains (Junie), AWS (Kiro), Block (Goose), Sourcegraph (Amp), Snowflake, Databricks, ByteDance (TRAE), and Mistral AI** [27].

**Mental model (the key distinction a toolkit must encode):**
- **Skills** = progressively-disclosed instructions + scripts injected into a context window; model-invoked; enabled by adding `"Skill"` to `allowed_tools` [5][8].
- **Subagents** = separate context windows with their own prompt/tools/permissions; return a summary to the parent [1].
- **MCP** = external tool servers consumed over a protocol [17].

### 2. Structured output / return contracts

**Native Claude structured outputs (newer).** Anthropic shipped structured outputs in public beta on November 14, 2025 (beta header `structured-outputs-2025-11-13`), now generally available across Claude Opus 4.5/4.6/4.7/4.8, Sonnet 4.5/4.6, and Haiku 4.5 [7]. Two modes: (1) **JSON outputs** via `output_config`/`output_format` with a `json_schema` constrains the final response; (2) **strict tool use** via `"strict": True` on a tool definition guarantees tool inputs match schema. Both use **constrained decoding** — the schema is compiled into a grammar that restricts token generation. They can be combined. Known incompatibilities: structured outputs don't work with citations (returns 400) or with JSON-output prefilling [7].

**Forced tool use (the long-standing pattern).** Define a tool with an `input_schema`, then force it with `tool_choice={"type": "tool", "name": "..."}`. The `tool_use` block's `input` is already a dict. This still works on older models and remains necessary when using extended thinking [7].

**Agent SDK structured outputs.** Pass a JSON Schema to `query()` via `outputFormat` (TS) / `output_format` (Python); the result message includes a `structured_output` field with validated data, and the SDK re-prompts on mismatch up to a retry limit (error if still failing). Pydantic models can be passed directly and `response.parsed_output` returns a typed instance [8].

**Recommended subagent return contract.** Because a Claude subagent returns a free-text summary to its parent, the robust pattern is: give the subagent (a) a system-prompt instruction to return a specific structure and (b) a structured-output schema (or a forced "return_result" tool) so the parent — or a `coact` realization layer — can parse it deterministically. The Anthropic multi-agent research system uses an analogous "artifact" pattern: subagents write findings to a shared filesystem and return lightweight references rather than dumping everything through chat [21].

**Provider-agnostic patterns.** OpenAI has native `response_format`/strict schema mode; Gemini supports `response_mime_type` + `response_json_schema`; open models use constrained decoding (Outlines/XGrammar — the latter is the default constrained-decoding backend for vLLM, SGLang, and TensorRT-LLM, masking invalid tokens during generation). Cross-provider libraries:
- **instructor** — Pydantic-based, patches the client, automatic validation+retry, broad provider support; best default for portability [28].
- **Outlines** — FSM/grammar-based constrained generation; strongest for high-volume local-model extraction.
- **BAML** — a DSL with a Rust compiler generating typed clients across languages; "Schema Aligned Parsing" recovers structured data from malformed output; best when one schema must serve Python+TS and parsing reliability is paramount [28].
- **PydanticAI** — agent framework with structured output + reflection-based retry built in.
- **Marvin** — decorator-based Python functions with Pydantic return types.

For `coact`, the cleanest abstraction is a `structured(prompt, schema) -> model` call that internally selects native structured output where available and falls back to forced-tool-use or instructor-style retry otherwise.

### 3. Cross-framework agent definitions

| Framework | Single-agent definition fields | Topology / control-flow | Capability vs. orchestration |
|---|---|---|---|
| **Claude Agent SDK** | `description`, `prompt`, `tools`, `model`, `skills`, `memory`, `mcpServers` | Flat orchestrator→subagents via Agent/Task tool; no nesting | Mostly separated (definition is data; orchestration is the agent loop) |
| **LangGraph** | Node functions + typed `State` schema (TypedDict/Pydantic) with reducers | Explicit graph: nodes + normal/conditional edges, cycles, `interrupt()`, checkpointers | Entangled — the agent IS the graph; orchestration is first-class |
| **CrewAI** | `Agent(role, goal, backstory, tools, llm, allow_delegation)` | `Crew(agents, tasks, process=)`; `Process.sequential`/`hierarchical` (manager agent); `Task(description, expected_output, agent, context, output schema)` | Partly separated — agents are declarative; orchestration is the process + tasks |
| **OpenAI Agents SDK** | `Agent(name, instructions, model, tools, handoffs, guardrails, output_type)` | `handoffs` (transfer control; tool `transfer_to_<agent>`), agents-as-tools, `Runner` loop, subagents (beta, Apr 2026), sandbox agents | Cleanest separation — small primitive set, orchestration in plain code |
| **Google ADK** | `LlmAgent(name, model, instruction, description, tools, sub_agents, output_schema, output_key)` | Workflow agents `SequentialAgent`/`ParallelAgent`/`LoopAgent`; LLM-driven delegation via `sub_agents`; `AgentTool`; single-parent hierarchy; shared `session.state` | Explicit separation — capability agents vs. workflow/orchestration agents |
| **AutoGen / AG2** | `AssistantAgent(name, system_message, description, model_client, tools)`; `UserProxyAgent` | `GroupChat` + `GroupChatManager` (speaker selection: auto/round-robin), nested chats, swarm (`after_work`), `max_round` | Entangled — conversation-driven; orchestration is the chat pattern |

(Sources: Claude SDK [2][3]; LangGraph [9]; CrewAI [12]; OpenAI Agents SDK [10][11]; Google ADK [13][14]; AutoGen/AG2 [15][16].)

**What's portable vs. framework-specific.** Portable across all six: the **capability core** — a name/identifier, a system prompt (instructions), a model selector, a tool list, and (increasingly) a structured output type. This maps cleanly to a `coact` canonical agent definition. **Framework-specific** (NOT cleanly portable): the orchestration/topology layer — LangGraph's edges and state reducers, CrewAI's process+tasks, OpenAI's handoffs, ADK's workflow-agent wrappers, AutoGen's group-chat speaker selection. Anthropic's own OpenAI-Agents-SDK migration guide is a *manual* mapping (e.g., `@function_tool`→`@tool`, `Agent`→`ClaudeAgentOptions`, `Runner.run`→`ClaudeSDKClient`), which underscores that there is no automatic transpiler.

The practical design implication: `coact` should serialize the **capability core** as the portable unit and treat orchestration as backend-specific *realization strategies*, not as something to round-trip.

### 4. MCP as an interop substrate

**Exposing Python tools.** The dominant pattern is **FastMCP** (incorporated into the official `mcp` Python SDK as v1.0, now maintained as a standalone project at v3.x) [17][18]. The decorator API is minimal:

```python
from fastmcp import FastMCP
mcp = FastMCP("Demo")

@mcp.tool
def add(a: int, b: int) -> int:
    """Add two numbers"""
    return a + b

if __name__ == "__main__":
    mcp.run()
```

`@mcp.tool`, `@mcp.resource`, and `@mcp.prompt` auto-generate JSON schemas from type hints; transports include stdio, Streamable HTTP, and SSE [17]. FastMCP reportedly powers a large share of MCP servers across languages. Use the raw official SDK (`modelcontextprotocol/python-sdk`) when you need wire-level control; use FastAPI-MCP to wrap an existing FastAPI app [18]. The Claude Agent SDK additionally offers in-process SDK MCP servers via `@tool` + `create_sdk_mcp_server` (no subprocess) [2].

**Consumption across hosts.** Claude Code and the Claude Agent SDK are MCP-native (pass `mcp_servers`/`mcpServers`; subagents reference servers by name or inline config) [2]. Every framework in §3 consumes MCP: LangGraph/LangChain via **`langchain-mcp-adapters`** (`MultiServerMCPClient`, stateless per-call sessions by default, structured content surfaced as artifacts) [19][23]; OpenAI Agents SDK has built-in MCP tool calling; AutoGen via `McpWorkbench`/`StdioServerParams` [16]; CrewAI and others via **`mcpadapt`** (a multi-framework adapter for smolagents, CrewAI, LangChain, google-genai) [20].

**Maturity in 2026.** MCP is the de-facto standard for cross-host tool reuse: **the Python and TypeScript SDKs alone saw roughly 97 million monthly downloads by March 2026**, and the official MCP Registry grew to nearly 2,000 entries within months of its September 2025 launch — while the wider ecosystem is far larger, with PulseMCP indexing 15,930+ servers and Smithery ~7,300. Known gaps are real and quantified: **context bloat** is the headline one — Apideck reported three MCP servers (GitHub, Slack, Sentry) consuming 143,000 of a 200,000-token window: *"That's 72% of the context window burned on tool definitions. The agent had 57,000 tokens left for the actual conversation, retrieved documents, reasoning, and response."* A Scalekit benchmark (75 head-to-head runs on Claude Sonnet 4) found MCP cost 4–32× more tokens than a CLI, with a simple repo-language check consuming 1,365 tokens via CLI vs 44,026 via MCP, *"of which the agent uses one or two"* of 43 injected tool definitions. **Auth** is the #1 operational pain point past local demos, and tool-result payloads can be oversized. For `coact`, MCP is the right substrate for the tool layer, but the toolkit should support **selective tool loading** to manage context cost.

### 5. The multi-agent cost question

**The headline multiplier.** Anthropic's engineering write-up on its multi-agent research system is the primary source. Verbatim: *"agents typically use about 4× more tokens than chat interactions, and multi-agent systems use about 15× more tokens than chats"* [21]. On their internal research eval, *"a multi-agent system with Claude Opus 4 as the lead agent and Claude Sonnet 4 subagents outperformed single-agent Claude Opus 4 by 90.2% on our internal research eval"* [21]. Critically, *"three factors explained 95% of the performance variance in the BrowseComp evaluation... token usage by itself explains 80% of the variance, with the number of tool calls and the model choice as the two other explanatory factors"* — i.e., "multi-agent works mainly because it spends enough tokens to solve the problem" [21].

**Dependence on task interdependence.** Anthropic is explicit about the boundary: *"domains that require all agents to share the same context or involve many dependencies between agents are not a good fit for multi-agent systems today"* [21]. The 15× premium buys parallelism only when work is breadth-first and decomposes into independent directions (legal due diligence, competitive intelligence, literature review). For coding and other tightly-coupled, context-sharing-heavy pipelines, the multiplier is paid without the benefit.

**The countervailing view.** Cognition's "Don't Build Multi-Agents" essay (Walden Yan, June 2025) argues parallel sub-agents are fragile because of context isolation: sub-agents make conflicting implicit decisions without a shared trace (the "Flappy Bird" example — one sub-agent builds a Mario-style background while another builds a non-matching bird) [22]. Their principles: agents must share full context including complete traces, and every action carries implicit decisions that can conflict. The two camps are actually aligned: single-threaded for deep/narrow coherence-critical work; multi-agent for breadth-first parallelizable work.

**Decision heuristics for `coact` (skill set → fleet vs. single host).** Convert skills into a fleet of running agents when: (a) sub-tasks are *independent* (no sub-agent needs another's output), (b) the combined information *exceeds a single context window*, (c) the task is *breadth-first* (many sources to explore in parallel), and (d) the *task value justifies* a 15× token spend. Prefer a single host agent running the skills sequentially when: tasks are interdependent, decisions must stay coherent (coding, long-form writing), the work fits one context window, latency/cost matters more than wall-clock parallelism, or the steps form a tightly-coupled pipeline. Concrete guardrails the toolkit should enforce: cap concurrency (≤4–6 is a common practical sweet spot below the ~10 hard cap), forbid recursive sub-agent spawning by default, set per-run token/budget ceilings, and route cheap sub-tasks to Haiku-class models while reserving Opus for the orchestrator.

### 6. Existing skill→agent / definition-conversion tooling

The honest finding: **this space is immature and fragmented**, which is precisely the gap `coact` addresses.

**Category A — SKILL.md → MCP / non-Claude runtimes (most mature).** Several real, installable tools exist: `agent-skills-mcp-rs` (DiscreteTom; a Rust MCP server that scans a folder for SKILL.md files and exposes them either as system-prompt injections or as MCP tools); `agentskills-mcp` / `mcp-agentskills` (zouyingcao; the most faithful re-implementation of Anthropic's progressive-disclosure model for any MCP client, exposing load-metadata / load-skill / read-reference / run-shell tools); a Rust "Skill Engine" with WASM sandboxing and MCP server mode; and **FastMCP's Skills Provider** (v3.0+) which exposes platform skill directories as MCP resources with `list_skills`/`download_skill`/`sync_skills` utilities [17]. The need here is also shrinking because SKILL.md became a cross-tool standard natively read by 32 runtimes [27].

**Category B — declarative spec → multi-backend running agent (emerging/fragmented).** Dedicated projects exist but each stops short. `open-agent-spec` (prime-vector; a YAML standard + `oa` CLI that runs specs across LLM engines and MCP/native/custom tools) deliberately has **no branching/loops/conditionals** — `depends_on` is a data contract, not control flow, and "backends" means LLM engines, not frameworks. Oracle's `agent-spec`/`pyagentspec` (backed by an arXiv report) models agents AND graph workflows with validation and round-trip serialization, but its **runtime adapters for frameworks like LangGraph are roadmap, not finished**. **BAML** is a mature compiler but compiles *prompts/functions*, not whole-agent specs, and is unrelated to SKILL.md.

**Category C — SKILL.md ⇄ subagent ⇄ LangGraph/CrewAI/OpenAI/ADK transpiler (largely absent).** Only format-to-format converters for coding-assistant configs exist: `himmelreich-it/agent-skill-converter` (Claude → Mistral Vibe / Copilot, via LLM-followed mapping tables), `alirezarezvani/claude-skills` (a `convert.sh --tool` across ~13 tools), `FrancyJGLisboa/agent-skill-creator` (emits SKILL.md + AGENTS.md + per-tool adapters across 17 platforms) [25], and `shinpr/sub-agents-skills` (an Agent Skill that routes `.agents/*.md` definitions to Codex/Claude/Cursor/Gemini CLIs — cross-LLM orchestration, but by shelling out, not transpiling) [24]. A tool ("GitAgent") claiming true spec→LangGraph/CrewAI/AutoGen export appears in one promotional-leaning article but **could not be independently verified** and should be treated as an unconfirmed lead. The structural reason clean transpilation is hard: Claude subagents are "single-agent-with-tools," not graph nodes, so they don't map cleanly onto LangGraph/CrewAI runtimes.

**What they do well / where they stop:** the skill-library + installer tools (agent-skill-creator, claude-skills) do cross-*config* portability well but never touch programmatic frameworks; the MCP-wrapper tools faithfully expose skills to non-Claude runtimes but don't realize them as autonomous running agents; the spec languages (open-agent-spec, pyagentspec) define portable specs well but punt on multi-framework execution. **No existing tool does the full `coact` arc: SKILL.md (+ scripts) → canonical agent definition → realized running agent across multiple execution backends.**

## Recommendations

**Stage 1 — serializations to target first (build these in order):**
1. **`SKILL.md` ingestion** (the open standard, with three-tier progressive disclosure and `scripts/`/`references/`/`assets/` bundling). This is the input format and the most stable, widely-adopted surface [4][27].
2. **A canonical `coact` agent definition** = the portable capability core: `name`, `description`, `instructions/prompt`, `model`, `tools`, `structured_output_schema`, `skills`, `mcp_servers`. Make it a lossless superset of Anthropic's `AgentDefinition` and round-trippable to `.claude/agents/*.md` frontmatter [1][2].
3. **MCP server definitions** for the tool layer (consume via FastMCP-generated servers; expose `coact`'s own tools the same way) [17].

**Stage 2 — realization (execution) backends to target first:**
1. **Claude Agent SDK (Python)** — first-class because it natively understands skills, subagents, MCP, and structured outputs; the impedance mismatch is lowest. This is the reference backend [2][8].
2. **OpenAI Agents SDK + LiteLLM** (provider-agnostic) — gives breadth (100+ models), clean `Agent(instructions, tools, handoffs, output_type)` mapping, and MCP support. This validates that the canonical definition is genuinely portable [10].
3. **A "single host agent runs skills sequentially" local backend** — the cheap default that avoids the 15× multiplier; should be the out-of-the-box realization unless the user opts into fan-out [21].

**Defer**: LangGraph, CrewAI, ADK, and AutoGen realizers until the canonical definition is proven on the two SDKs above. When added, treat their orchestration layers as backend-specific realization strategies — do NOT try to round-trip graph/crew/group-chat topology through the canonical format.

**Cross-cutting:** implement `structured(prompt, schema) -> model` with native-structured-output-first / forced-tool-use fallback; enforce concurrency caps, no-recursive-spawn, and per-run budget ceilings by default; support selective MCP tool loading to control context bloat.

## Caveats — most volatile interface assumptions to revisit in 6 months

1. **The `AgentDefinition` schema is actively expanding.** Fields like `criticalSystemReminder_EXPERIMENTAL`, the `effort`/`xhigh` levels, and Agent Teams / fork mode are experimental and version-gated. The frontmatter `model:` bug means model routing semantics may change. Re-verify field-by-field against the Python and TS SDK references each release [2][3].
2. **Native structured outputs are new (Nov 2025 beta → GA across some models).** Model coverage, the beta header lifecycle, and incompatibilities (citations, prefilling, extended-thinking + forced tools) are in flux. Don't hard-code the beta header [7].
3. **Subagent topology limits may loosen.** "No subagent-spawning-subagents" and the ~10 concurrency cap are current engineering constraints, not laws; Agent Teams is an early attempt to relax them. A toolkit that hard-codes flat topology may need to adapt [1].
4. **The Agent Skills standard is <1 year old** (Dec 18, 2025) and adoption is exploding (32 tools by March 2026); the spec (especially `allowed-tools`, still experimental) and cross-tool compatibility edge cases will move [4][27].
5. **MCP context-cost ergonomics and auth are unsettled.** Selective tool loading, gateways, and OAuth patterns are evolving; the per-call-vs-persistent session model in adapters differs and may converge [19][23].
6. **OpenAI Agents SDK is moving fast** (subagents beta + sandbox agents added April 2026; frequent releases). Its primitive set could shift, affecting the second realization backend [10].
7. **No spec→framework transpiler exists yet** — but Category B/C projects (open-agent-spec, pyagentspec, possibly GitAgent) are racing to build one. Revisit whether a third party has solved multi-backend realization before over-investing in `coact`'s own realizer breadth.

## References

[1] [Create custom subagents — Claude Code Docs](https://code.claude.com/docs/en/sub-agents)
[2] [Agent SDK reference — Python — Claude API Docs](https://platform.claude.com/docs/en/agent-sdk/python)
[3] [Agent SDK reference — TypeScript — Claude API Docs](https://platform.claude.com/docs/en/agent-sdk/typescript)
[4] [Equipping agents for the real world with Agent Skills — Anthropic](https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills)
[5] [Agent Skills — Claude API Docs](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview)
[6] [Skill authoring best practices — Claude API Docs](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices)
[7] [Structured outputs — Claude API Docs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs)
[8] [Get structured output from agents — Claude Code Docs](https://code.claude.com/docs/en/agent-sdk/structured-outputs)
[9] [Graph API overview — Docs by LangChain](https://docs.langchain.com/oss/python/langgraph/graph-api)
[10] [Agents — OpenAI Agents SDK](https://openai.github.io/openai-agents-python/agents/)
[11] [Handoffs — OpenAI Agents SDK](https://openai.github.io/openai-agents-python/handoffs/)
[12] [Hierarchical Process — CrewAI](https://docs.crewai.com/en/learn/hierarchical-process)
[13] [Simple agents — Agent Development Kit (ADK)](https://google.github.io/adk-docs/agents/llm-agents/)
[14] [Custom template workflows — Agent Development Kit (ADK)](https://google.github.io/adk-docs/agents/custom-agents/)
[15] [GroupChat — AG2](https://docs.ag2.ai/latest/docs/user-guide/advanced-concepts/groupchat/groupchat/)
[16] [GitHub — microsoft/autogen](https://github.com/microsoft/autogen)
[17] [Welcome to FastMCP](https://gofastmcp.com/getting-started/welcome)
[18] [GitHub — modelcontextprotocol/python-sdk](https://github.com/modelcontextprotocol/python-sdk)
[19] [GitHub — langchain-ai/langchain-mcp-adapters](https://github.com/langchain-ai/langchain-mcp-adapters)
[20] [MCP Adapt](https://grll.github.io/mcpadapt/)
[21] [How we built our multi-agent research system — Anthropic](https://www.anthropic.com/engineering/multi-agent-research-system)
[22] [Don't Build Multi-Agents — Cognition (Hacker News discussion)](https://news.ycombinator.com/item?id=45096962)
[23] [Model Context Protocol (MCP) — Docs by LangChain](https://docs.langchain.com/oss/python/langchain/mcp)
[24] [GitHub — shinpr/sub-agents-skills](https://github.com/shinpr/sub-agents-skills)
[25] [GitHub — FrancyJGLisboa/agent-skill-creator](https://github.com/FrancyJGLisboa/agent-skill-creator)
[26] [GitHub — agentskills/agentskills](https://github.com/agentskills/agentskills)
[27] [Agent Skills Open Standard Explained — Paperclipped (interoperability guide, 2026)](https://www.paperclipped.de/en/blog/agent-skills-open-standard-interoperability/)
[28] [BAML vs Instructor: Structured LLM Outputs — Rost Glukhov](https://www.glukhov.org/post/2025/12/baml-vs-instruct-for-structured-output-llm-in-python/)

---

*Note on deliverable format: This report is provided as Markdown text ready to be saved as a `.md` file (suggested filename: `agent-definition-interop-landscape-2026.md`). To produce the downloadable file, copy the content above verbatim into a file with the `.md` extension.*