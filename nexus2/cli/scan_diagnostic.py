"""
Retroactive Scan Diagnostic Tool

Checks whether a given symbol would have appeared in the scanner's data sources
and whether it would pass all scanner filter stages for a historical date.

Usage:
    python -m nexus2.cli.scan_diagnostic EVMN 2026-02-10
    python -m nexus2.cli.scan_diagnostic --all-test-cases
    python -m nexus2.cli.scan_diagnostic --all-test-cases --output report.md
"""

import argparse
import sys
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ─── ANSI colors ────────────────────────────────────────────────────────────────
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"


def _pass(text: str = "PASS") -> str:
    return f"{GREEN}{text}{RESET}"


def _fail(text: str = "FAIL") -> str:
    return f"{RED}{text}{RESET}"


def _warn(text: str) -> str:
    return f"{YELLOW}{text}{RESET}"


def _cyan(text: str) -> str:
    return f"{CYAN}{text}{RESET}"


def _bold(text: str) -> str:
    return f"{BOLD}{text}{RESET}"


def _format_float_shares(value: Optional[int]) -> str:
    """Format float shares for display."""
    if value is None:
        return "N/A"
    if value >= 1_000_000_000:
        return f"{value / 1_000_000_000:.1f}B"
    elif value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    elif value >= 1_000:
        return f"{value / 1_000:.1f}K"
    return str(value)


def _format_volume(value: int) -> str:
    """Format volume with commas."""
    return f"{value:,}"


# ─── Diagnostic Result ──────────────────────────────────────────────────────────

@dataclass
class FilterResult:
    stage: int
    name: str
    passed: bool
    detail: str = ""


@dataclass
class DiagnosticResult:
    symbol: str
    date: str
    
    # Data source presence
    fmp_gainers: str = "UNAVAILABLE"
    polygon_gainers: str = "UNAVAILABLE"
    alpaca_movers: str = "UNAVAILABLE"
    
    # Market data
    open_price: Optional[Decimal] = None
    close_price: Optional[Decimal] = None
    prev_close: Optional[Decimal] = None
    gap_pct: Optional[float] = None
    day_volume: Optional[int] = None
    float_shares: Optional[int] = None
    avg_volume: Optional[int] = None
    rvol: Optional[float] = None
    ema_200: Optional[Decimal] = None
    ema_200_room_pct: Optional[float] = None
    country: Optional[str] = None
    
    # News
    headlines: List[Tuple[str, str]] = field(default_factory=list)  # (headline, date)
    
    # Filter results
    filters: List[FilterResult] = field(default_factory=list)
    
    # Final verdict
    would_pass: bool = False
    fail_stage: Optional[str] = None
    
    # Errors
    errors: List[str] = field(default_factory=list)


# ─── Core Diagnostic Logic ──────────────────────────────────────────────────────

def _get_previous_trading_day(date_str: str) -> str:
    """Get the previous trading day (skip weekends)."""
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    dt -= timedelta(days=1)
    # Skip weekends
    while dt.weekday() >= 5:  # 5=Sat, 6=Sun
        dt -= timedelta(days=1)
    return dt.strftime("%Y-%m-%d")


def _compute_ema(closes: List[Decimal], period: int) -> Optional[Decimal]:
    """Compute EMA from a list of closing prices (oldest first)."""
    if len(closes) < period:
        return None
    multiplier = Decimal(2) / (Decimal(period) + 1)
    ema = closes[0]
    for close in closes[1:]:
        ema = (close * multiplier) + (ema * (1 - multiplier))
    return ema


