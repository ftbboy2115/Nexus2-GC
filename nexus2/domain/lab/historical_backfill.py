"""
Historical Gapper Backfill - Populates scan_history with historical gapper data.

Uses FMP API to find stocks that gapped significantly on each historical date,
allowing the R&D Lab to backtest on a richer universe of symbols.
"""

import logging
from datetime import date, timedelta
from typing import List, Dict, Any, Optional
import time

logger = logging.getLogger(__name__)


async def backfill_historical_gappers(
    start_date: date,
    end_date: date,
    min_gap_percent: float = 5.0,
    min_price: float = 1.0,
    max_price: float = 20.0,
    max_symbols_per_day: int = 20,
    delay_between_days: float = 0.5,
) -> Dict[str, Any]:
    """
    Backfill scan_history with historical gappers from FMP.
    
    Uses FMP's batch quote endpoint to find stocks that gapped significantly.
    Entries are marked with source="backfill" to distinguish from real scans.
    
    Args:
        start_date: First date to backfill
        end_date: Last date to backfill
        min_gap_percent: Minimum gap percentage (default 5%)
        min_price: Minimum stock price filter
        max_price: Maximum stock price filter
        max_symbols_per_day: Max symbols to log per day
        delay_between_days: Seconds between API calls (rate limiting)
        
    Returns:
        Dict with backfill statistics
    """
    from nexus2.domain.lab.scan_history_logger import get_scan_history_logger
    from nexus2.adapters.market_data.fmp_adapter import FMPAdapter
    
    history = get_scan_history_logger()
    fmp = FMPAdapter()
    
    stats = {
        "dates_processed": 0,
        "dates_skipped": 0,
        "symbols_added": 0,
        "errors": [],
    }
    
    current_date = start_date
    while current_date <= end_date:
        # Skip weekends
        if current_date.weekday() >= 5:
            current_date += timedelta(days=1)
            continue
            
        # Skip if already have data for this date
        existing = history.get_symbols_for_date(current_date)
        if existing:
            logger.debug(f"[Backfill] Skipping {current_date} - already has {len(existing)} symbols")
            stats["dates_skipped"] += 1
            current_date += timedelta(days=1)
            continue
        
        try:
            # Get historical gainers for this date
            # FMP doesn't have historical gainers, so we use their stock screener
            # with change criteria, filtering by date
            gainers = await _get_historical_gainers(
                fmp, 
                current_date, 
                min_gap_percent,
                min_price,
                max_price,
            )
            
            # Log the top gainers
            count = 0
            for gainer in gainers[:max_symbols_per_day]:
                try:
                    history.log_passed_symbol(
                        symbol=gainer["symbol"],
                        scan_date=current_date,
                        gap_percent=gainer["gap_percent"],
                        rvol=1.0,  # Unknown for historical
                        score=5,   # Default score
                        catalyst=None,
                        source="backfill",
                    )
                    count += 1
                    stats["symbols_added"] += 1
                except Exception as e:
                    logger.warning(f"[Backfill] Failed to log {gainer['symbol']}: {e}")
            
            logger.info(f"[Backfill] {current_date}: Added {count} gappers")
            stats["dates_processed"] += 1
            
        except Exception as e:
            logger.warning(f"[Backfill] Error on {current_date}: {e}")
            stats["errors"].append({"date": str(current_date), "error": str(e)})
        
        # Rate limiting
        time.sleep(delay_between_days)
        current_date += timedelta(days=1)
    
    return stats


async def _get_historical_gainers(
    fmp: 'FMPAdapter',
    target_date: date,
    min_gap_percent: float,
    min_price: float,
    max_price: float,
) -> List[Dict[str, Any]]:
    """
    Find stocks that gapped up significantly on a historical date.
    
    Strategy: Use FMP's historical price endpoint to compare
    previous close to open and find large gaps.
    """
    # Get stocks that were major gainers on this date
    # FMP's batch_historical_prices can give us daily bars
    # We look for stocks where open > previous close by gap%
    
    # For now, use a simpler approach: fetch daily bars for known gapper symbols
    # and check if they gapped on this date
    
    # Fallback: Use stock screener with price range
    try:
        # FMP has a "stock-screener" endpoint with filters
        # But it's for current data only. For historical, we need to query
        # a list of potential gappers and check their historical data.
        
        # Simple approach: Query the batch historical for some common gapper tickers
        # This is a bootstrap - once you have some scan history, it builds on itself
        
        gainers = []
        
        # Use the most recent gainers as seed candidates
        # (This works better after you've collected some real scan data)
        seed_symbols = await _get_seed_symbols(fmp)
        
        if not seed_symbols:
            # Fallback to a static list of commonly gapping stocks
            seed_symbols = [
                "AAPL", "TSLA", "NVDA", "AMD", "META", "AMZN", "MSFT", "GOOG",
                "NFLX", "COIN", "PLTR", "SOFI", "HOOD", "MARA", "RIOT", "LCID",
            ]
        
        # Check each seed symbol for a gap on target_date
        for symbol in seed_symbols[:50]:  # Limit to avoid too many API calls
            try:
                # Get daily bar for target_date and previous day
                bars = fmp.get_daily_bars(
                    symbol=symbol,
                    from_date=str(target_date - timedelta(days=5)),
                    to_date=str(target_date),
                )
                
                if len(bars) < 2:
                    continue
                    
                # Find the bar for target_date
                target_bar = None
                prev_bar = None
                for i, bar in enumerate(bars):
                    if bar.get("date") and str(bar["date"])[:10] == str(target_date):
                        target_bar = bar
                        if i + 1 < len(bars):
                            prev_bar = bars[i + 1]  # Previous trading day
                        break
                
                if not target_bar or not prev_bar:
                    continue
                
                # Calculate gap
                prev_close = float(prev_bar.get("close", 0))
                current_open = float(target_bar.get("open", 0))
                
                if prev_close <= 0:
                    continue
                    
                gap_percent = ((current_open - prev_close) / prev_close) * 100
                
                # Check criteria
                if (gap_percent >= min_gap_percent and 
                    min_price <= current_open <= max_price):
                    gainers.append({
                        "symbol": symbol,
                        "gap_percent": round(gap_percent, 2),
                        "open": current_open,
                        "prev_close": prev_close,
                    })
                    
            except Exception as e:
                # Skip symbols that fail
                continue
        
        # Sort by gap percent descending
        gainers.sort(key=lambda x: x["gap_percent"], reverse=True)
        return gainers
        
    except Exception as e:
        logger.warning(f"[Backfill] Failed to get historical gainers for {target_date}: {e}")
        return []


async def _get_seed_symbols(fmp: 'FMPAdapter') -> List[str]:
    """Get a list of symbols to check for historical gaps."""
    try:
        # Try to get current gainers as seed
        gainers = fmp.get_gainers()
        if gainers:
            return [g["symbol"] for g in gainers[:30]]
    except:
        pass
    
    # Try to get from existing scan history
    try:
        from nexus2.domain.lab.scan_history_logger import get_scan_history_logger
        history = get_scan_history_logger()
        return history.get_all_symbols()[:30]
    except:
        pass
    
    return []
