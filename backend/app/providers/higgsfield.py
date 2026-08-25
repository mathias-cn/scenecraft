from app.core.config import settings


def generate_video(*, script: str, job_id: str) -> str:
    """Gera o vídeo via Higgsfield. Sem chave, devolve um URL placeholder."""
    if not settings.higgsfield_api_key or settings.higgsfield_api_key.startswith("your_"):
        return f"stub://video/{job_id}.mp4"

    import httpx

    response = httpx.post(
        "https://api.higgsfield.ai/v1/generate",
        headers={"Authorization": f"Bearer {settings.higgsfield_api_key}"},
        json={"prompt": script, "job_id": job_id},
        timeout=180.0,
    )
    response.raise_for_status()
    payload = response.json()
    return payload.get("video_url") or payload.get("url") or f"higgsfield://{job_id}"
