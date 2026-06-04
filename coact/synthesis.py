"""Persona & return-contract synthesis — the two real "extras" of a skill→agent lift.

COACT_SPEC §5.5 / §3.2. A skill body is *procedural*, not a persona, and skills
return *nothing*. The two fields that actually turn a skill into an agent are the
**system prompt (persona/identity)** and the **return contract (consumable
output)**. This module synthesizes both.

This PR ships the **template** path (no LLM, always available, a sound default).
The optional **LLM-assisted** path (a richer persona drafted from the skill body
via an injected facade) is added on top in a later milestone — both paths obey
the same rules: author-pinned ``coact: persona`` / ``coact: returns`` always win
(inspectable, overridable, LLM-assisted-but-not-required, DECISIONS D10).

Crucially the persona **references** the skill by name and instructs the agent to
follow it — it never copies the skill body (point-don't-copy / SSOT, §3.3).
"""

from __future__ import annotations

import json

from skill.base import Skill

from coact.base import ProvenanceSource, ReturnContract
from coact.frontmatter import CoactMeta

#: A generic-but-useful default return schema (used when the author pins none).
DEFAULT_RETURN_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {
            "type": "string",
            "description": "One-paragraph summary of what was done.",
        },
        "result": {"description": "The primary artifact or finding."},
        "status": {"type": "string", "enum": ["ok", "partial", "failed"]},
    },
    "required": ["summary", "status"],
}


def synthesize_return_contract(
    skill: Skill, *, coact_meta: CoactMeta
) -> tuple[ReturnContract, ProvenanceSource]:
    """Choose the agent's return contract: author-pinned, else a template default.

    >>> from skill.base import Skill, SkillMeta
    >>> s = Skill(meta=SkillMeta(name='x', description='y'), body='z')
    >>> rc, src = synthesize_return_contract(s, coact_meta=CoactMeta())
    >>> rc.json_schema['type'], src
    ('object', 'synthesized-template')
    >>> rc2, src2 = synthesize_return_contract(s, coact_meta=CoactMeta(returns={'schema_ref': 'm:N'}))
    >>> rc2.ref, src2
    ('m:N', 'coact-frontmatter')
    """
    if coact_meta.returns:
        return coact_meta.return_contract(), "coact-frontmatter"
    description = (
        f"Result of the {skill.meta.name!r} agent: {skill.meta.description}".rstrip()
    )
    return (
        ReturnContract(json_schema=dict(DEFAULT_RETURN_SCHEMA), description=description),
        "synthesized-template",
    )


def render_return_contract_section(rc: ReturnContract) -> str:
    """Render the human/model-facing "Return contract" markdown for a persona body.

    >>> rc = ReturnContract(json_schema={'type': 'object'}, description='findings')
    >>> 'Return contract' in render_return_contract_section(rc)
    True
    """
    lines = ["## Return contract", ""]
    lines.append(
        "Your final message MUST be consumable by the agent that delegated to "
        "you — return the result in this shape:"
    )
    lines.append("")
    if rc.description:
        lines.append(rc.description)
        lines.append("")
    if rc.json_schema:
        lines.append("```json")
        lines.append(json.dumps(rc.json_schema, indent=2))
        lines.append("```")
    elif rc.ref:
        lines.append(f"Conform to the schema `{rc.ref}`.")
    else:
        lines.append("Return a concise structured summary of the outcome.")
    return "\n".join(lines)


def synthesize_persona(
    skill: Skill,
    *,
    return_contract: ReturnContract,
    tools: list[str] | None = None,
    extra_skills: list[str] | None = None,
) -> tuple[str, ProvenanceSource]:
    """Synthesize the system prompt (persona) for an agent derived from ``skill``.

    The template wraps the skill's intent as an identity, states operating
    invariants, and appends the return contract — while **pointing at** the
    source skill rather than inlining it (§3.3).

    >>> from skill.base import Skill, SkillMeta
    >>> s = Skill(meta=SkillMeta(name='ux-analyst', description='Analyze UX bundles.'), body='steps')
    >>> rc = ReturnContract(json_schema={'type': 'object'}, description='findings')
    >>> persona, src = synthesize_persona(s, return_contract=rc, tools=['Read', 'Grep'])
    >>> 'ux-analyst' in persona and 'Return contract' in persona and src == 'synthesized-template'
    True
    """
    name = skill.meta.name
    description = skill.meta.description.rstrip(".")
    tool_note = (
        f"Stay within your tool allowlist: {', '.join(tools)}."
        if tools
        else "Use only the tools you have been granted."
    )
    skills_clause = f"the `{name}` skill"
    if extra_skills:
        others = ", ".join(f"`{s}`" for s in extra_skills)
        skills_clause = f"the `{name}` skill (and {others})"

    sections = [
        f"You are the **{name}** agent. {description}.",
        "",
        f"You have {skills_clause} loaded — follow its procedure exactly; do not "
        "re-derive or duplicate it. The skill is the single source of truth for "
        "*how* to do the work; you add identity, judgment, and a consumable result.",
        "",
        "## Operating invariants",
        f"- {tool_note}",
        "- Work only on the task delegated to you; stop and return once the "
        "skill's procedure is complete.",
        '- If you cannot complete the task, return status `"failed"` with a short '
        "reason rather than guessing.",
        "",
        render_return_contract_section(return_contract),
    ]
    return "\n".join(sections), "synthesized-template"
