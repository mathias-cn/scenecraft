"""Cliente ElevenLabs: listagem de vozes e TTS com timestamps por palavra.

A síntese usa POST /v1/text-to-speech/{voice_id}/with-timestamps (alinhamento
por caractere). Agrupamos em palavras para o pipeline (audio_tracks.word_timestamps).
A listagem usa GET /v2/voices (paginada) para o seletor do frontend.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

from app.core.config import settings

STUB_VOICES = (
    ("21m00Tcm4TlvDq8ikWAM", "Rachel"),
    ("pNInz6obpgDQGcFmaJgB", "Adam"),
    ("EXAVITQu4vr4xnSDxMaL", "Bella"),
    ("ErXwobaYiN019PkySvjV", "Antoni"),
)

_API = "https://api.elevenlabs.io"
_VOICES_URL = f"{_API}/v2/voices"
_TTS_PATH = "/v1/text-to-speech/{voice_id}/with-timestamps"
_TTS_MODEL = "eleven_multilingual_v2"
_TTS_OUTPUT_FORMAT = "mp3_44100_128"
_MAX_VOICE_PAGES = 5
_VOICE_PAGE_SIZE = 100


@dataclass(frozen=True)
class Voice:
    id: str
    name: str


class ElevenLabsError(RuntimeError):
    """Falha na API da ElevenLabs."""


def _api_key() -> str:
    key = (settings.elevenlabs_api_key or "").strip()
    if not key or key.startswith("your_"):
        return ""
    return key


def word_timestamps_from_alignment(alignment: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Agrupa o alinhamento por caractere da ElevenLabs em timestamps por palavra (ms)."""
    if not alignment:
        return []
    characters = alignment.get("characters") or []
    starts = alignment.get("character_start_times_seconds") or []
    ends = alignment.get("character_end_times_seconds") or []
    count = min(len(characters), len(starts), len(ends))
    words: list[dict[str, Any]] = []
    buffer: list[tuple[str, float, float]] = []

    def flush() -> None:
        if not buffer:
            return
        token = "".join(char for char, _start, _end in buffer)
        if token:
            words.append(
                {
                    "word": token,
                    "start_ms": int(round(buffer[0][1] * 1000)),
                    "end_ms": int(round(buffer[-1][2] * 1000)),
                }
            )
        buffer.clear()

    for index in range(count):
        char = str(characters[index])
        if char.isspace():
            flush()
            continue
        buffer.append((char, float(starts[index]), float(ends[index])))
    flush()
    return words


def list_voices(*, http: Any | None = None) -> list[Voice]:
    """Vozes da conta (premade + pessoais) para o seletor do frontend."""
    key = _api_key()
    if not key:
        return [Voice(voice_id, name) for voice_id, name in STUB_VOICES]

    voices: list[Voice] = []
    seen: set[str] = set()
    token = ""
    for _ in range(_MAX_VOICE_PAGES):
        params: dict[str, Any] = {
            "page_size": _VOICE_PAGE_SIZE,
            "sort": "name",
            "sort_direction": "asc",
            "include_total_count": "false",
        }
        if token:
            params["next_page_token"] = token
        payload = _get_json(_VOICES_URL, key, params=params, timeout=30.0, http=http)
        for item in payload.get("voices") or []:
            voice_id = str(item.get("voice_id") or "").strip()
            name = str(item.get("name") or voice_id).strip()
            if not voice_id or voice_id in seen:
                continue
            seen.add(voice_id)
            voices.append(Voice(voice_id, name or voice_id))
        if not payload.get("has_more"):
            break
        token = str(payload.get("next_page_token") or "").strip()
        if not token:
            break
    return voices or [Voice(voice_id, name) for voice_id, name in STUB_VOICES]


