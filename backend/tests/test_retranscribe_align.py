from types import SimpleNamespace
from uuid import uuid4

from app.core.retranscribe_align import retranscribe_and_align
from app.models.enums import AudioTrackSource, MediaType, SceneStatus, SourceType
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


def test_retranscribe_and_align_updates_scene_times(monkeypatch, tmp_path):
    pid = uuid4()
    scene = SimpleNamespace(
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
    segment = SimpleNamespace(
        index=0,
        start_ms=0,
        end_ms=800,
        text_original="hello there friend",
        text_translated=None,
    )
    track = SimpleNamespace(
        source=AudioTrackSource.GENERATED,
        file_url="https://cdn.example.com/narration.mp3",
        provider="elevenlabs",
    )
    project = SimpleNamespace(
        id=pid,
        source_type=SourceType.YOUTUBE_LINK,
        automation_config={},
        scenes=[scene],
        transcript_segments=[segment],
        audio_tracks=[track],
        video_assemblies=[],
        video_assembly=None,
    )
    audio = tmp_path / "n.mp3"
    audio.write_bytes(b"mp3")
    monkeypatch.setattr("app.core.retranscribe_align._download_audio", lambda *_a, **_k: audio)
    monkeypatch.setattr(
        "app.providers.transcription_client.transcribe",
        lambda *_a, **_k: [
            Segment(start_ms=0, end_ms=1200, text="hello there friend"),
        ],
    )
    db = FakeDB(project)
    result = retranscribe_and_align(project.id, db=db)
    assert result["scene_count"] == 1
    assert scene.start_ms == 0
    assert scene.end_ms == 1200
    assert project.video_assemblies[0].render_config["audio_url"] == track.file_url
