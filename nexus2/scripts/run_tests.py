"""
Mock Market Test Runner CLI

Calls the batch test runner endpoint and produces formatted terminal output
with baseline comparison support.

Usage:
    python -m nexus2.scripts.run_tests                    # Run all test cases
    python -m nexus2.scripts.run_tests --baseline save    # Save results as baseline
    python -m nexus2.scripts.run_tests --compare          # Compare against baseline
    python -m nexus2.scripts.run_tests --cases ross_lrhc_20260130 ross_rdib_20260206
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SERVER_URL = os.environ.get("NEXUS_SERVER_URL", "http://localhost:8000")
BATCH_ENDPOINT = f"{SERVER_URL}/warrior/sim/run_batch"

# Results directory (relative to this file → nexus2/tests/test_cases/results/)
SCRIPT_DIR = Path(__file__).resolve().parent
RESULTS_DIR = SCRIPT_DIR.parent / "tests" / "test_cases" / "results"
BASELINE_FILE = RESULTS_DIR / "baseline.json"


# ---------------------------------------------------------------------------
# ANSI Color Helpers
# ---------------------------------------------------------------------------

def _supports_color() -> bool:
    """Check whether the terminal likely supports ANSI colors."""
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("FORCE_COLOR"):
        return True
    # Windows Terminal / modern PowerShell support ANSI
    if sys.platform == "win32":
        # Enable VT100 escape sequences on Windows 10+
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            # STD_OUTPUT_HANDLE = -11
            handle = kernel32.GetStdHandle(-11)
            # ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
            mode = ctypes.c_ulong()
            kernel32.GetConsoleMode(handle, ctypes.byref(mode))
            kernel32.SetConsoleMode(handle, mode.value | 0x0004)
            return True
        except Exception:
            return False
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


_COLOR = _supports_color()


def green(text: str) -> str:
    return f"\033[32m{text}\033[0m" if _COLOR else text


def red(text: str) -> str:
    return f"\033[31m{text}\033[0m" if _COLOR else text


def yellow(text: str) -> str:
    return f"\033[33m{text}\033[0m" if _COLOR else text


def bold(text: str) -> str:
    return f"\033[1m{text}\033[0m" if _COLOR else text


def dim(text: str) -> str:
    return f"\033[2m{text}\033[0m" if _COLOR else text


# ---------------------------------------------------------------------------
# HTTP Client
# ---------------------------------------------------------------------------

def call_batch_endpoint(
    case_ids: Optional[List[str]] = None,
    timeout: float = 300.0,
) -> Dict[str, Any]:
    """
    Call the batch test runner endpoint.

    Returns the JSON response or raises on error.
    """
    import httpx

    payload: Dict[str, Any] = {}
    if case_ids:
        payload["case_ids"] = case_ids

    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(BATCH_ENDPOINT, json=payload)
            resp.raise_for_status()
            return resp.json()
    except httpx.ConnectError:
        print(red("\n  ERROR: Cannot connect to Nexus server."))
        print(f"  Make sure it is running at {SERVER_URL}")
        print(dim("  Start with: cd nexus2 && python -m uvicorn api.main:app --reload"))
        sys.exit(1)
    except httpx.HTTPStatusError as exc:
        print(red(f"\n  ERROR: Server returned {exc.response.status_code}"))
        try:
            detail = exc.response.json()
            print(f"  Detail: {json.dumps(detail, indent=2)}")
        except Exception:
            print(f"  Body: {exc.response.text[:500]}")
        sys.exit(1)
    except httpx.TimeoutException:
        print(red(f"\n  ERROR: Request timed out after {timeout}s"))
        print("  The batch runner may need more time. Try --timeout <seconds>")
        sys.exit(1)


# ---------------------------------------------------------------------------
# Baseline Management
# ---------------------------------------------------------------------------

def save_baseline(data: Dict[str, Any]) -> Path:
    """Save results as baseline and timestamped copy."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    # Save canonical baseline
    with open(BASELINE_FILE, "w") as f:
        json.dump(data, f, indent=2)

    # Save timestamped copy
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    ts_path = RESULTS_DIR / f"results_{ts}.json"
    with open(ts_path, "w") as f:
        json.dump(data, f, indent=2)

    return ts_path


