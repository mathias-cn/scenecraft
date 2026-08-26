from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.deps import DbDep, require_owner
from app.core.style_links import STYLE_IN_USE_MESSAGE, style_is_in_use
from app.models.style import Style
from app.schemas.style import StyleCreate, StylePatch, StyleRead

router = APIRouter(prefix="/api/styles", tags=["styles"], dependencies=[require_owner])


@router.get("")
def list_styles(
    db: DbDep,
    active: Annotated[bool | None, Query()] = None,
) -> list[StyleRead]:
    stmt = select(Style).order_by(Style.name.asc())
    if active is not None:
        stmt = stmt.where(Style.active.is_(active))
    rows = list(db.scalars(stmt).all())
    return [StyleRead.model_validate(row) for row in rows]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_style(payload: StyleCreate, db: DbDep) -> StyleRead:
    style = Style(name=payload.name, slug=payload.slug, active=True)
    db.add(style)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="já existe um estilo com esse slug",
        ) from exc
    db.refresh(style)
    return StyleRead.model_validate(style)


@router.patch("/{style_id}")
def patch_style(style_id: UUID, payload: StylePatch, db: DbDep) -> StyleRead:
    style = db.get(Style, style_id)
    if style is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Estilo não encontrado")
    style.active = payload.active
    db.commit()
    db.refresh(style)
    return StyleRead.model_validate(style)


@router.delete("/{style_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_style(style_id: UUID, db: DbDep) -> None:
    style = db.get(Style, style_id)
    if style is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Estilo não encontrado")
    if style_is_in_use(db, style):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=STYLE_IN_USE_MESSAGE)
    db.delete(style)
    db.commit()
