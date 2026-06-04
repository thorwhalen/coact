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
from coact.complete import complete, plan_completion
from coact.emit import emit_agent, emitters, from_claude_agent_md, to_claude_agent_md
from coact.frontmatter import (
    CoactMeta,
    parse_coact_meta,
    register_validator,
    validate_coact_block,
)
from coact.policy import CompletionPolicy, default_policy
from coact.realize import (
    RealizedHost,
    RunnableAgent,
    realize,
    realize_host,
    realize_sdk,
)
from coact.realize import backends as realization_backends
from coact.stores import AgentStore, agents_dir

# Make `skill validate` aware of the coact: block as soon as coact is imported.
register_validator()

__version__ = "0.0.2"

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
    "RealizedHost",
    "RunnableAgent",
    "realization_backends",
    # Emit
    "emit_agent",
    "emitters",
    "to_claude_agent_md",
    "from_claude_agent_md",
    # Frontmatter convention
    "CoactMeta",
    "parse_coact_meta",
    "validate_coact_block",
    "register_validator",
    # Stores
    "AgentStore",
    "agents_dir",
]
