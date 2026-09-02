"""Tests for auth/ - who is calling this backend, verified.

Toolstation, upload-canvas and the other Vercel apps call this backend directly
from the browser, so the backend is the security boundary (the email-search
add-in's cookie-behind-a-proxy model does not transplant). Every browser app
sends `Authorization: Bearer <token>` where the token is either

  - a Microsoft Entra access token for our exposed API scope, verified RS256
    against the tenant JWKS, or
  - a backend-minted HS256 session token from the shared-password fallback.

`current_user` routes between the two by issuer. AUTH_MODE gates rollout:
off / log never reject a request; only enforce returns 401.

Entra verification is tested hermetically: a throwaway RSA key stands in for
Microsoft's JWKS via monkeypatching auth.entra._jwks.
"""
from __future__ import annotations

import json
import time

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

import auth.entra as entra
from auth.config import (
    AAD_CLIENT_ID,
    AAD_ISSUERS,
    SESSION_ISSUER,
    TENANT_EMAIL_DOMAIN,
)
from auth.deps import current_user
from auth.entra import Identity, TokenError, verify_entra_token
from auth.session import (
    check_password,
    issuer_of,
    mint_session_token,
    password_fallback_enabled,
    verify_session_token,
)

FDG = f"@{TENANT_EMAIL_DOMAIN}"
SECRET = "test-auth-secret-of-at-least-thirty-two-bytes"


# --------------------------------------------------------------------------
# Fixtures: a fake Microsoft signing key
# --------------------------------------------------------------------------


class _FakeKey:
    def __init__(self, key):
        self.key = key


class _FakeJwks:
    """Stands in for jwt.PyJWKClient: always returns our test public key."""

    def __init__(self, public_key):
        self._key = _FakeKey(public_key)

    def get_signing_key_from_jwt(self, token):  # noqa: ARG002 - signature parity
        return self._key


@pytest.fixture(scope="module")
def rsa_keys():
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    public = private.public_key()
    return private_pem, public


@pytest.fixture
def entra_keys(monkeypatch, rsa_keys):
    private_pem, public = rsa_keys
    monkeypatch.setattr(entra, "_jwks", _FakeJwks(public))
    return private_pem


@pytest.fixture
def auth_env(monkeypatch):
    monkeypatch.setenv("AUTH_SECRET", SECRET)
    monkeypatch.setenv("APP_PASSWORD", "hunter2")
    monkeypatch.setenv("AUTH_MODE", "enforce")


def entra_token(private_pem, **overrides) -> str:
    now = int(time.time())
    claims = {
        "iss": AAD_ISSUERS[0],
        "aud": f"api://{AAD_CLIENT_ID}",
        "sub": "abc123",
        "scp": "access_as_user",
        "preferred_username": f"sam{FDG}",
        "name": "Sam Bennett",
        "iat": now,
        "nbf": now,
        "exp": now + 3600,
    }
    for key, value in overrides.items():
        if value is None:
            claims.pop(key, None)
        else:
            claims[key] = value
    return jwt.encode(claims, private_pem, algorithm="RS256", headers={"kid": "test"})


# --------------------------------------------------------------------------
# Entra access tokens
# --------------------------------------------------------------------------


