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


def _link_skill(
    name: str,
    skills_target: Path,
    *,
    sources: list[Path] = (),
    force: bool = False,
) -> Optional[Path]:
    """Symlink one referenced skill into ``skills_target``; None if unresolved.

    Resolution order: each ``sources`` dir (``<source>/<name>/SKILL.md``), then
    by name via the local store / project (``_resolve_skill``). Point-don't-copy:
    symlink, never copy the skill body. If already present it is left as-is.
    """
    dest = skills_target / name
    if dest.exists() or dest.is_symlink():
        if not force:
            return dest  # already discoverable
        if dest.is_symlink() or dest.is_file():
            dest.unlink()
        else:
            shutil.rmtree(dest)

    source: Optional[Path] = None
    for src_dir in sources:
        candidate = Path(src_dir) / name
        if (candidate / "SKILL.md").exists():
            source = candidate
            break
    if source is None:
        try:
            source = _resolve_skill(name).source_path
        except FileNotFoundError:
            source = None
    if source is None:
        return None

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
        # wire the return contract to the SDK's structured-output option (D6).
        if self.agent_def.returns.json_schema:
            kwargs["output_format"] = self.agent_def.returns.json_schema
        return ClaudeAgentOptions(**_filter_kwargs(ClaudeAgentOptions, kwargs))

    def execute(
        self, input_data: Any, context: Any = None
    ) -> tuple[Any, dict[str, Any]]:
        """Run the agent over ``input_data``; return ``(artifact, info)`` (aw protocol)."""
        options = self.build_options()
        prompt = self._prompt_from(input_data)
        runner = self.runner or _default_sdk_runner
        raw = runner(prompt, options)
        artifact = _extract_artifact(raw)
        info = {
            "agent": self.agent_def.name,
            "model": self.agent_def.model,
            "backend": "sdk",
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


def _extract_artifact(raw: Any) -> Any:
    """Best-effort extraction of the agent's result from a runner's return value."""
    if isinstance(raw, str):
        return raw
    # a structured-output carrying object
    structured = getattr(raw, "structured_output", None)
    if structured is not None:
        return structured
    # a list of SDK messages -> concatenate text blocks of the last assistant message
    if isinstance(raw, list) and raw:
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
    policy: Optional[CompletionPolicy] = None,
) -> RunnableAgent:
    """Realize a single agent as a runnable :class:`RunnableAgent` (aw-compatible)."""
    agents = _coerce_agents(target, policy=policy)
    if len(agents) != 1:
        raise ValueError(
            f"backend='sdk' realizes exactly one agent; got {len(agents)}. "
            "Realize each separately (topology is out of scope — DECISIONS D8)."
        )
    return RunnableAgent(agent_def=agents[0], llm=llm, runner=runner)


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
