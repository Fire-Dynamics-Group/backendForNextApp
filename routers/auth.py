"""/auth: the shared-password fallback and a whoami.

Microsoft sign-in needs no route here: the browser gets its token from Entra
and simply sends it as a bearer. This router exists for the fallback the
sign-in screen offers underneath the Microsoft button, and for the screen to
learn whether that fallback is switched on.
"""

from __future__ import annotations

import json
import os

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth.deps import current_user
from auth.entra import Identity, is_tenant_email
from auth.session import (
    check_password,
    mint_session_token,
    password_fallback_enabled,
)

router = APIRouter()

# The fee-proposal engineer roster doubles as the "who are you?" list; it is
# the list the email-search add-in copied its USERS from.
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENGINEERS_PATH = os.path.join(_BASE_DIR, "data", "engineers.json")


class PasswordLogin(BaseModel):
    email: str
    password: str


def _roster_name(prefix: str) -> str:
    """Display name for an address prefix from the roster, else the prefix.
    A missing or malformed roster must never block sign-in."""
    try:
        with open(ENGINEERS_PATH, encoding="utf-8") as f:
            roster = json.load(f)
        for entry in roster:
            if str(entry.get("email_prefix", "")).lower() == prefix:
                return str(entry.get("full_name") or prefix)
    except (OSError, ValueError):
        pass
    return prefix


@router.get("/config")
def auth_config():
    """What the sign-in screen should offer. Nothing secret here."""
    return {"password_fallback": password_fallback_enabled()}


@router.post("/password")
def password_login(body: PasswordLogin):
    if not password_fallback_enabled():
        raise HTTPException(status_code=503, detail="Password sign-in is not enabled.")
    email = body.email.strip().lower()
    if not is_tenant_email(email):
        raise HTTPException(status_code=400, detail="Choose your name from the list.")
    if not check_password(body.password):
        raise HTTPException(status_code=401, detail="Incorrect password.")

    prefix = email.split("@")[0]
    identity = Identity(email=email, name=_roster_name(prefix), via="password")
    return {"token": mint_session_token(identity), "email": identity.email, "name": identity.name}


@router.get("/me")
def whoami(user: Identity | None = Depends(current_user)):
    """The verified caller, or null while AUTH_MODE is off/log and no token was sent."""
    if user is None:
        return None
    return {"email": user.email, "name": user.name, "via": user.via}
