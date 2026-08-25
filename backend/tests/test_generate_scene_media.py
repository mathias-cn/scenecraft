from contextlib import nullcontext
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.core.generate_scene_media import generate_scene_media
from app.models.enums import MediaType, SceneStatus, SourceType
from app.models.project import Project
from app.models.scene import Scene
from app.providers.image_provider import ImageResult
from app.schemas.project import ProjectCreate


class FakeDB:
    def __init__(self, project, scene, extra=None):
        self.project = project
        self.scene = scene
        self.extra = extra or {}
        self.commits = 0
        self.rollbacks = 0

    def get(self, model, pid):
        if model is Project:
            return self.project if self.project.id == pid else None
        if model is Scene:
            return self.scene if self.scene.id == pid else None
        extra = getattr(self, "extra", None) or {}
        if extra.get(model) is not None and extra[model].id == pid:
            return extra[model]
        return None

    def flush(self):
        return None

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        return None


class FakeProvider:
    def __init__(self, name="openai"):
        self.name = name
        self.calls = []
        self.edits = []

    def generate_image(self, prompt, **kwargs):
        self.calls.append((prompt, kwargs))
        return ImageResult(image_bytes=b"PNG", cost_usd=0.041)

    def edit_image(self, prompt, image_bytes, **kwargs):
        self.edits.append((prompt, image_bytes, kwargs))
        return ImageResult(image_bytes=b"EDIT", cost_usd=0.041)


def _scene_project(provider="openai"):
    pid = uuid4()
    sid = uuid4()
    project = SimpleNamespace(
        id=pid,
        automation_config={
            "image_provider": provider,
            "image_model": "gpt-image-2" if provider == "openai" else "higgsfield-ai/soul/v2/standard",
            "image_quality": "medium",
        },
    )
    scene = SimpleNamespace(
        id=sid,
        project_id=pid,
        index=0,
        visual_prompt="cinematic forest",
        status=SceneStatus.PENDING,
        generation_provider=None,
        media_url=None,
        media_type=MediaType.IMAGE,
        cost_usd=None,
        style=None,
    )
    return project, scene


def test_generate_scene_media_uses_named_provider(monkeypatch):
    project, scene = _scene_project("openai")
    db = FakeDB(project, scene)
    fake = FakeProvider("openai")
    held = []
    monkeypatch.setattr("app.core.generate_scene_media.get_image_provider", lambda name: fake)
    monkeypatch.setattr(
        "app.core.generate_scene_media.provider_semaphore.hold",
        lambda name, **kwargs: held.append(name) or nullcontext(),
    )
    result = generate_scene_media(
        project.id,
        scene.id,
        db=db,
        upload=lambda *_a, **_k: "https://cdn.example.com/s.png",
    )
    assert result["provider"] == "openai"
    assert held == ["openai"]
    assert fake.calls[0][0] == "cinematic forest"
    assert fake.calls[0][1]["model"] == "gpt-image-2"
    assert scene.status is SceneStatus.COMPLETED
    assert scene.media_url == "https://cdn.example.com/s.png"
    assert scene.generation_provider == "openai"


def test_generate_scene_media_reads_model_and_quality_from_config(monkeypatch):
    project, scene = _scene_project("openai")
    project.automation_config["image_model"] = "gpt-image-1-mini"
    project.automation_config["image_quality"] = "high"
    db = FakeDB(project, scene)
    fake = FakeProvider("openai")
    monkeypatch.setattr("app.core.generate_scene_media.get_image_provider", lambda name: fake)
    monkeypatch.setattr(
        "app.core.generate_scene_media.provider_semaphore.hold",
        lambda name, **kwargs: nullcontext(),
    )
    generate_scene_media(
        project.id,
        scene.id,
        db=db,
        upload=lambda *_a, **_k: "https://cdn.example.com/s.png",
    )
    assert fake.calls[0][1]["model"] == "gpt-image-1-mini"
    assert fake.calls[0][1]["quality"] == "high"


def test_generate_scene_media_uses_higgsfield_semaphore(monkeypatch):
    project, scene = _scene_project("higgsfield")
    db = FakeDB(project, scene)
    fake = FakeProvider("higgsfield")
    held = []
    monkeypatch.setattr("app.core.generate_scene_media.get_image_provider", lambda name: fake)
    monkeypatch.setattr(
        "app.core.generate_scene_media.provider_semaphore.hold",
        lambda name, **kwargs: held.append(name) or nullcontext(),
    )
    generate_scene_media(
        project.id,
        scene.id,
        db=db,
        upload=lambda *_a, **_k: "https://cdn.example.com/h.png",
    )
    assert held == ["higgsfield"]
    assert fake.calls[0][1]["model"] == "higgsfield-ai/soul/v2/standard"


