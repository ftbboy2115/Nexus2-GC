"""
Scanner Routes

Scanner API with FMP market data integration.
"""

from datetime import datetime
from typing import List, Optional
from decimal import Decimal
from fastapi import APIRouter, HTTPException

from nexus2.api.schemas import (
    ScannerRunRequest,
    ScanResultResponse,
    ScannerResultsResponse,
)
from nexus2.domain.scanner.models import (
    Stock,
    StockMetrics,
    Exchange,
)
from nexus2.domain.scanner.scanner_engine import ScannerEngine
from nexus2.settings.scanner_settings import (
    ScannerSettings,
    DisqualifierSettings,
    QualityScoringSettings,
)
from nexus2.adapters.market_data.fmp_adapter import FMPAdapter, get_fmp_adapter

# EP Scanner for unified EP detection
from nexus2.domain.scanner.ep_scanner_service import (
    EPScannerService,
    EPScanSettings,
    get_ep_scanner_service,
)

# Breakout Scanner for flag/consolidation breakouts
from nexus2.domain.scanner.breakout_scanner_service import (
    BreakoutScannerService,
    BreakoutScanSettings,
    BreakoutStatus,
    get_breakout_scanner_service,
)

# HTF Scanner for High-Tight Flag patterns
from nexus2.domain.scanner.htf_scanner_service import (
    HTFScannerService,
    HTFScanSettings,
    HTFStatus,
    get_htf_scanner_service,
)


router = APIRouter(prefix="/scanner", tags=["scanner"])

# In-memory cache for scanner results
_last_results: Optional[ScannerResultsResponse] = None


def convert_to_exchange(exchange_str: str) -> Exchange:

    """Convert exchange string to Exchange enum."""
    mapping = {
        "NASDAQ": Exchange.NASDAQ,
        "NYSE": Exchange.NYSE,
        "AMEX": Exchange.AMEX,
        "OTC": Exchange.OTC,
    }
    return mapping.get(exchange_str.upper(), Exchange.NYSE)


