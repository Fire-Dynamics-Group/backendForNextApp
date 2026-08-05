# `ops/` — scheduled checks for the FD estate

External uptime checks, run from this backend because it is already always-on
and **independent of the machines it watches**. That independence is the whole
point: the auto-restart watchdog on TinyBot cannot tell you TinyBot is down.

## Status: built and passing locally, NOT yet deployed

```powershell
python -m ops.daily      # one sweep, prints a line per service, exits
pytest test_ops_uptime.py test_ops_health.py test_ops_daily.py -q
```

Live run against the estate on 2026-07-22: **10 of 10 UP**, exit 0.
58 unit tests pass.

One compromise to know about: `backendForNextApp (prod)` is only a *liveness*
check on `/docs`, even though it owns Postgres and MinIO and deserves a deep
one. `/health` exists in this repo but prod has not been deployed since
2026-06-12 (`dev` is 48 commits ahead of `master`), so a deep check would
report DOWN and alert every day until the backend ships.
`test_ops_daily.py::TestBackendCheckIsTemporarilyShallow` fails the moment that
is fixed, so it cannot be forgotten.

## What it checks

Nine services, at two depths.

| Depth | Question | Used for |
| --- | --- | --- |
| `live` | did anything answer | the Vercel frontends, the MinIO liveness route |
| `deep` | does it report *itself* well | backendForNextApp, the mobile backend |

**Why deep checks exist.** The mobile app's S3 bucket went down while its API
kept answering 200. Liveness monitoring would have called that green for as
long as it lasted; the outage was found only when uploads failed, and diagnosed
by hand. Anything owning a database or a bucket therefore publishes a `/health`
payload and the sweep reads the payload, not the status line.

`ops/health.classify_health` maps that payload to a verdict:

| Service reports | Verdict | Why |
| --- | --- | --- |
| `"healthy"` | UP | |
| `"degraded"` | **DOWN** | a real dependency is broken even though the process answers |
| `"unhealthy"` | **DOWN** | |
| unparseable / no `status` field | UNKNOWN | could not ask ≠ is broken |

`degraded` is deliberately DOWN. The exit code is the only alerting channel, so
a storage outage that leaves reads working still has to fail the run — that is
precisely the failure this was built for.

### Probe paths — each learned the hard way

- **email-search probes `/login`, not `/health`.** `/health` is ungated in the
  `ui/proxy.ts` source but the *deployed* prod build still gates it, so it
  answers 401 permanently. Probing it would report a false alarm every day.
  **Do not "fix" this.**
- **backendForNextApp has no root route** — `GET /` is a genuine 404. It gets a
  deep check on `/health`; never fall back to `/` for liveness.
- **MinIO is checked directly as well as through the two backends.** That makes
  an outage attributable: if the bucket line is DOWN too, the bucket is the
  fault rather than the app depending on it.

## The devtunnel trap (the expensive lesson)

Getting a devtunnel to return the *app* rather than a challenge page needs a
specific request shape. All three matter:

| Request shape | What the relay returns |
| --- | --- |
| No / unusual `User-Agent` | `401 {"message":"Authentication required."}` |
| Browser UA + `Accept: text/html` | **`200` carrying the anti-phishing interstitial** |
| Browser UA + `Accept: */*` + `X-Tunnel-Skip-AntiPhishing-Page: true` | the real app |

The middle row is the dangerous one: a status-code-only monitor sees `200` and
reports green while never once having reached the app. That is why `classify()`
fingerprints the body and why `Verdict` has three states, not two —
`UNKNOWN` ("could not ask") must never be reported as `DOWN` ("is broken").
`test_ops_uptime.py::TestProbeRequestShape` pins the header contract.

## Deploying as a Railway cron

Not done yet. Steps:

1. New **service in the same Railway project**, same repo, so it inherits the
   project env vars.
2. Start command: `python -m ops.daily`
3. Set a **Cron Schedule** on the service (e.g. `0 8 * * *`).
4. Set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` on the service (below).

### Alerting: Telegram, not the exit code

**Railway does not notify you when a cron service exits non-zero.** It records
the run as failed and nothing else — no email, no webhook. An earlier version
of this file claimed the exit code *was* the alert; that was wrong, and it
would have meant the sweep failing silently in the logs forever.

The exit code is still set (it marks the run failed in the Railway UI and is
the right Unix behaviour), but the alert is a Telegram message from
`ops/notify.py`.

Setup, once:

1. Message [@BotFather](https://t.me/BotFather) → `/newbot` → copy the token.
2. Send your new bot a message, then read your chat id from
   `https://api.telegram.org/bot<TOKEN>/getUpdates`.
3. Set both as variables on the cron service:
   `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`.

Unset variables are not an error — the sweep prints that it skipped the alert
and still exits with the right code, so local runs need no credentials.

**Only failures are sent.** A daily "all fine" message is how an alert channel
becomes one you mute. The trade-off is that silence cannot distinguish "all
healthy" from "the cron never ran" — see *Next* for the dead-man's-switch that
closes that gap.

The process must exit; Railway will not start the next run while the previous
one is alive. `ops/daily.py` returns from `run()` and never blocks.

Probe URLs are env-overridable (`EMAIL_SEARCH_PROBE_URL`) so the tunnel
hostname can change without a code deploy — it is pinned in `SERVICES` only as
a default.

## Adding a service

Append a `Service` to `SERVICES` in `ops/daily.py`. No entrypoint change.

```python
Service(
    name="thing",
    env_var="THING_PROBE_URL",   # must end _PROBE_URL and be unique
    url="https://thing.vercel.app",
    deep=False,                  # True only if it serves a /health payload
)
```

`test_ops_daily.py::TestEstateRegistry` enforces the conventions (unique names
and env vars, deep checks pointing at a `/health` path), so a malformed entry
fails the suite rather than silently monitoring nothing.

## Next

- **Deploy the cron service (above) — until then nothing runs on a schedule.**
  This is the only thing standing between "written" and "working".
- Deploy the backend so `/health` exists, then switch its entry back to a deep
  check (`url` → `.../health`, `deep=True`) and delete
  `TestBackendCheckIsTemporarilyShallow`. Until then the service that owns
  Postgres and the bucket is the *least* well monitored thing in the estate.
- `i-macs` is not yet in `SERVICES` — no deployed URL was found for it.
- **Dead-man's-switch.** Only failures are alerted, so a cron that never fires
  (bad schedule, deleted service, Railway outage) is indistinguishable from a
  healthy estate. Pinging healthchecks.io on each *successful* run closes it:
  the monitor alerts when the ping stops arriving. Not done — it is the one
  remaining way this can fail silently.
- Persist results to an `ops_check_runs` table if you ever want history or a
  digest. Deliberately skipped in v1 — logs plus exit code are enough to answer
  "is it up".
- Deliberately **not** in scope: anything mutating (DB hygiene, cleanup). Do
  not add destructive work to a job that runs unattended until the reporting
  path has proven itself.
