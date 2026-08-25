import json
from types import SimpleNamespace

import pytest

from app.providers.llm_client import (
    LLMError,
    LLMJSONError,
    LLMProvider,
    OpenAILLMProvider,
    generate_description,
    plan_scenes,
    set_llm_provider,
    structured_completion,
    translate_segments,
)
from app.providers import llm_client as llm_module
from app.providers import transcription_client as transcription_module
from app.providers.openai_auth import openai_client as shared_openai_client


class FakeCompletions:
    def __init__(self, content, recorder):
        self._content = content
        self._recorder = recorder

    def create(self, **kwargs):
        self._recorder.append(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=self._content))])


def _client(content, recorder):
    return SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions(content, recorder)))


@pytest.fixture(autouse=True)
def restore_llm_provider():
    set_llm_provider(OpenAILLMProvider())
    yield
    set_llm_provider(OpenAILLMProvider())


def test_structured_completion_parses_json_object():
    recorder: list[dict] = []
    set_llm_provider(OpenAILLMProvider(client=_client('{"scenes": [1], "title": "x"}', recorder)))
    result = structured_completion("Você é um planejador. Responda em JSON.", "liste as cenas")
    assert result == {"scenes": [1], "title": "x"}
    assert recorder[0]["model"] == "gpt-4o-mini"
    assert recorder[0]["response_format"] == {"type": "json_object"}
    assert recorder[0]["messages"] == [
        {"role": "system", "content": "Você é um planejador. Responda em JSON."},
        {"role": "user", "content": "liste as cenas"},
    ]


def test_structured_completion_invalid_json_raises():
    set_llm_provider(OpenAILLMProvider(client=_client("não é json {", [])))
    with pytest.raises(LLMJSONError, match="não é JSON válido") as exc_info:
        structured_completion("sys", "user")
    assert isinstance(exc_info.value.__cause__, json.JSONDecodeError)


def test_structured_completion_empty_body():
    set_llm_provider(OpenAILLMProvider(client=_client("   ", [])))
    with pytest.raises(LLMJSONError, match="vazia"):
        structured_completion("sys", "user")


def test_structured_completion_rejects_json_array():
    set_llm_provider(OpenAILLMProvider(client=_client("[1, 2]", [])))
    with pytest.raises(LLMJSONError, match="objeto JSON"):
        structured_completion("sys", "user")


def test_structured_completion_requires_api_key(monkeypatch):
    monkeypatch.setattr(
        "app.providers.openai_auth.settings",
        SimpleNamespace(openai_api_key=""),
    )
    with pytest.raises(LLMError, match="OPENAI_API_KEY"):
        OpenAILLMProvider().structured_completion("sys", "user")


def test_openai_provider_is_llm_provider():
    assert issubclass(OpenAILLMProvider, LLMProvider)
    assert isinstance(OpenAILLMProvider(), LLMProvider)


def test_transcription_and_llm_share_openai_api_key():
    assert transcription_module.openai_client is shared_openai_client
    assert llm_module.openai_client is shared_openai_client


def test_plan_scenes_returns_visual_prompts(monkeypatch):
    captured: list[tuple[str, str]] = []

    def fake_completion(system_prompt: str, user_content: str) -> dict:
        captured.append((system_prompt, user_content))
        return {
            "scenes": [
                {
                    "index": 0,
                    "start_ms": 0,
                    "end_ms": 2000,
                    "source_segment_ids": [0, 1],
                    "visual_prompt": "Wide shot of a rainy street at night, neon reflections",
                }
            ]
        }

    monkeypatch.setattr("app.providers.llm_client.structured_completion", fake_completion)
    scenes = plan_scenes(
        [
            {"index": 0, "start_ms": 0, "end_ms": 1000, "text_original": "olá"},
            {"index": 1, "start_ms": 1000, "end_ms": 2000, "text": "mundo"},
        ],
        language="pt-BR",
        character_description="heroína de casaco vermelho",
        style_name="Anime",
    )
    assert scenes[0]["visual_prompt"].startswith("Wide shot")
    assert scenes[0]["source_segment_ids"] == [0, 1]
    assert "heroína de casaco vermelho" in scenes[0]["visual_prompt"]
    assert "Anime" in scenes[0]["visual_prompt"]
    assert "character" in captured[0][1]
    assert "olá" in captured[0][1]


def test_translate_segments_keeps_original_timestamps(monkeypatch):
    def fake_completion(_system: str, _user: str) -> dict:
        return {
            "segments": [
                {
                    "index": 0,
                    "start_ms": 999,
                    "end_ms": 999,
                    "text_translated": "hello there",
                }
            ]
        }

    monkeypatch.setattr("app.providers.llm_client.structured_completion", fake_completion)
    rows = translate_segments(
        [{"index": 0, "start_ms": 120, "end_ms": 880, "text": "olá"}],
        target_language="en",
    )
    assert rows == [
        {
            "index": 0,
            "start_ms": 120,
            "end_ms": 880,
            "text_original": "olá",
            "text_translated": "hello there",
        }
    ]


def test_translate_segments_batches_long_transcripts(monkeypatch):
    import json

    calls: list[list[int]] = []

    def fake_completion(_system: str, user_content: str) -> dict:
        payload = json.loads(user_content)
        indexes = [int(item["index"]) for item in payload["segments"]]
        calls.append(indexes)
        return {
            "segments": [
                {
                    "index": item["index"],
                    "start_ms": item["start_ms"],
                    "end_ms": item["end_ms"],
                    "text_translated": f"{item['text']}-pt",
                }
                for item in payload["segments"]
            ]
        }

    monkeypatch.setattr("app.providers.llm_client.structured_completion", fake_completion)
    items = [
        {"index": index, "start_ms": index * 10, "end_ms": index * 10 + 9, "text": f"t{index}"}
        for index in range(45)
    ]
    rows = translate_segments(items, target_language="pt", batch_size=20)
    assert calls == [list(range(0, 20)), list(range(20, 40)), list(range(40, 45))]
    assert len(rows) == 45
    assert rows[0]["start_ms"] == 0
    assert rows[21]["end_ms"] == 219
    assert rows[44]["text_translated"] == "t44-pt"


def test_generate_description_from_transcript(monkeypatch):
    monkeypatch.setattr(
        "app.providers.llm_client.structured_completion",
        lambda _s, _u: {"text": "Um vídeo sobre o mar.", "title": "O Mar"},
    )
    result = generate_description(title="Mar", transcript="o mar é azul", language="pt-BR")
    assert result == {"text": "Um vídeo sobre o mar.", "title": "O Mar"}
