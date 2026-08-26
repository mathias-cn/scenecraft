"""Re-transcreve o áudio final e realinha start_ms/end_ms das cenas."""

from __future__ import annotations

import tempfile
from pathlib import Path
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.audio_align import align_scene_times
from app.core.project_audio import (
    ProjectAudioError,
    final_narration_track,
    set_final_audio,
    should_skip_audio_stage,
    source_value,
)
from app.core.provider_limiter import provider_semaphore
from app.core.state_machine import IllegalTransition, ProjectNotFound, advance_stage, parse_stage
from app.core.transcribe_project import language_code, record_whisper_cost
from app.models.enums import ProjectStage
from app.models.project import Project
from app.providers import transcription_client
from app.providers.transcription_client import TranscriptionError

_AUDIO_HOPS = frozenset({ProjectStage.AUDIO_STAGE, ProjectStage.AUDIO_REVIEW})


def retranscribe_and_align(project_id: str | UUID, db: Session | None = None) -> dict:
    """Whisper no áudio final + SequenceMatcher; avança para RENDERING (exceto reuse)."""
    session, owns = _session(db)
    try:
        pid = project_id if isinstance(project_id, UUID) else UUID(str(project_id))
        project = session.get(Project, pid)
        if project is None:
            raise ProjectNotFound(str(pid))

        if should_skip_audio_stage(project):
            return {
                "project_id": str(project.id),
                "skipped": True,
                "reason": "reuse_original_audio",
            }

        track = final_narration_track(project)
        if track is None or not (track.file_url or "").strip():
            raise ProjectAudioError("projeto sem áudio final para re-transcrever")

        set_final_audio(session, project, track.file_url, source_value(track.source) or "generated")

        with tempfile.TemporaryDirectory(prefix="scenecraft-retranscribe-") as tmp:
            local = Path(tmp) / "final_audio"
            audio_path = _download_audio(track.file_url, str(local))
            with provider_semaphore.hold("openai"):
                segments = transcription_client.transcribe(str(audio_path), language="auto")
            record_whisper_cost(track, audio_path, segments)

        if not segments:
            raise TranscriptionError("re-transcrição vazia")

        scenes = sorted(
            list(getattr(project, "scenes", None) or []),
            key=lambda item: int(getattr(item, "index", 0) or 0),
        )
        original = list(getattr(project, "transcript_segments", None) or [])
        use_translated = bool(language_code(getattr(project, "target_language", None)))
        spans = align_scene_times(scenes, original, segments, use_translated=use_translated)
        for scene, (start_ms, end_ms) in zip(scenes, spans):
            scene.start_ms = start_ms
            scene.end_ms = end_ms
        session.flush()
        advanced = _advance_to_rendering(session, project)
        if owns:
            session.commit()
        return {
            "project_id": str(project.id),
            "scene_count": len(scenes),
            "segment_count": len(segments),
            "audio_url": track.file_url,
            "skipped": False,
            "advanced": advanced,
        }
    except Exception:
        if owns:
            session.rollback()
        raise
    finally:
        if owns:
            session.close()


def _advance_to_rendering(session: Session, project: Project) -> bool:
    """AUDIO_STAGE → AUDIO_REVIEW → RENDERING, sem pausar para review de áudio."""
    hops = 0
    while hops < 4:
        try:
            current = parse_stage(project.current_stage)
        except Exception:
            return hops > 0
        if current not in _AUDIO_HOPS:
            return hops > 0 or current is ProjectStage.RENDERING
        try:
            advance_stage(project.id, current, db=session)
        except IllegalTransition:
            return hops > 0
        hops += 1
    try:
        return parse_stage(project.current_stage) is ProjectStage.RENDERING
    except Exception:
        return hops > 0


def _download_audio(url: str, local_path: str) -> Path:
    from app.storage import download_file

    destination = Path(local_path)
    suffix = Path(url.split("?", 1)[0]).suffix or ".mp3"
    if destination.suffix.lower() != suffix.lower():
        destination = destination.with_suffix(suffix)
    return download_file(url, str(destination))


def _session(db: Session | None) -> tuple[Session, bool]:
    if db is not None:
        return db, False
    from app.db import SessionLocal

    return SessionLocal(), True
