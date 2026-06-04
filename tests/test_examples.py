"""Smoke test for the examples walkthrough — keeps the docs from rotting.

Examples are excluded from ruff/coverage, but exercising ``walkthrough.main`` here
ensures the public API the README advertises keeps working end-to-end (no LLM, no
API call). The optional ``sdk`` step is guarded inside ``main``.
"""

import importlib.util
from pathlib import Path

_EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


def _load_walkthrough():
    spec = importlib.util.spec_from_file_location(
        "coact_example_walkthrough", _EXAMPLES / "walkthrough.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_example_skill_exists():
    assert (_EXAMPLES / "skills" / "ux-analyst" / "SKILL.md").is_file()


def test_walkthrough_runs_end_to_end(tmp_path):
    walkthrough = _load_walkthrough()
    result = walkthrough.main(dest=tmp_path)

    # COMPLETE produced the expected agent + return contract.
    assert result["agent_name"] == "ux-analyst"
    assert result["return_props"] == ["findings", "summary"]
    # the coact: block drove the lift (not just policy defaults).
    assert "coact-frontmatter" in result["provenance_sources"]
    # REALIZE(host) materialized the agent file and linked the skill.
    assert result["host_agent_files"] == ["ux-analyst.md"]
    assert result["host_linked_skills"] == ["ux-analyst"]
    assert (tmp_path / ".claude" / "agents" / "ux-analyst.md").is_file()
    assert (tmp_path / ".claude" / "skills" / "ux-analyst").exists()
    # analysis ran; the agent is discoverable in the inventory.
    assert result["inventory_agents"] == 1
    assert result["estimate_rendered"]
