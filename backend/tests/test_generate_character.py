from contextlib import nullcontext
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.generate_character import (
    BASE_POSE_INSTRUCTION,
    CHARACTER_ASSET_PROMPTS,
    CharacterImageError,
    CharacterNotFound,
    build_asset_prompt,
    build_base_prompt,
    generate_character_asset,
    generate_character_base_image,
    generate_character_set,
    reference_filename,
)
from app.models.character import Character
from app.models.enums import CharacterAssetType, CharacterStatus
from app.models.style import Style
from app.providers.image_provider import ImageResult
from app.providers.openai_image_client import OpenAIImageClient
from app.schemas.character import CharacterCreate


class FakeScalars:
    def __init__(self, rows):
        self._rows = rows

    def first(self):
        return self._rows[0] if self._rows else None

    def all(self):
        return list(self._rows)


class FakeDB:
    def __init__(self, character, style=None, assets=None):
        self.character = character
        self.style = style
        self.assets = list(assets or [])
        self.added = []

    def get(self, model, pid):
        if model is Character and self.character is not None and self.character.id == pid:
            return self.character
        if model is Style and self.style is not None and self.style.id == pid:
            return self.style
        return None

    def refresh(self, _obj):
        return None

    def scalars(self, _stmt):
        return FakeScalars(self.assets)

    def add(self, obj):
        if getattr(obj, "id", None) is None:
            obj.id = uuid4()
        self.added.append(obj)
        self.assets.append(obj)

    def flush(self):
        return None

    def commit(self):
        return None

    def rollback(self):
        return None

    def close(self):
        return None


class FakeOpenAI:
    def __init__(self):
        self.generate_calls = []
        self.edit_calls = []

    def generate_image(self, prompt, **kwargs):
        self.generate_calls.append((prompt, kwargs))
        return ImageResult(image_bytes=b"GEN", cost_usd=0.04)

    def edit_image(self, prompt, image_bytes, **kwargs):
        self.edit_calls.append((prompt, image_bytes, kwargs))
        return ImageResult(image_bytes=b"EDIT", cost_usd=0.04)


