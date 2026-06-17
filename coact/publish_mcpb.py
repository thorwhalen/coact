"""``claude-local-mcpb`` publish target — bundle a capability as a Claude Desktop
Desktop Extension (``.mcpb``) for one-click **local** install.

A ``.mcpb`` is a ZIP carrying a ``manifest.json`` + a small ``server/`` that runs
a **local stdio** MCP server. We delegate the MCP server to ``py2mcp`` (which
already builds a FastMCP server from ``'module:function'`` refs); the bundle's
manifest launches ``python server/main.py`` → ``py2mcp.serve`` over stdio. coact
writes no MCP plumbing — only the *packaging* (mirrors the ``mcp`` realize
backend, DECISIONS §6.1.3 / D17).

Scope (P1): the LOCAL surface — stdio, no OAuth, runs on the user's machine. This
is **not** a claude.ai remote *connector* (a remote MCP server reached from
Anthropic's cloud over HTTPS + OAuth — a separate target, later). See
``misc/docs/CHATBOT_INTEGRATION_LANDSCAPE.md`` §5.1/§5.4 & §9.3.

Building a bundle is pure stdlib (``json`` + ``zipfile``); ``py2mcp``/``fastmcp``
are needed only in the Python that *runs* the installed extension — so a missing
runtime dep is reported as a warning, not a build error.
"""

from __future__ import annotations

import json
import zipfile
from collections import Counter
from importlib.util import find_spec
from pathlib import Path
from typing import Any, Optional

from coact.integration import IntegrationSource, IntegrationSpec, integration_spec_from
from coact.publish import PublishResult, targets
from coact.util import import_object, safe_filename

#: MCPB manifest schema version emitted (modelcontextprotocol/mcpb; current 0.3).
MCPB_MANIFEST_VERSION = "0.3"
#: Name of the bundled py2mcp server config, under ``server/``.
SERVER_CONFIG_NAME = "py2mcp_config.json"

#: The generated ``server/main.py`` shim (launches py2mcp's stdio runner).
_SERVER_MAIN = '''\
"""Entry point for a coact-generated Claude Desktop (.mcpb) extension.

Runs a py2mcp MCP server over stdio from the bundled config. Requires `py2mcp`
(and `fastmcp`) to be importable by the Python that Claude Desktop launches.
"""
import os

from py2mcp.serve import main

if __name__ == "__main__":
    config = os.path.join(os.path.dirname(__file__), "{config_name}")
    main(["--config", config])
'''.format(config_name=SERVER_CONFIG_NAME)


