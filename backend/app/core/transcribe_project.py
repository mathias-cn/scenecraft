"""Transcreve o áudio de um projeto e avança o estágio TRANSCRIBING."""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.core.project_audio import persist_original_audio
from app.core.source_downloader import load_audio
from app.core.state_machine import ProjectNotFound, advance_stage
from app.core.youtube_captions import (
    TRANSCRIPT_METHOD_CAPTION_API,
    TRANSCRIPT_METHOD_WHISPER,
    TRANSCRIPT_METHOD_WHISPER_FALLBACK,
    fetch_youtube_captions,
)
from app.models.enums import SourceType
from app.models.project import Project
from app.models.transcript_segment import TranscriptSegment
from app.providers import llm_client, transcription_client
from app.providers.pricing import add_cost, add_project_llm_cost, estimate_whisper_cost_usd
from app.providers.transcription_client import Segment, TranscriptionError

logger = logging.getLogger(__name__)

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
    """Obtém o transcript, traduz se preciso, grava segmentos e avança TRANSCRIBING.

    YouTube (`youtube_link`) tenta legendas oficiais primeiro (`caption_api`);
    se falhar, cai no download yt-dlp + Whisper (`whisper_fallback`). Uploads
    vão direto para Whisper (`whisper`).
    """
    session, owns = _session(db)
    try:
        pid = project_id if isinstance(project_id, UUID) else UUID(str(project_id))
        project = session.get(Project, pid)
        if project is None:
            raise ProjectNotFound(str(pid))

        segments, transcript_method, detected = _obtain_transcript(session, project)

        if not segments:
            raise TranscriptionError("transcrição vazia")

        language = (detected or project.target_language or "und")[:16]
        translations, translation_cost = _translate_if_needed(segments, detected, project.target_language)
        _replace_segments(session, project, segments, language, translations)
        add_project_llm_cost(project, translation_cost)
        session.flush()
        advance_stage(project.id, "TRANSCRIBING", db=session)
        logger.info(
            "transcript project=%s method=%s language=%s segments=%s translated=%s",
            project.id,
            transcript_method,
            language,
            len(segments),
            bool(translations),
        )
        return {
            "project_id": str(project.id),
            "segment_count": len(segments),
            "language": language,
            "translated": bool(translations),
            "transcript_method": transcript_method,
        }
    except Exception:
        session.rollback()
        raise
    finally:
        if owns:
            session.close()


def _is_youtube_link(project: Project) -> bool:
    value = getattr(project.source_type, "value", project.source_type)
    return str(value) == SourceType.YOUTUBE_LINK.value


def _obtain_transcript(
    session: Session,
    project: Project,
) -> tuple[list[Segment], str, str]:
    """Devolve (segmentos, método, idioma detectado)."""
    if _is_youtube_link(project):
        captions = fetch_youtube_captions(project.source_ref, project.target_language)
        if captions is not None:
            detected = (captions.language or _whisper_language(captions.segments))[:16]
            return captions.segments, TRANSCRIPT_METHOD_CAPTION_API, detected
        logger.warning(
            "transcript project=%s method=%s (caption_api indisponível)",
            project.id,
            TRANSCRIPT_METHOD_WHISPER_FALLBACK,
        )
        segments = _transcribe_via_whisper(session, project)
        return segments, TRANSCRIPT_METHOD_WHISPER_FALLBACK, _whisper_language(segments)

    segments = _transcribe_via_whisper(session, project)
    return segments, TRANSCRIPT_METHOD_WHISPER, _whisper_language(segments)


def _transcribe_via_whisper(session: Session, project: Project) -> list[Segment]:
    with tempfile.TemporaryDirectory(prefix="scenecraft-transcribe-") as tmp:
        audio_path = load_audio(project, Path(tmp))
        # Persiste no R2 (audio_tracks.source=original) antes do tmp sumir.
        track = persist_original_audio(session, project, audio_path)
        segments = transcription_client.transcribe(str(audio_path), language="auto")
        record_whisper_cost(track, audio_path, segments)
    return segments


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
