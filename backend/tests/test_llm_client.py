import json
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.providers.llm_client import (
    LLMError,
    LLMJSONError,
    LLMProvider,
    OpenAILLMProvider,
    PLAN_SCENES_SYSTEM,
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
    def __init__(self, content, recorder, usage=None):
        self._content = content
        self._recorder = recorder
        self._usage = usage

    def create(self, **kwargs):
        self._recorder.append(kwargs)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=self._content))],
            usage=self._usage,
        )


def _client(content, recorder, usage=None):
    return SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions(content, recorder, usage=usage)))


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
    assert getattr(result, "cost_usd") > 0
    assert recorder[0]["response_format"] == {"type": "json_object"}
    assert recorder[0]["messages"] == [
        {"role": "system", "content": "Você é um planejador. Responda em JSON."},
        {"role": "user", "content": "liste as cenas"},
    ]


def test_structured_completion_uses_usage_tokens_for_cost():
    recorder: list[dict] = []
    usage = SimpleNamespace(prompt_tokens=1_000_000, completion_tokens=0)
    set_llm_provider(OpenAILLMProvider(client=_client('{"ok": true}', recorder, usage=usage)))
    result = structured_completion("sys", "user", model="gpt-4o-mini")
    assert result.cost_usd == Decimal("0.150000")


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


