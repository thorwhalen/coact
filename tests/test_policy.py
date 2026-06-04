"""Tests for ``coact.policy`` — the injectable model/memory/tool routing table."""

from __future__ import annotations

from skill.base import Skill, SkillMeta

from coact.frontmatter import CoactMeta
from coact.policy import CompletionPolicy, default_policy


def _skill(body="steps", name="x", description="y", resources=None):
    s = Skill(meta=SkillMeta(name=name, description=description), body=body)
    if resources is not None:
        s.resources = resources
    return s


def test_choose_model_haiku_read_only():
    model, why = default_policy.choose_model(
        tools=["Read", "Grep"], description="Audit the bundle.", n_skills=1
    )
    assert model == "haiku" and "read-only" in why


def test_choose_model_opus_keyword():
    model, why = default_policy.choose_model(
        tools=["Read"], description="Orchestrate the review.", n_skills=1
    )
    assert model == "opus"


def test_choose_model_opus_many_skills():
    model, why = default_policy.choose_model(
        tools=["Write"], description="Do work.", n_skills=3
    )
    assert model == "opus" and "skills" in why


def test_choose_model_default_worker():
    model, why = default_policy.choose_model(
        tools=["Read", "Write"], description="Implement the fix.", n_skills=1
    )
    assert model == "sonnet" and "default worker" in why


def test_choose_memory_default_none():
    memory, why = default_policy.choose_memory()
    assert memory is None and "no memory" in why


def test_choose_memory_when_policy_sets_default():
    memory, why = default_policy.override(default_memory="project").choose_memory()
    assert memory == "project" and "policy default" in why


def test_infer_tools_declared_wins():
    tools, why = default_policy.infer_tools(
        _skill(), CoactMeta(tools=["Read", "Bash"])
    )
    assert tools == ["Read", "Bash"] and "declared" in why


def test_infer_tools_scripts_add_bash():
    tools, why = default_policy.infer_tools(
        _skill(resources={"scripts": {}}), CoactMeta()
    )
    assert "Bash" in tools and "scripts" in why


def test_infer_tools_write_keyword_adds_write_edit():
    tools, why = default_policy.infer_tools(
        _skill(body="Write the report and edit the file."), CoactMeta()
    )
    assert "Write" in tools and "Edit" in tools and "writing" in why


def test_policy_override_returns_new_instance():
    p = CompletionPolicy()
    p2 = p.override(default_model="opus")
    assert p2.default_model == "opus" and p.default_model == "sonnet" and p2 is not p
