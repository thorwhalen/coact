"""Tests for the provider-agnostic LLM facade (``coact.llm``).

Focus on the *fallback* paths that keep the mechanical contract intact: no
provider configured → ``None`` (callers use templates); an injected ``llm`` that
misbehaves never crashes (DECISIONS D10). Also covers the JSON extractors used by
the optional ``structured`` helper.
"""

from __future__ import annotations

from coact.llm import (
    _extract_json,
    _first_balanced_object,
    resolve_llm,
    structured,
)


# --- resolve_llm ------------------------------------------------------------


def test_resolve_llm_passes_callable_through():
    fn = resolve_llm(lambda p: "hi")
    assert callable(fn) and fn("x") == "hi"


def test_resolve_llm_step_config_like_object():
    class _StepConfigLike:
        def resolve_llm(self):
            return lambda p: "from-step-config"

    fn = resolve_llm(_StepConfigLike())
    assert fn("anything") == "from-step-config"


def test_resolve_llm_step_config_resolve_raises_returns_none():
    class _Broken:
        def resolve_llm(self):
            raise RuntimeError("no provider")

    assert resolve_llm(_Broken()) is None


def test_resolve_llm_step_config_resolves_non_callable_returns_none():
    class _BadResolve:
        def resolve_llm(self):
            return "not callable"

    assert resolve_llm(_BadResolve()) is None


def test_resolve_llm_unrecognized_object_returns_none():
    assert resolve_llm(object()) is None


def test_resolve_llm_none_when_no_provider(monkeypatch):
    # Force skill.ai to look unavailable so resolve_llm(None) degrades to None.
    import skill.ai as ai

    monkeypatch.setattr(ai, "is_ai_available", lambda: False)
    assert resolve_llm() is None


def test_resolve_llm_string_model_no_provider(monkeypatch):
    import skill.ai as ai

    monkeypatch.setattr(ai, "is_ai_available", lambda: False)
    assert resolve_llm("some-model") is None


def test_resolve_llm_is_ai_available_raises_returns_none(monkeypatch):
    import skill.ai as ai

    def _boom():
        raise RuntimeError("provider check exploded")

    monkeypatch.setattr(ai, "is_ai_available", _boom)
    assert resolve_llm() is None


def test_resolve_llm_provider_available_returns_chat_wrapper(monkeypatch):
    import skill.ai as ai

    seen = {}

    def _chat(prompt, model=None):
        seen["prompt"], seen["model"] = prompt, model
        return "chat-reply"

    monkeypatch.setattr(ai, "is_ai_available", lambda: True)
    monkeypatch.setattr(ai, "chat", _chat)
    fn = resolve_llm("haiku")
    assert callable(fn) and fn("hello") == "chat-reply"
    assert seen == {"prompt": "hello", "model": "haiku"}


# --- structured -------------------------------------------------------------


def test_structured_none_llm_returns_none(monkeypatch):
    import skill.ai as ai

    monkeypatch.setattr(ai, "is_ai_available", lambda: False)
    assert structured("do it", {"type": "object"}, llm=None) is None


def test_structured_llm_yields_none_no_crash():
    # an injected llm that returns None must not crash (the _extract_json guard).
    assert structured("do it", {"type": "object"}, llm=lambda p: None) is None


def test_structured_parses_json_from_llm():
    out = structured("x", {"type": "object"}, llm=lambda p: '{"a": 1}')
    assert out == {"a": 1}


def test_structured_retries_then_gives_up():
    calls = {"n": 0}

    def flaky(prompt):
        calls["n"] += 1
        return "not json at all"

    assert structured("x", {"type": "object"}, llm=flaky, retries=1) is None
    assert calls["n"] == 2  # initial + 1 retry


def test_structured_non_dict_json_keeps_trying():
    # a JSON array is not a dict -> structured insists on an object, then None.
    assert structured("x", {"type": "object"}, llm=lambda p: "[1, 2, 3]") is None


# --- _extract_json / _first_balanced_object ---------------------------------


def test_extract_json_none_input_returns_none():
    # the D10 "no crash" guard: a None reply yields None, not AttributeError.
    assert _extract_json(None) is None
    assert _extract_json(123) is None


def test_extract_json_fenced_block():
    assert _extract_json('```json\n{"k": 1}\n```') == {"k": 1}


def test_extract_json_trailing_prose():
    assert _extract_json('{"k": 1} and then prose {with braces}') == {"k": 1}


def test_extract_json_no_object_returns_none():
    assert _extract_json("no json here") is None


def test_first_balanced_object_handles_strings_with_braces():
    assert _first_balanced_object('{"a": "}{"}') == '{"a": "}{"}'


def test_first_balanced_object_unclosed_returns_none():
    assert _first_balanced_object("prefix {unclosed") is None


def test_first_balanced_object_no_open_brace_returns_none():
    assert _first_balanced_object("no braces") is None