def run_diagnostic(symbol: str, date_str: str) -> DiagnosticResult:
    """
    Run full diagnostic for a symbol on a given date.
    
    Uses Polygon for historical daily bars (reliable) and FMP for fundamentals.
    """
    from nexus2.adapters.market_data.polygon_adapter import PolygonAdapter
    from nexus2.adapters.market_data.fmp_adapter import FMPAdapter
    from nexus2.domain.scanner.warrior_scanner_service import is_tradeable_equity
    from nexus2 import config as app_config
    
    result = DiagnosticResult(symbol=symbol, date=date_str)
    
    # Initialize adapters
    polygon = PolygonAdapter()
    fmp = FMPAdapter()
    
    # ── Data Source Presence ──────────────────────────────────────────────────
    # Gainers endpoints are live-only — cannot check historical
    result.fmp_gainers = "UNAVAILABLE (live-only, cannot check historical)"
    result.polygon_gainers = "UNAVAILABLE (live-only, cannot check historical)"
    result.alpaca_movers = "UNAVAILABLE (live-only, cannot check historical)"
    
    # ── Historical Price Data (Polygon) ──────────────────────────────────────
    prev_day = _get_previous_trading_day(date_str)
    
    # Get trade date bars
    try:
        trade_bars = polygon.get_daily_bars(
            symbol, from_date=date_str, to_date=date_str
        )
        if trade_bars and len(trade_bars) > 0:
            bar = trade_bars[-1]  # Last bar for the date
            result.open_price = bar.open
            result.close_price = bar.close
            result.day_volume = int(bar.volume)
        else:
            result.errors.append(f"No Polygon daily bars for {date_str}")
    except Exception as e:
        result.errors.append(f"Polygon daily bars error: {e}")
    
    # Get previous close
    try:
        prev_bars = polygon.get_daily_bars(
            symbol, from_date=prev_day, to_date=prev_day
        )
        if prev_bars and len(prev_bars) > 0:
            result.prev_close = prev_bars[-1].close
        else:
            # Try a wider range to find the previous trading day
            wider_start = (datetime.strptime(date_str, "%Y-%m-%d") - timedelta(days=7)).strftime("%Y-%m-%d")
            wider_bars = polygon.get_daily_bars(
                symbol, from_date=wider_start, to_date=prev_day
            )
            if wider_bars and len(wider_bars) > 0:
                result.prev_close = wider_bars[-1].close
            else:
                result.errors.append(f"No prev close data found")
    except Exception as e:
        result.errors.append(f"Prev close error: {e}")
    
    # Calculate gap %
    if result.open_price and result.prev_close and result.prev_close > 0:
        result.gap_pct = float(
            (result.open_price - result.prev_close) / result.prev_close * 100
        )
    
    # ── Float Shares (FMP, current data) ─────────────────────────────────────
    try:
        import httpx
        response = httpx.get(
            "https://financialmodelingprep.com/stable/shares-float",
            params={"symbol": symbol, "apikey": app_config.FMP_API_KEY},
            timeout=10.0,
        )
        response.raise_for_status()
        float_data = response.json()
        if float_data and len(float_data) > 0:
            float_val = float_data[0].get("floatShares")
            if float_val:
                result.float_shares = int(float_val)
    except Exception as e:
        result.errors.append(f"Float shares error: {e}")
    
    # ── Average Volume & RVOL ────────────────────────────────────────────────
    try:
        # Get 30 trading days before the date for avg volume
        lookback_start = (
            datetime.strptime(date_str, "%Y-%m-%d") - timedelta(days=45)
        ).strftime("%Y-%m-%d")
        hist_bars = polygon.get_daily_bars(
            symbol, limit=50, from_date=lookback_start, to_date=prev_day
        )
        if hist_bars and len(hist_bars) >= 5:
            # Use last 20 bars (or all if <20)
            recent_bars = hist_bars[-20:]
            volumes = [int(b.volume) for b in recent_bars]
            result.avg_volume = int(sum(volumes) / len(volumes))
            
            if result.day_volume and result.avg_volume > 0:
                result.rvol = result.day_volume / result.avg_volume
        else:
            result.errors.append("Insufficient historical bars for RVOL calculation")
    except Exception as e:
        result.errors.append(f"RVOL calculation error: {e}")
    
    # ── 200 EMA ──────────────────────────────────────────────────────────────
    try:
        ema_start = (
            datetime.strptime(date_str, "%Y-%m-%d") - timedelta(days=500)
        ).strftime("%Y-%m-%d")
        ema_bars = polygon.get_daily_bars(
            symbol, limit=500, from_date=ema_start, to_date=date_str
        )
        if ema_bars and len(ema_bars) >= 200:
            closes = [b.close for b in ema_bars]
            result.ema_200 = _compute_ema(closes, 200)
            if result.ema_200 and result.open_price and result.ema_200 > 0:
                result.ema_200_room_pct = float(
                    (result.open_price - result.ema_200) / result.ema_200 * 100
                )
        else:
            bar_count = len(ema_bars) if ema_bars else 0
            result.errors.append(f"Only {bar_count} bars for 200 EMA (need 200)")
    except Exception as e:
        result.errors.append(f"200 EMA error: {e}")
    
    # ── Country (for Chinese stock check) ────────────────────────────────────
    try:
        result.country = fmp.get_country(symbol)
    except Exception as e:
        result.errors.append(f"Country lookup error: {e}")
    
    # ── News Headlines ───────────────────────────────────────────────────────
    try:
        news = fmp.get_stock_news(symbol, limit=20)
        trade_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        window_start = trade_date - timedelta(days=5)
        window_end = trade_date + timedelta(days=1)
        
        for item in news:
            pub_str = item.get("date", "")
            title = item.get("title", "")
            if pub_str and title:
                try:
                    pub_date = datetime.fromisoformat(
                        pub_str.replace("Z", "+00:00")
                    ).date()
                    if window_start <= pub_date <= window_end:
                        result.headlines.append((title, pub_date.isoformat()))
                except (ValueError, TypeError):
                    result.headlines.append((title, "unknown"))
    except Exception as e:
        result.errors.append(f"News lookup error: {e}")
    
    # ── Filter Walkthrough ───────────────────────────────────────────────────
    stage = 0
    all_passed = True
    
    # [1] Tradeable equity check
    stage += 1
    equity_pass = is_tradeable_equity(symbol)
    result.filters.append(FilterResult(
        stage=stage,
        name="Tradeable equity check",
        passed=equity_pass,
        detail="" if equity_pass else "Non-equity ticker (warrant/unit/right)",
    ))
    if not equity_pass:
        all_passed = False
        result.fail_stage = "Tradeable equity"
    
    # [2] Price range ($1.50 - $20)
    stage += 1
    price_val = result.open_price
    if price_val is not None:
        price_pass = Decimal("1.50") <= price_val <= Decimal("20.00")
        result.filters.append(FilterResult(
            stage=stage,
            name="Price range ($1.50-$20)",
            passed=price_pass,
            detail=f"${price_val:.2f}",
        ))
        if all_passed and not price_pass:
            all_passed = False
            result.fail_stage = f"Price (${price_val:.2f})"
    else:
        result.filters.append(FilterResult(
            stage=stage,
            name="Price range ($1.50-$20)",
            passed=False,
            detail="NO DATA",
        ))
        if all_passed:
            all_passed = False
            result.fail_stage = "Price (no data)"
    
    # [3] Gap % (min 4%)
    stage += 1
    if result.gap_pct is not None:
        gap_pass = result.gap_pct >= 4.0
        result.filters.append(FilterResult(
            stage=stage,
            name="Gap % (min 4%)",
            passed=gap_pass,
            detail=f"{result.gap_pct:.1f}%",
        ))
        if all_passed and not gap_pass:
            all_passed = False
            result.fail_stage = f"Gap ({result.gap_pct:.1f}%)"
    else:
        result.filters.append(FilterResult(
            stage=stage,
            name="Gap % (min 4%)",
            passed=False,
            detail="NO DATA",
        ))
        if all_passed:
            all_passed = False
            result.fail_stage = "Gap (no data)"
    
    # [4] Float (max 100M)
    stage += 1
    if result.float_shares is not None:
        float_pass = result.float_shares <= 100_000_000
        result.filters.append(FilterResult(
            stage=stage,
            name="Float (max 100M)",
            passed=float_pass,
            detail=f"{_format_float_shares(result.float_shares)}",
        ))
        if all_passed and not float_pass:
            all_passed = False
            result.fail_stage = f"Float ({_format_float_shares(result.float_shares)})"
    else:
        # Float unknown = scanner would PASS (skip check)
        result.filters.append(FilterResult(
            stage=stage,
            name="Float (max 100M)",
            passed=True,
            detail="N/A (unknown = skip)",
        ))
    
    # [5] RVOL (min 2.0x)
    stage += 1
    if result.rvol is not None:
        rvol_pass = result.rvol >= 2.0
        result.filters.append(FilterResult(
            stage=stage,
            name="RVOL (min 2.0x)",
            passed=rvol_pass,
            detail=f"{result.rvol:.1f}x",
        ))
        if all_passed and not rvol_pass:
            all_passed = False
            result.fail_stage = f"RVOL ({result.rvol:.1f}x)"
    else:
        result.filters.append(FilterResult(
            stage=stage,
            name="RVOL (min 2.0x)",
            passed=False,
            detail="NO DATA",
        ))
        if all_passed:
            all_passed = False
            result.fail_stage = "RVOL (no data)"
    
    # [6] Catalyst check
    stage += 1
    catalyst_pass = False
    catalyst_detail = "no headlines found"
    if result.headlines:
        try:
            from nexus2.domain.automation.catalyst_classifier import get_classifier
            classifier = get_classifier()
            headline_texts = [h[0] for h in result.headlines]
            has_positive, best_type, best_headline = classifier.has_positive_catalyst(
                headline_texts
            )
            if has_positive and best_type:
                match = classifier.classify(best_headline)
                if match.confidence >= 0.6:
                    catalyst_pass = True
                    catalyst_detail = f"{best_type} (conf={match.confidence:.2f})"
                else:
                    catalyst_detail = f"weak: {best_type} (conf={match.confidence:.2f})"
            else:
                catalyst_detail = f"{len(result.headlines)} headlines, none classified as positive"
        except Exception as e:
            catalyst_detail = f"classifier error: {e}"
    
    result.filters.append(FilterResult(
        stage=stage,
        name="Catalyst check",
        passed=catalyst_pass,
        detail=catalyst_detail,
    ))
    if all_passed and not catalyst_pass:
        all_passed = False
        result.fail_stage = f"Catalyst ({catalyst_detail})"
    
    # [7] 200 EMA room
    stage += 1
    if result.ema_200 is not None and result.ema_200_room_pct is not None:
        # Reject if price is below EMA but not far enough below
        # Negative % = price below EMA. We need at least -15% room (or above = auto pass)
        if result.ema_200_room_pct >= 0:
            ema_pass = True
            ema_detail = f"${result.ema_200:.2f} (above EMA, {result.ema_200_room_pct:+.1f}%)"
        elif result.ema_200_room_pct < -15.0:
            ema_pass = True
            ema_detail = f"${result.ema_200:.2f} ({result.ema_200_room_pct:+.1f}% room, enough)"
        else:
            ema_pass = False
            ema_detail = f"${result.ema_200:.2f} ({result.ema_200_room_pct:+.1f}% room < -15%)"
        
        result.filters.append(FilterResult(
            stage=stage,
            name="200 EMA room",
            passed=ema_pass,
            detail=ema_detail,
        ))
        if all_passed and not ema_pass:
            all_passed = False
            result.fail_stage = f"200 EMA ({ema_detail})"
    else:
        # No EMA data = skip check (pass)
        result.filters.append(FilterResult(
            stage=stage,
            name="200 EMA room",
            passed=True,
            detail="N/A (insufficient data = skip)",
        ))
    
    result.would_pass = all_passed
    return result


