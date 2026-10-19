# coact.emit

Emitters: one [`AgentDefinition`](coact.base.html.md#coact.base.AgentDefinition) → many serializations.

COACT_SPEC §5.3. Emit targets are an open-closed `skill`-style
`Registry` (register, don’t hardcode). Two ship by
default:

- `claude-agents-md` — the filesystem `.claude/agents/<name>.md` (host
  frontmatter using the host’s exact camelCase field names + the persona body).
  coact-specific fields (the return contract, `consumes`, `source_skill`) are
  carried in an additive `coact:` frontmatter sub-block so the round-trip is
  lossless and the host still ignores them. Reuses `skill.base` frontmatter
  helpers — coact writes no YAML by hand.
- `sdk-agent-dict` — kwargs for `claude_agent_sdk.AgentDefinition` plus the
  leftover `query()` options, built by **introspecting** the installed SDK
  dataclass so it degrades gracefully across SDK versions (DECISIONS D2). The
  SDK is imported lazily here only; core stays SDK-free.

Future emitters (CrewAI / OpenAI via the `aw` adapter) register without
touching this module. Topology is never emitted (DECISIONS D8).

### Module Attributes

| [`emitters`](#coact.emit.emitters)   | `AgentDefinition -> serialized form` (str or dict).   |
|-------------------------------------------------------------|-------------------------------------------------------|

### Functions

| [`agent_to_frontmatter`](#coact.emit.agent_to_frontmatter)(ad)       | Build the host frontmatter dict for an agent (omitting empty fields).           |
|---------------------------------------------------------------------------------|---------------------------------------------------------------------------------|
| [`emit_agent`](#coact.emit.emit_agent)(ad[, target, dest]) | Emit an agent to a registered target; optionally write a file target to `dest`. |
| [`from_claude_agent_md`](#coact.emit.from_claude_agent_md)(text)     | Parse `.claude/agents/*.md` content back into an `AgentDefinition`.             |
| [`to_aw_agent_spec`](#coact.emit.to_aw_agent_spec)(ad)           | Adapt an `AgentDefinition` to an `aw.translators.AgentSpec`.                    |
| [`to_claude_agent_md`](#coact.emit.to_claude_agent_md)(ad)         | Serialize an agent to `.claude/agents/<name>.md` content.                       |
| [`to_sdk_agent_dict`](#coact.emit.to_sdk_agent_dict)(ad)          | Build Agent-SDK kwargs + leftover query options for one agent.                  |

### coact.emit.agent_to_frontmatter(ad)

Build the host frontmatter dict for an agent (omitting empty fields).

```pycon
>>> ad = AgentDefinition(name='x', description='y', tools=['Read'], model='haiku')
>>> fm = agent_to_frontmatter(ad)
>>> fm['name'], fm['tools'], fm['model']
('x', ['Read'], 'haiku')
```

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### coact.emit.emit_agent(ad, target='claude-agents-md', , dest=None)

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

### coact.emit.emitters *: Registry[[Callable](https://docs.python.org/3/library/collections.abc.html#collections.abc.Callable)[[[AgentDefinition](coact.base.html.md#coact.base.AgentDefinition)], [Any](https://docs.python.org/3/library/typing.html#typing.Any)]]* *= Registry('emitters', keys=['claude-agents-md', 'sdk-agent-dict'])*

`AgentDefinition -> serialized form` (str or dict).

* **Type:**
  Registry of emit targets

### coact.emit.from_claude_agent_md(text)

Parse `.claude/agents/*.md` content back into an `AgentDefinition`.

The inverse of [`to_claude_agent_md()`](#coact.emit.to_claude_agent_md): lossless for every **structured**
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

### coact.emit.to_aw_agent_spec(ad)

Adapt an `AgentDefinition` to an `aw.translators.AgentSpec`.

Lets coact reuse `aw`’s CrewAI / OpenAI / SKILL.md renderers (the
`*_from_spec` cores) instead of reimplementing them — the ecosystem
coordination point. Requires `aw`.

### coact.emit.to_claude_agent_md(ad)

Serialize an agent to `.claude/agents/<name>.md` content.

```pycon
>>> ad = AgentDefinition(name='ux', description='Analyze.', prompt='You are...')
>>> md = to_claude_agent_md(ad)
>>> md.startswith('---') and 'name: ux' in md and 'You are...' in md
True
```

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### coact.emit.to_sdk_agent_dict(ad)

Build Agent-SDK kwargs + leftover query options for one agent.

Returns `{'name', 'agent_kwargs', 'options'}` where `agent_kwargs` are
accepted by the *installed* `claude_agent_sdk.AgentDefinition` and
`options` holds fields that version cannot express (to be wired into
`query()` by the `sdk` realize backend). Requires the Agent SDK.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)
