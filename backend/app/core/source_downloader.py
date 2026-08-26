"""Carrega o áudio de origem do projeto (YouTube ou arquivo já enviado).

O YouTube trata downloaders como scrapers e muda as defesas com frequência
(nsig, PO Token, fingerprint de TLS, bloqueio de IP de VPS). Isso não é um
bug pontual do SceneCraft: exige manutenção recorrente — atualizar `yt-dlp`,
retocar `player_client` / impersonation, e às vezes um PO Token provider.
Atualize `yt-dlp` no `pyproject.toml` / `poetry.lock` pelo menos uma vez por
mês e reconstrua a imagem do backend sem cache dessa camada. Versões recentes
também precisam de `yt-dlp-ejs`, Deno e `curl-cffi` (impersonate Chrome).
"""

from __future__ import annotations

import logging
import tempfile
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

AUDIO_CODECS = ("mp3", "wav")

logger = logging.getLogger(__name__)

# Cascata de InnerTube clients (yt-dlp 2026.8.19). Ordem: menos dependência de
# PO Token primeiro. `android_vr` ainda existe, mas desde 2026.08.17 o YouTube
# responde 403 em todos os formatos desse client — por isso vai por último.
# Se o 403 voltar, o próximo ajuste costuma ser esta lista, um PO Token
# provider, ou o alvo de impersonate (ver `yt-dlp --help` / INNERTUBE_CLIENTS).
YOUTUBE_PLAYER_CLIENTS = ("tv", "web_embedded", "web", "android_vr")

# Sintomas clássicos de yt-dlp desatualizado (YouTube mudou o nsig).
_EXTRACTOR_NEEDLES = (
    "nsig extraction failed",
    "requested format is not available",
    "only images are available",
    "format is not available",
    "some formats may be missing",
)

# 403 / anti-bot / PO Token: o vídeo pode estar público; o servidor é que foi barrado.
_YOUTUBE_BLOCKED_NEEDLES = (
    "http error 403",
    "403: forbidden",
    "http 403",
    "got http error 403",
    "po token",
    "gvs po token",
    "confirm you're not a bot",
    "confirm you are not a bot",
    "confirm that you are not a bot",
    "detected unusual traffic",
    "unusual traffic from your computer",
)


class SourceDownloadError(Exception):
    """Falha ao obter o áudio. `ui_message` / str(exc) pode ir direto para a UI."""

    def __init__(self, message: str, *, code: str = "source_download_failed") -> None:
        super().__init__(message)
        self.ui_message = message
        self.code = code


class YoutubeDownloadError(SourceDownloadError):
    """Vídeo do YouTube inacessível (privado, removido, indisponível, etc.)."""


def load_audio(project: Project, dest_dir: str | Path) -> Path:
    """Devolve um caminho local com o áudio/vídeo pronto para o Whisper."""
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    source_type = project.source_type
    ref = (project.source_ref or "").strip()
    if not ref:
        raise SourceDownloadError("projeto sem source_ref", code="missing_source")
    if source_type == SourceType.YOUTUBE_LINK or _is_youtube_url(ref):
        return download_from_youtube(ref, dest_dir=dest)
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


def download_from_youtube(url: str, dest_dir: str | Path | None = None) -> Path:
    """Extrai o áudio (mp3, com fallback wav) de um link do YouTube via yt-dlp."""
    cleaned = (url or "").strip()
    if not cleaned:
        raise YoutubeDownloadError("Informe um link do YouTube.", code="youtube_invalid_url")
    if not _is_youtube_url(cleaned):
        raise YoutubeDownloadError(
            "Informe um link válido do YouTube (youtube.com ou youtu.be).",
            code="youtube_invalid_url",
        )

    dest = Path(dest_dir) if dest_dir is not None else Path(tempfile.mkdtemp(prefix="scenecraft-yt-"))
    dest.mkdir(parents=True, exist_ok=True)

    try:
        import yt_dlp
        from yt_dlp.utils import DownloadError, ExtractorError
    except ImportError as exc:
        raise YoutubeDownloadError(
            "Não foi possível baixar o YouTube: yt-dlp não está instalado.",
            code="youtube_tool_missing",
        ) from exc

    last_error: BaseException | None = None
    for codec in AUDIO_CODECS:
        try:
            path = _extract_youtube_audio(yt_dlp, cleaned, dest, codec)
            if path is not None:
                return path
        except (DownloadError, ExtractorError) as exc:
            last_error = exc
            break
        except YoutubeDownloadError:
            raise
        except Exception as exc:  # noqa: BLE001 — yt-dlp lança tipos variados
            last_error = exc
            break

    if last_error is not None:
        raise classify_youtube_error(last_error) from last_error
    raise YoutubeDownloadError(
        "Não foi possível extrair o áudio deste vídeo do YouTube.",
        code="youtube_unavailable",
    )


def download_youtube_audio(url: str, dest_dir: Path) -> Path:
    """Alias usado por `load_audio`."""
    return download_from_youtube(url, dest_dir=dest_dir)