# ─── Output Formatting ──────────────────────────────────────────────────────────

def format_result(result: DiagnosticResult, use_color: bool = True) -> str:
    """Format a DiagnosticResult as a human-readable report."""
    lines = []
    
    if use_color:
        p, f, w, c, b = _pass, _fail, _warn, _cyan, _bold
    else:
        p = lambda t="PASS": t
        f = lambda t="FAIL": t
        w = lambda t: t
        c = lambda t: t
        b = lambda t: t
    
    lines.append(f"\n{'='*60}")
    lines.append(b(f"  {result.symbol} on {result.date}"))
    lines.append(f"{'='*60}")
    
    # Data source presence
    lines.append(f"\n{b('DATA SOURCE PRESENCE:')}")
    lines.append(f"  FMP Gainers:     {w(result.fmp_gainers)}")
    lines.append(f"  Polygon Gainers: {w(result.polygon_gainers)}")
    lines.append(f"  Alpaca Movers:   {w(result.alpaca_movers)}")
    
    # Market data
    lines.append(f"\n{b('MARKET DATA (reconstructed from historical APIs):')}")
    if result.open_price is not None:
        lines.append(f"  Open Price:  ${result.open_price:.2f}")
    else:
        lines.append(f"  Open Price:  {w('N/A')}")
    
    if result.close_price is not None:
        lines.append(f"  Close Price: ${result.close_price:.2f}")
    else:
        lines.append(f"  Close Price: {w('N/A')}")
    
    if result.prev_close is not None:
        lines.append(f"  Prev Close:  ${result.prev_close:.2f}")
    else:
        lines.append(f"  Prev Close:  {w('N/A')}")
    
    if result.gap_pct is not None:
        gap_str = f"{result.gap_pct:.1f}%"
        if result.gap_pct >= 4.0:
            lines.append(f"  Gap %:       {p(gap_str)}")
        else:
            lines.append(f"  Gap %:       {f(gap_str)}")
    else:
        lines.append(f"  Gap %:       {w('N/A')}")
    
    if result.day_volume is not None:
        lines.append(f"  Day Volume:  {_format_volume(result.day_volume)}")
    else:
        lines.append(f"  Day Volume:  {w('N/A')}")
    
    float_note = " (current, may differ from trade date)" if result.float_shares else ""
    lines.append(f"  Float:       {_format_float_shares(result.float_shares)}{float_note}")
    
    if result.avg_volume is not None:
        lines.append(f"  Avg Volume:  {_format_volume(result.avg_volume)} (20-day prior)")
    else:
        lines.append(f"  Avg Volume:  {w('N/A')}")
    
    if result.rvol is not None:
        rvol_str = f"{result.rvol:.1f}x"
        if result.rvol >= 2.0:
            lines.append(f"  RVOL:        {p(rvol_str)}")
        else:
            lines.append(f"  RVOL:        {f(rvol_str)}")
    else:
        lines.append(f"  RVOL:        {w('N/A')}")
    
    if result.ema_200 is not None:
        room_str = f" (room: {result.ema_200_room_pct:+.1f}%)" if result.ema_200_room_pct is not None else ""
        lines.append(f"  200 EMA:     ${result.ema_200:.2f}{room_str}")
    else:
        lines.append(f"  200 EMA:     {w('N/A (insufficient history)')}")
    
    if result.country:
        lines.append(f"  Country:     {result.country}")
    
    # Headlines
    if result.headlines:
        lines.append(f"\n  {b('News Headlines (around trade date):')}")
        for title, pub_date in result.headlines[:5]:
            title_short = title[:80] + "..." if len(title) > 80 else title
            lines.append(f"    - \"{title_short}\" ({pub_date})")
        if len(result.headlines) > 5:
            lines.append(f"    ... and {len(result.headlines) - 5} more")
    else:
        lines.append(f"\n  {w('No news headlines found around trade date')}")
    
    # Filter walkthrough
    lines.append(f"\n{b('SCANNER FILTER WALKTHROUGH:')}")
    for fr in result.filters:
        status = p("PASS") if fr.passed else f("FAIL")
        detail = f" ({fr.detail})" if fr.detail else ""
        lines.append(f"  [{fr.stage}] {fr.name + ':':<27} {status}{detail}")
    
    # Verdict
    lines.append("")
    if result.would_pass:
        lines.append(f"  {b('VERDICT:')} {p('Would PASS all filters')} ✅")
    else:
        lines.append(
            f"  {b('VERDICT:')} {f('Would FAIL')} at stage: {result.fail_stage} ❌"
        )
    
    # Errors
    if result.errors:
        lines.append(f"\n  {w('Data Collection Issues:')}")
        for err in result.errors:
            lines.append(f"    ⚠ {err}")
    
    lines.append("")
    return "\n".join(lines)


