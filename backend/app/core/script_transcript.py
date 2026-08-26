"""Divide um roteiro em frases e estima timestamps placeholder (~150 wpm)."""

from __future__ import annotations

import re

from app.providers.transcription_client import Segment

WORDS_PER_MINUTE = 150
MIN_SENTENCE_MS = 400
TRANSCRIPT_METHOD_TEXT_SCRIPT = "text_script"

_PARAGRAPH = re.compile(r"\n+")
_SENTENCE = re.compile(r"(?<=[.!?…])\s+")


def split_script_sentences(text: str) -> list[str]:
    raw = (text or "").strip()
    if not raw:
        return []
    sentences: list[str] = []
    for paragraph in _PARAGRAPH.split(raw):
        para = paragraph.strip()
        if not para:
            continue
        parts = _SENTENCE.split(para)
        sentences.extend(part.strip() for part in parts if part.strip())
    return sentences


def estimate_speech_ms(text: str, *, wpm: int = WORDS_PER_MINUTE) -> int:
    words = len((text or "").split())
    if words <= 0:
        return MIN_SENTENCE_MS
    ms = int(round(words / wpm * 60_000))
    return max(ms, MIN_SENTENCE_MS)


def script_segments(text: str) -> list[Segment]:
    """Frases do roteiro com start_ms/end_ms sequenciais (placeholders até o áudio final)."""
    sentences = split_script_sentences(text)
    if not sentences:
        return []
    cursor = 0
    out: list[Segment] = []
    for sentence in sentences:
        duration = estimate_speech_ms(sentence)
        out.append(Segment(start_ms=cursor, end_ms=cursor + duration, text=sentence, language=""))
        cursor += duration
    return out
