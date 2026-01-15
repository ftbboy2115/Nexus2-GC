"""
Momentum Scanner CLI

Scan for momentum stocks meeting KK criteria.

Usage:
    python -m nexus2.cli.scan_momentum [--min-rs 80] [--output results.csv]
"""

import argparse
import csv
import sys
from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from nexus2.adapters.market_data import UnifiedMarketData
from nexus2.domain.scanner.models import (
    Stock,
    StockMetrics,
    ScannerResult,
    Exchange,
    WatchlistTier,
)
from nexus2.domain.scanner.scanner_engine import ScannerEngine
from nexus2.settings.scanner_settings import (
    ScannerSettings,
    DisqualifierSettings,
    QualityScoringSettings,
)
from nexus2.utils.time_utils import now_et


def print_header():
    """Print CLI header."""
    print("\n" + "=" * 70)
    print("  NEXUS 2 - Momentum Scanner")
    print("  KK-Style Stock Selection")
    print("=" * 70)
    print(f"  {now_et().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70 + "\n")


def tier_emoji(tier: WatchlistTier) -> str:
    """Get emoji for tier."""
    return {
        WatchlistTier.FOCUS: "🎯",
        WatchlistTier.WIDE: "📋",
        WatchlistTier.UNIVERSE: "📊",
    }.get(tier, "")


def print_result(result: ScannerResult, idx: int):
    """Print a single scanner result."""
    emoji = tier_emoji(result.tier_recommendation)
    quality = f"Q{result.quality_score}"
    price = f"${result.stock.price:.2f}"
    
    # Get key metrics
    rs = f"RS{result.metrics.rs_percentile}"
    adr = f"ADR{result.metrics.adr_percent:.1f}%"
    
    print(f"  {idx:2d}. {emoji} {result.stock.symbol:6s} | {price:10s} | "
          f"{quality:3s} | {rs:5s} | {adr:8s} | {result.tier_recommendation.value}")


def print_results(results: List[ScannerResult], show_failed: bool = False):
    """Print scan results."""
    passing = [r for r in results if r.passes_filter]
    
    if not passing:
        print("  No stocks found matching all criteria.\n")
        return
    
    # Group by tier
    focus = [r for r in passing if r.tier_recommendation == WatchlistTier.FOCUS]
    wide = [r for r in passing if r.tier_recommendation == WatchlistTier.WIDE]
    universe = [r for r in passing if r.tier_recommendation == WatchlistTier.UNIVERSE]
    
    print(f"  Found {len(passing)} stocks passing filter:\n")
    
    if focus:
        print("  🎯 FOCUS LIST (High Quality):")
        print("-" * 70)
        for idx, r in enumerate(focus[:10], 1):  # Top 10
            print_result(r, idx)
        print()
    
    if wide:
        print("  📋 WIDE LIST (Quality):")
        print("-" * 70)
        for idx, r in enumerate(wide[:15], 1):  # Top 15
            print_result(r, idx)
        print()
    
    if universe and show_failed:
        print("  📊 UNIVERSE (Watchable):")
        print("-" * 70)
        for idx, r in enumerate(universe[:20], 1):  # Top 20
            print_result(r, idx)
        print()


def export_csv(results: List[ScannerResult], filename: str):
    """Export results to CSV."""
    passing = [r for r in results if r.passes_filter]
    
    with open(filename, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "Symbol", "Name", "Exchange", "Price", "MarketCap",
            "AvgVolume", "ADR%", "RS", "Quality", "Tier",
            "vs50MA", "vs200MA", "MAStacked"
        ])
        
        for r in passing:
            writer.writerow([
                r.stock.symbol,
                r.stock.name,
                r.stock.exchange.value,
                f"{r.stock.price:.2f}",
                f"{r.stock.market_cap:,.0f}",
                f"{r.stock.avg_volume_20d:,}",
                f"{r.metrics.adr_percent:.2f}",
                r.metrics.rs_percentile,
                r.quality_score,
                r.tier_recommendation.value,
                f"{r.metrics.price_vs_sma50:.2f}",
                f"{r.metrics.price_vs_sma200:.2f}",
                r.metrics.ma_stacked,
            ])
    
    print(f"  Results exported to: {filename}\n")


