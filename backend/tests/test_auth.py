import json
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from jwt.algorithms import RSAAlgorithm

from app.core import auth as auth_mod
from app.core.auth import clear_jwks_cache, get_current_user, get_jwks


def _rsa_private_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _public_jwk(private_key, kid: str = "test-key") -> dict:
    data = json.loads(RSAAlgorithm.to_jwk(private_key.public_key()))
    data.update({"kid": kid, "alg": "RS256", "use": "sig"})
    return data


def _encode(private_key, email: str, *, kid: str = "test-key", exp_offset: int = 60) -> str:
    now = int(time.time())
    return jwt.encode(
        {"email": email, "sub": "user-1", "exp": now + exp_offset, "iat": now},
        private_key,
        algorithm="RS256",
        headers={"kid": kid},
    )


@pytest.fixture
def owner_key(monkeypatch):
    private_key = _rsa_private_key()
    jwks = {"keys": [_public_jwk(private_key)]}
    monkeypatch.setattr(auth_mod.settings, "owner_email", "owner@example.com")
    monkeypatch.setattr(auth_mod, "get_jwks", lambda: jwks)
    clear_jwks_cache()
    return private_key


def test_missing_authorization_is_401(owner_key):
    with pytest.raises(HTTPException) as exc_info:
        get_current_user(authorization=None)
    assert exc_info.value.status_code == 401


def test_invalid_token_is_401(owner_key):
    with pytest.raises(HTTPException) as exc_info:
        get_current_user(authorization="Bearer not-a-jwt")
    assert exc_info.value.status_code == 401


def test_wrong_email_is_401(owner_key):
    token = _encode(owner_key, "intruder@example.com")
    with pytest.raises(HTTPException) as exc_info:
        get_current_user(authorization=f"Bearer {token}")
    assert exc_info.value.status_code == 401


def test_expired_token_is_401(owner_key):
    token = _encode(owner_key, "owner@example.com", exp_offset=-30)
    with pytest.raises(HTTPException) as exc_info:
        get_current_user(authorization=f"Bearer {token}")
    assert exc_info.value.status_code == 401


def test_valid_owner_token(owner_key):
    token = _encode(owner_key, "owner@example.com")
    user = get_current_user(authorization=f"Bearer {token}")
    assert user.email == "owner@example.com"
    assert user.subject == "user-1"


def test_jwks_is_cached(monkeypatch):
    calls = {"n": 0}

    def fake_client(*_args, **_kwargs):
        class _Resp:
            def raise_for_status(self) -> None:
                return None

            def json(self) -> dict:
                return {"keys": [{"kid": "cached"}]}

        class _Client:
            def __enter__(self):
                calls["n"] += 1
                return self

            def __exit__(self, *_exc) -> None:
                return None

            def get(self, _url: str):
                return _Resp()

        return _Client()

    monkeypatch.setattr(auth_mod.settings, "better_auth_jwks_url", "https://example.test/jwks")
    monkeypatch.setattr(auth_mod.httpx, "Client", fake_client)
    clear_jwks_cache()
    first = get_jwks()
    second = get_jwks()
    assert first == second == {"keys": [{"kid": "cached"}]}
    assert calls["n"] == 1
