"""
EP Scanner Service

Shared service for EP (Episodic Pivot) scanning.
Used by both CLI and API for consistent results.
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from nexus2.adapters.market_data import UnifiedMarketData
from nexus2.domain.setup_detection.ep_models import (
    EPCandidate,
    EPCandidateStatus,
    EPValidationResult,
    CatalystType,
)
from nexus2.domain.setup_detection.ep_detection import (
    EPDetectionService,
    EPSettings,
)
from nexus2.domain.automation.rejection_tracker import (
    get_rejection_tracker,
    RejectionReason,
)


@dataclass
class EPScanSettings:
    """Settings for EP scan."""
    min_gap: Decimal = Decimal("8.0")
    min_rvol: Decimal = Decimal("2.0")
    min_dollar_vol: Decimal = Decimal("10000000")
    min_change: Decimal = Decimal("3.0")
    min_price: Decimal = Decimal("5.0")
    
    # Range quality filter - reject if price in lower X% of range
    min_range_position: Decimal = Decimal("0.40")


@dataclass
class EPScanResult:
    """Result from EP scan."""
    candidates: List[EPCandidate]
    processed_count: int
    filtered_count: int
    scan_time: datetime


class EPScannerService:
    """
    Unified EP Scanner Service.
    
    Extracts core EP scanning logic for use by both CLI and API.
    """
    
    def __init__(
        self, 
        settings: Optional[EPScanSettings] = None,
        market_data: Optional[UnifiedMarketData] = None,
    ):
        self.settings = settings or EPScanSettings()
        self.market_data = market_data or UnifiedMarketData()
        
        # Initialize EP detection service
        ep_settings = EPSettings(
            min_gap_percent=self.settings.min_gap,
            min_relative_volume=self.settings.min_rvol,
            min_price=self.settings.min_price,
        )
        self.ep_service = EPDetectionService(ep_settings)
    
    def scan(self, verbose: bool = False) -> EPScanResult:
        """
        Run EP scan on top gainers + actives.
        
        Returns:
            EPScanResult with candidates and stats
        """
        # Step 1: Get top gainers + most active
        gainers = self.market_data.get_gainers()
        actives = self.market_data.get_actives()
        
        # Combine and dedupe
        seen = set()
        all_movers = []
        
        for g in gainers:
            sym = g["symbol"]
            if sym not in seen:
                seen.add(sym)
                all_movers.append(g)
        
        for a in actives:
            sym = a["symbol"]
            if sym not in seen:
                seen.add(sym)
                all_movers.append(a)
        
        if not all_movers:
            return EPScanResult(
                candidates=[],
                processed_count=0,
                filtered_count=0,
                scan_time=datetime.now(),
            )
        
        # Pre-filter by minimum change % and price
        filtered_movers = [
            g for g in all_movers 
            if g["change_percent"] >= self.settings.min_change
            and g["price"] >= self.settings.min_price
        ]
        
        # Exclude ETFs
        etf_set = self.market_data.fmp.get_etf_symbols()
        filtered_movers = [g for g in filtered_movers if g["symbol"] not in etf_set]
        
        filtered_count = len(filtered_movers)
        moving_symbols = [g["symbol"] for g in filtered_movers]
        
        if not moving_symbols:
            return EPScanResult(
                candidates=[],
                processed_count=0,
                filtered_count=filtered_count,
                scan_time=datetime.now(),
            )
        
        # Step 2: Evaluate EP criteria
        ep_candidates = []
        processed = 0
        
        for symbol in moving_symbols:
            processed += 1
            
            try:
                candidate = self._evaluate_symbol(symbol, verbose)
                if candidate:
                    ep_candidates.append(candidate)
            except Exception as e:
                if verbose:
                    print(f"Error processing {symbol}: {e}")
        
        # Sort by gap %
        ep_candidates.sort(key=lambda c: c.gap_percent, reverse=True)
        
        return EPScanResult(
            candidates=ep_candidates,
            processed_count=processed,
            filtered_count=filtered_count,
            scan_time=datetime.now(),
        )
    
    def _evaluate_symbol(
        self, 
        symbol: str, 
        verbose: bool = False
    ) -> Optional[EPCandidate]:
        """
        Evaluate a single symbol for EP criteria.
        
        Returns:
            EPCandidate if passes criteria, None otherwise
        """
        # Get EP session snapshot
        snapshot = self.market_data.build_ep_session_snapshot(symbol)
        if not snapshot:
            get_rejection_tracker().record(
                symbol=symbol,
                scanner="ep",
                reason=RejectionReason.SNAPSHOT_FAILED,
                details="Failed to build session snapshot",
            )
            return None
        
        # Calculate EP metrics
        yesterday_close = snapshot["yesterday_close"]
        session_open = snapshot["session_open"]
        avg_volume = snapshot["avg_daily_volume"]
        session_volume = snapshot["session_volume"]
        
        gap_pct = ((session_open - yesterday_close) / yesterday_close) * 100
        rvol = session_volume / avg_volume if avg_volume > 0 else 0
        dollar_vol = snapshot["last_price"] * session_volume
        
        # Check criteria
        tracker = get_rejection_tracker()
        
        if gap_pct < float(self.settings.min_gap):
            tracker.record(
                symbol=symbol, scanner="ep",
                reason=RejectionReason.GAP_TOO_SMALL,
                values={"gap": round(gap_pct, 2), "min": float(self.settings.min_gap)},
            )
            return None
        if rvol < float(self.settings.min_rvol):
            tracker.record(
                symbol=symbol, scanner="ep",
                reason=RejectionReason.RVOL_TOO_LOW,
                values={"rvol": round(rvol, 2), "min": float(self.settings.min_rvol)},
            )
            return None
        if dollar_vol < float(self.settings.min_dollar_vol):
            tracker.record(
                symbol=symbol, scanner="ep",
                reason=RejectionReason.DOLLAR_VOL_LOW,
                values={"dollar_vol": round(dollar_vol), "min": float(self.settings.min_dollar_vol)},
            )
            return None
        
        # Range quality check - reject if price in lower portion of range
        # SKIP this check for big gap days since OR-timing uses OPEN price
        # (OPEN is naturally low in day's range on gap-up days that run)
        is_gap_day = gap_pct >= 5.0  # Same threshold as OR-timing logic
        session_high = snapshot["session_high"]
        session_low = snapshot["session_low"]
        last_price = snapshot["last_price"]
        range_len = session_high - session_low
        
        if range_len > 0 and not is_gap_day:
            range_position = (last_price - session_low) / range_len
            if range_position < float(self.settings.min_range_position):
                tracker.record(
                    symbol=symbol, scanner="ep",
                    reason=RejectionReason.RANGE_POSITION,
                    values={"position": round(range_position * 100, 1), "min": float(self.settings.min_range_position) * 100},
                )
                if verbose:
                    print(f"{symbol}: Rejected - price in lower {range_position*100:.0f}% of range")
                return None
        
        # Get additional data
        atr = self.market_data.get_atr(symbol, period=14) or Decimal("1")
        adr = self.market_data.get_adr_percent(symbol, period=14) or Decimal("5")
        
        # Catalyst verification - reject stocks without real catalysts
        # This prevents garbage picks (random movers with no earnings/news)
        # KK methodology: 5 days lookback for earnings plays (past only, NOT upcoming)
        has_catalyst, catalyst_type_str, catalyst_desc = self.market_data.has_recent_catalyst(symbol, days=5)
        
        if not has_catalyst:
            tracker.record(
                symbol=symbol, scanner="ep",
                reason=RejectionReason.NO_CATALYST,
                details=catalyst_desc,
            )
            if verbose:
                print(f"{symbol}: Rejected - no catalyst found ({catalyst_desc})")
            return None
        
        # Block stocks with UPCOMING earnings in next 3 days (earnings risk)
        # 3 days = balanced: catches immediate risk without over-filtering
        has_upcoming, earnings_date = self.market_data.has_upcoming_earnings(symbol, days=3)
        if has_upcoming:
            tracker.record(
                symbol=symbol, scanner="ep",
                reason=RejectionReason.UPCOMING_EARNINGS,
                details=f"Earnings on {earnings_date}",
            )
            if verbose:
                print(f"{symbol}: Rejected - upcoming earnings on {earnings_date} (avoid earnings risk)")
            return None
        
        # Map catalyst type string to enum
        if catalyst_type_str == "earnings":
            catalyst_type = CatalystType.EARNINGS
        elif catalyst_type_str == "news":
            catalyst_type = CatalystType.NEWS
        else:
            catalyst_type = CatalystType.OTHER
        
        # Create candidate with verified catalyst
        candidate = self.ep_service.create_candidate(
            symbol=symbol,
            catalyst_date=datetime.now().date(),
            catalyst_type=catalyst_type,
            catalyst_description=catalyst_desc,
            prev_close=yesterday_close,
            open_price=session_open,
            pre_market_volume=int(session_volume),
            avg_volume=avg_volume,
            atr=atr,
            adr_percent=adr,
        )
        
        # Set current price and status
        candidate.current_price = snapshot["last_price"]
        candidate.status = EPCandidateStatus.ACTIVE
        candidate.relative_volume = Decimal(str(rvol))
        candidate.gap_percent = Decimal(str(gap_pct))
        
        # Establish opening range for KK-style tactical stop calculation
        # Try to get true 5-minute opening range from intraday data
        opening_range = self.market_data.get_opening_range(
            symbol,
            timeframe_minutes=self.ep_service.settings.opening_range_minutes,
        )
        
        if opening_range:
            # Use real opening range from first 5min bar
            or_high, or_low = opening_range
            if verbose:
                print(f"{symbol}: Using true opening range: high={or_high}, low={or_low}")
            self.ep_service.establish_opening_range(
                candidate,
                high=or_high,
                low=or_low,
                timeframe_minutes=self.ep_service.settings.opening_range_minutes,
            )
        else:
            # Fallback: Use session high/low as proxy (pre-market or API issue)
            if verbose:
                print(f"{symbol}: Intraday data unavailable, using session high/low")
            self.ep_service.establish_opening_range(
                candidate,
                high=Decimal(str(session_high)),
                low=Decimal(str(session_low)),
                timeframe_minutes=60,  # Using daily as approximation
            )
        
        # Also set EP candle low for invalidation level
        # This is separate from tactical stop (the session low, not opening range low)
        candidate.ep_candle_low = Decimal(str(session_low))
        
        # Validate
        validation = self.ep_service.validate_candidate(candidate)
        if validation != EPValidationResult.VALID:
            tracker.record(
                symbol=symbol, scanner="ep",
                reason=RejectionReason.VALIDATION_FAILED,
                details=validation.value,
            )
            if verbose:
                print(f"{symbol}: Rejected - {validation.value}")
            return None
        
        return candidate


# Singleton instance
_scanner_service: Optional[EPScannerService] = None


def get_ep_scanner_service() -> EPScannerService:
    """Get singleton EP scanner service."""
    global _scanner_service
    if _scanner_service is None:
        _scanner_service = EPScannerService()
    return _scanner_service