def classify_youtube_error(exc: BaseException) -> YoutubeDownloadError:
    """Traduz erros do yt-dlp para mensagens estáveis da UI."""
    text = " ".join(part for part in (str(exc), getattr(exc, "msg", None)) if part).lower()
    if any(needle in text for needle in _EXTRACTOR_NEEDLES):
        logger.warning(
            "falha de extração do YouTube (possível yt-dlp desatualizado, versão %s): %s",
            _yt_dlp_version(),
            text[:500],
        )
        return YoutubeDownloadError(
            "Não foi possível extrair o áudio deste vídeo (formato indisponível). "
            "Isso costuma indicar yt-dlp desatualizado — atualize a dependência e reconstrua a imagem.",
            code="youtube_extractor_outdated",
        )
    rules: tuple[tuple[tuple[str, ...], str, str], ...] = (
        (
            ("private video", "this video is private"),
            "Este vídeo do YouTube é privado e não pode ser transcrito.",
            "youtube_private",
        ),
        (
            ("video has been removed", "this video is no longer available", "removed by the uploader", "account associated with this video has been terminated"),
            "Este vídeo foi removido do YouTube.",
            "youtube_removed",
        ),
        (
            ("not available in your country", "not made this video available in your country"),
            "Este vídeo do YouTube não está disponível na sua região.",
            "youtube_geo_blocked",
        ),
        (
            ("sign in to confirm your age", "age-restricted", "age restricted"),
            "Este vídeo do YouTube tem restrição de idade.",
            "youtube_age_restricted",
        ),
        (
            ("members-only", "members only", "join this channel"),
            "Este vídeo é exclusivo para membros do canal.",
            "youtube_members_only",
        ),
        (
            ("copyright", "blocked it on copyright"),
            "Este vídeo foi bloqueado no YouTube por direitos autorais.",
            "youtube_copyright",
        ),
        (
            ("live event", "this live stream recording is not available", "premier"),
            "Não é possível transcrever lives ou estreias do YouTube.",
            "youtube_live",
        ),
        (
            _YOUTUBE_BLOCKED_NEEDLES,
            "O YouTube bloqueou a extração a partir deste servidor — "
            "tente novamente mais tarde ou use upload direto do arquivo.",
            "youtube_blocked",
        ),
        (
            ("video unavailable", "this video is unavailable", "unavailable"),
            "Este vídeo do YouTube está indisponível.",
            "youtube_unavailable",
        ),
    )
    for needles, message, code in rules:
        if any(needle in text for needle in needles):
            return YoutubeDownloadError(message, code=code)
    return YoutubeDownloadError(
        "Não foi possível baixar este vídeo do YouTube. Verifique se o link está público.",
        code="youtube_unavailable",
    )


def _yt_dlp_version() -> str:
    try:
        import yt_dlp

        version_mod = getattr(yt_dlp, "version", None)
        if version_mod is not None:
            pinned = getattr(version_mod, "__version__", None)
            if pinned:
                return str(pinned)
        return str(getattr(yt_dlp, "__version__", "?"))
    except Exception:
        return "?"


def _chrome_impersonate_target():
    """Alvo Chrome para curl_cffi. String basta nos testes; a API real quer ImpersonateTarget."""
    try:
        from yt_dlp.networking.impersonate import ImpersonateTarget

        return ImpersonateTarget.from_str("chrome")
    except Exception:
        return "chrome"


def _youtube_dl_opts(dest: Path, codec: str, *, impersonate: bool) -> dict:
    opts: dict = {
        "format": "bestaudio/best",
        "outtmpl": str(dest / "youtube_audio.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "noprogress": True,
        "overwrites": True,
        "extractor_args": {"youtube": {"player_client": list(YOUTUBE_PLAYER_CLIENTS)}},
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": codec,
                "preferredquality": "64" if codec == "mp3" else "0",
            }
        ],
    }
    if impersonate:
        opts["impersonate"] = _chrome_impersonate_target()
    return opts


def _extract_youtube_audio(yt_dlp, url: str, dest: Path, codec: str) -> Path | None:
    basename = "youtube_audio"
    last_init_error: BaseException | None = None
    for impersonate in (True, False):
        opts = _youtube_dl_opts(dest, codec, impersonate=impersonate)
        try:
            ydl_ctx = yt_dlp.YoutubeDL(opts)
        except Exception as exc:  # noqa: BLE001 — constructor raises if curl_cffi is missing
            last_init_error = exc
            if impersonate:
                logger.warning(
                    "yt-dlp impersonate=chrome indisponível (%s); tentando sem impersonation",
                    exc,
                )
                continue
            raise
        with ydl_ctx as ydl:
            ydl.download([url])
        break
    else:
        if last_init_error is not None:
            raise last_init_error
    preferred = dest / f"{basename}.{codec}"
    if preferred.is_file():
        return preferred
    matches = sorted(
        path
        for path in dest.glob(f"{basename}.*")
        if path.is_file() and path.suffix.lower() in {".mp3", ".wav", ".m4a", ".ogg", ".webm"}
    )
    return matches[0] if matches else None


def _is_youtube_url(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    return host in {item.removeprefix("www.") for item in YOUTUBE_HOSTS} or host.endswith("youtube.com")
