import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ed25519, rsa
from fastapi import HTTPException

from app.core import auth as auth_mod
from app.core.auth import clear_jwks_cache, get_current_user


class _FakeSigningKey:
    def __init__(self, key, algorithm_name: str):
        self.key = key
        self.algorithm_name = algorithm_name


class _FakeJwksClient:
    def __init__(self, key, algorithm_name: str):
        self.key = key
        self.algorithm_name = algorithm_name
        self.calls = 0

    def get_signing_key_from_jwt(self, _token: str) -> _FakeSigningKey:
        self.calls += 1
        return _FakeSigningKey(self.key, self.algorithm_name)


def _rsa_private_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _encode(
    private_key,
    email: str,
    *,
    algorithm: str = "RS256",
    kid: str = "test-key",
    exp_offset: int = 60,
    extra_claims: dict | None = None,
) -> str:
    now = int(time.time())
    payload = {
        "email": email,
        "sub": "user-1",
        "exp": now + exp_offset,
        "iat": now,
        "iss": "https://scenecraft.mazting.studio",
        "aud": "https://api.mazting.studio",
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(
        payload,
        private_key,
        algorithm=algorithm,
        headers={"kid": kid},
    )


@pytest.fixture
def owner_rsa(monkeypatch):
    private_key = _rsa_private_key()
    public_key = private_key.public_key()
    client = _FakeJwksClient(public_key, "RS256")
    monkeypatch.setattr(auth_mod.settings, "owner_email", "owner@example.com")
    monkeypatch.setattr(auth_mod.settings, "better_auth_url", "https://scenecraft.mazting.studio")
    monkeypatch.setattr(auth_mod.settings, "next_public_api_url", "https://api.mazting.studio")
    monkeypatch.setattr(auth_mod, "_get_jwks_client", lambda: client)
    clear_jwks_cache()
    return private_key, client


def test_missing_authorization_is_401(owner_rsa):
    with pytest.raises(HTTPException) as exc_info:
        get_current_user(authorization=None)
    assert exc_info.value.status_code == 401


def test_invalid_token_is_401(owner_rsa):
    with pytest.raises(HTTPException) as exc_info:
        get_current_user(authorization="Bearer not-a-jwt")
    assert exc_info.value.status_code == 401


def test_wrong_email_is_401(owner_rsa):
    private_key, _client = owner_rsa
    token = _encode(private_key, "intruder@example.com")
    with pytest.raises(HTTPException) as exc_info:
        get_current_user(authorization=f"Bearer {token}")
    assert exc_info.value.status_code == 401


def test_expired_token_is_401(owner_rsa):
    private_key, _client = owner_rsa
    token = _encode(private_key, "owner@example.com", exp_offset=-30)
    with pytest.raises(HTTPException) as exc_info:
        get_current_user(authorization=f"Bearer {token}")
    assert exc_info.value.status_code == 401


def test_valid_owner_token_with_aud_and_iss(owner_rsa):
    private_key, _client = owner_rsa
    token = _encode(private_key, "owner@example.com")
    user = get_current_user(authorization=f"Bearer {token}")
    assert user.email == "owner@example.com"
    assert user.subject == "user-1"


def test_nested_user_email_claim(owner_rsa):
    private_key, _client = owner_rsa
    token = _encode(
        private_key,
        "",
        extra_claims={"email": "", "user": {"email": "owner@example.com"}},
    )
    user = get_current_user(authorization=f"Bearer {token}")
    assert user.email == "owner@example.com"


def test_wrong_audience_is_401(owner_rsa):
    private_key, _client = owner_rsa
    token = _encode(
        private_key,
        "owner@example.com",
        extra_claims={"aud": "https://wrong.example"},
    )
    with pytest.raises(HTTPException) as exc_info:
        get_current_user(authorization=f"Bearer {token}")
    assert exc_info.value.status_code == 401


def test_token_with_aud_still_works_when_audience_unset(monkeypatch):
    private_key = _rsa_private_key()
    client = _FakeJwksClient(private_key.public_key(), "RS256")
    monkeypatch.setattr(auth_mod.settings, "owner_email", "owner@example.com")
    monkeypatch.setattr(auth_mod.settings, "better_auth_url", "")
    monkeypatch.setattr(auth_mod.settings, "next_public_api_url", "")
    monkeypatch.setattr(auth_mod, "_get_jwks_client", lambda: client)
    token = _encode(private_key, "owner@example.com")
    user = get_current_user(authorization=f"Bearer {token}")
    assert user.email == "owner@example.com"


def test_eddsa_token(monkeypatch):
    private_key = ed25519.Ed25519PrivateKey.generate()
    client = _FakeJwksClient(private_key.public_key(), "EdDSA")
    monkeypatch.setattr(auth_mod.settings, "owner_email", "owner@example.com")
    monkeypatch.setattr(auth_mod.settings, "better_auth_url", "https://scenecraft.mazting.studio")
    monkeypatch.setattr(auth_mod.settings, "next_public_api_url", "https://api.mazting.studio")
    monkeypatch.setattr(auth_mod, "_get_jwks_client", lambda: client)
    token = _encode(private_key, "owner@example.com", algorithm="EdDSA")
    user = get_current_user(authorization=f"Bearer {token}")
    assert user.email == "owner@example.com"


def test_jwks_client_is_reused_for_signing_keys(owner_rsa):
    private_key, client = owner_rsa
    token = _encode(private_key, "owner@example.com")
    get_current_user(authorization=f"Bearer {token}")
    get_current_user(authorization=f"Bearer {token}")
    assert client.calls == 2
