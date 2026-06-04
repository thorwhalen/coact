"""Tests for the deepened schema_ref resolver: annotation -> typed JSON Schema.

Covers ``coact.base._annotation_to_schema`` and the dataclass / TypedDict
structural builder behind ``resolve_schema_ref`` (offline; no LLM).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, TypedDict

from coact.base import _annotation_to_schema, resolve_schema_ref


# --- annotation -> schema fragment ------------------------------------------


def test_primitive_annotations():
    assert _annotation_to_schema(str) == {"type": "string"}
    assert _annotation_to_schema(int) == {"type": "integer"}
    assert _annotation_to_schema(float) == {"type": "number"}
    assert _annotation_to_schema(bool) == {"type": "boolean"}


def test_optional_unwraps_to_inner_type():
    assert _annotation_to_schema(Optional[int]) == {"type": "integer"}
    assert _annotation_to_schema(int | None) == {"type": "integer"}


def test_union_becomes_anyof():
    out = _annotation_to_schema(int | str)
    assert out == {"anyOf": [{"type": "integer"}, {"type": "string"}]}


def test_list_and_dict_containers():
    assert _annotation_to_schema(list[str]) == {"type": "array", "items": {"type": "string"}}
    assert _annotation_to_schema(list) == {"type": "array"}
    assert _annotation_to_schema(dict) == {"type": "object"}
    assert _annotation_to_schema(dict[str, int]) == {"type": "object"}


def test_unknown_annotation_is_permissive():
    assert _annotation_to_schema(object) == {}


# --- dataclass resolution (typed properties + required) ---------------------


@dataclass
class _Finding:
    severity: str
    score: int
    tags: list[str]
    note: Optional[str] = None
    extras: dict = field(default_factory=dict)


def test_dataclass_resolves_to_typed_properties_and_required():
    schema = resolve_schema_ref(f"{__name__}:_Finding")
    assert schema["type"] == "object"
    props = schema["properties"]
    assert props["severity"] == {"type": "string"}
    assert props["score"] == {"type": "integer"}
    assert props["tags"] == {"type": "array", "items": {"type": "string"}}
    assert props["note"] == {"type": "string"}  # Optional[str] -> string
    assert props["extras"] == {"type": "object"}
    # fields without a default are required; defaulted ones are not
    assert schema["required"] == ["severity", "score", "tags"]


def test_nested_dataclass_recurses_one_level():
    @dataclass
    class _Outer:
        item: _Finding
        count: int

    # _Outer must be importable by ref; register it on this module
    globals()["_Outer"] = _Outer
    schema = resolve_schema_ref(f"{__name__}:_Outer")
    assert schema["properties"]["count"] == {"type": "integer"}
    assert schema["properties"]["item"]["type"] == "object"
    assert "severity" in schema["properties"]["item"]["properties"]


# --- TypedDict resolution ----------------------------------------------------


class _UxFindings(TypedDict):
    summary: str
    issues: list[str]


def test_typeddict_resolves_to_typed_properties_required_by_total():
    schema = resolve_schema_ref(f"{__name__}:_UxFindings")
    assert schema["type"] == "object"
    assert schema["properties"]["summary"] == {"type": "string"}
    assert schema["properties"]["issues"] == {"type": "array", "items": {"type": "string"}}
    # a total=True TypedDict marks all keys required
    assert set(schema["required"]) == {"summary", "issues"}
