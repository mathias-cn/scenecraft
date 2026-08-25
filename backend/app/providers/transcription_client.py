"""Transcrição de áudio via OpenAI Whisper (`whisper-1`)."""

from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from app.core.config import settings

WHISPER_MODEL = "whisper-1"
WHISPER_MAX_BYTES = 25 * 1024 * 1024
# mp3 64 kbps: margem abaixo de 25 MB para o envelope do upload
_MP3_BITRATE_KBPS = 64
_MP3_BYTES_PER_MS = (_MP3_BITRATE_KBPS * 1000) / 8 / 1000
MAX_CHUNK_MS = int(WHISPER_MAX_BYTES * 0.9 / _MP3_BYTES_PER_MS)
MIN_SILENCE_LEN_MS = 400


class TranscriptionError(Exception):
    """Falha ao transcrever áudio na API da OpenAI."""


@dataclass(frozen=True)
class Segment:
    start_ms: int
    end_ms: int
    text: str


class TranscriptionProvider(Protocol):
    def transcribe(self, audio_path: str, language: str = "auto") -> list[Segment]:
        """Transcreve um arquivo de áudio em segmentos com timestamps em ms."""


def seconds_to_ms(value: float) -> int:
    return int(round(float(value) * 1000))


def language_param(language: str | None) -> str | None:
    raw = (language or "auto").strip().lower()
    if not raw or raw == "auto":
        return None
    return raw.split("-", 1)[0]


def cut_points_from_nonsilent(duration_ms: int, nonsilent: list[list[int] | tuple[int, int]]) -> list[int]:
    """Pontos de corte só em silêncio: início/fim do arquivo e bordas das regiões com fala."""
    points = {0, int(duration_ms)}
    for region in nonsilent:
        start, end = int(region[0]), int(region[1])
        if 0 < start < duration_ms:
            points.add(start)
        if 0 < end < duration_ms:
            points.add(end)
    return sorted(points)


def pack_ranges(duration_ms: int, cut_points: list[int], max_ms: int) -> list[tuple[int, int]]:
    """Empacota o áudio em intervalos ≤ max_ms, preferindo cortes em `cut_points`."""
    if duration_ms <= 0:
        return []
    if duration_ms <= max_ms:
        return [(0, duration_ms)]
    cuts = sorted({0, duration_ms, *cut_points})
    cuts = [point for point in cuts if 0 <= point <= duration_ms]
    ranges: list[tuple[int, int]] = []
    start = 0
    idx = 1
    while start < duration_ms:
        farthest = start
        while idx < len(cuts) and cuts[idx] - start <= max_ms:
            farthest = cuts[idx]
            idx += 1
        if farthest == start:
            farthest = min(start + max_ms, duration_ms)
            while idx < len(cuts) and cuts[idx] <= farthest:
                idx += 1
        ranges.append((start, farthest))
        start = farthest
    return ranges


def segments_from_verbose(payload: Any, offset_ms: int = 0) -> list[Segment]:
    raw_segments = _attr_or_key(payload, "segments") or []
    out: list[Segment] = []
    for item in raw_segments:
        text = str(_attr_or_key(item, "text") or "").strip()
        if not text:
            continue
        start = _attr_or_key(item, "start") or 0
        end = _attr_or_key(item, "end") or start
        out.append(
            Segment(
                start_ms=seconds_to_ms(start) + offset_ms,
                end_ms=seconds_to_ms(end) + offset_ms,
                text=text,
            )
        )
    if out:
        return out
    text = str(_attr_or_key(payload, "text") or "").strip()
    if not text:
        return []
    return [Segment(start_ms=offset_ms, end_ms=offset_ms, text=text)]


def _attr_or_key(obj: Any, name: str) -> Any:
    if isinstance(obj, dict):
        return obj.get(name)
    return getattr(obj, name, None)


def _api_key() -> str:
    key = (settings.openai_api_key or "").strip()
    if not key or key.startswith("your_"):
        raise TranscriptionError("OPENAI_API_KEY não configurada")
    return key


def _openai_client():
    key = _api_key()
    from openai import OpenAI

    return OpenAI(api_key=key)


def _split_oversized_audio(audio_path: str):
    from pydub import AudioSegment
    from pydub.silence import detect_nonsilent

    audio = AudioSegment.from_file(audio_path)
    duration_ms = len(audio)
    if duration_ms <= MAX_CHUNK_MS:
        return [audio]
    dbfs = audio.dBFS
    thresh = -40 if dbfs == float("-inf") else min(dbfs - 16, -20)
    nonsilent = detect_nonsilent(
        audio,
        min_silence_len=MIN_SILENCE_LEN_MS,
        silence_thresh=int(thresh),
    )
    cuts = cut_points_from_nonsilent(duration_ms, nonsilent or [])
    ranges = pack_ranges(duration_ms, cuts, MAX_CHUNK_MS)
    return [audio[start:end] for start, end in ranges] or [audio]


def _export_mp3(chunk) -> io.BytesIO:
    buf = io.BytesIO()
    chunk.export(buf, format="mp3", bitrate=f"{_MP3_BITRATE_KBPS}k")
    buf.seek(0)
    buf.name = "chunk.mp3"
    return buf


class OpenAITranscriptionProvider:
    def __init__(self, client: Any | None = None) -> None:
        self._client = client

    def transcribe(self, audio_path: str, language: str = "auto") -> list[Segment]:
        path = Path(audio_path)
        if not path.is_file():
            raise TranscriptionError(f"arquivo de áudio não encontrado: {audio_path}")
        if path.stat().st_size <= WHISPER_MAX_BYTES:
            with path.open("rb") as handle:
                return self._transcribe_file(handle, language, offset_ms=0)
        return self._transcribe_chunked(str(path), language)

    def _client_or_default(self):
        return self._client if self._client is not None else _openai_client()

    def _transcribe_file(self, handle: Any, language: str, offset_ms: int) -> list[Segment]:
        kwargs: dict[str, Any] = {
            "model": WHISPER_MODEL,
            "file": handle,
            "response_format": "verbose_json",
            "timestamp_granularities": ["segment"],
        }
        lang = language_param(language)
        if lang:
            kwargs["language"] = lang
        result = self._client_or_default().audio.transcriptions.create(**kwargs)
        return segments_from_verbose(result, offset_ms=offset_ms)

    def _transcribe_chunked(self, audio_path: str, language: str) -> list[Segment]:
        segments: list[Segment] = []
        offset_ms = 0
        for chunk in _split_oversized_audio(audio_path):
            duration_ms = len(chunk)
            handle = _export_mp3(chunk)
            segments.extend(self._transcribe_file(handle, language, offset_ms=offset_ms))
            offset_ms += duration_ms
        return segments


def transcribe(audio_path: str, language: str = "auto") -> list[Segment]:
    return OpenAITranscriptionProvider().transcribe(audio_path, language)
