"""COMPLETE — lift a ``.claude/skills/`` skill into a ``.claude/agents/`` definition.

COACT_SPEC §5. Given a skill, synthesize the §3.2 "extras envelope" (persona,
return contract, tool allowlist, model, memory, …) and produce an
:class:`~coact.base.AgentDefinition` that **references** the skill (never copies
it — §3.3). This is the mechanical, **no-LLM** path (DECISIONS D10): it reads the
author's ``coact:`` block plus an injected :class:`~coact.policy.CompletionPolicy`
and *reports what it guessed* via :class:`~coact.base.AgentPlan` provenance — it
never decides silently.

Two entry points (progressive disclosure: dry-run first):

- :func:`plan_completion` — returns an :class:`AgentPlan` (the proposed agent +
  per-field provenance + warnings) **without** writing anything.
- :func:`complete` — returns the :class:`AgentDefinition` (the plan's agent).
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Optional, Union

from skill.base import Skill
from skill.stores import LocalSkillStore
from skill.util import find_project_root

from coact.base import (
    AgentDefinition,
    AgentPlan,
    FieldProvenance,
    resolve_schema_ref,
)
from coact.frontmatter import parse_coact_meta
from coact.policy import CompletionPolicy, default_policy
from coact.synthesis import synthesize_persona, synthesize_return_contract

SkillSource = Union[str, Path, Skill]


def plan_completion(
    source: SkillSource,
    *,
    policy: Optional[CompletionPolicy] = None,
    llm: object = None,
) -> AgentPlan:
    """Plan the skill→agent completion, recording the provenance of every field.

    Accepts a :class:`~skill.base.Skill`, a path to a skill directory / SKILL.md,
    or a skill key/name resolvable in the local store or project skills. Pass an
    optional ``llm`` (any ``callable(str)->str``, an ``aw`` ``StepConfig``, or a
    model name) to *draft* a richer persona — the mechanical path needs none.

    >>> from skill.base import Skill, SkillMeta
    >>> s = Skill(meta=SkillMeta(name='auditor', description='Audit a bundle for issues.'), body='steps')
    >>> plan = plan_completion(s)
    >>> plan.agent.name
    'auditor'
    >>> plan.agent.model  # read-only description with default tools -> haiku
    'haiku'
    >>> any(p.field == 'prompt' for p in plan.provenance)
    True
    """
    policy = policy or default_policy
    skill = resolve_skill(source)
    coact_meta = parse_coact_meta(skill)
    prov: list[FieldProvenance] = []
    warnings: list[str] = []

    name = skill.meta.name
    prov.append(FieldProvenance("name", name, "skill", "skill name"))

    description = skill.meta.description
    prov.append(
        FieldProvenance(
            "description", description, "skill", "reused as delegation trigger"
        )
    )

    # tools (declared-or-heuristic + report) then narrow with denylist.
    tools, tools_reason = policy.infer_tools(skill, coact_meta)
    tools_source = "coact-frontmatter" if coact_meta.tools is not None else "inferred"
    prov.append(FieldProvenance("tools", tools, tools_source, tools_reason))
    if tools_source == "inferred":
        warnings.append(f"tools not declared; {tools_reason}")

    disallowed = list(coact_meta.disallowed_tools)
    if disallowed:
        prov.append(
            FieldProvenance("disallowed_tools", disallowed, "coact-frontmatter", "")
        )

    # skills: source skill + explicit extra references (mechanical graph).
    skills = _unique([name, *coact_meta.skills])
    skills_src = "coact-frontmatter" if coact_meta.skills else "skill"
    prov.append(
        FieldProvenance("skills", skills, skills_src, "source skill + declared refs")
    )

    # model routing from effective tools / description / skill count.
    if coact_meta.model:
        model, model_reason, model_src = coact_meta.model, "pinned", "coact-frontmatter"
    else:
        model, model_reason = policy.choose_model(
            tools=tools, description=description, n_skills=len(skills)
        )
        model_src = "policy"
    prov.append(FieldProvenance("model", model, model_src, model_reason))

    # memory (opt-in).
    if coact_meta.memory:
        memory, mem_reason, mem_src = coact_meta.memory, "pinned", "coact-frontmatter"
    else:
        memory, mem_reason = policy.choose_memory()
        mem_src = "policy" if memory is not None else "default"
    if memory is not None:
        prov.append(FieldProvenance("memory", memory, mem_src, mem_reason))

    permission_mode = coact_meta.permission_mode
    if permission_mode:
        prov.append(
            FieldProvenance("permission_mode", permission_mode, "coact-frontmatter", "")
        )

    # return contract (author-pinned else template) — the most important extra.
    return_contract, rc_src = synthesize_return_contract(skill, coact_meta=coact_meta)
    # Resolve a schema_ref to canonical JSON Schema now (D6), or warn (never crash).
    if return_contract.ref and not return_contract.json_schema:
        resolved = resolve_schema_ref(return_contract.ref)
        if resolved:
            return_contract = replace(return_contract, json_schema=resolved)
        else:
            warnings.append(
                f"return schema_ref {return_contract.ref!r} could not be resolved "
                "to a JSON Schema; the contract carries only the reference."
            )
    prov.append(
        FieldProvenance(
            "returns",
            return_contract.ref or return_contract.json_schema,
            rc_src,
            return_contract.description,
        )
    )

    # persona (author-pinned else template).
    if coact_meta.persona:
        persona, persona_src = coact_meta.persona, "coact-frontmatter"
    else:
        persona, persona_src = synthesize_persona(
            skill,
            return_contract=return_contract,
            tools=tools,
            extra_skills=[s for s in skills if s != name],
            llm=llm,
        )
    prov.append(
        FieldProvenance("prompt", persona, persona_src, "system prompt / persona")
    )

    if coact_meta.consumes:
        prov.append(
            FieldProvenance("consumes", coact_meta.consumes, "coact-frontmatter", "")
        )

    if coact_meta.mcp:
        n = sum(len(e.get("functions", []) or []) for e in coact_meta.mcp)
        warnings.append(
            f"{n} python tool(s) declared in coact: mcp — exposed at realize-time "
            "(backend='mcp'), not embedded in the definition."
        )

    agent = AgentDefinition(
        name=name,
        description=description,
        prompt=persona,
        tools=tools,
        disallowed_tools=disallowed,
        model=model,
        skills=skills,
        memory=memory,
        permission_mode=permission_mode,
        returns=return_contract,
        consumes=coact_meta.consumes,
        source_skill=_skill_key(skill),
    )
    return AgentPlan(agent=agent, provenance=prov, warnings=warnings)


def complete(
    source: SkillSource,
    *,
    policy: Optional[CompletionPolicy] = None,
    llm: object = None,
) -> AgentDefinition:
    """Complete a skill into an :class:`AgentDefinition` (the plan's agent).

    >>> from skill.base import Skill, SkillMeta
    >>> s = Skill(meta=SkillMeta(name='ux', description='Analyze bundles.'), body='steps')
    >>> ad = complete(s)
    >>> ad.name, ad.skills, ('Return contract' in ad.prompt)
    ('ux', ['ux'], True)
    """
    return plan_completion(source, policy=policy, llm=llm).agent


# ---------------------------------------------------------------------------
# Skill resolution
# ---------------------------------------------------------------------------


def resolve_skill(source: SkillSource) -> Skill:
    """Resolve a Skill from an object, a path, or a key/name.

    Resolution order for strings: filesystem path → local store key → project
    ``.claude/skills/<name>``.
    """
    if isinstance(source, Skill):
        return source

    path = Path(source)
    if path.is_dir() and (path / "SKILL.md").exists():
        return Skill.from_path(path)
    if path.is_file() and path.name == "SKILL.md":
        return Skill.from_path(path.parent)

    key = str(source)
    store = LocalSkillStore()
    if key in store:
        return store[key]

    # project .claude/skills/<name>
    root = find_project_root()
    if root is not None:
        candidate = Path(root) / ".claude" / "skills" / key
        if (candidate / "SKILL.md").exists():
            return Skill.from_path(candidate)

    raise FileNotFoundError(
        f"Could not resolve skill {source!r}: not a skill directory, a local "
        f"store key, or a project skill. Looked in the local store and "
        f".claude/skills/."
    )


def _skill_key(skill: Skill) -> Optional[str]:
    """Best-effort canonical key/name for provenance (``source_skill``)."""
    if skill.source_path is not None:
        return skill.source_path.name
    return skill.meta.name or None


def _unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    return [x for x in items if x and not (x in seen or seen.add(x))]
