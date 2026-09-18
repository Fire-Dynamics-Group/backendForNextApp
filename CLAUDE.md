# backendForNextApp

FastAPI backend for the Fire Dynamics upload-canvas app (fire engineering calcs: time equivalence, FDS, radiation, stairs, fee proposals).

## Deployed URLs

**This backend (Railway):**
- dev branch: https://backendfornextapp-dev.up.railway.app (interactive docs at `/docs`)
- production (master): https://backendfornextapp-production.up.railway.app

**Frontend — upload-canvas (Vercel, team scope `fire-dynamics-projects`):**
- dev branch preview: https://upload-canvas-git-dev-fire-dynamics-projects.vercel.app
- production alias: https://upload-canvas.vercel.app
- https://upload-canvas-next.vercel.app is a **stale old project** (pre-Nov-2024 code) despite the "-next" name — don't use it as a reference for current behaviour, even though `.env` `NEXT_PUBLIC_BASE_URL` still points at it.

Vercel branch previews follow `<project>-git-<branch>-fire-dynamics-projects.vercel.app`.

**Related services** (see `ops/daily.py` for the full probe list):
- mobile backend: https://web-production-44b8.up.railway.app
- MinIO, upload-canvas bucket: https://bucket-production-fd13.up.railway.app
- MinIO, Outlook add-in assets: https://bucket-production-a0e4.up.railway.app
