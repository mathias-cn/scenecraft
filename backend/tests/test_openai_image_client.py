import base64
from types import SimpleNamespace

import pytest

from app.providers.image_provider import ContentModerationError, ImageProviderError
from app.providers.openai_image_client import (
    OpenAIImageClient,
    estimate_image_cost_usd,
    generate_image,
)

_PNG_B64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="


class FakeImages:
    def __init__(self, *, encoded=None, error=None, recorder=None):
        self._encoded = encoded
        self._error = error
        self._recorder = recorder if recorder is not None else []

    def generate(self, **kwargs):
        self._recorder.append(kwargs)
        if self._error is not None:
            raise self._error
        return SimpleNamespace(data=[SimpleNamespace(b64_json=self._encoded)])


def _client(encoded=_PNG_B64, error=None, recorder=None):
    return SimpleNamespace(images=FakeImages(encoded=encoded, error=error, recorder=recorder))


def test_estimate_cost_uses_model_quality_size():
    assert estimate_image_cost_usd("gpt-image-2", "medium", "1536x1024") == 0.041
    assert estimate_image_cost_usd("gpt-image-1-mini", "low", "1024x1024") == 0.005


def test_generate_image_decodes_base64():
    recorder: list[dict] = []
    client = OpenAIImageClient(client=_client(recorder=recorder))
    result = client.generate_image("a cat", model="gpt-image-2", quality="medium", size="1536x1024")
    assert result.image_bytes == base64.b64decode(_PNG_B64)
    assert result.cost_usd == 0.041
    assert recorder[0]["model"] == "gpt-image-2"
    assert recorder[0]["quality"] == "medium"
    assert recorder[0]["size"] == "1536x1024"


def test_module_generate_image_returns_bytes(monkeypatch):
    monkeypatch.setattr(
        "app.providers.openai_image_client.OpenAIImageClient.generate_image",
        lambda self, prompt, **kwargs: SimpleNamespace(image_bytes=b"PNG", cost_usd=0.1),
    )
    assert generate_image("sky") == b"PNG"


def test_moderation_blocked_raises_content_error():
    err = RuntimeError("safety system")
    err.code = "moderation_blocked"
    client = OpenAIImageClient(client=_client(error=err))
    with pytest.raises(ContentModerationError, match="moderação"):
        client.generate_image("blocked")
    assert ContentModerationError.permanent is True


def test_empty_prompt_raises():
    with pytest.raises(ImageProviderError, match="vazio"):
        OpenAIImageClient(client=_client()).generate_image("  ")
