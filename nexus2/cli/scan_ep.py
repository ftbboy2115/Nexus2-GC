"""
EP Scanner CLI

Scan for Episodic Pivot candidates.

Usage:
    python -m nexus2.cli.scan_ep [--min-gap 8] [--min-rvol 2] [--output results.csv]
"""

import argparse
import csv
import sys
from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from nexus2.adapters.market_data import UnifiedMarketData
from nexus2.domain.setup_detection.ep_models import (
    EPCandidate,
    EPCandidateStatus,
    CatalystType,
)
from nexus2.domain.setup_detection.ep_detection import (
    EPDetectionService,
    EPSettings,
)
from nexus2.utils.time_utils import now_et


def print_header():
    """Print CLI header."""
    print("\n" + "=" * 70)
    print("  NEXUS 2 - Episodic Pivot Scanner")
    print("  KK-Style Momentum Trading")
    print("=" * 70)
    print(f"  {now_et().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70 + "\n")


def print_candidate(candidate: EPCandidate, idx: int):
    """Print a single EP candidate."""
    gap_str = f"+{candidate.gap_percent:.1f}%" if candidate.gap_percent > 0 else f"{candidate.gap_percent:.1f}%"
    rvol_str = f"{candidate.relative_volume:.1f}x"
    
    print(f"  {idx}. {candidate.symbol:6s} | Gap: {gap_str:8s} | RVOL: {rvol_str:6s} | "
          f"Catalyst: {candidate.catalyst_type.value}")


def print_results(candidates: List[EPCandidate]):
    """Print scan results."""
    if not candidates:
        print("  No EP candidates found matching criteria.\n")
        return
    
    print(f"  Found {len(candidates)} EP candidate(s):\n")
    print("-" * 70)
    
    for idx, candidate in enumerate(candidates, 1):
        print_candidate(candidate, idx)
    
    print("-" * 70 + "\n")


def export_csv(candidates: List[EPCandidate], filename: str):
    """Export results to CSV."""
    with open(filename, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "Symbol", "Gap%", "RVOL", "Catalyst", 
            "Open", "High", "Low", "Last", "Volume",
            "ATR", "ADR%", "Status"
        ])
        
        for c in candidates:
            writer.writerow([
                c.symbol,
                f"{c.gap_percent:.2f}",
                f"{c.relative_volume:.2f}",
                c.catalyst_type.value,
                f"{c.open_price:.2f}",
                c.opening_range.high if c.opening_range else "",
                c.opening_range.low if c.opening_range else "",
                c.current_price or "",
                c.pre_market_volume,
                f"{c.atr:.2f}",
                f"{c.adr_percent:.2f}",
                c.status.value,
            ])
    
    print(f"  Results exported to: {filename}\n")


def run_scan(
    min_gap: float = 8.0,
    min_rvol: float = 2.0,
    min_dollar_vol: float = 10_000_000,
    min_change: float = 3.0,
    output_file: Optional[str] = None,
    verbose: bool = False,
):
    """
    Run the EP scanner.
    
    Args:
        min_gap: Minimum gap percentage
        min_rvol: Minimum relative volume
        min_dollar_vol: Minimum dollar volume
        min_change: Minimum change % for initial filter
        output_file: Optional CSV output file
        verbose: Print verbose output
    """
    from nexus2.domain.scanner.ep_scanner_service import (
        EPScannerService,
        EPScanSettings,
    )
    
    print_header()
    
    # Initialize with settings
    settings = EPScanSettings(
        min_gap=Decimal(str(min_gap)),
        min_rvol=Decimal(str(min_rvol)),
        min_dollar_vol=Decimal(str(min_dollar_vol)),
        min_change=Decimal(str(min_change)),
    )
    
    print("  Initializing EP scanner service...")
    ep_scanner = EPScannerService(settings=settings)
    
    # Run scan
    print(f"  Running EP scan (gap {min_gap}%+, RVOL {min_rvol}x+)...")
    result = ep_scanner.scan(verbose=verbose)
    
    print(f"  Processed {result.processed_count} stocks from {result.filtered_count} filtered movers")
    
    # Print results
    print()
    print_results(result.candidates)
    
    # Export if requested
    if output_file and result.candidates:
        export_csv(result.candidates, output_file)
    
    return result.candidates


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Nexus 2 EP Scanner - Find Episodic Pivot candidates"
    )
    parser.add_argument(
        "--min-gap", 
        type=float, 
        default=8.0,
        help="Minimum gap percentage (default: 8.0)"
    )
    parser.add_argument(
        "--min-rvol", 
        type=float, 
        default=2.0,
        help="Minimum relative volume (default: 2.0)"
    )
    parser.add_argument(
        "--min-dollar-vol", 
        type=float, 
        default=10_000_000,
        help="Minimum dollar volume (default: 10M)"
    )
    parser.add_argument(
        "--min-change", 
        type=float, 
        default=3.0,
        help="Minimum change %% for initial filter (default: 3.0)"
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
            min_gap=args.min_gap,
            min_rvol=args.min_rvol,
            min_dollar_vol=args.min_dollar_vol,
            min_change=args.min_change,
            output_file=args.output,
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
