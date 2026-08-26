"""Soma os custos estimados de um projeto."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.state_machine import ProjectNotFound
from app.models.project import Project
from app.providers.pricing import add_usd, as_usd


def _items_cost(items: Any) -> Any:
    return add_usd(*(getattr(item, "cost_usd", None) for item in (items or [])))


def project_cost_breakdown(project: Any) -> dict[str, Any]:
    scenes_usd = _items_cost(getattr(project, "scenes", None))
    audio_usd = _items_cost(getattr(project, "audio_tracks", None))
    descriptions_usd = _items_cost(getattr(project, "descriptions", None))
    thumbnails_usd = _items_cost(getattr(project, "thumbnails", None))
    llm_usd = as_usd(getattr(project, "llm_cost_usd", None))
    return {
        "project_id": project.id,
        "total_usd": add_usd(scenes_usd, audio_usd, descriptions_usd, thumbnails_usd, llm_usd),
        "scenes_usd": scenes_usd,
        "audio_tracks_usd": audio_usd,
        "descriptions_usd": descriptions_usd,
        "thumbnails_usd": thumbnails_usd,
        "llm_usd": llm_usd,
    }


def load_project_cost(project_id: UUID | str, db: Session) -> dict[str, Any]:
    pid = project_id if isinstance(project_id, UUID) else UUID(str(project_id))
    project = db.get(Project, pid)
    if project is None:
        raise ProjectNotFound(str(pid))
    return project_cost_breakdown(project)
