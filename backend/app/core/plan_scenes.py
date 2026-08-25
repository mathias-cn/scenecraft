"""Planeja cenas do projeto, incluindo personagem e estilo quando houver."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.core.project_cast import enrich_visual_prompt, load_project_character, load_project_style
from app.core.state_machine import ProjectNotFound
from app.models.enums import MediaType, SceneStatus
from app.models.project import Project
from app.models.scene import Scene
from app.providers.llm_client import plan_scenes


def plan_project_scenes(project_id: str | UUID, db: Session | None = None) -> dict:
    """Lê transcript + cast do projeto, gera visual_prompts e persiste as cenas."""
    session, owns = _session(db)
    try:
        pid = project_id if isinstance(project_id, UUID) else UUID(str(project_id))
        project = session.get(Project, pid)
        if project is None:
            raise ProjectNotFound(str(pid))
        segments = list(getattr(project, "transcript_segments", None) or [])
        if not segments:
            raise ValueError("projeto sem transcript para planejar cenas")

        config = project.automation_config or {}
        character = load_project_character(session, config)
        style = load_project_style(session, config)
        planned = plan_scenes(
            [
                {
                    "index": segment.index,
                    "start_ms": segment.start_ms,
                    "end_ms": segment.end_ms,
                    "text_original": segment.text_original,
                    "text": segment.text_translated or segment.text_original,
                }
                for segment in sorted(segments, key=lambda item: item.index)
            ],
            language=project.target_language or "pt-BR",
            character_description=(character.description_prompt if character is not None else None),
            style_name=(style.name if style is not None else None),
        )
        session.execute(delete(Scene).where(Scene.project_id == project.id))
        for row in planned:
            prompt = enrich_visual_prompt(
                str(row["visual_prompt"]),
                character=character,
                style=style,
            )
            session.add(
                Scene(
                    project_id=project.id,
                    index=int(row["index"]),
                    start_ms=int(row["start_ms"]),
                    end_ms=int(row["end_ms"]),
                    source_segment_ids=list(row.get("source_segment_ids") or []),
                    visual_prompt=prompt,
                    media_type=MediaType.IMAGE,
                    status=SceneStatus.PENDING,
                )
            )
        session.flush()
        if owns:
            session.commit()
        return {"project_id": str(project.id), "scene_count": len(planned)}
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
