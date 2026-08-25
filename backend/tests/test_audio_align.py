from types import SimpleNamespace

from app.core.audio_align import align_scene_times, find_word_span, tokenize
from app.providers.transcription_client import Segment


def test_tokenize_lowercases_words():
    assert tokenize("Olá, Mundo!") == ["olá", "mundo"]


def test_find_word_span_locates_subsequence():
    haystack = tokenize("hello there friend how are you today")
    needle = tokenize("how are you")
    span = find_word_span(haystack, needle)
    assert span == (3, 6)


def test_find_word_span_matches_similar_wording():
    haystack = tokenize("hello there my good friend how are you today")
    needle = tokenize("hello there friend")
    span = find_word_span(haystack, needle)
    assert span is not None
    assert span[0] == 0
    assert haystack[span[0] : span[1]][0] == "hello"


def test_align_scene_times_uses_new_transcription_windows():
    original = [
        SimpleNamespace(index=0, text_original="hello there friend", text_translated=None, end_ms=1000),
        SimpleNamespace(index=1, text_original="how are you today", text_translated=None, end_ms=2000),
    ]
    scenes = [
        SimpleNamespace(index=0, source_segment_ids=[0], start_ms=0, end_ms=1000, visual_prompt="wide shot"),
        SimpleNamespace(index=1, source_segment_ids=[1], start_ms=1000, end_ms=2000, visual_prompt="close up"),
    ]
    new_segments = [
        Segment(start_ms=0, end_ms=1500, text="hello there friend"),
        Segment(start_ms=1500, end_ms=3000, text="how are you today"),
    ]
    spans = align_scene_times(scenes, original, new_segments)
    assert spans[0][0] == 0
    assert spans[0][1] <= spans[1][0]
    assert spans[1][1] == 3000
    assert spans[0][1] <= 1500 or spans[1][0] >= 1500


def test_align_falls_back_to_scaled_times_when_text_diverges():
    original = [
        SimpleNamespace(index=0, text_original="alpha beta", text_translated=None, end_ms=1000),
    ]
    scenes = [
        SimpleNamespace(index=0, source_segment_ids=[0], start_ms=0, end_ms=1000, visual_prompt="x"),
    ]
    new_segments = [Segment(start_ms=0, end_ms=4000, text="zzzz yyyy xxxx wwww")]
    spans = align_scene_times(scenes, original, new_segments)
    assert spans[0] == (0, 4000)


def test_align_uses_original_transcript_not_translation():
    original = [
        SimpleNamespace(
            index=0,
            text_original="hello there friend",
            text_translated="olá amigo querido demais",
            end_ms=1000,
        ),
    ]
    scenes = [
        SimpleNamespace(index=0, source_segment_ids=[0], start_ms=0, end_ms=1000, visual_prompt="x"),
    ]
    new_segments = [Segment(start_ms=0, end_ms=2500, text="hello there friend")]
    spans = align_scene_times(scenes, original, new_segments, use_translated=False)
    assert spans[0] == (0, 2500)


def test_align_uses_translated_text_when_requested():
    original = [
        SimpleNamespace(
            index=0,
            text_original="hello there friend",
            text_translated="olá amigo",
            end_ms=1000,
        ),
    ]
    scenes = [
        SimpleNamespace(index=0, source_segment_ids=[0], start_ms=0, end_ms=1000, visual_prompt="x"),
    ]
    new_segments = [Segment(start_ms=100, end_ms=900, text="olá amigo")]
    spans = align_scene_times(scenes, original, new_segments, use_translated=True)
    assert spans[0][0] == 100
    assert spans[0][1] == 900