class TestVerifyEntraToken:
    def test_valid_token_yields_identity(self, entra_keys):
        identity = verify_entra_token(entra_token(entra_keys))

        assert identity == Identity(email=f"sam{FDG}", name="Sam Bennett")

    def test_upn_is_lowercased(self, entra_keys):
        token = entra_token(entra_keys, preferred_username=f"Sam{FDG.upper()}")

        assert verify_entra_token(token).email == f"sam{FDG}"

    def test_v1_issuer_accepted(self, entra_keys):
        # accessTokenAcceptedVersion left at 1 in the manifest -> sts.windows.net issuer.
        token = entra_token(entra_keys, iss=AAD_ISSUERS[1])

        assert verify_entra_token(token).email == f"sam{FDG}"

    def test_bare_client_id_audience_accepted(self, entra_keys):
        token = entra_token(entra_keys, aud=AAD_CLIENT_ID)

        assert verify_entra_token(token).email == f"sam{FDG}"

    def test_wrong_audience_rejected(self, entra_keys):
        token = entra_token(entra_keys, aud="00000003-0000-0000-c000-000000000000")

        with pytest.raises(TokenError, match="entra token rejected"):
            verify_entra_token(token)

    def test_wrong_issuer_rejected(self, entra_keys):
        token = entra_token(entra_keys, iss="https://login.microsoftonline.com/other-tenant/v2.0")

        with pytest.raises(TokenError, match="entra token rejected"):
            verify_entra_token(token)

    def test_expired_rejected(self, entra_keys):
        token = entra_token(entra_keys, exp=int(time.time()) - 120)

        with pytest.raises(TokenError, match="entra token rejected"):
            verify_entra_token(token)

    def test_wrong_signing_key_rejected(self, entra_keys):
        other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        other_pem = other.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
        token = entra_token(other_pem)

        with pytest.raises(TokenError, match="entra token rejected"):
            verify_entra_token(token)

    def test_missing_scope_rejected(self, entra_keys):
        # An ID token or a Graph token has no scp for our API; refuse it.
        token = entra_token(entra_keys, scp=None)

        with pytest.raises(TokenError, match="missing scope"):
            verify_entra_token(token)

    def test_other_scope_only_rejected(self, entra_keys):
        token = entra_token(entra_keys, scp="User.Read")

        with pytest.raises(TokenError, match="missing scope"):
            verify_entra_token(token)

    def test_foreign_upn_rejected(self, entra_keys):
        # A guest account in the tenant still carries its home UPN.
        token = entra_token(entra_keys, preferred_username="guest@example.com")

        with pytest.raises(TokenError, match="not an FDG address"):
            verify_entra_token(token)

    def test_no_email_claim_rejected(self, entra_keys):
        token = entra_token(entra_keys, preferred_username=None)

        with pytest.raises(TokenError, match="no email claim"):
            verify_entra_token(token)

    def test_email_claim_fallback(self, entra_keys):
        token = entra_token(entra_keys, preferred_username=None, email=f"thomas{FDG}")

        assert verify_entra_token(token).email == f"thomas{FDG}"

    def test_name_falls_back_to_prefix(self, entra_keys):
        token = entra_token(entra_keys, name=None, preferred_username=f"kirsty{FDG}")

        assert verify_entra_token(token).name == "kirsty"

    def test_garbage_rejected(self, entra_keys):
        with pytest.raises(TokenError):
            verify_entra_token("not.a.jwt")


# --------------------------------------------------------------------------
# Password-fallback session tokens
# --------------------------------------------------------------------------


class TestSessionToken:
    def test_round_trip(self, auth_env):
        token = mint_session_token(Identity(email=f"sam{FDG}", name="Sam Bennett"))

        assert verify_session_token(token) == Identity(
            email=f"sam{FDG}", name="Sam Bennett", via="password"
        )

    def test_issuer_is_ours(self, auth_env):
        token = mint_session_token(Identity(email=f"sam{FDG}", name="Sam"))

        assert issuer_of(token) == SESSION_ISSUER

    def test_tampered_signature_rejected(self, auth_env):
        token = mint_session_token(Identity(email=f"sam{FDG}", name="Sam"))
        head, body, sig = token.split(".")
        tampered = f"{head}.{body}.{'A' if sig[0] != 'A' else 'B'}{sig[1:]}"

        with pytest.raises(TokenError, match="session token rejected"):
            verify_session_token(tampered)

    def test_wrong_secret_rejected(self, auth_env):
        forged = jwt.encode(
            {"iss": SESSION_ISSUER, "sub": f"sam{FDG}", "exp": int(time.time()) + 60},
            "some-other-secret-also-at-least-thirty-two-bytes",
            algorithm="HS256",
        )

        with pytest.raises(TokenError, match="session token rejected"):
            verify_session_token(forged)

    def test_expired_rejected(self, auth_env):
        expired = jwt.encode(
            {"iss": SESSION_ISSUER, "sub": f"sam{FDG}", "exp": int(time.time()) - 60},
            SECRET,
            algorithm="HS256",
        )

        with pytest.raises(TokenError, match="session token rejected"):
            verify_session_token(expired)

    def test_non_fdg_subject_rejected(self, auth_env):
        forged = jwt.encode(
            {"iss": SESSION_ISSUER, "sub": "mallory@example.com", "exp": int(time.time()) + 60},
            SECRET,
            algorithm="HS256",
        )

        with pytest.raises(TokenError, match="non-FDG"):
            verify_session_token(forged)

    def test_unset_secret_disables_verification(self, auth_env, monkeypatch):
        # Minted while configured, then the secret is removed: every password
        # session must die rather than verify against an empty key.
        token = mint_session_token(Identity(email=f"sam{FDG}", name="Sam"))
        monkeypatch.delenv("AUTH_SECRET")

        with pytest.raises(TokenError, match="AUTH_SECRET"):
            verify_session_token(token)

    def test_issuer_of_entra_token(self, entra_keys):
        assert issuer_of(entra_token(entra_keys)) == AAD_ISSUERS[0]

    def test_issuer_of_garbage_is_none(self):
        assert issuer_of("nope") is None


