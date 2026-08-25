"""Re-transcreve o áudio final e realinha start_ms/end_ms das cenas."""

from __future__ import annotations

import tempfile
from pathlib import Path
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.audio_align import align_scene_times
from app.core.project_audio import ProjectAudioError, final_narration_track, set_final_audio, source_value
from app.core.state_machine import ProjectNotFound
from app.models.project import Project
from app.providers import transcription_client
from app.providers.transcription_client import TranscriptionError


def retranscribe_and_align(project_id: str | UUID, db: Session | None = None) -> dict:
    """Whisper no áudio final + SequenceMatcher para atualizar tempos das cenas."""
    session, owns = _session(db)
    try:
        pid = project_id if isinstance(project_id, UUID) else UUID(str(project_id))
        project = session.get(Project, pid)
        if project is None:
            raise ProjectNotFound(str(pid))

        track = final_narration_track(project)
        if track is None or not (track.file_url or "").strip():
            raise ProjectAudioError("projeto sem áudio final para re-transcrever")

        set_final_audio(session, project, track.file_url, source_value(track.source) or "generated")

        with tempfile.TemporaryDirectory(prefix="scenecraft-retranscribe-") as tmp:
            local = Path(tmp) / "final_audio"
            audio_path = _download_audio(track.file_url, str(local))
            segments = transcription_client.transcribe(str(audio_path), language="auto")

        if not segments:
            raise TranscriptionError("re-transcrição vazia")

        scenes = list(getattr(project, "scenes", None) or [])
        original = list(getattr(project, "transcript_segments", None) or [])
        spans = align_scene_times(scenes, original, segments)
        for scene, (start_ms, end_ms) in zip(scenes, spans):
            scene.start_ms = start_ms
            scene.end_ms = end_ms
        session.flush()
        if owns:
            session.commit()
        return {
            "project_id": str(project.id),
            "scene_count": len(scenes),
            "segment_count": len(segments),
            "audio_url": track.file_url,
        }
    except Exception:
        if owns:
            session.rollback()
        raise
    finally:
        if owns:
            session.close()


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
