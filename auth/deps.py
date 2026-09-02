"""`current_user`: who is calling, verified.

    @router.get("/thing")
    def thing(user: Identity | None = Depends(current_user)): ...

or, for a whole router at include time:

    app.include_router(r, prefix="/x", dependencies=[Depends(current_user)])

Rollout is controlled by AUTH_MODE (see auth/config.py):

  off      never inspect the header; user is None everywhere (today's behaviour)
  log      verify when a token is present, log the outcome, never reject
  enforce  401 without a valid token

Sync functions on purpose: PyJWKClient does blocking I/O on a key-cache miss
and FastAPI runs sync dependencies in the threadpool.
"""

from __future__ import annotations

import logging

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from auth.config import SESSION_ISSUER, auth_mode
from auth.entra import Identity, TokenError, verify_entra_token
from auth.session import issuer_of, verify_session_token

log = logging.getLogger("auth")

# auto_error=False: a missing or non-Bearer Authorization header yields None
# rather than an immediate 403, so off/log modes can wave it through.
_bearer = HTTPBearer(auto_error=False)


def verify_bearer(token: str) -> Identity:
    """Pick the verifier by issuer. Our own session tokens are the only
    non-Entra issuer; everything else must satisfy the Entra checks."""
    if issuer_of(token) == SESSION_ISSUER:
        return verify_session_token(token)
    return verify_entra_token(token)


def optional_user(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> Identity | None:
    """The verified caller, or None. Rejects (401) only in enforce mode and
    only when a token was presented and failed; a missing token is left to
    `current_user` to judge."""
    mode = auth_mode()
    if mode == "off":
        return None
    if creds is None:
        log.debug("auth: no token on %s %s", request.method, request.url.path)
        return None
    try:
        identity = verify_bearer(creds.credentials)
    except TokenError as e:
        log.warning("auth: rejected token on %s %s: %s", request.method, request.url.path, e)
        if mode == "enforce":
            raise HTTPException(
                status_code=401,
                detail="Sign-in could not be verified.",
                headers={"WWW-Authenticate": "Bearer"},
            ) from e
        return None
    log.info(
        "auth: %s via %s on %s %s", identity.email, identity.via, request.method, request.url.path
    )
    request.state.user = identity
    return identity


def current_user(identity: Identity | None = Depends(optional_user)) -> Identity | None:
    """Required identity once AUTH_MODE=enforce; None (never 401) in off/log so
    nothing changes for callers until the switch is flipped."""
    if identity is None and auth_mode() == "enforce":
        raise HTTPException(
            status_code=401,
            detail="Authentication required.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return identity
