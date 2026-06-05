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
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Union

from skill.base import Skill
from skill.registry import Registry

from coact.base import AgentDefinition
from coact.complete import resolve_skill, complete
from coact.emit import emit_agent, from_claude_agent_md
from coact.frontmatter import parse_coact_meta
from coact.policy import CompletionPolicy
from coact.return_contract import (
    RETURN_TOOL_FULLNAME,
    RETURN_TOOL_NAME,
    RETURN_TOOL_SERVER,
    ReturnPlan,
    as_object_schema,
    auto_return_mode,
    extract_return_tool_input,
    render_tool_return_instruction,
)
from coact.stores import agents_dir
from coact.util import agent_filename, check_requirements

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


def coerce_agents(
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
            out.extend(coerce_agents(item, policy=policy))
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
    """The materialized result of host realization (files the host will discover).

    When produced by a ``dry_run`` the paths are what *would* be written/linked
    (``dry_run=True`` is recorded so the caller / CLI can label the preview);
    nothing on disk is touched.
    """

    agents: dict[str, Path] = field(default_factory=dict)
    skills: dict[str, Path] = field(default_factory=dict)
    agents_dir: Optional[Path] = None
    skills_dir: Optional[Path] = None
    warnings: list[str] = field(default_factory=list)
    dry_run: bool = False


def realize_host(
    target: RealizeTarget,
    *,
    scope: str = "project",
    dest: Path | str | None = None,
    project_dir: Path | str | None = None,
    link: bool = True,
    skills_source: Path | str | list | None = None,
    force: bool = False,
    dry_run: bool = False,
    policy: Optional[CompletionPolicy] = None,
) -> RealizedHost:
    """Materialize agents (+ linked skills) so the host agent runs them.

    Writes ``<dest>/<name>.md`` for each agent and (when ``link``) symlinks each
    **referenced** skill into the sibling ``.claude/skills/`` so Claude Code
    discovers both. ``skills_source`` (a dir or list of dirs each holding
    ``<name>/SKILL.md``) is searched first; otherwise skills are resolved by name
    via the local store / project. Verifies discovery and reports anything missing.

    Pass ``dry_run=True`` to *preview* — the returned :class:`RealizedHost` lists
    the agent files that would be written and the skills that would link (with the
    same unresolvable-skill warnings), but **no file or symlink is created**. This
    mirrors :func:`coact.complete.plan_completion`'s look-before-you-leap contract
    for the one backend that mutates the filesystem (progressive disclosure).
    """
    agents = coerce_agents(target, policy=policy)
    out_dir = (
        Path(dest)
        if dest is not None
        else agents_dir(scope=scope, project_dir=project_dir)
    )
    skills_target = out_dir.parent / "skills"
    sources = _as_source_list(skills_source)

    result = RealizedHost(
        agents_dir=out_dir, skills_dir=skills_target, dry_run=dry_run
    )
    if dry_run:
        for ad in agents:
            result.agents[ad.name] = out_dir / agent_filename(ad.name)
    else:
        out_dir.mkdir(parents=True, exist_ok=True)
        # Render every agent up-front (pure, and validates each name) so a
        # predictable failure — an unsafe name, an emit error — aborts before any
        # file is written, rather than leaving a half-written agents/ dir. D5
        # promises no transactional rollback, but partial output is avoidable.
        rendered = [
            (ad.name, out_dir / agent_filename(ad.name), emit_agent(ad, "claude-agents-md"))
            for ad in agents
        ]
        for name, path, content in rendered:
            path.write_text(content)
            result.agents[name] = path

    if link:
        if not dry_run:
            skills_target.mkdir(parents=True, exist_ok=True)
        for ad in agents:
            for skill_name in ad.skills:
                linked = _link_skill(
                    skill_name,
                    skills_target,
                    sources=sources,
                    force=force,
                    dry_run=dry_run,
                )
                if linked is not None:
                    result.skills[skill_name] = linked
                else:
                    result.warnings.append(
                        f"agent {ad.name!r} references skill {skill_name!r}, which "
                        f"could not be resolved to link into {skills_target}"
                    )

    # verify discovery — only meaningful once files actually exist (real run).
    if not dry_run:
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
        return resolve_skill(name).source_path
    except FileNotFoundError:
        return None


def _link_skill(
    name: str,
    skills_target: Path,
    *,
    sources=(),
    force: bool = False,
    dry_run: bool = False,
) -> Optional[Path]:
    """Symlink one referenced skill into ``skills_target``; None if unresolved.

    Resolution order: each ``sources`` dir (``<source>/<name>/SKILL.md``), then
    by name via the local store / project. Point-don't-copy: symlink, never copy.
    Safety invariants: a **real** (non-symlink) entry already in place is the
    user's and is never touched; a working coact symlink is kept unless ``force``;
    the source is resolved **before** any existing link is removed, so a failed
    re-link can never destroy a previously working one; a dangling symlink is
    re-linked rather than reported as discoverable. With ``dry_run`` the source is
    resolved (read-only) to predict the outcome, but no symlink is created.
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

    if dry_run:
        # Source resolves, so a (re)link *would* happen here — predict it, mutate nothing.
        return dest

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
# the native ``output_format`` option, or a forced ``return_result`` tool. The
# backend-agnostic pieces (naming, ReturnPlan, mode selection, object-schema
# coercion, instruction rendering, tool-use extraction) live in
# :mod:`coact.return_contract`; what stays here is the SDK-specific *wiring*
# (the in-process MCP server, ``ClaudeAgentOptions``, ``mcp_servers`` coercion).


def _coerce_mcp_servers(servers: Any) -> tuple[dict, list[str]]:
    """Coerce coact's ``mcp_servers`` to the SDK's ``dict[name -> config]`` shape.

    ``AgentDefinition.mcp_servers`` is a list of *names or inline-dict configs* (the
    portable, frontmatter-friendly form), but the Agent SDK wants a
    ``dict[str, McpServerConfig]``. Returns ``(servers_dict, warnings)``:

    - a dict is taken as-is (already keyed by name);
    - an inline config dict is keyed by its ``name`` field, by its single key if it
      is itself a ``{name: config}`` mapping, or positionally as a last resort;
    - a bare **name string** cannot be turned into an SDK config here, so it is
      reported in ``warnings`` (not silently dropped) — the ``host`` backend
      resolves such names, the ``sdk`` backend needs an inline config.

    >>> _coerce_mcp_servers([])
    ({}, [])
    >>> _coerce_mcp_servers({'s': {'type': 'sdk'}})
    ({'s': {'type': 'sdk'}}, [])
    >>> d, w = _coerce_mcp_servers(['bare_name'])
    >>> d, ('bare_name' in w[0])
    ({}, True)
    """
    if not servers:
        return {}, []
    if isinstance(servers, dict):
        return dict(servers), []
    out: dict = {}
    warnings: list[str] = []
    for i, item in enumerate(servers):
        if isinstance(item, dict):
            name = item.get("name")
            if isinstance(name, str):
                out[name] = item
            elif len(item) == 1 and isinstance(next(iter(item.values())), dict):
                out.update(item)  # already a {name: config} mapping
            else:
                out[f"server_{i}"] = item
        elif isinstance(item, str):
            warnings.append(
                f"mcp server {item!r} is a bare name with no inline config; the "
                "sdk backend needs a config dict — declare it inline in the "
                "coact: mcp block, or use backend='host'."
            )
        else:
            warnings.append(f"unrecognized mcp_servers entry: {item!r}")
    return out, warnings


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

    def _resolved_return(self) -> ReturnPlan:
        """Resolve how this agent's return contract maps onto the SDK (no API call).

        Honors ``return_mode`` and, in ``'auto'``, the installed SDK's
        capabilities. ``.schema()`` resolves an inline schema or a ``schema_ref``
        to canonical JSON Schema. A *truly empty* contract yields ``mode='none'``;
        a *declared-but-unresolvable* one (a ``schema_ref`` that fails to import)
        raises rather than silently dropping the contract.
        """
        if self.return_mode not in ("auto", "output_format", "tool"):
            raise ValueError(
                f"Unknown return_mode {self.return_mode!r}; "
                "expected 'auto', 'output_format', or 'tool'."
            )
        from claude_agent_sdk import ClaudeAgentOptions

        option_fields = {f.name for f in dataclasses.fields(ClaudeAgentOptions)}
        schema = self.agent_def.returns.schema()
        if not schema:
            # Distinguish "no contract" from "contract declared but unresolved".
            if self.agent_def.returns.is_empty():
                return ReturnPlan("none", {})
            raise ValueError(
                f"Return contract references schema_ref "
                f"{self.agent_def.returns.ref!r}, which could not be resolved to a "
                "JSON Schema. Install the module that defines it, or supply an "
                "inline json_schema."
            )
        mode = self.return_mode
        if mode == "auto":
            mode = auto_return_mode(option_fields)
        if mode == "output_format":
            # An explicit output_format request must not be silently swallowed by
            # _filter_kwargs on an SDK that lacks the field (the 'auto' path would
            # have chosen 'tool' instead).
            if "output_format" not in option_fields:
                raise ValueError(
                    "return_mode='output_format' but the installed claude_agent_sdk "
                    "has no output_format option (it predates structured output). "
                    "Upgrade claude-agent-sdk, or use return_mode='auto' to fall back "
                    "to the forced return_result tool automatically (or 'tool' to "
                    "force it)."
                )
            return ReturnPlan("output_format", schema)
        obj_schema, unwrap_key = as_object_schema(schema)
        return ReturnPlan("tool", obj_schema, unwrap_key, RETURN_TOOL_FULLNAME)

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
        kwargs["allowed_tools"] = (
            list(tools) if tools is not None else list(self.default_tools)
        )
        if self.agent_def.disallowed_tools:
            kwargs["disallowed_tools"] = list(self.agent_def.disallowed_tools)
        if self.agent_def.model:
            kwargs["model"] = self.agent_def.model
        # Normalize mcp_servers to the SDK's dict shape on EVERY path (never hand
        # the SDK a bare list); the return-tool fallback then merges into this dict.
        servers, _ = _coerce_mcp_servers(self.agent_def.mcp_servers)
        if servers:
            kwargs["mcp_servers"] = servers
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

        desc = (
            self.agent_def.returns.description or "Return your final structured result."
        )

        @tool(RETURN_TOOL_NAME, desc, obj_schema)
        async def _return_result(args):  # pragma: no cover - runs in the SDK loop
            return {"content": [{"type": "text", "text": "Result recorded."}]}

        server = create_sdk_mcp_server(RETURN_TOOL_SERVER, tools=[_return_result])
        # build_options already normalized mcp_servers to a dict (or left it unset);
        # merge ours in without clobbering the agent's own servers.
        existing = kwargs.get("mcp_servers")
        servers = dict(existing) if isinstance(existing, dict) else {}
        servers[RETURN_TOOL_SERVER] = server
        kwargs["mcp_servers"] = servers

        allowed = list(kwargs.get("allowed_tools") or [])
        if RETURN_TOOL_FULLNAME not in allowed:
            allowed.append(RETURN_TOOL_FULLNAME)
        kwargs["allowed_tools"] = allowed
        # The forced contract takes precedence: never leave the return tool sitting
        # in disallowed_tools (where it would be unreachable and break the contract).
        disallowed = kwargs.get("disallowed_tools")
        if disallowed and RETURN_TOOL_FULLNAME in disallowed:
            kwargs["disallowed_tools"] = [
                t for t in disallowed if t != RETURN_TOOL_FULLNAME
            ]

        kwargs["system_prompt"] = render_tool_return_instruction(
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
        _, mcp_warnings = _coerce_mcp_servers(self.agent_def.mcp_servers)
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
            "warnings": mcp_warnings,
            "raw": raw,
        }
        return artifact, info

    @staticmethod
    def _prompt_from(input_data: Any) -> str:
        return input_data if isinstance(input_data, str) else repr(input_data)


def _default_sdk_runner(prompt: str, options: Any) -> list:
    """Run a real Agent SDK session to completion, collecting messages.

    Uses :class:`ClaudeSDKClient` (streaming mode) rather than the one-shot
    ``query(prompt=<str>)`` helper. This is required for the D6 ``tool`` fallback:
    in-process SDK MCP servers (the forced ``return_result`` tool) are wired over
    the bidirectional control protocol, which is initialized **only** in streaming
    mode — a string prompt to ``query()`` runs one-shot and never calls
    ``initialize()``, leaving the return tool unreachable. Streaming is harmless
    for the ``output_format`` / ``none`` paths, so it is the single robust path.
    """
    import asyncio

    from claude_agent_sdk import ClaudeSDKClient

    async def _collect() -> list:
        async with ClaudeSDKClient(options=options) as client:
            await client.query(prompt)
            return [message async for message in client.receive_response()]

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
            captured = extract_return_tool_input(raw, unwrap_key)
            if captured is not None:
                return captured
        # the output_format result surfaces as ResultMessage.structured_output
        for message in raw:
            structured = getattr(message, "structured_output", None)
            if structured is not None:
                return structured
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
        # a ResultMessage carries the final text in `.result` when no blocks remain
        for message in raw:
            result = getattr(message, "result", None)
            if isinstance(result, str) and result:
                return result
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
    agents = coerce_agents(target, policy=policy)
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
        return [resolve_skill(target.source_skill or target.name)]
    return [resolve_skill(target)]


backends.register("mcp", realize_mcp)