def fetch_stock_with_metrics(symbol: str, fmp: FMPAdapter) -> tuple[Stock, StockMetrics, Decimal]:
    """Fetch stock info and calculate metrics from FMP. Returns (stock, metrics, rvol)."""
    # Get stock info
    info = fmp.get_stock_info(symbol)
    if not info:
        raise ValueError(f"Could not get info for {symbol}")
    
    # Get quote for current price
    quote = fmp.get_quote(symbol)
    if not quote:
        raise ValueError(f"Could not get quote for {symbol}")
    
    # Get daily bars for calculations
    bars = fmp.get_daily_bars(symbol, limit=250)
    if not bars or len(bars) < 50:
        raise ValueError(f"Not enough bar data for {symbol}")
    
    # Calculate SMAs - ensure Decimal types
    closes = [Decimal(str(b.close)) for b in bars]
    sma10 = sum(closes[-10:]) / 10 if len(closes) >= 10 else closes[-1]
    sma20 = sum(closes[-20:]) / 20 if len(closes) >= 20 else closes[-1]
    sma50 = sum(closes[-50:]) / 50 if len(closes) >= 50 else closes[-1]
    sma200 = sum(closes[-200:]) / 200 if len(closes) >= 200 else sma50
    
    # Calculate EMAs
    def calc_ema(prices: List[Decimal], period: int) -> Decimal:
        if len(prices) < period:
            return prices[-1]
        multiplier = Decimal(2) / (Decimal(period) + 1)
        ema = prices[0]
        for price in prices[1:]:
            ema = (price * multiplier) + (ema * (1 - multiplier))
        return ema
    
    ema10 = calc_ema(closes, 10)
    ema20 = calc_ema(closes, 20)
    ema21 = calc_ema(closes, 21)
    
    # Calculate ATR
    atr = fmp.get_atr(symbol, 14) or Decimal("5.0")
    
    # Calculate price vs MAs (percentage)
    current_price = Decimal(str(quote.price))  # Ensure Decimal for calculations
    price_vs_sma10 = ((current_price - sma10) / sma10) * 100 if sma10 > 0 else Decimal("0")
    price_vs_sma20 = ((current_price - sma20) / sma20) * 100 if sma20 > 0 else Decimal("0")
    price_vs_sma50 = ((current_price - sma50) / sma50) * 100 if sma50 > 0 else Decimal("0")
    price_vs_sma200 = ((current_price - sma200) / sma200) * 100 if sma200 > 0 else Decimal("0")
    price_vs_ema10 = ((current_price - ema10) / ema10) * 100 if ema10 > 0 else Decimal("0")
    price_vs_ema20 = ((current_price - ema20) / ema20) * 100 if ema20 > 0 else Decimal("0")
    price_vs_ema21 = ((current_price - ema21) / ema21) * 100 if ema21 > 0 else Decimal("0")
    
    # Check if MAs are stacked
    ma_stacked = sma10 > sma20 > sma50 > sma200
    
    # Calculate ADR (average daily range) - ensure Decimal types
    ranges = [(Decimal(str(b.high)) - Decimal(str(b.low))) for b in bars[-20:]]
    adr = sum(ranges) / len(ranges) if ranges else Decimal("0")
    adr_percent = (adr / current_price) * 100 if current_price > 0 else Decimal("0")
    
    # Calculate performance
    if len(closes) >= 21:
        perf_1m = ((current_price - closes[-21]) / closes[-21]) * 100
    else:
        perf_1m = Decimal("0")
    
    if len(closes) >= 63:
        perf_3m = ((current_price - closes[-63]) / closes[-63]) * 100
    else:
        perf_3m = perf_1m
    
    if len(closes) >= 126:
        perf_6m = ((current_price - closes[-126]) / closes[-126]) * 100
    else:
        perf_6m = perf_3m
    
    # Calculate RS percentile (simplified - based on 3m performance)
    # In production, this would compare against all stocks
    rs_percentile = min(99, max(1, int(50 + float(perf_3m))))
    
    # Distance to 52-week high
    high_52w = max(Decimal(str(b.high)) for b in bars[-252:]) if len(bars) >= 252 else max(Decimal(str(b.high)) for b in bars)
    distance_to_high = ((high_52w - current_price) / high_52w) * 100 if high_52w > 0 else Decimal("0")
    
    # Volume contraction (compare recent 5-day avg to 20-day avg)
    volumes = [Decimal(str(b.volume)) for b in bars]
    avg_vol_5 = sum(volumes[-5:]) / 5 if len(volumes) >= 5 else volumes[-1]
    avg_vol_20 = sum(volumes[-20:]) / 20 if len(volumes) >= 20 else avg_vol_5
    volume_contraction = avg_vol_5 < avg_vol_20 * Decimal("0.7")
    
    # Calculate RVOL (current session volume vs avg daily)
    current_volume = Decimal(str(quote.volume)) if quote.volume else Decimal("0")
    avg_vol = Decimal(str(info.avg_volume_20d)) if info.avg_volume_20d else Decimal("1")
    rvol = current_volume / avg_vol if avg_vol > 0 else Decimal("0")
    
    # Create Stock entity
    stock = Stock(
        symbol=symbol,
        name=info.name,
        exchange=convert_to_exchange(info.exchange),
        price=current_price,
        market_cap=info.market_cap,
        float_shares=info.float_shares or 0,
        avg_volume_20d=info.avg_volume_20d,
        dollar_volume=current_price * Decimal(info.avg_volume_20d),
        adr_percent=adr_percent,
    )
    
    # Create StockMetrics
    metrics = StockMetrics(
        symbol=symbol,
        performance_1m=perf_1m,
        performance_3m=perf_3m,
        performance_6m=perf_6m,
        rs_percentile=rs_percentile,
        rs_line_52w_high=distance_to_high < Decimal("5"),
        price_vs_sma10=price_vs_sma10,
        price_vs_sma20=price_vs_sma20,
        price_vs_sma50=price_vs_sma50,
        price_vs_sma200=price_vs_sma200,
        price_vs_ema10=price_vs_ema10,
        price_vs_ema20=price_vs_ema20,
        price_vs_ema21=price_vs_ema21,
        ma_stacked=ma_stacked,
        atr=atr,
        adr_percent=adr_percent,
        avg_volume_20d=info.avg_volume_20d,
        dollar_volume=current_price * Decimal(info.avg_volume_20d),
        volume_contraction=volume_contraction,
        distance_to_52w_high=distance_to_high,
        quality_score=0,  # Will be calculated by engine
    )
    
    return stock, metrics, rvol


