"""Vínculos de um estilo com projetos e personagens."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import inspect, select, text
from sqlalchemy.orm import Session

from app.models.project import Project
from app.models.style import Style

STYLE_IN_USE_MESSAGE = "Este estilo está em uso e não pode ser excluído, apenas desativado"


def scene_style_matches(config: dict | None, *, slug: str, style_id: str) -> bool:
    raw = (config or {}).get("scene_style")
    if raw is None or str(raw).strip() == "":
        return False
    return str(raw).strip() in {slug, style_id}


def _projects_use_style(db: Session, style: Style) -> bool:
    style_id = str(style.id)
    slug = style.slug
    configs = list(db.scalars(select(Project.automation_config)).all())
    return any(scene_style_matches(config, slug=slug, style_id=style_id) for config in configs)


def _characters_use_style(db: Session, style_id: UUID) -> bool:
    try:
        bind = db.get_bind()
        if bind is None or not inspect(bind).has_table("characters"):
            return False
        row = db.execute(
            text("SELECT 1 FROM characters WHERE style_id = :id LIMIT 1"),
            {"id": style_id},
        ).first()
    except Exception:
        return False
    return row is not None


def style_is_in_use(db: Session, style: Style) -> bool:
    """True se algum personagem (style_id) ou projeto (automation_config.scene_style) usa o estilo."""
    return _projects_use_style(db, style) or _characters_use_style(db, style.id)
