from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from app.providers.image_provider import IMAGE_PROVIDERS, ImageProviderError, list_image_models
from app.schemas.project import ImageModelRead

router = APIRouter(prefix="/api/image-models", tags=["image-models"])


@router.get("")
def list_catalog_image_models(
    provider: Annotated[str, Query()] = "higgsfield",
) -> list[ImageModelRead]:
    name = str(provider or "higgsfield").strip().lower()
    if name not in IMAGE_PROVIDERS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="provider deve ser 'higgsfield' ou 'openai'",
        )
    try:
        models = list_image_models(name)
    except ImageProviderError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"não foi possível listar modelos: {exc}",
        ) from exc
    return [ImageModelRead(id=model.id, name=model.name) for model in models]
