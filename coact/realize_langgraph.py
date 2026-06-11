"""LangGraph realization backend — one definition → one composable graph node.

Realizes a **single** :class:`~coact.base.AgentDefinition` (DECISIONS D8) into a
LangGraph ``CompiledStateGraph`` built by the modern ``langchain.agents.create_agent``
(langchain >= 1.0), falling back to ``langgraph.prebuilt.create_react_agent`` on
older installs. Both are reached through an **injectable** ``factory`` so this
backend is unit-testable with no API key and no ``langchain``/``langgraph``
installed (dependency injection, mirroring :mod:`coact.realize_litellm`).

Like the ``sdk``/``litellm`` backends it produces an ``aw.AgenticStep``-compatible
runnable (``execute(input_data, context) -> (artifact, info)``) and **self-registers**
into :data:`coact.realize.backends` on import — no core change (open-closed).

**Topology stays out (D8).** This realizes *one* agent; it never wires a graph of
many. The compiled graph IS the framework-native object and is **exposed** (via
:meth:`RunnableLLMGraphAgent.build_agent` / the ``.agent`` property) precisely so
*you* can drop it as a node into *your own* ``StateGraph``
(``g.add_node(agent.name, runnable.agent)``). coact serializes no nodes, edges, or
cycles — that orchestration is yours to own.

Notable specifics:

- **Model strings are colon-form** ``"provider:model"`` (e.g. ``"anthropic:claude-sonnet-4-5"``),
  what ``langchain``'s ``init_chat_model`` expects — distinct from the slash-form
  LiteLLM strings the ``litellm``/``crewai`` backends use. The map is open-closed
  data (``model_map=``); an explicit provider string in ``model`` is used verbatim.
  The chosen provider's ``langchain-<provider>`` integration must also be installed
  on the real path (the default model is ``openai``-prefixed → ``langchain-openai``).
- **Return contract (D6) is belt-and-suspenders:** the canonical JSON-Schema dict is
  passed to ``create_agent(response_format=ToolStrategy(schema))`` (both
  ``ToolStrategy`` and ``ProviderStrategy`` accept the raw dict) **and** embedded as a
  system-prompt instruction; ``execute`` reads the native ``structured_response`` when
  present and otherwise JSON-parses the final message text (langchain can omit
  ``structured_response`` without error), so structured output degrades gracefully.
- **Tools are opt-in** via ``tools_map={name: callable}``: coact tools are
  host-resolved *name strings* (D12), and LangGraph wants Python callables, so bare
  names are **never** passed to the framework (``tools=[]`` when no ``tools_map`` —
  the common path then matches ``litellm``). Unbound names are surfaced in
  ``info['unbound_tools']``, never silently dropped.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Optional

from coact.base import AgentDefinition
from coact.policy import CompletionPolicy
from coact.realize import RealizeTarget, backends, coerce_agents
from coact.realize_litellm import _to_user_text, _try_json  # DRY: reuse, never edit
from coact.return_contract import render_json_return_instruction
from coact.util import check_requirements

#: Map coact's model *selectors* to langchain colon-form ``"provider:model"`` strings.
#: Data, not code — pass ``model_map=`` to ``realize(..., backend='langgraph')`` to
#: target any provider. An explicit provider string in ``model`` is used verbatim.
DEFAULT_MODEL_MAP: dict = {
    "haiku": "anthropic:claude-3-5-haiku-latest",
    "sonnet": "anthropic:claude-sonnet-4-5",
    "opus": "anthropic:claude-opus-4-1",
    "inherit": "openai:gpt-4o-mini",
}
#: Used when the definition pins no model and none maps.
DEFAULT_MODEL = "openai:gpt-4o-mini"


@dataclass
class RunnableLLMGraphAgent:
    """An ``aw.AgenticStep``-compatible runnable backed by a LangGraph graph.

    The compiled graph is built lazily and cached; ``factory`` is injectable so the
    agent can be constructed and unit-tested without a live API call or a
    ``langchain``/``langgraph`` install (dependency injection). The graph itself is
    exposed via :meth:`build_agent` / the :attr:`agent` property for composition.

    >>> from coact import AgentDefinition
    >>> ad = AgentDefinition(name='x', description='d', prompt='You are X.', model='sonnet')
    >>> RunnableLLMGraphAgent(ad).resolve_model()
    'anthropic:claude-sonnet-4-5'
    """

    agent_def: AgentDefinition
    model_map: dict = field(default_factory=lambda: dict(DEFAULT_MODEL_MAP))
    default_model: str = DEFAULT_MODEL
    #: ``factory(*, model, tools, system_prompt, response_format, name) -> graph``;
    #: defaults to :func:`_default_langgraph_factory`. The primary DI seam.
    factory: Optional[Callable[..., Any]] = None
    #: Optional test-only bypass of ``graph.invoke``: ``runner(graph, state) -> result``.
    runner: Optional[Callable[[Any, Any], Any]] = None
    #: ``{tool_name: callable | BaseTool}`` — opt-in tool binding (D12); names with
    #: no entry here are reported in ``info['unbound_tools']`` and never passed on.
    tools_map: Optional[dict] = None
    #: Also request native structured output (in addition to the prompt instruction).
    use_response_format: bool = True
    #: ``'auto'`` / ``'tool'`` -> ``ToolStrategy`` (safest cross-provider); ``'provider'``
    #: -> ``ProviderStrategy`` (native provider structured output).
    structured_strategy: str = "auto"
    _agent_cache: Any = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        # Defensive copy: a caller's dict must not be aliased into — nor mutated by —
        # the agent (mirrors RunnableLLMAgent).
        self.model_map = dict(self.model_map)
        if self.structured_strategy not in ("auto", "tool", "provider"):
            raise ValueError(
                f"Unknown structured_strategy {self.structured_strategy!r}; "
                "expected 'auto', 'tool', or 'provider'."
            )

    def resolve_model(self) -> str:
        """Map the definition's model selector to a langchain ``provider:model`` string.

        A mapped selector wins; an explicit provider string in ``model`` is used
        verbatim; otherwise ``default_model``.
        """
        model = self.agent_def.model
        if model in self.model_map:
            return self.model_map[model]
        return model or self.default_model

    def build_system_prompt(self) -> str:
        """Persona (+ the D6 return-contract instruction when a schema is declared)."""
        system = self.agent_def.prompt or self.agent_def.description or ""
        schema = self.agent_def.returns.schema()
        if schema:
            system = (system + "\n\n" + render_json_return_instruction(schema)).strip()
        return system

    def build_response_format(self) -> Any:
        """Build the ``create_agent`` ``response_format`` for the return contract, or None.

        Wraps the canonical JSON-Schema dict in ``ToolStrategy`` (default) or
        ``ProviderStrategy`` — both accept the raw dict. When ``langchain`` is not
        importable (an injected factory in tests, or the ``create_react_agent``
        fallback, which accepts a bare dict), the raw schema dict is returned so the
        offline path needs no framework.
        """
        schema = self.agent_def.returns.schema()
        if not schema or not self.use_response_format:
            return None
        try:
            from langchain.agents.structured_output import (
                ProviderStrategy,
                ToolStrategy,
            )
        except ImportError:
            return schema
        if self.structured_strategy == "provider":
            return ProviderStrategy(schema)
        return ToolStrategy(schema)

    def _resolve_tools(self) -> tuple[list, list[str]]:
        """Split declared tool names into (bound callables, unbound names) via tools_map."""
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
        """Build (once) and return the framework-native ``CompiledStateGraph``.

        Pure with respect to API calls — constructing the graph does not invoke a
        model. The default path imports ``langchain``/``langgraph`` lazily and
        checks they are installed; an injected ``factory`` bypasses both.
        """
        if self._agent_cache is None:
            factory = self.factory
            if factory is None:
                check_requirements(
                    {"langchain": "langchain", "langgraph": "langgraph"},
                    feature="realize(backend='langgraph')",
                )
                factory = _default_langgraph_factory
            bound, _ = self._resolve_tools()
            self._agent_cache = factory(
                model=self.resolve_model(),
                tools=bound,
                system_prompt=self.build_system_prompt(),
                response_format=self.build_response_format(),
                name=self.agent_def.name,
            )
        return self._agent_cache

    @property
    def agent(self) -> Any:
        """The native ``CompiledStateGraph`` — add it as a node to your own ``StateGraph``."""
        return self.build_agent()

    def build_state(self, input_data: Any) -> dict:
        """Build the LangGraph input state (a single user message)."""
        content = input_data if isinstance(input_data, str) else _to_user_text(input_data)
        return {"messages": [{"role": "user", "content": content}]}

    def execute(
        self, input_data: Any, context: Any = None
    ) -> tuple[Any, dict[str, Any]]:
        """Run the agent over ``input_data``; return ``(artifact, info)`` (aw protocol).

        ``context`` is accepted for ``aw.AgenticStep`` compatibility and ignored.
        Uses the native ``structured_response`` when the graph returns one; otherwise
        falls back to JSON-parsing the final message text (graceful, like litellm) —
        langchain may omit ``structured_response`` even when a schema was requested.
        """
        graph = self.build_agent()
        runner = self.runner or (lambda g, s: g.invoke(s))
        result = runner(graph, self.build_state(input_data))
        has_schema = bool(self.agent_def.returns.schema())
        structured_used = False
        structured = (
            result.get("structured_response") if isinstance(result, dict) else None
        )
        if has_schema and structured is not None:
            artifact = _structured_to_dict(structured)
            structured_used = True
        else:
            text = _final_text(result)
            if text is None:
                artifact = result  # unexpected shape: surface raw (mirrors litellm)
            elif has_schema:
                parsed = _try_json(text)
                artifact = parsed if parsed is not None else text
            else:
                artifact = text
        _, unbound = self._resolve_tools()
        info = {
            "agent": self.agent_def.name,
            "model": self.resolve_model(),
            "backend": "langgraph",
            "structured": has_schema,
            "structured_response_used": structured_used,
            "unbound_tools": unbound,
            "raw": result,
        }
        return artifact, info


def _default_langgraph_factory(
    *, model: Any, tools: list, system_prompt: str, response_format: Any, name: str
) -> Any:
    """Build a ``CompiledStateGraph`` via ``create_agent`` (or ``create_react_agent``).

    Prefers the modern ``langchain.agents.create_agent`` (``system_prompt=``); on an
    older install without it, falls back to ``langgraph.prebuilt.create_react_agent``
    (``prompt=`` and positional ``tools``), normalizing both behind one kwarg set.
    """
    try:
        from langchain.agents import create_agent

        return create_agent(
            model,
            tools or None,
            system_prompt=system_prompt,
            response_format=response_format,
            name=name,
        )
    except ImportError:
        from langgraph.prebuilt import create_react_agent

        return create_react_agent(
            model,
            tools or [],
            prompt=system_prompt,
            response_format=response_format,
            name=name,
        )


def _final_text(result: Any) -> Optional[str]:
    """Extract the final assistant text from a LangGraph result dict, else ``None``.

    Reads ``result['messages'][-1].content`` (getattr/dict-guarded), joining a
    multi-part content list into one string.
    """
    if not isinstance(result, dict):
        return None
    messages = result.get("messages")
    if not messages:
        return None
    last = messages[-1]
    content = getattr(last, "content", None)
    if content is None and isinstance(last, dict):
        content = last.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and isinstance(block.get("text"), str):
                parts.append(block["text"])
        return "\n".join(parts) if parts else str(content)
    if content is None:
        return None
    return str(content)


def _structured_to_dict(value: Any) -> Any:
    """A pydantic ``BaseModel`` -> ``dict`` via ``model_dump()``; anything else as-is."""
    dump = getattr(value, "model_dump", None)
    if callable(dump):
        return dump()
    return value


def realize_langgraph(
    target: RealizeTarget,
    *,
    model_map: Optional[dict] = None,
    default_model: str = DEFAULT_MODEL,
    factory: Optional[Callable[..., Any]] = None,
    runner: Optional[Callable[[Any, Any], Any]] = None,
    tools_map: Optional[dict] = None,
    structured_strategy: str = "auto",
    use_response_format: bool = True,
    policy: Optional[CompletionPolicy] = None,
) -> RunnableLLMGraphAgent:
    """Realize one agent as a LangGraph-backed :class:`RunnableLLMGraphAgent` (aw-compatible).

    ``model_map`` overrides how coact selectors (``sonnet``/``opus``/``haiku``) map to
    langchain ``provider:model`` strings. ``tools_map`` opt-in binds host-resolved tool
    *names* to Python callables (D12). ``factory`` injects the graph builder for
    testing. Raises if asked to realize more than one agent (topology is out — D8).
    """
    agents = coerce_agents(target, policy=policy)
    if len(agents) != 1:
        raise ValueError(
            f"backend='langgraph' realizes exactly one agent; got {len(agents)}. "
            "Realize each separately (topology is out of scope — DECISIONS D8)."
        )
    return RunnableLLMGraphAgent(
        agent_def=agents[0],
        model_map=dict(model_map) if model_map else dict(DEFAULT_MODEL_MAP),
        default_model=default_model,
        factory=factory,
        runner=runner,
        tools_map=tools_map,
        structured_strategy=structured_strategy,
        use_response_format=use_response_format,
    )


backends.register("langgraph", realize_langgraph)
