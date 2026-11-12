"""Gate for the i-macs desktop routes (`/imacs/*`).

Staff sign in with the FD Microsoft Entra app that Upload Canvas and Mail
Marshal already use. The desktop sends that token as
`Authorization: Bearer`. `verify_entra_token` checks the signature, issuer,
audience, and that the account is an `@firedynamicsgroup.com` user.

The shared `X-IMACS-App-Key` header (env `IMACS_APP_KEY`) is still accepted
so an older desktop build keeps working. It is not required when the bearer
token is valid, including when the env var is unset.

    router = APIRouter(dependencies=[Depends(require_imacs_app)])

  valid FD bearer                 200  (app key not consulted)
  valid app key, bearer absent    200
  valid app key, bearer rejected  200  older clients that also send a key
  bearer rejected, no valid key   401  Not authorised.
  nothing sent, key configured    401  Sign in to Upload Canvas.
  wrong app key                   403  Not authorised.
  key unset, no valid bearer      503  i-macs access is not configured.

The key is compared with hmac.compare_digest. Browser routes stay on
`auth.deps.current_user`.
"""

from __future__ import annotations

import hmac
import logging
import os

from fastapi import Depends, Header, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from auth.entra import Identity, TokenError, verify_entra_token

log = logging.getLogger("auth")

HEADER_NAME = "X-IMACS-App-Key"
_bearer = HTTPBearer(auto_error=False)


def require_imacs_app(
    request: Request,
    x_imacs_app_key: str | None = Header(default=None, alias=HEADER_NAME),
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> Identity | None:
    bearer_failed = False
    if creds is not None and creds.credentials:
        try:
            identity = verify_entra_token(creds.credentials)
        except TokenError as exc:
            log.warning("auth: i-macs bearer rejected: %s", exc)
            bearer_failed = True
        else:
            log.info("auth: i-macs %s via microsoft", identity.email)
            request.state.user = identity
            return identity

    expected = os.environ.get("IMACS_APP_KEY", "")
    presented = x_imacs_app_key or ""
    if expected and presented and hmac.compare_digest(
        presented.encode("utf-8"), expected.encode("utf-8")
    ):
        return None

    if bearer_failed:
        raise HTTPException(
            status_code=401,
            detail="Not authorised.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not expected:
        log.error("auth: IMACS_APP_KEY is not set; rejecting i-macs request")
        raise HTTPException(status_code=503, detail="i-macs access is not configured.")
    if not presented:
        raise HTTPException(
            status_code=401,
            detail="Sign in to Upload Canvas.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    raise HTTPException(status_code=403, detail="Not authorised.")
