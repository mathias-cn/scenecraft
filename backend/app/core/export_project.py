"""Pacote de exportação do projeto (vídeo final, thumbnail, título, descrição e tags)."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.core.state_machine import ProjectNotFound
from app.models.project import Project


def export_project(
    project_id: str | UUID,
    db: Session | None = None,
) -> dict:
    """Monta o payload de export com object_keys; a API assina na serialização."""
    session, owns = _session(db)
    try:
        pid = project_id if isinstance(project_id, UUID) else UUID(str(project_id))
        project = session.get(Project, pid)
        if project is None:
            raise ProjectNotFound(str(pid))

        assembly = getattr(project, "video_assembly", None)
        stored_video = (getattr(assembly, "output_url", None) or "").strip() if assembly is not None else ""

        thumbs = list(getattr(project, "thumbnails", None) or [])
        thumb = thumbs[-1] if thumbs else None
        stored_thumb = (getattr(thumb, "file_url", None) or "").strip() if thumb is not None else ""

        rows = list(getattr(project, "descriptions", None) or [])
        description = rows[-1] if rows else None
        return {
            "title": str(getattr(project, "title", "") or ""),
            "video_assembly": {"output_url": stored_video or None},
            "thumbnails": {"file_url": stored_thumb or None},
            "descriptions": {
                "text": str(getattr(description, "text", "") or "") if description is not None else "",
                "tags": list(getattr(description, "tags", None) or []) if description is not None else [],
            },
        }
    finally:
        if owns:
            session.close()


def _session(db: Session | None) -> tuple[Session, bool]:
    if db is not None:
        return db, False
    from app.db import SessionLocal

    return SessionLocal(), True
