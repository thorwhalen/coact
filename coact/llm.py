"""Provider-agnostic LLM facade — thin, injected, never a hard dependency.

COACT_SPEC §5.5 / §8 / DECISIONS D10. Any LLM use in coact goes through this
facade, and **every mechanical path runs with no LLM at all**. The facade
resolves an injected ``llm`` to a ``callable(str) -> str`` from, in order:

1. an explicit ``callable`` (use as-is);
2. an ``aw`` ``StepConfig`` (use its ``resolve_llm()`` — reuse aw's injection);
3. a model-name ``str`` (wrap ``skill.ai.chat`` with that model);
4. ``None`` → ``skill.ai.chat`` if any provider is configured, else ``None``.

When nothing is available, :func:`resolve_llm` returns ``None`` and callers fall
back to their template path — no provider lock-in, no crash. :func:`structured`
adds a best-effort ``(prompt, schema) -> dict`` on top (instruct-JSON + parse +
one retry), used only for *optional* return-contract drafting.
"""

from __future__ import annotations

import json
import re
from typing import Any, Callable, Optional

from coact.util import first_balanced_span

LLMCallable = Callable[[str], str]


def resolve_llm(llm: Any = None) -> Optional[LLMCallable]:
    """Resolve ``llm`` to a ``callable(str) -> str``, or ``None`` if unavailable.

    >>> resolve_llm(lambda p: 'hi')('x')
    'hi'
    >>> resolve_llm('no-such-thing') is None or callable(resolve_llm('no-such-thing'))
    True
    """
    if llm is None:
        return _skill_ai_llm()
    if callable(llm):
        return llm
    # aw StepConfig (or anything exposing resolve_llm)
    resolve = getattr(llm, "resolve_llm", None)
    if callable(resolve):
        try:
            resolved = resolve()
            if callable(resolved):
                return resolved
        except Exception:
            return None
    if isinstance(llm, str):
        return _skill_ai_llm(model=llm)
    return None


def _skill_ai_llm(*, model: Optional[str] = None) -> Optional[LLMCallable]:
    """A ``callable(str) -> str`` backed by ``skill.ai.chat``, or ``None`` if no provider."""
    try:
        from skill import ai
    except Exception:
        return None
    try:
        if not ai.is_ai_available():
            return None
    except Exception:
        return None

    def _chat(prompt: str) -> str:
        return ai.chat(prompt, model=model)

    return _chat


def structured(
    prompt: str,
    schema: dict,
    *,
    llm: Any = None,
    retries: int = 1,
) -> Optional[dict]:
    """Best-effort schema-conforming dict from an LLM, or ``None`` if unavailable.

    Native structured output is provider-specific; this facade stays portable by
    instructing JSON-only output that conforms to ``schema`` and parsing it,
    retrying once on a parse miss. Returns ``None`` when no LLM is resolvable —
    callers fall back to a template (DECISIONS D10).
    """
    fn = resolve_llm(llm)
    if fn is None:
        return None
    instruction = (
        f"{prompt}\n\nReturn ONLY a JSON object conforming to this JSON Schema "
        f"(no prose, no code fences):\n{json.dumps(schema, indent=2)}"
    )
    last_text = ""
    for _ in range(retries + 1):
        last_text = fn(instruction)
        parsed = _extract_json(last_text)
        if isinstance(parsed, dict):
            return parsed
        instruction = (
            f"{prompt}\n\nYour previous reply was not valid JSON. Return ONLY a "
            f"JSON object for this schema:\n{json.dumps(schema)}"
        )
    return None


def _extract_json(text: Any) -> Any:
    """Pull a JSON object out of an LLM reply (tolerating code fences/trailing prose).

    Non-string input (e.g. an injected ``llm`` that returns ``None``) yields
    ``None`` rather than crashing — the facade's "no crash" contract (DECISIONS
    D10), mirroring ``coact.realize_litellm._try_json``'s guard.

    >>> _extract_json(None) is None
    True
    """
    if not isinstance(text, str):
        return None
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    candidate = fence.group(1) if fence else text
    try:
        return json.loads(candidate)
    except (ValueError, TypeError):
        obj = _first_balanced_object(candidate)
        if obj is not None:
            try:
                return json.loads(obj)
            except (ValueError, TypeError):
                return None
    return None


def _first_balanced_object(s: str) -> Optional[str]:
    """Return the first brace-balanced ``{...}`` substring (ignoring braces in strings).

    Thin object-only wrapper over :func:`coact.util.first_balanced_span` (the
    ``structured()`` facade insists on a JSON *object*); the shared primitive
    keeps this depth-balanced matching in one place.

    >>> _first_balanced_object('Result: {"a": 1}. Note: use {braces}.')
    '{"a": 1}'
    """
    return first_balanced_span(s, "{", "}")