def load_baseline() -> Optional[Dict[str, Any]]:
    """Load the saved baseline, or None if it doesn't exist."""
    if not BASELINE_FILE.exists():
        return None
    try:
        with open(BASELINE_FILE, "r") as f:
            return json.load(f)
    except Exception as exc:
        print(yellow(f"  Warning: Could not load baseline: {exc}"))
        return None


# ---------------------------------------------------------------------------
# Formatting Helpers
# ---------------------------------------------------------------------------

def _fmt_dollar(value: Optional[float], width: int = 10) -> str:
    """Format a dollar value right-aligned."""
    if value is None:
        return "N/A".rjust(width)
    sign = "" if value >= 0 else "-"
    return f"{sign}${abs(value):,.2f}".rjust(width)


def _fmt_delta(current: Optional[float], baseline_val: Optional[float], width: int = 9) -> str:
    """Format a delta value with +/- prefix and color."""
    if current is None or baseline_val is None:
        return "—".center(width)
    diff = current - baseline_val
    if abs(diff) < 0.005:
        return dim("  $0.00".ljust(width))
    sign_char = "+" if diff >= 0 else "-"
    text = f"{sign_char}${abs(diff):,.0f}"
    if diff > 0:
        return green(text.rjust(width))
    else:
        return red(text.rjust(width))


def _truncate(text: str, max_len: int) -> str:
    """Truncate text with ellipsis if needed."""
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


# ---------------------------------------------------------------------------
# Table Rendering
# ---------------------------------------------------------------------------

# Column widths
COL_CASE = 22
COL_SYM = 6
COL_OUR = 10
COL_ROSS = 10
COL_DELTA = 9
COL_ENTRY = 23
COL_TRADES = 6

TABLE_INNER_WIDTH = COL_CASE + COL_SYM + COL_OUR + COL_ROSS + COL_DELTA + COL_ENTRY + COL_TRADES + 6 * 3  # 6 separators × 3 chars


def _hline(left: str, mid: str, right: str, fill: str = "═") -> str:
    """Render a horizontal line with connectors."""
    segments = [
        fill * (COL_CASE + 2),
        fill * (COL_SYM + 2),
        fill * (COL_OUR + 2),
        fill * (COL_ROSS + 2),
        fill * (COL_DELTA + 2),
        fill * (COL_ENTRY + 2),
        fill * (COL_TRADES + 2),
    ]
    return left + mid.join(segments) + right


def _row(*cells: str) -> str:
    """Render a data row with column separators."""
    padded = [
        f" {cells[0]:<{COL_CASE}} ",
        f" {cells[1]:<{COL_SYM}} ",
        f" {cells[2]:>{COL_OUR}} ",
        f" {cells[3]:>{COL_ROSS}} ",
        f" {cells[4]:>{COL_DELTA}} ",
        f" {cells[5]:<{COL_ENTRY}} ",
        f" {cells[6]:>{COL_TRADES}} ",
    ]
    return "║" + "║".join(padded) + "║"


