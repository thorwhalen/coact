"""Shared pytest configuration.

Live ``real_llm`` tests (those that make a real API / agent-runtime call) are
**skipped by default** so the suite stays offline and CI never spends tokens. Opt
in by setting ``COACT_RUN_REAL_LLM=1`` (and providing the relevant credentials).
"""

import os

import pytest

_RUN_REAL_LLM_ENV = "COACT_RUN_REAL_LLM"


def pytest_collection_modifyitems(config, items):
    """Skip every ``@pytest.mark.real_llm`` test unless explicitly opted in."""
    if os.environ.get(_RUN_REAL_LLM_ENV):
        return
    skip_live = pytest.mark.skip(
        reason=f"live LLM test; set {_RUN_REAL_LLM_ENV}=1 (with credentials) to run"
    )
    for item in items:
        if "real_llm" in item.keywords:
            item.add_marker(skip_live)
