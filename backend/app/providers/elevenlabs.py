"""Compat: a implementação vive em elevenlabs_client."""

from app.providers.elevenlabs_client import (
    STUB_VOICES,
    ElevenLabsError,
    Voice,
    generate_speech,
    list_voices,
)


def synthesize(*, text: str, voice_id: str, job_id: str | None = None) -> bytes:
    """Gera narração. Sem chave, devolve bytes placeholder (não chama a API)."""
    _ = job_id
    audio_bytes, _timestamps = generate_speech(text, voice_id)
    return audio_bytes
