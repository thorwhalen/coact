"""NL-description → IntegrationSpec — the **opt-in LLM ingress** for PUBLISH.

:func:`coact.integration.integration_spec_from` is the *mechanical* ingress: it
turns ``'module:function'`` refs / callables / skills into an
:class:`~coact.integration.IntegrationSpec` with **zero** LLM (DECISIONS D10).
This module is the *opt-in* LLM path — it refines a natural-language description
of a desired integration into a **draft** ``IntegrationSpec`` (name, description,
proposed tools with input JSON schemas), routing generation through ``aix``
(provider-agnostic, per the route-through-aix policy) via ``oa``'s
prompt-as-function machinery.

D10 is upheld two ways: (1) nothing on a mechanical path imports this module, and
(2) ``oa``/``aix`` are imported **lazily inside** the entry function, so
``import coact`` pulls in neither and a missing backend raises an actionable
``ImportError`` rather than imposing a hard dependency.

The result is a *draft*: each tool is *proposed* (no importable handler) unless
the description named existing code. Binding proposed tools to real
``module:function`` handlers — or supplying them — is the user's next step before
a runnable ``.mcpb`` can be built (coact writes the design; the user owns the
code, mirroring the D8/D13 scaffold philosophy).
"""

from __future__ import annotations

import json
import re
from typing import Any, Callable, Optional

from coact.integration import IntegrationSpec, ToolSpec
from coact.util import check_requirements, first_balanced_span, to_kebab_case

LLMPromptFunc = Callable[..., str]

#: The default integration-authoring prompt. A single ``{description}`` placeholder
#: (no other ``{}`` — the JSON shape is described in prose so ``oa``'s
#: ``str.format`` embodier sees exactly one field).
_INTEGRATION_AUTHORING_TEMPLATE = """\
You are an expert architect of AI-chatbot integrations (MCP servers).

Turn the natural-language description below into a structured plan for an
integration that exposes a small set of well-designed tools.

Respond with ONLY a single JSON object (no prose, no markdown fences). The JSON
object must have exactly these keys:
- "name": a short kebab-case name for the integration (string).
- "description": one sentence summarizing what the integration does (string).
- "tools": an array of tool objects. Each tool object has:
    - "name": a snake_case verb_noun tool name (for example get_weather), string.
    - "description": what the tool does, when to use it, and key boundaries or
      examples. Tool naming and description quality dominate reliability — make
      each one precise and unambiguous (string).
    - "input_schema": a JSON Schema (draft 2020-12) describing the tool's input —
      type object, a properties map, and a required list where appropriate.
    - "handler": a "module:function" reference ONLY if the description explicitly
      names existing importable code for this tool; otherwise null.
- "resources": an array of short names for readable data resources (or empty).
- "prompts": an array of short names for templated workflows (or empty).

Design guidance:
- Prefer a few well-named, task-aligned tools over many overlapping ones.
- Keep input schemas minimal and typed; mark genuinely-required fields required.

Natural-language description of the desired integration:
{description}
"""

#: Per-target authoring-prompt library. coact owns these templates as the SSOT
#: (one entry per publish target — extend as targets land). ``pyrompt`` is the
#: recommended place to *manage and iterate* on authoring prompts; load one there
#: and pass it via ``prompt_template=`` to override the default used here.
DFLT_AUTHORING_PROMPTS: dict[str, str] = {
    "integration": _INTEGRATION_AUTHORING_TEMPLATE,
}


