"""Synthesize a pydantic model class from a coact JSON-Schema return contract.

Needed only where a realization backend's structured-output API wants a *type*
rather than a JSON-Schema dict — currently just the ``crewai`` backend, whose
``Agent.kickoff(response_format=<class>)`` is class-only. The ``langgraph``
backend passes the canonical JSON-Schema dict straight into
``ToolStrategy``/``ProviderStrategy`` and never calls this.

:func:`json_schema_to_model` returns ``None`` (it **never raises**) for any
schema it cannot represent *faithfully* — empty, non-object, or carrying
``$ref``/``anyOf``/``oneOf``/``allOf`` or nested objects — so the caller degrades
to the portable in-prompt return-contract instruction (DECISIONS D6) instead of
fabricating a lossy model. Pydantic is imported **lazily** (it ships with crewai
on the real path), so importing this module is free and does not pull pydantic.
"""

from __future__ import annotations

from typing import Any, Optional

#: JSON-Schema type -> Python type for pydantic field annotations (unknown -> Any).
_JSON_TO_PY: dict[str, Any] = {
    "string": str,
    "integer": int,
    "number": float,
    "boolean": bool,
    "array": list,
    "object": dict,
}


def _is_flat_property(prop: Any) -> bool:
    """True when a property schema maps to one Python type with no nesting.

    Rejects composition (``$ref``/``anyOf``/``oneOf``/``allOf`` — which coact will
    not fake-flatten) and a nested object that declares its own ``properties``
    (that would require a sub-model). A nested object *without* ``properties`` is
    fine (it maps to ``dict``).
    """
    if not isinstance(prop, dict):
        return False
    if prop.keys() & {"$ref", "anyOf", "oneOf", "allOf"}:
        return False
    if prop.get("type") == "object" and prop.get("properties"):
        return False
    return True


def json_schema_to_model(
    schema: dict, *, name: str = "ReturnContract"
) -> Optional[type]:
    """Flat JSON-Schema object -> a pydantic ``BaseModel`` subclass, else ``None``.

    Handles ``{"type": "object", "properties": {...}, "required": [...]}`` whose
    property types are scalars/array/object (``string``->``str``,
    ``integer``->``int``, ``number``->``float``, ``boolean``->``bool``,
    ``array``->``list``, ``object``->``dict``, unknown->``Any``). A property absent
    from ``required`` becomes ``Optional`` with default ``None``. Anything that
    cannot be represented faithfully (non-object root, no properties, or any
    ``$ref``/``anyOf``/``oneOf``/nested-object-with-properties property) returns
    ``None`` so the caller relies on the prompt instruction. Never raises.

    >>> json_schema_to_model({"type": "array", "items": {"type": "string"}}) is None
    True
    >>> json_schema_to_model({}) is None
    True
    >>> json_schema_to_model({"type": "object", "properties": {}}) is None
    True
    """
    if (
        not isinstance(schema, dict)
        or schema.get("type") != "object"
        or not isinstance(schema.get("properties"), dict)
        or not schema["properties"]
    ):
        return None
    properties: dict = schema["properties"]
    if not all(_is_flat_property(p) for p in properties.values()):
        return None
    required = set(schema.get("required") or [])
    try:
        from pydantic import create_model

        fields: dict[str, Any] = {}
        for prop_name, prop in properties.items():
            py_type = _JSON_TO_PY.get(prop.get("type"), Any)
            if prop_name in required:
                fields[prop_name] = (py_type, ...)
            else:
                fields[prop_name] = (Optional[py_type], None)
        return create_model(name, **fields)
    except Exception:
        # pydantic missing, or a field annotation it rejects: degrade to prompt-only.
        return None
