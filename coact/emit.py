"""Emitters: one :class:`~coact.base.AgentDefinition` → many serializations.

COACT_SPEC §5.3. Emit targets are an open-closed ``skill``-style
:class:`~skill.registry.Registry` (register, don't hardcode). Two ship by
default:

- ``claude-agents-md`` — the filesystem ``.claude/agents/<name>.md`` (host
  frontmatter using the host's exact camelCase field names + the persona body).
  coact-specific fields (the return contract, ``consumes``, ``source_skill``) are
  carried in an additive ``coact:`` frontmatter sub-block so the round-trip is
  lossless and the host still ignores them. Reuses ``skill.base`` frontmatter
  helpers — coact writes no YAML by hand.
- ``sdk-agent-dict`` — kwargs for ``claude_agent_sdk.AgentDefinition`` plus the
  leftover ``query()`` options, built by **introspecting** the installed SDK
  dataclass so it degrades gracefully across SDK versions (DECISIONS D2). The
  SDK is imported lazily here only; core stays SDK-free.

Future emitters (CrewAI / OpenAI via the ``aw`` adapter) register without
touching this module. Topology is never emitted (DECISIONS D8).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from skill.base import parse_frontmatter, render_frontmatter
from skill.registry import Registry

from coact.base import AgentDefinition, ReturnContract
from coact.util import check_requirements

#: Registry of emit targets: ``AgentDefinition -> serialized form`` (str or dict).
emitters: Registry[Callable[[AgentDefinition], Any]] = Registry("emitters")

# Mapping from AgentDefinition snake_case fields to the host's frontmatter names.
# Only the host-recognized subagent fields appear here; coact-specific fields go
# in the additive `coact:` sub-block.
_SNAKE_TO_HOST = {
    "disallowed_tools": "disallowedTools",
    "mcp_servers": "mcpServers",
    "permission_mode": "permissionMode",
}
_HOST_TO_SNAKE = {v: k for k, v in _SNAKE_TO_HOST.items()}


# ---------------------------------------------------------------------------
# claude-agents-md
# ---------------------------------------------------------------------------


def agent_to_frontmatter(ad: AgentDefinition) -> dict:
    """Build the host frontmatter dict for an agent (omitting empty fields).

    >>> ad = AgentDefinition(name='x', description='y', tools=['Read'], model='haiku')
    >>> fm = agent_to_frontmatter(ad)
    >>> fm['name'], fm['tools'], fm['model']
    ('x', ['Read'], 'haiku')
    """
    fm: dict[str, Any] = {"name": ad.name, "description": ad.description}
    if ad.tools is not None:
        fm["tools"] = ad.tools
    if ad.disallowed_tools:
        fm["disallowedTools"] = ad.disallowed_tools
    if ad.model:
        fm["model"] = ad.model
    if ad.skills:
        fm["skills"] = ad.skills
    if ad.memory:
        fm["memory"] = ad.memory
    if ad.mcp_servers:
        fm["mcpServers"] = ad.mcp_servers
    if ad.permission_mode:
        fm["permissionMode"] = ad.permission_mode

    # coact-specific fields in an additive, host-ignored sub-block.
    coact_block: dict[str, Any] = {}
    if not ad.returns.is_empty():
        coact_block["returns"] = ad.returns.to_dict()
    if ad.consumes:
        coact_block["consumes"] = ad.consumes
    if ad.source_skill:
        coact_block["source_skill"] = ad.source_skill
    if coact_block:
        fm["coact"] = coact_block
    return fm


def to_claude_agent_md(ad: AgentDefinition) -> str:
    """Serialize an agent to ``.claude/agents/<name>.md`` content.

    >>> ad = AgentDefinition(name='ux', description='Analyze.', prompt='You are...')
    >>> md = to_claude_agent_md(ad)
    >>> md.startswith('---') and 'name: ux' in md and 'You are...' in md
    True
    """
    frontmatter = render_frontmatter(agent_to_frontmatter(ad))
    body = ad.prompt or ""
    return f"{frontmatter}\n{body}".rstrip() + "\n"


def from_claude_agent_md(text: str) -> AgentDefinition:
    """Parse ``.claude/agents/*.md`` content back into an :class:`AgentDefinition`.

    The inverse of :func:`to_claude_agent_md`: lossless for every **structured**
    field; the ``prompt`` body is whitespace-trimmed on both ends (personas are
    not whitespace-sensitive).

    >>> ad = AgentDefinition(name='ux', description='Analyze.', prompt='You are an analyst.',
    ...     tools=['Read', 'Grep'], model='sonnet',
    ...     returns=ReturnContract(json_schema={'type': 'object'}, description='out'))
    >>> back = from_claude_agent_md(to_claude_agent_md(ad))
    >>> (back.name, back.tools, back.model, back.prompt) == (ad.name, ad.tools, ad.model, ad.prompt)
    True
    >>> back.returns.json_schema
    {'type': 'object'}
    """
    meta, body = parse_frontmatter(text)
    coact_block = meta.get("coact") or {}
    return AgentDefinition(
        name=meta.get("name", ""),
        description=meta.get("description", ""),
        prompt=body.strip(),
        tools=meta.get("tools"),
        disallowed_tools=meta.get("disallowedTools") or [],
        model=meta.get("model"),
        skills=meta.get("skills") or [],
        memory=meta.get("memory"),
        mcp_servers=meta.get("mcpServers") or [],
        permission_mode=meta.get("permissionMode"),
        returns=ReturnContract.from_dict(coact_block.get("returns")),
        consumes=coact_block.get("consumes"),
        source_skill=coact_block.get("source_skill"),
    )


emitters.register("claude-agents-md", to_claude_agent_md)


# ---------------------------------------------------------------------------
# sdk-agent-dict
# ---------------------------------------------------------------------------

# AgentDefinition field -> SDK AgentDefinition field name (camelCase where the
# SDK uses it). Only fields the SDK might accept are listed; we filter against
# the *installed* dataclass so missing ones fall through to `options`.
_AD_TO_SDK_FIELD = {
    "description": "description",
    "prompt": "prompt",
    "tools": "tools",
    "model": "model",
    "skills": "skills",
    "memory": "memory",
    "mcp_servers": "mcpServers",
    "disallowed_tools": "disallowedTools",
}


def to_sdk_agent_dict(ad: AgentDefinition) -> dict:
    """Build Agent-SDK kwargs + leftover query options for one agent.

    Returns ``{'name', 'agent_kwargs', 'options'}`` where ``agent_kwargs`` are
    accepted by the *installed* ``claude_agent_sdk.AgentDefinition`` and
    ``options`` holds fields that version cannot express (to be wired into
    ``query()`` by the ``sdk`` realize backend). Requires the Agent SDK.
    """
    check_requirements(
        {"claude_agent_sdk": "claude-agent-sdk"}, feature="sdk-agent-dict"
    )
    import dataclasses

    from claude_agent_sdk import AgentDefinition as SDKAgentDefinition

    accepted = {f.name for f in dataclasses.fields(SDKAgentDefinition)}
    agent_kwargs: dict[str, Any] = {}
    options: dict[str, Any] = {}

    for ad_field, sdk_field in _AD_TO_SDK_FIELD.items():
        value = getattr(ad, ad_field)
        if ad_field == "tools":
            # Preserve the None (inherit all) vs [] (no tools) distinction (base.py):
            # drop only None; an empty allowlist is meaningful and must be emitted.
            if value is None:
                continue
        elif value in (None, [], "", {}):
            continue
        if sdk_field in accepted:
            agent_kwargs[sdk_field] = value
        else:
            options[ad_field] = value

    # description & prompt are required by the SDK dataclass; ensure present.
    agent_kwargs.setdefault("description", ad.description)
    agent_kwargs.setdefault("prompt", ad.prompt or ad.description)

    if not ad.returns.is_empty():
        options["returns"] = ad.returns
    if ad.permission_mode:
        options["permission_mode"] = ad.permission_mode

    return {"name": ad.name, "agent_kwargs": agent_kwargs, "options": options}


emitters.register("sdk-agent-dict", to_sdk_agent_dict)


# ---------------------------------------------------------------------------
# Optional aw-bridged emitters (CrewAI / OpenAI) — reuse aw's renderers
# ---------------------------------------------------------------------------


def to_aw_agent_spec(ad: AgentDefinition):
    """Adapt an :class:`AgentDefinition` to an ``aw.translators.AgentSpec``.

    Lets coact reuse ``aw``'s CrewAI / OpenAI / SKILL.md renderers (the
    ``*_from_spec`` cores) instead of reimplementing them — the ecosystem
    coordination point. Requires ``aw``.
    """
    check_requirements({"aw": "aw"}, feature="aw-bridged emitters")
    from aw.translators import AgentSpec, ToolSpec

    return AgentSpec(
        name=ad.name,
        description=ad.description,
        instructions=ad.prompt or ad.description,
        tools=[ToolSpec(name=t) for t in (ad.tools or [])],
        model=ad.model or "",
        source_class=ad.name,
    )


def _register_aw_emitters() -> None:
    """Register ``crewai`` / ``openai-tools`` emitters when ``aw`` is importable."""
    try:
        from aw.translators import crewai_yaml_from_spec, openai_tools_from_spec
    except Exception:
        return
    emitters.register(
        "crewai", lambda ad: crewai_yaml_from_spec(to_aw_agent_spec(ad), name=ad.name)
    )
    emitters.register(
        "openai-tools", lambda ad: openai_tools_from_spec(to_aw_agent_spec(ad))
    )


_register_aw_emitters()


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------


def emit_agent(
    ad: AgentDefinition,
    target: str = "claude-agents-md",
    *,
    dest: str | Path | None = None,
) -> Any:
    """Emit an agent to a registered target; optionally write a file target to ``dest``.

    For string targets (e.g. ``claude-agents-md``) with ``dest`` given, writes
    ``<dest>/<name>.md`` and returns the :class:`~pathlib.Path`. Otherwise
    returns the emitter's value (str or dict).

    >>> ad = AgentDefinition(name='ux', description='Analyze.', prompt='You are...')
    >>> emit_agent(ad).splitlines()[0]
    '---'
    """
    emitter = emitters.get(target)
    if emitter is None:
        available = ", ".join(sorted(emitters))
        raise ValueError(f"Unknown emit target: {target!r}. Available: {available}")
    result = emitter(ad)
    if dest is not None and isinstance(result, str):
        out = Path(dest) / f"{ad.name}.md"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(result)
        return out
    return result