def _character(**kwargs):
    style_id = kwargs.pop("style_id", uuid4())
    defaults = dict(
        id=uuid4(),
        description_prompt="mulher loira de 30 anos, casaco vermelho",
        style_id=style_id,
        reference_image_url=None,
        base_image_url=None,
        status=CharacterStatus.PENDING_APPROVAL,
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_build_base_prompt_includes_style_and_pose():
    prompt = build_base_prompt("herói magro", "Anime")
    assert "herói magro" in prompt
    assert "Anime" in prompt
    assert BASE_POSE_INSTRUCTION in prompt


def test_asset_prompts_cover_all_types():
    assert set(CHARACTER_ASSET_PROMPTS) == set(CharacterAssetType)
    text = build_asset_prompt("herói", "Cartoon", CharacterAssetType.HOLDING_MUG)
    assert "caneca" in text
    assert "Cartoon" in text


def test_reference_filename_keeps_safe_suffix():
    assert reference_filename("foto.JPEG") == "reference.jpeg"
    assert reference_filename("notes.txt") == "reference.png"


def test_character_create_strips_prompt():
    payload = CharacterCreate(description_prompt="  um mago  ", style_id=uuid4())
    assert payload.description_prompt == "um mago"
    assert payload.reference_image_url is None


def test_base_image_uses_generate_without_reference(monkeypatch):
    style_id = uuid4()
    character = _character(style_id=style_id)
    style = SimpleNamespace(id=style_id, name="Anime")
    db = FakeDB(character, style)
    client = FakeOpenAI()
    monkeypatch.setattr(
        "app.core.generate_character.provider_semaphore.hold",
        lambda *_a, **_k: nullcontext(),
    )
    result = generate_character_base_image(
        character.id,
        db=db,
        client=client,
        upload=lambda *_a, **_k: "https://cdn.example.com/base.png",
    )
    assert client.generate_calls
    assert not client.edit_calls
    assert character.base_image_url == "https://cdn.example.com/base.png"
    assert result["used_reference"] is False


def test_base_image_uses_edit_with_reference(monkeypatch):
    style_id = uuid4()
    character = _character(style_id=style_id, reference_image_url="https://cdn.example.com/ref.png")
    style = SimpleNamespace(id=style_id, name="Anime")
    db = FakeDB(character, style)
    client = FakeOpenAI()
    monkeypatch.setattr(
        "app.core.generate_character.provider_semaphore.hold",
        lambda *_a, **_k: nullcontext(),
    )
    result = generate_character_base_image(
        character.id,
        db=db,
        client=client,
        upload=lambda *_a, **_k: "https://cdn.example.com/base.png",
        fetch_image=lambda url: b"REF",
    )
    assert client.edit_calls
    assert not client.generate_calls
    assert client.edit_calls[0][1] == b"REF"
    assert result["used_reference"] is True


def test_base_image_skips_save_if_rejected(monkeypatch):
    style_id = uuid4()
    character = _character(style_id=style_id)

    class RejectDB(FakeDB):
        def refresh(self, obj):
            obj.status = CharacterStatus.REJECTED

    db = RejectDB(character, SimpleNamespace(id=style_id, name="Anime"))
    client = FakeOpenAI()
    monkeypatch.setattr(
        "app.core.generate_character.provider_semaphore.hold",
        lambda *_a, **_k: nullcontext(),
    )
    result = generate_character_base_image(
        character.id,
        db=db,
        client=client,
        upload=lambda *_a, **_k: "https://cdn.example.com/base.png",
    )
    assert result["skipped"] is True
    assert character.base_image_url is None


def test_base_image_missing_character():
    db = FakeDB(None)
    with pytest.raises(CharacterNotFound):
        generate_character_base_image(uuid4(), db=db, client=FakeOpenAI())


def test_character_set_fans_out_all_asset_types():
    character = _character(status=CharacterStatus.APPROVED, base_image_url="https://cdn.example.com/base.png")
    db = FakeDB(character)
    seen = []

    def fake_asset(cid, asset_type, **_kwargs):
        seen.append(asset_type)
        return {"asset_type": getattr(asset_type, "value", asset_type)}

    result = generate_character_set(character.id, db=db, generate_asset=fake_asset)
    assert result["count"] == len(CharacterAssetType)
    assert set(seen) == set(CharacterAssetType)


def test_character_set_requires_approval():
    character = _character(status=CharacterStatus.PENDING_APPROVAL, base_image_url="https://x")
    with pytest.raises(CharacterImageError, match="aprovado"):
        generate_character_set(character.id, db=FakeDB(character), generate_asset=lambda *_a, **_k: {})


def test_character_asset_edits_from_base(monkeypatch):
    style_id = uuid4()
    character = _character(
        style_id=style_id,
        status=CharacterStatus.APPROVED,
        base_image_url="https://cdn.example.com/base.png",
    )
    db = FakeDB(character, SimpleNamespace(id=style_id, name="Anime"))
    client = FakeOpenAI()
    monkeypatch.setattr(
        "app.core.generate_character.provider_semaphore.hold",
        lambda *_a, **_k: nullcontext(),
    )
    result = generate_character_asset(
        character.id,
        CharacterAssetType.SMILING,
        db=db,
        client=client,
        upload=lambda *_a, **_k: "https://cdn.example.com/smiling.png",
        fetch_image=lambda url: b"BASE",
    )
    assert client.edit_calls
    assert client.edit_calls[0][1] == b"BASE"
    assert "sorrindo" in client.edit_calls[0][0]
    assert result["image_url"] == "https://cdn.example.com/smiling.png"
    assert db.added
    assert db.added[0].asset_type is CharacterAssetType.SMILING


def test_character_asset_skips_existing(monkeypatch):
    existing = SimpleNamespace(id=uuid4(), image_url="https://cdn.example.com/old.png", asset_type=CharacterAssetType.ANGRY)
    character = _character(status=CharacterStatus.APPROVED, base_image_url="https://cdn.example.com/base.png")
    db = FakeDB(character, assets=[existing])
    client = FakeOpenAI()
    result = generate_character_asset(
        character.id,
        "angry",
        db=db,
        client=client,
        fetch_image=lambda url: b"BASE",
    )
    assert result["skipped"] is True
    assert not client.edit_calls


def test_openai_edit_image_decodes_base64():
    import base64
    from types import SimpleNamespace as NS

    png = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="

    class FakeImages:
        def __init__(self):
            self.calls = []

        def edit(self, **kwargs):
            self.calls.append(kwargs)
            return NS(data=[NS(b64_json=png)])

        def generate(self, **kwargs):
            raise AssertionError("generate não deveria ser chamado")

    images = FakeImages()
    client = OpenAIImageClient(client=NS(images=images))
    result = client.edit_image("same character sitting", b"REF", model="gpt-image-2")
    assert result.image_bytes == base64.b64decode(png)
    assert images.calls[0]["image"][1] == b"REF"
    assert images.calls[0]["prompt"] == "same character sitting"
