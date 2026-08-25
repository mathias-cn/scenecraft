import json
from types import SimpleNamespace

import pytest

from app.providers.llm_client import LLMJSONError, structured_completion


class FakeCompletions:
    def __init__(self, content, recorder):
        self._content = content
        self._recorder = recorder

    def create(self, **kwargs):
        self._recorder.append(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=self._content))])


def _client(content, recorder):
    return SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions(content, recorder)))


def test_structured_completion_parses_json_object(monkeypatch):
    recorder: list[dict] = []
    monkeypatch.setattr(
        "app.providers.llm_client._openai_client",
        lambda: _client('{"scenes": [1], "title": "x"}', recorder),
    )
    result = structured_completion("Você é um planejador. Responda em JSON.", "liste as cenas")
    assert result == {"scenes": [1], "title": "x"}
    assert recorder[0]["model"] == "gpt-4o-mini"
    assert recorder[0]["response_format"] == {"type": "json_object"}
    assert recorder[0]["messages"] == [
        {"role": "system", "content": "Você é um planejador. Responda em JSON."},
        {"role": "user", "content": "liste as cenas"},
    ]


def test_structured_completion_invalid_json_raises(monkeypatch):
    monkeypatch.setattr(
        "app.providers.llm_client._openai_client",
        lambda: _client("não é json {", []),
    )
    with pytest.raises(LLMJSONError, match="não é JSON válido") as exc_info:
        structured_completion("sys", "user")
    assert isinstance(exc_info.value.__cause__, json.JSONDecodeError)


def test_structured_completion_empty_body(monkeypatch):
    monkeypatch.setattr("app.providers.llm_client._openai_client", lambda: _client("   ", []))
    with pytest.raises(LLMJSONError, match="vazia"):
        structured_completion("sys", "user")


def test_structured_completion_rejects_json_array(monkeypatch):
    monkeypatch.setattr("app.providers.llm_client._openai_client", lambda: _client("[1, 2]", []))
    with pytest.raises(LLMJSONError, match="objeto JSON"):
        structured_completion("sys", "user")


def test_structured_completion_requires_api_key(monkeypatch):
    monkeypatch.setattr(
        "app.providers.llm_client.settings",
        SimpleNamespace(openai_api_key=""),
    )
    with pytest.raises(LLMJSONError, match="OPENAI_API_KEY"):
        structured_completion("sys", "user")
