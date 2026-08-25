import base64
from types import SimpleNamespace

import pytest

from app.providers.elevenlabs_client import (
    STUB_VOICES,
    ElevenLabsError,
    Voice,
    generate_speech,
    list_voices,
    word_timestamps_from_alignment,
)


class FakeResponse:
    def __init__(self, *, json_body=None, status_code=200):
        self._json = json_body or {}
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"http {self.status_code}")

    def json(self):
        return self._json


class FakeHTTP:
    def __init__(self, response):
        self.response = response
        self.gets = []
        self.posts = []

    def get(self, url, headers=None, timeout=None):
        self.gets.append((url, headers, timeout))
        return self.response

    def post(self, url, headers=None, json=None, timeout=None):
        self.posts.append((url, headers, json, timeout))
        return self.response


def test_word_timestamps_group_characters_into_words():
    stamps = word_timestamps_from_alignment(
        {
            "characters": list("Hi there"),
            "character_start_times_seconds": [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7],
            "character_end_times_seconds": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8],
        }
    )
    assert stamps == [
        {"word": "Hi", "start_ms": 0, "end_ms": 200},
        {"word": "there", "start_ms": 300, "end_ms": 800},
    ]


def test_list_voices_returns_stubs_without_api_key(monkeypatch):
    monkeypatch.setattr(
        "app.providers.elevenlabs_client.settings",
        SimpleNamespace(elevenlabs_api_key=""),
    )
    voices = list_voices()
    assert [voice.id for voice in voices] == [item[0] for item in STUB_VOICES]


def test_list_voices_parses_api_payload(monkeypatch):
    monkeypatch.setattr(
        "app.providers.elevenlabs_client.settings",
        SimpleNamespace(elevenlabs_api_key="sk-test"),
    )
    http = FakeHTTP(
        FakeResponse(
            json_body={"voices": [{"voice_id": "abc", "name": "Clara"}, {"voice_id": ""}]}
        )
    )
    voices = list_voices(http=http)
    assert voices == [Voice(id="abc", name="Clara")]
    assert http.gets[0][0].endswith("/v1/voices")


def test_generate_speech_stub_without_key(monkeypatch):
    monkeypatch.setattr(
        "app.providers.elevenlabs_client.settings",
        SimpleNamespace(elevenlabs_api_key=""),
    )
    audio, stamps = generate_speech("olá mundo", "Rachel")
    assert audio.startswith(b"ID3")
    assert stamps == []


def test_generate_speech_rejects_empty_text(monkeypatch):
    monkeypatch.setattr(
        "app.providers.elevenlabs_client.settings",
        SimpleNamespace(elevenlabs_api_key="sk-test"),
    )
    with pytest.raises(ElevenLabsError, match="vazio"):
        generate_speech("  ", "Rachel")


def test_generate_speech_decodes_audio_and_timestamps(monkeypatch):
    monkeypatch.setattr(
        "app.providers.elevenlabs_client.settings",
        SimpleNamespace(elevenlabs_api_key="sk-test"),
    )
    audio = b"ID3fake"
    http = FakeHTTP(
        FakeResponse(
            json_body={
                "audio_base64": base64.b64encode(audio).decode("ascii"),
                "alignment": {
                    "characters": list("Olá"),
                    "character_start_times_seconds": [0.0, 0.12, 0.2],
                    "character_end_times_seconds": [0.12, 0.2, 0.4],
                },
            }
        )
    )
    body, stamps = generate_speech("Olá", "voice-1", http=http)
    assert body == audio
    assert stamps == [{"word": "Olá", "start_ms": 0, "end_ms": 400}]
    assert "/text-to-speech/voice-1/with-timestamps" in http.posts[0][0]
    assert http.posts[0][2]["text"] == "Olá"
