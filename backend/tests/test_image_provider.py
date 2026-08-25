from uuid import uuid4

import pytest

from app.providers.higgsfield_client import FALLBACK_IMAGE_MODELS, HiggsfieldClient
from app.providers.image_provider import (
    ContentModerationError,
    get_image_provider,
    parse_image_provider,
)
from app.providers.openai_image_client import OpenAIImageClient


class FakeResponse:
    def __init__(self, status_code=200, json_body=None, content=b"", text=""):
        self.status_code = status_code
        self._json = json_body
        self.content = content
        self.text = text or ("" if json_body is None else str(json_body))

    def json(self):
        if self._json is None:
            raise ValueError("no json")
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeHTTP:
    def __init__(self, handlers: list[tuple[str, FakeResponse]]):
        self.handlers = handlers

    def post(self, url, **kwargs):
        return self._match(url)

    def get(self, url, **kwargs):
        return self._match(url)

    def close(self):
        return None

    def _match(self, url: str) -> FakeResponse:
        for prefix, response in self.handlers:
            if str(url).startswith(prefix) or prefix in str(url):
                return response
        return FakeResponse(status_code=404, json_body={"detail": url})


def _client(handlers, monkeypatch):
    monkeypatch.setattr(
        "app.providers.higgsfield_client.higgsfield_auth_headers",
        lambda: {"Authorization": "Key test:secret"},
    )
    return HiggsfieldClient(http=FakeHTTP(handlers))


def test_factory_returns_matching_clients():
    assert isinstance(get_image_provider("openai"), OpenAIImageClient)
    assert isinstance(get_image_provider("higgsfield"), HiggsfieldClient)
    with pytest.raises(Exception, match="inválido"):
        get_image_provider("midjourney")


def test_parse_image_provider_defaults():
    assert parse_image_provider({}) == "higgsfield"
    assert parse_image_provider({"image_provider": "openai"}) == "openai"


def test_higgsfield_nsfw_raises_moderation(monkeypatch):
    request_id = str(uuid4())
    client = _client(
        [
            (
                "https://platform.higgsfield.ai/higgsfield-ai/soul",
                FakeResponse(
                    json_body={
                        "request_id": request_id,
                        "status_url": f"https://platform.higgsfield.ai/requests/{request_id}/status",
                    }
                ),
            ),
            ("/status", FakeResponse(json_body={"status": "nsfw", "request_id": request_id})),
        ],
        monkeypatch,
    )
    with pytest.raises(ContentModerationError, match="nsfw"):
        client.generate_image("x", model="higgsfield-ai/soul/v2/standard")


def test_higgsfield_downloads_completed_image(monkeypatch):
    request_id = str(uuid4())
    client = _client(
        [
            (
                "https://cdn.example.com/out.png",
                FakeResponse(content=b"PNGDATA"),
            ),
            (
                "https://platform.higgsfield.ai/higgsfield-ai/soul",
                FakeResponse(
                    json_body={
                        "request_id": request_id,
                        "status_url": f"https://platform.higgsfield.ai/requests/{request_id}/status",
                    }
                ),
            ),
            (
                "/status",
                FakeResponse(
                    json_body={
                        "status": "completed",
                        "images": [{"url": "https://cdn.example.com/out.png"}],
                        "cost_usd": 0.12,
                    }
                ),
            ),
        ],
        monkeypatch,
    )
    result = client.generate_image("forest", model="higgsfield-ai/soul/v2/standard")
    assert result.image_bytes == b"PNGDATA"
    assert result.cost_usd == 0.12


def test_list_image_models_falls_back_when_openapi_missing(monkeypatch):
    client = _client(
        [("openapi.json", FakeResponse(status_code=404, json_body={"detail": "no"}))],
        monkeypatch,
    )
    models = client.list_image_models()
    assert models[0].id == FALLBACK_IMAGE_MODELS[0].id


def test_list_image_models_openai_is_static():
    from app.providers.image_provider import list_image_models

    models = list_image_models("openai")
    assert [item.id for item in models] == ["gpt-image-2", "gpt-image-1-mini"]
