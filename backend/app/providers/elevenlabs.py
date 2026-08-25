"""Narração via ElevenLabs (TTS). Sem chave, usa vozes stub e bytes placeholder."""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import settings

STUB_VOICES = (
    ("21m00Tcm4TlvDq8ikWAM", "Rachel"),
    ("pNInz6obpgDQGcFmaJgB", "Adam"),
    ("EXAVITQu4vr4xnSDxMaL", "Bella"),
    ("ErXwobaYiN019PkySvjV", "Antoni"),
)


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


def list_voices() -> list[Voice]:
    key = _api_key()
    if not key:
        return [Voice(voice_id, name) for voice_id, name in STUB_VOICES]
    import httpx

    try:
        response = httpx.get(
            "https://api.elevenlabs.io/v1/voices",
            headers={"xi-api-key": key},
            timeout=30.0,
        )
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        raise ElevenLabsError(f"não foi possível listar vozes ElevenLabs: {exc}") from exc
    voices: list[Voice] = []
    for item in payload.get("voices") or []:
        voice_id = str(item.get("voice_id") or "").strip()
        name = str(item.get("name") or voice_id).strip()
        if voice_id:
            voices.append(Voice(voice_id, name or voice_id))
    return voices or [Voice(voice_id, name) for voice_id, name in STUB_VOICES]


def synthesize(*, text: str, voice_id: str, job_id: str | None = None) -> bytes:
    """Gera narração. Sem chave, devolve bytes placeholder (não chama a API)."""
    _ = job_id
    script = (text or "").strip()
    if not script:
        raise ElevenLabsError("texto vazio para síntese")
    voice = (voice_id or "").strip() or STUB_VOICES[0][0]
    key = _api_key()
    if not key:
        return b"ID3\x04stub-elevenlabs"

    import httpx

    try:
        response = httpx.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{voice}",
            headers={
                "xi-api-key": key,
                "Accept": "audio/mpeg",
            },
            json={"text": script, "model_id": "eleven_multilingual_v2"},
            timeout=120.0,
        )
        response.raise_for_status()
    except Exception as exc:
        raise ElevenLabsError(f"falha na síntese ElevenLabs: {exc}") from exc
    if not response.content:
        raise ElevenLabsError("ElevenLabs devolveu áudio vazio")
    return response.content
