from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.source_downloader import SourceDownloadError, load_audio, load_uploaded_source
from app.models.enums import AudioTrackSource, ProjectStage, SourceType
from app.providers.transcription_client import Segment, TranscriptionError
from app.core.transcribe_project import transcribe_project


@pytest.fixture(autouse=True)
def stub_original_audio_persist(monkeypatch):
    monkeypatch.setattr(
        "app.core.transcribe_project.persist_original_audio",
        lambda *_a, **_k: SimpleNamespace(cost_usd=None),
    )


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

    monkeypatch.setattr("app.core.source_downloader.download_from_youtube", fake_yt)
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
    assert result["translated"] is False
    assert db.added[0].text_translated is None
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
    assert result["translated"] is False
    assert db.added[0].language == "es"
    assert db.added[0].text_translated is None


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


def test_transcribe_project_translates_when_target_differs(monkeypatch, tmp_path):
    audio = tmp_path / "a.wav"
    audio.write_bytes(b"x")
    project = _project(source_ref=str(audio), target_language="pt-BR")
    db = RecordingDB(project)
    monkeypatch.setattr("app.core.transcribe_project.load_audio", lambda *_a: audio)
    monkeypatch.setattr(
        "app.core.transcribe_project.transcription_client.transcribe",
        lambda *_a, **_k: [
            Segment(start_ms=100, end_ms=400, text="hello there", language="en"),
            Segment(start_ms=400, end_ms=900, text="how are you", language="en"),
        ],
    )
    captured: list[list] = []

    def fake_translate(payload, *, target_language, batch_size=20):
        captured.append((list(payload), target_language, batch_size))
        return [
            {
                "index": item["index"],
                "start_ms": 0,
                "end_ms": 0,
                "text_original": item["text"],
                "text_translated": f"pt:{item['text']}",
            }
            for item in payload
        ]

    monkeypatch.setattr("app.core.transcribe_project.llm_client.translate_segments", fake_translate)
    monkeypatch.setattr("app.core.transcribe_project.advance_stage", lambda *_a, **_k: None)

    result = transcribe_project(project.id, db=db)

    assert result["translated"] is True
    assert result["language"] == "en"
    assert captured[0][1] == "pt-BR"
    assert [row.start_ms for row in db.added] == [100, 400]
    assert [row.end_ms for row in db.added] == [400, 900]
    assert db.added[0].text_original == "hello there"
    assert db.added[0].text_translated == "pt:hello there"
    assert db.added[1].text_translated == "pt:how are you"


def test_transcribe_project_skips_translation_for_original_target(monkeypatch, tmp_path):
    audio = tmp_path / "a.wav"
    audio.write_bytes(b"x")
    project = _project(source_ref=str(audio), target_language="original")
    db = RecordingDB(project)
    called = []
    monkeypatch.setattr("app.core.transcribe_project.load_audio", lambda *_a: audio)
    monkeypatch.setattr(
        "app.core.transcribe_project.transcription_client.transcribe",
        lambda *_a, **_k: [Segment(start_ms=0, end_ms=10, text="hello", language="en")],
    )
    monkeypatch.setattr(
        "app.core.transcribe_project.llm_client.translate_segments",
        lambda *_a, **_k: called.append(1) or [],
    )
    monkeypatch.setattr("app.core.transcribe_project.advance_stage", lambda *_a, **_k: None)
    result = transcribe_project(project.id, db=db)
    assert result["translated"] is False
    assert called == []
    assert db.added[0].text_translated is None


