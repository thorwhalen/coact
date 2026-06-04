"""Pure helpers for coact with no internal coact imports.

Small, reusable string/name utilities and a thin ``check_requirements`` helper
for the optional-dependency backends (Agent SDK, py2mcp/FastMCP, an LLM
provider). Kept dependency-free so every other coact module can import it.
"""

from __future__ import annotations

import re
from importlib import import_module
from typing import Any


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
    missing — the package-UX convention for optional backends.

    >>> check_requirements({'json': 'json'}, feature='noop')  # importable -> no raise
    """
    missing = []
    for module_name, pip_target in modules.items():
        try:
            import_module(module_name)
        except ImportError:
            missing.append(pip_target)
    if missing:
        raise ImportError(
            f"The {feature!r} feature needs optional dependencies that are not "
            f"installed. Install them with:\n\n    pip install {' '.join(sorted(set(missing)))}\n"
        )
