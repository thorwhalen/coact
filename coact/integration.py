"""IntegrationSpec — the target-neutral SSOT for a *published* integration.

coact's COMPLETE/REALIZE axes turn skills into agent definitions and run them.
The **PUBLISH** axis (this module + :mod:`coact.publish`) is orthogonal: it takes
a *capability* — a set of Python tools given as ``'module:function'`` refs, live
callables, or a skill's ``coact: mcp:`` block — and ships it to a chatbot host as
a deployable integration (a Claude Desktop ``.mcpb`` bundle today; remote
connectors / skills / plugins / other hosts later).

The spec is deliberately **separate from** :class:`~coact.base.AgentDefinition`
(which is agent-persona-centric): an integration is MCP-server-shaped
(tools/resources/prompts + auth + deployment), per the chatbot-integration
landscape research (``misc/docs/CHATBOT_INTEGRATION_LANDSCAPE.md``). The canonical
artifact is an MCP server, built by ``py2mcp`` — coact owns the spec, the
packaging, and the target registry, **not** the MCP plumbing (mirrors the ``mcp``
realize backend, DECISIONS §6.1.3 / D17).
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Optional, Union

from coact.util import to_kebab_case

#: What :func:`integration_spec_from` accepts: a built spec, a ``module:function``
#: ref, a skill source (path/``Skill``), a live callable, or an iterable of those.
IntegrationSource = Union[
    "IntegrationSpec", str, Path, Callable[..., Any], Iterable[Any]
]


@dataclass
class ToolSpec:
    """A richer, target-neutral description of one tool in an :class:`IntegrationSpec`.

    The *mechanical* ingress represents tools as bare ``'module:function'`` ref
    strings (``IntegrationSpec.tools``). The *NL* ingress (:mod:`coact.nl_ingress`)
    and the landscape-doc §9.1 model need more — a name, a description, an input
    JSON Schema, and an **optional** handler ref:

    - A ToolSpec **with** a ``handler`` is *bound* (runnable): its ref joins the
      spec's runnable set and the published server can import and call it.
    - A ToolSpec **without** a handler is a *proposed* tool — a design draft to
      bind to real code (or supply a ref for) before it can run.

    >>> ToolSpec(name='get_weather', handler='wx.api:current').is_bound()
    True
    >>> ToolSpec(name='get_weather').is_bound()
    False
    """

    name: str
    description: str = ""
    input_schema: Optional[dict] = None
    handler: Optional[str] = None  # 'module:function' ref, or None if unbound

    def is_bound(self) -> bool:
        """True when a ``module:function`` handler backs this tool (so it can run)."""
        return bool(self.handler)


@dataclass
class IntegrationSpec:
    """Target-neutral description of an integration to publish.

    The connectivity core maps onto MCP's three primitives. Tools come in two
    shapes that coexist: bare ``'module:function'`` refs in ``tools`` (the
    mechanical/code ingress) and richer :class:`ToolSpec` descriptors in
    ``tool_specs`` (the NL ingress, landscape-doc §9.1). ``resources``/``prompts``
    and the ``auth``/``deployment`` hints are declared now (open-closed) for the
    remote connector and other targets to come.

    >>> spec = IntegrationSpec(name='paths', tools=['os.path:basename'])
    >>> spec.name, spec.tools, spec.deployment
    ('paths', ['os.path:basename'], 'local-stdio')
    >>> IntegrationSpec(name='empty').is_empty()
    True
    >>> draft = IntegrationSpec(name='wx', tool_specs=[ToolSpec(name='get')])
    >>> draft.is_empty(), draft.runnable_refs()
    (False, [])
    """

    name: str
    description: str = ""
    version: str = "0.1.0"
    tools: list[str] = field(default_factory=list)  # 'module:function' refs (MCP tools)
    resources: list[str] = field(default_factory=list)  # reserved (MCP resources)
    prompts: list[str] = field(default_factory=list)  # reserved (MCP prompts)
    tool_specs: list[ToolSpec] = field(default_factory=list)  # richer tool descriptors
    instructions: Optional[str] = None  # reserved (SKILL.md procedural knowledge)
    auth: str = "none"  # 'none' | 'env' | 'oauth2.1' (reserved for remote targets)
    deployment: str = "local-stdio"  # 'local-stdio' | 'remote-http' (reserved)
    author: Optional[str] = None
    source: Optional[str] = None  # provenance: the skill/module it came from

    def is_empty(self) -> bool:
        """True when there is nothing to publish (no tools/tool_specs/resources/prompts)."""
        return not (self.tools or self.tool_specs or self.resources or self.prompts)

    def runnable_refs(self) -> list[str]:
        """The importable ``'module:function'`` refs that back *runnable* tools.

        Bare refs in ``tools`` plus the ``handler`` of every *bound* ToolSpec,
        de-duplicated preserving order. A draft whose tools are all *proposed*
        (unbound) returns ``[]`` — it has nothing a server can actually run yet.
        """
        refs = list(self.tools)
        for ts in self.tool_specs:
            if ts.handler and ts.handler not in refs:
                refs.append(ts.handler)
        return refs

    def render(self) -> str:
        """A terminal-friendly summary of the (possibly draft) integration."""
        lines = [f"IntegrationSpec: {self.name} (v{self.version})"]
        if self.description:
            lines.append(f"  {self.description}")
        lines.append(f"  deployment: {self.deployment}   auth: {self.auth}")
        runnable = set(self.runnable_refs())
        if self.tools or self.tool_specs:
            lines.append("  tools:")
            for ref in self.tools:
                lines.append(f"    - {ref}  [ref]")
            for ts in self.tool_specs:
                tag = f"bound -> {ts.handler}" if ts.is_bound() else "proposed (no handler)"
                lines.append(f"    - {ts.name}  [{tag}]")
                if ts.description:
                    lines.append(f"        {ts.description}")
        if self.resources:
            lines.append("  resources: " + ", ".join(self.resources))
        if self.prompts:
            lines.append("  prompts: " + ", ".join(self.prompts))
        if self.tool_specs and not runnable:
            lines.append(
                "  NOTE: design draft — no tool is bound to importable code. Bind "
                "each tool to a 'module:function' handler (or supply refs) before "
                "building a runnable .mcpb."
            )
        return "\n".join(lines)


def integration_spec_from(
    source: IntegrationSource,
    *,
    name: Optional[str] = None,
    description: str = "",
    version: str = "0.1.0",
    author: Optional[str] = None,
) -> IntegrationSpec:
    """Coerce a capability source into an :class:`IntegrationSpec`.

    Accepts (and flattens lists of): a prebuilt :class:`IntegrationSpec`, a
    ``'module:function'`` ref string, a live callable (its
    ``__module__:__qualname__`` becomes the ref), or a skill source carrying a
    ``coact: mcp:`` block. The resulting ``name`` is kebab-cased so it is a safe,
    machine-readable bundle identifier.

    >>> integration_spec_from(['os.path:basename'], name='paths').tools
    ['os.path:basename']
    >>> integration_spec_from('os.path:basename', name='My Tools').name
    'my-tools'
    """
    if isinstance(source, IntegrationSpec):
        return source

    refs: list[str] = []
    derived_name: Optional[str] = name
    src_label: Optional[str] = None
    unrecognized: list[str] = []
    items = list(source) if isinstance(source, (list, tuple)) else [source]

    for item in items:
        if isinstance(item, IntegrationSpec):
            refs.extend(item.tools)
            derived_name = derived_name or item.name
        elif _is_skill_obj(item):  # before callable(): a Skill may define __call__
            sk_refs, sk_name = _refs_and_name_from_skill(item)
            refs.extend(sk_refs)
            derived_name = derived_name or sk_name
        elif callable(item):
            refs.append(_ref_from_callable(item))
            derived_name = derived_name or getattr(item, "__name__", None)
        elif isinstance(item, str) and _looks_like_ref(item):
            refs.append(item)
        elif isinstance(item, (str, Path)) and Path(item).exists():
            sk_refs, sk_name = _refs_and_name_from_skill(item)
            refs.extend(sk_refs)
            derived_name = derived_name or sk_name
            src_label = src_label or str(item)
        else:  # a string/path that is neither a ref nor an existing skill source
            unrecognized.append(str(item) if isinstance(item, (str, Path)) else repr(item))

    if unrecognized:
        raise ValueError(
            "Unrecognized publish source(s): "
            + ", ".join(repr(u) for u in unrecognized)
            + ". Expected a 'module:function' ref (note the colon), an existing "
            "skill directory / SKILL.md, or a live callable."
        )
    if not refs:
        raise ValueError(
            "No tools found to publish. Provide 'module:function' refs, live "
            "callables, or a skill carrying a `coact: mcp:` block (module + functions)."
        )

    return IntegrationSpec(
        name=to_kebab_case(derived_name or "integration"),
        description=description,
        version=version,
        tools=refs,
        author=author,
        source=src_label,
    )


def _ref_from_callable(fn: Callable) -> str:
    """Derive a ``'module:qualname'`` ref from a live callable.

    Rejects ``__main__``-defined functions: a published server re-imports tools
    by reference, so they must live in an importable module.
    """
    if inspect.ismethod(fn):
        raise ValueError(
            f"{fn!r} is a bound method; pass the underlying function or a "
            "'module:function' ref — a bound method can't be re-imported by reference."
        )
    module = getattr(fn, "__module__", None)
    qual = getattr(fn, "__qualname__", None) or getattr(fn, "__name__", None)
    if not module or not qual:
        raise ValueError(f"cannot derive a 'module:function' ref from {fn!r}")
    if module == "__main__":
        raise ValueError(
            f"{qual!r} is defined in __main__; move it into an importable module "
            "so the published server can import it by reference."
        )
    return f"{module}:{qual}"


def _is_skill_obj(item: Any) -> bool:
    """True if ``item`` is a :class:`skill.base.Skill` (checked before ``callable``)."""
    try:
        from skill.base import Skill

        return isinstance(item, Skill)
    except Exception:  # pragma: no cover - skill import is best-effort here
        return False


def _looks_like_ref(s: str) -> bool:
    """A ``'module:function'`` ref, as opposed to a filesystem skill source."""
    return ":" in s and not Path(s).exists()


def _refs_and_name_from_skill(source: Any) -> tuple[list[str], Optional[str]]:
    """Collect ``'module:function'`` refs (and a name) from a skill's coact: mcp block."""
    from coact.frontmatter import parse_coact_meta

    refs: list[str] = []
    for entry in parse_coact_meta(source).mcp:
        module = entry.get("module")
        if not module:
            continue
        for fn in entry.get("functions") or []:
            refs.append(f"{module}:{fn}")

    name: Optional[str] = None
    try:
        from skill.base import Skill

        if isinstance(source, Skill):
            name = source.meta.name
    except Exception:  # pragma: no cover - skill import/shape is best-effort here
        pass
    if name is None and isinstance(source, (str, Path)):
        p = Path(source)
        name = p.name if p.is_dir() else (p.parent.name if p.is_file() else None)
    return refs, name
