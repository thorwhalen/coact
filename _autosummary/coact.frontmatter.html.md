# coact.frontmatter

The additive `coact:` SKILL.md frontmatter convention and its validator.

COACT_SPEC §4 / DECISIONS D1. The standard SKILL.md frontmatter (`name`,
`description`) does not carry what COMPLETE needs to derive tools, model, MCP,
or a return contract. `coact` defines an **optional, additive** `coact:`
block (snake_case interior) that a skill author — or coact itself — fills in so
the skill→agent lift is mechanical and reproducible (SSOT for the extras):

```default
coact:
  tools: [Read, Grep, Glob]
  model: sonnet
  memory: project
  mcp:
    - module: ov.analyzers
      functions: [score_contrast, find_tap_targets]
  returns:
    schema_ref: ov.schemas:UxFindings
    description: Usability findings for the captured bundle
  consumes: evidence_bundle
  persona: |
    You are a meticulous UX analyst...
```

The block is ignored by other tools (a skill carrying it is still a valid plain
SKILL.md). The Agent Skills spec keeps custom keys under `metadata:`, so a
spec-clean skill may nest the block there instead (`metadata: {coact: {...}}`);
coact reads either, and a top-level block wins when both exist. coact reads it from the **raw** frontmatter because
`skill.SkillMeta` only retains the standard keys — so this module parses the
SKILL.md text directly rather than going through `Skill.meta`.

The validator is registered into `skill.create.validators` (additive) and also
exposed via a `skill.validators` entry point, so `skill validate` checks the
block without coact having to be the entry point.

### Module Attributes

| [`COACT_KEY`](#coact.frontmatter.COACT_KEY)    | The single namespaced frontmatter key coact reads/writes.          |
|---------------------------------------------------------------|--------------------------------------------------------------------|
| [`METADATA_KEY`](#coact.frontmatter.METADATA_KEY) | `metadata.coact` is read when there is no top-level `coact` block. |

### Functions

| [`coact_block_location`](#coact.frontmatter.coact_block_location)(meta)          | Return `(block, path)`: the frontmatter's coact block and where it was found.                                          |
|--------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------|
| [`parse_coact_meta`](#coact.frontmatter.parse_coact_meta)(source)            | Parse a [`CoactMeta`](#coact.frontmatter.CoactMeta) from a SKILL.md path/text/`Skill`/frontmatter dict. |
| [`register_validator`](#coact.frontmatter.register_validator)()                | Register the coact-block validator into `skill.create.validators` (idempotent).                                        |
| [`validate_coact_block`](#coact.frontmatter.validate_coact_block)(skill_or_meta) | Validate a `coact:` block, returning issue strings (empty = valid/absent).                                             |

### Classes

| [`CoactMeta`](#coact.frontmatter.CoactMeta)([tools, disallowed_tools, model, ...])   | The parsed `coact:` block (every field optional; all default to absent).   |
|-----------------------------------------------------------------------------------------------------|----------------------------------------------------------------------------|

### coact.frontmatter.COACT_KEY *= 'coact'*

The single namespaced frontmatter key coact reads/writes.

### *class* coact.frontmatter.CoactMeta(tools=None, disallowed_tools=list(), model=None, memory=None, permission_mode=None, skills=list(), mcp=list(), returns=None, consumes=None, persona=None)

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
  [`CoactMeta`](#coact.frontmatter.CoactMeta)

#### is_empty()

True when the block carries no author-provided information.

* **Return type:**
  [`bool`](https://docs.python.org/3/builtins/functions.html#bool)

#### return_contract()

The author-pinned [`ReturnContract`](coact.base.html.md#coact.base.ReturnContract), if any.

* **Return type:**
  [`ReturnContract`](coact.base.html.md#coact.base.ReturnContract)

### coact.frontmatter.METADATA_KEY *= 'metadata'*

`metadata.coact` is read when there is no
top-level `coact` block.

* **Type:**
  The spec’s home for custom keys

### coact.frontmatter.coact_block_location(meta)

Return `(block, path)`: the frontmatter’s coact block and where it was found.

`path` is `"coact"` (top level, which wins when both exist),
`"metadata.coact"` (the Agent Skills spec’s home for custom keys), or
`"coact"` with a `None` block when there is none, so writers default to
the top level.

```pycon
>>> coact_block_location({'metadata': {'coact': {'model': 'opus'}}})
({'model': 'opus'}, 'metadata.coact')
>>> coact_block_location({'coact': {'model': 'haiku'}, 'metadata': {'coact': {}}})
({'model': 'haiku'}, 'coact')
>>> coact_block_location({'name': 'x'})
(None, 'coact')
```

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`Any`](https://docs.python.org/3/library/typing.html#typing.Any), [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

### coact.frontmatter.parse_coact_meta(source)

Parse a [`CoactMeta`](#coact.frontmatter.CoactMeta) from a SKILL.md path/text/`Skill`/frontmatter dict.

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
  [`CoactMeta`](#coact.frontmatter.CoactMeta)

### coact.frontmatter.register_validator()

Register the coact-block validator into `skill.create.validators` (idempotent).

* **Return type:**
  [`None`](https://docs.python.org/3/builtins/constants.html#None)

### coact.frontmatter.validate_coact_block(skill_or_meta)

Validate a `coact:` block, returning issue strings (empty = valid/absent).

Additive: a skill with no `coact:` block passes trivially. The block is read
from the top level or from `metadata.coact` (see [`coact_block_location()`](#coact.frontmatter.coact_block_location)),
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
