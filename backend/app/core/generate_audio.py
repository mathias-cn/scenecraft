"""Gera narração ElevenLabs e grava audio_tracks.source=generated."""

from __future__ import annotations

from io import BytesIO
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.project_audio import ProjectAudioError, set_final_audio
from app.core.provider_limiter import provider_semaphore
from app.core.state_machine import ProjectNotFound
from app.models.audio_track import AudioTrack
from app.models.enums import AudioTrackSource
from app.models.project import Project
from app.providers import elevenlabs


def narration_script(project: Project) -> str:
    segments = sorted(list(getattr(project, "transcript_segments", None) or []), key=lambda item: item.index)
    parts = []
    for segment in segments:
        text = (getattr(segment, "text_translated", None) or getattr(segment, "text_original", None) or "").strip()
        if text:
            parts.append(text)
    return " ".join(parts)


def generate_project_audio(
    project_id: str | UUID,
    *,
    voice_id: str,
    db: Session | None = None,
    upload=None,
) -> dict:
    """Sintetiza o transcript com ElevenLabs e persiste a faixa gerada."""
    session, owns = _session(db)
    try:
        pid = project_id if isinstance(project_id, UUID) else UUID(str(project_id))
        project = session.get(Project, pid)
        if project is None:
            raise ProjectNotFound(str(pid))
        script = narration_script(project)
        if not script:
            raise ProjectAudioError("transcript vazio para gerar áudio")
        voice = (voice_id or "").strip()
        if not voice:
            raise ProjectAudioError("voice_id ausente")

        with provider_semaphore.hold("elevenlabs"):
            audio_bytes = elevenlabs.synthesize(text=script, voice_id=voice)
        if not audio_bytes:
            raise ProjectAudioError("ElevenLabs devolveu áudio vazio")

        if upload is None:
            from app.storage import upload_fileobj as upload

        url = upload(
            BytesIO(audio_bytes),
            str(project.id),
            "narration.mp3",
            content_type="audio/mpeg",
        )
        track = AudioTrack(
            project_id=project.id,
            source=AudioTrackSource.GENERATED,
            provider="elevenlabs",
            voice_id=voice,
            file_url=url,
        )
        session.add(track)
        tracks = getattr(project, "audio_tracks", None)
        if tracks is not None:
            tracks.append(track)
        set_final_audio(session, project, url, AudioTrackSource.GENERATED.value)
        session.flush()
        if owns:
            session.commit()
        return {
            "project_id": str(project.id),
            "audio_url": url,
            "voice_id": voice,
            "source": AudioTrackSource.GENERATED.value,
        }
    except Exception:
        if owns:
            session.rollback()
        raise
    finally:
        if owns:
            session.close()


def _session(db: Session | None) -> tuple[Session, bool]:
    if db is not None:
        return db, False
    from app.db import SessionLocal

    return SessionLocal(), True