def test_project_create_defaults_image_provider():
    payload = ProjectCreate(
        title="clip",
        source_type=SourceType.YOUTUBE_LINK,
        source_ref="https://youtu.be/x",
    )
    assert payload.image_provider == "higgsfield"
    assert payload.automation_config["image_provider"] == "higgsfield"
    assert payload.automation_config["image_model"] == "higgsfield-ai/soul/v2/standard"
    assert "image_quality" not in payload.automation_config


def test_project_create_accepts_openai_image_provider():
    payload = ProjectCreate(
        title="clip",
        source_type=SourceType.YOUTUBE_LINK,
        source_ref="https://youtu.be/x",
        image_provider="openai",
        automation_config={"auto_media": True},
    )
    assert payload.automation_config["image_provider"] == "openai"
    assert payload.automation_config["image_model"] == "gpt-image-2"
    assert payload.automation_config["image_quality"] == "medium"
    assert payload.automation_config["auto_media"] is True


def test_project_create_rejects_unknown_provider():
    with pytest.raises(ValidationError, match="higgsfield"):
        ProjectCreate(
            title="clip",
            source_type=SourceType.YOUTUBE_LINK,
            source_ref="https://youtu.be/x",
            image_provider="midjourney",
        )


def test_project_create_persists_openai_model_and_quality():
    payload = ProjectCreate(
        title="clip",
        source_type=SourceType.YOUTUBE_LINK,
        source_ref="https://youtu.be/x",
        image_provider="openai",
        automation_config={"image_model": "gpt-image-1-mini", "image_quality": "high"},
    )
    assert payload.automation_config["image_model"] == "gpt-image-1-mini"
    assert payload.automation_config["image_quality"] == "high"


def test_project_create_persists_higgsfield_model():
    payload = ProjectCreate(
        title="clip",
        source_type=SourceType.YOUTUBE_LINK,
        source_ref="https://youtu.be/x",
        image_provider="higgsfield",
        automation_config={"image_model": "higgsfield-ai/soul/v2/high", "image_quality": "high"},
    )
    assert payload.automation_config["image_model"] == "higgsfield-ai/soul/v2/high"
    assert "image_quality" not in payload.automation_config


def test_generate_scene_media_openai_edits_with_character(monkeypatch):
    from app.models.character import Character
    from app.models.enums import CharacterStatus

    project, scene = _scene_project("openai")
    cid = uuid4()
    project.automation_config["character_id"] = str(cid)
    character = SimpleNamespace(
        id=cid,
        description_prompt="heroína de casaco vermelho",
        style_id=uuid4(),
        status=CharacterStatus.APPROVED,
        base_image_url="https://cdn.example.com/base.png",
        _model=Character,
    )
    db = FakeDB(project, scene, extra={Character: character})
    fake = FakeProvider("openai")
    monkeypatch.setattr("app.core.generate_scene_media.get_image_provider", lambda name: fake)
    monkeypatch.setattr(
        "app.core.generate_scene_media.provider_semaphore.hold",
        lambda name, **kwargs: nullcontext(),
    )
    monkeypatch.setattr("app.core.generate_character.fetch_image_bytes", lambda url: b"REF")
    generate_scene_media(
        project.id,
        scene.id,
        db=db,
        upload=lambda *_a, **_k: "https://cdn.example.com/s.png",
    )
    assert fake.edits
    assert fake.edits[0][1] == b"REF"
    assert "heroína de casaco vermelho" in fake.edits[0][0]
    assert not fake.calls


def test_generate_scene_media_higgsfield_appends_character_text(monkeypatch):
    from app.models.character import Character
    from app.models.enums import CharacterStatus

    project, scene = _scene_project("higgsfield")
    cid = uuid4()
    project.automation_config["character_id"] = str(cid)
    character = SimpleNamespace(
        id=cid,
        description_prompt="heroína de casaco vermelho",
        style_id=uuid4(),
        status=CharacterStatus.APPROVED,
        base_image_url="https://cdn.example.com/base.png",
        _model=Character,
    )
    db = FakeDB(project, scene, extra={Character: character})
    fake = FakeProvider("higgsfield")
    monkeypatch.setattr("app.core.generate_scene_media.get_image_provider", lambda name: fake)
    monkeypatch.setattr(
        "app.core.generate_scene_media.provider_semaphore.hold",
        lambda name, **kwargs: nullcontext(),
    )
    generate_scene_media(
        project.id,
        scene.id,
        db=db,
        upload=lambda *_a, **_k: "https://cdn.example.com/h.png",
    )
    assert fake.calls
    assert not fake.edits
    assert "heroína de casaco vermelho" in fake.calls[0][0]
