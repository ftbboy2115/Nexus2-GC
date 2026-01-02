"""
Project: Nexus Evening Routine (The "Factory")
Filename: core/evening_routine.py
Version: 1.0.1
Author: Gemini (Assistant) & [Your Name]
Date: 2025-12-15

Changelog:
- v1.0.1: DEBUG MODE. Removed character limit on error logs to reveal full tracebacks.
- v1.0.0: Initial Release.
"""

import os
import sys
import time
import datetime
import requests
import json
import re

# --- PATH SETUP ---
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.append(project_root)

import config
import utils

# --- CONFIGURATION ---
SCRIPT_NAME = "Evening Routine"
VERSION = "1.0.1"

TASKS = [
    {
        "name": "HTF Scanner",
        "path": os.path.join("core", "scan_htf.py"),
        "desc": "Scanning for High Tight Flags (Structure)..."
    },
    {
        "name": "Momentum Scanner",
        "path": os.path.join("core", "scan_trend_daily.py"),
        "desc": "Scanning for Momentum/Squeezes (Trend)..."
    },
    {
        "name": "Watchlist Manager",
        "path": os.path.join("core", "watchlist_manager.py"),
        "desc": "Building Final Battle Plan..."
    }
]

# ==============================================================================
# 1. HELPER FUNCTIONS
# ==============================================================================
def parse_output(script_name, output):
    count = 0
    patterns = [
        r"Saved (\d+) .*candidates",        # HTF
        r"Found (\d+) Candidates",          # Momentum
        r"Watchlist Updated: (\d+) tickers" # Manager
    ]

    for p in patterns:
        match = re.search(p, output)
        if match:
            return int(match.group(1))

    return "N/A"

def send_discord_summary(stats, duration):
    if not config.DISCORD_URL:
        print("[INFO] Discord URL not set. Skipping notification.")
        return

    htf_count = stats.get("HTF Scanner", 0)
    mom_count = stats.get("Momentum Scanner", 0)
    total_loaded = stats.get("Watchlist Manager", 0)

    embed = {
        "title": "🌙 Nexus Evening Report: Market Closed",
        "description": "The factory has finished building the watchlist for tomorrow.",
        "color": 3447003, # Deep Blue
        "fields": [
            {
                "name": "🏛️ Structure (HTF)",
                "value": f"**{htf_count}** Setups",
                "inline": True
            },
            {
                "name": "🌊 Momentum",
                "value": f"**{mom_count}** Setups",
                "inline": True
            },
            {
                "name": "🎯 **Sniper Magazine**",
                "value": f"**{total_loaded} Targets Loaded**",
                "inline": False
            },
            {
                "name": "⏱️ Execution Time",
                "value": f"{duration:.1f} seconds",
                "inline": True
            }
        ],
        "footer": {
            "text": f"Nexus Core v{VERSION} • {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}"
        }
    }

    payload = {"embeds": [embed]}

    try:
        requests.post(config.DISCORD_URL, json=payload, timeout=5)
        print("[SUCCESS] Battle Plan sent to Discord.")
    except Exception as e:
        print(f"[WARN] Failed to send Discord summary: {e}")

# ==============================================================================
# 2. MAIN EXECUTION
# ==============================================================================
if __name__ == "__main__":
    utils.print_metadata(SCRIPT_NAME, VERSION)
    start_time = time.time()

    stats = {}

    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] 🚀 Starting Evening Factory...\n")

    for task in TASKS:
        name = task["name"]
        path = task["path"]

        print(f"--- {task['desc']} ---")

        # Execute the script (Blocking Call)
        success, output = utils.run_script(path, name)

        if success:
            count = parse_output(name, output)
            stats[name] = count
            print(f"✅ {name}: Success (Yield: {count})")
        else:
            stats[name] = "ERROR"
            print(f"❌ {name}: Failed")

            # --- DEBUG MODE: PRINT FULL LOG ---
            print("="*20 + " ERROR LOG " + "="*20)
            print(output)
            print("="*51)

        print("") # Spacer

    total_duration = time.time() - start_time

    print("=" * 60)
    print(f"[DONE] Factory Finished in {total_duration:.1f}s")

    send_discord_summary(stats, total_duration)