def integration_spec_from_description(
    description: str,
    *,
    llm: Any = None,
    model: Optional[str] = None,
    name: Optional[str] = None,
    version: str = "0.1.0",
    author: Optional[str] = None,
    prompt_template: Optional[str] = None,
    infer_tool_schemas: bool = True,
) -> IntegrationSpec:
    """Refine a natural-language ``description`` into a **draft** IntegrationSpec.

    The opt-in LLM ingress (DECISIONS D10): generation is routed through ``aix``
    (provider-agnostic) by default, via ``oa``'s prompt-as-function machinery.

    Args:
        description: What the integration should do, in plain language.
        llm: The LLM backend. ``None`` → ``aix.chat`` (the default, multi-provider);
            a ``callable(prompt, **kwargs) -> str`` is used as-is (handy for tests);
            a ``str`` is treated as a model name passed to ``aix.chat``.
        model: Explicit model id (overrides a model-name ``llm``); ``None`` lets the
            backend resolve its own configured default.
        name: Force the integration name (else the model proposes one). Kebab-cased.
        version: Spec version string.
        author: Optional author name recorded on the spec.
        prompt_template: Override the authoring prompt (e.g. one managed in
            ``pyrompt``). Must contain a single ``{description}`` placeholder.
        infer_tool_schemas: When a proposed tool lacks an ``input_schema``, infer
            one from its description via ``oa.infer_schema_from_verbal_description``
            (aix-backed). Best-effort — failures leave the schema ``None``.

    Returns:
        An :class:`~coact.integration.IntegrationSpec` whose ``tool_specs`` hold the
        proposed tools. Tools the description bound to existing code become runnable
        refs (``spec.runnable_refs()``); the rest are design drafts to bind later.

    Example (offline, with an injected backend):

    >>> reply = (
    ...     '{"name": "wx", "description": "weather",'
    ...     ' "tools": [{"name": "get_weather", "description": "lookup",'
    ...     ' "input_schema": {"type": "object", "properties": {"city":'
    ...     ' {"type": "string"}}}, "handler": null}]}'
    ... )
    >>> spec = integration_spec_from_description("a weather tool", llm=lambda p, **k: reply)
    >>> spec.name, [t.name for t in spec.tool_specs], spec.runnable_refs()
    ('wx', ['get_weather'], [])
    """
    if not isinstance(description, str) or not description.strip():
        raise ValueError("description must be a non-empty string")
    # `oa` is used on every path; `aix` only backs the default (None / model-name)
    # path — an injected callable needs neither aix installed nor a provider call.
    reqs = {"oa": "oa"}
    if not callable(llm):
        reqs["aix"] = "aix"
    check_requirements(reqs, feature="nl-ingress (NL -> IntegrationSpec)")

    from oa.tools import prompt_function  # lazy: D10 — no LLM dep on import

    prompt_func, eff_model = _resolve_backend(llm, model)
    template = prompt_template or DFLT_AUTHORING_PROMPTS["integration"]

    extract = prompt_function(
        template,
        prompt_func=prompt_func,
        prompt_func_kwargs={"model": eff_model},
    )
    raw = extract(description=description)
    data = _parse_json_object(raw)
    if data is None:
        raise ValueError(
            "NL ingress could not parse a JSON IntegrationSpec from the LLM reply. "
            "Try a more specific description or a different model (llm=...)."
        )
    return _spec_from_extracted(
        data,
        name=name,
        version=version,
        author=author,
        prompt_func=prompt_func,
        model=eff_model,
        infer_tool_schemas=infer_tool_schemas,
    )


def _resolve_backend(
    llm: Any, model: Optional[str]
) -> tuple[LLMPromptFunc, Optional[str]]:
    """Resolve ``(prompt_func, model)`` — default to ``aix.chat``; honor injection."""
    if callable(llm):
        return llm, model
    if isinstance(llm, str):  # a model name
        return _aix_chat(), (model or llm)
    return _aix_chat(), model  # None -> aix.chat with the given (or default) model


def _aix_chat() -> LLMPromptFunc:
    """The ``aix.chat`` callable (lazy import — keeps coact provider-free at import)."""
    from aix import chat

    return chat


