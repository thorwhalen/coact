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

from dataclasses import dataclass, field
from typing import Any, Literal, Optional

# Re-exported: schema resolution lives in coact.schema (a separable concern), but
# ReturnContract.schema() and several modules import it from here historically.
from coact.schema import resolve_schema_ref

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
