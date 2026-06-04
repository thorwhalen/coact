"""Core data model for coact — the single in-memory representation of an agent.

This module is the spine described in COACT_SPEC §3.1/§5.2: an
:class:`AgentDefinition` is *one* object that can serialize to **both** the
filesystem ``.claude/agents/*.md`` format and the Claude Agent SDK form (see
:mod:`coact.emit`). It is a lossless **superset** of the host subagent schema,
kept independent of the SDK type (DECISIONS D2) so coact's core carries no SDK
or LLM import.

Three dataclasses live here:

- :class:`ReturnContract` — the agent's final-message schema (so a manager can
  deterministically consume its output); the single most important "extra".
- :class:`AgentDefinition` — the SSOT object.
- :class:`AgentPlan` / :class:`FieldProvenance` — the inspectable dry-run result
  of COMPLETE, recording where every synthesized field came from.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from typing import Any, Literal, Optional

#: Host model selector values (the Agent SDK ``model`` literal).
ModelName = Literal["sonnet", "opus", "haiku", "inherit"]
#: Subagent memory scope.
MemoryScope = Literal["user", "project", "local"]

#: Provenance source tags — where a synthesized field's value originated.
ProvenanceSource = Literal[
    "skill",  # taken from the source SKILL.md (name/description/body)
    "coact-frontmatter",  # pinned by the author's `coact:` block
    "policy",  # stamped by the completion policy
    "inferred",  # heuristically derived (e.g. tools from resources)
    "synthesized-template",  # produced by the no-LLM template path
    "synthesized-llm",  # produced by the optional injected LLM
    "default",  # left at the dataclass default
]


@dataclass
class ReturnContract:
    """The agent's return contract: its final-message schema + a human summary.

    Skills return nothing; agents must define a consumable output. The canonical
    form is a JSON Schema dict (portable across realization backends, DECISIONS
    D6). ``ref`` records a ``'module:Name'`` source if the schema was resolved
    from a Pydantic model / dataclass / TypedDict.

    >>> rc = ReturnContract(json_schema={'type': 'object'}, description='findings')
    >>> rc.is_empty()
    False
    >>> ReturnContract().is_empty()
    True
    """

    json_schema: dict = field(default_factory=dict)
    ref: Optional[str] = None
    description: str = ""

    def is_empty(self) -> bool:
        """True when no schema (inline or ref) has been set."""
        return not self.json_schema and not self.ref

    def to_dict(self) -> dict:
        """Serialize to a plain dict (for the agent-md ``coact:`` block), omitting empties."""
        d: dict[str, Any] = {}
        if self.json_schema:
            d["json_schema"] = self.json_schema
        if self.ref:
            d["schema_ref"] = self.ref
        if self.description:
            d["description"] = self.description
        return d

    @classmethod
    def from_dict(cls, d: dict | None) -> "ReturnContract":
        """Parse from a ``coact: returns`` mapping (accepts ``schema_ref`` or ``json_schema``).

        >>> ReturnContract.from_dict({'schema_ref': 'ov.schemas:UxFindings'}).ref
        'ov.schemas:UxFindings'
        """
        if not d:
            return cls()
        return cls(
            json_schema=d.get("json_schema") or {},
            ref=d.get("schema_ref") or d.get("ref"),
            description=d.get("description", ""),
        )

    def schema(self) -> dict:
        """Return the canonical JSON Schema, resolving ``ref`` if needed (else ``{}``).

        Honors DECISIONS D6 ("JSON Schema is canonical; refs resolve to it"): an
        inline ``json_schema`` wins; otherwise a ``module:Name`` ``ref`` is
        resolved best-effort to a schema. Returns ``{}`` when neither is available.

        >>> ReturnContract(json_schema={'type': 'object'}).schema()
        {'type': 'object'}
        >>> 'properties' in ReturnContract(ref='coact.base:ReturnContract').schema()
        True
        """
        if self.json_schema:
            return self.json_schema
        if self.ref:
            return resolve_schema_ref(self.ref) or {}
        return {}


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


@dataclass
class AgentDefinition:
    """The SSOT: one object, two serializations (filesystem md + SDK form).

    Fields mirror the host subagent schema (snake_case here; coact owns the
    mapping to the host's camelCase frontmatter names in :mod:`coact.emit`),
    plus the coact-specific :attr:`returns` / :attr:`consumes`. ``tools=None``
    means *inherit all tools*; an empty list means *no tools* — the distinction
    is preserved.

    >>> ad = AgentDefinition(name='ux-analyst', description='Analyze UX bundles.')
    >>> ad.name, ad.tools, ad.returns.is_empty()
    ('ux-analyst', None, True)
    """

    name: str
    description: str
    prompt: str = ""
    tools: Optional[list[str]] = None
    disallowed_tools: list[str] = field(default_factory=list)
    model: Optional[ModelName] = None
    skills: list[str] = field(default_factory=list)
    memory: Optional[MemoryScope] = None
    mcp_servers: list[Any] = field(default_factory=list)  # names or inline dicts
    permission_mode: Optional[str] = None
    returns: ReturnContract = field(default_factory=ReturnContract)
    consumes: Optional[str] = None
    #: Canonical key/name of the source skill this agent was completed from.
    source_skill: Optional[str] = None


@dataclass
class FieldProvenance:
    """Where one :class:`AgentDefinition` field's value came from (dry-run audit).

    >>> FieldProvenance('model', 'sonnet', 'policy', 'default worker').source
    'policy'
    """

    field: str
    value: Any
    source: ProvenanceSource
    note: str = ""


@dataclass
class AgentPlan:
    """The inspectable result of ``plan_completion``: the agent + its provenance.

    Shows the proposed :class:`AgentDefinition` and, for each field, *why* it has
    its value — so a user can review before any file is written or agent spawned
    (progressive disclosure: dry-run first).
    """

    agent: AgentDefinition
    provenance: list[FieldProvenance] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def render(self) -> str:
        """Render a human-readable provenance table for terminal display.

        >>> plan = AgentPlan(
        ...     agent=AgentDefinition(name='x', description='y'),
        ...     provenance=[FieldProvenance('model', 'sonnet', 'policy', 'worker')],
        ... )
        >>> 'model' in plan.render() and 'policy' in plan.render()
        True
        """
        lines = [f"AgentPlan for {self.agent.name!r}", ""]
        width = max((len(p.field) for p in self.provenance), default=5)
        for p in self.provenance:
            value = p.value
            shown = value if isinstance(value, str) else repr(value)
            if isinstance(shown, str) and len(shown) > 60:
                shown = shown[:57] + "..."
            note = f"  — {p.note}" if p.note else ""
            lines.append(f"  {p.field:<{width}}  [{p.source}]  {shown}{note}")
        if self.warnings:
            lines.append("")
            lines.append("Warnings:")
            lines.extend(f"  ! {w}" for w in self.warnings)
        return "\n".join(lines)