class TestPasswordCheck:
    def test_unset_password_fails_closed(self, monkeypatch):
        monkeypatch.delenv("APP_PASSWORD", raising=False)

        assert check_password("") is False
        assert check_password("anything") is False

    def test_correct_and_incorrect(self, auth_env):
        assert check_password("hunter2") is True
        assert check_password("hunter3") is False

    def test_fallback_needs_both_secrets(self, monkeypatch):
        monkeypatch.setenv("APP_PASSWORD", "x")
        monkeypatch.delenv("AUTH_SECRET", raising=False)
        assert password_fallback_enabled() is False

        monkeypatch.setenv("AUTH_SECRET", "y")
        assert password_fallback_enabled() is True

        monkeypatch.delenv("APP_PASSWORD")
        assert password_fallback_enabled() is False


# --------------------------------------------------------------------------
# The FastAPI dependency across rollout modes
# --------------------------------------------------------------------------


def _probe_app() -> FastAPI:
    app = FastAPI()

    @app.get("/whoami")
    def whoami(user: Identity | None = Depends(current_user)):
        return {"email": None if user is None else user.email}

    return app


@pytest.fixture
def probe(monkeypatch):
    monkeypatch.setenv("AUTH_SECRET", SECRET)
    return TestClient(_probe_app())


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


class TestCurrentUserOff:
    """AUTH_MODE=off: today's behaviour, header never inspected."""

    @pytest.fixture(autouse=True)
    def _mode(self, monkeypatch):
        monkeypatch.setenv("AUTH_MODE", "off")

    def test_no_header(self, probe):
        assert probe.get("/whoami").json() == {"email": None}

    def test_bad_token_ignored(self, probe):
        res = probe.get("/whoami", headers=_bearer("garbage"))

        assert res.status_code == 200
        assert res.json() == {"email": None}

    def test_good_token_ignored(self, probe, entra_keys):
        res = probe.get("/whoami", headers=_bearer(entra_token(entra_keys)))

        assert res.json() == {"email": None}


class TestCurrentUserLog:
    """AUTH_MODE=log: verifies when a token is present, never rejects."""

    @pytest.fixture(autouse=True)
    def _mode(self, monkeypatch):
        monkeypatch.setenv("AUTH_MODE", "log")

    def test_no_header(self, probe):
        res = probe.get("/whoami")

        assert res.status_code == 200
        assert res.json() == {"email": None}

    def test_bad_token_not_rejected(self, probe, caplog):
        res = probe.get("/whoami", headers=_bearer("garbage"))

        assert res.status_code == 200
        assert res.json() == {"email": None}
        assert any("auth:" in r.getMessage() for r in caplog.records)

    def test_entra_token_identified(self, probe, entra_keys):
        res = probe.get("/whoami", headers=_bearer(entra_token(entra_keys)))

        assert res.json() == {"email": f"sam{FDG}"}

    def test_session_token_identified(self, probe):
        token = mint_session_token(Identity(email=f"joana{FDG}", name="Joana"))
        res = probe.get("/whoami", headers=_bearer(token))

        assert res.json() == {"email": f"joana{FDG}"}


class TestCurrentUserEnforce:
    """AUTH_MODE=enforce: 401 unless a valid token is presented."""

    @pytest.fixture(autouse=True)
    def _mode(self, monkeypatch):
        monkeypatch.setenv("AUTH_MODE", "enforce")

    def test_no_header_401(self, probe):
        res = probe.get("/whoami")

        assert res.status_code == 401
        assert res.headers["WWW-Authenticate"] == "Bearer"

    def test_bad_token_401(self, probe):
        assert probe.get("/whoami", headers=_bearer("garbage")).status_code == 401

    def test_non_bearer_scheme_401(self, probe):
        res = probe.get("/whoami", headers={"Authorization": "Basic abc"})

        assert res.status_code == 401

    def test_entra_token_ok(self, probe, entra_keys):
        res = probe.get("/whoami", headers=_bearer(entra_token(entra_keys)))

        assert res.status_code == 200
        assert res.json() == {"email": f"sam{FDG}"}

    def test_session_token_ok(self, probe):
        token = mint_session_token(Identity(email=f"joana{FDG}", name="Joana"))
        res = probe.get("/whoami", headers=_bearer(token))

        assert res.status_code == 200
        assert res.json() == {"email": f"joana{FDG}"}

    def test_entra_token_missing_scope_401(self, probe, entra_keys):
        res = probe.get("/whoami", headers=_bearer(entra_token(entra_keys, scp=None)))

        assert res.status_code == 401


