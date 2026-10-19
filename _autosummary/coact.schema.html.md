# coact.schema

JSON Schema resolution — turn a `module:Name` ref into a canonical schema.

Extracted from [`coact.base`](coact.base.html.md#module-coact.base) so that module stays a pure SSOT *data model*
and this one owns the (separable, independently testable) concern of mapping
Python types to JSON Schema (DECISIONS D6: “JSON Schema is canonical; refs
resolve to it”). The public entry point is [`resolve_schema_ref()`](#coact.schema.resolve_schema_ref); the
annotation/structural helpers are module-private.

Everything here is **best-effort and provider-agnostic**: a ref that cannot be
imported or mapped yields `None` (or a permissive `{}` fragment) so callers
warn and fall back rather than crash — no hard pydantic dependency, no LLM
(DECISIONS D10).

### Functions

| [`resolve_schema_ref`](#coact.schema.resolve_schema_ref)(ref)   | Best-effort resolve a `'module:Name'` ref to a JSON Schema dict, or `None`.   |
|----------------------------------------------------------------------------|-------------------------------------------------------------------------------|

### coact.schema.resolve_schema_ref(ref)

Best-effort resolve a `'module:Name'` ref to a JSON Schema dict, or `None`.

Handles Pydantic models (`model_json_schema`/`schema`), dataclasses, and
TypedDicts (structural `{type: object, properties: {...}}`). Provider- and
pydantic-agnostic: returns `None` on any failure so callers can warn and
fall back rather than crash (DECISIONS D6/D10).

```pycon
>>> resolve_schema_ref('coact.base:ReturnContract')['type']
'object'
>>> resolve_schema_ref('definitely.not:Real') is None
True
```

* **Return type:**
  [`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)]
