from contextlib import nullcontext
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.generate_description import DescriptionError, generate_description
from app.core.state_machine import linear_next, parse_stage
from app.models.description import Description
from app.models.enums import DescriptionSource, ProjectStage, ProjectStatus, SourceType
from app.models.project import Project


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


def _segment(**kwargs):
    data = dict(index=0, text_original="the ocean is blue", text_translated="o mar é azul")
    data.update(kwargs)
    return SimpleNamespace(**data)


def _project(**kwargs):
    pid = kwargs.pop("id", uuid4())
    data = dict(
        id=pid,
        title="O Mar",
        source_type=SourceType.YOUTUBE_LINK,
        target_language="pt-BR",
        current_stage=ProjectStage.DESCRIPTION_STAGE,
        status=ProjectStatus.RUNNING,
        transcript_segments=[_segment()],
        descriptions=[],
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


def _copy(**kwargs):
    return {
        "text": "Um parágrafo sobre o mar. Inscreva-se para mais vídeos.",
        "tags": [f"tag {i}" for i in range(12)],
        "title": "O Mar",
    }


def test_generate_description_saves_text_tags_and_source(monkeypatch):
    project = _project()
    captured = []
    monkeypatch.setattr(
        "app.core.generate_description.provider_semaphore.hold",
        lambda name, **kwargs: nullcontext(),
    )
    monkeypatch.setattr("app.core.generate_description.advance_stage", _stub_advance(project))

    def writer(**kwargs):
        captured.append(kwargs)
        return _copy()

    result = generate_description(project.id, db=FakeDB(project), write_copy=writer)
    assert result["source"] == DescriptionSource.GENERATED.value
    assert result["advanced"] is True
    assert project.current_stage is ProjectStage.READY_TO_PUBLISH
    assert "o mar é azul" in captured[0]["transcript"]
    row = project.descriptions[0]
    assert row.text == result["text"]
    assert row.tags == result["tags"]
    assert len(row.tags) == 12
    assert row.source is DescriptionSource.GENERATED


def test_generate_description_does_not_advance_when_paused(monkeypatch):
    project = _project(status=ProjectStatus.PAUSED_FOR_REVIEW)
    monkeypatch.setattr(
        "app.core.generate_description.provider_semaphore.hold",
        lambda name, **kwargs: nullcontext(),
    )
    advanced = []
    monkeypatch.setattr(
        "app.core.generate_description.advance_stage",
        lambda *a, **k: advanced.append(True),
    )
    result = generate_description(project.id, db=FakeDB(project), write_copy=_copy)
    assert result["advanced"] is False
    assert advanced == []
    assert project.current_stage is ProjectStage.DESCRIPTION_STAGE


def test_generate_description_requires_transcript(monkeypatch):
    project = _project(transcript_segments=[])
    monkeypatch.setattr(
        "app.core.generate_description.provider_semaphore.hold",
        lambda name, **kwargs: nullcontext(),
    )
    with pytest.raises(DescriptionError, match="transcript"):
        generate_description(project.id, db=FakeDB(project), write_copy=_copy)


def test_generate_description_caps_tags_at_fifteen(monkeypatch):
    project = _project()
    monkeypatch.setattr(
        "app.core.generate_description.provider_semaphore.hold",
        lambda name, **kwargs: nullcontext(),
    )
    monkeypatch.setattr("app.core.generate_description.advance_stage", _stub_advance(project))
    payload = {
        "text": "Um parágrafo sobre o mar.",
        "tags": [f"tag {i}" for i in range(20)],
    }
    result = generate_description(
        project.id, db=FakeDB(project), write_copy=lambda **kwargs: payload
    )
    assert len(result["tags"]) == 15
    assert project.descriptions[0].tags == result["tags"]


def test_generate_description_persists_via_session_add(monkeypatch):
    project = _project(descriptions=None)
    db = FakeDB(project)
    monkeypatch.setattr(
        "app.core.generate_description.provider_semaphore.hold",
        lambda name, **kwargs: nullcontext(),
    )
    monkeypatch.setattr("app.core.generate_description.advance_stage", _stub_advance(project))
    generate_description(project.id, db=db, write_copy=_copy)
    assert isinstance(db.added[0], Description)
    assert db.added[0].source is DescriptionSource.GENERATED
    assert db.added[0].tags[0] == "tag 0"


def test_celery_task_is_registered_with_project_id():
    celery = pytest.importorskip("celery")
    _ = celery
    from app.tasks.description import generate_description as task

    assert task.name == "scenecraft.generate_description"
