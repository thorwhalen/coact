# coact

coact — reuse your AI stuff across the layers of the modern agent stack.

`coact` (“co-act”: skills and agents acting as one reusable substrate) owns the
two transitions the rest of the ecosystem doesn’t:

```default
python functions/scripts  →  .claude/skills/  →  .claude/agents/  →  running agents
        (py2mcp, aw)            (skill pkg)         COMPLETE (coact)    REALIZE (coact)
```

- **COMPLETE** lifts `.claude/skills/` into `.claude/agents/` definitions,
  adding the agent-only “extras” (persona, return contract, tool allowlist,
  model, memory).
- **REALIZE** turns a completed definition into an actually running agent,
  picking an execution backend (host agent / Agent SDK / MCP-exposed).

It is glue over `skill` (foundation), `aw` (runtime substrate), and
`py2mcp` (tool exposure) — see `misc/docs/REUSE.md`.

Simple usage:

```default
from coact import complete, emit_agent, realize

agent = complete('.claude/skills/ux-analyst')      # Skill -> AgentDefinition
emit_agent(agent, 'claude-agents-md', dest='.claude/agents/')
realize(agent, backend='host')                     # materialize for Claude Code
```

### Functions

| [`complete`](#coact.complete)(source, \*[, policy, llm])                | Complete a skill into an [`AgentDefinition`](#coact.AgentDefinition) (the plan's agent).                   |
|-----------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------|
| [`plan_completion`](#coact.plan_completion)(source, \*[, policy, llm])         | Plan the skill→agent completion, recording the provenance of every field.                                                       |
| [`realize`](#coact.realize)(target, \*[, backend])                     | Realize an agent (or skill, or list) via the named backend.                                                                     |
| [`realize_host`](#coact.realize_host)(target, \*[, scope, dest, ...])       | Materialize agents (+ linked skills) so the host agent runs them.                                                               |
| [`realize_sdk`](#coact.realize_sdk)(target, \*[, llm, runner, ...])        | Realize a single agent as a runnable [`RunnableAgent`](#coact.RunnableAgent) (aw-compatible).            |
| [`realize_mcp`](#coact.realize_mcp)(target, \*[, name, input_trans])       | Expose a skill's declared Python tools as a FastMCP server (foreign-host).                                                      |
| [`realize_litellm`](#coact.realize_litellm)(target, \*[, model_map, ...])      | Realize one agent as a provider-agnostic [`RunnableLLMAgent`](#coact.RunnableLLMAgent) (via LiteLLM).       |
| [`realize_langgraph`](#coact.realize_langgraph)(target, \*[, model_map, ...])    | Realize one agent as a LangGraph-backed [`RunnableLLMGraphAgent`](#coact.RunnableLLMGraphAgent) (aw-compatible). |
| [`realize_crewai`](#coact.realize_crewai)(target, \*[, model_map, ...])       | Realize one agent as a CrewAI-backed [`RunnableCrewAIAgent`](#coact.RunnableCrewAIAgent) (aw-compatible).      |
| [`integration_spec_from`](#coact.integration_spec_from)(source, \*[, name, ...])     | Coerce a capability source into an [`IntegrationSpec`](#coact.IntegrationSpec).                            |
| [`integration_spec_from_description`](#coact.integration_spec_from_description)(description, \*) | Refine a natural-language `description` into a **draft** IntegrationSpec.                                                       |
| [`publish`](#coact.publish)(source, \*[, target, dry_run])             | Publish a capability to a chatbot host via the named target.                                                                    |
| [`publish_targets`](#coact.publish_targets)()                                  | The names of all registered publish targets.                                                                                    |
| [`publish_mcpb`](#coact.publish_mcpb)(source, \*[, dest, dry_run, ...])     | Bundle `source` into a Claude Desktop `.mcpb` extension.                                                                        |
| [`publish_remote`](#coact.publish_remote)(source, \*[, dest, dry_run, ...])   | Scaffold a remote Claude connector (Streamable-HTTP MCP server + OAuth 2.1).                                                    |
| [`scaffold_fleet`](#coact.scaffold_fleet)(target, \*[, dest, ...])            | Emit a starter shim wiring the target agents as a runnable `sdk` fleet.                                                         |
| [`synthesize_persona`](#coact.synthesize_persona)(skill, \*, return_contract)     | Synthesize the system prompt (persona) for an agent derived from `skill`.                                                       |
| [`synthesize_return_contract`](#coact.synthesize_return_contract)(skill, \*, coact_meta)  | Choose the agent's return contract: author-pinned, else a template default.                                                     |
| [`resolve_llm`](#coact.resolve_llm)([llm])                                 | Resolve `llm` to a `callable(str) -> str`, or `None` if unavailable.                                                            |
| [`structured`](#coact.structured)(prompt, schema, \*[, llm, retries])     | Best-effort schema-conforming dict from an LLM, or `None` if unavailable.                                                       |
| [`emit_agent`](#coact.emit_agent)(ad[, target, dest])                     | Emit an agent to a registered target; optionally write a file target to `dest`.                                                 |
| [`to_claude_agent_md`](#coact.to_claude_agent_md)(ad)                             | Serialize an agent to `.claude/agents/<name>.md` content.                                                                       |
| [`from_claude_agent_md`](#coact.from_claude_agent_md)(text)                         | Parse `.claude/agents/*.md` content back into an [`AgentDefinition`](#coact.AgentDefinition).              |
| [`to_aw_agent_spec`](#coact.to_aw_agent_spec)(ad)                               | Adapt an [`AgentDefinition`](#coact.AgentDefinition) to an `aw.translators.AgentSpec`.                     |
| [`diff`](#coact.diff)(skill, agent)                                 | Show what extras `agent` adds over its source `skill`.                                                                          |
| [`estimate`](#coact.estimate)(agents)                                   | Surface the fan-out cost tradeoff for an agent set (DECISIONS D9).                                                              |
| [`inventory`](#coact.inventory)([project])                               | Enumerate skills, derived agents, and MCP-exposed tools in a project.                                                           |
| [`back`](#coact.back)(agent)                                        | Best-effort, **lossy** agent→skill extraction (harvest an agent into a skill).                                                  |
| [`parse_coact_meta`](#coact.parse_coact_meta)(source)                           | Parse a [`CoactMeta`](#coact.CoactMeta) from a SKILL.md path/text/`Skill`/frontmatter dict.          |
| [`validate_coact_block`](#coact.validate_coact_block)(skill_or_meta)                | Validate a `coact:` block, returning issue strings (empty = valid/absent).                                                      |
| [`register_validator`](#coact.register_validator)()                               | Register the coact-block validator into `skill.create.validators` (idempotent).                                                 |
| [`agents_dir`](#coact.agents_dir)(\*[, scope, project_dir])               | Resolve the `.claude/agents` directory for the given scope.                                                                     |

### Classes

| [`AgentDefinition`](#coact.AgentDefinition)(name, description[, prompt, ...])   | The SSOT: one object, two serializations (filesystem md + SDK form).                                                     |
|------------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------|
| [`AgentPlan`](#coact.AgentPlan)(agent[, provenance, warnings])            | The inspectable result of `plan_completion`: the agent + its provenance.                                                 |
| [`FieldProvenance`](#coact.FieldProvenance)(field, value, source[, note])       | Where one [`AgentDefinition`](#coact.AgentDefinition) field's value came from (dry-run audit).      |
| [`ReturnContract`](#coact.ReturnContract)([json_schema, ref, description])     | The agent's return contract: its final-message schema + a human summary.                                                 |
| [`CompletionPolicy`](#coact.CompletionPolicy)([default_model, ...])              | Injectable defaults for the §3.2 extras COMPLETE must stamp on a skill.                                                  |
| [`RealizedHost`](#coact.RealizedHost)([agents, skills, agents_dir, ...])     | The materialized result of host realization (files the host will discover).                                              |
| [`RunnableAgent`](#coact.RunnableAgent)(agent_def[, llm, runner, ...])        | An `aw.AgenticStep`-compatible runnable backed by the Claude Agent SDK.                                                  |
| [`RunnableLLMAgent`](#coact.RunnableLLMAgent)(agent_def[, model_map, ...])       | An `aw.AgenticStep`-compatible runnable backed by LiteLLM (any provider).                                                |
| [`RunnableLLMGraphAgent`](#coact.RunnableLLMGraphAgent)(agent_def[, ...])             | An `aw.AgenticStep`-compatible runnable backed by a LangGraph graph.                                                     |
| [`RunnableCrewAIAgent`](#coact.RunnableCrewAIAgent)(agent_def[, model_map, ...])    | An `aw.AgenticStep`-compatible runnable backed by a single `crewai.Agent`.                                               |
| [`IntegrationSpec`](#coact.IntegrationSpec)(name[, description, ...])           | Target-neutral description of an integration to publish.                                                                 |
| [`ToolSpec`](#coact.ToolSpec)(name[, description, input_schema, ...])    | A richer, target-neutral description of one tool in an [`IntegrationSpec`](#coact.IntegrationSpec). |
| [`PublishResult`](#coact.PublishResult)(target[, dry_run, artifact, ...])     | The outcome of [`publish()`](#coact.publish) — what was (or *would be*) produced.           |
| [`CoactMeta`](#coact.CoactMeta)([tools, disallowed_tools, model, ...])    | The parsed `coact:` block (every field optional; all default to absent).                                                 |
| [`AgentStore`](#coact.AgentStore)([root, scope, project_dir])              | A `MutableMapping[str, AgentDefinition]` over a `.claude/agents/` dir.                                                   |

### *class* coact.AgentDefinition(name, description, prompt='', tools=None, disallowed_tools=list(), model=None, skills=list(), memory=None, mcp_servers=list(), permission_mode=None, returns=ReturnContract(), consumes=None, source_skill=None)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

The SSOT: one object, two serializations (filesystem md + SDK form).

Fields mirror the host subagent schema (snake_case here; coact owns the
mapping to the host’s camelCase frontmatter names in [`coact.emit`](coact.emit.html.md#module-coact.emit)),
plus the coact-specific `returns` / `consumes`. `tools=None`
means *inherit all tools*; an empty list means *no tools* — the distinction
is preserved.

```pycon
>>> ad = AgentDefinition(name='ux-analyst', description='Analyze UX bundles.')
>>> ad.name, ad.tools, ad.returns.is_empty()
('ux-analyst', None, True)
```

#### source_skill *: [Optional](https://docs.python.org/3/library/typing.html#typing.Optional)[[str](https://docs.python.org/3/builtins/stdtypes.html#str)]* *= None*

Canonical key/name of the source skill this agent was completed from.

### *class* coact.AgentPlan(agent, provenance=list(), warnings=list())

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

The inspectable result of `plan_completion`: the agent + its provenance.

Shows the proposed [`AgentDefinition`](#coact.AgentDefinition) and, for each field, *why* it has
its value — so a user can review before any file is written or agent spawned
(progressive disclosure: dry-run first).

#### render()

Render a human-readable provenance table for terminal display.

```pycon
>>> plan = AgentPlan(
...     agent=AgentDefinition(name='x', description='y'),
...     provenance=[FieldProvenance('model', 'sonnet', 'policy', 'worker')],
... )
>>> 'model' in plan.render() and 'policy' in plan.render()
True
```

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### *class* coact.AgentStore(root=None, , scope='project', project_dir=None)

Bases: [`MutableMapping`](https://docs.python.org/3/library/collections.abc.html#collections.abc.MutableMapping)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`AgentDefinition`](coact.base.html.md#coact.base.AgentDefinition)]

A `MutableMapping[str, AgentDefinition]` over a `.claude/agents/` dir.

Keys are agent names; each agent is one `<name>.md` file.

```pycon
>>> import tempfile
>>> from coact.base import AgentDefinition
>>> store = AgentStore(root=tempfile.mkdtemp())
>>> store['ux'] = AgentDefinition(name='ux', description='Analyze.', prompt='You are...')
>>> list(store)
['ux']
>>> store['ux'].description
'Analyze.'
>>> del store['ux']
>>> len(store)
0
```

### *class* coact.CoactMeta(tools=None, disallowed_tools=list(), model=None, memory=None, permission_mode=None, skills=list(), mcp=list(), returns=None, consumes=None, persona=None)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

The parsed `coact:` block (every field optional; all default to absent).

```pycon
>>> m = CoactMeta.from_frontmatter({'coact': {'model': 'opus', 'tools': ['Read']}})
>>> m.model, m.tools, m.is_empty()
('opus', ['Read'], False)
>>> CoactMeta.from_frontmatter({'name': 'x'}).is_empty()
True
>>> CoactMeta.from_frontmatter({'metadata': {'coact': {'model': 'haiku'}}}).model
'haiku'
```

#### *classmethod* from_frontmatter(meta)

Build from a full frontmatter dict (reads the `coact` sub-mapping).

The block is the top-level `coact` key, else `metadata.coact`.

* **Return type:**
  [`CoactMeta`](coact.frontmatter.html.md#coact.frontmatter.CoactMeta)

#### is_empty()

True when the block carries no author-provided information.

* **Return type:**
  [`bool`](https://docs.python.org/3/builtins/functions.html#bool)

#### return_contract()

The author-pinned [`ReturnContract`](coact.base.html.md#coact.base.ReturnContract), if any.

* **Return type:**
  [`ReturnContract`](coact.base.html.md#coact.base.ReturnContract)

### *class* coact.CompletionPolicy(default_model='sonnet', default_memory=None, default_tools=('Read', 'Grep', 'Glob'), read_only_tools=frozenset({'Glob', 'Grep', 'NotebookRead', 'Read', 'WebFetch', 'WebSearch'}), opus_keywords=('orchestrat\\\\w\*', 'architect\\\\w\*', 'coordinat\\\\w\*', '\\\\bplan(?:ning|s|ned)?\\\\b', '\\\\bdesign(?:s|ing|ed)?\\\\b', 'review\\\\w\*'), opus_skill_threshold=3, write_keywords=('write', 'edit', 'create file', 'modify', 'generate', 'refactor'))

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Injectable defaults for the §3.2 extras COMPLETE must stamp on a skill.

```pycon
>>> p = CompletionPolicy()
>>> p.choose_model(tools=['Read', 'Grep'], description='Audit the bundle.', n_skills=1)
('haiku', 'read-only/explore: tools ⊆ read-only set')
>>> p.choose_model(tools=['Read', 'Write'], description='Implement the fix.', n_skills=1)[0]
'sonnet'
>>> p.choose_model(tools=['Read'], description='Orchestrate the review.', n_skills=1)[0]
'opus'
```

#### choose_memory()

The default memory scope (opt-in; None = no memory).

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`Literal`](https://docs.python.org/3/library/typing.html#typing.Literal)[`'user'`, `'project'`, `'local'`]], [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

#### choose_model(, tools, description, n_skills)

Route to a model from the effective tools / description / skill count.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`Literal`](https://docs.python.org/3/library/typing.html#typing.Literal)[`'sonnet'`, `'opus'`, `'haiku'`, `'inherit'`], [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

#### infer_tools(skill, coact_meta)

Derive the tool allowlist (declared-or-heuristic + report; DECISIONS D3).

Precedence: an explicit `coact: tools` wins; otherwise a conservative
heuristic from the skill’s resources/body. Never silently guesses — the
reason is returned for provenance.

```pycon
>>> from skill.base import Skill, SkillMeta
>>> s = Skill(meta=SkillMeta(name='x', description='y'), body='Write the report.')
>>> tools, why = CompletionPolicy().infer_tools(s, CoactMeta())
>>> 'Write' in tools and 'Read' in tools
True
```

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)], [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

#### opus_keywords *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), ...]* *= ('orchestrat\\\\w\*', 'architect\\\\w\*', 'coordinat\\\\w\*', '\\\\bplan(?:ning|s|ned)?\\\\b', '\\\\bdesign(?:s|ing|ed)?\\\\b', 'review\\\\w\*')*

Regex patterns (matched case-insensitively against the description) that
route to opus. Word-bounded so ‘plan.’ matches but ‘designer’/’designate’
don’t. Data, not code — extend or replace per policy.

#### override(\*\*kwargs)

Return a new policy with overridden fields (cascading defaults).

```pycon
>>> CompletionPolicy().override(default_model='opus').default_model
'opus'
```

* **Return type:**
  [`CompletionPolicy`](coact.policy.html.md#coact.policy.CompletionPolicy)

#### write_keywords *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), ...]* *= ('write', 'edit', 'create file', 'modify', 'generate', 'refactor')*

body substrings that imply the agent writes/edits files.

### *class* coact.FieldProvenance(field, value, source, note='')

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Where one [`AgentDefinition`](#coact.AgentDefinition) field’s value came from (dry-run audit).

```pycon
>>> FieldProvenance('model', 'sonnet', 'policy', 'default worker').source
'policy'
```

### *class* coact.IntegrationSpec(name, description='', version='0.1.0', tools=list(), resources=list(), prompts=list(), tool_specs=list(), instructions=None, auth='none', deployment='local-stdio', author=None, source=None)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Target-neutral description of an integration to publish.

The connectivity core maps onto MCP’s three primitives. Tools come in two
shapes that coexist: bare `'module:function'` refs in `tools` (the
mechanical/code ingress) and richer [`ToolSpec`](#coact.ToolSpec) descriptors in
`tool_specs` (the NL ingress, landscape-doc §9.1). `resources`/`prompts`
and the `auth`/`deployment` hints are declared now (open-closed) for the
remote connector and other targets to come.

```pycon
>>> spec = IntegrationSpec(name='paths', tools=['os.path:basename'])
>>> spec.name, spec.tools, spec.deployment
('paths', ['os.path:basename'], 'local-stdio')
>>> IntegrationSpec(name='empty').is_empty()
True
>>> draft = IntegrationSpec(name='wx', tool_specs=[ToolSpec(name='get')])
>>> draft.is_empty(), draft.runnable_refs()
(False, [])
```

#### is_empty()

True when there is nothing to publish (no tools/tool_specs/resources/prompts).

* **Return type:**
  [`bool`](https://docs.python.org/3/builtins/functions.html#bool)

#### render()

A terminal-friendly summary of the (possibly draft) integration.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

#### runnable_refs()

The importable `'module:function'` refs that back *runnable* tools.

Bare refs in `tools` plus the `handler` of every *bound* ToolSpec,
de-duplicated preserving order. A draft whose tools are all *proposed*
(unbound) returns `[]` — it has nothing a server can actually run yet.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

### *class* coact.PublishResult(target, dry_run=False, artifact=None, files=dict(), instructions='', warnings=list())

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

The outcome of [`publish()`](#coact.publish) — what was (or *would be*) produced.

`dry_run` mirrors `realize(backend='host', dry_run=True)`: in a dry run
`artifact` is `None` and `files` holds the would-write bundle members
(relpath → short preview), so you can look before you leap.

```pycon
>>> PublishResult(target='claude-local-mcpb', dry_run=True).render().splitlines()[0]
"Would publish (target='claude-local-mcpb', dry-run)"
```

#### render()

A terminal-friendly summary (used by the CLI).

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### *class* coact.RealizedHost(agents=dict(), skills=dict(), agents_dir=None, skills_dir=None, warnings=list(), dry_run=False)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

The materialized result of host realization (files the host will discover).

When produced by a `dry_run` the paths are what *would* be written/linked
(`dry_run=True` is recorded so the caller / CLI can label the preview);
nothing on disk is touched.

### *class* coact.ReturnContract(json_schema=dict(), ref=None, description='')

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

The agent’s return contract: its final-message schema + a human summary.

Skills return nothing; agents must define a consumable output. The canonical
form is a JSON Schema dict (portable across realization backends, DECISIONS
D6). `ref` records a `'module:Name'` source if the schema was resolved
from a Pydantic model / dataclass / TypedDict.

```pycon
>>> rc = ReturnContract(json_schema={'type': 'object'}, description='findings')
>>> rc.is_empty()
False
>>> ReturnContract().is_empty()
True
```

#### *classmethod* from_dict(d)

Parse from a `coact: returns` mapping (accepts `schema_ref` or `json_schema`).

```pycon
>>> ReturnContract.from_dict({'schema_ref': 'ov.schemas:UxFindings'}).ref
'ov.schemas:UxFindings'
```

* **Return type:**
  [`ReturnContract`](coact.base.html.md#coact.base.ReturnContract)

#### is_empty()

True when no schema (inline or ref) has been set.

* **Return type:**
  [`bool`](https://docs.python.org/3/builtins/functions.html#bool)

#### schema()

Return the canonical JSON Schema, resolving `ref` if needed (else `{}`).

Honors DECISIONS D6 (“JSON Schema is canonical; refs resolve to it”): an
inline `json_schema` wins; otherwise a `module:Name` `ref` is
resolved best-effort to a schema. Returns `{}` when neither is available.

```pycon
>>> ReturnContract(json_schema={'type': 'object'}).schema()
{'type': 'object'}
>>> 'properties' in ReturnContract(ref='coact.base:ReturnContract').schema()
True
```

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

#### to_dict()

Serialize to a plain dict (for the agent-md `coact:` block), omitting empties.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### *class* coact.RunnableAgent(agent_def, llm=None, runner=None, default_tools=('Read', 'Grep', 'Glob'), return_mode='auto')

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

An `aw.AgenticStep`-compatible runnable backed by the Claude Agent SDK.

Satisfies `execute(input_data, context) -> (artifact, info_dict)` so it
drops into `aw` workflows and reuses `aw`’s retry/validation/human-in-loop.
The SDK is imported lazily; `runner` is injectable so the agent can be
constructed and unit-tested without a live API call (dependency injection).

#### build_options()

Construct `ClaudeAgentOptions` from the agent definition (no API call).

* **Return type:**
  [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)

#### execute(input_data, context=None)

Run the agent over `input_data`; return `(artifact, info)` (aw protocol).

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`Any`](https://docs.python.org/3/library/typing.html#typing.Any), [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]]

#### return_mode *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'auto'*

`'auto'` (native output_format when
the SDK supports it, else the forced return tool), `'output_format'`, or
`'tool'` (force the return_result tool — for older SDKs / extended
thinking that cannot honor output_format). See DECISIONS D6.

* **Type:**
  How the return contract is realized

### *class* coact.RunnableCrewAIAgent(agent_def, model_map=<factory>, default_model='openai/gpt-4o-mini', runner=None, tools_map=None, use_response_format=True)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

An `aw.AgenticStep`-compatible runnable backed by a single `crewai.Agent`.

The `Agent` is built lazily and cached; `runner` is injectable so the agent
runs in tests with no API key and no `crewai` install (dependency injection).
The `Agent` is exposed via [`build_agent()`](#coact.RunnableCrewAIAgent.build_agent) / the [`agent`](#coact.RunnableCrewAIAgent.agent) property.

```pycon
>>> from coact import AgentDefinition
>>> ad = AgentDefinition(name='x', description='d', prompt='You are X.', model='sonnet')
>>> RunnableCrewAIAgent(ad).resolve_model()
'anthropic/claude-sonnet-4-5'
```

#### *property* agent *: [Any](https://docs.python.org/3/library/typing.html#typing.Any)*

The native `crewai.Agent` — add it to your own `Crew(agents=[...])`.

#### build_agent()

Build (once) and return the framework-native `crewai.Agent`.

Pure with respect to API calls — constructing the `Agent` does not invoke a
model. Imports `crewai` lazily (checked first); only ever called on the
default (non-injected) run path.

* **Return type:**
  [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)

#### build_backstory()

The CrewAI `backstory` (persona + the D6 return-contract instruction).

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

#### build_goal()

The CrewAI `goal` (required, non-empty).

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

#### build_response_model()

Synthesize the pydantic class for `kickoff(response_format=)`, or `None`.

`None` when there is no schema, `use_response_format` is off, or the schema
is not flat enough to represent (then coact relies on the prompt instruction).

* **Return type:**
  [`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`type`](https://docs.python.org/3/builtins/functions.html#type)]

#### build_role()

The CrewAI `role` (required, non-empty) — the agent’s name.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

#### execute(input_data, context=None)

Run the agent over `input_data`; return `(artifact, info)` (aw protocol).

`context` is accepted for `aw.AgenticStep` compatibility and ignored. Uses
the native `.pydantic` result when present; otherwise JSON-parses `.raw`
(graceful, like litellm). An injected `runner` keeps `crewai` unimported.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`Any`](https://docs.python.org/3/library/typing.html#typing.Any), [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]]

#### resolve_model()

Map the definition’s model selector to a LiteLLM model string (slash form).

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

#### runner *: [Optional](https://docs.python.org/3/library/typing.html#typing.Optional)[[Callable](https://docs.python.org/3/library/collections.abc.html#collections.abc.Callable)[..., [Any](https://docs.python.org/3/library/typing.html#typing.Any)]]* *= None*

`runner(*, agent, input_text, response_format) -> output` (`.raw` / `.pydantic`);
defaults to `_default_crewai_runner()`. The DI seam (mirrors litellm `completion=`).

#### tools_map *: [Optional](https://docs.python.org/3/library/typing.html#typing.Optional)[[dict](https://docs.python.org/3/builtins/stdtypes.html#dict)]* *= None*

`{tool_name: callable | crewai BaseTool}` — opt-in tool binding (D12); names with
no entry are reported in `info['warnings']` and never passed on.

#### use_response_format *: [bool](https://docs.python.org/3/builtins/functions.html#bool)* *= True*

Also request native structured output (synthesized pydantic class) when possible.

### *class* coact.RunnableLLMAgent(agent_def, model_map=<factory>, default_model='openai/gpt-4o-mini', completion=None, use_response_format=True)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

An `aw.AgenticStep`-compatible runnable backed by LiteLLM (any provider).

The return contract is realized two ways at once (belt-and-suspenders, since
provider support for structured output varies): the JSON Schema is passed as
LiteLLM’s `response_format` *and* embedded as an instruction in the system
message. `completion` is injectable so the agent runs in tests with no API
key; LiteLLM is imported lazily only on the default path.

```pycon
>>> from coact import AgentDefinition, ReturnContract
>>> ad = AgentDefinition(name='x', description='d', prompt='You are X.', model='sonnet')
>>> RunnableLLMAgent(ad).resolve_model()
'anthropic/claude-sonnet-4-5'
```

#### build_kwargs(input_data)

Build the `litellm.completion` kwargs (model, messages, response_format).

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

#### build_messages(input_data)

Build the chat messages: persona (+ return-contract instruction) then input.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)]

#### completion *: [Optional](https://docs.python.org/3/library/typing.html#typing.Optional)[[Callable](https://docs.python.org/3/library/collections.abc.html#collections.abc.Callable)[..., [Any](https://docs.python.org/3/library/typing.html#typing.Any)]]* *= None*

`completion(**kwargs) -> response`; defaults to `litellm.completion`.

#### execute(input_data, context=None)

Run the agent over `input_data`; return `(artifact, info)` (aw protocol).

`context` is accepted for `aw.AgenticStep` compatibility and ignored by
this backend. If a provider rejects the structured `response_format`, the
call is retried once **without** it — the schema is still requested via the
system-prompt instruction (the belt-and-suspenders fallback made functional).

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`Any`](https://docs.python.org/3/library/typing.html#typing.Any), [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]]

#### resolve_model()

Map the definition’s model selector to a LiteLLM model string.

A mapped selector wins; an explicit LiteLLM string in `model` is used
verbatim; otherwise `default_model`. The lookup covers any hashable
selector (so a `model_map` entry always applies if present).

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

#### use_response_format *: [bool](https://docs.python.org/3/builtins/functions.html#bool)* *= True*

Also pass the schema as LiteLLM `response_format` (in addition to the prompt).

### *class* coact.RunnableLLMGraphAgent(agent_def, model_map=<factory>, default_model='openai:gpt-4o-mini', factory=None, runner=None, tools_map=None, use_response_format=True, structured_strategy='auto')

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

An `aw.AgenticStep`-compatible runnable backed by a LangGraph graph.

The compiled graph is built lazily and cached; `factory` is injectable so the
agent can be constructed and unit-tested without a live API call or a
`langchain`/`langgraph` install (dependency injection). The graph itself is
exposed via [`build_agent()`](#coact.RunnableLLMGraphAgent.build_agent) / the [`agent`](#coact.RunnableLLMGraphAgent.agent) property for composition.

```pycon
>>> from coact import AgentDefinition
>>> ad = AgentDefinition(name='x', description='d', prompt='You are X.', model='sonnet')
>>> RunnableLLMGraphAgent(ad).resolve_model()
'anthropic:claude-sonnet-4-5'
```

#### *property* agent *: [Any](https://docs.python.org/3/library/typing.html#typing.Any)*

The native `CompiledStateGraph` — add it as a node to your own `StateGraph`.

#### build_agent()

Build (once) and return the framework-native `CompiledStateGraph`.

Pure with respect to API calls — constructing the graph does not invoke a
model. The default path imports `langchain`/`langgraph` lazily and
checks they are installed; an injected `factory` bypasses both.

* **Return type:**
  [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)

#### build_response_format()

Build the `create_agent` `response_format` for the return contract, or None.

Wraps the canonical JSON-Schema dict in `ToolStrategy` (default) or
`ProviderStrategy` — both accept the raw dict. When `langchain` is not
importable (an injected factory in tests, or the `create_react_agent`
fallback, which accepts a bare dict), the raw schema dict is returned so the
offline path needs no framework.

* **Return type:**
  [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)

#### build_state(input_data)

Build the LangGraph input state (a single user message).

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

#### build_system_prompt()

Persona (+ the D6 return-contract instruction when a schema is declared).

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

#### execute(input_data, context=None)

Run the agent over `input_data`; return `(artifact, info)` (aw protocol).

`context` is accepted for `aw.AgenticStep` compatibility and ignored.
Uses the native `structured_response` when the graph returns one; otherwise
falls back to JSON-parsing the final message text (graceful, like litellm) —
langchain may omit `structured_response` even when a schema was requested.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`Any`](https://docs.python.org/3/library/typing.html#typing.Any), [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]]

#### factory *: [Optional](https://docs.python.org/3/library/typing.html#typing.Optional)[[Callable](https://docs.python.org/3/library/collections.abc.html#collections.abc.Callable)[..., [Any](https://docs.python.org/3/library/typing.html#typing.Any)]]* *= None*

`factory(*, model, tools, system_prompt, response_format, name) -> graph`;
defaults to `_default_langgraph_factory()`. The primary DI seam.

#### resolve_model()

Map the definition’s model selector to a langchain `provider:model` string.

A mapped selector wins; an explicit provider string in `model` is used
verbatim; otherwise `default_model`.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

#### runner *: [Optional](https://docs.python.org/3/library/typing.html#typing.Optional)[[Callable](https://docs.python.org/3/library/collections.abc.html#collections.abc.Callable)[[[Any](https://docs.python.org/3/library/typing.html#typing.Any), [Any](https://docs.python.org/3/library/typing.html#typing.Any)], [Any](https://docs.python.org/3/library/typing.html#typing.Any)]]* *= None*

`runner(graph, state) -> result`.

* **Type:**
  Optional test-only bypass of `graph.invoke`

#### structured_strategy *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'auto'*

`'auto'` / `'tool'` -> `ToolStrategy` (safest cross-provider); `'provider'`
-> `ProviderStrategy` (native provider structured output).

#### tools_map *: [Optional](https://docs.python.org/3/library/typing.html#typing.Optional)[[dict](https://docs.python.org/3/builtins/stdtypes.html#dict)]* *= None*

`{tool_name: callable | BaseTool}` — opt-in tool binding (D12); names with
no entry here are reported in `info['unbound_tools']` and never passed on.

#### use_response_format *: [bool](https://docs.python.org/3/builtins/functions.html#bool)* *= True*

Also request native structured output (in addition to the prompt instruction).

### *class* coact.ToolSpec(name, description='', input_schema=None, handler=None)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A richer, target-neutral description of one tool in an [`IntegrationSpec`](#coact.IntegrationSpec).

The *mechanical* ingress represents tools as bare `'module:function'` ref
strings (`IntegrationSpec.tools`). The *NL* ingress ([`coact.nl_ingress`](coact.nl_ingress.html.md#module-coact.nl_ingress))
and the landscape-doc §9.1 model need more — a name, a description, an input
JSON Schema, and an **optional** handler ref:

- A ToolSpec **with** a `handler` is *bound* (runnable): its ref joins the
  spec’s runnable set and the published server can import and call it.
- A ToolSpec **without** a handler is a *proposed* tool — a design draft to
  bind to real code (or supply a ref for) before it can run.

```pycon
>>> ToolSpec(name='get_weather', handler='wx.api:current').is_bound()
True
>>> ToolSpec(name='get_weather').is_bound()
False
```

#### is_bound()

True when a `module:function` handler backs this tool (so it can run).

* **Return type:**
  [`bool`](https://docs.python.org/3/builtins/functions.html#bool)

### coact.agents_dir(, scope='project', project_dir=None)

Resolve the `.claude/agents` directory for the given scope.

`scope='project'` resolves against the detected project root (or
`project_dir`); `scope='global'` resolves against `~/.claude`.

```pycon
>>> agents_dir(scope='global').as_posix().endswith('.claude/agents')
True
```

* **Return type:**
  [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)

### coact.back(agent)

Best-effort, **lossy** agent→skill extraction (harvest an agent into a skill).

Strips the persona/return-contract envelope down to a reusable skill stub
(name + description + a pointer to the skills it referenced). The actual
procedure usually lives in those referenced skills, so this cannot recover
it — the result is a starting point the user fleshes out, not a faithful
inverse of COMPLETE.

```pycon
>>> from coact import AgentDefinition
>>> sk = back(AgentDefinition(name='ux', description='Analyze.', skills=['ux', 'shared']))
>>> sk.meta.name
'ux'
>>> 'lossy' in sk.body.lower()
True
```

* **Return type:**
  `Skill`

### coact.complete(source, , policy=None, llm=None)

Complete a skill into an [`AgentDefinition`](#coact.AgentDefinition) (the plan’s agent).

```pycon
>>> from skill.base import Skill, SkillMeta
>>> s = Skill(meta=SkillMeta(name='ux', description='Analyze bundles.'), body='steps')
>>> ad = complete(s)
>>> ad.name, ad.skills, ('Return contract' in ad.prompt)
('ux', ['ux'], True)
```

* **Return type:**
  [`AgentDefinition`](coact.base.html.md#coact.base.AgentDefinition)

### coact.diff(skill, agent)

Show what extras `agent` adds over its source `skill`.

`skill` is any skill source; `agent` is an [`AgentDefinition`](#coact.AgentDefinition), an
agent `*.md` path, or a skill source (which is completed first).

```pycon
>>> from skill.base import Skill, SkillMeta
>>> s = Skill(meta=SkillMeta(name='ux', description='Analyze bundles.'), body='steps')
>>> from coact import complete
>>> d = diff(s, complete(s))
>>> any(f == 'prompt' and cls.startswith('extra') for f, cls, _ in d.rows)
True
```

* **Return type:**
  [`AgentDiff`](coact.analysis.html.md#coact.analysis.AgentDiff)

### coact.emit_agent(ad, target='claude-agents-md', , dest=None)

Emit an agent to a registered target; optionally write a file target to `dest`.

For string targets (e.g. `claude-agents-md`) with `dest` given, writes
`<dest>/<name>.md` and returns the [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path). Otherwise
returns the emitter’s value (str or dict).

```pycon
>>> ad = AgentDefinition(name='ux', description='Analyze.', prompt='You are...')
>>> emit_agent(ad).splitlines()[0]
'---'
```

* **Return type:**
  [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)

### coact.estimate(agents)

Surface the fan-out cost tradeoff for an agent set (DECISIONS D9).

```pycon
>>> from coact import AgentDefinition
>>> a = AgentDefinition(name='a', description='x', skills=['shared'])
>>> b = AgentDefinition(name='b', description='y', skills=['shared'])
>>> est = estimate([a, b])
>>> est.interdependent, est.shared_skills
(True, ['shared'])
```

* **Return type:**
  [`Estimate`](coact.analysis.html.md#coact.analysis.Estimate)

### coact.from_claude_agent_md(text)

Parse `.claude/agents/*.md` content back into an [`AgentDefinition`](#coact.AgentDefinition).

The inverse of [`to_claude_agent_md()`](#coact.to_claude_agent_md): lossless for every **structured**
field; the `prompt` body is whitespace-trimmed on both ends (personas are
not whitespace-sensitive).

```pycon
>>> ad = AgentDefinition(name='ux', description='Analyze.', prompt='You are an analyst.',
...     tools=['Read', 'Grep'], model='sonnet',
...     returns=ReturnContract(json_schema={'type': 'object'}, description='out'))
>>> back = from_claude_agent_md(to_claude_agent_md(ad))
>>> (back.name, back.tools, back.model, back.prompt) == (ad.name, ad.tools, ad.model, ad.prompt)
True
>>> back.returns.json_schema
{'type': 'object'}
```

* **Return type:**
  [`AgentDefinition`](coact.base.html.md#coact.base.AgentDefinition)

### coact.integration_spec_from(source, , name=None, description='', version='0.1.0', author=None)

Coerce a capability source into an [`IntegrationSpec`](#coact.IntegrationSpec).

Accepts (and flattens lists of): a prebuilt [`IntegrationSpec`](#coact.IntegrationSpec), a
`'module:function'` ref string, a live callable (its
`__module__:__qualname__` becomes the ref), or a skill source carrying a
`coact: mcp:` block. The resulting `name` is kebab-cased so it is a safe,
machine-readable bundle identifier.

```pycon
>>> integration_spec_from(['os.path:basename'], name='paths').tools
['os.path:basename']
>>> integration_spec_from('os.path:basename', name='My Tools').name
'my-tools'
```

* **Return type:**
  [`IntegrationSpec`](coact.integration.html.md#coact.integration.IntegrationSpec)

### coact.integration_spec_from_description(description, , llm=None, model=None, name=None, version='0.1.0', author=None, prompt_template=None, infer_tool_schemas=True)

Refine a natural-language `description` into a **draft** IntegrationSpec.

The opt-in LLM ingress (DECISIONS D10): generation is routed through `aix`
(provider-agnostic) by default, via `oa`’s prompt-as-function machinery.

* **Parameters:**
  * **description** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – What the integration should do, in plain language.
  * **llm** ([`Any`](https://docs.python.org/3/library/typing.html#typing.Any)) – The LLM backend. `None` → `aix.chat` (the default, multi-provider);
    a `callable(prompt, **kwargs) -> str` is used as-is (handy for tests);
    a `str` is treated as a model name passed to `aix.chat`.
  * **model** ([`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]) – Explicit model id (overrides a model-name `llm`); `None` lets the
    backend resolve its own configured default.
  * **name** ([`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]) – Force the integration name (else the model proposes one). Kebab-cased.
  * **version** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – Spec version string.
  * **author** ([`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]) – Optional author name recorded on the spec.
  * **prompt_template** ([`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]) – Override the authoring prompt (e.g. one managed in
    `pyrompt`). Must contain a single `{description}` placeholder.
  * **infer_tool_schemas** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – When a proposed tool lacks an `input_schema`, infer
    one from its description via `oa.infer_schema_from_verbal_description`
    (aix-backed). Best-effort — failures leave the schema `None`.
* **Return type:**
  [`IntegrationSpec`](coact.integration.html.md#coact.integration.IntegrationSpec)
* **Returns:**
  An [`IntegrationSpec`](coact.integration.html.md#coact.integration.IntegrationSpec) whose `tool_specs` hold the
  proposed tools. Tools the description bound to existing code become runnable
  refs (`spec.runnable_refs()`); the rest are design drafts to bind later.

Example (offline, with an injected backend):

```pycon
>>> reply = (
...     '{"name": "wx", "description": "weather",'
...     ' "tools": [{"name": "get_weather", "description": "lookup",'
...     ' "input_schema": {"type": "object", "properties": {"city":'
...     ' {"type": "string"}}}, "handler": null}]}'
... )
>>> spec = integration_spec_from_description("a weather tool", llm=lambda p, **k: reply)
>>> spec.name, [t.name for t in spec.tool_specs], spec.runnable_refs()
('wx', ['get_weather'], [])
```

### coact.inventory(project=None)

Enumerate skills, derived agents, and MCP-exposed tools in a project.

```pycon
>>> import tempfile
>>> inv = inventory(tempfile.mkdtemp())
>>> inv.skills, inv.agents
([], [])
```

* **Return type:**
  [`Inventory`](coact.analysis.html.md#coact.analysis.Inventory)

### coact.parse_coact_meta(source)

Parse a [`CoactMeta`](#coact.CoactMeta) from a SKILL.md path/text/`Skill`/frontmatter dict.

Accepts the several shapes coact callers have on hand:

- a `Skill` (uses its `source_path` to re-read the raw
  frontmatter, since `Skill.meta` drops the `coact` key);
- a filesystem path to a skill directory or a SKILL.md file;
- raw SKILL.md text;
- an already-parsed frontmatter dict.

```pycon
>>> parse_coact_meta("---\nname: x\ncoact:\n  model: haiku\n---\nbody").model
'haiku'
```

* **Return type:**
  [`CoactMeta`](coact.frontmatter.html.md#coact.frontmatter.CoactMeta)

### coact.plan_completion(source, , policy=None, llm=None)

Plan the skill→agent completion, recording the provenance of every field.

Accepts a `Skill`, a path to a skill directory / SKILL.md,
or a skill key/name resolvable in the local store or project skills. Pass an
optional `llm` (any `callable(str)->str`, an `aw` `StepConfig`, or a
model name) to *draft* a richer persona — the mechanical path needs none.

```pycon
>>> from skill.base import Skill, SkillMeta
>>> s = Skill(meta=SkillMeta(name='auditor', description='Audit a bundle for issues.'), body='steps')
>>> plan = plan_completion(s)
>>> plan.agent.name
'auditor'
>>> plan.agent.model  # read-only description with default tools -> haiku
'haiku'
>>> any(p.field == 'prompt' for p in plan.provenance)
True
```

* **Return type:**
  [`AgentPlan`](coact.base.html.md#coact.base.AgentPlan)

### coact.publish(source, , target='claude-local-mcpb', dry_run=False, \*\*kwargs)

Publish a capability to a chatbot host via the named target.

`source` is anything [`coact.integration.integration_spec_from()`](coact.integration.html.md#coact.integration.integration_spec_from)
accepts: `'module:function'` refs, live callables, a skill carrying a
`coact: mcp:` block, or a prebuilt [`IntegrationSpec`](coact.integration.html.md#coact.integration.IntegrationSpec).
Target-specific options (`dest`, `name`, `author`, …) pass through as
keyword arguments.

* **Return type:**
  [`PublishResult`](#coact.PublishResult)

### coact.publish_mcpb(source, , dest=None, dry_run=False, name=None, author=None, version='0.1.0', description='', python_command='python', manifest_version='0.3')

Bundle `source` into a Claude Desktop `.mcpb` extension.

```pycon
>>> res = publish_mcpb(['os.path:basename'], name='paths', dry_run=True)
>>> res.dry_run, res.artifact, sorted(res.files)
(True, None, ['manifest.json', 'server/main.py', 'server/py2mcp_config.json'])
```

* **Return type:**
  [`PublishResult`](#coact.PublishResult)

### coact.publish_remote(source, , dest=None, dry_run=False, name=None, author=None, version='0.1.0', description='', connector_url=None, idp_issuer=None, jwks_uri=None, audience=None, required_scopes=None, host='127.0.0.1', port=8000, transport='streamable-http', include_dockerfile=True)

Scaffold a remote Claude connector (Streamable-HTTP MCP server + OAuth 2.1).

`source` is anything [`coact.integration.integration_spec_from()`](coact.integration.html.md#coact.integration.integration_spec_from) accepts.
The OAuth parameters describe the **managed IdP** that issues tokens and *this*
server’s public identity; when omitted, placeholder values + a loud warning are
emitted so the scaffold is still useful (fill them in before going public).

```pycon
>>> res = publish_remote(['os.path:basename'], name='paths', dry_run=True)
>>> res.dry_run, sorted(res.files)
(True, ['DEPLOY.md', 'Dockerfile', 'requirements.txt', 'server/app.py',
        'server/connector_config.json'])
```

* **Return type:**
  [`PublishResult`](#coact.PublishResult)

### coact.publish_targets()

The names of all registered publish targets.

```pycon
>>> isinstance(publish_targets(), list)
True
```

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

### coact.realize(target, , backend='host', \*\*kwargs)

Realize an agent (or skill, or list) via the named backend.

```pycon
>>> from coact import AgentDefinition
>>> import tempfile
>>> ad = AgentDefinition(name='ux', description='Analyze.', prompt='You are...', skills=['ux'])
>>> res = realize(ad, backend='host', dest=tempfile.mkdtemp(), link=False)
>>> res.agents['ux'].name
'ux.md'
```

* **Return type:**
  [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)

### coact.realize_crewai(target, , model_map=None, default_model='openai/gpt-4o-mini', runner=None, tools_map=None, use_response_format=True, policy=None)

Realize one agent as a CrewAI-backed [`RunnableCrewAIAgent`](#coact.RunnableCrewAIAgent) (aw-compatible).

`model_map` overrides how coact selectors map to LiteLLM model strings;
`tools_map` opt-in binds host-resolved tool *names* to callables/tools (D12);
`runner` injects the run call for testing. Raises if asked to realize more than
one agent (topology is out of scope — D8).

* **Return type:**
  [`RunnableCrewAIAgent`](#coact.RunnableCrewAIAgent)

### coact.realize_host(target, , scope='project', dest=None, project_dir=None, link=True, skills_source=None, force=False, dry_run=False, policy=None)

Materialize agents (+ linked skills) so the host agent runs them.

Writes `<dest>/<name>.md` for each agent and (when `link`) symlinks each
**referenced** skill into the sibling `.claude/skills/` so Claude Code
discovers both. `skills_source` (a dir or list of dirs each holding
`<name>/SKILL.md`) is searched first; otherwise skills are resolved by name
via the local store / project. Verifies discovery and reports anything missing.

Pass `dry_run=True` to *preview* — the returned [`RealizedHost`](#coact.RealizedHost) lists
the agent files that would be written and the skills that would link (with the
same unresolvable-skill warnings), but **no file or symlink is created**. This
mirrors `coact.complete.plan_completion()`’s look-before-you-leap contract
for the one backend that mutates the filesystem (progressive disclosure).

* **Return type:**
  [`RealizedHost`](#coact.RealizedHost)

### coact.realize_langgraph(target, , model_map=None, default_model='openai:gpt-4o-mini', factory=None, runner=None, tools_map=None, structured_strategy='auto', use_response_format=True, policy=None)

Realize one agent as a LangGraph-backed [`RunnableLLMGraphAgent`](#coact.RunnableLLMGraphAgent) (aw-compatible).

`model_map` overrides how coact selectors (`sonnet`/`opus`/`haiku`) map to
langchain `provider:model` strings. `tools_map` opt-in binds host-resolved tool
*names* to Python callables (D12). `factory` injects the graph builder for
testing. Raises if asked to realize more than one agent (topology is out — D8).

* **Return type:**
  [`RunnableLLMGraphAgent`](#coact.RunnableLLMGraphAgent)

### coact.realize_litellm(target, , model_map=None, default_model='openai/gpt-4o-mini', completion=None, use_response_format=True, policy=None)

Realize one agent as a provider-agnostic [`RunnableLLMAgent`](#coact.RunnableLLMAgent) (via LiteLLM).

`model_map` overrides how coact model selectors (`sonnet`/`opus`/`haiku`)
map to LiteLLM model strings — point them at any provider to prove portability.

* **Return type:**
  [`RunnableLLMAgent`](#coact.RunnableLLMAgent)

### coact.realize_mcp(target, , name=None, input_trans=None)

Expose a skill’s declared Python tools as a FastMCP server (foreign-host).

Reads the `coact: mcp:` block (`module` + `functions`) of the source
skill(s) and delegates to `py2mcp.mk_mcp_from_refs` — coact writes no MCP
plumbing (DECISIONS §6.1.3). `target` may be a skill source or an
[`AgentDefinition`](#coact.AgentDefinition) (whose `source_skill` is resolved back to the
skill that carries the declaration).

* **Return type:**
  [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)

### coact.realize_sdk(target, , llm=None, runner=None, return_mode='auto', policy=None)

Realize a single agent as a runnable [`RunnableAgent`](#coact.RunnableAgent) (aw-compatible).

`return_mode` selects how the return contract reaches the SDK (DECISIONS
D6): `'auto'` uses native `output_format` when the installed SDK supports
it and otherwise falls back to a forced `return_result` tool; pass
`'tool'` to force that fallback (e.g. for models / extended-thinking modes
that cannot honor `output_format`).

* **Return type:**
  [`RunnableAgent`](#coact.RunnableAgent)

### coact.register_validator()

Register the coact-block validator into `skill.create.validators` (idempotent).

* **Return type:**
  [`None`](https://docs.python.org/3/builtins/constants.html#None)

### coact.resolve_llm(llm=None)

Resolve `llm` to a `callable(str) -> str`, or `None` if unavailable.

```pycon
>>> resolve_llm(lambda p: 'hi')('x')
'hi'
>>> resolve_llm('no-such-thing') is None or callable(resolve_llm('no-such-thing'))
True
```

* **Return type:**
  [`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`Callable`](https://docs.python.org/3/library/typing.html#typing.Callable)[[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)], [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]]

### coact.scaffold_fleet(target, , dest=None, agents_dir='.claude/agents', policy=None)

Emit a starter shim wiring the target agents as a runnable `sdk` fleet.

`target` is anything [`coact.realize()`](#coact.realize) accepts (an
[`AgentDefinition`](coact.base.html.md#coact.base.AgentDefinition), a skill source, an agent `*.md` path,
or a list of these). Returns the shim **source string**; if `dest` is given
(a file path, or a directory in which `fleet.py` is written) the file is
written and its [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path) returned instead.

The shim references each agent by name under `agents_dir` and chains them
**sequentially** — a deliberately thin starting point. It is the *only*
topology-adjacent artifact coact produces (DECISIONS D8): coact writes it once
and never runs it; you own the control flow from there.

```pycon
>>> from coact import AgentDefinition
>>> shim = scaffold_fleet([AgentDefinition(name='collector', description='x'),
...                         AgentDefinition(name='summarizer', description='y')])
>>> 'AGENTS = ["collector", "summarizer"]' in shim
True
>>> 'backend="sdk"' in shim and 'YOU OWN THIS FILE' in shim
True
```

* **Return type:**
  [`Union`](https://docs.python.org/3/library/typing.html#typing.Union)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)]

### coact.structured(prompt, schema, , llm=None, retries=1)

Best-effort schema-conforming dict from an LLM, or `None` if unavailable.

Native structured output is provider-specific; this facade stays portable by
instructing JSON-only output that conforms to `schema` and parsing it,
retrying once on a parse miss. Returns `None` when no LLM is resolvable —
callers fall back to a template (DECISIONS D10).

* **Return type:**
  [`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)]

### coact.synthesize_persona(skill, , return_contract, tools=None, extra_skills=None, llm=None)

Synthesize the system prompt (persona) for an agent derived from `skill`.

Wraps the skill’s intent as an identity, states operating invariants, and
appends the return contract — while **pointing at** the source skill rather
than inlining it (§3.3). The identity paragraph is template-generated by
default; when an `llm` is resolvable it is *drafted* by the LLM instead
(richer, but the invariants and the return contract stay deterministic so the
machine-facing contract is never at the mercy of generation). The LLM is
optional — absent one, the template path is a sound default (DECISIONS D10).

```pycon
>>> from skill.base import Skill, SkillMeta
>>> s = Skill(meta=SkillMeta(name='ux-analyst', description='Analyze UX bundles.'), body='steps')
>>> rc = ReturnContract(json_schema={'type': 'object'}, description='findings')
>>> persona, src = synthesize_persona(s, return_contract=rc, tools=['Read', 'Grep'])
>>> 'ux-analyst' in persona and 'Return contract' in persona and src == 'synthesized-template'
True
```

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Literal`](https://docs.python.org/3/library/typing.html#typing.Literal)[`'skill'`, `'coact-frontmatter'`, `'policy'`, `'inferred'`, `'synthesized-template'`, `'synthesized-llm'`, `'default'`]]

### coact.synthesize_return_contract(skill, , coact_meta)

Choose the agent’s return contract: author-pinned, else a template default.

```pycon
>>> from skill.base import Skill, SkillMeta
>>> s = Skill(meta=SkillMeta(name='x', description='y'), body='z')
>>> rc, src = synthesize_return_contract(s, coact_meta=CoactMeta())
>>> rc.json_schema['type'], src
('object', 'synthesized-template')
>>> rc2, src2 = synthesize_return_contract(s, coact_meta=CoactMeta(returns={'schema_ref': 'm:N'}))
>>> rc2.ref, src2
('m:N', 'coact-frontmatter')
```

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`ReturnContract`](coact.base.html.md#coact.base.ReturnContract), [`Literal`](https://docs.python.org/3/library/typing.html#typing.Literal)[`'skill'`, `'coact-frontmatter'`, `'policy'`, `'inferred'`, `'synthesized-template'`, `'synthesized-llm'`, `'default'`]]

### coact.to_aw_agent_spec(ad)

Adapt an [`AgentDefinition`](#coact.AgentDefinition) to an `aw.translators.AgentSpec`.

Lets coact reuse `aw`’s CrewAI / OpenAI / SKILL.md renderers (the
`*_from_spec` cores) instead of reimplementing them — the ecosystem
coordination point. Requires `aw`.

### coact.to_claude_agent_md(ad)

Serialize an agent to `.claude/agents/<name>.md` content.

```pycon
>>> ad = AgentDefinition(name='ux', description='Analyze.', prompt='You are...')
>>> md = to_claude_agent_md(ad)
>>> md.startswith('---') and 'name: ux' in md and 'You are...' in md
True
```

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### coact.validate_coact_block(skill_or_meta)

Validate a `coact:` block, returning issue strings (empty = valid/absent).

Additive: a skill with no `coact:` block passes trivially. The block is read
from the top level or from `metadata.coact` (see `coact_block_location()`),
and issues are prefixed with where it was found. Checks key
spelling, `model`/`memory` enums, `mcp` entry shape, and that
`returns` carries exactly one of `schema_ref`/`json_schema`.

```pycon
>>> validate_coact_block({'coact': {'model': 'gpt-4'}})
["coact.model: 'gpt-4' is not one of sonnet, opus, haiku, inherit"]
>>> validate_coact_block({'coact': {'mcp': [{'functions': ['f']}]}})
["coact.mcp[0]: missing required 'module'"]
>>> validate_coact_block({'name': 'ok'})
[]
```

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

### Modules

| [`analysis`](coact.analysis.html.md#module-coact.analysis)               | Analysis utilities — small tools to *see and move between* the layers.                                                           |
|-----------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------------|
| [`base`](coact.base.html.md#module-coact.base)                       | Core data model for coact — the single in-memory representation of an agent.                                                     |
| [`emit`](coact.emit.html.md#module-coact.emit)                       | Emitters: one [`AgentDefinition`](coact.base.html.md#coact.base.AgentDefinition) → many serializations. |
| [`frontmatter`](coact.frontmatter.html.md#module-coact.frontmatter)         | The additive `coact:` SKILL.md frontmatter convention and its validator.                                                         |
| [`integration`](coact.integration.html.md#module-coact.integration)         | IntegrationSpec — the target-neutral SSOT for a *published* integration.                                                         |
| [`llm`](coact.llm.html.md#module-coact.llm)                         | Provider-agnostic LLM facade — thin, injected, never a hard dependency.                                                          |
| [`nl_ingress`](coact.nl_ingress.html.md#module-coact.nl_ingress)           | NL-description → IntegrationSpec — the **opt-in LLM ingress** for PUBLISH.                                                       |
| [`policy`](coact.policy.html.md#module-coact.policy)                   | Completion policy — the injectable model / memory / tool choices COMPLETE stamps.                                                |
| [`return_contract`](coact.return_contract.html.md#module-coact.return_contract) | Realizing a return contract — the backend-agnostic part of DECISIONS D6.                                                         |
| [`scaffold`](coact.scaffold.html.md#module-coact.scaffold)               | Scaffold a *starter* multi-agent shim — the one topology-adjacent thing coact emits.                                             |
| [`schema`](coact.schema.html.md#module-coact.schema)                   | JSON Schema resolution — turn a `module:Name` ref into a canonical schema.                                                       |
| [`stores`](coact.stores.html.md#module-coact.stores)                   | Mapping facades over agent definitions on disk.                                                                                  |
| [`synthesis`](coact.synthesis.html.md#module-coact.synthesis)             | Persona & return-contract synthesis — the two real "extras" of a skill→agent lift.                                               |
| [`util`](coact.util.html.md#module-coact.util)                       | Pure helpers for coact with no internal coact imports.                                                                           |
