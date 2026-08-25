from pathlib import Path

from app.storage import StorageError, download_file, upload_file, upload_fileobj


def upload_media(*, job_id: str, source: str) -> str:
    """Envia media do pipeline para o bucket. Sem arquivo local, devolve o source."""
    if source.startswith(("stub://", "memory://", "higgsfield://")):
        return source
    path = Path(source)
    if path.is_file():
        return upload_file(str(path), job_id, path.name)
    return source


__all__ = ["StorageError", "download_file", "upload_file", "upload_fileobj", "upload_media"]
