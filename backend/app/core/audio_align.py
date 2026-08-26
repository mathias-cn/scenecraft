"""Alinha timestamps de cenas com uma nova transcrição, por similaridade de palavras."""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any, Sequence

from app.providers.transcription_client import Segment

_WORD = re.compile(r"\w+", re.UNICODE)
_MIN_RATIO = 0.25


def tokenize(text: str) -> list[str]:
    return _WORD.findall((text or "").lower())


def segment_script(segment: Any, *, use_translated: bool = False) -> str:
    original = str(getattr(segment, "text_original", None) or getattr(segment, "text", None) or "").strip()
    translated = str(getattr(segment, "text_translated", None) or "").strip()
    if use_translated:
        return translated or original
    return original


def scene_script(scene: Any, segments_by_index: dict[int, Any], *, use_translated: bool = False) -> str:
    """Texto da cena via source_segment_ids (transcript original) ou visual_prompt."""
    parts: list[str] = []
    for raw in list(getattr(scene, "source_segment_ids", None) or []):
        try:
            index = int(raw)
        except (TypeError, ValueError):
            continue
        segment = segments_by_index.get(index)
        if segment is None:
            continue
        text = segment_script(segment, use_translated=use_translated)
        if text:
            parts.append(text)
    if parts:
        return " ".join(parts)
    return str(getattr(scene, "visual_prompt", None) or "").strip()


def words_with_times(segments: Sequence[Segment]) -> list[tuple[str, int, int]]:
    """Cada palavra da nova transcrição com start_ms/end_ms interpolados no segmento."""
    out: list[tuple[str, int, int]] = []
    for segment in segments:
        tokens = tokenize(segment.text)
        if not tokens:
            continue
        start = int(segment.start_ms)
        end = int(segment.end_ms)
        duration = max(end - start, 1)
        step = duration / len(tokens)
        for index, word in enumerate(tokens):
            word_start = start + int(index * step)
            word_end = start + int((index + 1) * step) if index + 1 < len(tokens) else end
            out.append((word, word_start, max(word_end, word_start + 1)))
    return out


def find_word_span(haystack: Sequence[str], needle: Sequence[str]) -> tuple[int, int] | None:
    """Índices [start, end) em haystack que melhor cobrem needle (SequenceMatcher)."""
    if not haystack or not needle:
        return None
    matcher = SequenceMatcher(None, list(haystack), list(needle), autojunk=False)
    if matcher.ratio() < _MIN_RATIO:
        blocks = [block for block in matcher.get_matching_blocks() if block.size > 0]
        if not blocks:
            return None
        covered = sum(block.size for block in blocks)
        if covered / max(len(needle), 1) < _MIN_RATIO:
            return None
    blocks = [block for block in matcher.get_matching_blocks() if block.size > 0]
    if not blocks:
        return None
    start = min(block.a for block in blocks)
    end = max(block.a + block.size for block in blocks)
    if end <= start:
        return None
    return start, end


def scale_span(start_ms: int, end_ms: int, old_duration: int, new_duration: int) -> tuple[int, int]:
    if old_duration <= 0 or new_duration <= 0:
        return 0, max(new_duration, 1)
    start = int(round(start_ms * new_duration / old_duration))
    end = int(round(end_ms * new_duration / old_duration))
    return start, max(end, start + 1)


def align_scene_times(
    scenes: Sequence[Any],
    original_segments: Sequence[Any],
    new_segments: Sequence[Segment],
    *,
    use_translated: bool = False,
) -> list[tuple[int, int]]:
    """Devolve (start_ms, end_ms) alinhados para cada cena, na mesma ordem."""
    timed = words_with_times(new_segments)
    haystack = [word for word, _start, _end in timed]
    new_duration = max((int(item.end_ms) for item in new_segments), default=0)
    old_duration = 0
    if original_segments:
        old_duration = max((int(getattr(item, "end_ms", 0) or 0) for item in original_segments), default=0)
    if not old_duration and scenes:
        old_duration = max((int(getattr(item, "end_ms", 0) or 0) for item in scenes), default=0)

    by_index: dict[int, Any] = {}
    for segment in original_segments:
        try:
            by_index[int(segment.index)] = segment
        except (TypeError, ValueError, AttributeError):
            continue

    ordered = sorted(scenes, key=lambda item: int(getattr(item, "index", 0) or 0))
    spans_by_id: dict[int, tuple[int, int]] = {}
    cursor = 0
    for scene in ordered:
        needle = tokenize(scene_script(scene, by_index, use_translated=use_translated))
        matched = find_word_span(haystack[cursor:], needle) if needle else None
        if matched is not None and timed:
            start_i, end_i = matched
            start_i += cursor
            end_i += cursor
            start_ms = timed[start_i][1]
            end_ms = timed[min(end_i, len(timed)) - 1][2]
            cursor = end_i
        else:
            start_ms, end_ms = scale_span(
                int(getattr(scene, "start_ms", 0) or 0),
                int(getattr(scene, "end_ms", 0) or 0),
                old_duration,
                new_duration or old_duration or 1,
            )
        start_ms = max(start_ms, 0)
        end_ms = max(end_ms, start_ms + 1)
        spans_by_id[id(scene)] = (start_ms, end_ms)

    prev_end = 0
    normalized_by_id: dict[int, tuple[int, int]] = {}
    for scene in ordered:
        start_ms, end_ms = spans_by_id[id(scene)]
        start_ms = max(start_ms, prev_end)
        end_ms = max(end_ms, start_ms + 1)
        if new_duration:
            end_ms = min(end_ms, new_duration)
            start_ms = min(start_ms, max(end_ms - 1, 0))
        normalized_by_id[id(scene)] = (start_ms, end_ms)
        prev_end = end_ms
    return [normalized_by_id[id(scene)] for scene in scenes]


def align_segment_times(
    original_segments: Sequence[Any],
    new_segments: Sequence[Segment],
    *,
    use_translated: bool = False,
) -> list[tuple[int, int]]:
    """Alinha cada segmento original ao whisper novo, reusando `align_scene_times`."""
    from types import SimpleNamespace

    ordered = sorted(
        original_segments,
        key=lambda item: int(getattr(item, "index", 0) or 0),
    )
    proxies = []
    for segment in ordered:
        idx = int(getattr(segment, "index", 0) or 0)
        proxies.append(
            SimpleNamespace(
                index=idx,
                start_ms=int(getattr(segment, "start_ms", 0) or 0),
                end_ms=int(getattr(segment, "end_ms", 0) or 0),
                source_segment_ids=[idx],
                visual_prompt="",
            )
        )
    spans = align_scene_times(
        proxies,
        original_segments,
        new_segments,
        use_translated=use_translated,
    )
    by_index = {
        int(getattr(segment, "index", 0) or 0): span for segment, span in zip(ordered, spans)
    }
    return [by_index[int(getattr(item, "index", 0) or 0)] for item in original_segments]
