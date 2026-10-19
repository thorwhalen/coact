# coact.llm

Provider-agnostic LLM facade — thin, injected, never a hard dependency.

COACT_SPEC §5.5 / §8 / DECISIONS D10. Any LLM use in coact goes through this
facade, and **every mechanical path runs with no LLM at all**. The facade
resolves an injected `llm` to a `callable(str) -> str` from, in order:

1. an explicit `callable` (use as-is);
2. an `aw` `StepConfig` (use its `resolve_llm()` — reuse aw’s injection);
3. a model-name `str` (wrap `skill.ai.chat` with that model);
4. `None` → `skill.ai.chat` if any provider is configured, else `None`.

When nothing is available, [`resolve_llm()`](#coact.llm.resolve_llm) returns `None` and callers fall
back to their template path — no provider lock-in, no crash. [`structured()`](#coact.llm.structured)
adds a best-effort `(prompt, schema) -> dict` on top (instruct-JSON + parse +
one retry), used only for *optional* return-contract drafting.

### Functions

| [`resolve_llm`](#coact.llm.resolve_llm)([llm])                             | Resolve `llm` to a `callable(str) -> str`, or `None` if unavailable.      |
|-------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------|
| [`structured`](#coact.llm.structured)(prompt, schema, \*[, llm, retries]) | Best-effort schema-conforming dict from an LLM, or `None` if unavailable. |

### coact.llm.resolve_llm(llm=None)

Resolve `llm` to a `callable(str) -> str`, or `None` if unavailable.

```pycon
>>> resolve_llm(lambda p: 'hi')('x')
'hi'
>>> resolve_llm('no-such-thing') is None or callable(resolve_llm('no-such-thing'))
True
```

* **Return type:**
  [`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`Callable`](https://docs.python.org/3/library/typing.html#typing.Callable)[[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)], [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]]

### coact.llm.structured(prompt, schema, , llm=None, retries=1)

Best-effort schema-conforming dict from an LLM, or `None` if unavailable.

Native structured output is provider-specific; this facade stays portable by
instructing JSON-only output that conforms to `schema` and parsing it,
retrying once on a parse miss. Returns `None` when no LLM is resolvable —
callers fall back to a template (DECISIONS D10).

* **Return type:**
  [`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)]
