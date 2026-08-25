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
    def __init__(self, project, scene):
        self.project = project
        self.scene = scene
        self.commits = 0
        self.rollbacks = 0

    def get(self, model, pid):
        if model is Project:
            return self.project if self.project.id == pid else None
        if model is Scene:
            return self.scene if self.scene.id == pid else None
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

    def generate_image(self, prompt, **kwargs):
        self.calls.append((prompt, kwargs))
        return ImageResult(image_bytes=b"PNG", cost_usd=0.041)


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


def test_project_create_accepts_openai_image_provider():
    payload = ProjectCreate(
        title="clip",
        source_type=SourceType.YOUTUBE_LINK,
        source_ref="https://youtu.be/x",
        image_provider="openai",
        automation_config={"auto_media": True},
    )
    assert payload.automation_config["image_provider"] == "openai"
    assert payload.automation_config["auto_media"] is True


def test_project_create_rejects_unknown_provider():
    with pytest.raises(ValidationError, match="higgsfield"):
        ProjectCreate(
            title="clip",
            source_type=SourceType.YOUTUBE_LINK,
            source_ref="https://youtu.be/x",
            image_provider="midjourney",
        )
