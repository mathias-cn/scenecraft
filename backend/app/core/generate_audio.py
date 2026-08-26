"""Gera narração ElevenLabs e grava audio_tracks.source=generated."""

from __future__ import annotations

from io import BytesIO
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.project_audio import ProjectAudioError, audio_generation_mode, set_final_audio
from app.core.provider_limiter import provider_semaphore
from app.core.state_machine import ProjectNotFound
from app.core.transcribe_project import language_code
from app.models.audio_track import AudioTrack
from app.models.enums import AudioTrackSource
from app.models.project import Project
from app.providers.elevenlabs_client import generate_speech
from app.providers.pricing import as_usd, estimate_elevenlabs_cost_usd


def narration_script(project: Project) -> str:
    """Concatena o transcript: traduzido se target_language não for 'original'."""
    use_translated = bool(language_code(getattr(project, "target_language", "pt-BR")))
    segments = sorted(
        list(getattr(project, "transcript_segments", None) or []),
        key=lambda item: item.index,
    )
    parts = []
    for segment in segments:
        original = (getattr(segment, "text_original", None) or "").strip()
        translated = (getattr(segment, "text_translated", None) or "").strip()
        text = (translated or original) if use_translated else original
        if text:
            parts.append(text)
    return " ".join(parts)


def generate_audio(
    project_id: str | UUID,
    voice_id: str,
    db: Session | None = None,
    *,
    upload=None,
    speak=None,
) -> dict:
    """Sintetiza o transcript com ElevenLabs e persiste a faixa gerada."""
    session, owns = _session(db)
    try:
        pid = project_id if isinstance(project_id, UUID) else UUID(str(project_id))
        project = session.get(Project, pid)
        if project is None:
            raise ProjectNotFound(str(pid))
        if audio_generation_mode(project.automation_config) != "elevenlabs":
            raise ProjectAudioError("generate_audio só se aplica quando audio_generation_mode='elevenlabs'")
        script = narration_script(project)
        if not script:
            raise ProjectAudioError("transcript vazio para gerar áudio")
        voice = (voice_id or "").strip()
        if not voice:
            raise ProjectAudioError("voice_id ausente")

        tts = speak or generate_speech
        with provider_semaphore.hold("elevenlabs"):
            audio_bytes, word_timestamps = tts(script, voice)
        if not audio_bytes:
            raise ProjectAudioError("ElevenLabs devolveu áudio vazio")
        cost = estimate_elevenlabs_cost_usd(script)

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
            word_timestamps=list(word_timestamps or []),
            cost_usd=as_usd(cost),
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
            "word_timestamps": list(word_timestamps or []),
            "cost_usd": float(cost),
        }
    except Exception:
        if owns:
            session.rollback()
        raise
    finally:
        if owns:
            session.close()


def generate_project_audio(
    project_id: str | UUID,
    *,
    voice_id: str,
    db: Session | None = None,
    upload=None,
    speak=None,
) -> dict:
    return generate_audio(project_id, voice_id, db=db, upload=upload, speak=speak)


def _session(db: Session | None) -> tuple[Session, bool]:
    if db is not None:
        return db, False
    from app.db import SessionLocal

    return SessionLocal(), True
