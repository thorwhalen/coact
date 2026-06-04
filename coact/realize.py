"""REALIZE — turn a completed agent definition into something that actually runs.

COACT_SPEC §6. "Running agent" means different things for different hosts, so
``coact`` offers a small set of realization backends behind one ``realize(...)``
interface (an open-closed :class:`~skill.registry.Registry`, DECISIONS §6.3):

- ``host`` (default, cheapest — DECISIONS D5/D9): do **not** stand up a new
  runtime. Materialize the agent ``.md`` into ``.claude/agents/`` and link the
  referenced skills into ``.claude/skills/`` so the *host* (Claude Code) becomes
  the executor. "Realize" here = materialize files + verify discovery.
- ``sdk``: a runnable, in-process object backed by the Claude Agent SDK that
  **satisfies ``aw.AgenticStep``** (``execute(input_data, context) -> (artifact,
  info)``), so coact-realized agents drop straight into ``aw`` workflows.
- ``mcp`` (added in a later milestone): expose a skill's Python tools as an MCP
  server via ``py2mcp``.

The cheap path is the default; spawning a running fleet is opt-in (the §3.5 cost
gate, surfaced by :func:`coact.analysis.estimate`). Topology stays out (D8).
"""

from __future__ import annotations

import dataclasses
import os
import shutil
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Union

from skill.base import Skill
from skill.registry import Registry
from skill.util import find_project_root

from coact.base import AgentDefinition
from coact.complete import _resolve_skill, complete
from coact.emit import emit_agent, from_claude_agent_md
from coact.frontmatter import parse_coact_meta
from coact.policy import CompletionPolicy
from coact.stores import agents_dir
from coact.util import check_requirements

RealizeTarget = Union[AgentDefinition, str, Path, Skill, list]

#: Registry of realization backends (``realize(target, backend=<name>)``).
backends: Registry[Callable] = Registry("realization_backends")


def realize(target: RealizeTarget, *, backend: str = "host", **kwargs) -> Any:
    """Realize an agent (or skill, or list) via the named backend.

    >>> from coact import AgentDefinition
    >>> import tempfile
    >>> ad = AgentDefinition(name='ux', description='Analyze.', prompt='You are...', skills=['ux'])
    >>> res = realize(ad, backend='host', dest=tempfile.mkdtemp(), link=False)
    >>> res.agents['ux'].name
    'ux.md'
    """
    impl = backends.get(backend)
    if impl is None:
        available = ", ".join(sorted(backends))
        raise ValueError(
            f"Unknown realize backend: {backend!r}. Available: {available}"
        )
    return impl(target, **kwargs)


# ---------------------------------------------------------------------------
# Target coercion: AgentDefinition | skill source | agent .md | list -> [AgentDefinition]
# ---------------------------------------------------------------------------


def _coerce_agents(
    target: RealizeTarget, *, policy: Optional[CompletionPolicy] = None
) -> list[AgentDefinition]:
    """Resolve a realize target to a list of :class:`AgentDefinition`.

    - an :class:`AgentDefinition` → itself
    - a list/tuple → each element coerced and flattened
    - an agent ``*.md`` file → parsed back
    - anything else (skill dir / store key / ``Skill``) → ``complete``-d
    """
    if isinstance(target, AgentDefinition):
        return [target]
    if isinstance(target, (list, tuple)):
        out: list[AgentDefinition] = []
        for item in target:
            out.extend(_coerce_agents(item, policy=policy))
        return out
    if isinstance(target, (str, Path)):
        path = Path(target)
        if path.is_file() and path.suffix == ".md" and path.name != "SKILL.md":
            return [from_claude_agent_md(path.read_text())]
    return [complete(target, policy=policy)]


# ---------------------------------------------------------------------------
# host backend
# ---------------------------------------------------------------------------


@dataclass
class RealizedHost:
    """The materialized result of host realization (files the host will discover)."""

    agents: dict[str, Path] = field(default_factory=dict)
    skills: dict[str, Path] = field(default_factory=dict)
    agents_dir: Optional[Path] = None
    skills_dir: Optional[Path] = None
    warnings: list[str] = field(default_factory=list)


