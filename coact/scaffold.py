"""Scaffold a *starter* multi-agent shim — the one topology-adjacent thing coact emits.

COACT_SPEC §6.4 / DECISIONS D8. coact emits agent *definitions* + tool/MCP wiring
and **stops at topology** — it is not LangGraph, and a subagent definition can't
express graphs/edges/cycles. The single sanctioned exception is *scaffolding*: for
a multi-agent run, coact may emit a **starter Python file** that wires N realized
``sdk`` agents under an ``aw`` coordinator, "clearly marked as a starting point the
user owns." That file is data coact writes once, not a runtime coact operates.

:func:`scaffold_fleet` is exactly that emitter: it takes the same targets
``realize`` accepts (agents, skills, ``*.md`` files, or a list) and returns — or
writes — a runnable, heavily-commented sequential-pipeline starter the user then
reshapes. It runs **no LLM and stands up no runtime** (it only renders source);
the emitted shim defers all execution to ``coact.realize(..., backend='sdk')`` and
all topology to the human who owns it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional, Union

from coact.policy import CompletionPolicy
from coact.realize import RealizeTarget, coerce_agents

#: Default filename when ``dest`` is a directory.
DEFAULT_SHIM_NAME = "fleet.py"


def scaffold_fleet(
    target: RealizeTarget,
    *,
    dest: Union[str, Path, None] = None,
    agents_dir: str = ".claude/agents",
    policy: Optional[CompletionPolicy] = None,
) -> Union[str, Path]:
    """Emit a starter shim wiring the target agents as a runnable ``sdk`` fleet.

    ``target`` is anything :func:`coact.realize` accepts (an
    :class:`~coact.base.AgentDefinition`, a skill source, an agent ``*.md`` path,
    or a list of these). Returns the shim **source string**; if ``dest`` is given
    (a file path, or a directory in which ``fleet.py`` is written) the file is
    written and its :class:`~pathlib.Path` returned instead.

    The shim references each agent by name under ``agents_dir`` and chains them
    **sequentially** — a deliberately thin starting point. It is the *only*
    topology-adjacent artifact coact produces (DECISIONS D8): coact writes it once
    and never runs it; you own the control flow from there.

    >>> from coact import AgentDefinition
    >>> shim = scaffold_fleet([AgentDefinition(name='collector', description='x'),
    ...                         AgentDefinition(name='summarizer', description='y')])
    >>> 'AGENTS = ["collector", "summarizer"]' in shim
    True
    >>> 'backend="sdk"' in shim and 'YOU OWN THIS FILE' in shim
    True
    """
    agents = coerce_agents(target, policy=policy)
    if not agents:
        raise ValueError("scaffold_fleet needs at least one agent to wire.")
    source = _render_fleet_shim([ad.name for ad in agents], agents_dir=agents_dir)
    if dest is None:
        return source
    out = Path(dest)
    if out.is_dir() or out.suffix == "":
        out = out / DEFAULT_SHIM_NAME
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(source)
    return out


def _render_fleet_shim(names: list[str], *, agents_dir: str) -> str:
    """Render the starter-shim source for ``names`` (pure string build, no I/O)."""
    agents_literal = "[" + ", ".join(json.dumps(n) for n in names) + "]"
    agents_dir_literal = json.dumps(agents_dir)
    # NOTE: this is a code *template*. Keep it dependency-light and runnable as-is;
    # every coact-specific concern (cost gate, D8 boundary, ownership) is stated in
    # the emitted docstring/comments so the file is self-explanatory once on disk.
    return f'''"""Starter multi-agent fleet — YOU OWN THIS FILE (coact scaffolded it).

coact emits agent *definitions* and stops at topology (DECISIONS D8): it is not
LangGraph. This starter wires the agents below as a simple SEQUENTIAL hand-off so
you have a running fleet to shape. Replace the control flow with whatever the task
needs — branches, parallel fan-out, validation, retries — using ``aw.orchestration``
or the Claude Agent SDK directly. coact will not regenerate or overwrite your edits.

Cost gate (DECISIONS D9): a running fleet costs ~an order of magnitude more tokens
than a single host agent, and the premium is worst on *interdependent* tasks. Run
``coact estimate {" ".join(agents_dir + "/" + n + ".md" for n in names)}`` first;
prefer ``backend='host'`` unless you have a real throughput/isolation need.
"""

from __future__ import annotations

from pathlib import Path

from coact import realize

#: The agents this fleet coordinates, by name (each is one ``<name>.md`` definition).
AGENTS = {agents_literal}

#: Where the agent ``*.md`` definitions live (override per call).
AGENTS_DIR = {agents_dir_literal}


def build_fleet(agents_dir: str = AGENTS_DIR) -> dict:
    """Realize each agent as an ``aw.AgenticStep``-compatible ``sdk`` runnable."""
    return {{
        name: realize(Path(agents_dir) / f"{{name}}.md", backend="sdk")
        for name in AGENTS
    }}


def run(task, *, agents_dir: str = AGENTS_DIR):
    """Run the fleet over ``task``. STARTER: a sequential hand-off — edit me.

    Each agent's ``(artifact, info)`` feeds the next. Insert your real topology
    where marked: inspect ``artifact`` / ``info`` to branch, validate, retry, or
    fan out (e.g. with ``aw.orchestration.AgenticWorkflow``).
    """
    steps = build_fleet(agents_dir)
    artifact, infos = task, []
    for name in AGENTS:
        artifact, info = steps[name].execute(artifact, context={{}})
        infos.append(info)
        # TODO(you): branch / validate / retry / fan out on artifact + info here.
    return artifact, infos


if __name__ == "__main__":
    import sys

    result, _ = run(sys.argv[1] if len(sys.argv) > 1 else "")
    print(result)
'''
