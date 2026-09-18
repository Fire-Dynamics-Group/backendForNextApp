"""Getting the sweep's verdict to a human, via a Telegram bot.

Railway does **not** alert on a cron service exiting non-zero - it records the
failed run and nothing else. The exit code is still set (it makes the failure
visible in the Railway UI and is the right Unix behaviour), but on its own it
would mean the daily sweep fails silently in the logs. This module is the
actual notification path.

Two env vars, both set on the Railway cron service:

    TELEGRAM_BOT_TOKEN   from @BotFather
    TELEGRAM_CHAT_ID     the chat to post into

Nothing here may raise. A broken notifier must not turn a one-service outage
into a crashed run with no output at all - the printed sweep is still worth
having.
"""
from __future__ import annotations

import os

TELEGRAM_API = "https://api.telegram.org"

# Long enough to survive a slow API, short enough that a hung notifier cannot
# hold the cron run open - Railway skips the next run while one is still alive.
TIMEOUT_SECONDS = 15.0


def format_alert(down: list[str], *, total_checked: int) -> str:
    """Build the alert text. Pure.

    Returns "" when nothing is down, so the caller sends nothing. A daily
    "all fine" message is how an alert channel becomes one you mute - and a
    muted channel is worse than no channel.
    """
    if not down:
        return ""

    lines = [f"FD estate: {len(down)} of {total_checked} services DOWN", ""]
    lines.extend(f"- {entry}" for entry in down)
    return "\n".join(lines)


def send_telegram(
    text: str,
    *,
    token: str | None = None,
    chat_id: str | None = None,
    poster=None,
) -> bool:
    """Post `text` to the configured chat. Returns whether it was delivered.

    `poster` is the injection seam for tests; it defaults to httpx.post.
    Never raises - an unconfigured or unreachable notifier is reported as
    False, not as an exception that takes the whole run down.
    """
    token = token if token is not None else os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = chat_id if chat_id is not None else os.environ.get("TELEGRAM_CHAT_ID", "")

    if not token or not chat_id:
        print(
            "notify: TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set - no alert sent",
            flush=True,
        )
        return False

    if poster is None:
        import httpx

        poster = httpx.post

    # Plain text on purpose: service names and reasons carry underscores and
    # brackets that Telegram's Markdown parser would reject, and a rejected
    # alert is an alert you never see.
    payload = {"chat_id": chat_id, "text": text, "disable_web_page_preview": True}

    try:
        response = poster(
            f"{TELEGRAM_API}/bot{token}/sendMessage",
            json=payload,
            timeout=TIMEOUT_SECONDS,
        )
    except Exception as exc:  # noqa: BLE001 - a dead notifier must not kill the run
        print(f"notify: could not reach Telegram: {type(exc).__name__}: {exc}", flush=True)
        return False

    if response.status_code != 200:
        print(f"notify: Telegram rejected the message ({response.status_code})", flush=True)
        return False

    return True
