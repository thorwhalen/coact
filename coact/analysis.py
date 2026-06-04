"""Analysis utilities — small tools to *see and move between* the layers.

COACT_SPEC §7. Thin tooling around the two transforms:

- :func:`diff` — what extras an agent adds over its source skill (audit drift
  between the SSOT skill and a derived agent).
- :func:`estimate` — the §3.5 / DECISIONS-D9 cost gate: the implied fan-out token
  multiplier of an agent set, flagging interdependent sets where multi-agent is a
  poor fit.
- :func:`inventory` — enumerate a project's reusable AI assets: skills, derived
  agents, and MCP-exposed tools (reuses ``skill`` discovery; adds the agent + MCP
  dimensions).
- :func:`back` — best-effort, **lossy** agent→skill extraction (harvest an ad-hoc
  agent back into reusable procedural knowledge).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from skill.base import Skill, SkillMeta
from skill.util import find_project_root

from coact.base import AgentDefinition
from coact.complete import _resolve_skill, complete
from coact.frontmatter import parse_coact_meta
from coact.realize import _coerce_agents
from coact.stores import AgentStore

# ---------------------------------------------------------------------------
# diff — the §3.2 extras-with-provenance table
# ---------------------------------------------------------------------------

# Which AgentDefinition fields are skill-derived vs agent-only extras.
_SKILL_DERIVED = {"name", "description", "skills"}


@dataclass
class AgentDiff:
    """What a derived agent adds over its source skill."""

    skill_name: str
    agent_name: str
    rows: list[tuple[str, str, str]] = field(default_factory=list)  # field, class, value

    def render(self) -> str:
        """Render the extras table for terminal display."""
        lines = [f"diff: skill {self.skill_name!r} → agent {self.agent_name!r}", ""]
        width = max((len(f) for f, _, _ in self.rows), default=6)
        for fname, cls, value in self.rows:
            shown = value if len(value) <= 60 else value[:57] + "..."
            lines.append(f"  {fname:<{width}}  [{cls}]  {shown}")
        return "\n".join(lines)


def diff(skill: object, agent: object) -> AgentDiff:
    """Show what extras ``agent`` adds over its source ``skill``.

    ``skill`` is any skill source; ``agent`` is an :class:`AgentDefinition`, an
    agent ``*.md`` path, or a skill source (which is completed first).

    >>> from skill.base import Skill, SkillMeta
    >>> s = Skill(meta=SkillMeta(name='ux', description='Analyze bundles.'), body='steps')
    >>> from coact import complete
    >>> d = diff(s, complete(s))
    >>> any(f == 'prompt' and cls.startswith('extra') for f, cls, _ in d.rows)
    True
    """
    sk = _resolve_skill(skill) if not isinstance(skill, Skill) else skill
    ad = agent if isinstance(agent, AgentDefinition) else _coerce_agents(agent)[0]

    rows: list[tuple[str, str, str]] = []
    for fname in (
        "name",
        "description",
        "skills",
        "tools",
        "model",
        "memory",
        "disallowed_tools",
        "permission_mode",
        "consumes",
        "prompt",
        "returns",
    ):
        value = getattr(ad, fname)
        if value in (None, [], "", {}):
            continue
        if fname == "returns":
            if value.is_empty():
                continue
            value = value.description or value.ref or "(inline schema)"
        cls = "from skill" if fname in _SKILL_DERIVED else "extra (agent-only)"
        rows.append((fname, cls, _short(value)))
    return AgentDiff(skill_name=sk.meta.name, agent_name=ad.name, rows=rows)


# ---------------------------------------------------------------------------
# estimate — the cost gate
# ---------------------------------------------------------------------------

# Anthropic's figures: one agent ≈ 4× a chat's tokens; a multi-agent system
# ≈ 15× (an order of magnitude). The multiplier scales toward that ceiling.
_AGENT_FACTOR = 4.0
_FLEET_CEILING = 15.0


@dataclass
class Estimate:
    """The implied cost tradeoff of realizing an agent set as a running fleet."""

    n_agents: int
    interdependent: bool
    shared_skills: list[str]
    token_multiplier_vs_chat: float
    recommendation: str

    def render(self) -> str:
        """Render the cost gate for terminal display."""
        lines = [
            f"estimate: {self.n_agents} agent(s)",
            f"  ~{self.token_multiplier_vs_chat:g}× the tokens of a single chat "
            f"(one agent ≈ {_AGENT_FACTOR:g}×, a fleet ≈ {_FLEET_CEILING:g}×)",
            f"  interdependent: {self.interdependent}"
            + (f" (shared skills: {', '.join(self.shared_skills)})" if self.shared_skills else ""),
            f"  → {self.recommendation}",
        ]
        return "\n".join(lines)


def estimate(agents: object) -> Estimate:
    """Surface the fan-out cost tradeoff for an agent set (DECISIONS D9).

    >>> from coact import AgentDefinition
    >>> a = AgentDefinition(name='a', description='x', skills=['shared'])
    >>> b = AgentDefinition(name='b', description='y', skills=['shared'])
    >>> est = estimate([a, b])
    >>> est.interdependent, est.shared_skills
    (True, ['shared'])
    """
    ads = _coerce_agents(agents)
    n = len(ads)

    # interdependence heuristics: shared skills, or any declared input contract.
    skill_counts: dict[str, int] = {}
    for ad in ads:
        for s in ad.skills:
            skill_counts[s] = skill_counts.get(s, 0) + 1
    shared = sorted(s for s, c in skill_counts.items() if c > 1)
    has_consumes = any(ad.consumes for ad in ads)
    interdependent = bool(shared) or has_consumes

    multiplier = _AGENT_FACTOR if n <= 1 else min(_FLEET_CEILING, _AGENT_FACTOR * n)

    if n <= 1:
        rec = "single agent — cheapest; realize with backend='host'."
    elif interdependent:
        rec = (
            "interdependent set — multi-agent is a POOR fit (shared context / "
            "dependencies erase the isolation benefit). Prefer one host agent "
            "running the skills sequentially (backend='host')."
        )
    else:
        rec = (
            "independent, breadth-first set — a running fleet may pay off if the "
            "task value justifies the spend; otherwise prefer backend='host'."
        )
    return Estimate(
        n_agents=n,
        interdependent=interdependent,
        shared_skills=shared,
        token_multiplier_vs_chat=multiplier,
        recommendation=rec,
    )


# ---------------------------------------------------------------------------
# inventory — a project's reusable AI assets
# ---------------------------------------------------------------------------


@dataclass
class Inventory:
    """One picture of a project's reusable AI assets."""

    project: Path
    skills: list[str] = field(default_factory=list)
    agents: list[str] = field(default_factory=list)
    mcp_tools: list[str] = field(default_factory=list)

    def render(self) -> str:
        """Render the inventory for terminal display."""
        lines = [f"inventory: {self.project}", ""]
        lines.append(f"  skills ({len(self.skills)}): {', '.join(self.skills) or '—'}")
        lines.append(f"  agents ({len(self.agents)}): {', '.join(self.agents) or '—'}")
        lines.append(
            f"  mcp tools ({len(self.mcp_tools)}): {', '.join(self.mcp_tools) or '—'}"
        )
        return "\n".join(lines)