def format_result_markdown(result: DiagnosticResult) -> str:
    """Format a DiagnosticResult as markdown for file output."""
    lines = []
    
    lines.append(f"## {result.symbol} on {result.date}")
    lines.append("")
    
    lines.append("### Data Source Presence")
    lines.append(f"- FMP Gainers: {result.fmp_gainers}")
    lines.append(f"- Polygon Gainers: {result.polygon_gainers}")
    lines.append(f"- Alpaca Movers: {result.alpaca_movers}")
    lines.append("")
    
    lines.append("### Market Data")
    lines.append(f"| Metric | Value |")
    lines.append(f"|--------|-------|")
    lines.append(f"| Open Price | {'${:.2f}'.format(result.open_price) if result.open_price else 'N/A'} |")
    lines.append(f"| Close Price | {'${:.2f}'.format(result.close_price) if result.close_price else 'N/A'} |")
    lines.append(f"| Prev Close | {'${:.2f}'.format(result.prev_close) if result.prev_close else 'N/A'} |")
    lines.append(f"| Gap % | {'{:.1f}%'.format(result.gap_pct) if result.gap_pct is not None else 'N/A'} |")
    lines.append(f"| Day Volume | {_format_volume(result.day_volume) if result.day_volume else 'N/A'} |")
    lines.append(f"| Float | {_format_float_shares(result.float_shares)} |")
    lines.append(f"| Avg Volume (20d) | {_format_volume(result.avg_volume) if result.avg_volume else 'N/A'} |")
    lines.append(f"| RVOL | {'{:.1f}x'.format(result.rvol) if result.rvol is not None else 'N/A'} |")
    lines.append(f"| 200 EMA | {'${:.2f} ({:+.1f}%)'.format(result.ema_200, result.ema_200_room_pct) if result.ema_200 and result.ema_200_room_pct is not None else 'N/A'} |")
    lines.append(f"| Country | {result.country or 'N/A'} |")
    lines.append("")
    
    if result.headlines:
        lines.append("### News Headlines")
        for title, pub_date in result.headlines[:5]:
            lines.append(f"- \"{title[:100]}\" ({pub_date})")
        lines.append("")
    
    lines.append("### Filter Walkthrough")
    lines.append("| # | Filter | Result | Detail |")
    lines.append("|---|--------|--------|--------|")
    for fr in result.filters:
        status = "✅ PASS" if fr.passed else "❌ FAIL"
        lines.append(f"| {fr.stage} | {fr.name} | {status} | {fr.detail} |")
    lines.append("")
    
    verdict = "✅ **Would PASS all filters**" if result.would_pass else f"❌ **Would FAIL** at: {result.fail_stage}"
    lines.append(f"**VERDICT:** {verdict}")
    lines.append("")
    
    if result.errors:
        lines.append("### Data Collection Issues")
        for err in result.errors:
            lines.append(f"- ⚠️ {err}")
        lines.append("")
    
    lines.append("---")
    lines.append("")
    return "\n".join(lines)


