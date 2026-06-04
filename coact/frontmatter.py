"""The additive ``coact:`` SKILL.md frontmatter convention and its validator.

COACT_SPEC §4 / DECISIONS D1. The standard SKILL.md frontmatter (``name``,
``description``) does not carry what COMPLETE needs to derive tools, model, MCP,
or a return contract. ``coact`` defines an **optional, additive** ``coact:``
block (snake_case interior) that a skill author — or coact itself — fills in so
the skill→agent lift is mechanical and reproducible (SSOT for the extras)::

    coact:
      tools: [Read, Grep, Glob]
      model: sonnet
      memory: project
      mcp:
        - module: ov.analyzers
          functions: [score_contrast, find_tap_targets]
      returns:
        schema_ref: ov.schemas:UxFindings
        description: Usability findings for the captured bundle
      consumes: evidence_bundle
      persona: |
        You are a meticulous UX analyst...

The block is ignored by other tools (a skill carrying it is still a valid plain
SKILL.md). coact reads it from the **raw** frontmatter because
``skill.SkillMeta`` only retains the standard keys — so this module parses the
SKILL.md text directly rather than going through ``Skill.meta``.

The validator is registered into ``skill.create.validators`` (additive) and also
exposed via a ``skill.validators`` entry point, so ``skill validate`` checks the
block without coact having to be the entry point.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from skill.base import Skill, parse_frontmatter

from coact.base import ReturnContract

#: The single namespaced frontmatter key coact reads/writes.
COACT_KEY = "coact"

_VALID_MODELS = {"sonnet", "opus", "haiku", "inherit"}
_VALID_MEMORY = {"user", "project", "local"}
_KNOWN_KEYS = {
    "tools",
    "disallowed_tools",
    "model",
    "memory",
    "permission_mode",
    "skills",
    "mcp",
    "returns",
    "consumes",
    "persona",
}


@dataclass
class CoactMeta:
    """The parsed ``coact:`` block (every field optional; all default to absent).

    >>> m = CoactMeta.from_frontmatter({'coact': {'model': 'opus', 'tools': ['Read']}})
    >>> m.model, m.tools, m.is_empty()
    ('opus', ['Read'], False)
    >>> CoactMeta.from_frontmatter({'name': 'x'}).is_empty()
    True
    """

    tools: Optional[list[str]] = None
    disallowed_tools: list[str] = field(default_factory=list)
    model: Optional[str] = None
    memory: Optional[str] = None
    permission_mode: Optional[str] = None
    skills: list[str] = field(default_factory=list)
    mcp: list[dict] = field(default_factory=list)
    returns: Optional[dict] = None
    consumes: Optional[str] = None
    persona: Optional[str] = None

    @classmethod
    def from_frontmatter(cls, meta: dict) -> "CoactMeta":
        """Build from a full frontmatter dict (reads the ``coact`` sub-mapping)."""
        block = (meta or {}).get(COACT_KEY) or {}
        if not isinstance(block, dict):
            return cls()
        return cls(
            tools=block.get("tools"),
            disallowed_tools=block.get("disallowed_tools") or [],
            model=block.get("model"),
            memory=block.get("memory"),
            permission_mode=block.get("permission_mode"),
            skills=block.get("skills") or [],
            mcp=block.get("mcp") or [],
            returns=block.get("returns"),
            consumes=block.get("consumes"),
            persona=block.get("persona"),
        )

    def is_empty(self) -> bool:
        """True when the block carries no author-provided information."""
        return self == CoactMeta()

    def return_contract(self) -> ReturnContract:
        """The author-pinned :class:`~coact.base.ReturnContract`, if any."""
        return ReturnContract.from_dict(self.returns)


def parse_coact_meta(source: str | Path | Skill | dict) -> CoactMeta:
    """Parse a :class:`CoactMeta` from a SKILL.md path/text/``Skill``/frontmatter dict.

    Accepts the several shapes coact callers have on hand:

    - a :class:`~skill.base.Skill` (uses its ``source_path`` to re-read the raw
      frontmatter, since ``Skill.meta`` drops the ``coact`` key);
    - a filesystem path to a skill directory or a SKILL.md file;
    - raw SKILL.md text;
    - an already-parsed frontmatter dict.

    >>> parse_coact_meta("---\\nname: x\\ncoact:\\n  model: haiku\\n---\\nbody").model
    'haiku'
    """
    if isinstance(source, CoactMeta):  # idempotent convenience
        return source
    if isinstance(source, dict):
        return CoactMeta.from_frontmatter(source)
    if isinstance(source, Skill):
        if source.source_path is not None:
            text = (Path(source.source_path) / "SKILL.md").read_text()
            return CoactMeta.from_frontmatter(parse_frontmatter(text)[0])
        return CoactMeta()  # no path -> coact block was not retained; nothing to read
    text = _read_skill_md_text(source)
    return CoactMeta.from_frontmatter(parse_frontmatter(text)[0])


def _read_skill_md_text(source: str | Path) -> str:
    """Return SKILL.md text given a directory, a file path, or the text itself."""
    p = Path(source)
    try:
        if p.is_dir():
            return (p / "SKILL.md").read_text()
        if p.is_file():
            return p.read_text()
    except OSError:
        pass
    return str(source)


def validate_coact_block(skill_or_meta: Skill | dict) -> list[str]:
    """Validate a ``coact:`` block, returning issue strings (empty = valid/absent).

    Additive: a skill with no ``coact:`` block passes trivially. Checks key
    spelling, ``model``/``memory`` enums, ``mcp`` entry shape, and that
    ``returns`` carries exactly one of ``schema_ref``/``json_schema``.

    >>> validate_coact_block({'coact': {'model': 'gpt-4'}})
    ["coact.model: 'gpt-4' is not one of sonnet, opus, haiku, inherit"]
    >>> validate_coact_block({'coact': {'mcp': [{'functions': ['f']}]}})
    ["coact.mcp[0]: missing required 'module'"]
    >>> validate_coact_block({'name': 'ok'})
    []
    """
    if isinstance(skill_or_meta, Skill):
        meta = (
            parse_frontmatter(
                (Path(skill_or_meta.source_path) / "SKILL.md").read_text()
            )[0]
            if skill_or_meta.source_path is not None
            else {}
        )
    else:
        meta = skill_or_meta or {}

    block = meta.get(COACT_KEY)
    if block is None:
        return []
    issues: list[str] = []
    if not isinstance(block, dict):
        return [f"coact: block must be a mapping, got {type(block).__name__}"]

    for key in block:
        if key not in _KNOWN_KEYS:
            issues.append(
                f"coact.{key}: unknown key (known: {', '.join(sorted(_KNOWN_KEYS))})"
            )

    model = block.get("model")
    if model is not None and model not in _VALID_MODELS:
        issues.append(
            f"coact.model: {model!r} is not one of sonnet, opus, haiku, inherit"
        )

    memory = block.get("memory")
    if memory is not None and memory not in _VALID_MEMORY:
        issues.append(f"coact.memory: {memory!r} is not one of user, project, local")

    for list_key in ("tools", "disallowed_tools", "skills"):
        val = block.get(list_key)
        if val is not None and not _is_list_of_str(val):
            issues.append(f"coact.{list_key}: must be a list of strings")

    mcp = block.get("mcp")
    if mcp is not None:
        if not isinstance(mcp, list):
            issues.append("coact.mcp: must be a list of {module, functions} entries")
        else:
            for i, entry in enumerate(mcp):
                if not isinstance(entry, dict):
                    issues.append(f"coact.mcp[{i}]: must be a mapping")
                    continue
                if not entry.get("module"):
                    issues.append(f"coact.mcp[{i}]: missing required 'module'")

    returns = block.get("returns")
    if returns is not None:
        if not isinstance(returns, dict):
            issues.append("coact.returns: must be a mapping")
        else:
            has_ref = bool(returns.get("schema_ref") or returns.get("ref"))
            has_inline = bool(returns.get("json_schema"))
            if has_ref and has_inline:
                issues.append(
                    "coact.returns: provide only one of 'schema_ref' or 'json_schema'"
                )
            elif not has_ref and not has_inline:
                issues.append(
                    "coact.returns: needs one of 'schema_ref' or 'json_schema'"
                )

    return issues


def _is_list_of_str(val: Any) -> bool:
    return isinstance(val, list) and all(isinstance(x, str) for x in val)


def _coact_validator(skill: Skill) -> list[str]:
    """``skill.create.validators`` adapter: validate the ``coact:`` block of a Skill."""
    return validate_coact_block(skill)


def register_validator() -> None:
    """Register the coact-block validator into ``skill.create.validators`` (idempotent)."""
    from skill.create import validators

    validators.register("coact_frontmatter", _coact_validator)
