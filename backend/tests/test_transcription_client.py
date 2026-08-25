from types import SimpleNamespace

import pytest

from app.providers.transcription_client import (
    OpenAITranscriptionProvider,
    Segment,
    TranscriptionError,
    cut_points_from_nonsilent,
    language_param,
    pack_ranges,
    seconds_to_ms,
    segments_from_verbose,
    transcribe,
)


def test_seconds_to_ms_rounds():
    assert seconds_to_ms(0) == 0
    assert seconds_to_ms(1.5) == 1500
    assert seconds_to_ms(2.3456) == 2346


def test_language_param_auto_omits():
    assert language_param("auto") is None
    assert language_param("") is None
    assert language_param("pt-BR") == "pt"
    assert language_param("en") == "en"


def test_segments_from_verbose_converts_seconds_and_offset():
    payload = SimpleNamespace(
        segments=[
            SimpleNamespace(start=1.25, end=3.5, text="  olá "),
            SimpleNamespace(start=3.5, end=4.0, text=""),
        ]
    )
    segs = segments_from_verbose(payload, offset_ms=10_000)
    assert segs == [Segment(start_ms=11250, end_ms=13500, text="olá")]


def test_segments_from_verbose_dict_and_fallback_text():
    segs = segments_from_verbose({"segments": [], "text": "inteiro"})
    assert segs == [Segment(start_ms=0, end_ms=0, text="inteiro")]


def test_cut_points_only_at_silence_boundaries():
    assert cut_points_from_nonsilent(10_000, [[1000, 4000], [6000, 9000]]) == [
        0,
        1000,
        4000,
        6000,
        9000,
        10_000,
    ]


def test_pack_ranges_prefers_silence_then_hard_splits():
    assert pack_ranges(100, [0, 100], max_ms=1000) == [(0, 100)]
    packed = pack_ranges(10_000, [0, 3000, 10_000], max_ms=4000)
    assert packed == [(0, 3000), (3000, 7000), (7000, 10_000)]


class FakeTranscriptions:
    def __init__(self, payload, recorder):
        self._payload = payload
        self._recorder = recorder

    def create(self, **kwargs):
        self._recorder.append(kwargs)
        handle = kwargs["file"]
        if hasattr(handle, "seek"):
            handle.seek(0)
        return self._payload


class FakeOpenAI:
    def __init__(self, payload, recorder):
        self.audio = SimpleNamespace(transcriptions=FakeTranscriptions(payload, recorder))


def _payload(*parts: tuple[float, float, str]):
    return SimpleNamespace(
        segments=[SimpleNamespace(start=start, end=end, text=text) for start, end, text in parts]
    )


def test_transcribe_small_file_calls_whisper(tmp_path, monkeypatch):
    audio = tmp_path / "clip.wav"
    audio.write_bytes(b"RIFF" + b"\x00" * 64)
    recorder: list[dict] = []
    client = FakeOpenAI(_payload((0.0, 1.2, "oi")), recorder)
    monkeypatch.setattr(
        "app.providers.transcription_client.WHISPER_MAX_BYTES",
        10_000_000,
    )
    segs = OpenAITranscriptionProvider(client=client).transcribe(str(audio), language="auto")
    assert segs == [Segment(start_ms=0, end_ms=1200, text="oi")]
    assert recorder[0]["model"] == "whisper-1"
    assert recorder[0]["response_format"] == "verbose_json"
    assert recorder[0]["timestamp_granularities"] == ["segment"]
    assert "language" not in recorder[0]


def test_transcribe_passes_language(tmp_path):
    audio = tmp_path / "clip.mp3"
    audio.write_bytes(b"id3")
    recorder: list[dict] = []
    client = FakeOpenAI(_payload((0.5, 0.8, "hey")), recorder)
    OpenAITranscriptionProvider(client=client).transcribe(str(audio), language="en")
    assert recorder[0]["language"] == "en"


def test_transcribe_missing_file():
    with pytest.raises(TranscriptionError, match="não encontrado"):
        OpenAITranscriptionProvider(client=FakeOpenAI(_payload(), [])).transcribe("missing.wav")


def test_module_transcribe_uses_provider(tmp_path, monkeypatch):
    audio = tmp_path / "a.wav"
    audio.write_bytes(b"x" * 8)
    recorder: list[dict] = []
    monkeypatch.setattr(
        "app.providers.transcription_client._openai_client",
        lambda: FakeOpenAI(_payload((2.0, 2.5, "fim")), recorder),
    )
    segs = transcribe(str(audio), language="pt-BR")
    assert segs[0].text == "fim"
    assert segs[0].start_ms == 2000
    assert recorder[0]["language"] == "pt"


def test_chunked_transcription_adds_duration_offsets(tmp_path, monkeypatch):
    audio = tmp_path / "long.wav"
    audio.write_bytes(b"big")
    monkeypatch.setattr("app.providers.transcription_client.WHISPER_MAX_BYTES", 1)

    class FakeChunk:
        def __init__(self, duration_ms: int, label: str):
            self._duration_ms = duration_ms
            self.label = label

        def __len__(self):
            return self._duration_ms

        def export(self, buf, format, bitrate=None):
            buf.write(self.label.encode())

    monkeypatch.setattr(
        "app.providers.transcription_client._split_oversized_audio",
        lambda _path: [FakeChunk(1500, "a"), FakeChunk(2000, "b")],
    )
    recorder: list[dict] = []
    payloads = {
        "a": _payload((0.1, 0.4, "um")),
        "b": _payload((0.0, 0.2, "dois")),
    }

    class Sequential:
        def create(self, **kwargs):
            recorder.append(kwargs)
            handle = kwargs["file"]
            handle.seek(0)
            label = handle.read().decode()
            handle.seek(0)
            return payloads[label]

    client = SimpleNamespace(audio=SimpleNamespace(transcriptions=Sequential()))
    segs = OpenAITranscriptionProvider(client=client).transcribe(str(audio))
    assert segs == [
        Segment(start_ms=100, end_ms=400, text="um"),
        Segment(start_ms=1500, end_ms=1700, text="dois"),
    ]
    assert [call["model"] for call in recorder] == ["whisper-1", "whisper-1"]
