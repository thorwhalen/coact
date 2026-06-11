"""CrewAI realization backend — one definition → one composable ``crewai.Agent``.

Realizes a **single** :class:`~coact.base.AgentDefinition` (DECISIONS D8) into a
``crewai.Agent`` run via the lightweight ``Agent.kickoff()`` path — deliberately
**not** ``Crew``/``Task``: a Crew would force inventing a Task and serialize a
degenerate one-agent crew, i.e. topology. The ``Agent`` instance IS the
framework-native object and is **exposed** (via :meth:`RunnableCrewAIAgent.build_agent`
/ the ``.agent`` property) so *you* drop it into *your own*
``Crew(agents=[runnable.agent, ...], tasks=[...], process=...)``. coact builds no
Crew, Task, or Process — that orchestration is yours to own.

Like the ``sdk``/``litellm`` backends it produces an ``aw.AgenticStep``-compatible
runnable (``execute(input_data, context) -> (artifact, info)``); the run call is
**injectable** so it is unit-testable with no API key and no ``crewai`` install, and
it **self-registers** into :data:`coact.realize.backends` on import (open-closed).

Notable specifics:

- **Model strings are slash-form** LiteLLM strings (``"anthropic/claude-sonnet-4-5"``) —
  CrewAI consumes LiteLLM model strings, so the default map matches
  :mod:`coact.realize_litellm` verbatim. Open-closed via ``model_map=``.
- **Return contract (D6) is belt-and-suspenders.** CrewAI's ``kickoff(response_format=)``
  wants a pydantic **class**, not a JSON-Schema dict — synthesized at run time from the
  canonical schema by :func:`coact._pydantic_schema.json_schema_to_model`, which returns
  ``None`` for non-flat schemas (then coact relies on the prompt-only instruction always
  embedded in the agent's backstory and JSON-parses the text result). This is the one
  asymmetry with ``langgraph``, which enforces deep schemas natively via ``ToolStrategy``.
- **Tools are opt-in** via ``tools_map={name: callable | BaseTool}``: coact tools are
  host-resolved *name strings* (D12), so bare names are never passed; unbound names are
  reported in ``info['warnings']``.
- CrewAI requires Python ``>=3.10,<3.14``; coact pins only ``>=3.10`` (compatible) and
  does **not** tighten its own ``requires-python`` for one optional backend.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Optional

from coact._pydantic_schema import json_schema_to_model
from coact.base import AgentDefinition
from coact.policy import CompletionPolicy
from coact.realize import RealizeTarget, backends, coerce_agents
from coact.realize_litellm import _to_user_text, _try_json  # DRY: reuse, never edit
from coact.return_contract import render_json_return_instruction
from coact.util import check_requirements

#: Map coact's model *selectors* to LiteLLM slash-form strings (CrewAI speaks LiteLLM).
#: Mirrors :data:`coact.realize_litellm.DEFAULT_MODEL_MAP`; override via ``model_map=``.
DEFAULT_MODEL_MAP: dict = {
    "haiku": "anthropic/claude-3-5-haiku-latest",
    "sonnet": "anthropic/claude-sonnet-4-5",
    "opus": "anthropic/claude-opus-4-1",
    "inherit": "openai/gpt-4o-mini",
}
#: Used when the definition pins no model and none maps.
DEFAULT_MODEL = "openai/gpt-4o-mini"


@dataclass
class RunnableCrewAIAgent:
    """An ``aw.AgenticStep``-compatible runnable backed by a single ``crewai.Agent``.

    The ``Agent`` is built lazily and cached; ``runner`` is injectable so the agent
    runs in tests with no API key and no ``crewai`` install (dependency injection).
    The ``Agent`` is exposed via :meth:`build_agent` / the :attr:`agent` property.

    >>> from coact import AgentDefinition
    >>> ad = AgentDefinition(name='x', description='d', prompt='You are X.', model='sonnet')
    >>> RunnableCrewAIAgent(ad).resolve_model()
    'anthropic/claude-sonnet-4-5'
    """

    agent_def: AgentDefinition
    model_map: dict = field(default_factory=lambda: dict(DEFAULT_MODEL_MAP))
    default_model: str = DEFAULT_MODEL
    #: ``runner(*, agent, input_text, response_format) -> output`` (``.raw`` / ``.pydantic``);
    #: defaults to :func:`_default_crewai_runner`. The DI seam (mirrors litellm ``completion=``).
    runner: Optional[Callable[..., Any]] = None
    #: ``{tool_name: callable | crewai BaseTool}`` — opt-in tool binding (D12); names with
    #: no entry are reported in ``info['warnings']`` and never passed on.
    tools_map: Optional[dict] = None
    #: Also request native structured output (synthesized pydantic class) when possible.
    use_response_format: bool = True
    _agent_cache: Any = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        # Defensive copy (mirrors RunnableLLMAgent): never alias/mutate the caller's dict.
        self.model_map = dict(self.model_map)

    def resolve_model(self) -> str:
        """Map the definition's model selector to a LiteLLM model string (slash form)."""
        model = self.agent_def.model
        if model in self.model_map:
            return self.model_map[model]
        return model or self.default_model

    def build_role(self) -> str:
        """The CrewAI ``role`` (required, non-empty) — the agent's name."""
        return self.agent_def.name

    def build_goal(self) -> str:
        """The CrewAI ``goal`` (required, non-empty)."""
        return (
            self.agent_def.description
            or self.agent_def.prompt
            or "(no goal specified)"
        )

    def build_backstory(self) -> str:
        """The CrewAI ``backstory`` (persona + the D6 return-contract instruction)."""
        body = (
            self.agent_def.prompt or self.agent_def.description or self.agent_def.name
        )
        schema = self.agent_def.returns.schema()
        if schema:
            return (body + "\n\n" + render_json_return_instruction(schema)).strip()
        return body

    def build_response_model(self) -> Optional[type]:
        """Synthesize the pydantic class for ``kickoff(response_format=)``, or ``None``.

        ``None`` when there is no schema, ``use_response_format`` is off, or the schema
        is not flat enough to represent (then coact relies on the prompt instruction).
        """
        schema = self.agent_def.returns.schema()
        if not schema or not self.use_response_format:
            return None
        return json_schema_to_model(schema)

    def _resolve_tools(self) -> tuple[list, list[str]]:
        """Split declared tool names into (bound values, unbound names) via tools_map."""
        if self.tools_map is None:
            return [], []
        bound: list = []
        unbound: list[str] = []
        for name in self.agent_def.tools or []:
            if name in self.tools_map:
                bound.append(self.tools_map[name])
            else:
                unbound.append(name)
        return bound, unbound

    def build_agent(self) -> Any:
        """Build (once) and return the framework-native ``crewai.Agent``.

        Pure with respect to API calls — constructing the ``Agent`` does not invoke a
        model. Imports ``crewai`` lazily (checked first); only ever called on the
        default (non-injected) run path.
        """
        if self._agent_cache is None:
            check_requirements(
                {"crewai": "crewai"}, feature="realize(backend='crewai')"
            )
            from crewai import Agent

            bound, _ = self._resolve_tools()
            tools = [_as_crewai_tool(t) for t in bound]
            self._agent_cache = Agent(
                role=self.build_role(),
                goal=self.build_goal(),
                backstory=self.build_backstory(),
                llm=self.resolve_model(),
                tools=tools,
                allow_delegation=False,
                verbose=False,
            )
        return self._agent_cache

    @property
    def agent(self) -> Any:
        """The native ``crewai.Agent`` — add it to your own ``Crew(agents=[...])``."""
        return self.build_agent()

    def execute(
        self, input_data: Any, context: Any = None
    ) -> tuple[Any, dict[str, Any]]:
        """Run the agent over ``input_data``; return ``(artifact, info)`` (aw protocol).

        ``context`` is accepted for ``aw.AgenticStep`` compatibility and ignored. Uses
        the native ``.pydantic`` result when present; otherwise JSON-parses ``.raw``
        (graceful, like litellm). An injected ``runner`` keeps ``crewai`` unimported.
        """
        input_text = (
            input_data if isinstance(input_data, str) else _to_user_text(input_data)
        )
        response_format = self.build_response_model()
        has_schema = bool(self.agent_def.returns.schema())
        if self.runner is None:
            check_requirements(
                {"crewai": "crewai"}, feature="realize(backend='crewai')"
            )
            result = _default_crewai_runner(
                agent=self.build_agent(),
                input_text=input_text,
                response_format=response_format,
            )
        else:
            result = self.runner(
                agent=None, input_text=input_text, response_format=response_format
            )

        structured_used = False
        pyd = getattr(result, "pydantic", None)
        if has_schema and pyd is not None:
            artifact = pyd.model_dump() if hasattr(pyd, "model_dump") else pyd
            structured_used = True
        else:
            raw_text = getattr(result, "raw", None)
            if not isinstance(raw_text, str):
                raw_text = str(result)
            if has_schema:
                parsed = _try_json(raw_text)
                artifact = parsed if parsed is not None else raw_text
            else:
                artifact = raw_text

        warnings: list[str] = []
        _, unbound = self._resolve_tools()
        warnings += [
            f"tool {n!r} has no callable in tools_map; not bound" for n in unbound
        ]
        if has_schema and self.use_response_format and response_format is None:
            warnings.append(
                "return schema not synthesizable to a pydantic class (non-flat schema "
                "or pydantic missing); using the prompt-only return-contract fallback"
            )
        info = {
            "agent": self.agent_def.name,
            "model": self.resolve_model(),
            "backend": "crewai",
            "structured": has_schema,
            "structured_response_used": structured_used,
            "warnings": warnings,
            "raw": result,
        }
        return artifact, info


