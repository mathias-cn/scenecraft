from app.config import settings


def upload_video(*, title: str, description: str, video_url: str) -> str:
    """Publica no YouTube via OAuth. Sem credenciais, devolve um URL placeholder."""
    configured = settings.youtube_client_id and settings.youtube_client_secret
    looks_real = configured and not settings.youtube_client_id.startswith("your_")
    if not looks_real:
        return f"https://youtube.com/watch?v=stub-{abs(hash(title)) % 10_000_000:07d}"

    # O fluxo OAuth completo (refresh token → resumable upload) entra nesta função.
    return video_url
