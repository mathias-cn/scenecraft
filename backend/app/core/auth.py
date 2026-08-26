"""Autenticação JWT (Better Auth) via JWKS (URL interna em BETTER_AUTH_JWKS_URL)."""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import Annotated, Any

import jwt
from fastapi import Header, HTTPException, status

from app.core.config import settings

logger = logging.getLogger(__name__)

JWKS_TTL_SECONDS = 3600
ALLOWED_ALGORITHMS = frozenset({"RS256", "EdDSA", "ES256", "ES512", "PS256"})

_JWKS_LOCK = threading.Lock()
_jwks_client: jwt.PyJWKClient | None = None
_jwks_client_url: str | None = None


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


def _get_jwks_client() -> jwt.PyJWKClient:
    """PyJWKClient com cache do JWKS (TTL 1h). Recria se a URL mudar."""
    global _jwks_client, _jwks_client_url
    url = (settings.better_auth_jwks_url or "").strip()
    if not url:
        logger.warning("auth failed: BETTER_AUTH_JWKS_URL is not configured")
        raise _unauthorized()
    with _JWKS_LOCK:
        if _jwks_client is None or _jwks_client_url != url:
            _jwks_client = jwt.PyJWKClient(
                url,
                cache_jwk_set=True,
                lifespan=JWKS_TTL_SECONDS,
                timeout=10,
            )
            _jwks_client_url = url
        return _jwks_client


def clear_jwks_cache() -> None:
    global _jwks_client, _jwks_client_url
    with _JWKS_LOCK:
        _jwks_client = None
        _jwks_client_url = None


def get_current_user(
    authorization: Annotated[str | None, Header()] = None,
) -> CurrentUser:
    """Valida o Bearer JWT via JWKS (alg da chave) e exige o email do dono."""
    if not authorization:
        logger.warning("auth failed: missing Authorization header")
        raise _unauthorized()
    token = _bearer_token(authorization)
    try:
        claims = _decode_token(token)
    except jwt.PyJWTError as exc:
        logger.warning("auth failed: %s", type(exc).__name__)
        raise _unauthorized() from exc

    email = _email_from_claims(claims)
    owner = (settings.owner_email or "").strip()
    if not owner:
        logger.warning("auth failed: OWNER_EMAIL is not configured")
        raise _unauthorized()
    if email.lower() != owner.lower():
        logger.warning("auth failed: email claim does not match owner")
        raise _unauthorized()

    subject = str(claims.get("sub") or claims.get("id") or "").strip()
    return CurrentUser(email=email, subject=subject)


def _decode_token(token: str) -> dict[str, Any]:
    client = _get_jwks_client()
    signing_key = client.get_signing_key_from_jwt(token)
    algorithm = signing_key.algorithm_name
    if algorithm not in ALLOWED_ALGORITHMS:
        raise jwt.InvalidAlgorithmError("Unsupported signing algorithm")

    issuer = (settings.better_auth_url or "").strip()
    audience = (settings.next_public_api_url or "").strip()
    options: dict[str, Any] = {"require": ["exp"]}
    decode_kwargs: dict[str, Any] = {
        "algorithms": [algorithm],
        "options": options,
        "leeway": 30,
    }
    if issuer:
        decode_kwargs["issuer"] = issuer
    else:
        options["verify_iss"] = False
    if audience:
        decode_kwargs["audience"] = audience
    else:
        # PyJWT 2.13+ rejeita tokens com `aud` se audience= não for passado.
        options["verify_aud"] = False

    claims = jwt.decode(token, signing_key.key, **decode_kwargs)
    if not isinstance(claims, dict):
        raise jwt.InvalidTokenError("JWT payload must be an object")
    return claims


def _bearer_token(authorization: str) -> str:
    scheme, _, credentials = authorization.partition(" ")
    if scheme.lower() != "bearer" or not credentials.strip():
        logger.warning("auth failed: malformed Authorization header")
        raise _unauthorized()
    return credentials.strip()


def _email_from_claims(claims: dict[str, Any]) -> str:
    email = claims.get("email")
    if isinstance(email, str) and email.strip():
        return email.strip()
    user = claims.get("user")
    if isinstance(user, dict):
        nested = user.get("email")
        if isinstance(nested, str) and nested.strip():
            return nested.strip()
    return ""
