"""Tests for the argh CLI verbs (``coact.__main__``).

The CLI wrappers format core results for the terminal; calling them directly
(rather than via a subprocess) exercises ``__main__.py`` and keeps the suite fast
and offline. The sdk verb is gated on the optional SDK.
"""

from __future__ import annotations

import importlib.util

import pytest

from coact import __main__ as cli

_HAS_SDK = importlib.util.find_spec("claude_agent_sdk") is not None


def _skill(tmp_path, name="ux", desc="Analyze a UX evidence bundle for issues."):
    d = tmp_path / ".claude" / "skills" / name
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {desc}\n---\n# {name}\nDo the work.\n"
    )
    return d


def test_cli_plan_renders_provenance(tmp_path):
    out = cli.plan(str(_skill(tmp_path)))
    assert "AgentPlan" in out and "model" in out


def test_cli_complete_prints_md(tmp_path):
    out = cli.complete(str(_skill(tmp_path)))
    assert out.startswith("---") and "name: ux" in out


def test_cli_complete_plan_flag(tmp_path):
    assert "AgentPlan" in cli.complete(str(_skill(tmp_path)), plan=True)


def test_cli_complete_writes_dest(tmp_path):
    dest = tmp_path / "agents"
    out = cli.complete(str(_skill(tmp_path)), dest=str(dest))
    assert out.startswith("Wrote ") and (dest / "ux.md").exists()


def test_cli_emit_default_target(tmp_path):
    md = cli.emit(str(_skill(tmp_path)), target="claude-agents-md")
    assert md.startswith("---") and "ux" in md


def test_cli_realize_host(tmp_path):
    skill = _skill(tmp_path)
    out = cli.realize(
        str(skill),
        backend="host",
        dest=str(tmp_path / "out" / "agents"),
        skills_source=str(tmp_path / ".claude" / "skills"),
    )
    assert "Realized (host)" in out and "ux.md" in out


def test_cli_realize_dry_run_writes_nothing(tmp_path):
    dest = tmp_path / "out" / "agents"
    out = cli.realize(
        str(_skill(tmp_path)),
        backend="host",
        dest=str(dest),
        skills_source=str(tmp_path / ".claude" / "skills"),
        dry_run=True,
    )
    assert "dry-run" in out and "ux.md" in out
    assert not dest.exists()  # preview mutated nothing


@pytest.mark.skipif(not _HAS_SDK, reason="claude_agent_sdk not installed")
def test_cli_realize_sdk_message(tmp_path):
    out = cli.realize(str(_skill(tmp_path)), backend="sdk")
    assert "RunnableAgent" in out and "aw.AgenticStep" in out


def test_cli_diff(tmp_path):
    skill = _skill(tmp_path)
    cli.complete(str(skill), dest=str(tmp_path / "agents"))
    out = cli.diff(str(skill), str(tmp_path / "agents" / "ux.md"))
    assert "diff:" in out and "prompt" in out


def test_cli_estimate_no_args_hints():
    assert "Pass one or more" in cli.estimate()


def test_cli_estimate(tmp_path):
    skill = _skill(tmp_path)
    cli.complete(str(skill), dest=str(tmp_path / "agents"))
    out = cli.estimate(str(tmp_path / "agents" / "ux.md"))
    assert "estimate:" in out and "agent" in out


def test_cli_inventory(tmp_path):
    _skill(tmp_path)
    out = cli.inventory(str(tmp_path))
    assert "inventory:" in out and "ux" in out


def test_cli_back_is_lossy_stub(tmp_path):
    skill = _skill(tmp_path)
    cli.complete(str(skill), dest=str(tmp_path / "agents"))
    out = cli.back(str(tmp_path / "agents" / "ux.md"))
    assert "lossy" in out.lower() and out.startswith("---")


def test_cli_scaffold_prints_and_writes(tmp_path):
    skill = _skill(tmp_path)
    cli.complete(str(skill), dest=str(tmp_path / "agents"))
    md = str(tmp_path / "agents" / "ux.md")
    printed = cli.scaffold([md])
    assert "AGENTS" in printed and "ux" in printed
    dest = tmp_path / "fleet.py"
    wrote = cli.scaffold([md], dest=str(dest))
    assert "Wrote" in wrote and dest.exists()


def test_cli_describe_renders_draft(monkeypatch):
    import json

    from coact import nl_ingress

    reply = json.dumps(
        {
            "name": "wx",
            "description": "weather",
            "tools": [
                {
                    "name": "get_weather",
                    "description": "lookup",
                    "input_schema": {"type": "object", "properties": {}},
                    "handler": None,
                }
            ],
            "resources": [],
            "prompts": [],
        }
    )
    # default backend is aix.chat; stub it so the CLI verb runs offline
    monkeypatch.setattr(nl_ingress, "_aix_chat", lambda: (lambda p, **k: reply))
    out = cli.describe("a weather tool")
    assert "IntegrationSpec: wx" in out
    assert "get_weather" in out and "proposed" in out


def test_main_wires_every_verb(monkeypatch):
    # main() registers exactly the documented verbs into argh.dispatch_commands.
    registered = {}

    def fake_dispatch(commands):
        registered["names"] = [c.__name__ for c in commands]
        registered["callable"] = all(callable(c) for c in commands)

    monkeypatch.setattr(cli.argh, "dispatch_commands", fake_dispatch)
    cli.main()
    assert registered["callable"]
    assert set(registered["names"]) == {
        "plan", "complete", "emit", "realize",
        "diff", "estimate", "inventory", "back", "scaffold", "publish", "describe",
    }
