"""Transcreve o áudio de um projeto e avança o estágio TRANSCRIBING."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.core.project_audio import persist_original_audio
from app.core.source_downloader import load_audio
from app.core.state_machine import ProjectNotFound, advance_stage
from app.models.project import Project
from app.models.transcript_segment import TranscriptSegment
from app.providers import llm_client, transcription_client
from app.providers.pricing import add_cost, add_project_llm_cost, estimate_whisper_cost_usd
from app.providers.transcription_client import Segment, TranscriptionError

_LANG_ALIASES = {
    "portuguese": "pt",
    "brazilian": "pt",
    "english": "en",
    "spanish": "es",
    "castilian": "es",
}


def language_code(value: str | None) -> str:
    """Normaliza `pt-BR` / `en` / `original` para o código ISO-639-1."""
    raw = (value or "").strip().lower().replace("_", "-")
    if not raw or raw in {"auto", "und", "original"}:
        return ""
    primary = raw.split("-", 1)[0]
    return _LANG_ALIASES.get(primary, primary)


def needs_translation(detected: str | None, target: str | None) -> bool:
    dest = language_code(target)
    src = language_code(detected)
    if not dest or not src:
        return False
    return src != dest


def transcribe_project(project_id: str | UUID, db: Session | None = None) -> dict:
    """Baixa o áudio, transcreve, traduz se preciso, grava segmentos e avança TRANSCRIBING."""
    session, owns = _session(db)
    try:
        pid = project_id if isinstance(project_id, UUID) else UUID(str(project_id))
        project = session.get(Project, pid)
        if project is None:
            raise ProjectNotFound(str(pid))

        with tempfile.TemporaryDirectory(prefix="scenecraft-transcribe-") as tmp:
            audio_path = load_audio(project, Path(tmp))
            # Persiste no R2 (audio_tracks.source=original) antes do tmp sumir.
            track = persist_original_audio(session, project, audio_path)
            segments = transcription_client.transcribe(str(audio_path), language="auto")
            record_whisper_cost(track, audio_path, segments)

        if not segments:
            raise TranscriptionError("transcrição vazia")

        detected = _whisper_language(segments)
        language = (detected or project.target_language or "und")[:16]
        translations, translation_cost = _translate_if_needed(segments, detected, project.target_language)
        _replace_segments(session, project, segments, language, translations)
        add_project_llm_cost(project, translation_cost)
        session.flush()
        advance_stage(project.id, "TRANSCRIBING", db=session)
        return {
            "project_id": str(project.id),
            "segment_count": len(segments),
            "language": language,
            "translated": bool(translations),
        }
    except Exception:
        session.rollback()
        raise
    finally:
        if owns:
            session.close()


def whisper_duration_ms(audio_path: str | Path, segments: list[Segment]) -> int:
    try:
        from app.core.plan_scenes import ffprobe_duration_ms

        return ffprobe_duration_ms(audio_path)
    except Exception:
        if segments:
            return max(int(segment.end_ms) for segment in segments)
        return 0


def record_whisper_cost(track: Any, audio_path: str | Path, segments: list[Segment]) -> None:
    if track is None:
        return
    duration_ms = whisper_duration_ms(audio_path, segments)
    add_cost(track, estimate_whisper_cost_usd(duration_ms=duration_ms))


def _whisper_language(segments: list[Segment]) -> str:
    for segment in segments:
        if segment.language:
            return segment.language[:16]
    return ""


def _translate_if_needed(
    segments: list[Segment],
    detected: str,
    target_language: str,
) -> tuple[dict[int, str], Any]:
    if not needs_translation(detected, target_language):
        return {}, 0
    payload = [
        {
            "index": index,
            "start_ms": segment.start_ms,
            "end_ms": segment.end_ms,
            "text": segment.text,
        }
        for index, segment in enumerate(segments)
    ]
    rows = llm_client.translate_segments(payload, target_language=target_language)
    return {int(row["index"]): str(row["text_translated"]) for row in rows}, getattr(rows, "cost_usd", 0)


def _replace_segments(
    db: Session,
    project: Project,
    segments: list[Segment],
    language: str,
    translations: dict[int, str],
) -> None:
    db.execute(delete(TranscriptSegment).where(TranscriptSegment.project_id == project.id))
    for index, segment in enumerate(segments):
        db.add(
            TranscriptSegment(
                project_id=project.id,
                index=index,
                start_ms=segment.start_ms,
                end_ms=segment.end_ms,
                text_original=segment.text,
                text_translated=translations.get(index),
                language=(segment.language or language)[:16],
            )
        )


def _session(db: Session | None) -> tuple[Session, bool]:
    if db is not None:
        return db, False
    from app.db import SessionLocal

    return SessionLocal(), True
