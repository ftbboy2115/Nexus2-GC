"""
GC Memory Bridge — Auto-writes verified metrics to GC's persistent markdown memory.

GC uses markdown files in `gravity-claw/data/memory/` with YAML frontmatter.
This module writes those files directly from Python scripts, so memory updates
are deterministic (no agent compliance needed).
"""
from __future__ import annotations

import os
from datetime import datetime

# GC memory directory
GC_MEMORY_DIR = os.environ.get(
    "GC_MEMORY_DIR",
    r"C:\Users\ftbbo\Nextcloud4\OneDrive Backup\Documents (sync'd)\Development\gravity-claw\data\memory"
)


def _write_memory(slug: str, title: str, tags: list[str], content: str):
    """Write a markdown memory file in GC's format."""
    os.makedirs(GC_MEMORY_DIR, exist_ok=True)
    filepath = os.path.join(GC_MEMORY_DIR, f"{slug}.md")
    now = datetime.now().isoformat()

    # Preserve original created date if file already exists
    created = now
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                for line in f:
                    if line.startswith("created:"):
                        created = line.split(":", 1)[1].strip()
                        break
        except Exception:
            pass

    tags_str = f"\ntags: [{', '.join(tags)}]" if tags else ""
    md = f"""---
title: "{title}"
created: {created}
updated: {now}{tags_str}
---

{content}
"""
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(md)


def write_benchmark_memory(data: dict):
    """Write WB Benchmark memory from batch test results.
    
    Args:
        data: Raw batch test result dict with 'results' and 'summary' keys
    """
    results = data.get("results", [])
    summary = data.get("summary", {})
    saved_at = data.get("saved_at", datetime.now().strftime("%Y-%m-%d %H:%M"))

    total_bot = summary.get("total_pnl", 0) or 0
    total_ross = summary.get("total_ross_pnl", 0) or 0
    capture = (total_bot / total_ross * 100) if total_ross else 0
    cases_profitable = summary.get("cases_profitable", 0) or 0

    # Compute per-case gaps
    gaps = []
    for r in results:
        bot = r.get("total_pnl", r.get("bot_pnl", 0)) or 0
        ross = r.get("ross_pnl", 0) or 0
        symbol = r.get("symbol", r.get("case_id", "???"))
        case_id = r.get("case_id", "")
        gaps.append({"symbol": symbol, "case_id": case_id, "bot": bot, "ross": ross, "gap": bot - ross})

    gaps.sort(key=lambda x: x["gap"])

    # Top 5 worst and best
    worst_5 = gaps[:5]
    best_5 = list(reversed(gaps[-5:]))

    content = f"""Last run: {saved_at}
Total cases: {len(results)}
Bot P&L: ${total_bot:,.0f}
Ross P&L: ${total_ross:,.0f}
Capture: {capture:.1f}%
Profitable: {cases_profitable}/{len(results)}

## Top 5 Gaps (Underperforming)
"""
    for g in worst_5:
        content += f"- {g['symbol']}: bot=${g['bot']:,.0f} ross=${g['ross']:,.0f} gap=${g['gap']:+,.0f}\n"

    content += "\n## Top 5 Wins (Outperforming)\n"
    for g in best_5:
        content += f"- {g['symbol']}: bot=${g['bot']:,.0f} ross=${g['ross']:,.0f} gap=${g['gap']:+,.0f}\n"

    content += f"\n## All Cases (sorted by gap)\n"
    for g in gaps:
        marker = "▼" if g["gap"] < -100 else ("▲" if g["gap"] > 100 else "·")
        content += f"- {marker} {g['case_id']}: bot=${g['bot']:,.0f} ross=${g['ross']:,.0f} gap=${g['gap']:+,.0f}\n"

    _write_memory("wb-benchmark", "WB Benchmark", ["benchmark", "warrior", "verified"], content)


def write_known_issues_memory(gaps: list[dict]):
    """Write WB Known Issues memory from gap analysis.
    
    Args:
        gaps: List of dicts with case_id, symbol, bot_pnl, ross_pnl, gap, guard_blocks
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    # Categorize issues
    direction_mismatches = [g for g in gaps if g["bot_pnl"] < 0 and g["ross_pnl"] > 100]
    big_gaps = [g for g in gaps if g["gap"] < -5000 and g not in direction_mismatches]

    content = f"Updated: {now}\n\n"

    if direction_mismatches:
        content += "## Direction Mismatches (bot loses, Ross wins)\n"
        for g in sorted(direction_mismatches, key=lambda x: x["gap"]):
            guards = f" ({g['guard_blocks']} guards)" if g["guard_blocks"] > 0 else ""
            content += f"- {g['symbol']}: bot=${g['bot_pnl']:,.0f} ross=${g['ross_pnl']:,.0f} gap=${g['gap']:+,.0f}{guards}\n"
        content += "\n"

    if big_gaps:
        content += "## Large Gaps (>$5K underperformance)\n"
        for g in sorted(big_gaps, key=lambda x: x["gap"]):
            guards = f" ({g['guard_blocks']} guards)" if g["guard_blocks"] > 0 else ""
            content += f"- {g['symbol']}: bot=${g['bot_pnl']:,.0f} ross=${g['ross_pnl']:,.0f} gap=${g['gap']:+,.0f}{guards}\n"

    _write_memory("wb-known-issues", "WB Known Issues", ["issues", "warrior", "priority"], content)
