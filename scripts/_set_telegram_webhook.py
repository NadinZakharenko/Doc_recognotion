"""Register Telegram webhook. Args: <bot_token> <webhook_url> <secret_token>"""

from __future__ import annotations

import json
import sys

import httpx


def main() -> int:
    if len(sys.argv) != 4:
        print("Usage: _set_telegram_webhook.py <token> <url> <secret>", file=sys.stderr)
        return 2
    token, url, secret = sys.argv[1], sys.argv[2], sys.argv[3]
    payload = {
        "url": url,
        "secret_token": secret,
        "drop_pending_updates": True,
        "allowed_updates": ["message", "callback_query"],
    }
    last_err: Exception | None = None
    for verify in (True, False):
        try:
            with httpx.Client(timeout=45, verify=verify) as client:
                resp = client.post(f"https://api.telegram.org/bot{token}/setWebhook", json=payload)
                print("setWebhook", resp.status_code, resp.text)
                resp.raise_for_status()
                data = resp.json()
                if not data.get("ok"):
                    raise RuntimeError(data)
                info = client.get(f"https://api.telegram.org/bot{token}/getWebhookInfo").json()
                print(json.dumps(info, ensure_ascii=False, indent=2))
                return 0
        except Exception as exc:  # noqa: BLE001 — report both verify attempts
            last_err = exc
            print(f"verify={verify} failed: {exc}", file=sys.stderr)
    print(
        f"Telegram API unreachable (pause Browsec/VPN?). Last error: {last_err}",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
