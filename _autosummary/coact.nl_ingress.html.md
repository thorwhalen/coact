# coact.nl_ingress

NL-description → IntegrationSpec — the **opt-in LLM ingress** for PUBLISH.

[`coact.integration.integration_spec_from()`](coact.integration.html.md#coact.integration.integration_spec_from) is the *mechanical* ingress: it
turns `'module:function'` refs / callables / skills into an
[`IntegrationSpec`](coact.integration.html.md#coact.integration.IntegrationSpec) with **zero** LLM (DECISIONS D10).
This module is the *opt-in* LLM path — it refines a natural-language description
of a desired integration into a **draft** `IntegrationSpec` (name, description,
proposed tools with input JSON schemas), routing generation through `aix`
(provider-agnostic, per the route-through-aix policy) via `oa`’s
prompt-as-function machinery.

D10 is upheld two ways: (1) nothing on a mechanical path imports this module, and
(2) `oa`/`aix` are imported **lazily inside** the entry function, so
`import coact` pulls in neither and a missing backend raises an actionable
`ImportError` rather than imposing a hard dependency.

The result is a *draft*: each tool is *proposed* (no importable handler) unless
the description named existing code. Binding proposed tools to real
`module:function` handlers — or supplying them — is the user’s next step before
a runnable `.mcpb` can be built (coact writes the design; the user owns the
code, mirroring the D8/D13 scaffold philosophy).

### Module Attributes

| [`DFLT_AUTHORING_PROMPTS`](#coact.nl_ingress.DFLT_AUTHORING_PROMPTS)   | Per-target authoring-prompt library.   |
|---------------------------------------------------------------------------|----------------------------------------|

### Functions

| [`integration_spec_from_description`](#coact.nl_ingress.integration_spec_from_description)(description, \*)   | Refine a natural-language `description` into a **draft** IntegrationSpec.   |
|-------------------------------------------------------------------------------------------------------|-----------------------------------------------------------------------------|

### coact.nl_ingress.DFLT_AUTHORING_PROMPTS *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [str](https://docs.python.org/3/builtins/stdtypes.html#str)]* *= {'integration': 'You are an expert architect of AI-chatbot integrations (MCP servers).\\n\\nTurn the natural-language description below into a structured plan for an\\nintegration that exposes a small set of well-designed tools.\\n\\nRespond with ONLY a single JSON object (no prose, no markdown fences). The JSON\\nobject must have exactly these keys:\\n- "name": a short kebab-case name for the integration (string).\\n- "description": one sentence summarizing what the integration does (string).\\n- "tools": an array of tool objects. Each tool object has:\\n    - "name": a snake_case verb_noun tool name (for example get_weather), string.\\n    - "description": what the tool does, when to use it, and key boundaries or\\n      examples. Tool naming and description quality dominate reliability — make\\n      each one precise and unambiguous (string).\\n    - "input_schema": a JSON Schema (draft 2020-12) describing the tool\\'s input —\\n      type object, a properties map, and a required list where appropriate.\\n    - "handler": a "module:function" reference ONLY if the description explicitly\\n      names existing importable code for this tool; otherwise null.\\n- "resources": an array of short names for readable data resources (or empty).\\n- "prompts": an array of short names for templated workflows (or empty).\\n\\nDesign guidance:\\n- Prefer a few well-named, task-aligned tools over many overlapping ones.\\n- Keep input schemas minimal and typed; mark genuinely-required fields required.\\n\\nNatural-language description of the desired integration:\\n{description}\\n'}*

Per-target authoring-prompt library. coact owns these templates as the SSOT
(one entry per publish target — extend as targets land). `pyrompt` is the
recommended place to *manage and iterate* on authoring prompts; load one there
and pass it via `prompt_template=` to override the default used here.

### coact.nl_ingress.integration_spec_from_description(description, , llm=None, model=None, name=None, version='0.1.0', author=None, prompt_template=None, infer_tool_schemas=True)

Refine a natural-language `description` into a **draft** IntegrationSpec.

The opt-in LLM ingress (DECISIONS D10): generation is routed through `aix`
(provider-agnostic) by default, via `oa`’s prompt-as-function machinery.

* **Parameters:**
  * **description** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – What the integration should do, in plain language.
  * **llm** ([`Any`](https://docs.python.org/3/library/typing.html#typing.Any)) – The LLM backend. `None` → `aix.chat` (the default, multi-provider);
    a `callable(prompt, **kwargs) -> str` is used as-is (handy for tests);
    a `str` is treated as a model name passed to `aix.chat`.
  * **model** ([`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]) – Explicit model id (overrides a model-name `llm`); `None` lets the
    backend resolve its own configured default.
  * **name** ([`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]) – Force the integration name (else the model proposes one). Kebab-cased.
  * **version** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – Spec version string.
  * **author** ([`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]) – Optional author name recorded on the spec.
  * **prompt_template** ([`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]) – Override the authoring prompt (e.g. one managed in
    `pyrompt`). Must contain a single `{description}` placeholder.
  * **infer_tool_schemas** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – When a proposed tool lacks an `input_schema`, infer
    one from its description via `oa.infer_schema_from_verbal_description`
    (aix-backed). Best-effort — failures leave the schema `None`.
* **Return type:**
  [`IntegrationSpec`](coact.integration.html.md#coact.integration.IntegrationSpec)
* **Returns:**
  An [`IntegrationSpec`](coact.integration.html.md#coact.integration.IntegrationSpec) whose `tool_specs` hold the
  proposed tools. Tools the description bound to existing code become runnable
  refs (`spec.runnable_refs()`); the rest are design drafts to bind later.

Example (offline, with an injected backend):

```pycon
>>> reply = (
...     '{"name": "wx", "description": "weather",'
...     ' "tools": [{"name": "get_weather", "description": "lookup",'
...     ' "input_schema": {"type": "object", "properties": {"city":'
...     ' {"type": "string"}}}, "handler": null}]}'
... )
>>> spec = integration_spec_from_description("a weather tool", llm=lambda p, **k: reply)
>>> spec.name, [t.name for t in spec.tool_specs], spec.runnable_refs()
('wx', ['get_weather'], [])
```
