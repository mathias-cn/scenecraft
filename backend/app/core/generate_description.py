"""Gera descrição YouTube + tags SEO a partir do transcript e grava descriptions."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.core.generate_thumbnail import project_transcript_text
from app.core.provider_limiter import provider_semaphore
from app.core.state_machine import IllegalTransition, ProjectNotFound, advance_stage, parse_stage
from app.models.description import Description
from app.models.enums import DescriptionSource, ProjectStage, ProjectStatus
from app.models.project import Project
from app.providers.llm_client import (
    MAX_YOUTUBE_TAGS,
    MIN_YOUTUBE_TAGS,
    generate_description as llm_generate_description,
)


class DescriptionError(RuntimeError):
    """Falha ao gerar ou persistir a descrição."""


def generate_description(
    project_id: str | UUID,
    db: Session | None = None,
    *,
    write_copy=None,
) -> dict:
    """Pede text+tags ao LLM numa resposta JSON e grava descriptions.source=generated."""
    session, owns = _session(db)
    try:
        pid = project_id if isinstance(project_id, UUID) else UUID(str(project_id))
        project = session.get(Project, pid)
        if project is None:
            raise ProjectNotFound(str(pid))

        transcript = project_transcript_text(project)
        if not transcript:
            raise DescriptionError("transcript vazio para gerar descrição")

        writer = write_copy or llm_generate_description
        with provider_semaphore.hold("openai"):
            payload = writer(
                title=project.title,
                transcript=transcript,
                language=getattr(project, "target_language", None) or "pt-BR",
            )
        text = str(payload.get("text") or "").strip()
        tags = [str(item).strip() for item in (payload.get("tags") or []) if str(item).strip()]
        tags = tags[:MAX_YOUTUBE_TAGS]
        if not text:
            raise DescriptionError("LLM devolveu descrição vazia")
        if len(tags) < MIN_YOUTUBE_TAGS:
            raise DescriptionError("LLM devolveu menos de 10 tags")

        row = Description(
            project_id=project.id,
            text=text,
            tags=tags,
            source=DescriptionSource.GENERATED,
        )
        session.add(row)
        rows = getattr(project, "descriptions", None)
        if rows is not None:
            rows.append(row)
        session.flush()
        advanced = _advance_description(session, project)
        if owns:
            session.commit()
        return {
            "project_id": str(project.id),
            "description_id": str(row.id) if getattr(row, "id", None) else None,
            "text": text,
            "tags": tags,
            "source": DescriptionSource.GENERATED.value,
            "advanced": advanced,
        }
    except Exception:
        if owns:
            session.rollback()
        raise
    finally:
        if owns:
            session.close()


def _advance_description(session: Session, project: Project) -> bool:
    try:
        current = parse_stage(project.current_stage)
    except Exception:
        return False
    if current is not ProjectStage.DESCRIPTION_STAGE:
        return False
    status = getattr(project, "status", None)
    if status is ProjectStatus.PAUSED_FOR_REVIEW:
        return False
    try:
        advance_stage(project.id, ProjectStage.DESCRIPTION_STAGE, db=session)
        return True
    except IllegalTransition:
        return False


def _session(db: Session | None) -> tuple[Session, bool]:
    if db is not None:
        return db, False
    from app.db import SessionLocal

    return SessionLocal(), True
