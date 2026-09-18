"""Verify a Microsoft Entra access token issued for our exposed API scope.

Mirrors email-search-addin/ui/lib/msauth.ts: signature checked against the
tenant's published JWKS, issuer and audience pinned, and the signed-in account
must be an FDG address (the issuer pin already limits us to the tenant; the
domain check is belt-and-braces against guest accounts with foreign UPNs).

PyJWKClient caches the key set and refetches on an unknown kid, which covers
Microsoft's routine signing-key rollovers.
"""

from __future__ import annotations

from dataclasses import dataclass

import jwt
from jwt import PyJWKClient

from auth.config import (
    AAD_API_SCOPE,
    AAD_AUDIENCES,
    AAD_ISSUERS,
    AAD_JWKS_URL,
    TENANT_EMAIL_DOMAIN,
)

# Module-level so keys are fetched once per process. Tests replace this.
_jwks = PyJWKClient(AAD_JWKS_URL, cache_keys=True, lifespan=6 * 3600)


class TokenError(Exception):
    """Any verification failure. One class on purpose: the distinctions matter
    in server logs, not to a sign-in screen."""


@dataclass(frozen=True)
class Identity:
    email: str
    name: str
    oid: str | None = None
    # "microsoft" for an Entra token, "password" for a fallback session token.
    via: str = "microsoft"


def is_tenant_email(email: str | None) -> bool:
    return bool(email) and email.lower().endswith(f"@{TENANT_EMAIL_DOMAIN}")


def verify_entra_token(token: str) -> Identity:
    """Raise TokenError on any failure; return the verified identity."""
    try:
        key = _jwks.get_signing_key_from_jwt(token).key
        claims = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            audience=list(AAD_AUDIENCES),
            issuer=list(AAD_ISSUERS),
            options={"require": ["exp", "iss", "aud", "sub"]},
        )
    except jwt.PyJWTError as e:
        raise TokenError(f"entra token rejected: {type(e).__name__}: {e}") from e

    # Once the Entra registration exposes access_as_user, Canvas sends an API
    # access token and we require that scope. Until then it sends an ID token
    # issued specifically to this same client (Mail Marshal's working SSO
    # configuration), which has no scp but still has the pinned audience.
    scopes = set(str(claims.get("scp") or "").split())
    is_identity_token_for_client = not scopes and claims.get("aud") == AAD_AUDIENCES[1]
    if AAD_API_SCOPE not in scopes and not is_identity_token_for_client:
        raise TokenError(
            f"entra token missing scope {AAD_API_SCOPE!r} (scp={claims.get('scp')!r})"
        )

    # preferred_username is the UPN; email / upn are fallbacks some token
    # shapes populate instead.
    raw = claims.get("preferred_username") or claims.get("email") or claims.get("upn") or ""
    email = str(raw).lower()
    if not is_tenant_email(email):
        raise TokenError(
            f"signed-in account {email or '(no email claim)'} is not an FDG address"
        )

    name = claims.get("name")
    if not isinstance(name, str) or not name:
        name = email.split("@")[0]
    oid = claims.get("oid")
    return Identity(email=email, name=name, oid=oid if isinstance(oid, str) and oid else None, via="microsoft")
