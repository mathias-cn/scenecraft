"""Upload e download de arquivos em bucket S3-compatible (Cloudflare R2 ou AWS S3)."""

from __future__ import annotations

import logging
import mimetypes
import time
from collections.abc import Callable
from io import BytesIO
from pathlib import Path
from typing import TypeVar
from urllib.parse import unquote, urlparse

import boto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import (
    ClientError,
    ConnectTimeoutError,
    ConnectionClosedError,
    EndpointConnectionError,
    ReadTimeoutError,
)

from app.core.config import settings

logger = logging.getLogger(__name__)

_RETRY_ATTEMPTS = 3
_RETRYABLE_HTTP = {408, 429, 500, 502, 503, 504}

T = TypeVar("T")


class StorageError(Exception):
    """Falha de storage após retries ou configuração inválida."""


def _require_config() -> None:
    missing = [
        name
        for name, value in (
            ("S3_BUCKET", settings.s3_bucket),
            ("S3_ACCESS_KEY_ID", settings.s3_access_key_id),
            ("S3_SECRET_ACCESS_KEY", settings.s3_secret_access_key),
        )
        if not value or str(value).startswith("your_")
    ]
    if missing:
        raise StorageError(f"storage não configurado: defina {', '.join(missing)}")


def _client():
    _require_config()
    endpoint = settings.object_storage_endpoint or None
    boto_kwargs: dict = {
        "retries": {"max_attempts": 1, "mode": "standard"},
        "connect_timeout": 10,
        "read_timeout": 120,
        "signature_version": "s3v4",
    }
    if endpoint:
        boto_kwargs["s3"] = {"addressing_style": "path"}

    client_kwargs: dict = {
        "service_name": "s3",
        "aws_access_key_id": settings.s3_access_key_id,
        "aws_secret_access_key": settings.s3_secret_access_key,
        "region_name": settings.s3_region or "auto",
        "config": BotoConfig(**boto_kwargs),
    }
    if endpoint:
        client_kwargs["endpoint_url"] = endpoint.rstrip("/")
    return boto3.client(**client_kwargs)


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, ClientError):
        code = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        error_code = exc.response.get("Error", {}).get("Code", "")
        return code in _RETRYABLE_HTTP or error_code in {
            "SlowDown",
            "RequestTimeout",
            "ServiceUnavailable",
            "InternalError",
        }
    return isinstance(
        exc,
        (
            EndpointConnectionError,
            ConnectionClosedError,
            ConnectTimeoutError,
            ReadTimeoutError,
            ConnectionError,
            TimeoutError,
            OSError,
        ),
    )


def _with_retry(operation: str, fn: Callable[[], T]) -> T:
    last: BaseException | None = None
    for attempt in range(1, _RETRY_ATTEMPTS + 1):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 — classificado em seguida
            last = exc
            if not _is_retryable(exc) or attempt == _RETRY_ATTEMPTS:
                break
            delay = 0.5 * (2 ** (attempt - 1))
            logger.warning(
                "storage %s falhou (tentativa %s/%s): %s; retry em %.1ss",
                operation,
                attempt,
                _RETRY_ATTEMPTS,
                exc,
                delay,
            )
            time.sleep(delay)
    raise StorageError(f"{operation} falhou após {_RETRY_ATTEMPTS} tentativas: {last}") from last


def object_key(project_id: str, filename: str) -> str:
    safe_name = Path(filename).name
    if not project_id.strip() or not safe_name or safe_name in {".", ".."}:
        raise StorageError("project_id ou filename inválido")
    return f"{project_id.strip()}/{safe_name}"


def public_url(key: str) -> str:
    if settings.r2_public_base_url:
        return f"{settings.r2_public_base_url.rstrip('/')}/{key}"
    endpoint = (settings.object_storage_endpoint or "").rstrip("/")
    if endpoint:
        return f"{endpoint}/{settings.s3_bucket}/{key}"
    return f"s3://{settings.s3_bucket}/{key}"


