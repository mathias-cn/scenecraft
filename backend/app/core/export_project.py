"""Pacote de exportação do projeto (vídeo final, thumbnail, título, descrição e tags)."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import unquote, urlparse
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.state_machine import ProjectNotFound
from app.models.project import Project


def export_project(
    project_id: str | UUID,
    db: Session | None = None,
    *,
    resolve_url=None,
) -> dict:
    """Monta o payload de export com URLs HTTP (públicas ou assinadas) do MP4 final."""
    session, owns = _session(db)
    try:
        pid = project_id if isinstance(project_id, UUID) else UUID(str(project_id))
        project = session.get(Project, pid)
        if project is None:
            raise ProjectNotFound(str(pid))

        resolver = resolve_url
        if resolver is None:
            from app.storage import download_url as resolver
        assembly = getattr(project, "video_assembly", None)
        stored_video = (getattr(assembly, "output_url", None) or "").strip() if assembly is not None else ""
        video_url = None
        if stored_video:
            video_url = resolver(
                stored_video,
                filename=_basename(stored_video, "render.mp4"),
                content_type="video/mp4",
            )

        thumbs = list(getattr(project, "thumbnails", None) or [])
        thumb = thumbs[-1] if thumbs else None
        stored_thumb = (getattr(thumb, "file_url", None) or "").strip() if thumb is not None else ""
        thumb_url = None
        if stored_thumb:
            thumb_url = resolver(
                stored_thumb,
                filename=_basename(stored_thumb, "thumbnail.png"),
                content_type=_image_content_type(stored_thumb),
            )

        rows = list(getattr(project, "descriptions", None) or [])
        description = rows[-1] if rows else None
        return {
            "title": str(getattr(project, "title", "") or ""),
            "video_assembly": {"output_url": video_url},
            "thumbnails": {"file_url": thumb_url},
            "descriptions": {
                "text": str(getattr(description, "text", "") or "") if description is not None else "",
                "tags": list(getattr(description, "tags", None) or []) if description is not None else [],
            },
        }
    finally:
        if owns:
            session.close()


def _basename(url: str, fallback: str) -> str:
    parsed = urlparse(url)
    name = Path(unquote(parsed.path)).name
    if name:
        return name
    return fallback


def _image_content_type(url: str) -> str | None:
    suffix = Path(urlparse(url).path).suffix.lower()
    return {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".gif": "image/gif",
    }.get(suffix)


def _session(db: Session | None) -> tuple[Session, bool]:
    if db is not None:
        return db, False
    from app.db import SessionLocal

    return SessionLocal(), True
