from types import SimpleNamespace

import pytest

from app.core.youtube_captions import (
    caption_language_priority,
    extract_youtube_video_id,
    fetch_youtube_captions,
    snippets_to_segments,
)
from app.providers.transcription_client import Segment


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=12s", "dQw4w9WgXcQ"),
        ("https://youtu.be/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://youtu.be/dQw4w9WgXcQ?t=30", "dQw4w9WgXcQ"),
        ("https://www.youtube.com/embed/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://www.youtube.com/shorts/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://www.youtube.com/live/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("www.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://youtu.be/abc", None),
        ("", None),
        ("https://vimeo.com/123456789", None),
    ],
)
def test_extract_youtube_video_id(url, expected):
    assert extract_youtube_video_id(url) == expected


def test_caption_language_priority_includes_project_lang_then_en():
    assert caption_language_priority("pt-BR") == ["pt-BR", "pt", "en"]
    assert caption_language_priority("en") == ["en"]
    assert caption_language_priority("original") == ["en"]
    assert caption_language_priority(None) == ["en"]
    assert caption_language_priority("spanish") == ["spanish", "es", "en"]


def test_snippets_to_segments_converts_start_duration_to_ms():
    fetched = SimpleNamespace(
        language_code="en",
        snippets=[
            SimpleNamespace(text="hello there", start=0.0, duration=1.5),
            SimpleNamespace(text="  world  ", start=1.5, duration=2.25),
            SimpleNamespace(text="   ", start=4.0, duration=1.0),
        ],
    )
    segments = snippets_to_segments(fetched)
    assert segments == [
        Segment(start_ms=0, end_ms=1500, text="hello there", language="en"),
        Segment(start_ms=1500, end_ms=3750, text="world", language="en"),
    ]


def test_snippets_to_segments_accepts_dict_items():
    segments = snippets_to_segments(
        [{"text": "olá", "start": 0.2, "duration": 0.8}],
        language="pt",
    )
    assert segments == [Segment(start_ms=200, end_ms=1000, text="olá", language="pt")]


def test_fetch_youtube_captions_uses_api_and_returns_segments(monkeypatch):
    calls: list[tuple] = []

    class FakeApi:
        def fetch(self, video_id, languages=None):
            calls.append((video_id, list(languages)))
            return SimpleNamespace(
                language_code="pt",
                snippets=[SimpleNamespace(text="olá mundo", start=0.0, duration=1.2)],
            )

    monkeypatch.setattr("app.core.youtube_captions.YouTubeTranscriptApi", FakeApi)
    result = fetch_youtube_captions("https://youtu.be/dQw4w9WgXcQ", "pt-BR")
    assert result is not None
    assert result.video_id == "dQw4w9WgXcQ"
    assert result.language == "pt"
    assert result.segments[0].text == "olá mundo"
    assert result.segments[0].start_ms == 0
    assert result.segments[0].end_ms == 1200
    assert calls == [("dQw4w9WgXcQ", ["pt-BR", "pt", "en"])]


def test_fetch_youtube_captions_returns_none_when_no_transcript(monkeypatch):
    class FakeApi:
        def fetch(self, video_id, languages=None):
            raise Exception("no transcript found")

    monkeypatch.setattr("app.core.youtube_captions.YouTubeTranscriptApi", FakeApi)
    assert fetch_youtube_captions("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "en") is None


def test_fetch_youtube_captions_returns_none_without_video_id():
    assert fetch_youtube_captions("https://youtu.be/abc", "en") is None