def _parse_location(url: str) -> tuple[str, str]:
    """Extrai (bucket, key) de uma URL devolvida por upload_file ou de um s3://."""
    parsed = urlparse(url)
    if parsed.scheme == "s3":
        bucket = parsed.netloc
        key = unquote(parsed.path.lstrip("/"))
        if not bucket or not key:
            raise StorageError(f"URL s3 inválida: {url}")
        return bucket, key

    path = unquote(parsed.path.lstrip("/"))
    public = (settings.r2_public_base_url or "").rstrip("/")
    if public and url.startswith(public + "/"):
        key = url[len(public) + 1 :]
        if not key:
            raise StorageError(f"URL pública sem key: {url}")
        return settings.s3_bucket, key

    endpoint = (settings.object_storage_endpoint or "").rstrip("/")
    if endpoint and url.startswith(endpoint + "/"):
        rest = url[len(endpoint) + 1 :]
        bucket, _, key = rest.partition("/")
        if not bucket or not key:
            raise StorageError(f"URL de endpoint sem bucket/key: {url}")
        return bucket, key

    # path-style: /bucket/key  |  virtual-hosted: host começa com bucket.
    if path and "/" in path:
        bucket, _, key = path.partition("/")
        if bucket and key:
            return bucket, key

    raise StorageError(f"não foi possível extrair bucket/key de {url}")


def upload_fileobj(
    fileobj,
    project_id: str,
    filename: str,
    *,
    content_type: str | None = None,
) -> str:
    """Envia um file-like para `{project_id}/{filename}` e devolve a URL pública (ou s3)."""
    key = object_key(project_id, filename)
    guessed, _ = mimetypes.guess_type(filename)
    media_type = content_type or guessed
    extra = {"ContentType": media_type} if media_type else None

    def _put() -> None:
        kwargs: dict = {
            "Fileobj": fileobj,
            "Bucket": settings.s3_bucket,
            "Key": key,
        }
        if extra:
            kwargs["ExtraArgs"] = extra
        _client().upload_fileobj(**kwargs)

    if hasattr(fileobj, "seek"):
        try:
            fileobj.seek(0)
        except (OSError, AttributeError):
            pass
    _with_retry("upload_fileobj", _put)
    return public_url(key)


def upload_file(local_path: str, project_id: str, filename: str) -> str:
    """Envia um arquivo local para `{project_id}/{filename}` e devolve a URL pública (ou s3)."""
    source = Path(local_path)
    if not source.is_file():
        raise StorageError(f"arquivo local não encontrado: {local_path}")

    key = object_key(project_id, filename)
    content_type, _ = mimetypes.guess_type(filename)
    extra = {"ContentType": content_type} if content_type else {}

    def _put() -> None:
        kwargs: dict = {
            "Filename": str(source),
            "Bucket": settings.s3_bucket,
            "Key": key,
        }
        if extra:
            kwargs["ExtraArgs"] = extra
        _client().upload_file(**kwargs)

    _with_retry("upload_file", _put)
    return public_url(key)


def download_file(url: str, local_path: str) -> Path:
    """Baixa o objeto referenciado por `url` para `local_path`."""
    if not url:
        raise StorageError("url vazia")
    destination = Path(local_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    bucket, key = _parse_location(url)

    def _get() -> None:
        _client().download_file(Bucket=bucket, Key=key, Filename=str(destination))

    _with_retry("download_file", _get)
    return destination


def download_bytes(url: str) -> bytes:
    """Baixa o objeto referenciado por `url` e devolve os bytes."""
    if not url:
        raise StorageError("url vazia")
    bucket, key = _parse_location(url)

    def _get() -> bytes:
        buf = BytesIO()
        _client().download_fileobj(Bucket=bucket, Key=key, Fileobj=buf)
        return buf.getvalue()

    data = _with_retry("download_bytes", _get)
    if not data:
        raise StorageError(f"objeto vazio: {url}")
    return data
