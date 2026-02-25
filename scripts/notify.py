"""
Send a Telegram notification via GC's bot.

Usage:
  python scripts/notify.py "Sweeps finished!"
  python scripts/notify.py "5 sweeps complete" --results sweep_results.json
  
Reads TELEGRAM_BOT_TOKEN and ALLOWED_USER_IDS from gravity-claw .env file.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request

# Find gravity-claw .env
GC_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "..", "gravity-claw"
)
ENV_FILE = os.path.join(GC_PATH, ".env")


def load_env(path: str) -> dict[str, str]:
    """Parse a .env file into a dict."""
    env = {}
    if not os.path.exists(path):
        return env
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def send_telegram(token: str, chat_id: str, message: str) -> bool:
    """Send a message via the Telegram Bot API."""
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown"
    }).encode()
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except Exception as e:
        print(f"Failed to send Telegram message: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Send a Telegram notification via GC's bot")
    parser.add_argument("message", help="Message to send")
    parser.add_argument("--results", help="Optional JSON results file to include summary from")
    args = parser.parse_args()

    env = load_env(ENV_FILE)
    token = env.get("TELEGRAM_BOT_TOKEN") or os.environ.get("TELEGRAM_BOT_TOKEN")
    user_ids = env.get("ALLOWED_USER_IDS") or os.environ.get("ALLOWED_USER_IDS", "")

    if not token:
        print("ERROR: TELEGRAM_BOT_TOKEN not found in .env or environment")
        sys.exit(1)
    if not user_ids:
        print("ERROR: ALLOWED_USER_IDS not found in .env or environment")
        sys.exit(1)

    chat_id = user_ids.split(",")[0].strip()

    message = f"🤖 *Nexus Notification*\n\n{args.message}"

    if args.results and os.path.exists(args.results):
        with open(args.results) as f:
            data = json.load(f)
        results = data.get("results", [])
        if results:
            message += "\n\n"
            for r in results:
                if "error" in r:
                    message += f"• {r['value']}: ERROR\n"
                else:
                    message += f"• {r['value']}: ${r.get('total_pnl', 0):,.0f}\n"

    if send_telegram(token, chat_id, message):
        print(f"✅ Notification sent to Telegram")
    else:
        print("❌ Failed to send notification")
        sys.exit(1)


if __name__ == "__main__":
    main()