def _default_crewai_runner(
    *, agent: Any, input_text: str, response_format: Optional[type]
) -> Any:
    """Run a real ``crewai.Agent`` to completion via ``Agent.kickoff`` (lazy path)."""
    return agent.kickoff(input_text, response_format=response_format)


def _as_crewai_tool(value: Any) -> Any:
    """Best-effort wrap a bare callable as a crewai tool; pass tool-like values through.

    Runs only on the real (crewai-installed) path. A value that already looks like a
    tool (has ``run``/``_run``) is returned unchanged; a plain callable is wrapped via
    ``crewai.tools.tool``. On any failure the value is returned as-is — tools are an
    advanced opt-in, and passing a crewai ``BaseTool`` directly is the reliable route.
    """
    if callable(value) and not hasattr(value, "run") and not hasattr(value, "_run"):
        try:
            from crewai.tools import tool as _tool

            return _tool(getattr(value, "__name__", "tool"))(value)
        except Exception:
            return value
    return value


def realize_crewai(
    target: RealizeTarget,
    *,
    model_map: Optional[dict] = None,
    default_model: str = DEFAULT_MODEL,
    runner: Optional[Callable[..., Any]] = None,
    tools_map: Optional[dict] = None,
    use_response_format: bool = True,
    policy: Optional[CompletionPolicy] = None,
) -> RunnableCrewAIAgent:
    """Realize one agent as a CrewAI-backed :class:`RunnableCrewAIAgent` (aw-compatible).

    ``model_map`` overrides how coact selectors map to LiteLLM model strings;
    ``tools_map`` opt-in binds host-resolved tool *names* to callables/tools (D12);
    ``runner`` injects the run call for testing. Raises if asked to realize more than
    one agent (topology is out of scope — D8).
    """
    agents = coerce_agents(target, policy=policy)
    if len(agents) != 1:
        raise ValueError(
            f"backend='crewai' realizes exactly one agent; got {len(agents)}. "
            "Realize each separately (topology is out of scope — DECISIONS D8)."
        )
    return RunnableCrewAIAgent(
        agent_def=agents[0],
        model_map=dict(model_map) if model_map else dict(DEFAULT_MODEL_MAP),
        default_model=default_model,
        runner=runner,
        tools_map=tools_map,
        use_response_format=use_response_format,
    )


backends.register("crewai", realize_crewai)
