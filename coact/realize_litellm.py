"""LiteLLM realization backend — proof that the canonical definition is portable.

The ``host``/``sdk`` backends realize an :class:`~coact.base.AgentDefinition`
against the *Anthropic* stack. This backend realizes the **same** definition
against **any** provider LiteLLM speaks (OpenAI, Anthropic, Gemini, Mistral,
local Ollama, …) — the Stage-2 portability recommendation from the interop
research (DECISIONS D12). It demonstrates that nothing in the definition is
Anthropic-specific: persona → system message, return contract → structured
output, model selector → a LiteLLM model string (via an open-closed map).

Like the ``sdk`` backend it produces an ``aw.AgenticStep``-compatible runnable
(``execute(input_data, context) -> (artifact, info)``), and the completion call
is injectable so it is unit-testable without a live API key. It registers itself
into :data:`coact.realize.backends` on import — **no core change** (open-closed).

Topology stays out (D8): one definition → one runnable; no graph is serialized.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Optional

from coact.base import AgentDefinition
from coact.policy import CompletionPolicy
from coact.realize import RealizeTarget, coerce_agents, backends
from coact.return_contract import render_json_return_instruction
from coact.util import check_requirements, first_balanced_span

#: Map coact's model *selectors* to LiteLLM model strings. Data, not code — pass a
#: ``model_map=`` to ``realize(..., backend='litellm')`` to target any provider.
#: An explicit LiteLLM string in ``AgentDefinition.model`` is used verbatim.
DEFAULT_MODEL_MAP: dict[str, str] = {
    "haiku": "anthropic/claude-3-5-haiku-latest",
    "sonnet": "anthropic/claude-sonnet-4-5",
    "opus": "anthropic/claude-opus-4-1",
    "inherit": "openai/gpt-4o-mini",
}
#: Used when the definition pins no model and none maps.
DEFAULT_MODEL = "openai/gpt-4o-mini"


@dataclass
class RunnableLLMAgent:
    """An ``aw.AgenticStep``-compatible runnable backed by LiteLLM (any provider).

    The return contract is realized two ways at once (belt-and-suspenders, since
    provider support for structured output varies): the JSON Schema is passed as
    LiteLLM's ``response_format`` *and* embedded as an instruction in the system
    message. ``completion`` is injectable so the agent runs in tests with no API
    key; LiteLLM is imported lazily only on the default path.

    >>> from coact import AgentDefinition, ReturnContract
    >>> ad = AgentDefinition(name='x', description='d', prompt='You are X.', model='sonnet')
    >>> RunnableLLMAgent(ad).resolve_model()
    'anthropic/claude-sonnet-4-5'
    """

    agent_def: AgentDefinition
    model_map: dict = field(default_factory=lambda: dict(DEFAULT_MODEL_MAP))
    default_model: str = DEFAULT_MODEL
    #: ``completion(**kwargs) -> response``; defaults to ``litellm.completion``.
    completion: Optional[Callable[..., Any]] = None
    #: Also pass the schema as LiteLLM ``response_format`` (in addition to the prompt).
    use_response_format: bool = True

    def __post_init__(self) -> None:
        # Defensive copy: a caller's dict (passed directly, bypassing realize_litellm)
        # must not be aliased into the agent — nor mutated by it.
        self.model_map = dict(self.model_map)

    def resolve_model(self) -> str:
        """Map the definition's model selector to a LiteLLM model string.

        A mapped selector wins; an explicit LiteLLM string in ``model`` is used
        verbatim; otherwise ``default_model``. The lookup covers any hashable
        selector (so a ``model_map`` entry always applies if present).
        """
        model = self.agent_def.model
        if model in self.model_map:
            return self.model_map[model]
        return model or self.default_model

    def build_messages(self, input_data: Any) -> list[dict]:
        """Build the chat messages: persona (+ return-contract instruction) then input."""
        system = self.agent_def.prompt or self.agent_def.description or ""
        schema = self.agent_def.returns.schema()
        if schema:
            system = (system + "\n\n" + render_json_return_instruction(schema)).strip()
        user = input_data if isinstance(input_data, str) else _to_user_text(input_data)
        messages: list[dict] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": user})
        return messages

    def build_kwargs(self, input_data: Any) -> dict:
        """Build the ``litellm.completion`` kwargs (model, messages, response_format)."""
        kwargs: dict[str, Any] = {
            "model": self.resolve_model(),
            "messages": self.build_messages(input_data),
        }
        schema = self.agent_def.returns.schema()
        if schema and self.use_response_format:
            kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "return_contract", "schema": schema},
            }
        return kwargs

    def execute(
        self, input_data: Any, context: Any = None
    ) -> tuple[Any, dict[str, Any]]:
        """Run the agent over ``input_data``; return ``(artifact, info)`` (aw protocol).

        ``context`` is accepted for ``aw.AgenticStep`` compatibility and ignored by
        this backend. If a provider rejects the structured ``response_format``, the
        call is retried once **without** it — the schema is still requested via the
        system-prompt instruction (the belt-and-suspenders fallback made functional).
        """
        completion = self.completion
        if completion is None:
            # Only the real path needs litellm; an injected completion does not.
            check_requirements(
                {"litellm": "litellm"}, feature="realize(backend='litellm')"
            )
            completion = _default_litellm_completion
        kwargs = self.build_kwargs(input_data)
        raw, response_format_used, fallback_error = _complete_with_fallback(
            completion, kwargs
        )
        has_schema = bool(self.agent_def.returns.schema())
        artifact = _extract_litellm_artifact(raw, has_schema=has_schema)
        info = {
            "agent": self.agent_def.name,
            "model": kwargs["model"],
            "backend": "litellm",
            "structured": has_schema,
            "response_format_used": response_format_used,
            "raw": raw,
        }
        # Surface (don't bury) the error that forced the no-response_format retry,
        # so a caller can tell "provider rejected structured output" from a real
        # network/auth failure that we happened to recover from on the retry.
        if fallback_error is not None:
            info["response_format_error"] = repr(fallback_error)
        return artifact, info


def _to_user_text(value: Any) -> str:
    """Render a non-string ``input_data`` as the user message — JSON when possible.

    JSON beats ``repr`` for a schema-aware model (``{"k": "v"}`` not ``{'k': 'v'}``);
    falls back to ``repr`` for anything not JSON-serializable.
    """
    try:
        return json.dumps(value)
    except (TypeError, ValueError):
        return repr(value)


def _complete_with_fallback(
    completion: Callable[..., Any], kwargs: dict
) -> tuple[Any, bool, Optional[Exception]]:
    """Call ``completion``; if ``response_format`` is rejected, retry once without it.

    Returns ``(response, response_format_used, fallback_error)``. The schema is
    still requested via the system-prompt instruction, so dropping
    ``response_format`` on a provider that doesn't support it degrades gracefully
    instead of hard-failing. The ``except`` is deliberately broad — providers
    signal "structured output unsupported" with wildly different exception types —
    but the caught error is **returned** (not swallowed) so ``execute`` can record
    it in ``info['response_format_error']``: a transient network/auth failure on
    the first call that the retry happens to mask stays observable.
    """
    if "response_format" not in kwargs:
        return completion(**kwargs), False, None
    try:
        return completion(**kwargs), True, None
    except Exception as error:
        retry = {k: v for k, v in kwargs.items() if k != "response_format"}
        return completion(**retry), False, error


def _default_litellm_completion(**kwargs: Any) -> Any:
    """Call the real ``litellm.completion`` (imported lazily)."""
    from litellm import completion

    return completion(**kwargs)


def _extract_litellm_artifact(raw: Any, *, has_schema: bool) -> Any:
    """Pull the assistant content from an OpenAI-style response; JSON-parse if structured."""
    content = _litellm_content(raw)
    if content is None:
        return raw
    if has_schema:
        parsed = _try_json(content)
        if parsed is not None:
            return parsed
    return content


def _litellm_content(raw: Any) -> Optional[str]:
    """Extract ``choices[0].message.content`` from a LiteLLM ModelResponse or dict."""
    choices = getattr(raw, "choices", None)
    if choices is None and isinstance(raw, dict):
        choices = raw.get("choices")
    if not choices:
        return None
    first = choices[0]
    message = getattr(first, "message", None)
    if message is None and isinstance(first, dict):
        message = first.get("message")
    if message is None:
        return None
    content = getattr(message, "content", None)
    if content is None and isinstance(message, dict):
        content = message.get("content")
    return content


def _try_json(content: Any) -> Any:
    """Best-effort parse of JSON content, tolerating a ```` ```json ```` fenced block.

    Tries, in order: the raw string; the fenced block's body (handling both a
    newline after the language tag and the malformed no-newline form); and finally
    the *first top-level* depth-balanced ``{...}`` / ``[...]`` span embedded in
    prose. Returns ``None`` on non-strings or when nothing parses.

    The span step uses :func:`coact.util.first_balanced_span`, not a naive
    ``find``/``rfind`` pair: the latter mismatched openers/closers, so
    ``'{found: [1,2,3]}'`` (an invalid object) wrongly yielded the nested
    ``[1,2,3]``, and a trailing stray ``}`` made a valid object unparseable.
    """
    if not isinstance(content, str):
        return None
    stripped = content.strip()

    candidates: list[str] = [stripped]
    if stripped.startswith("```"):
        body = stripped[3:]
        body = body.rsplit("```", 1)[0]  # drop the closing fence
        if "\n" in body:
            # the first line is the (optional) language tag; the rest is the payload
            candidates.append(body.split("\n", 1)[1])
        candidates.append(body)  # no-newline form, e.g. ```json{...}

    for candidate in candidates:
        try:
            return json.loads(candidate)
        except (ValueError, TypeError):
            continue
    # last resort: the earliest-starting top-level balanced span (object or
    # array), parsed as-is. Only that one value is tried — extracting a nested
    # fragment from an unparseable span would violate the return contract.
    best_start: Optional[int] = None
    best_span: Optional[str] = None
    for opener, closer in (("{", "}"), ("[", "]")):
        span = first_balanced_span(stripped, opener, closer)
        if span is None:
            continue
        start = stripped.find(opener)
        if best_start is None or start < best_start:
            best_start, best_span = start, span
    if best_span is not None:
        try:
            return json.loads(best_span)
        except (ValueError, TypeError):
            return None
    return None


def realize_litellm(
    target: RealizeTarget,
    *,
    model_map: Optional[dict] = None,
    default_model: str = DEFAULT_MODEL,
    completion: Optional[Callable[..., Any]] = None,
    use_response_format: bool = True,
    policy: Optional[CompletionPolicy] = None,
) -> RunnableLLMAgent:
    """Realize one agent as a provider-agnostic :class:`RunnableLLMAgent` (via LiteLLM).

    ``model_map`` overrides how coact model selectors (``sonnet``/``opus``/``haiku``)
    map to LiteLLM model strings — point them at any provider to prove portability.
    """
    agents = coerce_agents(target, policy=policy)
    if len(agents) != 1:
        raise ValueError(
            f"backend='litellm' realizes exactly one agent; got {len(agents)}. "
            "Realize each separately (topology is out of scope — DECISIONS D8)."
        )
    return RunnableLLMAgent(
        agent_def=agents[0],
        model_map=dict(model_map) if model_map else dict(DEFAULT_MODEL_MAP),
        default_model=default_model,
        completion=completion,
        use_response_format=use_response_format,
    )


backends.register("litellm", realize_litellm)
