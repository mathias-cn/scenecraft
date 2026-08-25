"""Transcreve o áudio de um projeto e avança o estágio TRANSCRIBING."""

from __future__ import annotations

import tempfile
from pathlib import Path
from uuid import UUID

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.core.source_downloader import load_audio
from app.core.state_machine import ProjectNotFound, advance_stage
from app.models.project import Project
from app.models.transcript_segment import TranscriptSegment
from app.providers import transcription_client
from app.providers.transcription_client import Segment, TranscriptionError


def transcribe_project(project_id: str | UUID, db: Session | None = None) -> dict:
    """Baixa o áudio, chama Whisper, grava `transcript_segments` e avança TRANSCRIBING."""
    session, owns = _session(db)
    try:
        pid = project_id if isinstance(project_id, UUID) else UUID(str(project_id))
        project = session.get(Project, pid)
        if project is None:
            raise ProjectNotFound(str(pid))

        with tempfile.TemporaryDirectory(prefix="scenecraft-transcribe-") as tmp:
            audio_path = load_audio(project, Path(tmp))
            segments = transcription_client.transcribe(str(audio_path), language="auto")

        if not segments:
            raise TranscriptionError("transcrição vazia")

        language = _detected_language(segments, project.target_language)
        _replace_segments(session, project, segments, language)
        session.flush()
        advance_stage(project.id, "TRANSCRIBING", db=session)
        return {
            "project_id": str(project.id),
            "segment_count": len(segments),
            "language": language,
        }
    except Exception:
        session.rollback()
        raise
    finally:
        if owns:
            session.close()


def _detected_language(segments: list[Segment], fallback: str) -> str:
    for segment in segments:
        if segment.language:
            return segment.language[:16]
    return (fallback or "und")[:16]


def _replace_segments(
    db: Session,
    project: Project,
    segments: list[Segment],
    language: str,
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
                language=(segment.language or language)[:16],
            )
        )


def _session(db: Session | None) -> tuple[Session, bool]:
    if db is not None:
        return db, False
    from app.db import SessionLocal

    return SessionLocal(), True
