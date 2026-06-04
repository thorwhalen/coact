"""JSON Schema resolution — turn a ``module:Name`` ref into a canonical schema.

Extracted from :mod:`coact.base` so that module stays a pure SSOT *data model*
and this one owns the (separable, independently testable) concern of mapping
Python types to JSON Schema (DECISIONS D6: "JSON Schema is canonical; refs
resolve to it"). The public entry point is :func:`resolve_schema_ref`; the
annotation/structural helpers are module-private.

Everything here is **best-effort and provider-agnostic**: a ref that cannot be
imported or mapped yields ``None`` (or a permissive ``{}`` fragment) so callers
warn and fall back rather than crash — no hard pydantic dependency, no LLM
(DECISIONS D10).
"""

from __future__ import annotations

import dataclasses
from typing import Any, Optional


def resolve_schema_ref(ref: str) -> Optional[dict]:
    """Best-effort resolve a ``'module:Name'`` ref to a JSON Schema dict, or ``None``.

    Handles Pydantic models (``model_json_schema``/``schema``), dataclasses, and
    TypedDicts (structural ``{type: object, properties: {...}}``). Provider- and
    pydantic-agnostic: returns ``None`` on any failure so callers can warn and
    fall back rather than crash (DECISIONS D6/D10).

    >>> resolve_schema_ref('coact.base:ReturnContract')['type']
    'object'
    >>> resolve_schema_ref('definitely.not:Real') is None
    True
    """
    try:
        from coact.util import import_object

        obj = import_object(ref)
    except Exception:
        # Best-effort resolution: an unimportable ref → None (DECISIONS D6).
        return None
    # Pydantic v2, then v1.
    for method in ("model_json_schema", "schema"):
        fn = getattr(obj, method, None)
        if callable(fn) and isinstance(obj, type):
            try:
                result = fn()
                if isinstance(result, dict) and result:
                    return result
            except Exception:
                # Not a usable pydantic schema method; fall through to structural.
                pass
    # Dataclass / TypedDict: a structural object schema with *typed* properties
    # (annotations mapped to JSON Schema where recognized; permissive {} otherwise).
    structural = _structural_object_schema(obj)
    if structural is not None:
        return structural
    return None


#: Python annotation → JSON Schema "type" for the primitives we map directly.
#: ``bool`` is listed before ``int`` only for readers — lookup is by identity, and
#: ``bool``/``int`` are distinct keys, so a ``bool`` field maps to ``boolean``.
_PRIMITIVE_JSON_TYPES = {
    str: "string",
    bool: "boolean",
    int: "integer",
    float: "number",
    bytes: "string",
}


def _annotation_to_schema(annotation: Any) -> dict:
    """Map a Python type annotation to a JSON Schema fragment (best-effort).

    Handles primitives, ``Optional[X]`` / ``X | None`` / ``Union`` (anyOf),
    ``list[X]``/``set``/``tuple`` (``array`` with typed ``items``), ``dict``
    (``object``), and nested dataclasses / TypedDicts (one level, recursively).
    Anything unrecognized yields a permissive ``{}`` so resolution never crashes.

    >>> _annotation_to_schema(str)
    {'type': 'string'}
    >>> from typing import Optional
    >>> _annotation_to_schema(Optional[int])
    {'type': 'integer'}
    >>> _annotation_to_schema(list[str])
    {'type': 'array', 'items': {'type': 'string'}}
    """
    import typing

    if annotation is None or annotation is type(None):
        return {}

    origin = typing.get_origin(annotation)
    args = typing.get_args(annotation)
    if origin is not None:
        import types as _types

        is_union = origin is typing.Union or (
            hasattr(_types, "UnionType") and origin is _types.UnionType
        )
        if is_union:
            non_none = [a for a in args if a is not type(None)]
            if len(non_none) == 1:
                return _annotation_to_schema(non_none[0])
            if non_none:
                return {"anyOf": [_annotation_to_schema(a) for a in non_none]}
            return {}
        if origin in (list, set, frozenset, tuple):
            item = args[0] if args and args[0] is not Ellipsis else None
            return (
                {"type": "array", "items": _annotation_to_schema(item)}
                if item is not None
                else {"type": "array"}
            )
        if origin is dict:
            return {"type": "object"}
        return {}

    if isinstance(annotation, type):
        if annotation in _PRIMITIVE_JSON_TYPES:
            return {"type": _PRIMITIVE_JSON_TYPES[annotation]}
        if annotation in (list, set, frozenset, tuple):
            return {"type": "array"}
        if annotation is dict:
            return {"type": "object"}
        nested = _structural_object_schema(annotation)
        if nested is not None:
            return nested
    return {}


def _structural_object_schema(obj: Any) -> Optional[dict]:
    """Build an object JSON Schema (typed properties + ``required``) for a dataclass/TypedDict.

    Returns ``None`` for anything that is neither. Forward-ref string annotations
    are resolved via ``typing.get_type_hints`` when possible (falling back to the
    raw annotation). Required keys come from dataclass fields lacking a default, or
    a TypedDict's ``__required_keys__`` / ``__total__``.
    """
    import typing

    if dataclasses.is_dataclass(obj):
        try:
            hints = typing.get_type_hints(obj)
        except Exception:
            hints = {f.name: f.type for f in dataclasses.fields(obj)}
        properties: dict[str, Any] = {}
        required: list[str] = []
        for f in dataclasses.fields(obj):
            properties[f.name] = _annotation_to_schema(hints.get(f.name, f.type))
            if (
                f.default is dataclasses.MISSING
                and f.default_factory is dataclasses.MISSING
            ):
                required.append(f.name)
        schema: dict[str, Any] = {"type": "object", "properties": properties}
        if required:
            schema["required"] = required
        return schema

    annotations = getattr(obj, "__annotations__", None)
    if annotations and getattr(obj, "__total__", None) is not None:
        try:
            hints = typing.get_type_hints(obj)
        except Exception:
            hints = dict(annotations)
        properties = {
            k: _annotation_to_schema(hints.get(k, v)) for k, v in annotations.items()
        }
        schema = {"type": "object", "properties": properties}
        required_keys = getattr(obj, "__required_keys__", None)
        if required_keys:
            schema["required"] = sorted(required_keys)
        elif getattr(obj, "__total__", False):
            schema["required"] = list(annotations)
        return schema

    return None