def test_transcribe_project_uploads_original_before_temp_cleanup(monkeypatch, tmp_path):
    audio = tmp_path / "youtube_audio.mp3"
    audio.write_bytes(b"ID3")
    project = _project(
        source_type=SourceType.YOUTUBE_LINK,
        source_ref="https://youtu.be/abc",
        audio_tracks=[],
    )
    db = RecordingDB(project)
    persisted: list[tuple] = []

    def fake_persist(session, proj, path):
        local = Path(path)
        assert local.is_file(), "upload deve ocorrer enquanto o tmp ainda existe"
        persisted.append((session, proj.id, local))
        return SimpleNamespace(cost_usd=None, file_url=f"{proj.id}/original.mp3")

    monkeypatch.setattr("app.core.transcribe_project.persist_original_audio", fake_persist)
    monkeypatch.setattr("app.core.transcribe_project.load_audio", lambda *_a: audio)
    monkeypatch.setattr(
        "app.core.transcribe_project.transcription_client.transcribe",
        lambda *_a, **_k: [Segment(start_ms=0, end_ms=10, text="hello", language="en")],
    )
    monkeypatch.setattr("app.core.transcribe_project.advance_stage", lambda *_a, **_k: None)

    transcribe_project(project.id, db=db)

    assert len(persisted) == 1
    assert persisted[0][0] is db
    assert persisted[0][1] == project.id
    assert persisted[0][2] == audio


def test_persist_original_audio_uploads_object_key_and_records_track(monkeypatch, tmp_path):
    from app.core.project_audio import persist_original_audio

    audio = tmp_path / "youtube_audio.wav"
    audio.write_bytes(b"RIFF")
    project = SimpleNamespace(id=uuid4(), audio_tracks=[])
    added: list = []
    session = SimpleNamespace(add=added.append)
    uploads: list[tuple[str, str, str]] = []

    def fake_upload(local_path, project_id, filename):
        uploads.append((local_path, project_id, filename))
        return f"{project_id}/{filename}"

    monkeypatch.setattr("app.storage.upload_file", fake_upload)
    track = persist_original_audio(session, project, audio)

    assert uploads == [(str(audio), str(project.id), "original.wav")]
    assert track.source is AudioTrackSource.ORIGINAL
    assert track.file_url == f"{project.id}/original.wav"
    assert added == [track]
    assert project.audio_tracks == [track]


def test_persist_original_audio_reuses_existing_original_track(monkeypatch, tmp_path):
    from app.core.project_audio import persist_original_audio

    existing = SimpleNamespace(
        source=AudioTrackSource.ORIGINAL,
        file_url=f"{uuid4()}/original.mp3",
    )
    project = SimpleNamespace(id=uuid4(), audio_tracks=[existing])
    session = SimpleNamespace(add=lambda *_a: (_ for _ in ()).throw(AssertionError("não deve recriar")))
    monkeypatch.setattr(
        "app.storage.upload_file",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("não deve reenviar")),
    )
    assert persist_original_audio(session, project, tmp_path / "a.mp3") is existing


def test_needs_translation_compares_language_codes():
    from app.core.transcribe_project import needs_translation

    assert needs_translation("en", "pt-BR") is True
    assert needs_translation("pt", "pt-BR") is False
    assert needs_translation("en", "original") is False
    assert needs_translation("", "pt") is False


def test_celery_task_is_registered_with_project_id_signature():
    celery = pytest.importorskip("celery")
    _ = celery
    from app.tasks.transcribe import transcribe_project_task

    assert transcribe_project_task.name == "scenecraft.transcribe_project"


def test_record_whisper_cost_uses_audio_duration(monkeypatch):
    from app.core.transcribe_project import record_whisper_cost
    from app.providers.pricing import WHISPER_USD_PER_MINUTE

    monkeypatch.setattr("app.core.plan_scenes.ffprobe_duration_ms", lambda _path: 60_000)
    track = SimpleNamespace(cost_usd=None)
    record_whisper_cost(track, "clip.mp3", [])
    assert track.cost_usd == WHISPER_USD_PER_MINUTE


def test_whisper_duration_falls_back_to_last_segment(monkeypatch):
    from app.core.transcribe_project import whisper_duration_ms

    def boom(_path):
        raise RuntimeError("ffprobe indisponível")

    monkeypatch.setattr("app.core.plan_scenes.ffprobe_duration_ms", boom)
    duration = whisper_duration_ms(
        "clip.mp3",
        [Segment(start_ms=0, end_ms=1500, text="olá", language="pt")],
    )
    assert duration == 1500
