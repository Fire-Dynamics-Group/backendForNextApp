"""Tests for ops/notify.py - getting the sweep's verdict to a human.

Railway does not alert on a cron service exiting non-zero: it records the
failed run and nothing else. So the exit code alone means the daily sweep
would fail silently in the logs. This module is the actual notification path.
"""
import pytest

from ops.notify import format_alert, send_telegram


class TestFormatAlert:
    def test_names_every_down_service_and_its_reason(self):
        text = format_alert(
            ["backendForNextApp (prod): server error (500)", "MinIO bucket: unreachable"],
            total_checked=9,
        )

        assert "backendForNextApp (prod)" in text
        assert "server error (500)" in text
        assert "MinIO bucket" in text

    def test_gives_the_scale_of_the_failure(self):
        """"2 of 9" reads very differently from "2 down" when half the estate
        is on fire."""
        text = format_alert(["a: x", "b: y"], total_checked=9)

        assert "2" in text and "9" in text

    def test_nothing_down_produces_no_message(self):
        """Falsy so the caller skips sending. A daily "all fine" message is how
        an alert channel becomes one you mute."""
        assert not format_alert([], total_checked=9)


class TestSendTelegram:
    """The impure edge, with the HTTP call injected so nothing leaves the box."""

    def test_posts_to_the_bot_sendmessage_endpoint(self):
        calls = []

        def fake_post(url, json, timeout):
            calls.append((url, json))
            return type("R", (), {"status_code": 200})()

        ok = send_telegram(
            "estate is on fire", token="123:ABC", chat_id="-100", poster=fake_post
        )

        assert ok is True
        url, payload = calls[0]
        assert url == "https://api.telegram.org/bot123:ABC/sendMessage"
        assert payload["chat_id"] == "-100"
        assert payload["text"] == "estate is on fire"

    def test_missing_token_is_skipped_not_crashed(self):
        """An unconfigured notifier must not fail the sweep - the sweep's own
        verdict is still worth having in the logs."""
        assert send_telegram("x", token="", chat_id="-100", poster=None) is False

    def test_missing_chat_id_is_skipped_not_crashed(self):
        assert send_telegram("x", token="123:ABC", chat_id="", poster=None) is False

    def test_telegram_rejecting_the_message_is_reported_not_raised(self):
        def fake_post(url, json, timeout):
            return type("R", (), {"status_code": 400})()

        assert (
            send_telegram("x", token="123:ABC", chat_id="-100", poster=fake_post)
            is False
        )

    def test_network_failure_is_swallowed(self):
        """A dead notifier must never turn a 1-service outage into a crashed
        run with no output at all."""

        def fake_post(url, json, timeout):
            raise OSError("connection reset")

        assert (
            send_telegram("x", token="123:ABC", chat_id="-100", poster=fake_post)
            is False
        )
