# Post-deploy smoke: `/projects?mode=` for every Upload Canvas mode

The 2026-09 incident: `GET /projects?mode=fdsGen` 500'd because production
Postgres had no `projects.mode` column. The browser reported **CORS** (the 500
body has no `Access-Control-Allow-Origin`). We only smoked `fdsGen`, so empty
or broken `timeEq` / `radiation` / `efs` lists would have slipped through.

This gate hits **all four** modes. It never drives interactive Entra.

**Empty mode lists are OK** (production `timeEq` is often 0). **HTTP 500,
non-JSON, and missing CORS are not.**

## Run after a Railway deploy (Firebot / Ian)

From the repo root:

```bash
SMOKE_BASE_URL=https://backendfornextapp-production.up.railway.app \
SMOKE_EMAIL=ian@firedynamicsgroup.com SMOKE_PASSWORD=… \
python scripts/smoke_projects_modes.py
```

Dev (separate database — do not assume the same project counts):

```bash
SMOKE_BASE_URL=https://backendfornextapp-dev.up.railway.app \
python scripts/smoke_projects_modes.py --readonly
```

`python scripts/smoke_projects_modes.py --help` prints the same contract.

## What it checks

For each of `fdsGen`, `timeEq`, `radiation`, `efs`:

1. `GET /projects?mode=<mode>` with `Origin: https://upload-canvas.vercel.app`
2. HTTP **200** (not 5xx)
3. Body is a JSON **array** (`count==0` is a pass)
4. Response includes `access-control-allow-origin` for that Origin, or `*`

Also `GET /health` must be 200 and report `healthy`.

Optional: unless `SMOKE_READONLY=1` / `--readonly`, it creates a throwaway
`[smoke] projects-modes …` project per mode and deletes it. GitHub Actions
runs readonly against production.

## Auth (no Entra)

`AUTH_MODE` stays whatever production is (`log` today, `enforce` later). The
smoke adapts:

| Setup | Behaviour |
| --- | --- |
| `SMOKE_EMAIL` + `SMOKE_PASSWORD` (or `APP_PASSWORD`) | `POST /auth/password`, then `Authorization: Bearer` |
| Password route returns 503 | Warn and continue unauthenticated (`AUTH_MODE=log` still lists) |
| Secrets missing | Readonly unauthenticated smoke; fail only on hard API errors (5xx / non-JSON / missing CORS) |
| `SMOKE_REQUIRE_AUTH=1` | Fail if a session was not minted, or if list returns 401/403 |

Once production flips to `AUTH_MODE=enforce`, set the GitHub secrets and
`SMOKE_REQUIRE_AUTH=1` (repo variable or the workflow_dispatch checkbox).

## GitHub Actions

Workflow: `.github/workflows/projects-mode-smoke.yml`

- `pull_request` → unit tests only (mocked HTTP, no live API)
- `push` to `master`, daily schedule, `workflow_dispatch` → unit tests then
  live readonly smoke (default production URL)

### Secrets / variables Ian must set (full auth smoke)

On the **GitHub** repo (Settings → Secrets and variables → Actions):

| Name | Where | Required? | What |
| --- | --- | --- | --- |
| `SMOKE_EMAIL` | Actions **secret** | for auth | FDG address, e.g. `ian@firedynamicsgroup.com` |
| `SMOKE_PASSWORD` | Actions **secret** | for auth | Same value as Railway `APP_PASSWORD` |
| `SMOKE_BASE_URL` | Actions **variable** or secret | no | Override default production URL |
| `SMOKE_REQUIRE_AUTH` | Actions **secret** or variable | only once enforce is on | `1` |

On **Railway** (already used by the API; do not change AUTH_MODE for this gate):

| Name | What |
| --- | --- |
| `APP_PASSWORD` | Shared fallback password; `/auth/password` is 503 without this **and** `AUTH_SECRET` |
| `AUTH_SECRET` | HMAC key for session tokens |

If GitHub secrets are missing, the live job still runs and fails only on hard
API errors. Unauthenticated CI against `AUTH_MODE=enforce` will log a 401
warning and stay green until `SMOKE_REQUIRE_AUTH=1`.

## Tests

```bash
python -m pytest test_smoke_projects_modes.py -q
```