def _spec_from_extracted(
    data: dict,
    *,
    name: Optional[str],
    version: str,
    author: Optional[str],
    prompt_func: LLMPromptFunc,
    model: Optional[str],
    infer_tool_schemas: bool,
) -> IntegrationSpec:
    """Coerce the LLM's (untrusted) extracted dict into a draft :class:`IntegrationSpec`.

    Every field is coerced defensively: the model may return a number/list/object
    where a string was asked for, so ``.strip()``/``to_kebab_case`` never see a
    non-string, and a bare-string ``resources``/``prompts`` is wrapped (not
    iterated character-by-character).
    """
    spec_name = to_kebab_case(name or _as_str(data.get("name")) or "integration")
    description = _as_str(data.get("description")).strip()

    tool_specs: list[ToolSpec] = []
    refs: list[str] = []
    for entry in data.get("tools") or []:
        if not isinstance(entry, dict):
            continue
        tname = _as_str(entry.get("name")).strip()
        if not tname:
            continue
        tdesc = _as_str(entry.get("description")).strip()
        schema = entry.get("input_schema")
        if not isinstance(schema, dict):
            schema = None
        handler = entry.get("handler")
        handler = handler if _looks_like_ref(handler) else None
        if schema is None and infer_tool_schemas:
            hint = _as_str(entry.get("input_description")) or tdesc
            if hint:
                schema = _infer_tool_schema(hint, prompt_func=prompt_func, model=model)
        tool_specs.append(
            ToolSpec(
                name=tname, description=tdesc, input_schema=schema, handler=handler
            )
        )
        if handler:
            refs.append(handler)

    resources = _as_str_list(data.get("resources"))
    prompts = _as_str_list(data.get("prompts"))
    return IntegrationSpec(
        name=spec_name,
        description=description,
        version=version,
        tools=refs,
        resources=resources,
        prompts=prompts,
        tool_specs=tool_specs,
        author=author,
        source="nl-description",
    )


def _infer_tool_schema(
    input_description: str, *, prompt_func: LLMPromptFunc, model: Optional[str]
) -> Optional[dict]:
    """Best-effort input JSON Schema from a tool's prose description (aix-backed).

    Wraps ``oa.infer_schema_from_verbal_description`` (now backend-injectable);
    any failure degrades to ``None`` so a flaky per-tool inference never aborts the
    whole draft.
    """
    try:
        from oa.tools import infer_schema_from_verbal_description

        result = infer_schema_from_verbal_description(
            input_description, prompt_func=prompt_func, model=model
        )
    except Exception:  # noqa: BLE001 - inference is optional; degrade gracefully
        return None
    if not isinstance(result, dict):
        return None
    props = result.get("properties")
    if not isinstance(props, dict):
        return None
    return {"type": result.get("type", "object"), "properties": props}


def _looks_like_ref(value: Any) -> bool:
    """True if ``value`` looks like an importable ``'module:function'`` ref."""
    return (
        isinstance(value, str)
        and ":" in value
        and " " not in value.strip()
        and not value.strip().startswith(":")
    )


def _as_str(value: Any) -> str:
    """Coerce an LLM-supplied scalar field to a string (untrusted output may not be)."""
    if isinstance(value, str):
        return value
    return "" if value is None else str(value)


def _as_str_list(value: Any) -> list[str]:
    """Coerce an LLM-supplied field to a list of non-empty strings.

    A bare string is *wrapped* (not iterated character-by-character); a list/tuple
    is element-coerced and emptied of blanks; anything else degrades sensibly.
    """
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, (list, tuple)):
        return [s for s in (_as_str(v).strip() for v in value) if s]
    coerced = _as_str(value).strip()
    return [coerced] if coerced else []


def _parse_json_object(text: Any) -> Optional[dict]:
    """Tolerantly pull a JSON object out of an LLM reply.

    Tries, in order, the whole stripped reply, a fenced ```` ```json … ``` ```` body,
    then each top-level brace-balanced ``{…}`` span (string-aware, via
    :func:`coact.util.first_balanced_span`) — so a reply whose real JSON is preceded
    by brace-bearing prose still parses (a single-span parse would wrongly seize the
    first, invalid, fragment). Returns ``None`` when no JSON *object* is recoverable.
    """
    if not isinstance(text, str):
        return None
    stripped = text.strip()
    candidates = [stripped]
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", stripped, re.DOTALL)
    if fence:
        candidates.append(fence.group(1))
    candidates.extend(_iter_balanced_objects(stripped))
    for candidate in candidates:
        try:
            obj = json.loads(candidate)
        except (ValueError, TypeError):
            continue
        if isinstance(obj, dict):
            return obj
    return None


def _iter_balanced_objects(s: str):
    """Yield each top-level brace-balanced ``{…}`` substring of ``s``, left to right."""
    i = 0
    while i < len(s):
        start = s.find("{", i)
        if start < 0:
            return
        span = first_balanced_span(s[start:], "{", "}")
        if span is None:
            return
        yield span
        i = start + len(span)
