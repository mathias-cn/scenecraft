from json import JSONDecodeError
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile
from fastapi import status as http_status
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import noload, selectinload

from app.api.deps import DbDep, require_owner
from app.core.daily_budget import DailyCostLimitReached, assert_paid_job_allowed
from app.core.generate_character import enqueue_character_task, reference_filename
from app.models.character import Character
from app.models.enums import CharacterStatus
from app.models.style import Style
from app.schemas.character import CharacterCreate, CharacterRead
from app.storage import StorageError, upload_fileobj

router = APIRouter(prefix="/api/characters", tags=["characters"], dependencies=[require_owner])

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
TASK_BASE = "scenecraft.generate_character_base_image"
TASK_SET = "scenecraft.generate_character_set"


class CreateCharacterInput:
    def __init__(self, payload: CharacterCreate, file: UploadFile | None) -> None:
        self.payload = payload
        self.file = file


async def parse_character_input(request: Request) -> CreateCharacterInput:
    content_type = (request.headers.get("content-type") or "").lower()
    if "multipart/form-data" in content_type:
        form = await request.form()
        raw_file = form.get("file")
        file = raw_file if isinstance(raw_file, UploadFile) else None
        try:
            payload = CharacterCreate(
                description_prompt=str(form.get("description_prompt") or ""),
                style_id=str(form.get("style_id") or ""),
                reference_image_url=str(form.get("reference_image_url") or "") or None,
            )
        except ValidationError as exc:
            raise RequestValidationError(exc.errors()) from exc
        return CreateCharacterInput(payload, file)

    try:
        body = await request.json()
    except JSONDecodeError as exc:
        raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail="JSON inválido") from exc
    try:
        payload = CharacterCreate.model_validate(body)
    except ValidationError as exc:
        raise RequestValidationError(exc.errors()) from exc
    return CreateCharacterInput(payload, None)


CreateInputDep = Annotated[CreateCharacterInput, Depends(parse_character_input)]


def _guard_paid_jobs(db) -> None:
    try:
        assert_paid_job_allowed(db)
    except DailyCostLimitReached as exc:
        raise HTTPException(status_code=http_status.HTTP_409_CONFLICT, detail=str(exc)) from exc


def _assert_image_file(file: UploadFile | None) -> None:
    if file is None or not file.filename:
        return
    suffix = Path(file.filename).suffix.lower()
    if suffix not in IMAGE_SUFFIXES:
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"imagem de referência inválida ({suffix or 'sem extensão'})",
        )


def _require_style(db, style_id: UUID, *, must_be_active: bool) -> Style:
    style = db.get(Style, style_id)
    if style is None:
        raise HTTPException(status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY, detail="estilo não encontrado")
    if must_be_active and not style.active:
        raise HTTPException(status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY, detail="estilo inativo")
    return style


def _to_read(row: Character, *, include_assets: bool) -> CharacterRead:
    data = CharacterRead.model_validate(row)
    if include_assets:
        return data
    return data.model_copy(update={"assets": []})


def _detail_query(db, character_id: UUID) -> Character | None:
    return db.scalars(
        select(Character)
        .options(selectinload(Character.style), selectinload(Character.assets))
        .where(Character.id == character_id)
    ).first()


def _store_reference(character: Character, file: UploadFile) -> str:
    return upload_fileobj(
        file.file,
        f"characters/{character.id}",
        reference_filename(file.filename),
        content_type=file.content_type,
    )


@router.get("")
def list_characters(
    db: DbDep,
    status: Annotated[CharacterStatus | None, Query()] = None,
) -> list[CharacterRead]:
    stmt = (
        select(Character)
        .options(selectinload(Character.style), noload(Character.assets))
        .order_by(Character.created_at.desc())
    )
    if status is not None:
        stmt = stmt.where(Character.status == status)
    rows = list(db.scalars(stmt).all())
    return [_to_read(row, include_assets=False) for row in rows]


@router.post("", status_code=http_status.HTTP_201_CREATED)
def create_character(parsed: CreateInputDep, db: DbDep) -> CharacterRead:
    payload = parsed.payload
    file = parsed.file
    has_file = file is not None and bool(file.filename)
    _assert_image_file(file if has_file else None)
    _require_style(db, payload.style_id, must_be_active=True)
    _guard_paid_jobs(db)

    character = Character(
        description_prompt=payload.description_prompt,
        style_id=payload.style_id,
        reference_image_url=payload.reference_image_url,
        status=CharacterStatus.PENDING_APPROVAL,
    )
    db.add(character)
    db.flush()
    if has_file:
        try:
            character.reference_image_url = _store_reference(character, file)
        except StorageError as exc:
            db.rollback()
            raise HTTPException(
                status_code=http_status.HTTP_502_BAD_GATEWAY,
                detail=str(exc),
            ) from exc
    db.commit()
    row = _detail_query(db, character.id)
    enqueue_character_task(db, TASK_BASE, str(character.id))
    return _to_read(row or character, include_assets=True)


@router.get("/{character_id}")
def get_character(character_id: UUID, db: DbDep) -> CharacterRead:
    row = _detail_query(db, character_id)
    if row is None:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Personagem não encontrado")
    return _to_read(row, include_assets=True)


@router.post("/{character_id}/approve")
def approve_character(character_id: UUID, db: DbDep) -> CharacterRead:
    row = _detail_query(db, character_id)
    if row is None:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Personagem não encontrado")
    if row.status != CharacterStatus.PENDING_APPROVAL:
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail="só é possível aprovar um personagem aguardando revisão",
        )
    _guard_paid_jobs(db)
    if not (row.base_image_url or "").strip():
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail="a imagem base ainda não está pronta",
        )
    row.status = CharacterStatus.APPROVED
    db.commit()
    row = _detail_query(db, character_id)
    enqueue_character_task(db, TASK_SET, str(character_id))
    return _to_read(row, include_assets=True)


@router.post("/{character_id}/reject")
def reject_character(character_id: UUID, db: DbDep) -> CharacterRead:
    row = _detail_query(db, character_id)
    if row is None:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Personagem não encontrado")
    if row.status != CharacterStatus.PENDING_APPROVAL:
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail="só é possível recusar um personagem aguardando revisão",
        )
    row.status = CharacterStatus.REJECTED
    db.commit()
    row = _detail_query(db, character_id)
    return _to_read(row, include_assets=True)


@router.post("/{character_id}/retry")
def retry_character(character_id: UUID, parsed: CreateInputDep, db: DbDep) -> CharacterRead:
    row = _detail_query(db, character_id)
    if row is None:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Personagem não encontrado")
    if row.status != CharacterStatus.REJECTED:
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail="só é possível reenviar um personagem recusado",
        )
    payload = parsed.payload
    file = parsed.file
    has_file = file is not None and bool(file.filename)
    _assert_image_file(file if has_file else None)
    _require_style(db, payload.style_id, must_be_active=True)
    _guard_paid_jobs(db)
    row.description_prompt = payload.description_prompt
    row.style_id = payload.style_id
    row.base_image_url = None
    row.status = CharacterStatus.PENDING_APPROVAL
    if has_file:
        try:
            row.reference_image_url = _store_reference(row, file)
        except StorageError as exc:
            db.rollback()
            raise HTTPException(
                status_code=http_status.HTTP_502_BAD_GATEWAY,
                detail=str(exc),
            ) from exc
    elif payload.reference_image_url is not None:
        row.reference_image_url = payload.reference_image_url
    db.commit()
    row = _detail_query(db, character_id)
    enqueue_character_task(db, TASK_BASE, str(character_id))
    return _to_read(row, include_assets=True)
