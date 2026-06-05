"""Pure helpers for coact with no internal coact imports.

Small, reusable string/name utilities and a thin ``check_requirements`` helper
for the optional-dependency backends (Agent SDK, py2mcp/FastMCP, an LLM
provider). Kept dependency-free so every other coact module can import it.
"""

from __future__ import annotations

import re
from importlib import import_module
from pathlib import Path
from typing import Any, Optional


def to_kebab_case(name: str) -> str:
    """Convert CamelCase / snake_case / spaces to kebab-case.

    >>> to_kebab_case('UxAnalyst')
    'ux-analyst'
    >>> to_kebab_case('ux_analyst')
    'ux-analyst'
    >>> to_kebab_case('already-kebab')
    'already-kebab'
    """
    s = re.sub(r"(?<=[a-z0-9])([A-Z])", r"-\1", name)
    s = re.sub(r"[\s_]+", "-", s)
    return s.lower().strip("-")


def to_snake_case(name: str) -> str:
    """Convert CamelCase / kebab-case / spaces to snake_case.

    >>> to_snake_case('UxAnalyst')
    'ux_analyst'
    >>> to_snake_case('ux-analyst')
    'ux_analyst'
    """
    s = re.sub(r"(?<=[a-z0-9])([A-Z])", r"_\1", name)
    s = re.sub(r"[\s-]+", "_", s)
    return s.lower().strip("_")


def agent_filename(name: str) -> str:
    """Return the safe ``<name>.md`` filename for an agent, rejecting unsafe names.

    Agent names become files under ``.claude/agents/``; a name carrying a path
    separator or ``..`` could escape that directory (CWE-22 path traversal) on
    write *or* read. Names must be a bare filename stem. Raises ``ValueError`` on
    an empty, non-string, or path-bearing name — the check lives at the
    filesystem boundary so in-memory :class:`~coact.base.AgentDefinition`\\ s stay
    unconstrained.

    >>> agent_filename('ux-analyst')
    'ux-analyst.md'
    >>> agent_filename('../escape')  # doctest: +ELLIPSIS
    Traceback (most recent call last):
        ...
    ValueError: unsafe agent name '../escape': ...
    """
    if not isinstance(name, str) or not name.strip():
        raise ValueError(f"agent name must be a non-empty string, got {name!r}")
    unsafe = (
        name in (".", "..")
        or name != Path(name).name
        or any(sep in name for sep in ("/", "\\"))
        or "\x00" in name
    )
    if unsafe:
        raise ValueError(
            f"unsafe agent name {name!r}: must be a bare filename stem "
            "(no '/', '\\', '..', or path separators)"
        )
    return f"{name}.md"


def first_balanced_span(s: str, opener: str = "{", closer: str = "}") -> Optional[str]:
    """Return the first depth-balanced ``opener…closer`` substring of ``s``.

    Brackets inside double-quoted JSON strings are ignored, so a valid value
    followed by prose that itself contains brackets is not over-captured (a
    greedy ``opener.*closer`` would run to the *last* ``closer`` and fail to
    parse). Returns ``None`` when no balanced span starts in ``s``. Shared by the
    LLM-reply JSON extractors (:mod:`coact.llm`, :mod:`coact.realize_litellm`).

    >>> first_balanced_span('Result: {"a": 1}. Note: {braces}.')
    '{"a": 1}'
    >>> first_balanced_span('see [1, [2, 3]] end', '[', ']')
    '[1, [2, 3]]'
    >>> first_balanced_span('no brackets here') is None
    True
    """
    start = s.find(opener)
    if start < 0:
        return None
    depth = 0
    in_str = False
    escaped = False
    for i in range(start, len(s)):
        ch = s[i]
        if in_str:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
        elif ch == opener:
            depth += 1
        elif ch == closer:
            depth -= 1
            if depth == 0:
                return s[start : i + 1]
    return None


def import_object(ref: str) -> Any:
    """Resolve a ``'module.path:attr'`` or ``'module.path.attr'`` reference.

    Prefer the ``module:attr`` form (unambiguous). Falls back to splitting on the
    last dot for the dotted form.

    >>> import_object('json:dumps')  # doctest: +ELLIPSIS
    <function dumps at ...>
    >>> import_object('os.path.join')  # doctest: +ELLIPSIS
    <function join at ...>
    """
    if ":" in ref:
        module_name, _, attr = ref.partition(":")
    else:
        module_name, _, attr = ref.rpartition(".")
    if not module_name or not attr:
        raise ValueError(
            f"Invalid object reference {ref!r}; expected 'module:attr' "
            f"or 'module.path.attr'."
        )
    module = import_module(module_name)
    obj = module
    for part in attr.split("."):
        obj = getattr(obj, part)
    return obj


def check_requirements(
    modules: dict[str, str],
    *,
    feature: str,
) -> None:
    """Verify optional dependencies are importable, else raise an actionable error.

    ``modules`` maps an importable module name to the pip target that provides
    it (e.g. ``{'claude_agent_sdk': 'claude-agent-sdk'}``). Raises
    ``ImportError`` listing the exact ``pip install`` line for whatever is
    missing — and, when some requirements *are* present, which ones — the
    package-UX convention for optional backends (informative, actionable errors).

    >>> check_requirements({'json': 'json'}, feature='noop')  # importable -> no raise
    """
    missing: list[str] = []
    present: list[str] = []
    for module_name, pip_target in modules.items():
        try:
            import_module(module_name)
            present.append(module_name)
        except ImportError:
            missing.append(pip_target)
    if missing:
        already = f" (already present: {', '.join(sorted(present))})" if present else ""
        raise ImportError(
            f"The {feature!r} feature needs optional dependencies that are not "
            f"installed{already}. Install them with:\n\n    "
            f"pip install {' '.join(sorted(set(missing)))}\n"
        )
