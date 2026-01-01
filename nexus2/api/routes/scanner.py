"""
Scanner Routes

Scanner API with FMP market data integration.
Now unified through UnifiedScannerService (same as automation).
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

# Unified Scanner (single source of truth for all scanning)
from nexus2.domain.automation.unified_scanner import (
    UnifiedScannerService,
    UnifiedScanSettings,
    ScanMode,
)
from nexus2.domain.automation.signals import Signal

# FMP adapter for rate stats and direct HTF/Breakout endpoints
from nexus2.adapters.market_data.fmp_adapter import get_fmp_adapter

# Individual scanners for dedicated endpoints
from nexus2.domain.scanner.breakout_scanner_service import (
    BreakoutStatus,
    get_breakout_scanner_service,
)
from nexus2.domain.scanner.htf_scanner_service import (
    HTFStatus,
    get_htf_scanner_service,
)


router = APIRouter(prefix="/scanner", tags=["scanner"])

# In-memory cache for scanner results
_last_results: Optional[ScannerResultsResponse] = None


def _signal_to_scan_result(signal: Signal) -> ScanResultResponse:
    """Convert a Signal to ScanResultResponse for the Scanner Page."""
    return ScanResultResponse(
        symbol=signal.symbol,
        name=signal.symbol,  # Signal doesn't have name, use symbol
        price=str(signal.entry_price),
        quality_score=signal.quality_score,
        passes_filter=True,  # If it's in signals, it passed
        failed_criteria=[],
        tier=signal.tier,
        rs_percentile=signal.rs_percentile,
        adr_percent=str(signal.adr_percent),
        price_vs_ma50="0",  # Signal doesn't track this directly
        # EP fields
        gap_percent=None,  # Would need to be added to Signal if needed
        relative_volume=None,  # Would need to be added to Signal if needed
        catalyst_type=None,  # Signal doesn't expose this yet
        catalyst_description=None,
    )


@router.post("/run", response_model=ScannerResultsResponse)
async def run_scanner(request: ScannerRunRequest):
    """
    Run the scanner with real FMP market data.
    
    Now uses UnifiedScannerService (same as automation) for consistent results.
    
    Mode mapping:
    - "gainers" -> EP scanner only (looking for EPs in top gainers)
    - "actives" -> EP + Breakout scanners
    - "trend_leaders" -> All scanners (EP, Breakout, HTF)
    """
    global _last_results
    
    # Map request mode to ScanMode
    mode_mapping = {
        "gainers": [ScanMode.EP_ONLY],
        "actives": [ScanMode.EP_ONLY, ScanMode.BREAKOUT_ONLY],
        "trend_leaders": [ScanMode.ALL],
    }
    
    scan_modes = mode_mapping.get(request.mode, [ScanMode.EP_ONLY])
    
    # Demo mode - return mock results without API calls
    if request.demo:
        print("[Scanner] Demo mode enabled")
        mock_results = [
            ScanResultResponse(
                symbol="NVDA", name="NVIDIA Corporation", price="450.00",
                quality_score=9, passes_filter=True, failed_criteria=[],
                tier="FOCUS", rs_percentile=95, adr_percent="4.5",
                price_vs_ma50="12.3", catalyst_type="earnings",
                catalyst_description="Beat Q4 estimates",
            ),
            ScanResultResponse(
                symbol="META", name="Meta Platforms", price="520.00",
                quality_score=8, passes_filter=True, failed_criteria=[],
                tier="FOCUS", rs_percentile=88, adr_percent="3.8",
                price_vs_ma50="8.1", catalyst_type="news",
                catalyst_description="AI investment announcement",
            ),
            ScanResultResponse(
                symbol="AAPL", name="Apple Inc.", price="195.00",
                quality_score=7, passes_filter=True, failed_criteria=[],
                tier="WIDE", rs_percentile=75, adr_percent="2.2",
                price_vs_ma50="3.5",
            ),
        ]
        _last_results = ScannerResultsResponse(
            results=mock_results[:request.limit],
            total=len(mock_results[:request.limit]),
            scanned_at=datetime.now(),
        )
        return _last_results
    
    # Create unified scanner with settings
    settings = UnifiedScanSettings(
        modes=scan_modes,
        min_quality_score=7,  # Match automation default
        stop_mode="atr",
        max_stop_atr=1.0,
    )
    
    scanner = UnifiedScannerService(settings=settings)
    
    try:
        # Run the unified scan
        result = scanner.scan(verbose=False)
        
        print(f"[Scanner] UnifiedScannerService returned {result.total_signals} signals")
        print(f"  EP: {result.ep_count}, Breakout: {result.breakout_count}, HTF: {result.htf_count}")
        
        # Convert signals to scanner results
        scan_results = []
        for signal in result.signals[:request.limit]:
            scan_results.append(_signal_to_scan_result(signal))
        
        _last_results = ScannerResultsResponse(
            results=scan_results,
            total=len(scan_results),
            scanned_at=datetime.now(),
        )
        
        # Persist to watchlist (optional - keep existing behavior)
        try:
            from uuid import uuid4
            from nexus2.db import SessionLocal, WatchlistRepository
            
            db = SessionLocal()
            try:
                repo = WatchlistRepository(db)
                persisted_count = 0
                
                for r in scan_results:
                    if r.passes_filter:
                        candidate_data = {
                            "id": str(uuid4()),
                            "symbol": r.symbol,
                            "name": r.name,
                            "source": request.mode,
                            "tier": r.tier.upper(),
                            "price": r.price,
                            "change_pct": r.gap_percent,
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
        
    except Exception as e:
        print(f"[Scanner] Error running unified scan: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


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
