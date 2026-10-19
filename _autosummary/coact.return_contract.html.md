# coact.return_contract

Realizing a return contract — the backend-agnostic part of DECISIONS D6.

The return contract (an agent’s final-message JSON Schema) reaches a runtime two
ways, and the *how* is a cohesive, independently testable subsystem extracted
here out of the (large) [`coact.realize`](coact.html.md#coact.realize):

- **tool** — a forced `return_result` MCP tool whose `input_schema` IS the
  schema, plus a system-prompt instruction to call it. The structured result is
  recovered from the tool-use block. Used by the `sdk` backend (older SDKs, or
  when `output_format` can’t be honored).
- **json** — ask for a single JSON value conforming to the schema in the system
  prompt. Used by the provider-agnostic `litellm` backend (where structured
  `response_format` support varies).

This module owns: the in-process return-tool naming, the `ReturnPlan` value,
mode selection, the object-schema coercion the SDK tool needs, the two
instruction renderers (sharing one schema-fence helper — DRY across backends),
and the tool-use extraction. The SDK-specific *wiring* (building the in-process
MCP server, `ClaudeAgentOptions`) stays in [`coact.realize`](coact.html.md#coact.realize); the
provider-specific response parsing stays in [`coact.realize_litellm`](coact.html.md#coact.realize_litellm).

### Module Attributes

| [`RETURN_TOOL_SERVER`](#coact.return_contract.RETURN_TOOL_SERVER)   | In-process SDK MCP server + tool names for the forced return path.   |
|-----------------------------------------------------------------------|----------------------------------------------------------------------|
| [`RETURN_TOOL_FULLNAME`](#coact.return_contract.RETURN_TOOL_FULLNAME) | How Claude references the tool (`mcp__<server>__<tool>`).            |

### Functions

| [`as_object_schema`](#coact.return_contract.as_object_schema)(schema)                        | Coerce a return schema to a valid object `inputSchema` for the return tool.                |
|--------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------|
| [`auto_return_mode`](#coact.return_contract.auto_return_mode)(option_field_names)            | Pick the return mode in `auto`: native `output_format` if the SDK has it.                  |
| [`extract_return_tool_input`](#coact.return_contract.extract_return_tool_input)(messages, unwrap_key) | Recover the forced `return_result` tool-use input from SDK messages, or None.              |
| [`is_return_tool`](#coact.return_contract.is_return_tool)(name)                            | True if `name` denotes coact's forced return tool (server-scoped).                         |
| [`render_json_return_instruction`](#coact.return_contract.render_json_return_instruction)(schema)          | The portable structured-output instruction: ask for JSON conforming to a schema (litellm). |
| [`render_tool_return_instruction`](#coact.return_contract.render_tool_return_instruction)(...)             | Append the "you MUST call return_result" instruction to a system prompt (sdk).             |

### Classes

| [`ReturnPlan`](#coact.return_contract.ReturnPlan)(mode, schema[, unwrap_key, ...])   | How an agent's return contract is realized for the SDK (resolved once).   |
|------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------|

### coact.return_contract.RETURN_TOOL_FULLNAME *= 'mcp_\_coact_return_\_return_result'*

How Claude references the tool (`mcp__<server>__<tool>`).

### coact.return_contract.RETURN_TOOL_SERVER *= 'coact_return'*

In-process SDK MCP server + tool names for the forced return path.

### *class* coact.return_contract.ReturnPlan(mode, schema, unwrap_key=None, tool_fullname='')

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

How an agent’s return contract is realized for the SDK (resolved once).

### coact.return_contract.as_object_schema(schema)

Coerce a return schema to a valid object `inputSchema` for the return tool.

The Agent SDK passes a dict `input_schema` through unchanged only when it is
an object schema with **both** `type: object` and `properties`; any other
dict is misread as a `{param: type}` map (and mangled). So:

- An object schema *with* `properties` → passed through, no wrapping.
- A free-form object schema (`type: object` but no `properties`) → given an
  empty `properties` key so the SDK passes it through verbatim. Crucially it
  is **not** wrapped: wrapping a free-form object under `result` would make a
  model’s own single-key `{result: ...}` output indistinguishable from the
  wrapper (a silent-collapse hazard).
- Any non-object schema (array / scalar) → wrapped under a `result` key, with
  that key returned so extraction can unwrap it.

```pycon
>>> as_object_schema({'type': 'object', 'properties': {'a': {}}})[1] is None
True
>>> as_object_schema({'type': 'object'})  # free-form object: passed through, not wrapped
({'type': 'object', 'properties': {}}, None)
>>> as_object_schema({'type': 'array', 'items': {'type': 'string'}})
({'type': 'object', 'properties': {'result': {'type': 'array', 'items': {'type': 'string'}}}, 'required': ['result']}, 'result')
```

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict), [`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]]

### coact.return_contract.auto_return_mode(option_field_names)

Pick the return mode in `auto`: native `output_format` if the SDK has it.

```pycon
>>> auto_return_mode({'system_prompt', 'output_format'})
'output_format'
>>> auto_return_mode({'system_prompt'})  # older SDK without the field
'tool'
```

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### coact.return_contract.extract_return_tool_input(messages, unwrap_key)

Recover the forced `return_result` tool-use input from SDK messages, or None.

Scans assistant messages for a tool-use block calling the return tool and
returns its `input` (the last one wins). When the schema was wrapped (a
non-object return type), the single `result` key is unwrapped.

* **Return type:**
  [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)

### coact.return_contract.is_return_tool(name)

True if `name` denotes coact’s forced return tool (server-scoped).

Matches the full MCP name, or any prefix variant scoped to coact’s own server
(`…__coact_return__return_result`). Deliberately does **not** match a bare
`return_result` or a `return_result` on a *different* MCP server, so a
user’s own same-named tool is never mistaken for the return contract.

```pycon
>>> is_return_tool('mcp__coact_return__return_result')
True
>>> is_return_tool('mcp__other_server__return_result')
False
>>> is_return_tool('Read')
False
```

* **Return type:**
  [`bool`](https://docs.python.org/3/builtins/functions.html#bool)

### coact.return_contract.render_json_return_instruction(schema)

The portable structured-output instruction: ask for JSON conforming to a schema (litellm).

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### coact.return_contract.render_tool_return_instruction(system_prompt, obj_schema, description)

Append the “you MUST call return_result” instruction to a system prompt (sdk).

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)
