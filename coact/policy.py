"""Completion policy — the injectable model / memory / tool choices COMPLETE stamps.

COACT_SPEC §5.4 / DECISIONS D4. The model, memory, and tool-narrowing choices
are **policy**: injected data, not hardcoded branches, with cascading defaults in
the spirit of ``aw.GlobalConfig`` (sensible defaults; override globally by
constructing a different :class:`CompletionPolicy`, or per-skill via the
``coact:`` block, which always wins over policy). This module imports no LLM and
no ``aw`` — it is a pure mechanical path (DECISIONS D10); the ``aw`` ``StepConfig``
LLM injection used for *optional* persona synthesis lives behind that optional
path in :mod:`coact.synthesis`.

The routing table is data on the dataclass, so users extend it without editing
code (open-closed).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Optional

from skill.base import Skill

from coact.base import MemoryScope, ModelName
from coact.frontmatter import CoactMeta

#: Tools that, taken alone, mark an agent as read-only / explore (→ haiku).
_READ_ONLY_TOOLS = frozenset(
    {"Read", "Grep", "Glob", "WebFetch", "WebSearch", "NotebookRead"}
)


@dataclass(frozen=True)
class CompletionPolicy:
    """Injectable defaults for the §3.2 extras COMPLETE must stamp on a skill.

    >>> p = CompletionPolicy()
    >>> p.choose_model(tools=['Read', 'Grep'], description='Audit the bundle.', n_skills=1)
    ('haiku', 'read-only/explore: tools ⊆ read-only set')
    >>> p.choose_model(tools=['Read', 'Write'], description='Implement the fix.', n_skills=1)[0]
    'sonnet'
    >>> p.choose_model(tools=['Read'], description='Orchestrate the review.', n_skills=1)[0]
    'opus'
    """

    default_model: ModelName = "sonnet"
    default_memory: Optional[MemoryScope] = None  # opt-in; None = no memory
    default_tools: tuple[str, ...] = ("Read", "Grep", "Glob")
    read_only_tools: frozenset[str] = _READ_ONLY_TOOLS
    #: Regex patterns (matched case-insensitively against the description) that
    #: route to opus. Word-bounded so 'plan.' matches but 'designer'/'designate'
    #: don't. Data, not code — extend or replace per policy.
    opus_keywords: tuple[str, ...] = (
        r"orchestrat\w*",
        r"architect\w*",
        r"coordinat\w*",
        r"\bplan(?:ning|s|ned)?\b",
        r"\bdesign(?:s|ing|ed)?\b",
        r"review\w*",
    )
    opus_skill_threshold: int = 3
    #: body substrings that imply the agent writes/edits files.
    write_keywords: tuple[str, ...] = (
        "write",
        "edit",
        "create file",
        "modify",
        "generate",
        "refactor",
    )

    # -- cascade (mirrors aw.GlobalConfig.override) --

    def override(self, **kwargs) -> "CompletionPolicy":
        """Return a new policy with overridden fields (cascading defaults).

        >>> CompletionPolicy().override(default_model='opus').default_model
        'opus'
        """
        return replace(self, **kwargs)

    # -- decisions (each returns (value, reason) so COMPLETE can record provenance) --

    def choose_model(
        self, *, tools: Optional[list[str]], description: str, n_skills: int
    ) -> tuple[ModelName, str]:
        """Route to a model from the effective tools / description / skill count."""
        desc = (description or "").lower()
        # opus: orchestration/architecture, or many skills.
        if any(re.search(pattern, desc) for pattern in self.opus_keywords):
            return "opus", "orchestration/architecture keyword in description"
        if n_skills >= self.opus_skill_threshold:
            return "opus", f"references ≥{self.opus_skill_threshold} skills"
        # haiku: read-only / explore.
        if tools is not None and tools and set(tools) <= self.read_only_tools:
            return "haiku", "read-only/explore: tools ⊆ read-only set"
        return self.default_model, "default worker"

    def choose_memory(self) -> tuple[Optional[MemoryScope], str]:
        """The default memory scope (opt-in; None = no memory)."""
        if self.default_memory is None:
            return None, "default: no memory (least privilege)"
        return self.default_memory, "policy default"

    def infer_tools(
        self, skill: Skill, coact_meta: CoactMeta
    ) -> tuple[list[str], str]:
        """Derive the tool allowlist (declared-or-heuristic + report; DECISIONS D3).

        Precedence: an explicit ``coact: tools`` wins; otherwise a conservative
        heuristic from the skill's resources/body. Never silently guesses — the
        reason is returned for provenance.

        >>> from skill.base import Skill, SkillMeta
        >>> s = Skill(meta=SkillMeta(name='x', description='y'), body='Write the report.')
        >>> tools, why = CompletionPolicy().infer_tools(s, CoactMeta())
        >>> 'Write' in tools and 'Read' in tools
        True
        """
        if coact_meta.tools is not None:
            return list(coact_meta.tools), "declared in coact: tools"

        tools = list(self.default_tools)
        reasons = ["default analysis set"]
        if "scripts" in (skill.resources or {}):
            tools.append("Bash")
            reasons.append("scripts/ present → Bash")
        body = (skill.body or "").lower()
        if any(k in body for k in self.write_keywords):
            for t in ("Write", "Edit"):
                if t not in tools:
                    tools.append(t)
            reasons.append("body implies writing → Write/Edit")
        # de-dupe, preserve order
        seen: set[str] = set()
        ordered = [t for t in tools if not (t in seen or seen.add(t))]
        return ordered, "inferred (" + "; ".join(reasons) + ")"


#: The default policy instance (importable, mutable-by-override).
default_policy = CompletionPolicy()
