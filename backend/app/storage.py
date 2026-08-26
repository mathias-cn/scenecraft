"""Upload e download de arquivos em bucket S3-compatible (Cloudflare R2 ou AWS S3)."""

from __future__ import annotations

import logging
import mimetypes
import time
from uuid import uuid4
from collections.abc import Callable
from io import BytesIO
from pathlib import Path
from typing import TypeVar
from urllib.parse import unquote, urlparse

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
    import boto3
    from botocore.config import Config as BotoConfig

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
    from botocore.exceptions import (
        ClientError,
        ConnectTimeoutError,
        ConnectionClosedError,
        EndpointConnectionError,
        ReadTimeoutError,
    )

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


def relative_object_key(key: str) -> str:
    """Caminho dentro do bucket, sem o nome do bucket no prefixo."""
    text = unquote((key or "").strip()).lstrip("/")
    bucket = (settings.s3_bucket or "").strip().strip("/")
    if bucket:
        if text == bucket:
            return ""
        prefix = f"{bucket}/"
        if text.startswith(prefix):
            text = text[len(prefix) :]
    return text


def object_key(project_id: str, filename: str) -> str:
    """Key S3 relativa ao bucket, ex. `characters/{id}/base.png` — sem `S3_BUCKET`."""
    safe_name = Path(filename).name
    if not project_id.strip() or not safe_name or safe_name in {".", ".."}:
        raise StorageError("project_id ou filename inválido")
    prefix = relative_object_key(project_id.strip().strip("/"))
    if not prefix:
        return safe_name
    return f"{prefix}/{safe_name}"


def versioned_filename(stem: str, suffix: str = ".png") -> str:
    """Nome único por geração para o CDN e o browser não reutilizarem cache de overwrite."""
    ext = suffix if str(suffix).startswith(".") else f".{suffix}"
    base = Path(stem).stem.strip() or "file"
    return f"{base}_{uuid4().hex}{ext.lower()}"


DOWNLOAD_URL_EXPIRES = 3600
_CDN_HOSTS = frozenset({"cdn.mazting.studio"})


def _host(url: str) -> str:
    parsed = urlparse(url if "://" in url else f"https://{url}")
    return (parsed.netloc or "").lower()


def object_key_from_stored(value: str) -> str | None:
    """Converte URL antiga (CDN / R2 / s3://) ou key relativa no object_key do bucket."""
    text = unquote((value or "").strip())
    if not text:
        return None
    text = text.split("?", 1)[0].split("#", 1)[0]
    if "://" not in text and not text.startswith("//"):
        return relative_object_key(text) or None

    parsed = urlparse(text)
    public_host = _host(settings.r2_public_base_url) if settings.r2_public_base_url else ""
    endpoint_host = _host(settings.object_storage_endpoint) if settings.object_storage_endpoint else ""
    ours = {host for host in (*_CDN_HOSTS, public_host, endpoint_host) if host}
    if parsed.scheme == "s3":
        return relative_object_key(unquote(parsed.path.lstrip("/"))) or None
    host = parsed.netloc.lower()
    if host not in ours and not host.endswith(".r2.cloudflarestorage.com"):
        return None
    return relative_object_key(unquote(parsed.path.lstrip("/"))) or None


def generate_presigned_url(object_key: str, expires_in: int = DOWNLOAD_URL_EXPIRES) -> str:
    """GET assinado no R2/S3. `object_key` é o caminho relativo no bucket."""
    key = object_key_from_stored(object_key) or relative_object_key(object_key)
    if not key:
        raise StorageError("object_key vazio")
    bucket = (settings.s3_bucket or "").strip()
    if not bucket:
        raise StorageError("S3_BUCKET não configurado")

    def _sign() -> str:
        return _client().generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": key},
            ExpiresIn=expires_in,
        )

    signed = _with_retry("generate_presigned_url", _sign)
    if not signed:
        raise StorageError("não foi possível assinar a URL de download")
    return signed


def signed_asset_url(stored: str | None, expires_in: int = DOWNLOAD_URL_EXPIRES) -> str | None:
    """URL temporária para a API. Keys/CDN viram presign; HTTP externo permanece."""
    text = (stored or "").strip()
    if not text:
        return None
    key = object_key_from_stored(text)
    if key:
        return generate_presigned_url(key, expires_in=expires_in)
    if text.startswith(("http://", "https://")):
        return text
    return generate_presigned_url(text, expires_in=expires_in)


def public_url(key: str) -> str:
    relative = relative_object_key(key)
    if not relative:
        raise StorageError("object_key vazio")
    if settings.r2_public_base_url:
        return f"{settings.r2_public_base_url.rstrip('/')}/{relative}"
    endpoint = (settings.object_storage_endpoint or "").rstrip("/")
    if endpoint:
        return f"{endpoint}/{settings.s3_bucket}/{relative}"
    return f"s3://{settings.s3_bucket}/{relative}"


def download_url(
    url: str,
    *,
    filename: str | None = None,
    content_type: str | None = None,
    expires_in: int = DOWNLOAD_URL_EXPIRES,
) -> str:
    """HTTP para preview/download: sempre GET assinado (bucket privado)."""
    del filename, content_type
    text = (url or "").strip()
    if not text:
        raise StorageError("url vazia")
    key = object_key_from_stored(text)
    if key:
        return generate_presigned_url(key, expires_in=expires_in)
    if text.startswith(("http://", "https://")):
        return text
    raise StorageError("object_key vazio")


def _parse_location(url: str) -> tuple[str, str]:
    """Extrai (bucket, key) de object_key, URL pública antiga, endpoint R2 ou s3://."""
    text = (url or "").strip()
    if not text:
        raise StorageError("url vazia")
    key = object_key_from_stored(text)
    if key:
        bucket = (settings.s3_bucket or "").strip()
        if not bucket:
            raise StorageError("S3_BUCKET não configurado")
        return bucket, key
    raise StorageError(f"não foi possível extrair bucket/key de {url}")


def upload_fileobj(
    fileobj,
    project_id: str,
    filename: str,
    *,
    content_type: str | None = None,
) -> str:
    """Envia um file-like para `{project_id}/{filename}` e devolve o object_key."""
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
    return key


def upload_file(local_path: str, project_id: str, filename: str) -> str:
    """Envia um arquivo local para `{project_id}/{filename}` e devolve o object_key."""
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
    return key


def object_exists(project_id: str, filename: str) -> bool:
    """True se `{project_id}/{filename}` já existe no bucket."""
    from botocore.exceptions import ClientError

    key = object_key(project_id, filename)
    try:
        _client().head_object(Bucket=settings.s3_bucket, Key=key)
        return True
    except ClientError as exc:
        status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        code = str(exc.response.get("Error", {}).get("Code", ""))
        if status == 404 or code in {"404", "NoSuchKey", "NotFound"}:
            return False
        raise StorageError(f"head_object falhou: {exc}") from exc


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
