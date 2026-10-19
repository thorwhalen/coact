# coact.base

Core data model for coact — the single in-memory representation of an agent.

This module is the spine described in COACT_SPEC §3.1/§5.2: an
[`AgentDefinition`](#coact.base.AgentDefinition) is *one* object that can serialize to **both** the
filesystem `.claude/agents/*.md` format and the Claude Agent SDK form (see
[`coact.emit`](coact.emit.html.md#module-coact.emit)). It is a lossless **superset** of the host subagent schema,
kept independent of the SDK type (DECISIONS D2) so coact’s core carries no SDK
or LLM import.

Three dataclasses live here:

- [`ReturnContract`](#coact.base.ReturnContract) — the agent’s final-message schema (so a manager can
  deterministically consume its output); the single most important “extra”.
- [`AgentDefinition`](#coact.base.AgentDefinition) — the SSOT object.
- [`AgentPlan`](#coact.base.AgentPlan) / [`FieldProvenance`](#coact.base.FieldProvenance) — the inspectable dry-run result
  of COMPLETE, recording where every synthesized field came from.

### Module Attributes

| [`ModelName`](#coact.base.ModelName)        | Host model selector values (the Agent SDK `model` literal).            |
|-------------------------------------------------------------------|------------------------------------------------------------------------|
| [`MemoryScope`](#coact.base.MemoryScope)      | Subagent memory scope.                                                 |
| [`ProvenanceSource`](#coact.base.ProvenanceSource) | Provenance source tags — where a synthesized field's value originated. |

### Classes

| [`AgentDefinition`](#coact.base.AgentDefinition)(name, description[, prompt, ...])   | The SSOT: one object, two serializations (filesystem md + SDK form).                                                |
|------------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------|
| [`AgentPlan`](#coact.base.AgentPlan)(agent[, provenance, warnings])            | The inspectable result of `plan_completion`: the agent + its provenance.                                            |
| [`FieldProvenance`](#coact.base.FieldProvenance)(field, value, source[, note])       | Where one [`AgentDefinition`](#coact.base.AgentDefinition) field's value came from (dry-run audit). |
| [`ReturnContract`](#coact.base.ReturnContract)([json_schema, ref, description])     | The agent's return contract: its final-message schema + a human summary.                                            |

### *class* coact.base.AgentDefinition(name, description, prompt='', tools=None, disallowed_tools=list(), model=None, skills=list(), memory=None, mcp_servers=list(), permission_mode=None, returns=ReturnContract(), consumes=None, source_skill=None)

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

### *class* coact.base.AgentPlan(agent, provenance=list(), warnings=list())

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

The inspectable result of `plan_completion`: the agent + its provenance.

Shows the proposed [`AgentDefinition`](#coact.base.AgentDefinition) and, for each field, *why* it has
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

### *class* coact.base.FieldProvenance(field, value, source, note='')

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Where one [`AgentDefinition`](#coact.base.AgentDefinition) field’s value came from (dry-run audit).

```pycon
>>> FieldProvenance('model', 'sonnet', 'policy', 'default worker').source
'policy'
```

### coact.base.MemoryScope

Subagent memory scope.

alias of [`Literal`](https://docs.python.org/3/library/typing.html#typing.Literal)[‘user’, ‘project’, ‘local’]

### coact.base.ModelName

Host model selector values (the Agent SDK `model` literal).

alias of [`Literal`](https://docs.python.org/3/library/typing.html#typing.Literal)[‘sonnet’, ‘opus’, ‘haiku’, ‘inherit’]

### coact.base.ProvenanceSource

Provenance source tags — where a synthesized field’s value originated.

alias of [`Literal`](https://docs.python.org/3/library/typing.html#typing.Literal)[‘skill’, ‘coact-frontmatter’, ‘policy’, ‘inferred’, ‘synthesized-template’, ‘synthesized-llm’, ‘default’]

### *class* coact.base.ReturnContract(json_schema=dict(), ref=None, description='')

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
  [`ReturnContract`](#coact.base.ReturnContract)

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