def inventory(project: Path | str | None = None) -> Inventory:
    """Enumerate skills, derived agents, and MCP-exposed tools in a project.

    >>> import tempfile
    >>> inv = inventory(tempfile.mkdtemp())
    >>> inv.skills, inv.agents
    ([], [])
    """
    root = Path(project) if project is not None else (find_project_root() or Path.cwd())
    skills_dir = root / ".claude" / "skills"

    skills: list[str] = []
    mcp_tools: list[str] = []
    if skills_dir.is_dir():
        for child in sorted(skills_dir.iterdir()):
            if not (child / "SKILL.md").exists():
                continue
            skills.append(child.name)
            try:
                meta = parse_coact_meta(child)
            except OSError:
                continue
            for entry in meta.mcp:
                module = entry.get("module")
                for fn in entry.get("functions") or []:
                    mcp_tools.append(f"{child.name}: {module}:{fn}")

    agents_root = root / ".claude" / "agents"
    agents = list(AgentStore(root=agents_root)) if agents_root.exists() else []

    return Inventory(
        project=root, skills=skills, agents=agents, mcp_tools=mcp_tools
    )


# ---------------------------------------------------------------------------
# back — lossy agent → skill extraction
# ---------------------------------------------------------------------------


def back(agent: object) -> Skill:
    """Best-effort, **lossy** agent→skill extraction (harvest an agent into a skill).

    Strips the persona/return-contract envelope down to a reusable skill stub
    (name + description + a pointer to the skills it referenced). The actual
    procedure usually lives in those referenced skills, so this cannot recover
    it — the result is a starting point the user fleshes out, not a faithful
    inverse of COMPLETE.

    >>> from coact import AgentDefinition
    >>> sk = back(AgentDefinition(name='ux', description='Analyze.', skills=['ux', 'shared']))
    >>> sk.meta.name
    'ux'
    >>> 'lossy' in sk.body.lower()
    True
    """
    ad = agent if isinstance(agent, AgentDefinition) else _coerce_agents(agent)[0]
    referenced = [s for s in ad.skills if s != ad.name]
    refs_note = (
        f"\n\nReferenced skills (procedure may live here): {', '.join(referenced)}."
        if referenced
        else ""
    )
    body = (
        f"# {ad.name}\n\n{ad.description}\n\n"
        f"> Extracted from an agent definition (lossy: persona and return "
        f"contract were stripped; the procedure is not recovered).{refs_note}\n\n"
        f"## Instructions\n\n<!-- Flesh out the procedural steps here. -->\n"
    )
    return Skill(meta=SkillMeta(name=ad.name, description=ad.description), body=body)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _short(value: object) -> str:
    text = value if isinstance(value, str) else repr(value)
    return text.replace("\n", " ")
