import json

import pytest

from trend_system.notify import send_telegram_message


def test_send_telegram_message_posts_expected_payload(monkeypatch):
    calls = []

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def read(self):
            return json.dumps({"ok": True}).encode("utf-8")

    def fake_urlopen(request, timeout):
        calls.append((request, timeout))
        return FakeResponse()

    monkeypatch.setattr("trend_system.notify.urllib.request.urlopen", fake_urlopen)

    send_telegram_message("hello", bot_token="token", chat_id="123")

    request, timeout = calls[0]
    assert request.full_url == "https://api.telegram.org/bottoken/sendMessage"
    assert timeout == 20
    assert b"chat_id=123" in request.data
    assert b"text=hello" in request.data


def test_send_telegram_message_rejects_empty_message():
    with pytest.raises(ValueError):
        send_telegram_message("   ", bot_token="token", chat_id="123")
