"""Cliente OpenAI Images (`gpt-image-2` / `gpt-image-1-mini`)."""

from __future__ import annotations

import base64
from typing import Any

from app.providers.image_provider import (
    ContentModerationError,
    DEFAULT_IMAGE_QUALITY,
    DEFAULT_IMAGE_SIZE,
    DEFAULT_OPENAI_MODEL,
    ImageProvider,
    ImageProviderError,
    ImageResult,
)
from app.providers.openai_auth import OpenAIKeyError, openai_client

# Estimativas oficiais (USD / imagem) da tabela de pricing GPT Image.
_COST_USD: dict[tuple[str, str, str], float] = {
    ("gpt-image-2", "low", "1024x1024"): 0.006,
    ("gpt-image-2", "low", "1024x1536"): 0.005,
    ("gpt-image-2", "low", "1536x1024"): 0.005,
    ("gpt-image-2", "medium", "1024x1024"): 0.053,
    ("gpt-image-2", "medium", "1024x1536"): 0.041,
    ("gpt-image-2", "medium", "1536x1024"): 0.041,
    ("gpt-image-2", "high", "1024x1024"): 0.211,
    ("gpt-image-2", "high", "1024x1536"): 0.165,
    ("gpt-image-2", "high", "1536x1024"): 0.165,
    ("gpt-image-1-mini", "low", "1024x1024"): 0.005,
    ("gpt-image-1-mini", "low", "1024x1536"): 0.006,
    ("gpt-image-1-mini", "low", "1536x1024"): 0.006,
    ("gpt-image-1-mini", "medium", "1024x1024"): 0.011,
    ("gpt-image-1-mini", "medium", "1024x1536"): 0.015,
    ("gpt-image-1-mini", "medium", "1536x1024"): 0.015,
    ("gpt-image-1-mini", "high", "1024x1024"): 0.036,
    ("gpt-image-1-mini", "high", "1024x1536"): 0.052,
    ("gpt-image-1-mini", "high", "1536x1024"): 0.052,
}

_SIZE_BUCKETS = ("1024x1024", "1024x1536", "1536x1024")


def _normalize_model(model: str) -> str:
    raw = (model or DEFAULT_OPENAI_MODEL).strip().lower()
    if raw.startswith("gpt-image-1-mini"):
        return "gpt-image-1-mini"
    if raw.startswith("gpt-image-2"):
        return "gpt-image-2"
    return raw


def _normalize_size(size: str) -> str:
    raw = (size or DEFAULT_IMAGE_SIZE).strip().lower().replace(" ", "")
    if raw in _SIZE_BUCKETS:
        return raw
    try:
        width, height = (int(part) for part in raw.split("x", 1))
    except (TypeError, ValueError):
        return DEFAULT_IMAGE_SIZE
    if width == height:
        return "1024x1024"
    if height > width:
        return "1024x1536"
    return "1536x1024"


def estimate_image_cost_usd(
    model: str = DEFAULT_OPENAI_MODEL,
    quality: str = DEFAULT_IMAGE_QUALITY,
    size: str = DEFAULT_IMAGE_SIZE,
) -> float:
    key = (_normalize_model(model), (quality or DEFAULT_IMAGE_QUALITY).lower(), _normalize_size(size))
    if key in _COST_USD:
        return _COST_USD[key]
    fallback = (key[0], DEFAULT_IMAGE_QUALITY, DEFAULT_IMAGE_SIZE)
    return _COST_USD.get(fallback, 0.041)


def _is_moderation_error(exc: BaseException) -> bool:
    code = str(getattr(exc, "code", "") or "").lower()
    if code == "moderation_blocked":
        return True
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        error = body.get("error") if isinstance(body.get("error"), dict) else body
        inner_code = str((error or {}).get("code") or "").lower()
        if inner_code == "moderation_blocked":
            return True
    text = str(exc).lower()
    return "moderation_blocked" in text or "safety system" in text


class OpenAIImageClient(ImageProvider):
    def __init__(self, client: Any | None = None) -> None:
        self._client = client

    def _sdk(self):
        if self._client is not None:
            return self._client
        try:
            return openai_client()
        except OpenAIKeyError as exc:
            raise ImageProviderError(str(exc)) from exc

    def generate_image(self, prompt: str, **kwargs: Any) -> ImageResult:
        model = str(kwargs.get("model") or DEFAULT_OPENAI_MODEL)
        quality = str(kwargs.get("quality") or DEFAULT_IMAGE_QUALITY)
        size = str(kwargs.get("size") or DEFAULT_IMAGE_SIZE)
        text = (prompt or "").strip()
        if not text:
            raise ImageProviderError("prompt vazio")

        try:
            response = self._sdk().images.generate(
                model=model,
                prompt=text,
                quality=quality,
                size=size,
                n=1,
            )
        except Exception as exc:
            if _is_moderation_error(exc):
                raise ContentModerationError("OpenAI recusou o prompt por moderação de conteúdo") from exc
            raise ImageProviderError(f"falha na OpenAI Images: {exc}") from exc

        data = getattr(response, "data", None) or []
        if not data:
            raise ImageProviderError("OpenAI Images devolveu resposta vazia")
        first = data[0]
        encoded = getattr(first, "b64_json", None) or (first.get("b64_json") if isinstance(first, dict) else None)
        if not encoded:
            raise ImageProviderError("OpenAI Images não devolveu b64_json")
        try:
            image_bytes = base64.b64decode(encoded)
        except (ValueError, TypeError) as exc:
            raise ImageProviderError("b64_json da OpenAI é inválido") from exc
        if not image_bytes:
            raise ImageProviderError("imagem decodificada veio vazia")
        return ImageResult(
            image_bytes=image_bytes,
            cost_usd=estimate_image_cost_usd(model, quality, size),
        )


def generate_image(
    prompt: str,
    model: str = DEFAULT_OPENAI_MODEL,
    quality: str = DEFAULT_IMAGE_QUALITY,
    size: str = DEFAULT_IMAGE_SIZE,
) -> bytes:
    """Gera uma imagem e devolve os bytes PNG/JPEG decodificados do base64."""
    return OpenAIImageClient().generate_image(
        prompt,
        model=model,
        quality=quality,
        size=size,
    ).image_bytes
