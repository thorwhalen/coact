# coact.stores

Mapping facades over agent definitions on disk.

COACT_SPEC §8 (“prefer Mapping/MutableMapping facades — a skills store, an
agents store”) mirroring `skill.stores.LocalSkillStore`. [`AgentStore`](#coact.stores.AgentStore)
is a `MutableMapping[str, AgentDefinition]` over a `.claude/agents/`
directory (one `<name>.md` per agent). Because it is a plain mapping, it drops
straight into `py2mcp.mk_mcp_from_store` to expose a project’s agents as CRUD
over MCP, and into `coact.analysis.inventory`.

### Functions

| [`agents_dir`](#coact.stores.agents_dir)(\*[, scope, project_dir])   | Resolve the `.claude/agents` directory for the given scope.   |
|-----------------------------------------------------------------------------------------|---------------------------------------------------------------|

### Classes

| [`AgentStore`](#coact.stores.AgentStore)([root, scope, project_dir])   | A `MutableMapping[str, AgentDefinition]` over a `.claude/agents/` dir.   |
|-------------------------------------------------------------------------------------------|--------------------------------------------------------------------------|

### *class* coact.stores.AgentStore(root=None, , scope='project', project_dir=None)

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

### coact.stores.agents_dir(, scope='project', project_dir=None)

Resolve the `.claude/agents` directory for the given scope.

`scope='project'` resolves against the detected project root (or
`project_dir`); `scope='global'` resolves against `~/.claude`.

```pycon
>>> agents_dir(scope='global').as_posix().endswith('.claude/agents')
True
```

* **Return type:**
  [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)