@router.post("/run", response_model=ScannerResultsResponse)
async def run_scanner(request: ScannerRunRequest):
    """
    Run the scanner with real FMP market data.
    
    Uses top gainers as the stock universe.
    """
    global _last_results
    
    fmp = get_fmp_adapter()
    
    # Initialize scanner engine
    engine = ScannerEngine(
        settings=ScannerSettings(),
        disqualifiers=DisqualifierSettings(),
        scoring=QualityScoringSettings(),
    )
    
    # Demo mode - use mock data
    if request.demo:
        print("[Scanner] Demo mode enabled")
        stocks_data = [
            {"symbol": "NVDA", "name": "NVIDIA Corporation"},
            {"symbol": "AAPL", "name": "Apple Inc."},
            {"symbol": "META", "name": "Meta Platforms"},
            {"symbol": "TSLA", "name": "Tesla Inc."},
            {"symbol": "AMZN", "name": "Amazon.com Inc."},
            {"symbol": "MSFT", "name": "Microsoft Corporation"},
            {"symbol": "GOOGL", "name": "Alphabet Inc."},
            {"symbol": "AMD", "name": "Advanced Micro Devices"},
            {"symbol": "NFLX", "name": "Netflix Inc."},
            {"symbol": "CRM", "name": "Salesforce Inc."},
        ]
    # Get stocks based on mode
    elif request.mode == "gainers":
        # EP Candidates - stocks gapping on potential catalyst
        stocks_data = fmp.get_gainers()
    elif request.mode == "actives":
        # Volume Movers - institutional interest signals
        stocks_data = fmp.get_actives()
    elif request.mode == "trend_leaders":
        # Trend Leaders - KK-style filters:
        # - Higher market cap (institutional quality)
        # - Minimum price $10+ (avoid low float junk)
        # - Higher volume (liquid enough for trading)
        candidates = fmp.screen_stocks(
            min_market_cap=500_000_000,  # $500M+ (quality names)
            min_price=10.0,              # $10+ (no penny stocks)
            min_volume=500_000,          # 500K+ avg volume
            limit=request.limit * 3,     # Get extra to filter by metrics
        )
        # Convert to same format as gainers/actives
        stocks_data = [{"symbol": c["symbol"], "name": c.get("sector", "")} for c in candidates]
    else:
        # Default to gainers
        stocks_data = fmp.get_gainers()
    
    if not stocks_data:
        # Fallback to actives
        stocks_data = fmp.get_actives()
    
    if not stocks_data:
        # Fallback to demo stocks (pre-market/weekend)
        print("[Scanner] FMP returned no data, using demo stocks")
        stocks_data = [
            {"symbol": "NVDA", "name": "NVIDIA Corporation"},
            {"symbol": "AAPL", "name": "Apple Inc."},
            {"symbol": "META", "name": "Meta Platforms"},
            {"symbol": "TSLA", "name": "Tesla Inc."},
            {"symbol": "AMZN", "name": "Amazon.com Inc."},
            {"symbol": "MSFT", "name": "Microsoft Corporation"},
            {"symbol": "GOOGL", "name": "Alphabet Inc."},
            {"symbol": "AMD", "name": "Advanced Micro Devices"},
            {"symbol": "NFLX", "name": "Netflix Inc."},
            {"symbol": "CRM", "name": "Salesforce Inc."},
        ]
    
    # Limit to requested number
    symbols_to_scan = [s["symbol"] for s in stocks_data[:request.limit]]
    
    # Index gainers data by symbol for quick lookup of change_percent
    gainers_by_symbol = {s["symbol"]: s for s in stocks_data}
    
    results = []
    
    # For gainers mode, also run EP scanner to get catalyst info
    ep_candidates = {}
    if request.mode == "gainers" and not request.demo:
        try:
            ep_service = get_ep_scanner_service()
            ep_result = ep_service.scan(verbose=False)
            # Index by symbol for quick lookup
            ep_candidates = {c.symbol: c for c in ep_result.candidates}
            print(f"[Scanner] EP scanner found {len(ep_candidates)} candidates")
        except Exception as e:
            print(f"[Scanner] EP scan failed: {e}")
    
    # Demo mode - generate mock results without API calls
    if request.demo:
        import random
        for i, stock_info in enumerate(stocks_data[:request.limit]):
            random.seed(hash(stock_info["symbol"]))
            price = round(random.uniform(50, 500), 2)
            quality = random.randint(5, 9)
            rs = random.randint(60, 95)
            adr = round(random.uniform(2, 6), 1)
            vs_ma50 = round(random.uniform(-5, 15), 1)
            
            results.append(ScanResultResponse(
                symbol=stock_info["symbol"],
                name=stock_info["name"],
                price=str(price),
                quality_score=quality,
                passes_filter=quality >= 6,
                failed_criteria=[] if quality >= 6 else ["Demo: below quality threshold"],
                tier="focus" if quality >= 8 else "wide" if quality >= 6 else "universe",
                rs_percentile=rs,
                adr_percent=str(adr),
                price_vs_ma50=str(vs_ma50),
            ))
    else:
        # Real mode - fetch from FMP
        for symbol in symbols_to_scan:
            try:
                stock, metrics, rvol = fetch_stock_with_metrics(symbol, fmp)
                result = engine.evaluate_stock(stock, metrics)
                
                # Get gap% from EP candidates or fallback to gainers change_percent
                gainer_data = gainers_by_symbol.get(symbol, {})
                gap_pct = None
                if symbol in ep_candidates:
                    gap_pct = str(ep_candidates[symbol].gap_percent)
                elif "change_percent" in gainer_data or "changesPercentage" in gainer_data:
                    raw_gap = gainer_data.get("change_percent") or gainer_data.get("changesPercentage")
                    if raw_gap is not None:
                        gap_pct = str(raw_gap)
                
                # Get RVOL from EP candidates or calculated value
                rvol_str = None
                if symbol in ep_candidates:
                    rvol_str = str(ep_candidates[symbol].relative_volume)
                elif rvol > 0:
                    rvol_str = f"{rvol:.2f}"
                
                results.append(ScanResultResponse(
                    symbol=result.stock.symbol,
                    name=result.stock.name,
                    price=str(result.stock.price),
                    quality_score=result.quality_score,
                    passes_filter=result.passes_filter,
                    failed_criteria=result.failed_criteria,
                    tier=result.tier_recommendation.value,
                    rs_percentile=result.metrics.rs_percentile,
                    adr_percent=str(result.metrics.adr_percent),
                    price_vs_ma50=str(result.metrics.price_vs_sma50),
                    # Gap% from EP candidates or gainers data
                    gap_percent=gap_pct,
                    relative_volume=rvol_str,
                    catalyst_type=ep_candidates[symbol].catalyst_type.value if symbol in ep_candidates else None,
                    catalyst_description=ep_candidates[symbol].catalyst_description if symbol in ep_candidates else None,
                ))
            except Exception as e:
                print(f"[Scanner] Error scanning {symbol}: {e}")
                continue
    
    # Sort by quality score
    results.sort(key=lambda r: r.quality_score, reverse=True)
    
    _last_results = ScannerResultsResponse(
        results=results,
        total=len(results),
        scanned_at=datetime.now(),
    )
    
    # Persist results to watchlist database
    try:
        from uuid import uuid4
        from nexus2.db import SessionLocal, WatchlistRepository
        
        db = SessionLocal()
        try:
            repo = WatchlistRepository(db)
            persisted_count = 0
            
            for r in results:
                if r.passes_filter:  # Only persist passing candidates
                    candidate_data = {
                        "id": str(uuid4()),
                        "symbol": r.symbol,
                        "name": r.name,
                        "source": request.mode,  # gainers, actives, screener
                        "tier": r.tier.upper(),
                        "price": r.price,
                        "change_pct": r.change_pct,
                        "quality_score": r.quality_score,
                        "rs_percentile": r.rs_percentile,
                        "adr_percent": r.adr_percent,
                        "status": "new",
                        "scanned_at": datetime.utcnow(),
                    }
                    repo.upsert(candidate_data)
                    persisted_count += 1
            
            print(f"[Scanner] Persisted {persisted_count} candidates to watchlist")
        finally:
            db.close()
    except Exception as e:
        print(f"[Scanner] Warning: Failed to persist to watchlist: {e}")
    
    return _last_results


