"""PUBLISH — ship a capability to a chatbot host as a deployable integration.

The third coact axis, beside COMPLETE and REALIZE. ``publish(source, target=...)``
dispatches to a target adapter held in an open-closed
:class:`skill.registry.Registry` — exactly the shape of :mod:`coact.realize`'s
``backends``. Targets self-register on import, so a new host (remote Claude
connector, ChatGPT app, Gemini, ...) is added by writing a module that calls
``targets.register(...)`` — **no edit to this file** (open-closed, DECISIONS D17).

Claude is the first target deliberately as *one* registered adapter among future
ones — the target-neutral design from ``misc/docs/CHATBOT_INTEGRATION_LANDSCAPE.md``.
The canonical artifact is an MCP server (built by ``py2mcp``); each target differs
only in packaging + where it runs (§9.1/§9.3 of that doc).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from skill.registry import Registry

from coact.integration import IntegrationSource

#: Registry of publish targets (``publish(source, target=<name>)``).
targets: Registry[Callable] = Registry("publish_targets")


@dataclass
class PublishResult:
    """The outcome of :func:`publish` — what was (or *would be*) produced.

    ``dry_run`` mirrors ``realize(backend='host', dry_run=True)``: in a dry run
    ``artifact`` is ``None`` and ``files`` holds the would-write bundle members
    (relpath → short preview), so you can look before you leap.

    >>> PublishResult(target='claude-local-mcpb', dry_run=True).render().splitlines()[0]
    "Would publish (target='claude-local-mcpb', dry-run)"
    """

    target: str
    dry_run: bool = False
    artifact: Optional[Path] = None
    files: dict = field(default_factory=dict)
    instructions: str = ""
    warnings: list[str] = field(default_factory=list)

    def render(self) -> str:
        """A terminal-friendly summary (used by the CLI)."""
        head = (
            f"Would publish (target={self.target!r}, dry-run)"
            if self.dry_run
            else f"Published (target={self.target!r})"
        )
        lines = [head]
        if self.artifact is not None:
            lines.append(f"  artifact: {self.artifact}")
        verb = "would write" if self.dry_run else "wrote"
        for rel in sorted(self.files):
            lines.append(f"  {verb}: {rel}")
        for w in self.warnings:
            lines.append(f"  ! {w}")
        if self.instructions:
            lines.extend(["", self.instructions])
        return "\n".join(lines)


def publish(
    source: IntegrationSource,
    *,
    target: str = "claude-local-mcpb",
    dry_run: bool = False,
    **kwargs: Any,
) -> PublishResult:
    """Publish a capability to a chatbot host via the named target.

    ``source`` is anything :func:`coact.integration.integration_spec_from`
    accepts: ``'module:function'`` refs, live callables, a skill carrying a
    ``coact: mcp:`` block, or a prebuilt :class:`~coact.integration.IntegrationSpec`.
    Target-specific options (``dest``, ``name``, ``author``, ...) pass through as
    keyword arguments.
    """
    impl = targets.get(target)
    if impl is None:
        available = ", ".join(sorted(targets)) or "(none registered)"
        raise ValueError(
            f"Unknown publish target: {target!r}. Available: {available}"
        )
    return impl(source, dry_run=dry_run, **kwargs)


def publish_targets() -> list[str]:
    """The names of all registered publish targets.

    >>> isinstance(publish_targets(), list)
    True
    """
    return sorted(targets)
