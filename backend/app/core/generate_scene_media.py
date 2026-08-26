"""Gera a mídia de uma cena com o ImageProvider configurado no projeto."""

from __future__ import annotations

from decimal import Decimal
from io import BytesIO
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.daily_budget import assert_paid_job_allowed
from app.core.job_groups import check_job_group_complete
from app.core.project_cast import enrich_visual_prompt, load_project_character, load_project_style
from app.core.provider_limiter import provider_semaphore
from app.core.state_machine import IllegalTransition, ProjectNotFound, advance_stage, parse_stage
from app.models.enums import MediaType, ProjectStage, ProjectStatus, SceneStatus
from app.models.project import Project
from app.models.scene import Scene
from app.providers.image_provider import (
    DEFAULT_IMAGE_QUALITY,
    DEFAULT_IMAGE_SIZE,
    default_image_model,
    get_image_provider,
    parse_image_provider,
)

_SCENE_DONE = frozenset({SceneStatus.READY, SceneStatus.COMPLETED})


def _scene_done(scene: Any) -> bool:
    status = getattr(scene, "status", None)
    if status in _SCENE_DONE:
        return True
    return str(getattr(status, "value", status) or "") in {item.value for item in _SCENE_DONE}


def maybe_finish_media_group(
    session: Session,
    project: Project,
    scene: Scene,
    job_group_id: UUID | str | None = None,
) -> dict[str, Any]:
    """Se todas as cenas terminaram, consulta o job group e avança GENERATING_MEDIA."""
    scenes = list(getattr(project, "scenes", None) or []) or [scene]
    scenes_complete = all(_scene_done(item) for item in scenes)
    group_complete = None
    if job_group_id is not None:
        try:
            group_complete = check_job_group_complete(project.id, job_group_id, db=session)
        except Exception:
            group_complete = None
    advanced = False
    current = getattr(project, "current_stage", None)
    if scenes_complete and current is not None:
        try:
            if parse_stage(current) is ProjectStage.GENERATING_MEDIA:
                advance_stage(project.id, ProjectStage.GENERATING_MEDIA, db=session)
                advanced = True
        except IllegalTransition:
            pass
    return {
        "scenes_complete": scenes_complete,
        "group_complete": group_complete,
        "advanced": advanced,
    }


def generate_scene_media(
    project_id: str | UUID,
    scene_id: str | UUID,
    db: Session | None = None,
    *,
    upload=None,
    job_group_id: UUID | str | None = None,
) -> dict:
    """Monta o prompt (visual_prompt + estilo), gera a imagem e marca a cena como ready."""
    session, owns = _session(db)
    try:
        scene = None
        pid = project_id if isinstance(project_id, UUID) else UUID(str(project_id))
        sid = scene_id if isinstance(scene_id, UUID) else UUID(str(scene_id))
        project = session.get(Project, pid)
        if project is None:
            raise ProjectNotFound(str(pid))
        scene = session.get(Scene, sid)
        if scene is None or scene.project_id != project.id:
            raise ProjectNotFound(f"scene {sid}")

        config = project.automation_config or {}
        provider_name = parse_image_provider(config)
        model = str(config.get("image_model") or default_image_model(provider_name))
        quality = str(config.get("image_quality") or DEFAULT_IMAGE_QUALITY)
        size = str(config.get("image_size") or DEFAULT_IMAGE_SIZE)
        character = load_project_character(session, config)
        style = load_project_style(session, config)
        prompt = enrich_visual_prompt(
            scene.visual_prompt or "",
            character=character,
            style=style,
        )
        if not prompt:
            raise ValueError(f"cena {scene.index} sem visual_prompt")

        scene.status = SceneStatus.GENERATING
        scene.generation_provider = provider_name
        session.flush()

        client = get_image_provider(provider_name)
        generate_kwargs: dict[str, Any] = {"model": model}
        if provider_name == "openai":
            generate_kwargs["quality"] = quality
            generate_kwargs["size"] = size

        reference_bytes = None
        if (
            provider_name == "openai"
            and character is not None
            and (character.base_image_url or "").strip()
        ):
            from app.core.generate_character import fetch_image_bytes

            reference_bytes = fetch_image_bytes(character.base_image_url)
        with provider_semaphore.hold(provider_name):
            if provider_name == "openai" and reference_bytes and hasattr(client, "edit_image"):
                result = client.edit_image(prompt, reference_bytes, **generate_kwargs)
            else:
                result = client.generate_image(prompt, **generate_kwargs)

        from app.storage import versioned_filename

        if upload is None:
            from app.storage import upload_fileobj as upload

        filename = versioned_filename(f"scene_{scene.index:04d}")
        url = upload(
            BytesIO(result.image_bytes),
            str(project.id),
            filename,
            content_type="image/png",
        )
        scene.media_url = url
        scene.media_type = MediaType.IMAGE
        scene.cost_usd = Decimal(str(result.cost_usd))
        scene.status = SceneStatus.READY
        session.flush()
        group = maybe_finish_media_group(session, project, scene, job_group_id=job_group_id)
        if owns:
            session.commit()
        return {
            "project_id": str(project.id),
            "scene_id": str(scene.id),
            "provider": provider_name,
            "model": model,
            "media_url": url,
            "cost_usd": float(result.cost_usd),
            **group,
        }
    except Exception:
        if scene is not None and not owns:
            scene.status = SceneStatus.FAILED
        if owns:
            session.rollback()
        raise
    finally:
        if owns:
            session.close()


