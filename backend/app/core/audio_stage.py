"""Trabalho do AUDIO_STAGE: TTS (se ElevenLabs) e re-transcrição alinhada."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.generate_audio import generate_project_audio
from app.core.project_audio import audio_generation_mode
from app.core.retranscribe_align import retranscribe_and_align
from app.core.state_machine import ProjectNotFound
from app.models.project import Project


def run_audio_stage(
    project_id: str | UUID,
    payload: dict[str, Any] | None = None,
    db: Session | None = None,
) -> dict:
    session, owns = _session(db)
    try:
        pid = project_id if isinstance(project_id, UUID) else UUID(str(project_id))
        project = session.get(Project, pid)
        if project is None:
            raise ProjectNotFound(str(pid))
        data = dict(payload or {})
        mode = str(data.get("audio_generation_mode") or audio_generation_mode(project.automation_config))
        if mode == "elevenlabs":
            voice_id = str(data.get("voice_id") or (project.automation_config or {}).get("voice_id") or "")
            generate_project_audio(project.id, voice_id=voice_id, db=session)
        result = retranscribe_and_align(project.id, db=session)
        result["audio_generation_mode"] = mode
        if owns:
            session.commit()
        return result
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
