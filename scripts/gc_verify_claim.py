"""
GC Verify Claim — Check P&L claims against verified benchmark data.

Usage:
  python scripts/gc_verify_claim.py "ROLR is $61K"
  python scripts/gc_verify_claim.py "capture is 40%" --json
  python scripts/gc_verify_claim.py "NPT bot pnl is $17539" --json
"""
from __future__ import annotations

import io
import json
import os
import re
import sys
import argparse

# Fix Windows encoding
try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
except (AttributeError, TypeError):
    pass

GC_MEMORY_DIR = os.environ.get(
    "GC_MEMORY_DIR",
    r"C:\Users\ftbbo\Nextcloud4\OneDrive Backup\Documents (sync'd)\Development\gravity-claw\data\memory"
)
BENCHMARK_FILE = os.path.join(GC_MEMORY_DIR, "wb-benchmark.md")


def load_benchmark() -> dict:
    """Parse wb-benchmark.md into structured data."""
    if not os.path.exists(BENCHMARK_FILE):
        return {"error": "No benchmark file found. Run a batch test first."}
    
    with open(BENCHMARK_FILE, "r", encoding="utf-8") as f:
        content = f.read()
    
    data = {"cases": {}, "summary": {}}
    
    # Extract summary stats
    for line in content.split("\n"):
        line = line.strip()
        if line.startswith("Bot P&L:"):
            data["summary"]["bot_pnl"] = parse_dollar(line.split(":", 1)[1])
        elif line.startswith("Ross P&L:"):
            data["summary"]["ross_pnl"] = parse_dollar(line.split(":", 1)[1])
        elif line.startswith("Capture:"):
            m = re.search(r"([\d.]+)%", line)
            if m:
                data["summary"]["capture"] = float(m.group(1))
        elif line.startswith("Total cases:"):
            m = re.search(r"\d+", line)
            if m:
                data["summary"]["total_cases"] = int(m.group())
        elif line.startswith("Last run:"):
            data["summary"]["last_run"] = line.split(":", 1)[1].strip()
        elif line.startswith("- ") and "ross_" in line:
            # Parse case line: - ▼ ross_npt_20260203: bot=$17,539 ross=$81,000 gap=$-63,461
            m = re.match(r"- [▼▲·] (ross_\w+): bot=\$([\d,.-]+) ross=\$([\d,.-]+) gap=\$([\d,+.-]+)", line)
            if m:
                case_id = m.group(1)
                symbol = case_id.split("_")[1].upper()
                data["cases"][case_id] = {
                    "symbol": symbol,
                    "bot_pnl": parse_dollar(m.group(2)),
                    "ross_pnl": parse_dollar(m.group(3)),
                    "gap": parse_dollar(m.group(4)),
                }
                # Also index by symbol for easy lookup
                if symbol not in data["cases"]:
                    data["cases"][symbol] = data["cases"][case_id]
    
    return data


def parse_dollar(s: str) -> float:
    """Parse dollar string like '$161,116' or '-$2,997' into float."""
    s = s.strip().replace("$", "").replace(",", "").replace("+", "")
    try:
        return float(s)
    except ValueError:
        return 0.0


