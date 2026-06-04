"""Live end-to-end smoke tests for the realization backends (opt-in).

These actually call a model, so they're marked ``real_llm`` and **skipped unless
``COACT_RUN_REAL_LLM=1``** (see ``conftest.py``). They close the loop the unit
tests can't: a real definition → a real runnable → a real structured answer. Kept
economical (cheapest model, tiny prompt, minimal schema). Run with::

    COACT_RUN_REAL_LLM=1 pytest tests/test_live_realize.py -v
"""

import os

import pytest

from coact import AgentDefinition, ReturnContract, realize

_SUM_CONTRACT = ReturnContract(
    json_schema={
        "type": "object",
        "properties": {"sum": {"type": "integer"}},
        "required": ["sum"],
    },
    description="The integer sum.",
)


def _need_anthropic_key():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        pytest.skip("ANTHROPIC_API_KEY not set")


@pytest.mark.real_llm
def test_litellm_backend_live_structured_output():
    """litellm backend returns the structured result for a trivial task."""
    pytest.importorskip("litellm")
    _need_anthropic_key()

    agent = AgentDefinition(
        name="adder",
        description="Adds two integers.",
        prompt="You add integers. Use the return contract; do not explain.",
        model="haiku",
        returns=_SUM_CONTRACT,
    )
    runnable = realize(
        agent,
        backend="litellm",
        # any LiteLLM-resolvable model; override here to whatever your key can reach
        model_map={"haiku": os.environ.get("COACT_LIVE_MODEL", "anthropic/claude-haiku-4-5")},
    )
    artifact, info = runnable.execute("Compute 2 + 3 and put it in 'sum'.")

    assert info["backend"] == "litellm"
    assert isinstance(artifact, dict), f"expected a structured dict, got {artifact!r}"
    assert int(artifact["sum"]) == 5


@pytest.mark.real_llm
def test_sdk_backend_live_runs():
    """sdk backend executes end-to-end and returns a non-empty artifact.

    The SDK spawns the Claude Code CLI subprocess; if that runtime isn't available
    in this environment the test skips rather than failing (it's an opt-in smoke).
    """
    pytest.importorskip("claude_agent_sdk")
    _need_anthropic_key()

    agent = AgentDefinition(
        name="ponger",
        description="Replies tersely.",
        prompt="Reply with exactly one word: pong",
        model="haiku",
    )
    runnable = realize(agent, backend="sdk")
    try:
        artifact, info = runnable.execute("ping")
    except Exception as exc:  # CLI/auth/runtime not available -> skip, don't fail
        pytest.skip(f"sdk runtime unavailable: {type(exc).__name__}: {exc}")

    assert info["backend"] == "sdk"
    assert artifact  # some non-empty result came back
