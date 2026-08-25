"""Cliente ElevenLabs: listagem de vozes e TTS com timestamps por palavra."""

from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Any

from app.core.config import settings

STUB_VOICES = (
    ("21m00Tcm4TlvDq8ikWAM", "Rachel"),
    ("pNInz6obpgDQGcFmaJgB", "Adam"),
    ("EXAVITQu4vr4xnSDxMaL", "Bella"),
    ("ErXwobaYiN019PkySvjV", "Antoni"),
)

_VOICES_URL = "https://api.elevenlabs.io/v1/voices"
_TTS_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/with-timestamps"
_TTS_MODEL = "eleven_multilingual_v2"


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
    key = _api_key()
    if not key:
        return [Voice(voice_id, name) for voice_id, name in STUB_VOICES]

    payload = _get_json(_VOICES_URL, key, timeout=30.0, http=http)
    voices: list[Voice] = []
    for item in payload.get("voices") or []:
        voice_id = str(item.get("voice_id") or "").strip()
        name = str(item.get("name") or voice_id).strip()
        if voice_id:
            voices.append(Voice(voice_id, name or voice_id))
    return voices or [Voice(voice_id, name) for voice_id, name in STUB_VOICES]


def generate_speech(
    text: str,
    voice_id: str,
    *,
    http: Any | None = None,
) -> tuple[bytes, list[dict[str, Any]]]:
    """Gera áudio MPEG e timestamps por palavra. Sem chave, devolve stub local."""
    script = (text or "").strip()
    if not script:
        raise ElevenLabsError("texto vazio para síntese")
    voice = (voice_id or "").strip() or STUB_VOICES[0][0]
    key = _api_key()
    if not key:
        return b"ID3\x04stub-elevenlabs", []

    payload = _post_json(
        _TTS_URL.format(voice_id=voice),
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
    timestamps = word_timestamps_from_alignment(payload.get("alignment") or payload.get("normalized_alignment"))
    return audio_bytes, timestamps


def _headers(key: str) -> dict[str, str]:
    return {"xi-api-key": key, "Accept": "application/json"}


def _get_json(url: str, key: str, *, timeout: float, http: Any | None) -> dict[str, Any]:
    client, owns = _http_client(http, timeout)
    try:
        response = client.get(url, headers=_headers(key), timeout=timeout)
        response.raise_for_status()
        return response.json()
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
        response.raise_for_status()
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