def render_results_table(
    data: Dict[str, Any],
    baseline: Optional[Dict[str, Any]] = None,
) -> None:
    """Render the full results table to stdout."""
    results: List[Dict] = data.get("results", [])
    summary: Dict = data.get("summary", {})

    # Build baseline lookup
    bl_map: Dict[str, float] = {}
    if baseline:
        for r in baseline.get("results", []):
            bl_map[r["case_id"]] = r.get("total_pnl", 0.0)

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    title = f"Mock Market Test Results — {now_str}"
    if baseline:
        title += "  [vs baseline]"

    # Header
    header_width = TABLE_INNER_WIDTH + 2  # +2 for outer ║
    print()
    print("╔" + "═" * header_width + "╗")
    print("║" + bold(title.center(header_width)) + "║")
    print(_hline("╠", "╦", "╣"))
    print(_row("Case ID", "Sym", "Our P&L", "Ross P&L", "Delta", "Entry", "Trades"))
    print(_hline("╠", "╬", "╣"))

    # Data rows
    total_our = 0.0
    total_ross = 0.0
    case_count = 0
    errors = []

    for r in results:
        case_id = r.get("case_id", "?")
        symbol = r.get("symbol", "?")
        our_pnl = r.get("total_pnl")
        ross_pnl = r.get("ross_pnl")
        trades = r.get("trades", [])
        error = r.get("error")

        if error:
            errors.append((case_id, error))
            # Show error row
            entry_info = red("ERROR")
            print(_row(
                _truncate(case_id, COL_CASE),
                symbol[:COL_SYM],
                "ERR".rjust(COL_OUR),
                _fmt_dollar(ross_pnl, COL_ROSS),
                "—".center(COL_DELTA),
                entry_info,
                "0".rjust(COL_TRADES),
            ))
            continue

        case_count += 1

        if our_pnl is not None:
            total_our += our_pnl
        if ross_pnl is not None:
            total_ross += ross_pnl

        # Entry info from first trade
        if trades and len(trades) > 0:
            first_trade = trades[0]
            trigger = first_trade.get("entry_trigger", "?")
            price = first_trade.get("entry_price", 0)
            entry_info = f"{trigger} @{price:.2f}"
        else:
            entry_info = "no entry"

        # Delta calculation
        if baseline and case_id in bl_map:
            delta_str = _fmt_delta(our_pnl, bl_map[case_id])
        elif baseline:
            delta_str = yellow("NEW".center(COL_DELTA))
        else:
            # No baseline → show delta vs Ross
            delta_str = _fmt_delta(our_pnl, ross_pnl)

        # Color the our_pnl
        our_str = _fmt_dollar(our_pnl, COL_OUR)
        if our_pnl is not None:
            if our_pnl > 0:
                our_str = green(our_str)
            elif our_pnl < 0:
                our_str = red(our_str)

        trade_count = str(len(trades))

        print(_row(
            _truncate(case_id, COL_CASE),
            symbol[:COL_SYM],
            our_str,
            _fmt_dollar(ross_pnl, COL_ROSS),
            delta_str,
            _truncate(entry_info, COL_ENTRY),
            trade_count.rjust(COL_TRADES),
        ))

    # Summary row
    print(_hline("╠", "╬", "╣"))

    total_delta: str
    if baseline:
        bl_total = baseline.get("summary", {}).get("total_pnl", 0.0)
        total_delta = _fmt_delta(total_our, bl_total)
    else:
        total_delta = _fmt_delta(total_our, total_ross)

    total_our_str = bold(_fmt_dollar(total_our, COL_OUR))
    cases_label = f"{case_count} cases"

    print(_row(
        bold("TOTAL"),
        "",
        total_our_str,
        _fmt_dollar(total_ross, COL_ROSS),
        total_delta,
        cases_label,
        "",
    ))
    print(_hline("╚", "╩", "╝"))

    # Footer
    runtime = summary.get("runtime_seconds", 0)
    print(dim(f"  Runtime: {runtime:.1f}s"))

    if errors:
        print()
        print(red(f"  ⚠ {len(errors)} case(s) failed:"))
        for cid, err in errors:
            print(red(f"    • {cid}: {err}"))

    print()


# ---------------------------------------------------------------------------
# Summary Stats
# ---------------------------------------------------------------------------