@router.get("/results", response_model=ScannerResultsResponse)
async def get_scanner_results():
    """Get latest scanner results."""
    if _last_results is None:
        raise HTTPException(
            status_code=404,
            detail="No scanner results available. Run /scanner/run first."
        )
    
    return _last_results


@router.get("/rate-stats")
async def get_rate_stats():
    """Get FMP API rate limit stats."""
    fmp = get_fmp_adapter()
    return fmp.get_rate_stats()


@router.post("/breakouts")
async def scan_breakouts(limit: int = 20):
    """
    Scan for breakout/flag patterns.
    
    Identifies:
    - Consolidating stocks (tight range, volume contraction)
    - Breaking out stocks (above consolidation on volume)
    """
    try:
        scanner = get_breakout_scanner_service()
        result = scanner.scan(verbose=False)
        
        # Format response
        candidates = []
        for c in result.candidates[:limit]:
            candidates.append({
                "symbol": c.symbol,
                "name": c.name,
                "price": str(c.price),
                "status": c.status.value,
                "consolidation_high": str(c.consolidation_high),
                "consolidation_low": str(c.consolidation_low),
                "tightness_score": f"{float(c.tightness_score):.2f}",
                "volume_ratio": f"{float(c.volume_ratio):.2f}",
                "distance_to_breakout": f"{float(c.distance_to_breakout):.1f}%",
                "rs_percentile": c.rs_percentile,
                "ma_stacked": c.ma_stacked,
                "entry_price": str(c.entry_price) if c.entry_price else None,
                "stop_price": str(c.stop_price) if c.stop_price else None,
            })
        
        return {
            "status": "success",
            "total": len(candidates),
            "processed": result.processed_count,
            "scanned_at": result.scan_time.isoformat(),
            "candidates": candidates,
        }
        
    except Exception as e:
        print(f"[Scanner] Breakout scan error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/htf")
