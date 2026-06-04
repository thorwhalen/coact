"""Realizing a return contract — the backend-agnostic part of DECISIONS D6.

The return contract (an agent's final-message JSON Schema) reaches a runtime two
ways, and the *how* is a cohesive, independently testable subsystem extracted
here out of the (large) :mod:`coact.realize`:

- **tool** — a forced ``return_result`` MCP tool whose ``input_schema`` IS the
  schema, plus a system-prompt instruction to call it. The structured result is
  recovered from the tool-use block. Used by the ``sdk`` backend (older SDKs, or
  when ``output_format`` can't be honored).
- **json** — ask for a single JSON value conforming to the schema in the system
  prompt. Used by the provider-agnostic ``litellm`` backend (where structured
  ``response_format`` support varies).

This module owns: the in-process return-tool naming, the ``ReturnPlan`` value,
mode selection, the object-schema coercion the SDK tool needs, the two
instruction renderers (sharing one schema-fence helper — DRY across backends),
and the tool-use extraction. The SDK-specific *wiring* (building the in-process
MCP server, ``ClaudeAgentOptions``) stays in :mod:`coact.realize`; the
provider-specific response parsing stays in :mod:`coact.realize_litellm`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Optional

#: In-process SDK MCP server + tool names for the forced return path.
RETURN_TOOL_SERVER = "coact_return"
RETURN_TOOL_NAME = "return_result"
#: How Claude references the tool (``mcp__<server>__<tool>``).
RETURN_TOOL_FULLNAME = f"mcp__{RETURN_TOOL_SERVER}__{RETURN_TOOL_NAME}"


@dataclass(frozen=True)
class ReturnPlan:
    """How an agent's return contract is realized for the SDK (resolved once)."""

    mode: str  # "none" | "output_format" | "tool"
    schema: dict
    unwrap_key: Optional[str] = None
    tool_fullname: str = ""


def auto_return_mode(option_field_names) -> str:
    """Pick the return mode in ``auto``: native ``output_format`` if the SDK has it.

    >>> auto_return_mode({'system_prompt', 'output_format'})
    'output_format'
    >>> auto_return_mode({'system_prompt'})  # older SDK without the field
    'tool'
    """
    return "output_format" if "output_format" in set(option_field_names) else "tool"


def as_object_schema(schema: dict) -> tuple[dict, Optional[str]]:
    """Coerce a return schema to a valid object ``inputSchema`` for the return tool.

    The Agent SDK passes a dict ``input_schema`` through unchanged only when it is
    an object schema with **both** ``type: object`` and ``properties``; any other
    dict is misread as a ``{param: type}`` map (and mangled). So:

    - An object schema *with* ``properties`` → passed through, no wrapping.
    - A free-form object schema (``type: object`` but no ``properties``) → given an
      empty ``properties`` key so the SDK passes it through verbatim. Crucially it
      is **not** wrapped: wrapping a free-form object under ``result`` would make a
      model's own single-key ``{result: ...}`` output indistinguishable from the
      wrapper (a silent-collapse hazard).
    - Any non-object schema (array / scalar) → wrapped under a ``result`` key, with
      that key returned so extraction can unwrap it.

    >>> as_object_schema({'type': 'object', 'properties': {'a': {}}})[1] is None
    True
    >>> as_object_schema({'type': 'object'})  # free-form object: passed through, not wrapped
    ({'type': 'object', 'properties': {}}, None)
    >>> as_object_schema({'type': 'array', 'items': {'type': 'string'}})
    ({'type': 'object', 'properties': {'result': {'type': 'array', 'items': {'type': 'string'}}}, 'required': ['result']}, 'result')
    """
    if isinstance(schema, dict) and schema.get("type") == "object":
        if "properties" in schema:
            return schema, None
        return {**schema, "properties": {}}, None
    return (
        {"type": "object", "properties": {"result": schema}, "required": ["result"]},
        "result",
    )


def _schema_fence(schema: dict) -> str:
    """Render a JSON Schema as a fenced ``json`` block (shared by both renderers)."""
    return f"```json\n{json.dumps(schema, indent=2)}\n```"


def render_tool_return_instruction(
    system_prompt: str, obj_schema: dict, description: str
) -> str:
    """Append the "you MUST call return_result" instruction to a system prompt (sdk)."""
    suffix = f" ({description})" if description else ""
    instruction = (
        "\n\n## Return contract\n"
        f"When you have finished, you MUST call the `{RETURN_TOOL_NAME}` tool "
        f"exactly once with your final result{suffix}. Its arguments must conform "
        f"to this JSON Schema:\n\n{_schema_fence(obj_schema)}\n"
        f"Do not return the result as prose — call `{RETURN_TOOL_NAME}` instead."
    )
    return (system_prompt or "") + instruction


def render_json_return_instruction(schema: dict) -> str:
    """The portable structured-output instruction: ask for JSON conforming to a schema (litellm)."""
    return (
        "## Return contract\n"
        "Respond with a single JSON value conforming to this JSON Schema. Output "
        f"JSON only — no prose, no code fences.\n\n{_schema_fence(schema)}"
    )


def is_return_tool(name: str) -> bool:
    """True if ``name`` denotes coact's forced return tool (server-scoped).

    Matches the full MCP name, or any prefix variant scoped to coact's own server
    (``…__coact_return__return_result``). Deliberately does **not** match a bare
    ``return_result`` or a ``return_result`` on a *different* MCP server, so a
    user's own same-named tool is never mistaken for the return contract.

    >>> is_return_tool('mcp__coact_return__return_result')
    True
    >>> is_return_tool('mcp__other_server__return_result')
    False
    >>> is_return_tool('Read')
    False
    """
    return name == RETURN_TOOL_FULLNAME or name.endswith(
        f"__{RETURN_TOOL_SERVER}__{RETURN_TOOL_NAME}"
    )


def extract_return_tool_input(messages: list, unwrap_key: Optional[str]) -> Any:
    """Recover the forced ``return_result`` tool-use input from SDK messages, or None.

    Scans assistant messages for a tool-use block calling the return tool and
    returns its ``input`` (the last one wins). When the schema was wrapped (a
    non-object return type), the single ``result`` key is unwrapped.
    """
    found = None
    for message in messages:
        content = getattr(message, "content", None)
        if not isinstance(content, list):
            continue
        for block in content:
            name = getattr(block, "name", None)
            block_input = getattr(block, "input", None)
            if name and block_input is not None and is_return_tool(name):
                found = block_input
    if found is None:
        return None
    if unwrap_key and isinstance(found, dict) and set(found) == {unwrap_key}:
        return found[unwrap_key]
    return found
