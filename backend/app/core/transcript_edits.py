"""Aplica edições manuais em `transcript_segments` durante TRANSCRIPT_REVIEW."""

from __future__ import annotations

from uuid import UUID

from app.models.transcript_segment import TranscriptSegment
from app.schemas.project import TranscriptSegmentPatch


class TranscriptEditError(ValueError):
    """Patch inválido (segmento inexistente ou texto vazio)."""


def apply_transcript_edits(
    rows: list[TranscriptSegment],
    patches: list[TranscriptSegmentPatch],
) -> list[UUID]:
    """Atualiza textos no lugar. Devolve os ids alterados."""
    by_id = {row.id: row for row in rows}
    changed: list[UUID] = []
    for patch in patches:
        row = by_id.get(patch.id)
        if row is None:
            raise TranscriptEditError(f"segmento não encontrado: {patch.id}")
        fields = patch.model_fields_set
        if "text_original" in fields and patch.text_original is not None:
            text = patch.text_original.strip()
            if not text:
                raise TranscriptEditError("text_original não pode ser vazio")
            row.text_original = text
        if "text_translated" in fields:
            raw = patch.text_translated
            row.text_translated = raw.strip() if isinstance(raw, str) and raw.strip() else None
        changed.append(patch.id)
    return changed
