"""Tests for ``coact.return_contract`` — the backend-agnostic D6 helpers.

These were extracted from ``coact.realize`` so they can be tested directly,
independent of the Claude Agent SDK (no SDK import here). The SDK *wiring* that
consumes them is tested in ``test_realize.py``.
"""

from __future__ import annotations

from types import SimpleNamespace

from coact.return_contract import (
    RETURN_TOOL_FULLNAME,
    ReturnPlan,
    as_object_schema,
    auto_return_mode,
    extract_return_tool_input,
    is_return_tool,
    render_json_return_instruction,
    render_tool_return_instruction,
)


def test_return_plan_defaults():
    plan = ReturnPlan("none", {})
    assert plan.mode == "none" and plan.unwrap_key is None and plan.tool_fullname == ""


def test_auto_return_mode():
    assert auto_return_mode({"output_format", "system_prompt"}) == "output_format"
    assert auto_return_mode({"system_prompt"}) == "tool"


def test_as_object_schema_passthrough_and_wrap():
    obj = {"type": "object", "properties": {"a": {"type": "string"}}}
    assert as_object_schema(obj) == (obj, None)
    # free-form object: empty properties added, NOT wrapped
    assert as_object_schema({"type": "object"}) == ({"type": "object", "properties": {}}, None)
    # scalar/array: wrapped under result
    wrapped, key = as_object_schema({"type": "integer"})
    assert key == "result" and wrapped["properties"]["result"] == {"type": "integer"}


def test_render_tool_return_instruction_embeds_schema_and_tool():
    out = render_tool_return_instruction("You are X.", {"type": "object"}, "a result")
    assert out.startswith("You are X.")
    assert "return_result" in out and "## Return contract" in out
    assert "(a result)" in out and '"type": "object"' in out


def test_render_tool_return_instruction_no_system_prompt():
    out = render_tool_return_instruction("", {"type": "object"}, "")
    assert out.startswith("\n\n## Return contract")


def test_render_json_return_instruction_asks_for_json_only():
    out = render_json_return_instruction({"type": "object"})
    assert "JSON only" in out and "no prose" in out and '```json' in out


def test_is_return_tool_server_scoped():
    assert is_return_tool(RETURN_TOOL_FULLNAME)
    assert is_return_tool("mcp__coact_return__return_result")
    assert not is_return_tool("mcp__other__return_result")
    assert not is_return_tool("return_result")
    assert not is_return_tool("Read")


def _msg(*blocks):
    return SimpleNamespace(content=list(blocks))


def _tool(name, payload):
    return SimpleNamespace(name=name, input=payload)


def test_extract_return_tool_input_last_wins():
    msgs = [
        _msg(_tool(RETURN_TOOL_FULLNAME, {"v": 1})),
        _msg(_tool(RETURN_TOOL_FULLNAME, {"v": 2})),
    ]
    assert extract_return_tool_input(msgs, None) == {"v": 2}


def test_extract_return_tool_input_unwraps_result_key():
    msgs = [_msg(_tool(RETURN_TOOL_FULLNAME, {"result": [1, 2]}))]
    assert extract_return_tool_input(msgs, "result") == [1, 2]


def test_extract_return_tool_input_does_not_unwrap_extra_keys():
    msgs = [_msg(_tool(RETURN_TOOL_FULLNAME, {"result": [1], "x": 2}))]
    assert extract_return_tool_input(msgs, "result") == {"result": [1], "x": 2}


def test_extract_return_tool_input_none_when_absent():
    assert extract_return_tool_input([_msg(_tool("Read", {"p": 1}))], None) is None
    # non-list content is skipped, not crashed on
    assert extract_return_tool_input([SimpleNamespace(content="text")], None) is None
