from io import BytesIO
from types import SimpleNamespace
from uuid import uuid4

from app.core.generate_audio import generate_project_audio, narration_script
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


def test_narration_script_prefers_translation():
    project = SimpleNamespace(
        transcript_segments=[
            SimpleNamespace(index=1, text_original="hello", text_translated="olá"),
            SimpleNamespace(index=0, text_original="there", text_translated=None),
        ]
    )
    assert narration_script(project) == "there olá"


def test_generate_project_audio_uploads_track(monkeypatch):
    pid = uuid4()
    project = SimpleNamespace(
        id=pid,
        source_type=SourceType.YOUTUBE_LINK,
        automation_config={},
        transcript_segments=[SimpleNamespace(index=0, text_original="olá mundo", text_translated=None)],
        audio_tracks=[],
        video_assemblies=[],
        video_assembly=None,
    )
    monkeypatch.setattr("app.providers.elevenlabs.synthesize", lambda **_k: b"ID3audio")
    monkeypatch.setattr(
        "app.core.generate_audio.provider_semaphore.hold",
        lambda *_a, **_k: __import__("contextlib").nullcontext(),
    )
    uploaded = []

    def fake_upload(fileobj, project_id, filename, content_type=None):
        uploaded.append((fileobj, project_id, filename, content_type))
        assert isinstance(fileobj, BytesIO)
        return "https://cdn.example.com/narration.mp3"

    db = FakeDB(project)
    result = generate_project_audio(project.id, voice_id="Rachel", db=db, upload=fake_upload)
    assert result["audio_url"] == "https://cdn.example.com/narration.mp3"
    assert result["source"] == AudioTrackSource.GENERATED.value
    assert db.added[0].voice_id == "Rachel"
    assert uploaded[0][2] == "narration.mp3"
    assert project.video_assemblies[0].render_config["audio_source"] == "generated"
