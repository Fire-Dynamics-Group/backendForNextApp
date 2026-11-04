# Agent instructions (backendForNextApp)

This FastAPI backend serves the Fire Dynamics upload-canvas app. Railway auto-deploys from `master`. Do not merge and do not deploy.

## Fire Dynamics overrides to pstack

Vendored pstack lives under `.cursor/skills/` (see `.cursor/skills/PSTACK_VENDORED.md`). These owner rules beat pstack defaults:

- **Never auto-merge, never land overnight, never deploy.** `autopilot-full` and the shipping playbook's landing step are off. Use **autopilot-stack** (build and verify PRs; the human lands them).
- **Ignore never-block-on-the-human** for merges, deploys, secrets, and paid changes.
- **Bug fixes:** play the gesture back first; reproduce and verify on the matching surface where the human saw it (their tab/device/prod URL); a pass on another surface (e.g. headless Playwright) is a proxy, not a pass; after two failed fixes on the same gate, write down and test the premise before a third attempt; never repeat a "hard refresh and try again" handback.
- **Red-green TDD**, production typecheck/build gate (`tsc` / `next build` for TS/Next), e2e of post-push integration, before/after evidence (screenshots or equivalent) in the PR.
- **One PR per concern;** stack if needed.

Full text: `.cursor/rules/fd-overrides.mdc`. Models: `.cursor/rules/pstack-models.mdc` (all pstack roles pinned to `grok-4.6` until 8 Nov 2026).

## Development servers & hot reload

- **Servers should always run with reload for dev**: Any backend, sidecar, or API server must run with auto-reload (`--reload`) enabled in development.
- **Why was the i-macs backend not running on hot reload?**
  - Tauri's `spawn_sidecar` was launching the Python sidecar without a `--reload` option, and uvicorn was running in static single-process mode.
  - We added the `--reload` CLI flag to `app.py` and updated `main.rs` to pass it in dev mode.
  - When starting or orchestrating dev servers across `i-macs`, `backendForNextApp`, and `upload-canvas`, always ensure hot reload is active.

## Honest engineering metrics (no fake / mock fallback data)

- **Never display fake, hardcoded mock values, or invented success metrics as fallbacks in engineering assessment UI or API responses.**
  - Real calculations and simulations must always reflect actual pipeline data.
  - Fallbacks such as hardcoded run counts (`10,000 runs`), artificial pass counts (`9,999 pass`, `passCount ?? 9999`), or default success percentages (`?? 100% Rel.`) disguise broken pipelines and give false engineering confidence.
  - If data is loading, missing, or an error occurs, return and display honest states: explicit loading indicators, skeletons, empty states (`—` or `0`), or clear error badges. Never show invented or optimistic defaults.
