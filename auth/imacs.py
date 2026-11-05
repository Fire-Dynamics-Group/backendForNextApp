"""`require_imacs_app`: shared-app-key gate for the i-macs desktop app.

i-macs (Tauri + Python sidecar driving MACS+) is a closed internal Windows app
with no per-user sign-in yet, so its endpoints (`/imacs/*`) are protected by
one shared key sent in the `X-IMACS-App-Key` header:

    router = APIRouter(dependencies=[Depends(require_imacs_app)])

Behaviour (the key is read from env `IMACS_APP_KEY` on every request, so a
Railway variable change needs no redeploy-time wiring):

  IMACS_APP_KEY unset/empty  503  fail closed - nothing is accepted, even a
                                  header that "matches" an empty key
  header missing/empty       401
  header wrong               403  (compared with hmac.compare_digest)

The key is accepted ONLY by routes that declare this dependency. Browser
routes stay on `auth.deps.current_user`.

Swapping to Entra later: replace the body of this one function with a call to
`current_user` (or a verifier that requires an i-macs app role) and keep the
name/signature, so `routers/imacs.py` and main.py need no change.
"""

from __future__ import annotations

import hmac
import logging
import os

from fastapi import Header, HTTPException

log = logging.getLogger("auth")

HEADER_NAME = "X-IMACS-App-Key"


def require_imacs_app(
    x_imacs_app_key: str | None = Header(default=None, alias=HEADER_NAME),
) -> None:
    expected = os.environ.get("IMACS_APP_KEY", "")
    if not expected:
        log.error("auth: IMACS_APP_KEY is not set; rejecting i-macs request")
        raise HTTPException(status_code=503, detail="i-macs access is not configured.")
    if not x_imacs_app_key:
        raise HTTPException(status_code=401, detail="i-macs app key required.")
    if not hmac.compare_digest(x_imacs_app_key.encode("utf-8"), expected.encode("utf-8")):
        raise HTTPException(status_code=403, detail="Invalid i-macs app key.")
