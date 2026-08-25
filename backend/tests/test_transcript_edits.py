from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.transcript_edits import TranscriptEditError, apply_transcript_edits
from app.schemas.project import TranscriptSegmentPatch


def test_updates_original_and_clears_translated():
    sid = uuid4()
    row = SimpleNamespace(id=sid, text_original="hi", text_translated="oi")
    apply_transcript_edits(
        [row],
        [
            TranscriptSegmentPatch(id=sid, text_original=" hello ", text_translated="  "),
        ],
    )
    assert row.text_original == "hello"
    assert row.text_translated is None


def test_null_translated_clears_field():
    sid = uuid4()
    row = SimpleNamespace(id=sid, text_original="hi", text_translated="oi")
    apply_transcript_edits([row], [TranscriptSegmentPatch(id=sid, text_translated=None)])
    assert row.text_original == "hi"
    assert row.text_translated is None


def test_unknown_segment_raises():
    row = SimpleNamespace(id=uuid4(), text_original="hi", text_translated=None)
    with pytest.raises(TranscriptEditError, match="não encontrado"):
        apply_transcript_edits([row], [TranscriptSegmentPatch(id=uuid4(), text_original="x")])


def test_empty_original_raises():
    sid = uuid4()
    row = SimpleNamespace(id=sid, text_original="hi", text_translated=None)
    with pytest.raises(TranscriptEditError, match="vazio"):
        apply_transcript_edits([row], [TranscriptSegmentPatch(id=sid, text_original="   ")])


def test_omitted_original_is_untouched():
    sid = uuid4()
    row = SimpleNamespace(id=sid, text_original="hi", text_translated="oi")
    apply_transcript_edits([row], [TranscriptSegmentPatch(id=sid, text_translated="hey")])
    assert row.text_original == "hi"
    assert row.text_translated == "hey"
