# coact.scaffold

Scaffold a *starter* multi-agent shim — the one topology-adjacent thing coact emits.

COACT_SPEC §6.4 / DECISIONS D8. coact emits agent *definitions* + tool/MCP wiring
and **stops at topology** — it is not LangGraph, and a subagent definition can’t
express graphs/edges/cycles. The single sanctioned exception is *scaffolding*: for
a multi-agent run, coact may emit a **starter Python file** that wires N realized
`sdk` agents under an `aw` coordinator, “clearly marked as a starting point the
user owns.” That file is data coact writes once, not a runtime coact operates.

[`scaffold_fleet()`](#coact.scaffold.scaffold_fleet) is exactly that emitter: it takes the same targets
`realize` accepts (agents, skills, `*.md` files, or a list) and returns — or
writes — a runnable, heavily-commented sequential-pipeline starter the user then
reshapes. It runs **no LLM and stands up no runtime** (it only renders source);
the emitted shim defers all execution to `coact.realize(..., backend='sdk')` and
all topology to the human who owns it.

### Module Attributes

| [`DEFAULT_SHIM_NAME`](#coact.scaffold.DEFAULT_SHIM_NAME)   | Default filename when `dest` is a directory.   |
|----------------------------------------------------------------------|------------------------------------------------|

### Functions

| [`scaffold_fleet`](#coact.scaffold.scaffold_fleet)(target, \*[, dest, ...])   | Emit a starter shim wiring the target agents as a runnable `sdk` fleet.   |
|--------------------------------------------------------------------------------------------|---------------------------------------------------------------------------|

### coact.scaffold.DEFAULT_SHIM_NAME *= 'fleet.py'*

Default filename when `dest` is a directory.

### coact.scaffold.scaffold_fleet(target, , dest=None, agents_dir='.claude/agents', policy=None)

Emit a starter shim wiring the target agents as a runnable `sdk` fleet.

`target` is anything [`coact.realize()`](coact.html.md#coact.realize) accepts (an
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
