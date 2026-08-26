"""Autenticação JWT (Better Auth) via JWKS público."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Annotated, Any

import httpx
import jwt
from fastapi import Header, HTTPException, status

from app.core.config import settings

JWKS_TTL_SECONDS = 3600
_JWKS_LOCK = threading.Lock()
_jwks_cache: tuple[float, dict[str, Any]] | None = None

def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Não autenticado",
        headers={"WWW-Authenticate": "Bearer"},
    )


@dataclass(frozen=True)
class CurrentUser:
    email: str
    subject: str


def get_jwks() -> dict[str, Any]:
    """Busca o JWKS do Better Auth e guarda em cache por 1 hora."""
    global _jwks_cache
    now = time.monotonic()
    cached = _jwks_cache
    if cached is not None and now - cached[0] < JWKS_TTL_SECONDS:
        return cached[1]

    with _JWKS_LOCK:
        cached = _jwks_cache
        if cached is not None and now - cached[0] < JWKS_TTL_SECONDS:
            return cached[1]
        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.get(settings.better_auth_jwks_url)
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise _unauthorized() from exc
        if not isinstance(payload, dict):
            raise _unauthorized()
        _jwks_cache = (time.monotonic(), payload)
        return payload


def clear_jwks_cache() -> None:
    global _jwks_cache
    with _JWKS_LOCK:
        _jwks_cache = None


def get_current_user(
    authorization: Annotated[str | None, Header()] = None,
) -> CurrentUser:
    """Valida o Bearer JWT (RS256 + JWKS) e exige o email do dono."""
    token = _bearer_token(authorization)
    try:
        signing_key = _signing_key(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            options={"require": ["exp"]},
        )
    except jwt.PyJWTError as exc:
        raise _unauthorized() from exc

    email = str(claims.get("email") or "").strip()
    owner = (settings.owner_email or "").strip()
    if not owner or email.lower() != owner.lower():
        raise _unauthorized()

    subject = str(claims.get("sub") or "").strip()
    return CurrentUser(email=email, subject=subject)


def _bearer_token(authorization: str | None) -> str:
    if not authorization:
        raise _unauthorized()
    scheme, _, credentials = authorization.partition(" ")
    if scheme.lower() != "bearer" or not credentials.strip():
        raise _unauthorized()
    return credentials.strip()


def _signing_key(token: str) -> jwt.PyJWK:
    try:
        header = jwt.get_unverified_header(token)
    except jwt.PyJWTError as exc:
        raise _unauthorized() from exc
    kid = header.get("kid")
    jwks = get_jwks()
    keys = jwks.get("keys")
    if not isinstance(keys, list):
        raise _unauthorized()
    for key_data in keys:
        if not isinstance(key_data, dict):
            continue
        if kid and key_data.get("kid") not in (None, kid):
            continue
        alg = key_data.get("alg")
        if alg and alg != "RS256":
            continue
        try:
            return jwt.PyJWK.from_dict(key_data)
        except jwt.PyJWTError:
            continue
    raise _unauthorized()
