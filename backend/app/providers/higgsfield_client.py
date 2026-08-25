"""Cliente Higgsfield para geração de imagem (API assíncrona + polling)."""

from __future__ import annotations

import time
from typing import Any
from urllib.parse import urljoin

from app.core.config import settings
from app.providers.image_provider import (
    ContentModerationError,
    DEFAULT_HIGGSFIELD_MODEL,
    ImageModelInfo,
    ImageProvider,
    ImageProviderError,
    ImageResult,
)

BASE_URL = "https://platform.higgsfield.ai"
_TERMINAL = frozenset({"completed", "failed", "nsfw", "canceled", "cancelled"})
_VIDEO_MARKERS = ("video", "dop", "seedance", "kling", "veo", "wan/", "ltx", "hailuo", "pixverse")

# Catálogo estático (docs Higgsfield) usado se o OpenAPI remoto falhar.
FALLBACK_IMAGE_MODELS: tuple[ImageModelInfo, ...] = (
    ImageModelInfo("higgsfield-ai/soul/v2/standard", "Soul 2"),
    ImageModelInfo("openai/gpt-image-2", "GPT Image 2"),
    ImageModelInfo("flux-2-pro", "Flux 2"),
    ImageModelInfo("nano-banana-2/text-to-image", "Nano Banana 2"),
    ImageModelInfo("nano-banana-2/lite/text-to-image", "Nano Banana 2 Lite"),
    ImageModelInfo("nano-banana-pro", "Nano Banana Pro"),
    ImageModelInfo("z-image/turbo", "Z-Image Turbo"),
    ImageModelInfo("recraft/v4.1/text-to-image", "Recraft 4.1"),
    ImageModelInfo("xai/grok-imagine-image-2.0", "Grok Imagine 2.0"),
    ImageModelInfo("ideogram/v4.0", "Ideogram 4.0"),
    ImageModelInfo("alibaba/qwen-image-3/text-to-image", "Qwen Image 3"),
)


class HiggsfieldError(ImageProviderError):
    """Falha HTTP ou de polling na Higgsfield."""


def higgsfield_auth_headers() -> dict[str, str]:
    key = (settings.higgsfield_api_key or "").strip()
    secret = (getattr(settings, "higgsfield_api_secret", "") or "").strip()
    if not key or key.startswith("your_"):
        raise HiggsfieldError("HIGGSFIELD_API_KEY não configurada")
    if secret:
        return {"Authorization": f"Key {key}:{secret}"}
    if ":" in key:
        return {"Authorization": f"Key {key}"}
    return {"Authorization": f"Bearer {key}"}


def _is_image_path(path: str) -> bool:
    lowered = path.lower()
    if any(marker in lowered for marker in _VIDEO_MARKERS):
        return False
    if "cancel" in lowered or "/requests/" in lowered:
        return False
    return True


