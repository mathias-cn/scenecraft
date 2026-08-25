from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.source_downloader import SourceDownloadError, load_audio, load_uploaded_source
from app.models.enums import ProjectStage, SourceType
from app.providers.transcription_client import Segment, TranscriptionError
from app.core.transcribe_project import transcribe_project


class RecordingDB:
    def __init__(self, project):
        self.project = project
        self.added: list = []
        self.executed: list = []
        self.commits = 0
        self.rollbacks = 0

    def get(self, _model, _pid):
        return self.project

    def add(self, obj):
        self.added.append(obj)

    def execute(self, stmt):
        self.executed.append(stmt)
        return SimpleNamespace(rowcount=0)

    def flush(self):
        return None

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        return None


def _project(**kwargs):
    data = dict(
        id=uuid4(),
        source_type=SourceType.UPLOAD_AUDIO,
        source_ref="s3://bucket/clip.mp3",
        target_language="pt-BR",
        current_stage=ProjectStage.TRANSCRIBING,
    )
    data.update(kwargs)
    return SimpleNamespace(**data)


def test_load_audio_uses_local_file_for_uploads(tmp_path):
    audio = tmp_path / "voice.wav"
    audio.write_bytes(b"RIFF")
    project = _project(source_type=SourceType.UPLOAD_AUDIO, source_ref=str(audio))
    assert load_audio(project, tmp_path / "out") == audio


def test_load_audio_downloads_uploaded_object(monkeypatch, tmp_path):
    dest = tmp_path / "dl"

    def fake_download(url, local_path):
        path = Path(local_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"data")
        return path

    monkeypatch.setattr("app.core.source_downloader.download_stored_source", fake_download)
    result = load_uploaded_source("https://r2.example/p/clip.mp4", dest)
    assert result == dest / "source.mp4"
    assert result.read_bytes() == b"data"


def test_load_audio_youtube_uses_downloader(monkeypatch, tmp_path):
    audio = tmp_path / "yt.mp3"
    audio.write_bytes(b"mp3")
    called: list[str] = []

    def fake_yt(url, dest_dir):
        called.append(url)
        return audio

    monkeypatch.setattr("app.core.source_downloader.download_youtube_audio", fake_yt)
    project = _project(source_type=SourceType.YOUTUBE_LINK, source_ref="https://youtu.be/abc")
    assert load_audio(project, tmp_path) == audio
    assert called == ["https://youtu.be/abc"]


def test_load_audio_rejects_empty_source():
    with pytest.raises(SourceDownloadError, match="source_ref"):
        load_audio(_project(source_ref=""), Path("/tmp"))


def test_transcribe_project_saves_segments_and_advances(monkeypatch, tmp_path):
    audio = tmp_path / "a.wav"
    audio.write_bytes(b"x")
    project = _project(source_ref=str(audio))
    db = RecordingDB(project)
    monkeypatch.setattr("app.core.transcribe_project.load_audio", lambda _project, _dest: audio)
    monkeypatch.setattr(
        "app.core.transcribe_project.transcription_client.transcribe",
        lambda _path, language="auto": [
            Segment(start_ms=0, end_ms=800, text="olá mundo", language="pt"),
            Segment(start_ms=800, end_ms=1500, text="tudo bem", language="pt"),
        ],
    )
    advanced: list[tuple] = []
    monkeypatch.setattr(
        "app.core.transcribe_project.advance_stage",
        lambda pid, stage, db=None: advanced.append((pid, stage, db)),
    )

    result = transcribe_project(project.id, db=db)

    assert result["segment_count"] == 2
    assert result["language"] == "pt"
    assert len(db.executed) == 1
    assert [row.index for row in db.added] == [0, 1]
    assert db.added[0].text_original == "olá mundo"
    assert db.added[0].start_ms == 0
    assert db.added[0].end_ms == 800
    assert db.added[1].language == "pt"
    assert advanced == [(project.id, "TRANSCRIBING", db)]


def test_transcribe_project_uses_target_language_when_undetected(monkeypatch, tmp_path):
    audio = tmp_path / "a.wav"
    audio.write_bytes(b"x")
    project = _project(source_ref=str(audio), target_language="es")
    db = RecordingDB(project)
    monkeypatch.setattr("app.core.transcribe_project.load_audio", lambda *_a: audio)
    monkeypatch.setattr(
        "app.core.transcribe_project.transcription_client.transcribe",
        lambda *_a, **_k: [Segment(start_ms=0, end_ms=10, text="hola")],
    )
    monkeypatch.setattr("app.core.transcribe_project.advance_stage", lambda *_a, **_k: None)
    result = transcribe_project(project.id, db=db)
    assert result["language"] == "es"
    assert db.added[0].language == "es"


def test_transcribe_project_empty_transcript_does_not_advance(monkeypatch, tmp_path):
    audio = tmp_path / "a.wav"
    audio.write_bytes(b"x")
    project = _project()
    db = RecordingDB(project)
    monkeypatch.setattr("app.core.transcribe_project.load_audio", lambda *_a: audio)
    monkeypatch.setattr("app.core.transcribe_project.transcription_client.transcribe", lambda *_a, **_k: [])
    advanced: list = []
    monkeypatch.setattr("app.core.transcribe_project.advance_stage", lambda *_a, **_k: advanced.append(1))
    with pytest.raises(TranscriptionError, match="vazia"):
        transcribe_project(project.id, db=db)
    assert advanced == []
    assert db.rollbacks == 1
    assert db.added == []


def test_celery_task_is_registered_with_project_id_signature():
    celery = pytest.importorskip("celery")
    _ = celery
    from app.tasks.transcribe import transcribe_project_task

    assert transcribe_project_task.name == "scenecraft.transcribe_project"