def print_summary_stats(data: Dict[str, Any], baseline: Optional[Dict[str, Any]] = None) -> None:
    """Print quick summary statistics below the table."""
    results = data.get("results", [])
    if not results:
        return

    winners = [r for r in results if r.get("total_pnl") is not None and r["total_pnl"] > 0 and not r.get("error")]
    losers = [r for r in results if r.get("total_pnl") is not None and r["total_pnl"] < 0 and not r.get("error")]
    flat = [r for r in results if r.get("total_pnl") is not None and r["total_pnl"] == 0 and not r.get("error")]
    no_entry = [r for r in results if r.get("total_pnl") is None and not r.get("error")]

    print(f"  {green('Winners')}: {len(winners)}  |  {red('Losers')}: {len(losers)}  |  Flat: {len(flat)}  |  No entry: {len(no_entry)}")

    if winners:
        best = max(winners, key=lambda r: r["total_pnl"])
        print(f"  Best: {green(best['symbol'])} {_fmt_dollar(best['total_pnl']).strip()}")
    if losers:
        worst = min(losers, key=lambda r: r["total_pnl"])
        print(f"  Worst: {red(worst['symbol'])} {_fmt_dollar(worst['total_pnl']).strip()}")

    # Win rate
    decided = len(winners) + len(losers)
    if decided > 0:
        wr = len(winners) / decided * 100
        wr_str = f"{wr:.0f}%"
        if wr >= 60:
            wr_str = green(wr_str)
        elif wr < 40:
            wr_str = red(wr_str)
        print(f"  Win rate: {wr_str} ({len(winners)}/{decided})")

    print()


# ---------------------------------------------------------------------------
# CLI Entry Point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Mock Market Test Runner — runs batch tests and compares results",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m nexus2.scripts.run_tests                     Run all test cases
  python -m nexus2.scripts.run_tests --baseline save     Save results as baseline
  python -m nexus2.scripts.run_tests --compare           Compare against saved baseline
  python -m nexus2.scripts.run_tests --cases ross_pavm_20260121 ross_npt_20260203
        """,
    )
    parser.add_argument(
        "--baseline",
        choices=["save"],
        help="Save current results as the baseline for future comparison",
    )
    parser.add_argument(
        "--compare",
        action="store_true",
        help="Compare results against saved baseline",
    )
    parser.add_argument(
        "--cases",
        nargs="+",
        metavar="CASE_ID",
        help="Run only specific test case IDs",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=300.0,
        help="HTTP timeout in seconds (default: 300)",
    )
    parser.add_argument(
        "--server",
        default=None,
        help=f"Server URL (default: {SERVER_URL})",
    )

    args = parser.parse_args()

    # Override server URL if provided
    global BATCH_ENDPOINT
    if args.server:
        BATCH_ENDPOINT = f"{args.server}/warrior/sim/run_batch"

    # Load baseline if comparing
    baseline: Optional[Dict[str, Any]] = None
    if args.compare:
        baseline = load_baseline()
        if baseline is None:
            print(yellow("  No baseline found. Run with --baseline save first."))
            print(f"  Expected at: {BASELINE_FILE}")
            sys.exit(1)

    # Call the endpoint
    print(dim(f"  Calling {BATCH_ENDPOINT} ..."))
    start = time.time()
    data = call_batch_endpoint(case_ids=args.cases, timeout=args.timeout)
    elapsed = time.time() - start

    # Inject client-side timing if server didn't provide it
    if "summary" not in data:
        data["summary"] = {}
    if "runtime_seconds" not in data["summary"]:
        data["summary"]["runtime_seconds"] = elapsed

    # Render
    render_results_table(data, baseline=baseline)
    print_summary_stats(data, baseline=baseline)

    # Save baseline if requested
    if args.baseline == "save":
        ts_path = save_baseline(data)
        print(green(f"  ✓ Baseline saved to {BASELINE_FILE.name}"))
        print(dim(f"    Timestamped copy: {ts_path.name}"))
        print()

    # Always save timestamped results
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_path = RESULTS_DIR / f"results_{ts}.json"
    with open(run_path, "w") as f:
        json.dump(data, f, indent=2)
    print(dim(f"  Results saved: {run_path.name}"))


if __name__ == "__main__":
    main()
