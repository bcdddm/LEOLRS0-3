from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path


TELEGRAM_API_BASE = "https://api.telegram.org"


def send_telegram_message(
    message: str,
    *,
    bot_token: str,
    chat_id: str,
    api_base: str = TELEGRAM_API_BASE,
) -> None:
    if not message.strip():
        raise ValueError("Cannot send an empty Telegram message.")

    url = f"{api_base}/bot{bot_token}/sendMessage"
    payload = urllib.parse.urlencode(
        {
            "chat_id": chat_id,
            "text": message,
            "disable_web_page_preview": "true",
        }
    ).encode("utf-8")
    request = urllib.request.Request(url, data=payload, method="POST")
    with urllib.request.urlopen(request, timeout=20) as response:
        body = response.read().decode("utf-8")

    result = json.loads(body)
    if not result.get("ok"):
        description = result.get("description", "unknown Telegram API error")
        raise RuntimeError(f"Telegram send failed: {description}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="trend_system.notify")
    parser.add_argument("--message", default=None)
    parser.add_argument("--message-file", default=None)
    args = parser.parse_args(argv)

    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not bot_token or not chat_id:
        raise RuntimeError("Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID before sending.")

    if args.message_file:
        message = Path(args.message_file).read_text(encoding="utf-8")
    elif args.message:
        message = args.message
    else:
        message = sys.stdin.read()

    send_telegram_message(message, bot_token=bot_token, chat_id=chat_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
