"""Backend-minted session tokens for the shared-password fallback.

Same idea as the email-search add-in's fdg_auth cookie, but issued as a bearer
token so browser clients handle it exactly like a Microsoft token (one code
path on the client, two verifiers here). HS256 with AUTH_SECRET.
"""

from __future__ import annotations

import hmac
import time

import jwt

from auth.config import (
    SESSION_ISSUER,
    SESSION_TTL_SECONDS,
    app_password,
    auth_secret,
)
from auth.entra import Identity, TokenError, is_tenant_email


def password_fallback_enabled() -> bool:
    """Both the password and the signing secret must be set."""
    return bool(app_password()) and bool(auth_secret())


def check_password(candidate: str) -> bool:
    """Fails closed when APP_PASSWORD is unset."""
    expected = app_password()
    return bool(expected) and hmac.compare_digest(candidate, expected)


def mint_session_token(identity: Identity) -> str:
    now = int(time.time())
    return jwt.encode(
        {
            "iss": SESSION_ISSUER,
            "sub": identity.email,
            "name": identity.name,
            "iat": now,
            "exp": now + SESSION_TTL_SECONDS,
        },
        auth_secret(),
        algorithm="HS256",
    )


def verify_session_token(token: str) -> Identity:
    """Raise TokenError on any failure; return the identity the token carries."""
    secret = auth_secret()
    if not secret:
        raise TokenError("AUTH_SECRET not configured; session tokens disabled")
    try:
        claims = jwt.decode(
            token,
            secret,
            algorithms=["HS256"],
            issuer=SESSION_ISSUER,
            options={"require": ["exp", "sub"]},
        )
    except jwt.PyJWTError as e:
        raise TokenError(f"session token rejected: {type(e).__name__}: {e}") from e

    email = str(claims["sub"]).lower()
    if not is_tenant_email(email):
        raise TokenError(f"session token for non-FDG address {email}")

    name = claims.get("name")
    if not isinstance(name, str) or not name:
        name = email.split("@")[0]
    return Identity(email=email, name=name, via="password")


def issuer_of(token: str) -> str | None:
    """Peek at `iss` WITHOUT verifying. Only ever used to choose which
    verifier runs; nothing is trusted until that verifier passes."""
    try:
        claims = jwt.decode(token, options={"verify_signature": False})
    except jwt.PyJWTError:
        return None
    iss = claims.get("iss")
    return iss if isinstance(iss, str) else None
