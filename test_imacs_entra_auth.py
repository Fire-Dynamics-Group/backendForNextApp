"""FD Microsoft sign-in on /imacs/*, with the shared app key kept as a fallback.

The desktop app sends Authorization: Bearer <Entra token> for the same
registration Upload Canvas and Mail Marshal already use. A valid FD tenant
user is accepted even when IMACS_APP_KEY is unset. X-IMACS-App-Key still
works for older builds, and only on these routes.
"""
from __future__ import annotations

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from auth.config import AAD_CLIENT_ID
from auth.imacs import require_imacs_app
from test_auth import _FakeJwks, entra_token
import auth.entra as entra


APP_KEY = "test-imacs-app-key-not-a-real-secret"


@pytest.fixture
def api(monkeypatch, rsa_keys):
    private_pem, public = rsa_keys
    monkeypatch.setattr(entra, "_jwks", _FakeJwks(public))
    monkeypatch.setenv("IMACS_APP_KEY", APP_KEY)
    app = FastAPI()

    @app.get("/imacs/projects", dependencies=[Depends(require_imacs_app)])
    def projects():
        return []

    return TestClient(app), private_pem


@pytest.fixture(scope="module")
def rsa_keys():
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    return private_pem, private.public_key()


def test_fd_access_token_is_accepted_without_the_app_key(api):
    client, private_pem = api
    res = client.get("/imacs/projects", headers={"Authorization": f"Bearer {entra_token(private_pem)}"})
    assert res.status_code == 200
    assert res.json() == []


def test_fd_id_token_is_accepted_without_the_app_key(api):
    client, private_pem = api
    token = entra_token(private_pem, aud=AAD_CLIENT_ID, scp=None)
    res = client.get("/imacs/projects", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200


def test_fd_token_works_when_the_shared_key_is_unset(api, monkeypatch):
    client, private_pem = api
    monkeypatch.delenv("IMACS_APP_KEY", raising=False)
    res = client.get(
        "/imacs/projects",
        headers={"Authorization": f"Bearer {entra_token(private_pem)}"},
    )
    assert res.status_code == 200


def test_foreign_account_is_not_authorised(api):
    client, private_pem = api
    token = entra_token(private_pem, preferred_username="guest@example.com")
    res = client.get("/imacs/projects", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 401
    assert res.json()["detail"] == "Not authorised."


def test_bad_signature_is_not_authorised(api):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    client, _private_pem = api
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    other_pem = other.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    res = client.get(
        "/imacs/projects",
        headers={"Authorization": f"Bearer {entra_token(other_pem)}"},
    )
    assert res.status_code == 401
    assert res.json()["detail"] == "Not authorised."


def test_shared_app_key_still_authorises_without_a_bearer(api):
    client, _private_pem = api
    res = client.get("/imacs/projects", headers={"X-IMACS-App-Key": APP_KEY})
    assert res.status_code == 200


def test_valid_app_key_still_works_when_the_bearer_is_rejected(api):
    client, _private_pem = api
    res = client.get(
        "/imacs/projects",
        headers={"Authorization": "Bearer not-a-jwt", "X-IMACS-App-Key": APP_KEY},
    )
    assert res.status_code == 200


def test_missing_credentials_ask_the_user_to_sign_in(api):
    client, _private_pem = api
    res = client.get("/imacs/projects")
    assert res.status_code == 401
    assert res.json()["detail"] == "Sign in to Upload Canvas."


def test_wrong_app_key_is_not_authorised(api):
    client, _private_pem = api
    res = client.get("/imacs/projects", headers={"X-IMACS-App-Key": "wrong-key"})
    assert res.status_code == 403
    assert res.json()["detail"] == "Not authorised."


def test_unset_app_key_still_fails_closed_without_a_bearer(api, monkeypatch):
    client, _private_pem = api
    monkeypatch.delenv("IMACS_APP_KEY", raising=False)
    res = client.get("/imacs/projects", headers={"X-IMACS-App-Key": APP_KEY})
    assert res.status_code == 503
    assert res.json()["detail"] == "i-macs access is not configured."