def test_plan_scenes_returns_grouping_without_timestamps(monkeypatch):
    captured: list[tuple[str, str]] = []

    def fake_completion(system_prompt: str, user_content: str) -> dict:
        captured.append((system_prompt, user_content))
        return {
            "scenes": [
                {
                    "start_ms": 999,
                    "end_ms": 999,
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
        scene_pacing="short",
        min_duration_ms=8000,
        max_duration_ms=15000,
    )
    assert scenes[0]["visual_prompt"].startswith("Wide shot")
    assert scenes[0]["source_segment_ids"] == [0, 1]
    assert "start_ms" not in scenes[0]
    assert "end_ms" not in scenes[0]
    assert "heroína de casaco vermelho" in scenes[0]["visual_prompt"]
    assert "Anime" in scenes[0]["visual_prompt"]
    assert "character" in captured[0][1]
    assert "olá" in captured[0][1]
    assert "[0] 00:00.000–00:01.000" in captured[0][1]
    assert "Never return start_ms" in captured[0][1]
    assert '"min_duration_ms": 8000' in captured[0][1]
    assert "NUNCA gere start_ms" in PLAN_SCENES_SYSTEM
    assert captured[0][0] == PLAN_SCENES_SYSTEM


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
    tags = [f"tag {i}" for i in range(12)]
    monkeypatch.setattr(
        "app.providers.llm_client.structured_completion",
        lambda _s, _u: {"text": "Um vídeo sobre o mar. Inscreva-se.", "tags": tags, "title": "O Mar"},
    )
    result = generate_description(title="Mar", transcript="o mar é azul", language="pt-BR")
    assert result["text"] == "Um vídeo sobre o mar. Inscreva-se."
    assert result["tags"] == tags
    assert result["title"] == "O Mar"
    assert result["cost_usd"] > 0


def test_generate_description_strips_hashtags_and_requires_ten_tags(monkeypatch):
    from app.providers.llm_client import generate_description

    raw = ["#mar", "oceano", "  oceano  ", "natação"] + [f"kw{i}" for i in range(8)]
    monkeypatch.setattr(
        "app.providers.llm_client.structured_completion",
        lambda _s, _u: {"text": "Parágrafo.", "tags": raw},
    )
    result = generate_description(title="Mar", transcript="azul")
    assert "mar" in result["tags"]
    assert "#" not in "".join(result["tags"])
    assert result["tags"].count("oceano") == 1
    assert 10 <= len(result["tags"]) <= 15

    monkeypatch.setattr(
        "app.providers.llm_client.structured_completion",
        lambda _s, _u: {"text": "Parágrafo.", "tags": ["só uma"]},
    )
    with pytest.raises(LLMJSONError, match="10 a 15"):
        generate_description(title="Mar", transcript="azul")


def test_generate_description_rejects_empty_transcript():
    from app.providers.llm_client import generate_description

    with pytest.raises(LLMError, match="vazio"):
        generate_description(title="x", transcript="  ")


def test_normalize_youtube_tags_caps_at_fifteen_and_rejects_missing_list():
    from app.providers.llm_client import MAX_YOUTUBE_TAGS, normalize_youtube_tags, sanitize_youtube_tags

    raw = [f"kw{i}" for i in range(20)]
    assert len(normalize_youtube_tags(raw)) == MAX_YOUTUBE_TAGS
    with pytest.raises(LLMJSONError, match="lista"):
        normalize_youtube_tags("mar, oceano")
    assert sanitize_youtube_tags(["#uma"]) == ["uma"]


def test_structured_completion_uses_override_model():
    recorder: list[dict] = []
    set_llm_provider(OpenAILLMProvider(client=_client('{"ok": true}', recorder)))
    structured_completion("sys", "user", model="gpt-5-nano")
    assert recorder[0]["model"] == "gpt-5-nano"


def test_generate_titles_returns_three_suggestions(monkeypatch):
    from app.providers.llm_client import generate_titles

    captured: list[tuple[str, str, str | None]] = []

    def fake_completion(system_prompt: str, user_content: str, *, model: str | None = None) -> dict:
        captured.append((system_prompt, user_content, model))
        return {
            "titles": [
                "Como eu automatizei meu canal em 30 dias",
                "O método simples para automatizar o canal",
                "Automatizei o YouTube — o que realmente funcionou",
            ]
        }

    monkeypatch.setattr("app.providers.llm_client.structured_completion", fake_completion)
    monkeypatch.setattr("app.providers.llm_client.title_model", lambda: "gpt-5-nano")
    titles = generate_titles("Como eu automatizei meu canal")
    assert len(titles) == 3
    assert "automatizei" in titles[0].lower()
    assert getattr(titles, "cost_usd") is not None
    assert "draft_title" in captured[0][1]
    assert captured[0][2] == "gpt-5-nano"


def test_generate_titles_rejects_empty():
    from app.providers.llm_client import generate_titles

    with pytest.raises(LLMError, match="vazio"):
        generate_titles("   ")


def test_generate_titles_requires_three_items(monkeypatch):
    from app.providers.llm_client import generate_titles

    monkeypatch.setattr(
        "app.providers.llm_client.structured_completion",
        lambda *_a, **_k: {"titles": ["só um"]},
    )
    with pytest.raises(LLMJSONError, match="3 títulos"):
        generate_titles("rascunho")


def test_summarize_video_returns_summary(monkeypatch):
    from app.providers.llm_client import summarize_video

    captured: list[tuple[str, str]] = []

    def fake_completion(system_prompt: str, user_content: str, *, model: str | None = None) -> dict:
        captured.append((system_prompt, user_content))
        return {"summary": "Uma caminhada pela floresta ao amanhecer."}

    monkeypatch.setattr("app.providers.llm_client.structured_completion", fake_completion)
    summary = summarize_video(title="Forest", transcript="we walked into the woods", language="pt-BR")
    assert "floresta" in summary.text.lower()
    assert summary.cost_usd > 0
    assert "transcript" in captured[0][1]
    assert "SUMMARY" in captured[0][0] or "resume" in captured[0][0].lower()


def test_summarize_video_rejects_empty():
    from app.providers.llm_client import summarize_video

    with pytest.raises(LLMError, match="vazio"):
        summarize_video(title="x", transcript="  ")


def test_thumbnail_prompt_uses_summary(monkeypatch):
    from app.providers.llm_client import thumbnail_prompt

    captured: list[str] = []

    def fake_completion(system_prompt: str, user_content: str, *, model: str | None = None) -> dict:
        captured.append(user_content)
        return {"prompt": "cinematic close-up of a hiker in mist, 16:9"}

    monkeypatch.setattr("app.providers.llm_client.structured_completion", fake_completion)
    prompt = thumbnail_prompt(
        summary="A walk through a misty forest.",
        title="Forest walk",
        character_description="red-coated heroine",
        style_name="cinematic",
    )
    assert "hiker" in prompt.text
    assert prompt.cost_usd > 0
    assert "misty forest" in captured[0]
    assert "red-coated heroine" in captured[0]


def test_generate_script_returns_narration(monkeypatch):
    from app.providers.llm_client import generate_script

    captured: list[tuple[str, str]] = []

    def fake_completion(system_prompt: str, user_content: str, *, model: str | None = None) -> dict:
        captured.append((system_prompt, user_content))
        return {"script": "A fotossíntese transforma luz em energia. As plantas crescem com isso."}

    monkeypatch.setattr("app.providers.llm_client.structured_completion", fake_completion)
    script = generate_script("fotossíntese", target_duration_minutes=2)
    assert "plantas" in script.text.lower()
    assert script.cost_usd is not None
    assert "target_word_count" in captured[0][1]
    assert "300" in captured[0][1]


def test_generate_script_rejects_empty():
    from app.providers.llm_client import generate_script

    with pytest.raises(LLMError, match="vazio"):
        generate_script("   ")


def test_generate_script_requires_script_field(monkeypatch):
    from app.providers.llm_client import generate_script

    monkeypatch.setattr(
        "app.providers.llm_client.structured_completion",
        lambda *_a, **_k: {"titles": ["não é roteiro"]},
    )
    with pytest.raises(LLMJSONError, match="script"):
        generate_script("tema")