async def scan_htf(limit: int = 20):
    """
    Scan for High-Tight Flag (HTF) patterns.
    
    KK-style HTF criteria:
    - +90% move (the "pole")
    - ≤25% pullback (the "flag")
    - Liquid stocks with $5M+ dollar volume
    
    Returns candidates with entry/stop levels.
    """
    try:
        scanner = get_htf_scanner_service()
        result = scanner.scan(verbose=False)
        
        # Format response
        candidates = []
        for c in result.candidates[:limit]:
            candidates.append({
                "symbol": c.symbol,
                "name": c.name,
                "price": str(c.price),
                "status": c.status.value,
                "move_pct": f"+{float(c.move_pct):.0f}%",
                "pullback_pct": f"-{float(c.pullback_pct):.1f}%",
                "highest_high": str(c.highest_high),
                "lowest_low": str(c.lowest_low),
                "dollar_volume": f"${float(c.dollar_volume)/1_000_000:.1f}M",
                "entry_price": str(c.entry_price) if c.entry_price else None,
                "stop_price": str(c.stop_price) if c.stop_price else None,
                "risk_reward": f"{float(c.risk_reward_ratio):.1f}:1" if c.risk_reward_ratio else None,
            })
        
        return {
            "status": "success",
            "total": len(candidates),
            "processed": result.processed_count,
            "scanned_at": result.scan_time.isoformat(),
            "candidates": candidates,
        }
        
    except Exception as e:
        print(f"[Scanner] HTF scan error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/htf/{symbol}")
async def get_htf_trend(symbol: str):
    """
    Get HTF trend status for a single symbol.
    
    Returns whether the stock qualifies as an HTF pattern
    with score and raw details.
    """
    try:
        scanner = get_htf_scanner_service()
        result = scanner.get_htf_trend(symbol.upper())
        
        return {
            "symbol": symbol.upper(),
            "htf_trend": result["htf_trend"],
            "htf_trend_score": result["htf_trend_score"],
            "details": result["htf_raw"],
        }
        
    except Exception as e:
        print(f"[Scanner] HTF trend error for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
