"""Gera a mídia de uma cena com o ImageProvider configurado no projeto."""

from __future__ import annotations

from decimal import Decimal
from io import BytesIO
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.project_cast import enrich_visual_prompt, load_project_character, load_project_style
from app.core.provider_limiter import provider_semaphore
from app.core.state_machine import ProjectNotFound
from app.models.enums import MediaType, SceneStatus
from app.models.project import Project
from app.models.scene import Scene
from app.providers.image_provider import (
    DEFAULT_IMAGE_QUALITY,
    DEFAULT_IMAGE_SIZE,
    default_image_model,
    get_image_provider,
    parse_image_provider,
)


def generate_scene_media(
    project_id: str | UUID,
    scene_id: str | UUID,
    db: Session | None = None,
    *,
    upload=None,
) -> dict:
    """Lê `automation_config.image_provider`, gera a imagem e grava a cena."""
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
                result = client.edit_image(prompt, reference_bytes, model=model, quality=quality, size=size)
            else:
                result = client.generate_image(prompt, model=model, quality=quality, size=size)

        if upload is None:
            from app.storage import upload_fileobj as upload

        filename = f"scenes/{scene.index:04d}.png"
        url = upload(
            BytesIO(result.image_bytes),
            str(project.id),
            filename,
            content_type="image/png",
        )
        scene.media_url = url
        scene.media_type = MediaType.IMAGE
        scene.cost_usd = Decimal(str(result.cost_usd))
        scene.status = SceneStatus.COMPLETED
        scene.style = model
        session.flush()
        if owns:
            session.commit()
        return {
            "project_id": str(project.id),
            "scene_id": str(scene.id),
            "provider": provider_name,
            "model": model,
            "media_url": url,
            "cost_usd": float(result.cost_usd),
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


def generate_project_media(project_id: str | UUID, db: Session | None = None) -> dict:
    """Gera todas as cenas do projeto (job único, sem scene_id no payload)."""
    session, owns = _session(db)
    try:
        pid = project_id if isinstance(project_id, UUID) else UUID(str(project_id))
        project = session.get(Project, pid)
        if project is None:
            raise ProjectNotFound(str(pid))
        scenes = list(project.scenes)
        results = [generate_scene_media(project.id, scene.id, db=session) for scene in scenes]
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


def _session(db: Session | None) -> tuple[Session, bool]:
    if db is not None:
        return db, False
    from app.db import SessionLocal

    return SessionLocal(), True