def verify_claim(claim: str, benchmark: dict) -> dict:
    """Verify a claim against benchmark data.
    
    Returns dict with: claim, verdict (CONFIRMED/WRONG/UNVERIFIABLE), 
    actual_value, explanation
    """
    claim_lower = claim.lower().strip()
    result = {"claim": claim, "verdict": "UNVERIFIABLE", "actual": None, "explanation": ""}
    
    if "error" in benchmark:
        result["explanation"] = benchmark["error"]
        return result
    
    cases = benchmark.get("cases", {})
    summary = benchmark.get("summary", {})
    
    # Extract symbol from claim
    symbol_match = re.search(r'\b([A-Z]{2,6})\b', claim)
    symbol = symbol_match.group(1) if symbol_match else None
    
    # Extract dollar amount from claim
    dollar_match = re.search(r'\$?([\d,]+(?:\.\d+)?)[Kk]?', claim)
    claimed_amount = None
    if dollar_match:
        raw = dollar_match.group(0)
        val = float(dollar_match.group(1).replace(",", ""))
        if raw.lower().endswith("k"):
            val *= 1000
        claimed_amount = val
    
    # Extract percentage from claim
    pct_match = re.search(r'([\d.]+)\s*%', claim)
    claimed_pct = float(pct_match.group(1)) if pct_match else None
    
    # Check capture percentage claim
    if claimed_pct is not None and ("capture" in claim_lower):
        actual = summary.get("capture", None)
        if actual is not None:
            result["actual"] = f"{actual:.1f}%"
            if abs(actual - claimed_pct) < 1.0:
                result["verdict"] = "CONFIRMED"
                result["explanation"] = f"Capture is {actual:.1f}%, claimed {claimed_pct:.1f}%"
            else:
                result["verdict"] = "WRONG"
                result["explanation"] = f"Capture is actually {actual:.1f}%, not {claimed_pct:.1f}%"
            return result
    
    # Check total bot P&L claim
    if claimed_amount is not None and ("total" in claim_lower or "bot total" in claim_lower) and symbol is None:
        actual = summary.get("bot_pnl", None)
        if actual is not None:
            result["actual"] = f"${actual:,.0f}"
            tolerance = max(abs(actual) * 0.05, 500)  # 5% or $500
            if abs(actual - claimed_amount) < tolerance:
                result["verdict"] = "CONFIRMED"
                result["explanation"] = f"Total bot P&L is ${actual:,.0f}, claimed ${claimed_amount:,.0f}"
            else:
                result["verdict"] = "WRONG"
                result["explanation"] = f"Total bot P&L is actually ${actual:,.0f}, not ${claimed_amount:,.0f}"
            return result
    
    # Check per-symbol claim
    if symbol and symbol in cases:
        case = cases[symbol]
        actual_bot = case["bot_pnl"]
        actual_ross = case["ross_pnl"]
        actual_gap = case["gap"]
        
        if claimed_amount is not None:
            # Determine what they're claiming about
            if "ross" in claim_lower:
                actual = actual_ross
                label = "Ross P&L"
            elif "gap" in claim_lower:
                actual = actual_gap
                label = "gap"
            else:
                actual = actual_bot
                label = "bot P&L"
            
            result["actual"] = f"${actual:,.0f}"
            tolerance = max(abs(actual) * 0.05, 100)  # 5% or $100
            
            # Handle K notation: claimed $61K vs actual $61,566
            if abs(actual - claimed_amount) < tolerance:
                result["verdict"] = "CONFIRMED"
                result["explanation"] = f"{symbol} {label} is ${actual:,.0f}, claimed ${claimed_amount:,.0f}"
            else:
                result["verdict"] = "WRONG"
                result["explanation"] = f"{symbol} {label} is actually ${actual:,.0f}, not ${claimed_amount:,.0f}"
            
            # Add full context
            result["context"] = {
                "symbol": symbol,
                "bot_pnl": f"${actual_bot:,.0f}",
                "ross_pnl": f"${actual_ross:,.0f}",
                "gap": f"${actual_gap:,.0f}",
            }
            return result
        else:
            # No amount claimed, just return the data
            result["verdict"] = "INFO"
            result["actual"] = f"bot=${actual_bot:,.0f} ross=${actual_ross:,.0f} gap=${actual_gap:,.0f}"
            result["explanation"] = f"Here's what I have for {symbol}"
            return result
    
    # Symbol not found
    if symbol:
        result["explanation"] = f"Symbol '{symbol}' not found in benchmark data"
    else:
        result["explanation"] = "Could not parse the claim. Try: 'verify ROLR is $61K' or 'verify capture is 37%'"
    
    return result


def main():
    parser = argparse.ArgumentParser(description="Verify P&L claims against benchmark")
    parser.add_argument("claim", help="The claim to verify (e.g., 'ROLR is $61K')")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args()
    
    benchmark = load_benchmark()
    result = verify_claim(args.claim, benchmark)
    
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        icon = {"CONFIRMED": "✅", "WRONG": "❌", "UNVERIFIABLE": "❓", "INFO": "ℹ️"}.get(result["verdict"], "?")
        print(f"\n  {icon} {result['verdict']}: {result['explanation']}")
        if result.get("actual"):
            print(f"  Actual: {result['actual']}")
        if result.get("context"):
            ctx = result["context"]
            print(f"  Full data: bot={ctx['bot_pnl']} ross={ctx['ross_pnl']} gap={ctx['gap']}")
        print()


if __name__ == "__main__":
    main()
