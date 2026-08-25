from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.retranscribe_align import retranscribe_and_align
from app.core.state_machine import linear_next, parse_stage
from app.models.enums import AudioTrackSource, MediaType, ProjectStage, SceneStatus, SourceType
from app.models.project import Project
from app.providers.transcription_client import Segment


class FakeDB:
    def __init__(self, project):
        self.project = project
        self.commits = 0
        self.rollbacks = 0

    def get(self, model, pid):
        if model is Project and self.project.id == pid:
            return self.project
        return None

    def flush(self):
        return None

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        return None

    def add(self, _obj):
        return None


def _scene(pid, **kwargs):
    data = dict(
        id=uuid4(),
        project_id=pid,
        index=0,
        start_ms=0,
        end_ms=800,
        source_segment_ids=[0],
        visual_prompt="wide shot of a street",
        media_type=MediaType.IMAGE,
        status=SceneStatus.PENDING,
    )
    data.update(kwargs)
    return SimpleNamespace(**data)


def _project(pid, scene, **kwargs):
    data = dict(
        id=pid,
        source_type=SourceType.YOUTUBE_LINK,
        target_language="original",
        current_stage=ProjectStage.AUDIO_STAGE,
        automation_config={"audio_generation_mode": "elevenlabs"},
        scenes=[scene],
        transcript_segments=[
            SimpleNamespace(
                index=0,
                start_ms=0,
                end_ms=800,
                text_original="hello there friend",
                text_translated=None,
            )
        ],
        audio_tracks=[
            SimpleNamespace(
                source=AudioTrackSource.GENERATED,
                file_url="https://cdn.example.com/narration.mp3",
                provider="elevenlabs",
            )
        ],
        video_assemblies=[],
        video_assembly=None,
    )
    data.update(kwargs)
    return SimpleNamespace(**data)


def _stub_advance(project):
    def fake_advance(_pid, stage, db=None):
        current = parse_stage(stage)
        nxt = linear_next(current)
        project.current_stage = nxt
        return SimpleNamespace(to_stage=nxt)

    return fake_advance


def test_retranscribe_and_align_updates_scene_times(monkeypatch, tmp_path):
    pid = uuid4()
    scene = _scene(pid)
    project = _project(pid, scene)
    audio = tmp_path / "n.mp3"
    audio.write_bytes(b"mp3")
    monkeypatch.setattr("app.core.retranscribe_align._download_audio", lambda *_a, **_k: audio)
    monkeypatch.setattr(
        "app.providers.transcription_client.transcribe",
        lambda *_a, **_k: [Segment(start_ms=0, end_ms=1200, text="hello there friend")],
    )
    monkeypatch.setattr(
        "app.core.retranscribe_align.provider_semaphore.hold",
        lambda *_a, **_k: __import__("contextlib").nullcontext(),
    )
    monkeypatch.setattr("app.core.retranscribe_align.advance_stage", _stub_advance(project))
    db = FakeDB(project)
    result = retranscribe_and_align(project.id, db=db)
    assert result["scene_count"] == 1
    assert result["skipped"] is False
    assert result["advanced"] is True
    assert scene.start_ms == 0
    assert scene.end_ms == 1200
    assert project.current_stage is ProjectStage.RENDERING
    assert project.video_assemblies[0].render_config["audio_url"] == project.audio_tracks[0].file_url


def test_retranscribe_and_align_skips_reuse_original_audio(monkeypatch):
    pid = uuid4()
    scene = _scene(pid, start_ms=0, end_ms=800)
    project = _project(
        pid,
        scene,
        source_type=SourceType.UPLOAD_AUDIO,
        automation_config={"reuse_original_audio": True},
    )
    called = []
    monkeypatch.setattr(
        "app.providers.transcription_client.transcribe",
        lambda *_a, **_k: called.append(True) or [],
    )
    monkeypatch.setattr("app.core.retranscribe_align.advance_stage", _stub_advance(project))
    result = retranscribe_and_align(project.id, db=FakeDB(project))
    assert result["skipped"] is True
    assert result["reason"] == "reuse_original_audio"
    assert called == []
    assert scene.start_ms == 0
    assert scene.end_ms == 800
    assert project.current_stage is ProjectStage.AUDIO_STAGE


def test_celery_task_is_registered_with_project_id_signature():
    celery = pytest.importorskip("celery")
    _ = celery
    from app.tasks.audio_gen import retranscribe_and_align as task

    assert task.name == "scenecraft.retranscribe_and_align"