class HiggsfieldClient(ImageProvider):
    def __init__(self, http: Any | None = None) -> None:
        self._http = http

    def _client(self) -> Any:
        if self._http is not None:
            return self._http
        import httpx

        return httpx.Client(timeout=httpx.Timeout(30.0, read=180.0))

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        headers.update(higgsfield_auth_headers())
        return headers

    def generate_image(self, prompt: str, **kwargs: Any) -> ImageResult:
        text = (prompt or "").strip()
        if not text:
            raise ImageProviderError("prompt vazio")
        model = str(kwargs.get("model") or DEFAULT_HIGGSFIELD_MODEL).lstrip("/")
        owns = self._http is None
        client = self._client()
        try:
            submitted = self._submit(client, model, text)
            payload = self._poll(client, submitted)
            status = str(payload.get("status") or "").lower()
            if status == "nsfw":
                raise ContentModerationError("Higgsfield recusou a geração por moderação de conteúdo (nsfw)")
            if status not in {"completed", "complete", "success"}:
                raise HiggsfieldError(payload.get("error") or f"geração Higgsfield terminou com status {status or '?'}")
            image_bytes = self._download_image(client, payload)
            return ImageResult(image_bytes=image_bytes, cost_usd=_cost_from_payload(payload))
        finally:
            if owns:
                client.close()

    def list_image_models(self) -> list[ImageModelInfo]:
        owns = self._http is None
        client = self._client()
        try:
            response = client.get(
                urljoin(BASE_URL + "/", "openapi.json"),
                headers=self._headers(),
                timeout=30.0,
            )
            if response.status_code >= 400:
                return list(FALLBACK_IMAGE_MODELS)
            spec = response.json()
            paths = spec.get("paths") if isinstance(spec, dict) else None
            if not isinstance(paths, dict):
                return list(FALLBACK_IMAGE_MODELS)
            models: list[ImageModelInfo] = []
            seen: set[str] = set()
            for path, methods in paths.items():
                if not isinstance(methods, dict) or "post" not in methods:
                    continue
                if not _is_image_path(str(path)):
                    continue
                model_id = str(path).lstrip("/")
                if model_id in seen:
                    continue
                seen.add(model_id)
                post = methods.get("post") or {}
                name = str(post.get("summary") or post.get("operationId") or model_id)
                models.append(ImageModelInfo(id=model_id, name=name))
            return models or list(FALLBACK_IMAGE_MODELS)
        except Exception:
            return list(FALLBACK_IMAGE_MODELS)
        finally:
            if owns:
                client.close()

    def _submit(self, client: Any, model: str, prompt: str) -> dict[str, Any]:
        url = urljoin(BASE_URL + "/", model)
        response = client.post(url, headers=self._headers(), json={"prompt": prompt}, timeout=60.0)
        self._raise_http(response)
        payload = response.json()
        if not isinstance(payload, dict):
            raise HiggsfieldError("resposta de submit Higgsfield inválida")
        return payload

    def _poll(self, client: Any, submitted: dict[str, Any]) -> dict[str, Any]:
        status_url = submitted.get("status_url")
        request_id = submitted.get("request_id")
        if not status_url:
            if not request_id:
                raise HiggsfieldError("submit Higgsfield sem status_url/request_id")
            status_url = f"{BASE_URL}/requests/{request_id}/status"
        delay = 2.0
        deadline = 240.0
        elapsed = 0.0
        while elapsed < deadline:
            response = client.get(str(status_url), headers=self._headers(), timeout=30.0)
            self._raise_http(response)
            payload = response.json()
            if not isinstance(payload, dict):
                raise HiggsfieldError("status Higgsfield inválido")
            status = str(payload.get("status") or "").lower()
            if status in _TERMINAL or status in {"complete", "success"}:
                return payload
            time.sleep(delay)
            elapsed += delay
            delay = min(delay * 1.5, 10.0)
        raise HiggsfieldError("timeout ao esperar a geração Higgsfield")

    def _download_image(self, client: Any, payload: dict[str, Any]) -> bytes:
        images = payload.get("images") or []
        url = None
        if images and isinstance(images[0], dict):
            url = images[0].get("url")
        elif images and isinstance(images[0], str):
            url = images[0]
        url = url or payload.get("url") or payload.get("image_url")
        if not url:
            raise HiggsfieldError("geração Higgsfield sem URL de imagem")
        response = client.get(str(url), timeout=60.0)
        response.raise_for_status()
        if not response.content:
            raise HiggsfieldError("download da imagem Higgsfield veio vazio")
        return response.content

    def _raise_http(self, response: Any) -> None:
        if response.status_code < 400:
            return
        detail = ""
        try:
            body = response.json()
            detail = str(body.get("detail") or body.get("error") or body)
        except ValueError:
            detail = response.text[:300]
        message = detail or f"HTTP {response.status_code}"
        lowered = message.lower()
        if response.status_code == 400 and ("nsfw" in lowered or "moderation" in lowered or "safety" in lowered):
            raise ContentModerationError(f"Higgsfield recusou o prompt por moderação: {message}")
        raise HiggsfieldError(f"Higgsfield HTTP {response.status_code}: {message}")


def _cost_from_payload(payload: dict[str, Any]) -> float:
    for key in ("cost_usd", "cost", "price_usd"):
        value = payload.get(key)
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return 0.0


def generate_image(prompt: str, **kwargs: Any) -> ImageResult:
    return HiggsfieldClient().generate_image(prompt, **kwargs)