# ─── Batch Mode ──────────────────────────────────────────────────────────────────

def run_batch(yaml_path: str) -> Tuple[List[DiagnosticResult], str]:
    """Run diagnostic for all test cases in the YAML file."""
    import yaml
    
    with open(yaml_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    
    test_cases = data.get("test_cases", [])
    results = []
    
    # Filter out synthetic test cases
    real_cases = [
        tc for tc in test_cases
        if not tc.get("synthetic", False)
        and tc.get("trade_date")
        and tc.get("symbol")
    ]
    
    print(f"\n{_bold('Batch Diagnostic Mode')}")
    print(f"Found {len(real_cases)} real test cases (skipped {len(test_cases) - len(real_cases)} synthetic)\n")
    
    for i, tc in enumerate(real_cases, 1):
        symbol = tc["symbol"]
        date = tc["trade_date"]
        print(f"  [{i}/{len(real_cases)}] {symbol} on {date}...", end=" ", flush=True)
        
        try:
            result = run_diagnostic(symbol, date)
            results.append(result)
            if result.would_pass:
                print(_pass("PASS"))
            else:
                print(_fail(f"FAIL ({result.fail_stage})"))
        except Exception as e:
            print(_fail(f"ERROR: {e}"))
            err_result = DiagnosticResult(symbol=symbol, date=date)
            err_result.errors.append(str(e))
            err_result.fail_stage = f"Error: {e}"
            results.append(err_result)
    
    # Build summary table
    summary_lines = []
    summary_lines.append(f"\n{'='*100}")
    summary_lines.append(_bold("  BATCH SUMMARY"))
    summary_lines.append(f"{'='*100}")
    summary_lines.append(
        f"  {'Symbol':<8} {'Date':<12} {'Gap%':>6} {'Float':>8} {'RVOL':>6} "
        f"{'Catalyst':>10} {'Result':>8} {'Fail Stage'}"
    )
    summary_lines.append(f"  {'-'*90}")
    
    pass_count = 0
    for r in results:
        gap_str = f"{r.gap_pct:.1f}%" if r.gap_pct is not None else "N/A"
        float_str = _format_float_shares(r.float_shares)
        rvol_str = f"{r.rvol:.1f}x" if r.rvol is not None else "N/A"
        
        # Get catalyst type from filter results
        catalyst_fr = next((fr for fr in r.filters if "Catalyst" in fr.name), None)
        catalyst_str = catalyst_fr.detail[:10] if catalyst_fr else "?"
        
        result_str = _pass("PASS") if r.would_pass else _fail("FAIL")
        fail_str = r.fail_stage or ""
        
        if r.would_pass:
            pass_count += 1
        
        summary_lines.append(
            f"  {r.symbol:<8} {r.date:<12} {gap_str:>6} {float_str:>8} {rvol_str:>6} "
            f"{catalyst_str:>10} {result_str:>17} {fail_str}"
        )
    
    summary_lines.append(f"\n  Total: {len(results)} | Pass: {pass_count} | Fail: {len(results) - pass_count}")
    summary_lines.append("")
    
    summary = "\n".join(summary_lines)
    return results, summary


def format_batch_markdown(results: List[DiagnosticResult]) -> str:
    """Format batch results as a markdown report."""
    lines = []
    lines.append("# Scanner Diagnostic Results")
    lines.append(f"")
    lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")
    
    # Summary table
    lines.append("## Summary")
    lines.append("")
    lines.append("| Symbol | Date | Gap% | Float | RVOL | Catalyst | Would Pass? | Fail Stage |")
    lines.append("|--------|------|------|-------|------|----------|------------|------------|")
    
    pass_count = 0
    for r in results:
        gap_str = f"{r.gap_pct:.1f}%" if r.gap_pct is not None else "N/A"
        float_str = _format_float_shares(r.float_shares)
        rvol_str = f"{r.rvol:.1f}x" if r.rvol is not None else "N/A"
        
        catalyst_fr = next((fr for fr in r.filters if "Catalyst" in fr.name), None)
        catalyst_str = catalyst_fr.detail[:25] if catalyst_fr else "?"
        
        result_str = "✅ PASS" if r.would_pass else "❌ FAIL"
        fail_str = r.fail_stage or "-"
        
        if r.would_pass:
            pass_count += 1
        
        lines.append(
            f"| {r.symbol} | {r.date} | {gap_str} | {float_str} | {rvol_str} | "
            f"{catalyst_str} | {result_str} | {fail_str} |"
        )
    
    lines.append("")
    lines.append(f"**Total: {len(results)} | Pass: {pass_count} | Fail: {len(results) - pass_count}**")
    lines.append("")
    
    # Detailed results
    lines.append("## Detailed Results")
    lines.append("")
    for r in results:
        lines.append(format_result_markdown(r))
    
    return "\n".join(lines)


# ─── Main ────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Retroactive Scan Diagnostic Tool — check historical scanner coverage",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m nexus2.cli.scan_diagnostic EVMN 2026-02-10
  python -m nexus2.cli.scan_diagnostic --all-test-cases
  python -m nexus2.cli.scan_diagnostic --all-test-cases --output report.md
  python -m nexus2.cli.scan_diagnostic VELO 2026-02-10 PMI 2026-02-12
        """,
    )
    parser.add_argument(
        "symbols_dates",
        nargs="*",
        help="Symbol and date pairs: SYMBOL DATE [SYMBOL DATE ...]",
    )
    parser.add_argument(
        "--all-test-cases",
        action="store_true",
        help="Run diagnostic for all test cases in warrior_setups.yaml",
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        help="Save markdown output to file",
    )
    
    args = parser.parse_args()
    
    if not args.all_test_cases and not args.symbols_dates:
        parser.print_help()
        sys.exit(1)
    
    # Validate symbol/date pairs
    if args.symbols_dates:
        if len(args.symbols_dates) % 2 != 0:
            print(f"{_fail('ERROR')}: Symbol/date arguments must be in pairs (SYMBOL DATE)")
            sys.exit(1)
    
    all_results = []
    
    if args.all_test_cases:
        # Find YAML file
        yaml_path = Path(__file__).parent.parent / "tests" / "test_cases" / "warrior_setups.yaml"
        if not yaml_path.exists():
            print(f"{_fail('ERROR')}: Test cases file not found: {yaml_path}")
            sys.exit(1)
        
        results, summary = run_batch(str(yaml_path))
        all_results.extend(results)
        print(summary)
        
        # Print detailed output for each
        for r in results:
            print(format_result(r))
    
    elif args.symbols_dates:
        pairs = list(zip(args.symbols_dates[::2], args.symbols_dates[1::2]))
        for symbol, date in pairs:
            symbol = symbol.upper()
            print(f"\nRunning diagnostic for {_bold(symbol)} on {_bold(date)}...")
            try:
                result = run_diagnostic(symbol, date)
                all_results.append(result)
                print(format_result(result))
            except Exception as e:
                print(f"{_fail('ERROR')}: {e}")
                import traceback
                traceback.print_exc()
    
    # Save output if requested
    if args.output and all_results:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        md_content = format_batch_markdown(all_results) if len(all_results) > 1 else format_result_markdown(all_results[0])
        
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(md_content)
        
        print(f"\n{_pass('Saved')} markdown report to: {output_path}")


if __name__ == "__main__":
    main()