def run_scan(
    min_price: float = 5.0,
    min_volume: int = 300_000,
    min_adr: float = 4.0,
    min_rs: int = 50,
    require_above_50ma: bool = True,
    require_above_200ma: bool = True,
    output_file: Optional[str] = None,
    show_universe: bool = False,
    verbose: bool = False,
):
    """
    Run the momentum scanner.
    
    Args:
        min_price: Minimum stock price
        min_volume: Minimum average volume
        min_adr: Minimum ADR%
        min_rs: Minimum RS percentile (not fully implemented yet)
        require_above_50ma: Require above 50-day MA
        require_above_200ma: Require above 200-day MA
        output_file: Optional CSV output file
        show_universe: Show universe tier stocks
        verbose: Print verbose output
    """
    print_header()
    
    # Initialize
    print("  Initializing market data...")
    market = UnifiedMarketData()
    
    settings = ScannerSettings(
        min_price=Decimal(str(min_price)),
        min_avg_volume=min_volume,
        min_adr_percent=Decimal(str(min_adr)),
        require_above_50ma=require_above_50ma,
        require_above_200ma=require_above_200ma,
    )
    disqualifiers = DisqualifierSettings()
    scoring = QualityScoringSettings()
    
    scanner = ScannerEngine(settings, disqualifiers, scoring)
    
    # Step 1: Screen for candidates
    print(f"  Step 1: Screening stocks (price > ${min_price}, volume > {min_volume:,})...")
    raw_candidates = market.screen_stocks(
        min_market_cap=300_000_000,
        min_price=min_price,
        min_volume=min_volume,
    )
    print(f"          Found {len(raw_candidates)} raw candidates")
    
    if not raw_candidates:
        print("\n  No candidates found from screener.\n")
        return []
    
    # Step 2: Evaluate each stock
    print(f"  Step 2: Evaluating KK criteria...")
    
    results = []
    processed = 0
    
    for candidate in raw_candidates[:200]:  # Limit for speed
        processed += 1
        if processed % 20 == 0:
            print(f"\r          Processing {processed}/200...", end="")
        
        symbol = candidate["symbol"]
        
        try:
            # Get stock info
            info = market.get_stock_info(symbol)
            if not info:
                continue
            
            # Get daily bars for calculations
            bars = market.get_daily_bars(symbol, limit=60)
            if not bars or len(bars) < 50:
                continue
            
            # Calculate metrics
            adr = market.get_adr_percent(symbol) or Decimal("0")
            sma50 = market.get_sma(symbol, 50) or Decimal("0")
            sma200 = market.get_sma(symbol, 200) or Decimal("0")
            sma10 = market.get_sma(symbol, 10) or Decimal("0")
            sma20 = market.get_sma(symbol, 20) or Decimal("0")
            
            current_price = bars[-1].close
            
            # Calculate distances
            vs_sma50 = ((current_price - sma50) / sma50 * 100) if sma50 > 0 else Decimal("0")
            vs_sma200 = ((current_price - sma200) / sma200 * 100) if sma200 > 0 else Decimal("0")
            vs_sma10 = ((current_price - sma10) / sma10 * 100) if sma10 > 0 else Decimal("0")
            vs_sma20 = ((current_price - sma20) / sma20 * 100) if sma20 > 0 else Decimal("0")
            
            # MA stacked
            ma_stacked = sma10 > sma20 > sma50 > sma200 if all([sma10, sma20, sma50, sma200]) else False
            
            # Create Stock entity
            stock = Stock(
                symbol=symbol,
                name=info.name,
                exchange=Exchange(info.exchange) if info.exchange in [e.value for e in Exchange] else Exchange.NASDAQ,
                price=current_price,
                market_cap=info.market_cap,
                float_shares=info.float_shares or 0,
                avg_volume_20d=info.avg_volume_20d,
                dollar_volume=current_price * info.avg_volume_20d,
                adr_percent=adr,
            )
            
            # Create StockMetrics
            metrics = StockMetrics(
                symbol=symbol,
                performance_1m=Decimal("0"),  # Would need historical calculation
                performance_3m=Decimal("0"),
                performance_6m=Decimal("0"),
                rs_percentile=75,  # Placeholder - need IBD-style RS calculation
                rs_line_52w_high=False,
                price_vs_sma10=vs_sma10,
                price_vs_sma20=vs_sma20,
                price_vs_sma50=vs_sma50,
                price_vs_sma200=vs_sma200,
                price_vs_ema10=vs_sma10,  # Simplified
                price_vs_ema20=vs_sma20,
                price_vs_ema21=vs_sma20,
                ma_stacked=ma_stacked,
                atr=market.get_atr(symbol) or Decimal("1"),
                adr_percent=adr,
                avg_volume_20d=info.avg_volume_20d,
                dollar_volume=stock.dollar_volume,
                volume_contraction=False,  # Would need pattern detection
                distance_to_52w_high=Decimal("10"),  # Placeholder
                quality_score=0,
            )
            
            # Evaluate
            result = scanner.evaluate_stock(stock, metrics)
            results.append(result)
            
        except Exception as e:
            if verbose:
                print(f"\n          Error processing {symbol}: {e}")
    
    print(f"\r          Processed {processed} stocks                ")
    
    # Sort by quality score
    results.sort(key=lambda r: r.quality_score, reverse=True)
    
    # Print results
    print()
    print_results(results, show_failed=show_universe)
    
    # Export if requested
    if output_file:
        export_csv(results, output_file)
    
    return results


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Nexus 2 Momentum Scanner - Find KK-style momentum stocks"
    )
    parser.add_argument(
        "--min-price", 
        type=float, 
        default=5.0,
        help="Minimum stock price (default: 5.0)"
    )
    parser.add_argument(
        "--min-volume", 
        type=int, 
        default=300_000,
        help="Minimum average volume (default: 300000)"
    )
    parser.add_argument(
        "--min-adr", 
        type=float, 
        default=4.0,
        help="Minimum ADR%% (default: 4.0)"
    )
    parser.add_argument(
        "--show-universe",
        action="store_true",
        help="Show universe tier stocks"
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        default=None,
        help="Export results to CSV file"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose output"
    )
    
    args = parser.parse_args()
    
    try:
        run_scan(
            min_price=args.min_price,
            min_volume=args.min_volume,
            min_adr=args.min_adr,
            output_file=args.output,
            show_universe=args.show_universe,
            verbose=args.verbose,
        )
    except KeyboardInterrupt:
        print("\n\n  Scan cancelled.\n")
        sys.exit(0)
    except Exception as e:
        print(f"\n  Error: {e}\n")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
