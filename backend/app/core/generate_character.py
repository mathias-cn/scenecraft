"""Gera imagem base e character set de um personagem via OpenAI Images."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.daily_budget import assert_paid_job_allowed
from app.core.provider_limiter import provider_semaphore
from app.models.character import Character, CharacterAsset
from app.models.enums import CharacterAssetType, CharacterStatus
from app.models.style import Style
from app.providers.image_provider import DEFAULT_IMAGE_QUALITY, DEFAULT_OPENAI_MODEL
from app.providers.openai_image_client import OpenAIImageClient

CHARACTER_IMAGE_SIZE = "1024x1536"
BASE_POSE_INSTRUCTION = "corpo inteiro, fundo neutro, pose neutra"
OPENAI_PROVIDER = "openai"
ASSET_FANOUT_WORKERS = 4

CHARACTER_ASSET_PROMPTS: dict[CharacterAssetType, str] = {
    CharacterAssetType.TPOSE_SIDE: "T-pose de corpo inteiro de lado, fundo neutro",
    CharacterAssetType.TPOSE_BACK: "T-pose de corpo inteiro de costas, fundo neutro",
    CharacterAssetType.HEAD_FRONT: "zoom na cabeça de frente, fundo neutro",
    CharacterAssetType.HEAD_SIDE: "zoom na cabeça de lado, fundo neutro",
    CharacterAssetType.HEAD_BACK: "zoom na cabeça de costas, fundo neutro",
    CharacterAssetType.SITTING: "personagem sentado, fundo neutro",
    CharacterAssetType.HOLDING_MUG: "personagem segurando uma caneca, fundo neutro",
    CharacterAssetType.SMILING: "personagem sorrindo, fundo neutro",
    CharacterAssetType.ANGRY: "personagem bravo, fundo neutro",
}

_IMAGE_FETCH_LIMIT = 20 * 1024 * 1024


class CharacterNotFound(ValueError):
    """Personagem inexistente."""


class CharacterImageError(ValueError):
    """Falha ao gerar ou persistir imagem do personagem."""


def build_base_prompt(description: str, style_name: str) -> str:
    parts = [
        (description or "").strip(),
        f"Estilo visual: {style_name.strip()}" if style_name and style_name.strip() else "",
        BASE_POSE_INSTRUCTION,
        "Personagem único, identidade visual consistente, sem texto na imagem.",
    ]
    return ". ".join(part.rstrip(".") for part in parts if part)


def build_asset_prompt(description: str, style_name: str, asset_type: CharacterAssetType) -> str:
    pose = CHARACTER_ASSET_PROMPTS[asset_type]
    parts = [
        (description or "").strip(),
        f"Estilo visual: {style_name.strip()}" if style_name and style_name.strip() else "",
        pose,
        "Mantenha a mesma identidade visual da imagem de referência aprovada. Sem texto na imagem.",
    ]
    return ". ".join(part.rstrip(".") for part in parts if part)


def fetch_image_bytes(url: str) -> bytes:
    """Baixa bytes da URL de storage; se falhar, tenta HTTP público."""
    if not (url or "").strip():
        raise CharacterImageError("url de imagem vazia")
    try:
        from app.storage import StorageError, download_bytes

        try:
            return download_bytes(url)
        except StorageError:
            pass
    except ImportError:
        pass
    import httpx

    try:
        response = httpx.get(url, timeout=30.0, follow_redirects=True)
        response.raise_for_status()
    except Exception as exc:
        raise CharacterImageError(f"não foi possível baixar a imagem de referência: {exc}") from exc
    data = response.content
    if not data:
        raise CharacterImageError("imagem de referência veio vazia")
    if len(data) > _IMAGE_FETCH_LIMIT:
        raise CharacterImageError("imagem de referência excede 20MB")
    return data


def generate_character_base_image(
    character_id: str | UUID,
    db: Session | None = None,
    *,
    client: OpenAIImageClient | None = None,
    upload=None,
    fetch_image=None,
) -> dict:
    """Gera a imagem base (generate ou images.edit se houver referência) e grava `base_image_url`."""
    session, owns = _session(db)
    try:
        character = _load_character(session, character_id)
        style_name = _style_name(session, character.style_id)
        prompt = build_base_prompt(character.description_prompt, style_name)
        openai = client or OpenAIImageClient()
        fetch = fetch_image or fetch_image_bytes
        reference = (character.reference_image_url or "").strip()

        with provider_semaphore.hold(OPENAI_PROVIDER):
            if reference:
                image_bytes = fetch(reference)
                result = openai.edit_image(
                    prompt,
                    image_bytes,
                    model=DEFAULT_OPENAI_MODEL,
                    quality=DEFAULT_IMAGE_QUALITY,
                    size=CHARACTER_IMAGE_SIZE,
                )
            else:
                result = openai.generate_image(
                    prompt,
                    model=DEFAULT_OPENAI_MODEL,
                    quality=DEFAULT_IMAGE_QUALITY,
                    size=CHARACTER_IMAGE_SIZE,
                )

        session.refresh(character)
        if character.status != CharacterStatus.PENDING_APPROVAL:
            return {"character_id": str(character.id), "skipped": True, "reason": "status_changed"}

        uploader = upload or _default_upload
        url = uploader(
            BytesIO(result.image_bytes),
            f"characters/{character.id}",
            "base.png",
            content_type="image/png",
        )
        character.base_image_url = url
        session.flush()
        if owns:
            session.commit()
        return {
            "character_id": str(character.id),
            "base_image_url": url,
            "used_reference": bool(reference),
        }
    except Exception:
        if owns:
            session.rollback()
        raise
    finally:
        if owns:
            session.close()


def generate_character_set(
    character_id: str | UUID,
    db: Session | None = None,
    *,
    client: OpenAIImageClient | None = None,
    upload=None,
    fetch_image=None,
    generate_asset=None,
) -> dict:
    """Fan-out das poses do character set, limitado pelo semáforo Redis do provider openai."""
    session, owns = _session(db)
    try:
        character = _load_character(session, character_id)
        if character.status != CharacterStatus.APPROVED:
            raise CharacterImageError("personagem precisa estar aprovado para gerar o character set")
        if not (character.base_image_url or "").strip():
            raise CharacterImageError("personagem sem imagem base aprovada")
        cid = str(character.id)
    finally:
        if owns:
            session.close()

    worker = generate_asset or generate_character_asset
    errors: list[str] = []
    generated: list[dict] = []
    with ThreadPoolExecutor(max_workers=ASSET_FANOUT_WORKERS) as pool:
        futures = {
            pool.submit(
                worker,
                cid,
                asset_type,
                client=client,
                upload=upload,
                fetch_image=fetch_image,
            ): asset_type
            for asset_type in CharacterAssetType
        }
        for future in as_completed(futures):
            asset_type = futures[future]
            try:
                generated.append(future.result())
            except Exception as exc:
                errors.append(f"{asset_type.value}: {exc}")
    if errors and not generated:
        raise CharacterImageError("falha ao gerar o character set: " + "; ".join(errors))
    return {
        "character_id": cid,
        "generated": generated,
        "failed": errors,
        "count": len(generated),
    }


def generate_character_asset(
    character_id: str | UUID,
    asset_type: CharacterAssetType | str,
    db: Session | None = None,
    *,
    client: OpenAIImageClient | None = None,
    upload=None,
    fetch_image=None,
) -> dict:
    """Gera uma pose com `images.edit` usando a imagem base aprovada como referência."""
    parsed = _parse_asset_type(asset_type)
    session, owns = _session(db)
    try:
        character = _load_character(session, character_id)
        if character.status != CharacterStatus.APPROVED:
            raise CharacterImageError("personagem precisa estar aprovado")
        base_url = (character.base_image_url or "").strip()
        if not base_url:
            raise CharacterImageError("personagem sem imagem base")

        existing = session.scalars(
            select(CharacterAsset).where(
                CharacterAsset.character_id == character.id,
                CharacterAsset.asset_type == parsed,
            )
        ).first()
        if existing and existing.image_url:
            return {
                "character_id": str(character.id),
                "asset_type": parsed.value,
                "image_url": existing.image_url,
                "skipped": True,
            }

        style_name = _style_name(session, character.style_id)
        prompt = build_asset_prompt(character.description_prompt, style_name, parsed)
        openai = client or OpenAIImageClient()
        fetch = fetch_image or fetch_image_bytes
        reference_bytes = fetch(base_url)

        with provider_semaphore.hold(OPENAI_PROVIDER):
            result = openai.edit_image(
                prompt,
                reference_bytes,
                model=DEFAULT_OPENAI_MODEL,
                quality=DEFAULT_IMAGE_QUALITY,
                size=CHARACTER_IMAGE_SIZE,
            )

        uploader = upload or _default_upload
        url = uploader(
            BytesIO(result.image_bytes),
            f"characters/{character.id}",
            f"{parsed.value}.png",
            content_type="image/png",
        )
        if existing:
            existing.image_url = url
            asset = existing
        else:
            asset = CharacterAsset(
                character_id=character.id,
                asset_type=parsed,
                image_url=url,
            )
            session.add(asset)
        session.flush()
        if owns:
            session.commit()
        return {
            "character_id": str(character.id),
            "asset_id": str(asset.id),
            "asset_type": parsed.value,
            "image_url": url,
        }
    except Exception:
        if owns:
            session.rollback()
        raise
    finally:
        if owns:
            session.close()


def enqueue_character_task(db: Session, task_name: str, *args) -> None:
    from app.celery_app import celery_app

    assert_paid_job_allowed(db)
    celery_app.send_task(task_name, args=list(args), queue="media_gen")


def _load_character(session: Session, character_id: str | UUID) -> Character:
    cid = character_id if isinstance(character_id, UUID) else UUID(str(character_id))
    character = session.get(Character, cid)
    if character is None:
        raise CharacterNotFound(str(cid))
    return character


def _style_name(session: Session, style_id: UUID) -> str:
    style = session.get(Style, style_id)
    return style.name if style is not None else ""


def _parse_asset_type(asset_type: CharacterAssetType | str) -> CharacterAssetType:
    if isinstance(asset_type, CharacterAssetType):
        return asset_type
    try:
        return CharacterAssetType(str(asset_type))
    except ValueError as exc:
        raise CharacterImageError(f"asset_type inválido: {asset_type}") from exc


def _default_upload(fileobj, prefix: str, filename: str, *, content_type: str | None = None) -> str:
    from app.storage import upload_fileobj

    return upload_fileobj(fileobj, prefix, filename, content_type=content_type)


def _session(db: Session | None) -> tuple[Session, bool]:
    if db is not None:
        return db, False
    from app.db import SessionLocal

    return SessionLocal(), True


def reference_filename(original: str | None) -> str:
    suffix = Path(original or "reference.png").suffix.lower()
    if suffix not in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
        suffix = ".png"
    return f"reference{suffix}"
