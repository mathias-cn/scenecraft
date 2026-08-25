"""Backoff de retry das tasks Celery."""


def retry_countdown(retries: int, base: int = 2) -> int:
    """Backoff exponencial: 2s, 4s, 8s… a partir da tentativa que acabou de falhar."""
    return int(base) ** (int(retries) + 1)
