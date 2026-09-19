import json
import time
from types import SimpleNamespace
from typing import Annotated, Any

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from google.auth import crypt, jwt
from google.auth import exceptions as google_exceptions

from app.core.auth import (
    TokenVerifier,
    get_current_attorney,
    get_token_verifier,
    make_google_verifier,
)
from app.core.config import Settings, get_settings

CLIENT_ID = "test-client-id.apps.googleusercontent.com"
KEY_ID = "test-key-1"


def _new_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _private_pem(key: rsa.RSAPrivateKey) -> bytes:
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )


def _public_pem(key: rsa.RSAPrivateKey) -> str:
    return (
        key.public_key()
        .public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode()
    )


@pytest.fixture(scope="module")
def google_key() -> rsa.RSAPrivateKey:
    return _new_key()


@pytest.fixture(scope="module")
def other_key() -> rsa.RSAPrivateKey:
    return _new_key()


def make_token(
    key: rsa.RSAPrivateKey, expires_in: int = 3600, **claim_overrides: Any
) -> str:
    """A Google-style ID token signed with `key`; a None override drops the claim."""
    now = int(time.time())
    claims: dict[str, Any] = {
        "iss": "https://accounts.google.com",
        "aud": CLIENT_ID,
        "sub": "1234567890",
        "email": "One@Firm.Example",
        "email_verified": True,
        "iat": now - 10,
        "exp": now + expires_in,
    }
    claims.update(claim_overrides)
    claims = {k: v for k, v in claims.items() if v is not None}
    signer = crypt.RSASigner.from_string(_private_pem(key), key_id=KEY_ID)
    return jwt.encode(signer, claims).decode()


def certs_request(key: rsa.RSAPrivateKey):
    """A stand-in for the HTTP call that fetches Google's signing certificates."""

    def request(url: str, method: str = "GET", **kwargs: Any) -> SimpleNamespace:
        body = json.dumps({KEY_ID: _public_pem(key)}).encode()
        return SimpleNamespace(status=200, data=body, headers={})

    return request


def make_client(verifier: TokenVerifier) -> TestClient:
    settings = Settings(
        _env_file=None,
        database_url="sqlite://",
        frontend_origin="http://localhost:3000",
        resume_storage_dir="./r",
        resume_max_bytes=1024,
        google_client_id=CLIENT_ID,
        attorney_emails="one@firm.example, Two@Firm.Example",
        email_from="no-reply@firm.example",
    )
    app = FastAPI()
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_token_verifier] = lambda: verifier

    @app.get("/me")
    def me(attorney: Annotated[str, Depends(get_current_attorney)]) -> dict:
        return {"email": attorney}

    @app.post("/echo")
    def echo(body: dict, attorney: Annotated[str, Depends(get_current_attorney)]) -> dict:
        return {"attorney": attorney, "body": body}

    return TestClient(app)


@pytest.fixture
def client(google_key: rsa.RSAPrivateKey) -> TestClient:
    return make_client(make_google_verifier(certs_request(google_key)))


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# Happy path


def test_valid_attorney_token_returns_the_lowercased_email(
    client: TestClient, google_key: rsa.RSAPrivateKey
) -> None:
    response = client.get("/me", headers=bearer(make_token(google_key)))

    assert response.status_code == 200
    assert response.json() == {"email": "one@firm.example"}


def test_allowlist_matching_ignores_case_on_both_sides(
    client: TestClient, google_key: rsa.RSAPrivateKey
) -> None:
    token = make_token(google_key, email="TWO@firm.example")
    assert client.get("/me", headers=bearer(token)).json() == {"email": "two@firm.example"}


# 401: not authenticated


def test_missing_header_returns_401(client: TestClient) -> None:
    response = client.get("/me")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_non_bearer_scheme_returns_401(client: TestClient) -> None:
    assert client.get("/me", headers={"Authorization": "Basic dXNlcjpwdw=="}).status_code == 401


def test_garbage_token_returns_401(client: TestClient) -> None:
    assert client.get("/me", headers=bearer("not-a-jwt")).status_code == 401


@pytest.mark.parametrize(
    "overrides",
    [
        {"exp": int(time.time()) - 3600, "iat": int(time.time()) - 7200},
        {"aud": "some-other-client-id"},
        {"iss": "https://evil.example"},
    ],
    ids=["expired", "wrong-audience", "wrong-issuer"],
)
def test_invalid_claims_return_401(
    client: TestClient, google_key: rsa.RSAPrivateKey, overrides: dict
) -> None:
    response = client.get("/me", headers=bearer(make_token(google_key, **overrides)))
    assert response.status_code == 401


def test_token_signed_by_a_different_key_returns_401(
    client: TestClient, other_key: rsa.RSAPrivateKey
) -> None:
    assert client.get("/me", headers=bearer(make_token(other_key))).status_code == 401


@pytest.mark.parametrize(
    "overrides",
    [{"email_verified": False}, {"email_verified": None}, {"email": None}, {"email": ""}],
    ids=["unverified", "no-verified-claim", "no-email", "empty-email"],
)
def test_unverified_or_missing_email_returns_401(
    client: TestClient, google_key: rsa.RSAPrivateKey, overrides: dict
) -> None:
    response = client.get("/me", headers=bearer(make_token(google_key, **overrides)))
    assert response.status_code == 401


# 403: authenticated but not an attorney


def test_verified_email_not_on_the_allowlist_returns_403(
    client: TestClient, google_key: rsa.RSAPrivateKey
) -> None:
    token = make_token(google_key, email="stranger@example.com")
    assert client.get("/me", headers=bearer(token)).status_code == 403


# Availability


def test_failure_to_reach_google_returns_503_not_401(
    google_key: rsa.RSAPrivateKey,
) -> None:
    def unreachable(url: str, method: str = "GET", **kwargs: Any):
        raise google_exceptions.TransportError("network down")

    client = make_client(make_google_verifier(unreachable))
    response = client.get("/me", headers=bearer(make_token(google_key)))

    assert response.status_code == 503


# Identity only from the token


def test_identity_in_the_body_is_ignored(
    client: TestClient, google_key: rsa.RSAPrivateKey
) -> None:
    response = client.post(
        "/echo",
        json={"email": "two@firm.example", "reached_out_by": "two@firm.example"},
        headers=bearer(make_token(google_key)),
    )

    assert response.status_code == 200
    assert response.json()["attorney"] == "one@firm.example"


def test_identity_in_the_body_does_not_authenticate(client: TestClient) -> None:
    response = client.post("/echo", json={"email": "one@firm.example"})
    assert response.status_code == 401