def generate_project_media(
    project_id: str | UUID,
    db: Session | None = None,
    *,
    job_group_id: UUID | str | None = None,
) -> dict:
    """Gera todas as cenas do projeto (job único, sem scene_id no payload)."""
    session, owns = _session(db)
    try:
        pid = project_id if isinstance(project_id, UUID) else UUID(str(project_id))
        project = session.get(Project, pid)
        if project is None:
            raise ProjectNotFound(str(pid))
        scenes = list(project.scenes)
        results = [
            generate_scene_media(project.id, scene.id, db=session, job_group_id=job_group_id)
            for scene in scenes
        ]
        if owns:
            session.commit()
        return {"project_id": str(pid), "scenes": results, "count": len(results)}
    except Exception:
        if owns:
            session.rollback()
        raise
    finally:
        if owns:
            session.close()


def enqueue_scene_regenerate(
    project_id: str | UUID,
    scene_id: str | UUID,
    db: Session | None = None,
    *,
    send_task=None,
) -> dict:
    """Marca a cena como generating e dispara generate_scene_media só para ela (media_review)."""
    session, owns = _session(db)
    try:
        pid = project_id if isinstance(project_id, UUID) else UUID(str(project_id))
        sid = scene_id if isinstance(scene_id, UUID) else UUID(str(scene_id))
        project = session.get(Project, pid)
        if project is None:
            raise ProjectNotFound(str(pid))
        if (
            parse_stage(project.current_stage) is not ProjectStage.MEDIA_REVIEW
            or project.status is not ProjectStatus.PAUSED_FOR_REVIEW
        ):
            raise IllegalTransition("cena só pode ser regenerada em media_review")
        scene = session.get(Scene, sid)
        if scene is None or scene.project_id != project.id:
            raise ProjectNotFound(f"scene {sid}")
        assert_paid_job_allowed(session, ProjectStage.GENERATING_MEDIA)
        scene.status = SceneStatus.GENERATING
        session.flush()
        enqueue = send_task
        if enqueue is None:
            from app.celery_app import celery_app

            enqueue = celery_app.send_task
        enqueue(
            "scenecraft.generate_scene_media",
            args=[str(project.id), str(scene.id)],
            queue="media_gen",
        )
        if owns:
            session.commit()
        return {"project_id": str(project.id), "scene_id": str(scene.id)}
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
