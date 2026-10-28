# Vendored pstack (pinned)

This tree is a **pinned copy** of Cursor's [pstack](https://github.com/cursor/plugins/tree/main/pstack) plugin (MIT, Lauren Tan). User-installed plugins do not load reliably in Cursor cloud agents, so skills and subagent definitions live in-repo.

Copies are pinned and **must be refreshed manually**. Do not auto-update.

| Field | Value |
| --- | --- |
| Source | https://github.com/cursor/plugins/tree/main/pstack |
| Commit SHA | `c742dd61706fbacc1b95f1a20b7b988cf096ce6c` |
| Commit date | 2026-10-27 |
| Version | `0.15.36` (0.15.x) |
| License | MIT (see `LICENSE` in this directory) |

`plugin.json` next to this file is the upstream manifest at that SHA (version/author only). It is not a live plugin install.

Skills are laid out as upstream `pstack/skills/` so `/poteto-mode` resolves at `.cursor/skills/poteto-mode/SKILL.md`. Subagent definitions are at `.cursor/agents/` (`poteto-agent`, `comment-sicko`). Hooks are not vendored (they do not run in cloud agents).

## Refresh later

1. Fetch a newer pstack SHA from https://github.com/cursor/plugins (path `pstack/`).
2. Replace `.cursor/skills/` **except** `PSTACK_VENDORED.md` and keep/replace `LICENSE` from upstream.
3. Replace `.cursor/agents/` with upstream `pstack/agents/`.
4. Update the SHA, date, and version in this file. Confirm `plugin.json` `version` still matches.
5. Re-run `.cursor/scripts/check-pstack.sh`. Do not loosen `.cursor/rules/pstack-models.mdc` or `.cursor/rules/fd-overrides.mdc` as part of a refresh.
