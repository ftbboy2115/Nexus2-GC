"""
Warrior Scanner Service

Implements Ross Cameron (Warrior Trading) low-float momentum scanning.
Based on:
- Ross Cameron's 5 Pillars of Stock Selection
- warrior_trading_strategy_guide.md

Distinct from KK-style scanners (EP, Breakout, HTF).
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import List, Optional, Dict, Any

from nexus2.adapters.market_data import UnifiedMarketData
from nexus2.domain.automation.rejection_tracker import (
    get_rejection_tracker,
    RejectionReason,
)


# =============================================================================
# SCAN LOGGER SETUP
# =============================================================================

def _get_warrior_scan_logger() -> logging.Logger:
    """Get or create the Warrior scan file logger."""
    logger = logging.getLogger("warrior_scan")
    
    if not logger.handlers:
        # Create data directory if needed
        log_dir = Path("data")
        log_dir.mkdir(exist_ok=True)
        
        # Rotating file handler: 1MB max, keep 7 files (1 week of logs)
        handler = RotatingFileHandler(
            log_dir / "warrior_scan.log",
            maxBytes=1_000_000,
            backupCount=7,
            encoding="utf-8",
        )
        handler.setFormatter(
            logging.Formatter("%(asctime)s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
        )
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    
    return logger


scan_logger = _get_warrior_scan_logger()


# =============================================================================
# SETTINGS
# =============================================================================

@dataclass
class WarriorScanSettings:
    """
    Settings for Warrior (Ross Cameron) scanning.
    
    Based on Ross Cameron's 5 Pillars of Stock Selection:
    1. Low Float (< 100M shares, ideal < 20M)
    2. Relative Volume (> 2x, ideal 3-5x)
    3. Catalyst (News/Earnings/Former Runner)
    4. Price ($1.50 - $20 default, configurable)
    5. Gap (> 4% pre-market, ideal 5-10%+)
    """
    # Pillar 1: Float
    max_float: int = 100_000_000  # 100M shares max
    ideal_float: int = 20_000_000  # 20M shares ideal
    
    # Pillar 2: Relative Volume
    min_rvol: Decimal = Decimal("2.0")  # 2x minimum
    ideal_rvol: Decimal = Decimal("3.0")  # 3-5x ideal
    rvol_lookback_days: int = 10  # Days for average volume calculation
    
    # Pillar 3: Catalyst - handled via has_recent_catalyst()
    catalyst_lookback_days: int = 5
    
    # Pillar 4: Price Range
    min_price: Decimal = Decimal("1.50")
    max_price: Decimal = Decimal("20.0")  # Editable in settings
    
    # Pillar 5: Gap %
    min_gap: Decimal = Decimal("4.0")  # 4% minimum
    ideal_gap: Decimal = Decimal("5.0")  # 5-10% ideal
    
    # Additional Filters
    min_dollar_volume: Decimal = Decimal("500000")  # $500K minimum turnover
    exclude_chinese_stocks: bool = True  # Ross avoids HKD, TOP, MEGL, etc.
    require_catalyst: bool = True  # Require news/earnings
    include_former_runners: bool = True  # "Former MOMO" stocks
    
    # Pre-market Filters
    min_premarket_volume: int = 100_000  # 100K shares pre-market
    
    # MACD Settings (12, 26, 9) - for future pattern detection
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9


# Chinese stock prefixes/patterns to exclude (pump & dump risk)
CHINESE_STOCK_PATTERNS = {
    "HKD", "TOP", "MEGL", "ATXG", "JYD", "SECO", "QUIK",
    "EUDA", "MGIH", "VCSA", "WIMI", "AIHS", "QD", "YQ",
}

# Dilution-related keywords that indicate bearish catalyst (ANPA trap)
DILUTION_KEYWORDS = [
    "private placement",
    "stock offering",
    "share offering",
    "secondary offering",
    "shelf registration",
    "dilution",
    "shares issued",
    "direct offering",
    "public offering",
    "at-the-market offering",
    "atm offering",
]


# =============================================================================
# RESULT MODELS
# =============================================================================

@dataclass
class WarriorCandidate:
    """
    A stock that passes Warrior Trading criteria.
    
    Contains the 5 Pillars metrics plus additional context.
    """
    symbol: str
    name: str
    
    # The 5 Pillars
    float_shares: Optional[int]  # Pillar 1
    relative_volume: Decimal  # Pillar 2
    catalyst_type: str  # Pillar 3: "earnings", "news", "former_runner", "none"
    catalyst_description: str
    price: Decimal  # Pillar 4
    gap_percent: Decimal  # Pillar 5
    
    # Quality indicators
    is_ideal_float: bool = False  # < 20M shares
    is_ideal_rvol: bool = False  # > 3x
    is_ideal_gap: bool = False  # > 5%
    
    # Technical context
    session_high: Decimal = Decimal("0")
    session_low: Decimal = Decimal("0")
    vwap: Optional[Decimal] = None  # For pullback entries
    pre_market_high: Optional[Decimal] = None  # PMH for breakout trigger
    
    # Volume
    session_volume: int = 0
    avg_volume: int = 0
    dollar_volume: Decimal = Decimal("0")
    
    # ATR for stop sizing
    atr: Decimal = Decimal("1.0")
    
    # Metadata
    scanned_at: datetime = field(default_factory=datetime.now)
    
    @property
    def quality_score(self) -> int:
        """
        Calculate quality score (0-10) based on ideal criteria.
        
        Higher score = better candidate.
        """
        score = 0
        
        # Float quality (3 points max)
        if self.float_shares:
            if self.float_shares < 10_000_000:
                score += 3  # Excellent: < 10M
            elif self.float_shares < 20_000_000:
                score += 2  # Ideal: < 20M
            elif self.float_shares < 50_000_000:
                score += 1  # Acceptable: < 50M
        
        # RVOL quality (2 points max)
        if self.relative_volume >= Decimal("5"):
            score += 2  # Excellent: 5x+
        elif self.relative_volume >= Decimal("3"):
            score += 1  # Good: 3x+
        
        # Gap quality (2 points max)
        if self.gap_percent >= Decimal("10"):
            score += 2  # Excellent: 10%+
        elif self.gap_percent >= Decimal("5"):
            score += 1  # Good: 5%+
        
        # Catalyst quality (2 points max)
        if self.catalyst_type == "earnings":
            score += 2  # Best: earnings
        elif self.catalyst_type == "news":
            score += 1  # Good: news
        
        # Price quality (1 point max)
        if Decimal("5") <= self.price <= Decimal("15"):
            score += 1  # Sweet spot
        
        return min(score, 10)


@dataclass
class WarriorScanResult:
    """Result from Warrior scan."""
    candidates: List[WarriorCandidate]
    processed_count: int
    filtered_count: int
    scan_time: datetime
    
    # Stats
    avg_rvol: Decimal = Decimal("0")
    avg_gap: Decimal = Decimal("0")


# =============================================================================
# SCANNER SERVICE
# =============================================================================

class WarriorScannerService:
    """
    Warrior Trading (Ross Cameron) Scanner Service.
    
    Implements the 5 Pillars of Stock Selection for low-float momentum trading.
    Designed to run independently of the KK-style scanners.
    """
    
    def __init__(
        self,
        settings: Optional[WarriorScanSettings] = None,
        market_data: Optional[UnifiedMarketData] = None,
    ):
        self.settings = settings or WarriorScanSettings()
        self.market_data = market_data or UnifiedMarketData()
    
    def scan(self, verbose: bool = False) -> WarriorScanResult:
        """
        Run Warrior scan on top gainers + most active.
        
        Applies the 5 Pillars filtering:
        1. Float < 100M (ideal < 20M)
        2. RVOL > 2x (ideal 3-5x)
        3. Catalyst (news/earnings/former runner)
        4. Price $1.50 - $20
        5. Gap > 4%
        
        Returns:
            WarriorScanResult with candidates and stats
        """
        import pytz
        
        # Check if we're in pre-market (before 9:30 AM ET)
        et = pytz.timezone("US/Eastern")
        now_et = datetime.now(et)
        is_premarket = now_et.hour < 9 or (now_et.hour == 9 and now_et.minute < 30)
        
        # Step 1: Get gainers from appropriate endpoint
        # Pre-market uses pre_post_market/gainers for actual gapping stocks
        # Regular hours uses stock_market/gainers for intraday movers
        if is_premarket:
            # Use pre-market gainers endpoint for stocks actually gapping today
            gainers = self.market_data.get_premarket_gainers(min_change_pct=float(self.settings.min_gap))
            scan_logger.info(f"PREMARKET MODE | Using pre_post_market/gainers | Found: {len(gainers)} stocks")
        else:
            gainers = self.market_data.get_gainers()
            scan_logger.info(f"REGULAR MODE | Using stock_market/gainers | Found: {len(gainers)} stocks")
        
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
            return WarriorScanResult(
                candidates=[],
                processed_count=0,
                filtered_count=0,
                scan_time=datetime.now(),
            )
        
        # Pre-filter by price and gap (Pillars 4 & 5)
        filtered_movers = [
            g for g in all_movers
            if g["price"] >= self.settings.min_price
            and g["price"] <= self.settings.max_price
            and g["change_percent"] >= self.settings.min_gap
        ]
        
        # Exclude ETFs
        etf_set = self.market_data.fmp.get_etf_symbols()
        filtered_movers = [g for g in filtered_movers if g["symbol"] not in etf_set]
        
        # Exclude Chinese stocks (Ross's rule)
        if self.settings.exclude_chinese_stocks:
            filtered_movers = [
                g for g in filtered_movers
                if g["symbol"] not in CHINESE_STOCK_PATTERNS
                and not self._is_likely_chinese(g["name"])
            ]
        
        filtered_count = len(filtered_movers)
        
        if not filtered_movers:
            return WarriorScanResult(
                candidates=[],
                processed_count=0,
                filtered_count=filtered_count,
                scan_time=datetime.now(),
            )
        
        # Step 2: Evaluate each symbol against all 5 Pillars
        candidates = []
        rejections = []  # Track rejections for logging
        processed = 0
        total = len(filtered_movers)
        progress_thresholds = {25, 50, 75}
        logged_thresholds = set()
        
        # Log all symbols being evaluated
        all_symbols = [m["symbol"] for m in filtered_movers]
        scan_logger.info(f"SCAN START | Total: {len(all_movers)} | Pre-filtered: {total} | Symbols: {','.join(all_symbols[:50])}")
        
        for mover in filtered_movers:
            processed += 1
            symbol = mover["symbol"]
            
            # Log progress
            if total > 0:
                pct = int((processed / total) * 100)
                for threshold in progress_thresholds:
                    if pct >= threshold and threshold not in logged_thresholds:
                        print(f"🔄 [Warrior Scanner] Processing {processed}/{total} ({threshold}%)...")
                        logged_thresholds.add(threshold)
            
            try:
                candidate = self._evaluate_symbol(
                    symbol=symbol,
                    name=mover.get("name", ""),
                    price=mover["price"],
                    change_percent=mover["change_percent"],
                    verbose=verbose,
                )
                if candidate:
                    candidates.append(candidate)
                    scan_logger.info(f"PASS | {symbol} | Gap:{mover['change_percent']:.1f}% | RVOL:{candidate.relative_volume:.1f}x | Score:{candidate.quality_score}")
            except Exception as e:
                scan_logger.error(f"ERROR | {symbol} | {e}")
                if verbose:
                    print(f"Error processing {symbol}: {e}")
        
        # Sort by quality score (higher = better)
        candidates.sort(key=lambda c: c.quality_score, reverse=True)
        
        # Calculate averages
        avg_rvol = Decimal("0")
        avg_gap = Decimal("0")
        if candidates:
            avg_rvol = sum(c.relative_volume for c in candidates) / len(candidates)
            avg_gap = sum(c.gap_percent for c in candidates) / len(candidates)
        
        # Log scan summary
        passed_symbols = [c.symbol for c in candidates]
        scan_logger.info(f"SCAN END | Processed: {processed} | Passed: {len(candidates)} | Candidates: {','.join(passed_symbols)}")
        
        return WarriorScanResult(
            candidates=candidates,
            processed_count=processed,
            filtered_count=filtered_count,
            scan_time=datetime.now(),
            avg_rvol=avg_rvol,
            avg_gap=avg_gap,
        )
    
    def _evaluate_symbol(
        self,
        symbol: str,
        name: str,
        price: Decimal,
        change_percent: Decimal,
        verbose: bool = False,
    ) -> Optional[WarriorCandidate]:
        """
        Evaluate a single symbol against Warrior criteria (5 Pillars).
        
        Returns:
            WarriorCandidate if passes all criteria, None otherwise
        """
        tracker = get_rejection_tracker()
        s = self.settings
        
        # Get session snapshot for volume and range data
        snapshot = self.market_data.build_ep_session_snapshot(symbol)
        if not snapshot:
            tracker.record(
                symbol=symbol,
                scanner="warrior",
                reason=RejectionReason.SNAPSHOT_FAILED,
                details="Failed to build session snapshot",
            )
            scan_logger.info(f"FAIL | {symbol} | Reason: snapshot_failed")
            return None
        
        # Extract metrics
        session_volume = snapshot["session_volume"]
        avg_volume = snapshot["avg_daily_volume"]
        session_high = snapshot["session_high"]
        session_low = snapshot["session_low"]
        last_price = snapshot["last_price"]
        
        # =========================================================================
        # CHINESE STOCK CHECK (Country-based)
        # =========================================================================
        if s.exclude_chinese_stocks:
            country = self._get_country(symbol)
            if self._is_likely_chinese(name, country=country):
                tracker.record(
                    symbol=symbol,
                    scanner="warrior",
                    reason=RejectionReason.COUNTRY_EXCLUDED,
                    details=f"Chinese/HK stock excluded (country={country})",
                )
                scan_logger.info(f"FAIL | {symbol} | Reason: chinese_stock | Country: {country}")
                if verbose:
                    print(f"{symbol}: Rejected - Chinese/HK stock (country={country})")
                return None
        
        # =========================================================================
        # PILLAR 1: Float (< 100M, ideal < 20M)
        # =========================================================================
        # Note: FMP doesn't provide float directly in most endpoints
        # We'll use the profile endpoint if available, or skip this check
        float_shares = self._get_float_shares(symbol)
        
        if float_shares is not None and float_shares > s.max_float:
            tracker.record(
                symbol=symbol,
                scanner="warrior",
                reason=RejectionReason.FLOAT_TOO_HIGH,
                values={"float": float_shares, "max": s.max_float},
            )
            scan_logger.info(f"FAIL | {symbol} | Reason: float_too_high | Float: {float_shares:,} > {s.max_float:,}")
            if verbose:
                print(f"{symbol}: Rejected - Float {float_shares:,} > {s.max_float:,}")
            return None
        
        is_ideal_float = float_shares is not None and float_shares < s.ideal_float
        
        # =========================================================================
        # PILLAR 2: Relative Volume (> 2x, ideal 3-5x)
        # =========================================================================
        rvol = Decimal(session_volume) / Decimal(avg_volume) if avg_volume > 0 else Decimal("0")
        
        if rvol < s.min_rvol:
            tracker.record(
                symbol=symbol,
                scanner="warrior",
                reason=RejectionReason.RVOL_TOO_LOW,
                values={"rvol": round(float(rvol), 2), "min": float(s.min_rvol)},
            )
            scan_logger.info(f"FAIL | {symbol} | Reason: rvol_too_low | RVOL: {rvol:.1f}x < {s.min_rvol}x")
            if verbose:
                print(f"{symbol}: Rejected - RVOL {rvol:.1f}x < {s.min_rvol}x")
            return None
        
        is_ideal_rvol = rvol >= s.ideal_rvol
        
        # =========================================================================
        # PILLAR 3: Catalyst (News/Earnings/Former Runner)
        # =========================================================================
        has_catalyst, catalyst_type, catalyst_desc = self.market_data.has_recent_catalyst(
            symbol, days=s.catalyst_lookback_days
        )
        
        if s.require_catalyst and not has_catalyst:
            # Check if it's a "former runner" (could add historical volatility check)
            if s.include_former_runners:
                is_former_runner = self._is_former_runner(symbol)
                if is_former_runner:
                    has_catalyst = True
                    catalyst_type = "former_runner"
                    catalyst_desc = "History of big moves"
        
        if s.require_catalyst and not has_catalyst:
            tracker.record(
                symbol=symbol,
                scanner="warrior",
                reason=RejectionReason.NO_CATALYST,
                details=catalyst_desc,
            )
            scan_logger.info(f"FAIL | {symbol} | Reason: no_catalyst")
            if verbose:
                print(f"{symbol}: Rejected - No catalyst found")
            return None
        
        # =========================================================================
        # DILUTION CHECK - Reject bearish catalysts (ANPA trap avoidance)
        # =========================================================================
        if catalyst_desc:
            catalyst_lower = catalyst_desc.lower()
            for dilution_kw in DILUTION_KEYWORDS:
                if dilution_kw in catalyst_lower:
                    tracker.record(
                        symbol=symbol,
                        scanner="warrior",
                        reason=RejectionReason.CATALYST_DILUTION,
                        details=f"Dilution catalyst: {dilution_kw}",
                    )
                    if verbose:
                        print(f"{symbol}: Rejected - Dilution catalyst: {dilution_kw}")
                    return None
        
        # =========================================================================
        # PILLAR 4: Price ($1.50 - $20)
        # =========================================================================
        # Already pre-filtered, but double-check
        if price < s.min_price or price > s.max_price:
            tracker.record(
                symbol=symbol,
                scanner="warrior",
                reason=RejectionReason.PRICE_OUT_OF_RANGE,
                values={"price": float(price), "min": float(s.min_price), "max": float(s.max_price)},
            )
            return None
        
        # =========================================================================
        # PILLAR 5: Gap % (> 4%, ideal 5-10%)
        # =========================================================================
        # Recalculate gap from actual yesterday_close vs current price
        # FMP's change_percent can be stale (from previous day's move, not today's)
        yesterday_close = snapshot["yesterday_close"]
        if yesterday_close and yesterday_close > 0:
            gap_pct = ((last_price - yesterday_close) / yesterday_close) * 100
        else:
            gap_pct = change_percent  # Fallback to FMP data if no yesterday close
        
        # Re-check gap threshold with corrected value
        if gap_pct < s.min_gap:
            tracker.record(
                symbol=symbol,
                scanner="warrior",
                reason=RejectionReason.GAP_TOO_LOW,
                values={"gap": round(float(gap_pct), 1), "min": float(s.min_gap)},
            )
            if verbose:
                print(f"{symbol}: Rejected - Gap {gap_pct:.1f}% < {s.min_gap}%")
            return None
        
        is_ideal_gap = gap_pct >= s.ideal_gap
        
        # =========================================================================
        # ADDITIONAL: Dollar Volume Check
        # =========================================================================
        dollar_vol = last_price * session_volume
        if dollar_vol < s.min_dollar_volume:
            tracker.record(
                symbol=symbol,
                scanner="warrior",
                reason=RejectionReason.DOLLAR_VOL_LOW,
                values={"dollar_vol": round(float(dollar_vol)), "min": float(s.min_dollar_volume)},
            )
            if verbose:
                print(f"{symbol}: Rejected - Dollar volume ${dollar_vol:,.0f} < ${s.min_dollar_volume:,.0f}")
            return None
        
        # =========================================================================
        # BUILD CANDIDATE
        # =========================================================================
        atr = self.market_data.get_atr(symbol, period=14) or Decimal("1")
        
        candidate = WarriorCandidate(
            symbol=symbol,
            name=name,
            float_shares=float_shares,
            relative_volume=rvol,
            catalyst_type=catalyst_type,
            catalyst_description=catalyst_desc,
            price=Decimal(str(last_price)),  # Use current quote price, not stale FMP price
            gap_percent=Decimal(str(gap_pct)),  # Recalculated gap
            is_ideal_float=is_ideal_float,
            is_ideal_rvol=is_ideal_rvol,
            is_ideal_gap=is_ideal_gap,
            session_high=Decimal(str(session_high)),
            session_low=Decimal(str(session_low)),
            session_volume=session_volume,
            avg_volume=avg_volume,
            dollar_volume=dollar_vol,
            atr=atr,
            scanned_at=datetime.now(),
        )
        
        if verbose:
            print(f"✅ {symbol}: Passed all 5 Pillars (score={candidate.quality_score})")
        
        return candidate
    
    def _get_float_shares(self, symbol: str) -> Optional[int]:
        """
        Get float shares for a symbol.
        
        Uses FMP's shares-float endpoint if available.
        Returns None if data unavailable (skip float check).
        """
        try:
            # Try to get float from FMP
            # FMP endpoint: /api/v4/shares_float?symbol=AAPL
            data = self.market_data.fmp._get(f"shares_float", params={"symbol": symbol})
            if data and len(data) > 0:
                return int(data[0].get("floatShares", 0))
        except Exception:
            pass
        
        return None  # Float data unavailable, skip check
    
    def _is_former_runner(self, symbol: str) -> bool:
        """
        Check if symbol is a "former runner" (history of big moves).
        
        This identifies stocks that have a track record of momentum,
        even without a current news catalyst.
        
        Criteria:
        - Has made 20%+ moves in the past 90 days
        """
        try:
            bars = self.market_data.fmp.get_daily_bars(symbol, limit=90)
            if not bars or len(bars) < 20:
                return False
            
            # Check for days with 20%+ move
            big_move_count = 0
            for bar in bars:
                if bar.high > 0 and bar.low > 0:
                    day_range_pct = ((bar.high - bar.low) / bar.low) * 100
                    if day_range_pct >= 20:
                        big_move_count += 1
            
            # If 3+ big move days in 90 days, it's a former runner
            return big_move_count >= 3
            
        except Exception:
            return False
    
    def _is_likely_chinese(self, name: str, country: Optional[str] = None) -> bool:
        """
        Detect likely Chinese stocks by country or company name.
        
        Ross avoids these due to pump & dump patterns.
        
        Args:
            name: Company name
            country: Country code from FMP profile (e.g., "CN", "HK")
        """
        # Primary check: country code from FMP profile
        if country:
            country_upper = country.upper()
            if country_upper in ("CN", "CHINA", "HK", "HONG KONG"):
                return True
        
        # Fallback: name-based heuristics
        if not name:
            return False
        
        name_lower = name.lower()
        chinese_indicators = [
            "china", "chinese", "hong kong", "shanghai", "shenzhen",
            "beijing", "guangzhou", "holdings ltd", "group ltd",
        ]
        
        return any(indicator in name_lower for indicator in chinese_indicators)
    
    def _get_country(self, symbol: str) -> Optional[str]:
        """Get country for a symbol from FMP profile."""
        try:
            return self.market_data.fmp.get_country(symbol)
        except Exception:
            return None


# =============================================================================
# SINGLETON
# =============================================================================

_warrior_scanner_service: Optional[WarriorScannerService] = None


def get_warrior_scanner_service() -> WarriorScannerService:
    """Get singleton Warrior scanner service."""
    global _warrior_scanner_service
    if _warrior_scanner_service is None:
        _warrior_scanner_service = WarriorScannerService()
    return _warrior_scanner_service
