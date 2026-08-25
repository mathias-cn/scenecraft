"""Personagem e estilo de cena gravados em automation_config."""

from __future__ import annotations

from uuid import UUID
from typing import Any

from sqlalchemy.orm import Session

from app.models.character import Character
from app.models.enums import CharacterStatus
from app.models.style import Style


class ProjectCastError(ValueError):
    """character_id ou scene_style_id inválidos."""


def parse_optional_uuid(value: Any) -> UUID | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return UUID(text)
    except ValueError as exc:
        raise ProjectCastError("id inválido") from exc


def apply_cast_to_config(
    db: Session,
    config: dict[str, Any],
    *,
    character_id: UUID | None = None,
    scene_style_id: UUID | None = None,
) -> dict[str, Any]:
    """Se houver personagem aprovado, trava scene_style_id no style_id dele."""
    merged = dict(config)
    cid = character_id or parse_optional_uuid(merged.get("character_id"))
    sid = scene_style_id or parse_optional_uuid(merged.get("scene_style_id"))

    if cid is not None:
        character = db.get(Character, cid)
        if character is None:
            raise ProjectCastError("personagem não encontrado")
        if character.status != CharacterStatus.APPROVED:
            raise ProjectCastError("personagem precisa estar aprovado")
        style = db.get(Style, character.style_id)
        merged["character_id"] = str(character.id)
        merged["scene_style_id"] = str(character.style_id)
        if style is not None:
            merged["scene_style"] = style.slug
        else:
            merged.pop("scene_style", None)
        return merged

    merged.pop("character_id", None)
    if sid is None:
        merged.pop("scene_style_id", None)
        return merged

    style = db.get(Style, sid)
    if style is None:
        raise ProjectCastError("estilo não encontrado")
    merged["scene_style_id"] = str(style.id)
    merged["scene_style"] = style.slug
    return merged


def load_project_character(db: Session, config: dict[str, Any] | None) -> Character | None:
    cid = parse_optional_uuid((config or {}).get("character_id"))
    if cid is None:
        return None
    return db.get(Character, cid)


def load_project_style(db: Session, config: dict[str, Any] | None) -> Style | None:
    data = config or {}
    sid = parse_optional_uuid(data.get("scene_style_id"))
    if sid is not None:
        style = db.get(Style, sid)
        if style is not None:
            return style
    slug = str(data.get("scene_style") or "").strip()
    if not slug:
        return None
    from sqlalchemy import select

    return db.scalars(select(Style).where(Style.slug == slug).limit(1)).first()


def enrich_visual_prompt(prompt: str, *, character: Character | None = None, style: Style | None = None) -> str:
    """Garante referência textual ao personagem e ao estilo no visual_prompt."""
    parts = [(prompt or "").strip()]
    if character is not None:
        description = (character.description_prompt or "").strip()
        if description:
            marker = "Recurring character"
            if marker.lower() not in parts[0].lower() and description.lower() not in parts[0].lower():
                parts.append(f"{marker}: {description}")
    if style is not None:
        name = (style.name or "").strip()
        if name and name.lower() not in parts[0].lower():
            parts.append(f"Visual style: {name}")
    return ". ".join(part.rstrip(".") for part in parts if part)
