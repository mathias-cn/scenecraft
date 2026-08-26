"""Legendas oficiais do YouTube, sem baixar áudio via yt-dlp.

O endpoint de captions é bloqueado com bem menos agressividade que o CDN de
vídeo/áudio. Falhas (vídeo sem legenda, IP bloqueado, etc.) devem ser tratadas
pelo chamador com fallback para Whisper.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse

from youtube_transcript_api import YouTubeTranscriptApi

from app.providers.transcription_client import Segment, seconds_to_ms

logger = logging.getLogger(__name__)

VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")

TRANSCRIPT_METHOD_CAPTION_API = "caption_api"
TRANSCRIPT_METHOD_WHISPER_FALLBACK = "whisper_fallback"
TRANSCRIPT_METHOD_WHISPER = "whisper"

_LANG_ALIASES = {
    "portuguese": "pt",
    "brazilian": "pt",
    "english": "en",
    "spanish": "es",
    "castilian": "es",
}


@dataclass(frozen=True)
class YoutubeCaptionResult:
    segments: list[Segment]
    language: str
    video_id: str


def extract_youtube_video_id(url: str) -> str | None:
    """Extrai o video_id de 11 caracteres de uma URL do YouTube (ou do próprio id)."""
    text = (url or "").strip()
    if not text:
        return None
    if VIDEO_ID_RE.fullmatch(text):
        return text
    parsed = urlparse(text if "://" in text else f"https://{text}")
    candidates: list[str] = []
    query = parse_qs(parsed.query)
    if "v" in query:
        candidates.append(query["v"][0])
    host = (parsed.hostname or "").lower().removeprefix("www.")
    parts = [part for part in parsed.path.split("/") if part]
    if host in {"youtu.be"} and parts:
        candidates.append(parts[0])
    for marker in ("embed", "shorts", "live", "v"):
        if marker in parts:
            idx = parts.index(marker)
            if idx + 1 < len(parts):
                candidates.append(parts[idx + 1])
    for candidate in candidates:
        video_id = candidate.split("?")[0].split("&")[0]
        if VIDEO_ID_RE.fullmatch(video_id):
            return video_id
    return None


def caption_language_priority(target_language: str | None) -> list[str]:
    """Idioma do projeto primeiro, depois `en`. `pt-BR` também tenta `pt`."""
    ordered: list[str] = []
    seen: set[str] = set()

    def add(code: str) -> None:
        key = (code or "").strip()
        if not key:
            return
        folded = key.lower()
        if folded in seen:
            return
        seen.add(folded)
        ordered.append(key)

    raw = (target_language or "").strip()
    lowered = raw.lower().replace("_", "-")
    if raw and lowered not in {"auto", "und", "original"}:
        add(raw)
        primary = lowered.split("-", 1)[0]
        add(_LANG_ALIASES.get(primary, primary))
    add("en")
    return ordered


def snippets_to_segments(fetched: object, language: str = "") -> list[Segment]:
    """Converte snippets (`text`, `start`, `duration`) em `Segment` (ms)."""
    lang = (language or str(getattr(fetched, "language_code", "") or ""))[:16]
    snippets = getattr(fetched, "snippets", fetched)
    segments: list[Segment] = []
    for item in snippets:
        if isinstance(item, dict):
            text = item.get("text")
            start = item.get("start")
            duration = item.get("duration") or 0
        else:
            text = getattr(item, "text", None)
            start = getattr(item, "start", None)
            duration = getattr(item, "duration", 0) or 0
        cleaned = str(text or "").strip()
        if not cleaned or start is None:
            continue
        start_ms = seconds_to_ms(start)
        end_ms = seconds_to_ms(float(start) + float(duration))
        if end_ms <= start_ms:
            end_ms = start_ms + 1
        segments.append(Segment(start_ms=start_ms, end_ms=end_ms, text=cleaned, language=lang))
    return segments


def fetch_youtube_captions(source_ref: str, target_language: str | None) -> YoutubeCaptionResult | None:
    """Busca legendas via YouTubeTranscriptApi. Devolve None se não houver transcript."""
    video_id = extract_youtube_video_id(source_ref)
    if not video_id:
        logger.warning("caption_api: não foi possível extrair video_id de source_ref")
        return None
    languages = caption_language_priority(target_language)
    try:
        fetched = YouTubeTranscriptApi().fetch(video_id, languages=languages)
    except Exception as exc:
        logger.warning(
            "caption_api: falha ao buscar legendas video_id=%s languages=%s: %s",
            video_id,
            languages,
            exc,
        )
        return None
    language = str(getattr(fetched, "language_code", "") or "")[:16]
    segments = snippets_to_segments(fetched, language)
    if not segments:
        logger.warning("caption_api: legendas vazias video_id=%s", video_id)
        return None
    logger.info(
        "caption_api: video_id=%s language=%s segments=%s",
        video_id,
        language,
        len(segments),
    )
    return YoutubeCaptionResult(segments=segments, language=language, video_id=video_id)