def publish_mcpb(
    source: IntegrationSource,
    *,
    dest: Optional[str] = None,
    dry_run: bool = False,
    name: Optional[str] = None,
    author: Optional[str] = None,
    version: str = "0.1.0",
    description: str = "",
    python_command: str = "python",
    manifest_version: str = MCPB_MANIFEST_VERSION,
) -> PublishResult:
    """Bundle ``source`` into a Claude Desktop ``.mcpb`` extension.

    >>> res = publish_mcpb(['os.path:basename'], name='paths', dry_run=True)
    >>> res.dry_run, res.artifact, sorted(res.files)
    (True, None, ['manifest.json', 'server/main.py', 'server/py2mcp_config.json'])
    """
    spec = integration_spec_from(
        source, name=name, author=author, version=version, description=description
    )
    if spec.is_empty():
        raise ValueError("nothing to publish: the IntegrationSpec carries no tools.")

    runnable_refs = spec.runnable_refs()
    if not runnable_refs:
        if spec.tool_specs:  # proposed tools exist, none bound -> a design draft
            proposed = ", ".join(ts.name for ts in spec.tool_specs)
            raise ValueError(
                f"This IntegrationSpec is a design draft: {len(spec.tool_specs)} "
                f"proposed tool(s) [{proposed}], none bound to an importable "
                "'module:function' handler. Bind handlers (or pass module:function "
                "refs) before building a runnable .mcpb — the draft is still usable "
                "as a design artifact (see `coact describe`)."
            )
        declared = []
        if spec.resources:
            declared.append(f"{len(spec.resources)} resource(s)")
        if spec.prompts:
            declared.append(f"{len(spec.prompts)} prompt(s)")
        raise ValueError(
            "nothing to publish to a .mcpb: this IntegrationSpec declares "
            + (", ".join(declared) or "no tools")
            + " but no tools. The claude-local-mcpb target consumes tools only "
            "(resources/prompts are reserved for future targets) — add "
            "'module:function' tool refs (or bound ToolSpecs) to publish."
        )

    manifest, warnings = build_manifest(
        spec, manifest_version=manifest_version, python_command=python_command
    )
    server_config = {"name": spec.name, "refs": runnable_refs}
    members = {
        "manifest.json": json.dumps(manifest, indent=2),
        "server/main.py": _SERVER_MAIN,
        f"server/{SERVER_CONFIG_NAME}": json.dumps(server_config, indent=2),
    }
    bundle_name = safe_filename(spec.name, suffix=".mcpb", kind="integration name")
    instructions = _install_instructions(spec, bundle_name)
    previews = {rel: _preview(content) for rel, content in members.items()}

    if dry_run:
        return PublishResult(
            target="claude-local-mcpb",
            dry_run=True,
            files=previews,
            instructions=instructions,
            warnings=warnings,
        )

    dest_dir = Path(dest) if dest is not None else Path.cwd()
    dest_dir.mkdir(parents=True, exist_ok=True)
    artifact = dest_dir / bundle_name
    with zipfile.ZipFile(artifact, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel, content in members.items():
            zf.writestr(rel, content)

    return PublishResult(
        target="claude-local-mcpb",
        dry_run=False,
        artifact=artifact,
        files=previews,
        instructions=instructions,
        warnings=warnings,
    )


def build_manifest(
    spec: IntegrationSpec,
    *,
    manifest_version: str = MCPB_MANIFEST_VERSION,
    python_command: str = "python",
) -> tuple[dict, list[str]]:
    """Build the MCPB ``manifest.json`` dict and any build-time warnings.

    The server is a Python stdio server launched as ``python server/main.py``;
    ``${__dirname}`` is resolved by Claude Desktop to the extracted bundle dir.

    Tool metadata is introspected from every *runnable* ref (``module:function``
    in ``tools`` plus bound ToolSpec handlers) — the bound function's own
    name/docstring are authoritative because they are what ``py2mcp`` actually
    serves at runtime (so the manifest never advertises a name the server won't
    expose). A bound ToolSpec's curated description only *fills in* an empty
    docstring. Any *proposed* (unbound) ToolSpec is listed by name/description for
    design visibility, with a warning that it will not run until bound.
    """
    runnable = spec.runnable_refs()
    tools, warnings = _introspect_tools(runnable)
    # Fill an empty introspected description from the bound ToolSpec's curated one
    # (a fidelity win that can't desync from runtime — names are left untouched).
    bound_by_ref = {ts.handler: ts for ts in spec.tool_specs if ts.handler}
    for tool, ref in zip(tools, runnable):
        ts = bound_by_ref.get(ref)
        if ts and ts.description and not tool["description"]:
            tool["description"] = ts.description
    seen = {t["name"] for t in tools}
    unbound: list[str] = []
    for ts in spec.tool_specs:
        if ts.handler:
            continue  # already covered via runnable_refs introspection
        unbound.append(ts.name)
        if ts.name not in seen:
            tools.append({"name": ts.name, "description": ts.description})
            seen.add(ts.name)
    if unbound:
        warnings.append(
            f"{len(unbound)} proposed tool(s) have no handler "
            f"({', '.join(unbound)}); listed in the manifest for design but they "
            "will NOT run until bound to importable module:function handlers."
        )
    if find_spec("py2mcp") is None:
        warnings.append(
            "py2mcp is not importable here; the bundle needs `py2mcp` and "
            "`fastmcp` installed in the Python that Claude Desktop runs."
        )
    tool_names = ", ".join(t["name"] for t in tools) or "(none)"
    manifest: dict[str, Any] = {
        "manifest_version": manifest_version,
        "name": spec.name,
        "version": spec.version,
        "description": spec.description or f"{spec.name} — MCP tools: {tool_names}",
        "author": {"name": spec.author or "unknown"},
        "server": {
            "type": "python",
            "entry_point": "server/main.py",
            "mcp_config": {
                "command": python_command,
                "args": ["${__dirname}/server/main.py"],
            },
        },
    }
    if tools:
        manifest["tools"] = tools
    return manifest, warnings


def _introspect_tools(refs: list[str]) -> tuple[list[dict], list[str]]:
    """Best-effort ``[{name, description}]`` per ref; importing is never fatal."""
    tools: list[dict] = []
    warnings: list[str] = []
    for ref in refs:
        tool_name = ref.split(":")[-1].split(".")[-1]
        description = ""
        try:
            obj = import_object(ref)
            doc = (getattr(obj, "__doc__", "") or "").strip()
            description = doc.splitlines()[0] if doc else ""
        except Exception as e:  # noqa: BLE001 - any import failure is non-fatal here
            warnings.append(
                f"could not import {ref!r} to read its docstring "
                f"({e.__class__.__name__}); listed by name only"
            )
        tools.append({"name": tool_name, "description": description})
    duplicates = sorted(n for n, c in Counter(t["name"] for t in tools).items() if c > 1)
    if duplicates:
        warnings.append(
            "duplicate tool name(s) "
            + ", ".join(duplicates)
            + ": only the last wins at runtime — rename or namespace the colliding functions."
        )
    return tools, warnings


def _install_instructions(spec: IntegrationSpec, bundle_name: str) -> str:
    """Human next-steps for installing the produced bundle."""
    return (
        f"Install {bundle_name!r}: open Claude Desktop → Settings → Extensions → "
        "Install Extension… (or double-click the file).\n"
        "This is a LOCAL extension (stdio) — it runs on this machine and needs a "
        "Python with `py2mcp` + `fastmcp` importable. It is NOT a claude.ai remote "
        "connector (those are remote MCP servers over HTTPS + OAuth — a separate "
        "publish target)."
    )


def _preview(content: str, *, limit: int = 200) -> str:
    """A one-line, length-bounded preview of a bundle member's content."""
    text = (content if isinstance(content, str) else repr(content)).strip()
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit] + "…"


targets.register("claude-local-mcpb", publish_mcpb)
