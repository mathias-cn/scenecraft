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
    sanitize_youtube_tags,
)
from app.providers.pricing import as_usd


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
        raw_cost = payload.get("cost_usd")
        cost = as_usd(raw_cost) if raw_cost is not None else None

        row = Description(
            project_id=project.id,
            text=text,
            tags=tags,
            source=DescriptionSource.GENERATED,
            cost_usd=cost,
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
            "cost_usd": float(cost) if cost is not None else None,
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


def enqueue_description_generate(
    project_id: str | UUID,
    db: Session | None = None,
    *,
    send_task=None,
) -> dict:
    """Dispara generate_description em description_stage, sem avançar o estágio."""
    session, owns = _session(db)
    try:
        project = _paused_description_project(session, project_id)
        enqueue = send_task
        if enqueue is None:
            from app.celery_app import celery_app

            enqueue = celery_app.send_task
        enqueue("scenecraft.generate_description", args=[str(project.id)], queue="description")
        if owns:
            session.commit()
        return {"project_id": str(project.id)}
    except Exception:
        if owns:
            session.rollback()
        raise
    finally:
        if owns:
            session.close()


def confirm_description(
    project_id: str | UUID,
    text: str,
    tags: list[str] | None = None,
    db: Session | None = None,
) -> dict:
    """Salva o texto/tags finais (source=manual se editou) e avança o estágio."""
    session, owns = _session(db)
    try:
        project = _paused_description_project(session, project_id)
        body = (text or "").strip()
        if not body:
            raise DescriptionError("descrição não pode ser vazia")
        cleaned = sanitize_youtube_tags(tags or [])
        latest = _latest_description(project)
        edited = _copy_changed(latest, body, cleaned)
        if edited:
            row = Description(
                project_id=project.id,
                text=body,
                tags=cleaned,
                source=DescriptionSource.MANUAL,
            )
            session.add(row)
            rows = getattr(project, "descriptions", None)
            if rows is not None:
                rows.append(row)
            session.flush()
            source = DescriptionSource.MANUAL
        else:
            row = latest
            source = getattr(latest, "source", DescriptionSource.GENERATED)
        advance_stage(project.id, ProjectStage.DESCRIPTION_STAGE, db=session)
        if owns:
            session.commit()
        source_value = source.value if hasattr(source, "value") else str(source)
        saved_tags = cleaned if edited else sanitize_youtube_tags(list(getattr(row, "tags", None) or []))
        return {
            "project_id": str(project.id),
            "description_id": str(row.id) if row is not None and getattr(row, "id", None) else None,
            "text": body,
            "tags": saved_tags,
            "source": source_value,
            "edited": edited,
            "advanced": True,
        }
    except Exception:
        if owns:
            session.rollback()
        raise
    finally:
        if owns:
            session.close()


def _paused_description_project(session: Session, project_id: str | UUID) -> Project:
    pid = project_id if isinstance(project_id, UUID) else UUID(str(project_id))
    project = session.get(Project, pid)
    if project is None:
        raise ProjectNotFound(str(pid))
    if (
        parse_stage(project.current_stage) is not ProjectStage.DESCRIPTION_STAGE
        or project.status is not ProjectStatus.PAUSED_FOR_REVIEW
    ):
        raise IllegalTransition("descrição só pode ser definida em description_stage")
    return project


def _latest_description(project: Project):
    rows = list(getattr(project, "descriptions", None) or [])
    return rows[-1] if rows else None


def _copy_changed(original, text: str, tags: list[str]) -> bool:
    if original is None:
        return True
    current_text = str(getattr(original, "text", "") or "").strip()
    current_tags = sanitize_youtube_tags(list(getattr(original, "tags", None) or []))
    return current_text != text or current_tags != tags


def _session(db: Session | None) -> tuple[Session, bool]:
    if db is not None:
        return db, False
    from app.db import SessionLocal

    return SessionLocal(), True
