"""Interface comum de geração de imagem (Higgsfield e OpenAI)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

IMAGE_PROVIDERS = frozenset({"higgsfield", "openai"})
DEFAULT_IMAGE_PROVIDER = "higgsfield"
DEFAULT_IMAGE_SIZE = "1536x1024"
DEFAULT_IMAGE_QUALITY = "medium"
OPENAI_IMAGE_MODELS = ("gpt-image-2", "gpt-image-1-mini")
DEFAULT_OPENAI_MODEL = "gpt-image-2"
DEFAULT_HIGGSFIELD_MODEL = "higgsfield-ai/soul/v2/standard"
IMAGE_QUALITIES = frozenset({"low", "medium", "high"})


class ImageProviderError(Exception):
    """Falha genérica ao gerar imagem."""


class ContentModerationError(ImageProviderError):
    """Prompt ou output recusado por moderação de conteúdo. Não deve sofrer retry."""

    permanent = True


@dataclass(frozen=True)
class ImageResult:
    image_bytes: bytes
    cost_usd: float


@dataclass(frozen=True)
class ImageModelInfo:
    id: str
    name: str


class ImageProvider(ABC):
    """Trocar de provider não muda quem chama `generate_image()`."""

    @abstractmethod
    def generate_image(self, prompt: str, **kwargs: Any) -> ImageResult:
        """Gera uma imagem a partir do prompt. kwargs dependem do provider (model, quality, size)."""


def parse_image_provider(config: dict[str, Any] | None) -> str:
    raw = (config or {}).get("image_provider") or DEFAULT_IMAGE_PROVIDER
    name = str(raw).strip().lower()
    if name not in IMAGE_PROVIDERS:
        raise ImageProviderError(f"image_provider inválido: {raw!r}")
    return name


def default_image_model(provider: str) -> str:
    if provider == "openai":
        return DEFAULT_OPENAI_MODEL
    return DEFAULT_HIGGSFIELD_MODEL


def get_image_provider(provider_name: str) -> ImageProvider:
    """Factory: devolve o client correspondente a `higgsfield` ou `openai`."""
    name = (provider_name or DEFAULT_IMAGE_PROVIDER).strip().lower()
    if name == "openai":
        from app.providers.openai_image_client import OpenAIImageClient

        return OpenAIImageClient()
    if name == "higgsfield":
        from app.providers.higgsfield_client import HiggsfieldClient

        return HiggsfieldClient()
    raise ImageProviderError(f"image_provider inválido: {provider_name!r}")