class TestUnknownMode:
    def test_unknown_mode_treated_as_log(self, probe, monkeypatch):
        # A typo in the Railway env must not lock everyone out.
        monkeypatch.setenv("AUTH_MODE", "enfroce")

        assert probe.get("/whoami").status_code == 200


# --------------------------------------------------------------------------
# /auth routes
# --------------------------------------------------------------------------


@pytest.fixture
def roster(tmp_path, monkeypatch):
    path = tmp_path / "engineers.json"
    path.write_text(
        json.dumps(
            [
                {"full_name": "Sam Bennett", "email_prefix": "sam"},
                {"full_name": "Ian Shaw", "email_prefix": "ianshaw"},
            ]
        ),
        encoding="utf-8",
    )
    import routers.auth as auth_router

    monkeypatch.setattr(auth_router, "ENGINEERS_PATH", str(path))
    return path


@pytest.fixture
def client(monkeypatch, roster):
    from routers.auth import router

    monkeypatch.setenv("AUTH_SECRET", SECRET)
    monkeypatch.setenv("APP_PASSWORD", "hunter2")
    monkeypatch.setenv("AUTH_MODE", "enforce")
    app = FastAPI()
    app.include_router(router, prefix="/auth")
    return TestClient(app)


class TestAuthConfig:
    def test_reports_fallback_enabled(self, client):
        assert client.get("/auth/config").json() == {"password_fallback": True}

    def test_reports_fallback_disabled(self, client, monkeypatch):
        monkeypatch.delenv("APP_PASSWORD")

        assert client.get("/auth/config").json() == {"password_fallback": False}


class TestPasswordLogin:
    def test_disabled_503(self, client, monkeypatch):
        monkeypatch.delenv("APP_PASSWORD")
        res = client.post("/auth/password", json={"email": f"sam{FDG}", "password": "hunter2"})

        assert res.status_code == 503

    def test_wrong_password_401(self, client):
        res = client.post("/auth/password", json={"email": f"sam{FDG}", "password": "nope"})

        assert res.status_code == 401
        assert res.json()["detail"] == "Incorrect password."

    def test_non_fdg_email_400(self, client):
        res = client.post("/auth/password", json={"email": "x@example.com", "password": "hunter2"})

        assert res.status_code == 400

    def test_success_returns_verifiable_token_and_roster_name(self, client):
        res = client.post("/auth/password", json={"email": f"Sam{FDG}", "password": "hunter2"})

        assert res.status_code == 200
        body = res.json()
        assert body["email"] == f"sam{FDG}"
        assert body["name"] == "Sam Bennett"
        assert verify_session_token(body["token"]) == Identity(
            email=f"sam{FDG}", name="Sam Bennett", via="password"
        )

    def test_unknown_prefix_falls_back_to_prefix_as_name(self, client):
        res = client.post("/auth/password", json={"email": f"newstarter{FDG}", "password": "hunter2"})

        assert res.status_code == 200
        assert res.json()["name"] == "newstarter"

    def test_roster_file_missing_still_signs_in(self, client, roster):
        roster.unlink()
        res = client.post("/auth/password", json={"email": f"sam{FDG}", "password": "hunter2"})

        assert res.status_code == 200
        assert res.json()["name"] == "sam"


class TestMe:
    def test_anonymous_401_in_enforce(self, client):
        assert client.get("/auth/me").status_code == 401

    def test_anonymous_null_in_log(self, client, monkeypatch):
        monkeypatch.setenv("AUTH_MODE", "log")

        assert client.get("/auth/me").json() is None

    def test_session_token_identifies(self, client):
        login = client.post("/auth/password", json={"email": f"ianshaw{FDG}", "password": "hunter2"})
        res = client.get("/auth/me", headers=_bearer(login.json()["token"]))

        assert res.json() == {"email": f"ianshaw{FDG}", "name": "Ian Shaw", "via": "password"}

    def test_entra_token_identifies(self, client, entra_keys):
        res = client.get("/auth/me", headers=_bearer(entra_token(entra_keys)))

        assert res.json() == {"email": f"sam{FDG}", "name": "Sam Bennett", "via": "microsoft"}