def realize_host(
    target: RealizeTarget,
    *,
    scope: str = "project",
    dest: Path | str | None = None,
    project_dir: Path | str | None = None,
    link: bool = True,
    skills_source: Path | str | list | None = None,
    force: bool = False,
    policy: Optional[CompletionPolicy] = None,
) -> RealizedHost:
    """Materialize agents (+ linked skills) so the host agent runs them.

    Writes ``<dest>/<name>.md`` for each agent and (when ``link``) symlinks each
    **referenced** skill into the sibling ``.claude/skills/`` so Claude Code
    discovers both. ``skills_source`` (a dir or list of dirs each holding
    ``<name>/SKILL.md``) is searched first; otherwise skills are resolved by name
    via the local store / project. Verifies discovery and reports anything missing.
    """
    agents = _coerce_agents(target, policy=policy)
    out_dir = Path(dest) if dest is not None else agents_dir(
        scope=scope, project_dir=project_dir
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    skills_target = out_dir.parent / "skills"
    sources = _as_source_list(skills_source)

    result = RealizedHost(agents_dir=out_dir, skills_dir=skills_target)
    for ad in agents:
        result.agents[ad.name] = emit_agent(ad, "claude-agents-md", dest=out_dir)

    if link:
        skills_target.mkdir(parents=True, exist_ok=True)
        for ad in agents:
            for skill_name in ad.skills:
                linked = _link_skill(
                    skill_name, skills_target, sources=sources, force=force
                )
                if linked is not None:
                    result.skills[skill_name] = linked
                else:
                    result.warnings.append(
                        f"agent {ad.name!r} references skill {skill_name!r}, which "
                        f"could not be resolved to link into {skills_target}"
                    )

    # verify discovery
    for ad in agents:
        path = result.agents[ad.name]
        if not path.exists():
            result.warnings.append(f"agent file not written: {path}")
        for skill_name in ad.skills:
            if link and not (skills_target / skill_name).exists():
                result.warnings.append(
                    f"skill {skill_name!r} not discoverable in {skills_target}"
                )
    return result


def _as_source_list(skills_source: Path | str | list | None) -> list[Path]:
    """Normalize ``skills_source`` to a list of directories to search first."""
    if skills_source is None:
        return []
    if isinstance(skills_source, (list, tuple)):
        return [Path(s) for s in skills_source]
    return [Path(skills_source)]


def _find_skill_source(name: str, sources) -> Optional[Path]:
    """Find a skill's source dir: each ``sources`` dir first, then store/project."""
    for src_dir in sources:
        candidate = Path(src_dir) / name
        if (candidate / "SKILL.md").exists():
            return candidate
    try:
        return _resolve_skill(name).source_path
    except FileNotFoundError:
        return None


def _link_skill(
    name: str,
    skills_target: Path,
    *,
    sources=(),
    force: bool = False,
) -> Optional[Path]:
    """Symlink one referenced skill into ``skills_target``; None if unresolved.

    Resolution order: each ``sources`` dir (``<source>/<name>/SKILL.md``), then
    by name via the local store / project. Point-don't-copy: symlink, never copy.
    Safety invariants: a **real** (non-symlink) entry already in place is the
    user's and is never touched; a working coact symlink is kept unless ``force``;
    the source is resolved **before** any existing link is removed, so a failed
    re-link can never destroy a previously working one; a dangling symlink is
    re-linked rather than reported as discoverable.
    """
    dest = skills_target / name

    # A real directory/file already in place belongs to the user — leave it.
    if dest.exists() and not dest.is_symlink():
        return dest
    # A working symlink we needn't replace.
    if dest.is_symlink() and dest.exists() and not force:
        return dest

    source = _find_skill_source(name, sources)
    if source is None:
        # Can't resolve a replacement: never delete; report only if it resolves.
        return dest if dest.exists() else None

    # Safe to (re)create the link now that we have a valid source. At this point
    # any existing dest is a symlink (good/broken) — real entries returned above.
    if dest.is_symlink():
        dest.unlink()
    dest.parent.mkdir(parents=True, exist_ok=True)
    os.symlink(Path(source).resolve(), dest)
    return dest


backends.register("host", realize_host)


# ---------------------------------------------------------------------------
# sdk backend — an aw.AgenticStep-compatible runnable
# ---------------------------------------------------------------------------


def _filter_kwargs(cls: type, kwargs: dict) -> dict:
    """Keep only the kwargs that ``cls`` (a dataclass) accepts (version-tolerant)."""
    accepted = {f.name for f in dataclasses.fields(cls)}
    return {k: v for k, v in kwargs.items() if k in accepted}


# --- D6 return-contract realization -----------------------------------------
#
# The return contract reaches the SDK by one of two mechanisms (DECISIONS D6):
#
# - ``output_format``: the native structured-output option. Used when the
#   installed ``ClaudeAgentOptions`` exposes the field (SDK ≥ 0.1.x).
# - ``tool``: a forced ``return_result`` tool whose ``input_schema`` IS the
#   return schema, plus a system-prompt instruction to call it. The fallback for
#   older SDKs that lack ``output_format`` (and selectable explicitly via
#   ``return_mode='tool'`` for models / extended-thinking modes that cannot honor
#   ``output_format`` at runtime). The structured result is then recovered from
#   the tool-use block's ``input`` in the message stream — no extra plumbing.

#: In-process SDK MCP server + tool names for the forced return path.
RETURN_TOOL_SERVER = "coact_return"
RETURN_TOOL_NAME = "return_result"
#: How Claude references the tool (``mcp__<server>__<tool>``).
RETURN_TOOL_FULLNAME = f"mcp__{RETURN_TOOL_SERVER}__{RETURN_TOOL_NAME}"


@dataclass(frozen=True)
class _ReturnPlan:
    """How an agent's return contract is realized for the SDK (resolved once)."""

    mode: str  # "none" | "output_format" | "tool"
    schema: dict
    unwrap_key: Optional[str] = None
    tool_fullname: str = ""


def _auto_return_mode(option_field_names) -> str:
    """Pick the return mode in ``auto``: native ``output_format`` if the SDK has it.

    >>> _auto_return_mode({'system_prompt', 'output_format'})
    'output_format'
    >>> _auto_return_mode({'system_prompt'})  # older SDK without the field
    'tool'
    """
    return "output_format" if "output_format" in set(option_field_names) else "tool"


def _as_object_schema(schema: dict) -> tuple[dict, Optional[str]]:
    """Coerce a return schema to a valid object ``inputSchema`` for the return tool.

    The Agent SDK passes a dict ``input_schema`` through unchanged only when it is
    an object schema (``type: object`` *and* ``properties``); any other dict is
    misread as a ``{param: type}`` map. A non-object schema is therefore wrapped
    under a ``result`` key, and that key is returned so extraction can unwrap it.

    >>> _as_object_schema({'type': 'object', 'properties': {'a': {}}})[1] is None
    True
    >>> _as_object_schema({'type': 'array', 'items': {'type': 'string'}})
    ({'type': 'object', 'properties': {'result': {'type': 'array', 'items': {'type': 'string'}}}, 'required': ['result']}, 'result')
    """
    if (
        isinstance(schema, dict)
        and schema.get("type") == "object"
        and "properties" in schema
    ):
        return schema, None
    return (
        {"type": "object", "properties": {"result": schema}, "required": ["result"]},
        "result",
    )


def _with_return_instruction(system_prompt: str, obj_schema: dict, description: str) -> str:
    """Append the "you MUST call return_result" instruction to a system prompt."""
    import json

    suffix = f" ({description})" if description else ""
    schema_json = json.dumps(obj_schema, indent=2)
    instruction = (
        "\n\n## Return contract\n"
        f"When you have finished, you MUST call the `{RETURN_TOOL_NAME}` tool "
        f"exactly once with your final result{suffix}. Its arguments must conform "
        f"to this JSON Schema:\n\n```json\n{schema_json}\n```\n"
        f"Do not return the result as prose — call `{RETURN_TOOL_NAME}` instead."
    )
    return (system_prompt or "") + instruction


def _is_return_tool(name: str) -> bool:
    """True if ``name`` denotes the forced return tool (full MCP name or bare)."""
    return (
        name == RETURN_TOOL_FULLNAME
        or name.endswith(f"__{RETURN_TOOL_NAME}")
        or name == RETURN_TOOL_NAME
    )


def _extract_return_tool_input(messages: list, unwrap_key: Optional[str]) -> Any:
    """Recover the forced ``return_result`` tool-use input from SDK messages, or None.

    Scans assistant messages for a tool-use block calling the return tool and
    returns its ``input`` (the last one wins). When the schema was wrapped (a
    non-object return type), the single ``result`` key is unwrapped.
    """
    found = None
    for message in messages:
        content = getattr(message, "content", None)
        if not isinstance(content, list):
            continue
        for block in content:
            name = getattr(block, "name", None)
            block_input = getattr(block, "input", None)
            if name and block_input is not None and _is_return_tool(name):
                found = block_input
    if found is None:
        return None
    if unwrap_key and isinstance(found, dict) and set(found) == {unwrap_key}:
        return found[unwrap_key]
    return found


@dataclass
class RunnableAgent:
    """An ``aw.AgenticStep``-compatible runnable backed by the Claude Agent SDK.

    Satisfies ``execute(input_data, context) -> (artifact, info_dict)`` so it
    drops into ``aw`` workflows and reuses ``aw``'s retry/validation/human-in-loop.
    The SDK is imported lazily; ``runner`` is injectable so the agent can be
    constructed and unit-tested without a live API call (dependency injection).
    """

    agent_def: AgentDefinition
    llm: Any = None  # reserved (SDK uses agent_def.model); kept for aw symmetry
    runner: Optional[Callable[[str, Any], Any]] = None
    default_tools: tuple[str, ...] = ("Read", "Grep", "Glob")
    #: How the return contract is realized: ``'auto'`` (native output_format when
    #: the SDK supports it, else the forced return tool), ``'output_format'``, or
    #: ``'tool'`` (force the return_result tool — for older SDKs / extended
    #: thinking that cannot honor output_format). See DECISIONS D6.
    return_mode: str = "auto"

    def _resolved_return(self) -> _ReturnPlan:
        """Resolve how this agent's return contract maps onto the SDK (no API call).

        Honors ``return_mode`` and, in ``'auto'``, the installed SDK's
        capabilities. ``.schema()`` resolves an inline schema or a ``schema_ref``
        to canonical JSON Schema; an empty contract yields ``mode='none'``.
        """
        from claude_agent_sdk import ClaudeAgentOptions

        schema = self.agent_def.returns.schema()
        if not schema:
            return _ReturnPlan("none", {})
        mode = self.return_mode
        if mode == "auto":
            mode = _auto_return_mode(f.name for f in dataclasses.fields(ClaudeAgentOptions))
        if mode == "output_format":
            return _ReturnPlan("output_format", schema)
        if mode == "tool":
            obj_schema, unwrap_key = _as_object_schema(schema)
            return _ReturnPlan("tool", obj_schema, unwrap_key, RETURN_TOOL_FULLNAME)
        raise ValueError(
            f"Unknown return_mode {self.return_mode!r}; "
            "expected 'auto', 'output_format', or 'tool'."
        )

    def build_options(self) -> Any:
        """Construct ``ClaudeAgentOptions`` from the agent definition (no API call)."""
        check_requirements(
            {"claude_agent_sdk": "claude-agent-sdk"}, feature="realize(backend='sdk')"
        )
        from claude_agent_sdk import ClaudeAgentOptions

        kwargs: dict[str, Any] = {
            "system_prompt": self.agent_def.prompt or self.agent_def.description,
        }
        tools = self.agent_def.tools
        kwargs["allowed_tools"] = list(tools) if tools is not None else list(
            self.default_tools
        )
        if self.agent_def.disallowed_tools:
            kwargs["disallowed_tools"] = list(self.agent_def.disallowed_tools)
        if self.agent_def.model:
            kwargs["model"] = self.agent_def.model
        if self.agent_def.mcp_servers:
            kwargs["mcp_servers"] = self.agent_def.mcp_servers
        if self.agent_def.permission_mode:
            kwargs["permission_mode"] = self.agent_def.permission_mode
        # Wire the return contract (D6). The native output_format must be the
        # {"type": "json_schema", "schema": <schema>} wrapper — a bare schema is
        # silently ignored. The tool fallback injects a forced return_result tool.
        plan = self._resolved_return()
        if plan.mode == "output_format":
            kwargs["output_format"] = {"type": "json_schema", "schema": plan.schema}
        elif plan.mode == "tool":
            self._wire_return_tool(kwargs, plan.schema)
        return ClaudeAgentOptions(**_filter_kwargs(ClaudeAgentOptions, kwargs))

    def _wire_return_tool(self, kwargs: dict, obj_schema: dict) -> None:
        """Add the forced ``return_result`` SDK MCP tool + instruction to ``kwargs``."""
        from claude_agent_sdk import create_sdk_mcp_server, tool

        desc = self.agent_def.returns.description or "Return your final structured result."

        @tool(RETURN_TOOL_NAME, desc, obj_schema)
        async def _return_result(args):  # pragma: no cover - runs in the SDK loop
            return {"content": [{"type": "text", "text": "Result recorded."}]}

        server = create_sdk_mcp_server(RETURN_TOOL_SERVER, tools=[_return_result])
        existing = kwargs.get("mcp_servers")
        servers = dict(existing) if isinstance(existing, dict) else {}
        servers[RETURN_TOOL_SERVER] = server
        kwargs["mcp_servers"] = servers

        allowed = list(kwargs.get("allowed_tools") or [])
        if RETURN_TOOL_FULLNAME not in allowed:
            allowed.append(RETURN_TOOL_FULLNAME)
        kwargs["allowed_tools"] = allowed

        kwargs["system_prompt"] = _with_return_instruction(
            kwargs.get("system_prompt") or "",
            obj_schema,
            self.agent_def.returns.description,
        )

    def execute(
        self, input_data: Any, context: Any = None
    ) -> tuple[Any, dict[str, Any]]:
        """Run the agent over ``input_data``; return ``(artifact, info)`` (aw protocol)."""
        options = self.build_options()
        plan = self._resolved_return()
        prompt = self._prompt_from(input_data)
        runner = self.runner or _default_sdk_runner
        raw = runner(prompt, options)
        artifact = _extract_artifact(
            raw,
            return_tool=plan.tool_fullname if plan.mode == "tool" else None,
            unwrap_key=plan.unwrap_key,
        )
        info = {
            "agent": self.agent_def.name,
            "model": self.agent_def.model,
            "backend": "sdk",
            "return_mode": plan.mode,
            "raw": raw,
        }
        return artifact, info

    @staticmethod
    def _prompt_from(input_data: Any) -> str:
        return input_data if isinstance(input_data, str) else repr(input_data)


def _default_sdk_runner(prompt: str, options: Any) -> list:
    """Run a real Agent SDK ``query`` to completion, collecting messages."""
    import asyncio

    from claude_agent_sdk import query

    async def _collect() -> list:
        return [message async for message in query(prompt=prompt, options=options)]

    return asyncio.run(_collect())


def _extract_artifact(
    raw: Any, *, return_tool: Optional[str] = None, unwrap_key: Optional[str] = None
) -> Any:
    """Best-effort extraction of the agent's result from a runner's return value.

    In the D6 ``tool`` fallback (``return_tool`` set), the forced
    ``return_result`` tool-use input is the canonical structured result and takes
    precedence over any prose text blocks.
    """
    if isinstance(raw, str):
        return raw
    # a structured-output carrying object
    structured = getattr(raw, "structured_output", None)
    if structured is not None:
        return structured
    # a list of SDK messages
    if isinstance(raw, list) and raw:
        if return_tool:
            captured = _extract_return_tool_input(raw, unwrap_key)
            if captured is not None:
                return captured
        # otherwise concatenate text blocks across assistant messages
        texts: list[str] = []
        for message in raw:
            content = getattr(message, "content", None)
            if isinstance(content, list):
                for block in content:
                    text = getattr(block, "text", None)
                    if text:
                        texts.append(text)
            elif isinstance(content, str):
                texts.append(content)
        if texts:
            return "\n".join(texts)
    return raw


def realize_sdk(
    target: RealizeTarget,
    *,
    llm: Any = None,
    runner: Optional[Callable[[str, Any], Any]] = None,
    return_mode: str = "auto",
    policy: Optional[CompletionPolicy] = None,
) -> RunnableAgent:
    """Realize a single agent as a runnable :class:`RunnableAgent` (aw-compatible).

    ``return_mode`` selects how the return contract reaches the SDK (DECISIONS
    D6): ``'auto'`` uses native ``output_format`` when the installed SDK supports
    it and otherwise falls back to a forced ``return_result`` tool; pass
    ``'tool'`` to force that fallback (e.g. for models / extended-thinking modes
    that cannot honor ``output_format``).
    """
    agents = _coerce_agents(target, policy=policy)
    if len(agents) != 1:
        raise ValueError(
            f"backend='sdk' realizes exactly one agent; got {len(agents)}. "
            "Realize each separately (topology is out of scope — DECISIONS D8)."
        )
    return RunnableAgent(
        agent_def=agents[0], llm=llm, runner=runner, return_mode=return_mode
    )


backends.register("sdk", realize_sdk)


# ---------------------------------------------------------------------------
# mcp backend — expose a skill's Python tools as an MCP server (via py2mcp)
# ---------------------------------------------------------------------------


def realize_mcp(
    target: RealizeTarget,
    *,
    name: Optional[str] = None,
    input_trans: Optional[Callable[[dict], dict]] = None,
) -> Any:
    """Expose a skill's declared Python tools as a FastMCP server (foreign-host).

    Reads the ``coact: mcp:`` block (``module`` + ``functions``) of the source
    skill(s) and delegates to ``py2mcp.mk_mcp_from_refs`` — coact writes no MCP
    plumbing (DECISIONS §6.1.3). ``target`` may be a skill source or an
    :class:`AgentDefinition` (whose ``source_skill`` is resolved back to the
    skill that carries the declaration).
    """
    check_requirements(
        {"py2mcp": "py2mcp", "fastmcp": "fastmcp"},
        feature="realize(backend='mcp')",
    )
    from py2mcp import mk_mcp_from_refs

    refs, server_name = _mcp_refs(target)
    if not refs:
        raise ValueError(
            "No Python tools to expose via MCP. Declare them in a `coact: mcp:` "
            "block (module + functions) on the source skill, or use "
            "backend='host' / 'sdk'."
        )
    return mk_mcp_from_refs(refs, name=name or server_name, input_trans=input_trans)


def _mcp_refs(target: RealizeTarget) -> tuple[list[str], str]:
    """Collect ``'module:function'`` refs (and a server name) from coact: mcp blocks."""
    skills = _resolve_skills_for_mcp(target)
    refs: list[str] = []
    names: list[str] = []
    for sk in skills:
        names.append(sk.meta.name)
        for entry in parse_coact_meta(sk).mcp:
            module = entry.get("module")
            if not module:
                continue
            for fn in entry.get("functions") or []:
                refs.append(f"{module}:{fn}")
    server_name = (names[0] if len(names) == 1 else "coact") + "-tools"
    return refs, server_name


def _resolve_skills_for_mcp(target: RealizeTarget) -> list[Skill]:
    """Resolve the skill(s) that carry the coact: mcp declaration for ``target``."""
    if isinstance(target, (list, tuple)):
        out: list[Skill] = []
        for item in target:
            out.extend(_resolve_skills_for_mcp(item))
        return out
    if isinstance(target, AgentDefinition):
        return [_resolve_skill(target.source_skill or target.name)]
    return [_resolve_skill(target)]


backends.register("mcp", realize_mcp)
