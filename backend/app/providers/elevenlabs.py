from app.config import settings


def synthesize(*, script: str, job_id: str) -> str:
    """Gera narração via ElevenLabs. Sem chave, devolve um URL placeholder."""
    if not settings.elevenlabs_api_key or settings.elevenlabs_api_key.startswith("your_"):
        return f"stub://voice/{job_id}.mp3"

    import httpx

    response = httpx.post(
        "https://api.elevenlabs.io/v1/text-to-speech/Rachel",
        headers={
            "xi-api-key": settings.elevenlabs_api_key,
            "Accept": "audio/mpeg",
        },
        json={"text": script, "model_id": "eleven_multilingual_v2"},
        timeout=120.0,
    )
    response.raise_for_status()
    return f"memory://elevenlabs/{job_id}.mp3"
