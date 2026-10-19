# coact.util

Pure helpers for coact with no internal coact imports.

Small, reusable string/name utilities and a thin `check_requirements` helper
for the optional-dependency backends (Agent SDK, py2mcp/FastMCP, an LLM
provider). Kept dependency-free so every other coact module can import it.

### Functions

| [`agent_filename`](#coact.util.agent_filename)(name)                     | Return the safe `<name>.md` filename for an agent, rejecting unsafe names.   |
|-------------------------------------------------------------------------------------------|------------------------------------------------------------------------------|
| [`check_requirements`](#coact.util.check_requirements)(modules, \*, feature) | Verify optional dependencies are importable, else raise an actionable error. |
| [`first_balanced_span`](#coact.util.first_balanced_span)(s[, opener, closer]) | Return the first depth-balanced `opener…closer` substring of `s`.            |
| [`import_object`](#coact.util.import_object)(ref)                       | Resolve a `'module.path:attr'` or `'module.path.attr'` reference.            |
| [`safe_filename`](#coact.util.safe_filename)(name, \*[, suffix, kind])  | Return `f"{name}{suffix}"` after rejecting unsafe, path-bearing names.       |
| [`to_kebab_case`](#coact.util.to_kebab_case)(name)                      | Convert CamelCase / snake_case / spaces to kebab-case.                       |
| [`to_snake_case`](#coact.util.to_snake_case)(name)                      | Convert CamelCase / kebab-case / spaces to snake_case.                       |

### coact.util.agent_filename(name)

Return the safe `<name>.md` filename for an agent, rejecting unsafe names.

Agent names become files under `.claude/agents/`; a name carrying a path
separator or `..` could escape that directory (CWE-22 path traversal) on
write *or* read. Names must be a bare filename stem. Raises `ValueError` on
an empty, non-string, or path-bearing name — the check lives at the
filesystem boundary so in-memory [`AgentDefinition`](coact.base.html.md#coact.base.AgentDefinition)s stay
unconstrained.

```pycon
>>> agent_filename('ux-analyst')
'ux-analyst.md'
>>> agent_filename('../escape')
Traceback (most recent call last):
    ...
ValueError: unsafe agent name '../escape': ...
```

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### coact.util.check_requirements(modules, , feature)

Verify optional dependencies are importable, else raise an actionable error.

`modules` maps an importable module name to the pip target that provides
it (e.g. `{'claude_agent_sdk': 'claude-agent-sdk'}`). Raises
`ImportError` listing the exact `pip install` line for whatever is
missing — and, when some requirements *are* present, which ones — the
package-UX convention for optional backends (informative, actionable errors).

```pycon
>>> check_requirements({'json': 'json'}, feature='noop')  # importable -> no raise
```

* **Return type:**
  [`None`](https://docs.python.org/3/builtins/constants.html#None)

### coact.util.first_balanced_span(s, opener='{', closer='}')

Return the first depth-balanced `opener…closer` substring of `s`.

Brackets inside double-quoted JSON strings are ignored, so a valid value
followed by prose that itself contains brackets is not over-captured (a
greedy `opener.*closer` would run to the *last* `closer` and fail to
parse). Returns `None` when no balanced span starts in `s`. Shared by the
LLM-reply JSON extractors ([`coact.llm`](coact.llm.html.md#module-coact.llm), [`coact.realize_litellm`](coact.html.md#coact.realize_litellm)).

```pycon
>>> first_balanced_span('Result: {"a": 1}. Note: {braces}.')
'{"a": 1}'
>>> first_balanced_span('see [1, [2, 3]] end', '[', ']')
'[1, [2, 3]]'
>>> first_balanced_span('no brackets here') is None
True
```

* **Return type:**
  [`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

### coact.util.import_object(ref)

Resolve a `'module.path:attr'` or `'module.path.attr'` reference.

Prefer the `module:attr` form (unambiguous). Falls back to splitting on the
last dot for the dotted form.

```pycon
>>> import_object('json:dumps')
<function dumps at ...>
>>> import_object('os.path.join')
<function join at ...>
```

* **Return type:**
  [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)

### coact.util.safe_filename(name, , suffix='', kind='name')

Return `f"{name}{suffix}"` after rejecting unsafe, path-bearing names.

Names that become files must be bare filename stems; one carrying a path
separator or `..` could escape its directory (CWE-22) on write *or* read.
Raises `ValueError` on an empty, non-string, or path-bearing name. `kind`
customizes the error wording for the caller’s domain. Shared by
[`agent_filename()`](#coact.util.agent_filename) (`.md` agents) and the publish axis (`.mcpb` bundles).

```pycon
>>> safe_filename('paths', suffix='.mcpb')
'paths.mcpb'
>>> safe_filename('../x', suffix='.mcpb')
Traceback (most recent call last):
    ...
ValueError: unsafe name '../x': ...
```

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### coact.util.to_kebab_case(name)

Convert CamelCase / snake_case / spaces to kebab-case.

```pycon
>>> to_kebab_case('UxAnalyst')
'ux-analyst'
>>> to_kebab_case('ux_analyst')
'ux-analyst'
>>> to_kebab_case('already-kebab')
'already-kebab'
```

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### coact.util.to_snake_case(name)

Convert CamelCase / kebab-case / spaces to snake_case.

```pycon
>>> to_snake_case('UxAnalyst')
'ux_analyst'
>>> to_snake_case('ux-analyst')
'ux_analyst'
```

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)
