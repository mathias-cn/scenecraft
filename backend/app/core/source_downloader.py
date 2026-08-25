"""Carrega o áudio de origem do projeto (YouTube ou arquivo já enviado)."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

from app.models.enums import SourceType
from app.models.project import Project

YOUTUBE_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "youtu.be",
    "www.youtu.be",
    "music.youtube.com",
}


class SourceDownloadError(Exception):
    """Não foi possível obter o áudio da fonte do projeto."""


def load_audio(project: Project, dest_dir: str | Path) -> Path:
    """Devolve um caminho local com o áudio/vídeo pronto para o Whisper."""
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    source_type = project.source_type
    ref = (project.source_ref or "").strip()
    if not ref:
        raise SourceDownloadError("projeto sem source_ref")
    if source_type == SourceType.YOUTUBE_LINK or _is_youtube_url(ref):
        return download_youtube_audio(ref, dest)
    return load_uploaded_source(ref, dest)


def load_uploaded_source(source_ref: str, dest_dir: Path) -> Path:
    local = Path(source_ref)
    if local.is_file():
        return local
    suffix = Path(urlparse(source_ref).path).suffix or ".bin"
    target = dest_dir / f"source{suffix}"
    return download_stored_source(source_ref, str(target))


def download_stored_source(source_ref: str, local_path: str) -> Path:
    from app.storage import download_file

    return download_file(source_ref, local_path)


def download_youtube_audio(url: str, dest_dir: Path) -> Path:
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    try:
        import yt_dlp
    except ImportError as exc:
        raise SourceDownloadError("yt-dlp não está instalado") from exc

    basename = "youtube_audio"
    opts = {
        "format": "bestaudio/best",
        "outtmpl": str(dest_dir / f"{basename}.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "noprogress": True,
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "64",
            }
        ],
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])
    except Exception as exc:  # noqa: BLE001 — yt-dlp lança tipos variados
        raise SourceDownloadError(f"falha ao baixar áudio do YouTube: {exc}") from exc

    mp3 = dest_dir / f"{basename}.mp3"
    if mp3.is_file():
        return mp3
    matches = sorted(path for path in dest_dir.glob(f"{basename}.*") if path.is_file())
    if not matches:
        raise SourceDownloadError(f"yt-dlp não gerou arquivo para {url}")
    return matches[0]


def _is_youtube_url(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    return host in {item.removeprefix("www.") for item in YOUTUBE_HOSTS} or host.endswith("youtube.com")
