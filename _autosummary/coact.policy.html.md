# coact.policy

Completion policy — the injectable model / memory / tool choices COMPLETE stamps.

COACT_SPEC §5.4 / DECISIONS D4. The model, memory, and tool-narrowing choices
are **policy**: injected data, not hardcoded branches, with cascading defaults in
the spirit of `aw.GlobalConfig` (sensible defaults; override globally by
constructing a different [`CompletionPolicy`](#coact.policy.CompletionPolicy), or per-skill via the
`coact:` block, which always wins over policy). This module imports no LLM and
no `aw` — it is a pure mechanical path (DECISIONS D10); the `aw` `StepConfig`
LLM injection used for *optional* persona synthesis lives behind that optional
path in [`coact.synthesis`](coact.synthesis.html.md#module-coact.synthesis).

The routing table is data on the dataclass, so users extend it without editing
code (open-closed).

### Module Attributes

| [`default_policy`](#coact.policy.default_policy)   | The default policy instance (importable, mutable-by-override).   |
|-------------------------------------------------------------------|------------------------------------------------------------------|

### Classes

| [`CompletionPolicy`](#coact.policy.CompletionPolicy)([default_model, ...])   | Injectable defaults for the §3.2 extras COMPLETE must stamp on a skill.   |
|-------------------------------------------------------------------------------------------|---------------------------------------------------------------------------|

### *class* coact.policy.CompletionPolicy(default_model='sonnet', default_memory=None, default_tools=('Read', 'Grep', 'Glob'), read_only_tools=frozenset({'Glob', 'Grep', 'NotebookRead', 'Read', 'WebFetch', 'WebSearch'}), opus_keywords=('orchestrat\\\\w\*', 'architect\\\\w\*', 'coordinat\\\\w\*', '\\\\bplan(?:ning|s|ned)?\\\\b', '\\\\bdesign(?:s|ing|ed)?\\\\b', 'review\\\\w\*'), opus_skill_threshold=3, write_keywords=('write', 'edit', 'create file', 'modify', 'generate', 'refactor'))

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
  [`CompletionPolicy`](#coact.policy.CompletionPolicy)

#### write_keywords *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), ...]* *= ('write', 'edit', 'create file', 'modify', 'generate', 'refactor')*

body substrings that imply the agent writes/edits files.

### coact.policy.default_policy *= CompletionPolicy(default_model='sonnet', default_memory=None, default_tools=('Read', 'Grep', 'Glob'), read_only_tools=frozenset({'WebSearch', 'WebFetch', 'Read', 'Glob', 'Grep', 'NotebookRead'}), opus_keywords=('orchestrat\\\\w\*', 'architect\\\\w\*', 'coordinat\\\\w\*', '\\\\bplan(?:ning|s|ned)?\\\\b', '\\\\bdesign(?:s|ing|ed)?\\\\b', 'review\\\\w\*'), opus_skill_threshold=3, write_keywords=('write', 'edit', 'create file', 'modify', 'generate', 'refactor'))*

The default policy instance (importable, mutable-by-override).
