"""coact — reuse your AI stuff across the layers of the modern agent stack.

``coact`` ("co-act": skills and agents acting as one reusable substrate) owns the
two transitions the rest of the ecosystem doesn't::

    python functions/scripts  →  .claude/skills/  →  .claude/agents/  →  running agents
            (py2mcp, aw)            (skill pkg)         COMPLETE (coact)    REALIZE (coact)

- **COMPLETE** lifts ``.claude/skills/`` into ``.claude/agents/`` definitions,
  adding the agent-only "extras" (persona, return contract, tool allowlist,
  model, memory).
- **REALIZE** turns a completed definition into an actually running agent,
  picking an execution backend (host agent / Agent SDK / MCP-exposed).

It is glue over ``skill`` (foundation), ``aw`` (runtime substrate), and
``py2mcp`` (tool exposure) — see ``misc/docs/REUSE.md``.

Simple usage::

    from coact import complete, emit_agent, realize

    agent = complete('.claude/skills/ux-analyst')      # Skill -> AgentDefinition
    emit_agent(agent, 'claude-agents-md', dest='.claude/agents/')
    realize(agent, backend='host')                     # materialize for Claude Code
"""

from coact.base import (
    AgentDefinition,
    AgentPlan,
    FieldProvenance,
    ReturnContract,
)
from coact.analysis import back, diff, estimate, inventory
from coact.complete import complete, plan_completion
from coact.emit import (
    emit_agent,
    emitters,
    from_claude_agent_md,
    to_aw_agent_spec,
    to_claude_agent_md,
)
from coact.frontmatter import (
    CoactMeta,
    parse_coact_meta,
    register_validator,
    validate_coact_block,
)
from coact.llm import resolve_llm, structured
from coact.policy import CompletionPolicy, default_policy
from coact.realize import (
    RealizedHost,
    RunnableAgent,
    realize,
    realize_host,
    realize_mcp,
    realize_sdk,
)
from coact.realize import backends as realization_backends
from coact.realize_litellm import (
    RunnableLLMAgent,
    realize_litellm,
)  # registers 'litellm'
from coact.realize_langgraph import (
    RunnableLLMGraphAgent,
    realize_langgraph,
)  # registers 'langgraph'
from coact.realize_crewai import (
    RunnableCrewAIAgent,
    realize_crewai,
)  # registers 'crewai'
from coact.integration import IntegrationSpec, integration_spec_from
from coact.publish import PublishResult, publish, publish_targets
from coact.publish_mcpb import publish_mcpb  # registers 'claude-local-mcpb'
from coact.scaffold import scaffold_fleet
from coact.stores import AgentStore, agents_dir
from coact.synthesis import synthesize_persona, synthesize_return_contract

# Make `skill validate` aware of the coact: block as soon as coact is imported.
register_validator()


def _resolve_version() -> str:
    """Read the installed distribution version (SSOT = pyproject), else a sentinel.

    Sourcing ``__version__`` from installed metadata keeps it from drifting away
    from ``pyproject.toml`` (the version wads bumps on release) — there is no
    second literal to forget to update. A source checkout that was never installed
    has no metadata, so a clearly-marked sentinel is returned rather than a stale
    number.
    """
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version("coact")
    except PackageNotFoundError:  # pragma: no cover - only in an uninstalled tree
        return "0.0.0+unknown"


__version__ = _resolve_version()

__all__ = [
    # Core data model (SSOT)
    "AgentDefinition",
    "AgentPlan",
    "FieldProvenance",
    "ReturnContract",
    # COMPLETE
    "complete",
    "plan_completion",
    "CompletionPolicy",
    "default_policy",
    # REALIZE
    "realize",
    "realize_host",
    "realize_sdk",
    "realize_mcp",
    "realize_litellm",
    "realize_langgraph",
    "realize_crewai",
    "RealizedHost",
    "RunnableAgent",
    "RunnableLLMAgent",
    "RunnableLLMGraphAgent",
    "RunnableCrewAIAgent",
    "realization_backends",
    # PUBLISH (ship a capability to a chatbot host; Claude-local .mcpb first; D17)
    "IntegrationSpec",
    "integration_spec_from",
    "publish",
    "publish_targets",
    "PublishResult",
    "publish_mcpb",
    # Scaffold (the one topology-adjacent emitter — a starter you own; D8)
    "scaffold_fleet",
    # Synthesis & LLM facade
    "synthesize_persona",
    "synthesize_return_contract",
    "resolve_llm",
    "structured",
    # Emit
    "emit_agent",
    "emitters",
    "to_claude_agent_md",
    "from_claude_agent_md",
    "to_aw_agent_spec",
    # Analysis
    "diff",
    "estimate",
    "inventory",
    "back",
    # Frontmatter convention
    "CoactMeta",
    "parse_coact_meta",
    "validate_coact_block",
    "register_validator",
    # Stores
    "AgentStore",
    "agents_dir",
]
