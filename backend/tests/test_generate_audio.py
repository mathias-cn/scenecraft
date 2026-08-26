from io import BytesIO
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.generate_audio import generate_audio, generate_project_audio, narration_script
from app.core.project_audio import ProjectAudioError
from app.models.enums import AudioTrackSource, SourceType
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


def _project(**kwargs):
    data = dict(
        id=uuid4(),
        source_type=SourceType.YOUTUBE_LINK,
        target_language="pt-BR",
        automation_config={"audio_generation_mode": "elevenlabs"},
        transcript_segments=[
            SimpleNamespace(index=0, text_original="olá mundo", text_translated=None),
        ],
        audio_tracks=[],
        video_assemblies=[],
        video_assembly=None,
    )
    data.update(kwargs)
    return SimpleNamespace(**data)


def test_narration_script_uses_translation_for_target_language():
    project = SimpleNamespace(
        target_language="pt-BR",
        transcript_segments=[
            SimpleNamespace(index=1, text_original="hello", text_translated="olá"),
            SimpleNamespace(index=0, text_original="there", text_translated=None),
        ],
    )
    assert narration_script(project) == "there olá"


def test_narration_script_uses_original_when_target_is_original():
    project = SimpleNamespace(
        target_language="original",
        transcript_segments=[
            SimpleNamespace(index=0, text_original="hello", text_translated="olá"),
            SimpleNamespace(index=1, text_original="there", text_translated="lá"),
        ],
    )
    assert narration_script(project) == "hello there"


def test_generate_audio_uploads_track_and_timestamps(monkeypatch):
    project = _project()
    monkeypatch.setattr(
        "app.core.generate_audio.provider_semaphore.hold",
        lambda *_a, **_k: __import__("contextlib").nullcontext(),
    )
    uploaded = []

    def fake_upload(fileobj, project_id, filename, content_type=None):
        uploaded.append((fileobj, project_id, filename, content_type))
        assert isinstance(fileobj, BytesIO)
        return "https://cdn.example.com/narration.mp3"

    stamps = [{"word": "olá", "start_ms": 0, "end_ms": 320}]
    db = FakeDB(project)
    result = generate_audio(
        project.id,
        "Rachel",
        db=db,
        upload=fake_upload,
        speak=lambda text, voice_id: (b"ID3audio", stamps),
    )
    assert result["audio_url"] == "https://cdn.example.com/narration.mp3"
    assert result["source"] == AudioTrackSource.GENERATED.value
    assert result["word_timestamps"] == stamps
    assert db.added[0].voice_id == "Rachel"
    assert db.added[0].source is AudioTrackSource.GENERATED
    assert db.added[0].word_timestamps == stamps
    assert db.added[0].cost_usd is not None
    assert db.added[0].cost_usd > 0
    assert result["cost_usd"] == float(db.added[0].cost_usd)
    assert uploaded[0][2] == "narration.mp3"
    assert project.video_assemblies[0].render_config["audio_source"] == "generated"


def test_generate_audio_sends_translated_script_to_elevenlabs(monkeypatch):
    project = _project(
        target_language="pt-BR",
        transcript_segments=[
            SimpleNamespace(index=0, text_original="hello", text_translated="olá"),
            SimpleNamespace(index=1, text_original="world", text_translated="mundo"),
        ],
    )
    monkeypatch.setattr(
        "app.core.generate_audio.provider_semaphore.hold",
        lambda *_a, **_k: __import__("contextlib").nullcontext(),
    )
    seen = []

    def fake_speak(text, voice_id):
        seen.append((text, voice_id))
        return b"ID3", []

    generate_audio(
        project.id,
        "voice-1",
        db=FakeDB(project),
        upload=lambda *_a, **_k: "https://cdn.example.com/n.mp3",
        speak=fake_speak,
    )
    assert seen == [("olá mundo", "voice-1")]


def test_generate_project_audio_alias_still_works(monkeypatch):
    project = _project()
    monkeypatch.setattr(
        "app.core.generate_audio.provider_semaphore.hold",
        lambda *_a, **_k: __import__("contextlib").nullcontext(),
    )
    result = generate_project_audio(
        project.id,
        voice_id="Adam",
        db=FakeDB(project),
        upload=lambda *_a, **_k: "https://cdn.example.com/n.mp3",
        speak=lambda *_a: (b"ID3", []),
    )
    assert result["voice_id"] == "Adam"


def test_generate_audio_rejects_non_elevenlabs_mode():
    project = _project(automation_config={"audio_generation_mode": "user_upload"})
    with pytest.raises(ProjectAudioError, match="elevenlabs"):
        generate_audio(
            project.id,
            "Rachel",
            db=FakeDB(project),
            upload=lambda *_a, **_k: "https://cdn.example.com/n.mp3",
            speak=lambda *_a: (b"ID3", []),
        )


def test_celery_task_is_registered_with_project_and_voice_ids():
    celery = pytest.importorskip("celery")
    _ = celery
    from app.tasks.audio_gen import generate_audio as task

    assert task.name == "scenecraft.generate_audio"
