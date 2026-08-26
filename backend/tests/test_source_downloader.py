from pathlib import Path
from types import SimpleNamespace

import pytest

from app.core.source_downloader import (
    YoutubeDownloadError,
    classify_youtube_error,
    download_from_youtube,
)


def _install_yt_dlp(monkeypatch, ydl_cls, error_cls=Exception):
    import sys

    utils = SimpleNamespace(DownloadError=error_cls, ExtractorError=error_cls)
    monkeypatch.setitem(sys.modules, "yt_dlp", SimpleNamespace(YoutubeDL=ydl_cls, utils=utils))
    monkeypatch.setitem(sys.modules, "yt_dlp.utils", utils)


class FakeYDL:
    def __init__(self, opts):
        self.opts = opts

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def download(self, urls):
        dest = Path(str(self.opts["outtmpl"]).replace(".%(ext)s", ".mp3"))
        dest.write_bytes(b"ID3")
        self.downloaded = urls


class Boom(Exception):
    pass


class FailingYDL:
    def __init__(self, _opts):
        self.message = "ERROR: Private video"

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def download(self, _urls):
        raise Boom("ERROR: Private video")


def test_download_from_youtube_rejects_non_youtube_url():
    with pytest.raises(YoutubeDownloadError, match="link válido") as exc_info:
        download_from_youtube("https://vimeo.com/123")
    assert exc_info.value.code == "youtube_invalid_url"
    assert exc_info.value.ui_message == str(exc_info.value)


def test_download_from_youtube_rejects_empty_url():
    with pytest.raises(YoutubeDownloadError, match="Informe um link") as exc_info:
        download_from_youtube("  ")
    assert exc_info.value.code == "youtube_invalid_url"


def test_download_from_youtube_writes_mp3(monkeypatch, tmp_path):
    _install_yt_dlp(monkeypatch, FakeYDL)
    path = download_from_youtube("https://youtu.be/abc123", dest_dir=tmp_path)
    assert path == tmp_path / "youtube_audio.mp3"
    assert path.read_bytes() == b"ID3"


def test_download_from_youtube_does_not_override_player_clients(monkeypatch, tmp_path):
    seen: list[dict] = []

    class CaptureYDL(FakeYDL):
        def __init__(self, opts):
            seen.append(opts)
            super().__init__(opts)

    _install_yt_dlp(monkeypatch, CaptureYDL)
    download_from_youtube("https://youtu.be/abc123", dest_dir=tmp_path)
    assert seen, "YoutubeDL should be constructed once"
    opts = seen[0]
    youtube_args = (opts.get("extractor_args") or {}).get("youtube") or {}
    assert "player_client" not in youtube_args
    assert str(opts["impersonate"]).startswith("chrome")


@pytest.mark.parametrize(
    ("raw", "code", "snippet"),
    [
        ("ERROR: Private video. Sign in if you've been granted access", "youtube_private", "privado"),
        ("ERROR: This video has been removed by the uploader", "youtube_removed", "removido"),
        ("ERROR: Video unavailable", "youtube_unavailable", "indisponível"),
        ("This video is not available in your country", "youtube_geo_blocked", "região"),
        ("Sign in to confirm your age", "youtube_age_restricted", "idade"),
        ("This video is members-only", "youtube_members_only", "membros"),
        ("The uploader has not made this video available in your country", "youtube_geo_blocked", "região"),
        (
            "WARNING: [youtube] nsig extraction failed: Some formats may be missing. "
            "ERROR: [youtube] Requested format is not available. Only images are available for download",
            "youtube_extractor_outdated",
            "yt-dlp",
        ),
        ("ERROR: [youtube] Requested format is not available", "youtube_extractor_outdated", "formato"),
        ("ERROR: Only images are available for download", "youtube_extractor_outdated", "yt-dlp"),
        (
            "ERROR: unable to download video webpage: HTTP Error 403: Forbidden",
            "youtube_blocked",
            "bloqueou",
        ),
        ("ERROR: [youtube] abc: HTTP Error 403: Forbidden", "youtube_blocked", "servidor"),
        ("ERROR: There is a PO Token required for this client", "youtube_blocked", "bloqueou"),
        ("Sign in to confirm you're not a bot", "youtube_blocked", "bloqueou"),
    ],
)
def test_classify_youtube_error_messages_are_ui_ready(raw: str, code: str, snippet: str):
    err = classify_youtube_error(RuntimeError(raw))
    assert isinstance(err, YoutubeDownloadError)
    assert err.code == code
    assert snippet in err.ui_message.lower()


def test_classify_youtube_error_keeps_geo_block_distinct_from_extractor_failure():
    err = classify_youtube_error(RuntimeError("This video is not available in your country"))
    assert err.code == "youtube_geo_blocked"


def test_classify_youtube_error_403_is_not_a_private_or_public_hint():
    err = classify_youtube_error(RuntimeError("HTTP Error 403: Forbidden"))
    assert err.code == "youtube_blocked"
    assert "público" not in err.ui_message.lower()
    assert "privado" not in err.ui_message.lower()


def test_download_from_youtube_maps_private_video(monkeypatch, tmp_path):
    _install_yt_dlp(monkeypatch, FailingYDL, error_cls=Boom)
    with pytest.raises(YoutubeDownloadError, match="privado") as exc_info:
        download_from_youtube("https://www.youtube.com/watch?v=x", dest_dir=tmp_path)
    assert exc_info.value.code == "youtube_private"
    assert "privado" in exc_info.value.ui_message.lower()
