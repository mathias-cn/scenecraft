"""Gera thumbnail 16:9 a partir do resumo do transcript e do ImageProvider do projeto."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.daily_budget import assert_paid_job_allowed
from app.core.project_cast import enrich_visual_prompt, load_project_character, load_project_style
from app.core.provider_limiter import provider_semaphore
from app.core.state_machine import IllegalTransition, ProjectNotFound, advance_stage, parse_stage
from app.core.transcribe_project import language_code
from app.models.enums import ProjectStage, ProjectStatus, ThumbnailSource
from app.models.project import Project
from app.models.thumbnail import Thumbnail
from app.providers.image_provider import (
    DEFAULT_IMAGE_QUALITY,
    default_image_model,
    get_image_provider,
    parse_image_provider,
)
from app.providers.llm_client import summarize_video, thumbnail_prompt
from app.providers.pricing import add_usd, as_usd, unpack_priced_text

THUMBNAIL_SIZE = "1280x720"
OPENAI_THUMBNAIL_SIZE = "1536x1024"


class ThumbnailError(RuntimeError):
    """Falha ao resumir, gerar ou persistir a thumbnail."""


def thumbnail_size_for(provider: str) -> str:
    return OPENAI_THUMBNAIL_SIZE if provider == "openai" else THUMBNAIL_SIZE


def project_transcript_text(project: Project) -> str:
    """Concatena o transcript (traduzido se o projeto não for 'original')."""
    use_translated = bool(language_code(getattr(project, "target_language", "pt-BR")))
    segments = sorted(
        list(getattr(project, "transcript_segments", None) or []),
        key=lambda item: int(getattr(item, "index", 0) or 0),
    )
    parts: list[str] = []
    for segment in segments:
        original = (getattr(segment, "text_original", None) or "").strip()
        translated = (getattr(segment, "text_translated", None) or "").strip()
        text = (translated or original) if use_translated else original
        if text:
            parts.append(text)
    return " ".join(parts)


def generate_thumbnail(
    project_id: str | UUID,
    db: Session | None = None,
    *,
    summarize=None,
    prompt_from_summary=None,
    upload=None,
    image_client=None,
) -> dict:
    """Resume o vídeo, gera a thumbnail e grava thumbnails.source=generated."""
    session, owns = _session(db)
    try:
        pid = project_id if isinstance(project_id, UUID) else UUID(str(project_id))
        project = session.get(Project, pid)
        if project is None:
            raise ProjectNotFound(str(pid))

        transcript = project_transcript_text(project)
        if not transcript:
            raise ThumbnailError("transcript vazio para gerar thumbnail")

        config = project.automation_config or {}
        provider_name = parse_image_provider(config)
        model = str(config.get("image_model") or default_image_model(provider_name))
        quality = str(config.get("image_quality") or DEFAULT_IMAGE_QUALITY)
        size = thumbnail_size_for(provider_name)
        character = load_project_character(session, config)
        style = load_project_style(session, config)
        character_description = (getattr(character, "description_prompt", None) or "").strip() or None
        style_name = (getattr(style, "name", None) or "").strip() or None

        make_summary = summarize or summarize_video
        make_prompt = prompt_from_summary or thumbnail_prompt
        summary, summary_cost = unpack_priced_text(
            make_summary(
                title=project.title,
                transcript=transcript,
                language=getattr(project, "target_language", None) or "pt-BR",
            )
        )
        prompt, prompt_cost = unpack_priced_text(
            make_prompt(
                summary=summary,
                title=project.title,
                character_description=character_description,
                style_name=style_name,
            )
        )
        prompt = enrich_visual_prompt(prompt, character=character, style=style)
        if not prompt:
            raise ThumbnailError("prompt de thumbnail vazio")

        client = image_client or get_image_provider(provider_name)
        generate_kwargs: dict[str, Any] = {"model": model, "size": size}
        if provider_name == "openai":
            generate_kwargs["quality"] = quality

        with provider_semaphore.hold(provider_name):
            result = client.generate_image(prompt, **generate_kwargs)
        if not result.image_bytes:
            raise ThumbnailError("ImageProvider devolveu imagem vazia")
        cost = add_usd(summary_cost, prompt_cost, result.cost_usd)

        from app.storage import upload_generated_image

        url = upload_generated_image(
            result.image_bytes,
            str(project.id),
            "thumbnail",
            upload=upload,
        )
        thumb = Thumbnail(
            project_id=project.id,
            source=ThumbnailSource.GENERATED,
            file_url=url,
            cost_usd=as_usd(cost),
        )
        session.add(thumb)
        thumbs = getattr(project, "thumbnails", None)
        if thumbs is not None:
            thumbs.append(thumb)
        session.flush()
        advanced = _advance_thumbnail(session, project)
        if owns:
            session.commit()
        return {
            "project_id": str(project.id),
            "thumbnail_id": str(thumb.id) if getattr(thumb, "id", None) else None,
            "file_url": url,
            "source": ThumbnailSource.GENERATED.value,
            "provider": provider_name,
            "model": model,
            "size": size,
            "summary": summary,
            "prompt": prompt,
            "cost_usd": float(cost),
            "advanced": advanced,
        }
    except Exception:
        if owns:
            session.rollback()
        raise
    finally:
        if owns:
            session.close()


def _advance_thumbnail(session: Session, project: Project) -> bool:
    try:
        current = parse_stage(project.current_stage)
    except Exception:
        return False
    if current is not ProjectStage.THUMBNAIL_STAGE:
        return False
    status = getattr(project, "status", None)
    if status is ProjectStatus.PAUSED_FOR_REVIEW:
        return False
    try:
        advance_stage(project.id, ProjectStage.THUMBNAIL_STAGE, db=session)
        return True
    except IllegalTransition:
        return False


def enqueue_thumbnail_generate(
    project_id: str | UUID,
    db: Session | None = None,
    *,
    send_task=None,
) -> dict:
    """Dispara generate_thumbnail em thumbnail_stage, sem avançar o estágio."""
    session, owns = _session(db)
    try:
        pid = project_id if isinstance(project_id, UUID) else UUID(str(project_id))
        project = session.get(Project, pid)
        if project is None:
            raise ProjectNotFound(str(pid))
        if (
            parse_stage(project.current_stage) is not ProjectStage.THUMBNAIL_STAGE
            or project.status is not ProjectStatus.PAUSED_FOR_REVIEW
        ):
            raise IllegalTransition("thumbnail só pode ser gerada em thumbnail_stage")
        assert_paid_job_allowed(session, ProjectStage.THUMBNAIL_STAGE)
        enqueue = send_task
        if enqueue is None:
            from app.celery_app import celery_app

            enqueue = celery_app.send_task
        enqueue("scenecraft.generate_thumbnail", args=[str(project.id)], queue="thumbnail")
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


def persist_uploaded_thumbnail(
    project_id: str | UUID,
    fileobj,
    filename: str,
    content_type: str | None,
    db: Session | None = None,
    *,
    upload=None,
) -> dict:
    """Grava uma thumbnail enviada (source=uploaded) sem avançar o estágio."""
    session, owns = _session(db)
    try:
        pid = project_id if isinstance(project_id, UUID) else UUID(str(project_id))
        project = session.get(Project, pid)
        if project is None:
            raise ProjectNotFound(str(pid))
        if (
            parse_stage(project.current_stage) is not ProjectStage.THUMBNAIL_STAGE
            or project.status is not ProjectStatus.PAUSED_FOR_REVIEW
        ):
            raise IllegalTransition("thumbnail só pode ser enviada em thumbnail_stage")

        from app.core.ingest import assert_image_upload_filename, persist_upload, sanitize_image_filename
        from app.storage import versioned_filename

        safe_name = sanitize_image_filename(filename)
        assert_image_upload_filename(safe_name)
        put = upload or persist_upload
        url = put(
            fileobj,
            project_id=project.id,
            filename=versioned_filename(Path(safe_name).stem, Path(safe_name).suffix or ".png"),
            content_type=content_type,
        )
        thumb = Thumbnail(
            project_id=project.id,
            source=ThumbnailSource.UPLOADED,
            file_url=url,
        )
        session.add(thumb)
        thumbs = getattr(project, "thumbnails", None)
        if thumbs is not None:
            thumbs.append(thumb)
        session.flush()
        if owns:
            session.commit()
        return {
            "project_id": str(project.id),
            "thumbnail_id": str(thumb.id) if getattr(thumb, "id", None) else None,
            "file_url": url,
            "source": ThumbnailSource.UPLOADED.value,
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
