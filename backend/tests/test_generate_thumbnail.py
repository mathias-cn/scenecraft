from contextlib import nullcontext
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.generate_thumbnail import (
    ThumbnailError,
    generate_thumbnail,
    project_transcript_text,
    thumbnail_size_for,
)
from app.core.state_machine import linear_next, parse_stage
from app.models.enums import ProjectStage, SourceType, ThumbnailSource
from app.models.project import Project
from app.models.thumbnail import Thumbnail
from app.providers.image_provider import ImageResult


class FakeDB:
    def __init__(self, project):
        self.project = project
        self.added = []
        self.commits = 0

    def get(self, model, pid):
        if model is Project and self.project.id == pid:
            return self.project
        return None

    def add(self, obj):
        self.added.append(obj)

    def flush(self):
        return None

    def commit(self):
        self.commits += 1

    def rollback(self):
        return None

    def close(self):
        return None


class FakeProvider:
    def __init__(self):
        self.calls = []

    def generate_image(self, prompt, **kwargs):
        self.calls.append((prompt, kwargs))
        return ImageResult(image_bytes=b"PNGTHUMB", cost_usd=0.041)


def _segment(**kwargs):
    data = dict(index=0, text_original="hello forest", text_translated=None)
    data.update(kwargs)
    return SimpleNamespace(**data)


def _project(provider="openai", **kwargs):
    pid = kwargs.pop("id", uuid4())
    config = {
        "image_provider": provider,
        "image_model": "gpt-image-2" if provider == "openai" else "higgsfield-ai/soul/v2/standard",
        "image_quality": "medium",
    }
    config.update(kwargs.pop("automation_config", {}))
    data = dict(
        id=pid,
        title="Forest walk",
        source_type=SourceType.YOUTUBE_LINK,
        target_language="pt-BR",
        automation_config=config,
        current_stage=ProjectStage.THUMBNAIL_STAGE,
        transcript_segments=[_segment()],
        thumbnails=[],
    )
    data.update(kwargs)
    data["id"] = pid
    return SimpleNamespace(**data)


def _stub_advance(project):
    def fake_advance(_pid, stage, db=None):
        nxt = linear_next(parse_stage(stage))
        project.current_stage = nxt
        return SimpleNamespace(to_stage=nxt)

    return fake_advance


def test_thumbnail_size_for_provider():
    assert thumbnail_size_for("openai") == "1536x1024"
    assert thumbnail_size_for("higgsfield") == "1280x720"


def test_project_transcript_text_prefers_translation():
    project = _project(
        transcript_segments=[
            _segment(index=1, text_original="there", text_translated="lá"),
            _segment(index=0, text_original="hello", text_translated="olá"),
        ]
    )
    assert project_transcript_text(project) == "olá lá"


def test_generate_thumbnail_uses_openai_from_config(monkeypatch):
    project = _project("openai")
    fake = FakeProvider()
    monkeypatch.setattr("app.core.generate_thumbnail.get_image_provider", lambda name: fake)
    monkeypatch.setattr(
        "app.core.generate_thumbnail.provider_semaphore.hold",
        lambda name, **kwargs: nullcontext(),
    )
    monkeypatch.setattr("app.core.generate_thumbnail.advance_stage", _stub_advance(project))
    summaries = []
    prompts = []

    result = generate_thumbnail(
        project.id,
        db=FakeDB(project),
        summarize=lambda **kwargs: summaries.append(kwargs) or "A walk through a misty forest.",
        prompt_from_summary=lambda **kwargs: prompts.append(kwargs) or "dramatic forest thumbnail",
        upload=lambda *_a, **_k: "https://cdn.example.com/thumbnail.png",
        image_client=fake,
    )
    assert result["provider"] == "openai"
    assert result["source"] == ThumbnailSource.GENERATED.value
    assert result["file_url"] == "https://cdn.example.com/thumbnail.png"
    assert result["size"] == "1536x1024"
    assert result["advanced"] is True
    assert project.current_stage is ProjectStage.DESCRIPTION_STAGE
    assert summaries[0]["transcript"] == "hello forest"
    assert prompts[0]["summary"] == "A walk through a misty forest."
    assert fake.calls[0][0] == "dramatic forest thumbnail"
    assert fake.calls[0][1]["model"] == "gpt-image-2"
    assert fake.calls[0][1]["quality"] == "medium"
    assert fake.calls[0][1]["size"] == "1536x1024"
    thumb = project.thumbnails[0]
    assert thumb.source is ThumbnailSource.GENERATED
    assert thumb.file_url == result["file_url"]


def test_generate_thumbnail_uses_higgsfield_provider(monkeypatch):
    project = _project("higgsfield")
    fake = FakeProvider()
    monkeypatch.setattr(
        "app.core.generate_thumbnail.provider_semaphore.hold",
        lambda name, **kwargs: nullcontext(),
    )
    monkeypatch.setattr("app.core.generate_thumbnail.advance_stage", _stub_advance(project))
    generate_thumbnail(
        project.id,
        db=FakeDB(project),
        summarize=lambda **_k: "resumo",
        prompt_from_summary=lambda **_k: "bold youtube thumbnail of a forest",
        upload=lambda *_a, **_k: "https://cdn.example.com/thumbnail.png",
        image_client=fake,
    )
    assert fake.calls[0][1]["model"] == "higgsfield-ai/soul/v2/standard"
    assert fake.calls[0][1]["size"] == "1280x720"
    assert "quality" not in fake.calls[0][1]


def test_generate_thumbnail_requires_transcript(monkeypatch):
    project = _project(transcript_segments=[])
    monkeypatch.setattr(
        "app.core.generate_thumbnail.provider_semaphore.hold",
        lambda name, **kwargs: nullcontext(),
    )
    with pytest.raises(ThumbnailError, match="transcript"):
        generate_thumbnail(
            project.id,
            db=FakeDB(project),
            summarize=lambda **_k: "x",
            prompt_from_summary=lambda **_k: "y",
            upload=lambda *_a, **_k: "https://cdn.example.com/x.png",
            image_client=FakeProvider(),
        )


def test_generate_thumbnail_persists_via_session_add(monkeypatch):
    project = _project("openai", thumbnails=None)
    db = FakeDB(project)
    monkeypatch.setattr(
        "app.core.generate_thumbnail.provider_semaphore.hold",
        lambda name, **kwargs: nullcontext(),
    )
    monkeypatch.setattr("app.core.generate_thumbnail.advance_stage", _stub_advance(project))
    generate_thumbnail(
        project.id,
        db=db,
        summarize=lambda **_k: "resumo",
        prompt_from_summary=lambda **_k: "prompt",
        upload=lambda *_a, **_k: "https://cdn.example.com/thumbnail.png",
        image_client=FakeProvider(),
    )
    assert len(db.added) == 1
    assert isinstance(db.added[0], Thumbnail)
    assert db.added[0].source is ThumbnailSource.GENERATED


def test_celery_task_is_registered_with_project_id():
    celery = pytest.importorskip("celery")
    _ = celery
    from app.tasks.thumbnail import generate_thumbnail as task

    assert task.name == "scenecraft.generate_thumbnail"
