# coact.integration

IntegrationSpec — the target-neutral SSOT for a *published* integration.

coact’s COMPLETE/REALIZE axes turn skills into agent definitions and run them.
The **PUBLISH** axis (this module + [`coact.publish`](coact.html.md#coact.publish)) is orthogonal: it takes
a *capability* — a set of Python tools given as `'module:function'` refs, live
callables, or a skill’s `coact: mcp:` block — and ships it to a chatbot host as
a deployable integration (a Claude Desktop `.mcpb` bundle today; remote
connectors / skills / plugins / other hosts later).

The spec is deliberately **separate from** [`AgentDefinition`](coact.base.html.md#coact.base.AgentDefinition)
(which is agent-persona-centric): an integration is MCP-server-shaped
(tools/resources/prompts + auth + deployment), per the chatbot-integration
landscape research (`misc/docs/CHATBOT_INTEGRATION_LANDSCAPE.md`). The canonical
artifact is an MCP server, built by `py2mcp` — coact owns the spec, the
packaging, and the target registry, **not** the MCP plumbing (mirrors the `mcp`
realize backend, DECISIONS §6.1.3 / D17).

### Module Attributes

| [`IntegrationSource`](#coact.integration.IntegrationSource)   | a built spec, a `module:function` ref, a skill source (path/`Skill`), a live callable, or an iterable of those.   |
|----------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------|

### Functions

| [`integration_spec_from`](#coact.integration.integration_spec_from)(source, \*[, name, ...])   | Coerce a capability source into an [`IntegrationSpec`](#coact.integration.IntegrationSpec).   |
|---------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------|

### Classes

| [`IntegrationSpec`](#coact.integration.IntegrationSpec)(name[, description, ...])        | Target-neutral description of an integration to publish.                                                                 |
|---------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------|
| [`ToolSpec`](#coact.integration.ToolSpec)(name[, description, input_schema, ...]) | A richer, target-neutral description of one tool in an [`IntegrationSpec`](#coact.integration.IntegrationSpec). |

### coact.integration.IntegrationSource

a built spec, a `module:function`
ref, a skill source (path/`Skill`), a live callable, or an iterable of those.

* **Type:**
  What [`integration_spec_from()`](#coact.integration.integration_spec_from) accepts

alias of [`IntegrationSpec`](#coact.integration.IntegrationSpec) | [`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path) | `Callable`[[…], [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)] | [`Iterable`](https://docs.python.org/3/library/typing.html#typing.Iterable)[[`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]

### *class* coact.integration.IntegrationSpec(name, description='', version='0.1.0', tools=list(), resources=list(), prompts=list(), tool_specs=list(), instructions=None, auth='none', deployment='local-stdio', author=None, source=None)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Target-neutral description of an integration to publish.

The connectivity core maps onto MCP’s three primitives. Tools come in two
shapes that coexist: bare `'module:function'` refs in `tools` (the
mechanical/code ingress) and richer [`ToolSpec`](#coact.integration.ToolSpec) descriptors in
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

### *class* coact.integration.ToolSpec(name, description='', input_schema=None, handler=None)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A richer, target-neutral description of one tool in an [`IntegrationSpec`](#coact.integration.IntegrationSpec).

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

### coact.integration.integration_spec_from(source, , name=None, description='', version='0.1.0', author=None)

Coerce a capability source into an [`IntegrationSpec`](#coact.integration.IntegrationSpec).

Accepts (and flattens lists of): a prebuilt [`IntegrationSpec`](#coact.integration.IntegrationSpec), a
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
  [`IntegrationSpec`](#coact.integration.IntegrationSpec)
