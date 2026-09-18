"""Identity-provider constants and the env-driven auth settings.

The Entra identifiers are PUBLIC (they appear in every auth redirect URL) and
are committed on purpose; they are the same registration the email-search
add-in uses (email-search-addin/ui/lib/msal-config.ts). Secrets and the rollout
switch come from the environment and are read at call time so a test can
monkeypatch them and so a Railway env change needs no code change.
"""

from __future__ import annotations

import os

AAD_TENANT_ID = "8c535dde-8170-4909-8edc-40bbff4924ba"
AAD_CLIENT_ID = "2b180b8a-7cd3-40b2-83dd-8338103ce41e"
# The scope exposed on the registration ("Expose an API"). Browser apps request
# api://<client-id>/access_as_user and the access token they get is what we verify.
AAD_API_SCOPE = "access_as_user"

AAD_JWKS_URL = f"https://login.microsoftonline.com/{AAD_TENANT_ID}/discovery/v2.0/keys"
# v2.0 issuer (accessTokenAcceptedVersion=2 in the manifest) first; the v1 form
# is accepted as a safety net in case that manifest change is missed.
AAD_ISSUERS = (
    f"https://login.microsoftonline.com/{AAD_TENANT_ID}/v2.0",
    f"https://sts.windows.net/{AAD_TENANT_ID}/",
)
# aud is the App ID URI or the bare client id depending on how the token was requested.
AAD_AUDIENCES = (f"api://{AAD_CLIENT_ID}", AAD_CLIENT_ID)

TENANT_EMAIL_DOMAIN = "firedynamicsgroup.com"

# Password-fallback session tokens are minted and verified here, never by Entra.
SESSION_ISSUER = "fdg-backend"
SESSION_TTL_SECONDS = 60 * 60 * 24 * 7

AUTH_MODES = ("off", "log", "enforce")


def auth_mode() -> str:
    """off: never look at the header. log: verify when present, never reject.
    enforce: 401 without a valid token. Anything unrecognised is treated as
    log, so a typo in the Railway env cannot lock everyone out."""
    mode = os.environ.get("AUTH_MODE", "log").strip().lower()
    return mode if mode in AUTH_MODES else "log"


def auth_secret() -> str:
    """HMAC key for password-fallback session tokens. Rotating it logs every
    password session out (a feature). Unset disables those tokens entirely."""
    return os.environ.get("AUTH_SECRET", "")


def app_password() -> str:
    """The shared fallback password. Unset disables the fallback: /auth/password
    returns 503 and /auth/config tells the sign-in screen to hide the form."""
    return os.environ.get("APP_PASSWORD", "")
