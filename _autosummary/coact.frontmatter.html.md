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
SKILL.md). coact reads it from the **raw** frontmatter because
`skill.SkillMeta` only retains the standard keys — so this module parses the
SKILL.md text directly rather than going through `Skill.meta`.

The validator is registered into `skill.create.validators` (additive) and also
exposed via a `skill.validators` entry point, so `skill validate` checks the
block without coact having to be the entry point.

### Module Attributes

| [`COACT_KEY`](#coact.frontmatter.COACT_KEY)   | The single namespaced frontmatter key coact reads/writes.   |
|--------------------------------------------------------------|-------------------------------------------------------------|

### Functions

| [`parse_coact_meta`](#coact.frontmatter.parse_coact_meta)(source)            | Parse a [`CoactMeta`](#coact.frontmatter.CoactMeta) from a SKILL.md path/text/`Skill`/frontmatter dict.   |
|--------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------|
| [`register_validator`](#coact.frontmatter.register_validator)()                | Register the coact-block validator into `skill.create.validators` (idempotent).                                          |
| [`validate_coact_block`](#coact.frontmatter.validate_coact_block)(skill_or_meta) | Validate a `coact:` block, returning issue strings (empty = valid/absent).                                               |

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
```

#### *classmethod* from_frontmatter(meta)

Build from a full frontmatter dict (reads the `coact` sub-mapping).

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

Additive: a skill with no `coact:` block passes trivially. Checks key
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