def generate_speech(
    text: str,
    voice_id: str,
    *,
    http: Any | None = None,
) -> tuple[bytes, list[dict[str, Any]]]:
    """Gera MPEG e timestamps por palavra via /with-timestamps. Sem chave, stub local."""
    script = (text or "").strip()
    if not script:
        raise ElevenLabsError("texto vazio para síntese")
    voice = (voice_id or "").strip() or STUB_VOICES[0][0]
    key = _api_key()
    if not key:
        return b"ID3\x04stub-elevenlabs", []

    url = f"{_API}{_TTS_PATH.format(voice_id=voice)}?{urlencode({'output_format': _TTS_OUTPUT_FORMAT})}"
    payload = _post_json(
        url,
        key,
        body={"text": script, "model_id": _TTS_MODEL},
        timeout=120.0,
        http=http,
    )
    encoded = str(payload.get("audio_base64") or "").strip()
    if not encoded:
        raise ElevenLabsError("ElevenLabs devolveu áudio vazio")
    try:
        audio_bytes = base64.b64decode(encoded)
    except Exception as exc:
        raise ElevenLabsError("ElevenLabs devolveu áudio inválido") from exc
    if not audio_bytes:
        raise ElevenLabsError("ElevenLabs devolveu áudio vazio")
    timestamps = word_timestamps_from_alignment(
        payload.get("alignment") or payload.get("normalized_alignment")
    )
    return audio_bytes, timestamps


def _headers(key: str) -> dict[str, str]:
    return {"xi-api-key": key, "Accept": "application/json"}


def _error_detail(response: Any) -> str:
    try:
        body = response.json()
    except Exception:
        text = (getattr(response, "text", None) or "").strip()
        return text[:400]
    if isinstance(body, dict):
        detail = body.get("detail")
        if isinstance(detail, dict):
            return str(detail.get("message") or detail.get("status") or detail)
        if isinstance(detail, str) and detail.strip():
            return detail.strip()
        message = body.get("message")
        if isinstance(message, str) and message.strip():
            return message.strip()
    return ""


def _ensure_ok(response: Any, fallback: str) -> None:
    status = int(getattr(response, "status_code", 0) or 0)
    if status < 400:
        return
    extra = _error_detail(response)
    suffix = f" — {extra}" if extra else ""
    raise ElevenLabsError(f"{fallback}: HTTP {status}{suffix}")


def _get_json(
    url: str,
    key: str,
    *,
    timeout: float,
    http: Any | None,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    client, owns = _http_client(http, timeout)
    try:
        response = client.get(url, headers=_headers(key), params=params, timeout=timeout)
        _ensure_ok(response, "não foi possível listar vozes ElevenLabs")
        payload = response.json()
        if not isinstance(payload, dict):
            raise ElevenLabsError("ElevenLabs devolveu lista de vozes inválida")
        return payload
    except ElevenLabsError:
        raise
    except Exception as exc:
        raise ElevenLabsError(f"não foi possível listar vozes ElevenLabs: {exc}") from exc
    finally:
        if owns:
            client.close()


def _post_json(
    url: str,
    key: str,
    *,
    body: dict[str, Any],
    timeout: float,
    http: Any | None,
) -> dict[str, Any]:
    client, owns = _http_client(http, timeout)
    try:
        response = client.post(
            url,
            headers={**_headers(key), "Content-Type": "application/json"},
            json=body,
            timeout=timeout,
        )
        _ensure_ok(response, "falha na síntese ElevenLabs")
        payload = response.json()
        if not isinstance(payload, dict):
            raise ElevenLabsError("ElevenLabs devolveu resposta inválida")
        return payload
    except ElevenLabsError:
        raise
    except Exception as exc:
        raise ElevenLabsError(f"falha na síntese ElevenLabs: {exc}") from exc
    finally:
        if owns:
            client.close()


def _http_client(http: Any | None, timeout: float) -> tuple[Any, bool]:
    if http is not None:
        return http, False
    import httpx

    return httpx.Client(timeout=timeout), True
