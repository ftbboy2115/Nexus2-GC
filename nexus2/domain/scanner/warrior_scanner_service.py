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

import pytz

from nexus2.adapters.market_data import UnifiedMarketData
from nexus2.domain.automation.rejection_tracker import (
    get_rejection_tracker,
    RejectionReason,
)
from nexus2.domain.automation.catalyst_classifier import get_classifier
from nexus2.domain.automation.ai_catalyst_validator import (
    get_ai_validator,
    get_catalyst_cache,
    get_multi_validator,
    get_headline_cache,
)
from nexus2.utils.time_utils import now_et, now_utc_factory


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


def _format_float(value: int) -> str:
    """Format float shares as #.#M, #.#K, or raw number for readability."""
    if value >= 1_000_000_000:
        return f"{value / 1_000_000_000:.1f}B"
    elif value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    elif value >= 1_000:
        return f"{value / 1_000:.1f}K"
    return str(value)


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
    
    # ETB + High Float Disqualifier (Ross Cameron methodology)
    # "Easy to borrow + 35M float = choppy, fake-outs, shorts will flush it"
    etb_high_float_threshold: int = 10_000_000  # Reject ETB stocks with float > 10M
    
    # Pure High Float Disqualifier (does NOT rely on broker ETB data)
    # Ross Cameron prefers sub-20M float; anything >30M is choppy/institutionally-held
    # This triggers REGARDLESS of borrow status since Alpaca ETB data is unreliable
    high_float_threshold: int = 30_000_000  # Hard reject if float > 30M
    
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
    # Icebreaker Exception: Ross trades Chinese with reduced size when score is exceptional (Jan 20 TWWG)
    chinese_icebreaker_enabled: bool = True  # Allow high-score Chinese stocks
    high_quality_threshold: int = 10  # A+ setup threshold (used by icebreaker, exit mode selection)
    require_catalyst: bool = True  # Require news/earnings
    include_former_runners: bool = False  # Disabled: Ross uses this as score boost, not catalyst substitute
    use_ai_catalyst_fallback: bool = True  # Use AI when regex fails
    debug_ai_comparison: bool = False  # Disabled: replaced by multi-model comparison
    
    # Reverse Split + Offering Bypass (Ross Cameron Jan 21, 2026)
    # "Can't exclude all stocks with shelf registrations - that would exclude the most volatile movers"
    # If stock is on RS watchlist AND has fresh positive catalyst → bypass offering rejection
    allow_offering_for_reverse_splits: bool = True  # Configurable for risk management
    
    # Multi-Model Comparison (for training regex patterns)
    enable_multi_model_comparison: bool = True  # Queue headlines for AI comparison
    comparison_models: list = None  # Default: ["flash_lite", "pro"] - set in __post_init__
    
    def __post_init__(self):
        if self.comparison_models is None:
            self.comparison_models = ["flash_lite", "pro"]
    
    # Pre-market Filters
    min_premarket_volume: int = 100_000  # 100K shares pre-market
    
    # MACD Settings (12, 26, 9) - for future pattern detection
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    
    # Pillar 6: 200 EMA Resistance Check (Ross Cameron methodology)
    # "200 EMA acts as ceiling until broken through with volume"
    # Reject if 200 EMA is too close overhead (less than min_room_to_200ema_pct)
    check_200_ema: bool = True  # Enable 200 EMA resistance check
    min_room_to_200ema_pct: float = 15.0  # Reject if < 15% room to 200 EMA


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
# NON-EQUITY TICKER FILTER
# =============================================================================
# Suffixes that indicate non-tradeable or non-equity securities
# Warrants, units, rights, and some private class shares don't trade intraday

NON_EQUITY_SUFFIXES = {
    "W",    # Warrants (e.g., GIWWR)
    "WS",   # Warrants
    "U",    # Units (e.g., MBAVU)
    "R",    # Rights (e.g., ALISR, APACR)
}

# Known non-intraday tickers (private funds, closed-end funds, etc.)
NON_INTRADAY_TICKERS = {
    "XSPIX",  # StepStone Private Venture Fund - only D/W/M intervals
}


def is_tradeable_equity(symbol: str) -> bool:
    """
    Check if ticker is a tradeable common stock.
    
    Filters out:
    - Warrants (end in W, WS)
    - Units (end in U)
    - Rights (end in R)
    - Known non-intraday tickers (private funds)
    
    Returns True if likely tradeable, False if should be skipped.
    """
    if not symbol:
        return False
    
    # Check known non-intraday tickers
    if symbol in NON_INTRADAY_TICKERS:
        return False
    
    # Check suffix patterns (only if symbol is long enough)
    # Short symbols like "W" or "R" are valid tickers
    for suffix in NON_EQUITY_SUFFIXES:
        # Only match if there's a base ticker before the suffix
        # and the suffix is at the end
        if len(symbol) > len(suffix) + 2 and symbol.endswith(suffix):
            # Additional check: the character before suffix should be a letter
            # This prevents matching things like "TSLAW" where "W" is part of name
            return False
    
    return True


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
    catalyst_date: Optional[datetime] = None  # For freshness scoring (Ross's flame colors)
    is_ideal_float: bool = False  # < 20M shares
    is_ideal_rvol: bool = False  # > 3x
    is_ideal_gap: bool = False  # > 5%
    is_former_runner: bool = False  # History of big moves (score boost)
    
    # Borrow status (from Alpaca)
    # Ross Cameron: "If it's easy to borrow with no news, it's probably going to just drop right back down"
    hard_to_borrow: bool = False  # HTB = squeezable, shorts can't pile in
    easy_to_borrow: bool = True  # ETB = default assumption if no data
    
    # Icebreaker flag (Chinese stock with high score)
    is_icebreaker: bool = False  # Flag for reduced position sizing
    
    # Reverse split watchlist (Ross Cameron Jan 21, 2026)
    # Companies pump stock after reverse splits before secondary offerings
    is_reverse_split: bool = False  # Had reverse split in last 45 days
    split_date: Optional[str] = None  # Date of split (YYYY-MM-DD)
    split_ratio: Optional[str] = None  # e.g., "1:10"
    
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
    
    # 200 EMA Resistance (Ross Cameron methodology)
    # "200 EMA acts as ceiling until broken"
    ema_200: Optional[Decimal] = None  # Daily 200 EMA value
    room_to_200_ema_pct: Optional[float] = None  # % room to 200 EMA (negative = above)
    
    # Metadata
    scanned_at: datetime = field(default_factory=now_utc_factory)
    
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
        
        # Catalyst freshness bonus (3 points max) - Ross's flame indicator colors
        # Red flame (0-2hr) = +3, Orange (2-12hr) = +2, Yellow (12-24hr) = +1
        freshness_bonus = 0
        if self.catalyst_date and self.catalyst_type not in ("none", None, ""):
            from datetime import timezone
            try:
                # Use simulation clock time if available (for historical replay)
                # Otherwise use real time (for live trading)
                try:
                    from nexus2.adapters.simulation import get_simulation_clock
                    sim_clock = get_simulation_clock()
                    if sim_clock and sim_clock.current_time:
                        now = sim_clock.current_time
                    else:
                        now = datetime.now(timezone.utc)
                except ImportError:
                    now = datetime.now(timezone.utc)
                
                # Ensure catalyst_date is aware
                cat_date = self.catalyst_date
                if cat_date.tzinfo is None:
                    cat_date = cat_date.replace(tzinfo=timezone.utc)
                hours_old = (now - cat_date).total_seconds() / 3600
                if hours_old <= 2:
                    freshness_bonus = 3  # 🔴 Red flame: breaking news
                elif hours_old <= 12:
                    freshness_bonus = 2  # 🟠 Orange flame: earlier today
                elif hours_old <= 24:
                    freshness_bonus = 1  # 🟡 Yellow flame: yesterday
                # >24hr: no bonus (no flame indicator)
                score += freshness_bonus
            except Exception:
                pass  # Skip freshness scoring if date parsing fails
        
        # Price quality (1 point max)
        if Decimal("5") <= self.price <= Decimal("15"):
            score += 1  # Sweet spot
        
        # Former runner bonus (1 point)
        if self.is_former_runner:
            score += 1  # History of big moves adds conviction
        
        # Hard-to-borrow bonus (1 point)
        # HTB stocks have higher squeeze potential - shorts can't easily cover
        if self.hard_to_borrow:
            score += 1  # HTB = squeezability bonus
        
        # Reverse split bonus (2 points) - Ross Cameron Jan 21, 2026
        # "Some of the biggest winners in the last 6 weeks were stocks that recently did reverse splits"
        if self.is_reverse_split:
            score += 2  # Proactive watchlist bonus
        
        return min(score, 16)  # Max now 16 with freshness + reverse split bonus


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
        alpaca_broker=None,  # Optional: for HTB/ETB lookups
    ):
        self.settings = settings or WarriorScanSettings()
        self.market_data = market_data or UnifiedMarketData()
        self.alpaca_broker = alpaca_broker  # Used for get_asset_info() HTB checks
    
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
        current_et = datetime.now(et)
        is_premarket = current_et.hour < 9 or (current_et.hour == 9 and current_et.minute < 30)
        
        # Step 1: Get gainers from appropriate endpoint
        # Pre-market uses pre_post_market/gainers for actual gapping stocks
        # Regular hours uses stock_market/gainers for intraday movers
        if is_premarket:
            # Use pre-market gainers endpoint for stocks actually gapping today
            gainers = self.market_data.get_premarket_gainers(min_change_pct=float(self.settings.min_gap))
            scan_logger.info(f"PREMARKET MODE | Using pre_post_market/gainers | Found: {len(gainers)} stocks")
            
            # Fallback to regular gainers if pre-market endpoint returns empty
            # (FMP pre_post_market can be empty early in pre-market or due to data issues)
            if not gainers:
                gainers = self.market_data.get_gainers()
                scan_logger.info(f"PREMARKET FALLBACK | Using stock_market/gainers | Found: {len(gainers)} stocks")
        else:
            gainers = self.market_data.get_gainers()
            scan_logger.info(f"REGULAR MODE | Using stock_market/gainers | Found: {len(gainers)} stocks")
        
        actives = self.market_data.get_actives()
        
        # Get Alpaca movers as secondary source (faster pre-market updates)
        alpaca_movers = self.market_data.get_alpaca_movers(
            top=50,
            min_change_pct=float(self.settings.min_gap)
        )
        scan_logger.info(f"ALPACA MOVERS | Found: {len(alpaca_movers)} stocks")
        
        # Combine and dedupe (prefer FMP data when available for name field)
        seen = set()
        all_movers = []
        
        # FMP gainers first (has name)
        for g in gainers:
            sym = g["symbol"]
            if sym not in seen:
                seen.add(sym)
                all_movers.append(g)
        
        # FMP actives second (has name)
        for a in actives:
            sym = a["symbol"]
            if sym not in seen:
                seen.add(sym)
                all_movers.append(a)
        
        # Alpaca movers third (fills gaps, may lack name)
        for m in alpaca_movers:
            sym = m["symbol"]
            if sym not in seen:
                seen.add(sym)
                all_movers.append(m)
        
        if not all_movers:
            return WarriorScanResult(
                candidates=[],
                processed_count=0,
                filtered_count=0,
                scan_time=now_et(),
            )
        
        # Recalculate gap with live prices (FMP screener data can be stale)
        # Use unified cross-validated quote (Alpaca + Schwab + FMP)
        # This prevents stale phantom prices like BATL $5.38 issue (Jan 29, 2026)
        for mover in all_movers:
            symbol = mover["symbol"]
            try:
                # Get live price using unified cross-validated source
                # This method checks Alpaca vs Schwab vs FMP and picks best source
                unified_quote = self.market_data.get_quote(symbol)
                if unified_quote and unified_quote.price > 0:
                    live_price = float(unified_quote.price)
                    # Get previousClose from FMP quote (reliable)
                    fmp_data = self.market_data.fmp._get(f"quote/{symbol}")
                    if fmp_data and len(fmp_data) > 0:
                        prev_close = float(fmp_data[0].get("previousClose", 0))
                        if prev_close > 0:
                            # Recalculate gap
                            old_gap = float(mover["change_percent"])
                            new_gap = ((live_price - prev_close) / prev_close) * 100
                            if abs(new_gap - old_gap) > 10:  # Log significant differences
                                scan_logger.info(
                                    f"GAP RECALC | {symbol}: {old_gap:.1f}% -> {new_gap:.1f}% "
                                    f"(live=${live_price:.2f}, prev=${prev_close:.2f})"
                                )
                            mover["change_percent"] = Decimal(str(new_gap))
                            mover["price"] = Decimal(str(live_price))
            except Exception as e:
                scan_logger.debug(f"GAP RECALC | {symbol}: Error - {e}")
        
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
        
        # Exclude non-equity tickers (warrants, units, rights, private funds)
        pre_filter_count = len(filtered_movers)
        filtered_movers = [g for g in filtered_movers if is_tradeable_equity(g["symbol"])]
        non_equity_removed = pre_filter_count - len(filtered_movers)
        if non_equity_removed > 0:
            scan_logger.debug(f"Excluded {non_equity_removed} non-equity tickers (warrants/units/rights/funds)")
        
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
                scan_time=now_et(),
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
                    
                    # Log to scan history for Lab backtesting universe
                    try:
                        from nexus2.domain.lab.scan_history_logger import get_scan_history_logger
                        history_logger = get_scan_history_logger()
                        history_logger.log_passed_symbol(
                            symbol=symbol,
                            scan_date=now_et().date(),
                            gap_percent=float(mover['change_percent']),
                            rvol=float(candidate.relative_volume),
                            score=candidate.quality_score,
                            catalyst=candidate.catalyst_type,
                        )
                    except Exception as e:
                        scan_logger.debug(f"[ScanHistory] Failed to log {symbol}: {e}")
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
            scan_time=now_et(),
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
            scan_logger.info(f"FAIL | {symbol} | Gap:{change_percent:.1f}% | Reason: snapshot_failed")
            return None
        
        # Extract metrics
        session_volume = snapshot["session_volume"]
        avg_volume = snapshot["avg_daily_volume"]
        session_high = snapshot["session_high"]
        session_low = snapshot["session_low"]
        last_price = snapshot["last_price"]
        
        # =========================================================================
        # CHINESE STOCK CHECK (Country-based)
        # With Icebreaker Exception: High-score Chinese stocks can pass with 50% size
        # (Ross Cameron, Jan 20 TWWG: "breaking the ice with smaller positions")
        # =========================================================================
        is_chinese = False
        country = None
        if s.exclude_chinese_stocks:
            country = self._get_country(symbol)
            if self._is_likely_chinese(name, country=country):
                is_chinese = True
                # If icebreaker not enabled, reject immediately
                if not s.chinese_icebreaker_enabled:
                    tracker.record(
                        symbol=symbol,
                        scanner="warrior",
                        reason=RejectionReason.COUNTRY_EXCLUDED,
                        details=f"Chinese/HK stock excluded (country={country})",
                    )
                    scan_logger.info(f"FAIL | {symbol} | Gap:{change_percent:.1f}% | Reason: chinese_stock | Country: {country}")
                    if verbose:
                        print(f"{symbol}: Rejected - Chinese/HK stock (country={country})")
                    return None
                # Otherwise, continue evaluation - will check score after candidate built
        
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
            scan_logger.info(f"FAIL | {symbol} | Gap:{change_percent:.1f}% | Reason: float_too_high | Float: {_format_float(float_shares)} > {_format_float(s.max_float)}")
            if verbose:
                print(f"{symbol}: Rejected - Float {float_shares:,} > {s.max_float:,}")
            return None
        
        is_ideal_float = float_shares is not None and float_shares < s.ideal_float
        
        # =========================================================================
        # PILLAR 2: Relative Volume (> 2x, ideal 3-5x)
        # Time-adjusted projection: normalize for time of day since volume
        # accumulates throughout the session. Projects current volume to full-day pace.
        # 
        # Trading windows:
        # - Pre-market: 4:00 AM - 9:30 AM ET (5.5 hours = 330 minutes)
        # - Regular:    9:30 AM - 4:00 PM ET (6.5 hours = 390 minutes)
        # - Total:      12 hours = 720 minutes of potential volume
        # =========================================================================
        if avg_volume > 0:
            et_tz = pytz.timezone('America/New_York')
            current_et = datetime.now(et_tz)
            market_open_today = current_et.replace(hour=9, minute=30, second=0, microsecond=0)
            premarket_start_today = current_et.replace(hour=4, minute=0, second=0, microsecond=0)
            
            # Total trading minutes in a day (pre-market + regular hours)
            trading_minutes_per_day = 390  # 6.5 hours = 390 minutes (regular session only for avg)
            
            if current_et > market_open_today:
                # Regular market hours - project based on elapsed time since open
                minutes_since_open = (current_et - market_open_today).total_seconds() / 60
                
                # Project current volume to full-day pace
                time_factor = trading_minutes_per_day / max(minutes_since_open, 1)
                time_factor = min(time_factor, 20.0)  # Cap at 20x projection
                
                projected_volume = Decimal(session_volume) * Decimal(str(time_factor))
                rvol = projected_volume / Decimal(avg_volume)
            else:
                # Pre-market (4:00 AM - 9:30 AM) - project based on elapsed pre-market time
                # Ross trades 7AM-10AM, so pre-market RVOL projection is critical
                minutes_since_premarket = max((current_et - premarket_start_today).total_seconds() / 60, 1)
                premarket_minutes = 330  # 5.5 hours = 330 minutes
                
                # Project pre-market volume to what it would be at open (9:30 AM)
                # Then compare to regular-hours average volume
                # This gives us "on pace to have Xx volume by open"
                premarket_factor = premarket_minutes / minutes_since_premarket
                premarket_factor = min(premarket_factor, 50.0)  # Cap at 50x for very early scans
                
                projected_premarket_volume = Decimal(session_volume) * Decimal(str(premarket_factor))
                
                # Pre-market volume is typically 10% of daily - multiply by 10x to normalize to daily equivalent
                # Based on analysis of Ross's trades (all ended 20x-4000x EOD RVOL)
                # This ensures stocks with strong pre-market activity pass the RVOL check early
                daily_equivalent_factor = 10.0  # Pre-market typically ~10% of daily volume
                projected_daily = projected_premarket_volume * Decimal(str(daily_equivalent_factor))
                
                rvol = projected_daily / Decimal(avg_volume)
        else:
            rvol = Decimal("0")
        
        if rvol < s.min_rvol:
            tracker.record(
                symbol=symbol,
                scanner="warrior",
                reason=RejectionReason.RVOL_TOO_LOW,
                values={"rvol": round(float(rvol), 2), "min": float(s.min_rvol)},
            )
            scan_logger.info(f"FAIL | {symbol} | Gap:{change_percent:.1f}% | RVOL:{rvol:.1f}x | Reason: rvol_too_low | RVOL: {rvol:.1f}x < {s.min_rvol}x")
            if verbose:
                print(f"{symbol}: Rejected - RVOL {rvol:.1f}x < {s.min_rvol}x")
            return None
        
        is_ideal_rvol = rvol >= s.ideal_rvol
        
        # =========================================================================
        # PILLAR 3: Catalyst (News/Earnings/Former Runner)
        # Uses CatalystClassifier with confidence scoring to filter weak catalysts
        # Now fetches from BOTH FMP and Alpaca (Benzinga) for better coverage
        # (AQMS "battery supply agreement" was in Alpaca but not FMP)
        # =========================================================================
        classifier = get_classifier()
        # Use merged headlines from FMP + Alpaca for better micro-cap coverage
        headlines = self.market_data.get_merged_headlines(
            symbol, 
            days=s.catalyst_lookback_days,
            alpaca_broker=self.alpaca_broker,
        )
        
        has_catalyst = False
        catalyst_type = "none"
        catalyst_desc = "No catalyst found"
        catalyst_confidence = 0.0
        catalyst_date = None  # For freshness scoring (Ross's flame colors)
        
        # Check headlines with classifier (confidence-based)
        if headlines:
            if verbose:
                print(f"[Catalyst Debug] {symbol}: Found {len(headlines)} headlines")
                # Show first 2 raw headlines for debugging
                for i, h in enumerate(headlines[:2]):
                    print(f"[Catalyst Debug] {symbol}: [{i+1}] {h[:80]}...")
            
            has_positive, best_type, best_headline = classifier.has_positive_catalyst(headlines)
            if has_positive and best_type:
                # Get confidence for the best match
                match = classifier.classify(best_headline)
                catalyst_confidence = match.confidence
                
                # Debug logging when verbose
                if verbose:
                    print(f"[Catalyst Debug] {symbol}: type={best_type}, conf={catalyst_confidence:.2f}, headline='{best_headline[:60]}...'")
                
                # Require confidence >= 0.6 (filters weak catalysts like conferences)
                if catalyst_confidence >= 0.6:
                    has_catalyst = True
                    catalyst_type = best_type
                    catalyst_desc = best_headline[:80] if best_headline else ""
                    # Try to get the publish date for this headline
                    news_with_dates = self.market_data.fmp.get_news_with_dates(symbol, days=s.catalyst_lookback_days)
                    for headline, pub_date in news_with_dates:
                        if headline == best_headline or headline[:50] == best_headline[:50]:
                            catalyst_date = pub_date
                            break
                else:
                    catalyst_desc = f"Weak catalyst (confidence {catalyst_confidence:.1f})"
            else:
                if verbose:
                    print(f"[Catalyst Debug] {symbol}: No positive catalyst pattern matched")
            
            # Also check for negative catalysts (offering, sec, miss) - reject these
            has_negative, neg_type, neg_headline = classifier.has_negative_catalyst(headlines)
            if has_negative:
                # REVERSE SPLIT BYPASS: Ross trades offerings if stock is RS + fresh positive catalyst
                # "Can't exclude all stocks with shelf registrations - that would exclude the most volatile movers"
                should_bypass = False
                is_reverse_split = False
                
                if s.allow_offering_for_reverse_splits and neg_type == "offering":
                    # Check if stock is on reverse split watchlist
                    try:
                        from nexus2.domain.automation.reverse_split_service import get_reverse_split_service
                        rs_service = get_reverse_split_service()
                        rs_record = rs_service.is_recent_reverse_split(symbol)
                        if rs_record:
                            is_reverse_split = True
                            # Only bypass if we found a positive catalyst (news/earnings)
                            if has_catalyst and catalyst_type not in ("none", "", None):
                                should_bypass = True
                                scan_logger.info(
                                    f"🔄 BYPASS | {symbol} | RS+Offering allowed | "
                                    f"RS: {rs_record.date} ({rs_record.ratio}) | "
                                    f"Catalyst: {catalyst_type} | Offering: {neg_headline[:40]}"
                                )
                                if verbose:
                                    print(f"[RS Bypass] {symbol}: Offering bypassed (RS + {catalyst_type})")
                    except Exception as e:
                        scan_logger.debug(f"[RS Check] {symbol}: Error - {e}")
                
                if not should_bypass:
                    tracker.record(
                        symbol=symbol,
                        scanner="warrior",
                        reason=RejectionReason.CATALYST_DILUTION,
                        details=f"Negative catalyst: {neg_type} - {neg_headline[:50]}",
                    )
                    scan_logger.info(f"FAIL | {symbol} | Gap:{change_percent:.1f}% | RVOL:{rvol:.1f}x | Reason: negative_catalyst | Type: {neg_type}")
                    if verbose:
                        print(f"{symbol}: Rejected - Negative catalyst: {neg_type}")
                    return None
        
        # Check for recent earnings as backup (strongest catalyst)
        if not has_catalyst:
            has_earnings, earnings_date = self.market_data.fmp.has_recent_earnings(symbol, days=s.catalyst_lookback_days)
            if has_earnings:
                has_catalyst = True
                catalyst_type = "earnings"
                catalyst_desc = f"Earnings {earnings_date}"
                catalyst_confidence = 0.9
                if verbose:
                    print(f"[Catalyst Debug] {symbol}: EARNINGS catalyst - {earnings_date}")
        
        # Check if it's a "former runner" (history of big moves)
        if s.require_catalyst and not has_catalyst:
            if s.include_former_runners:
                is_former_runner = self._is_former_runner(symbol)
                if is_former_runner:
                    has_catalyst = True
                    catalyst_type = "former_runner"
                    catalyst_desc = "History of big moves"
                    catalyst_confidence = 0.7
                    if verbose:
                        print(f"[Catalyst Debug] {symbol}: FORMER RUNNER catalyst")
        
        # =====================================================================
        # SYNC DUAL CATALYST VALIDATION (HeadlineCache + Regex + Flash-Lite)
        # 1. Check HeadlineCache for previously seen headlines
        # 2. Filter to only NEW headlines not yet validated
        # 3. Run sync dual validation: Regex vs Flash-Lite → Pro tiebreaker
        # 4. Cache all results to avoid re-validating
        # =====================================================================
        if headlines and s.enable_multi_model_comparison:
            headline_cache = get_headline_cache()
            
            # Check if we already have a valid catalyst from cached headlines
            cached_valid, cached_type = headline_cache.has_valid_catalyst(symbol)
            if cached_valid and not has_catalyst:
                has_catalyst = True
                catalyst_type = f"cached_{cached_type}"
                catalyst_desc = f"Cached: {cached_type}"
                catalyst_confidence = 0.85
                if verbose:
                    print(f"[Headline Cache] {symbol}: HIT - valid catalyst from cache ({cached_type})")
            
            # Filter to only NEW headlines we haven't seen before
            new_headlines = headline_cache.get_new_headlines(symbol, headlines)
            
            if new_headlines and not has_catalyst:
                # Need to validate new headlines
                multi_validator = get_multi_validator()
                
                for headline in new_headlines[:3]:  # Limit to top 3 new headlines
                    try:
                        # Check regex first for this headline
                        classifier = get_classifier()
                        regex_match = classifier.classify(headline)
                        regex_valid = regex_match.is_positive and regex_match.confidence >= 0.6
                        regex_type_h = regex_match.catalyst_type if regex_valid else None
                        
                        # Sync dual validation: Regex + Flash-Lite
                        final_valid, final_type, _, flash_passed, method = multi_validator.validate_sync(
                            headline=headline,
                            symbol=symbol,
                            regex_passed=regex_valid,
                            regex_type=regex_type_h,
                        )
                        
                        # Cache the result
                        headline_cache.add(
                            symbol=symbol,
                            headline=headline,
                            is_valid=final_valid,
                            catalyst_type=final_type,
                            regex_passed=regex_valid,
                            flash_passed=flash_passed,
                            method=method,
                        )
                        
                        # Use result if valid and we don't have a catalyst yet
                        if final_valid and not has_catalyst:
                            has_catalyst = True
                            catalyst_type = final_type
                            catalyst_desc = f"{method}: {headline[:50]}"
                            catalyst_confidence = 0.85
                            if verbose:
                                print(f"[Catalyst Debug] {symbol}: {method.upper()} - {final_type}")
                            # Log PASS to catalyst audit for traceability
                            from nexus2.domain.automation.catalyst_classifier import log_headline_evaluation
                            log_headline_evaluation(symbol, new_headlines, "PASS", final_type)
                            break  # Found valid, no need to check more
                            
                    except Exception as e:
                        if verbose:
                            print(f"[Catalyst Debug] {symbol}: Validation error - {e}")
                        # Cache the headline as invalid to avoid retrying
                        headline_cache.add(
                            symbol=symbol,
                            headline=headline,
                            is_valid=False,
                            catalyst_type=None,
                            regex_passed=False,
                            flash_passed=None,
                            method="error",
                        )
            elif new_headlines and verbose:
                print(f"[Headline Cache] {symbol}: {len(new_headlines)} new headlines skipped (already have catalyst)")
        
        # Legacy single-model fallback (when multi-model is disabled)
        elif headlines and s.use_ai_catalyst_fallback and not has_catalyst:
            catalyst_cache = get_catalyst_cache()
            cached = catalyst_cache.get(symbol)
            if cached:
                if not has_catalyst and cached.is_valid:
                    has_catalyst = True
                    catalyst_type = f"cached_{cached.catalyst_type}"
                    catalyst_desc = cached.description
                    catalyst_confidence = 0.8
            else:
                try:
                    ai_validator = get_ai_validator()
                    ai_valid, ai_type, ai_headline = ai_validator.validate_headlines(headlines, symbol)
                    catalyst_cache.set(symbol, ai_valid, ai_type, ai_headline[:80] if ai_headline else f"AI: {ai_type}")
                    if ai_valid:
                        has_catalyst = True
                        catalyst_type = f"ai_{ai_type}"
                        catalyst_desc = f"AI: {ai_headline}" if ai_headline else f"AI: {ai_type}"
                        catalyst_confidence = 0.8
                except Exception as e:
                    if verbose:
                        print(f"[Catalyst Debug] {symbol}: AI fallback error - {e}")
        
        
        if s.require_catalyst and not has_catalyst:
            tracker.record(
                symbol=symbol,
                scanner="warrior",
                reason=RejectionReason.NO_CATALYST,
                details=catalyst_desc,
            )
            scan_logger.info(f"FAIL | {symbol} | Gap:{change_percent:.1f}% | RVOL:{rvol:.1f}x | Reason: no_catalyst | {catalyst_desc}")
            # Log all headlines to dedicated catalyst audit log for regex training
            if headlines:
                from nexus2.domain.automation.catalyst_classifier import log_headline_evaluation
                log_headline_evaluation(symbol, headlines, "FAIL", None)
            if verbose:
                print(f"{symbol}: Rejected - {catalyst_desc}")
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
        # PILLAR 6: Room to 200 EMA (Ross Cameron methodology)
        # "200 EMA acts as ceiling until broken through with volume"
        # Reject if 200 EMA is too close overhead (< min_room_to_200ema_pct)
        # =========================================================================
        ema_200_value = None
        room_to_ema_pct = None
        
        if s.check_200_ema:
            ema_200_value = self._get_200_ema(symbol)
            if ema_200_value and ema_200_value > 0 and float(last_price) > 0:
                # Calculate room: how far the 200 EMA is above current price
                room_to_ema_pct = ((float(ema_200_value) - float(last_price)) / float(last_price)) * 100
                
                # Only check if 200 EMA is ABOVE current price (potential ceiling)
                if 0 < room_to_ema_pct < s.min_room_to_200ema_pct:
                    # 200 EMA is too close overhead - acts as resistance ceiling
                    tracker.record(
                        symbol=symbol,
                        scanner="warrior",
                        reason=RejectionReason.EMA_200_CEILING,
                        values={
                            "price": round(float(last_price), 2),
                            "ema_200": round(float(ema_200_value), 2),
                            "room_pct": round(room_to_ema_pct, 1),
                            "min_room": s.min_room_to_200ema_pct,
                        },
                    )
                    scan_logger.info(
                        f"FAIL | {symbol} | Gap:{gap_pct:.1f}% | RVOL:{rvol:.1f}x | "
                        f"Reason: ema_200_ceiling | Price: ${last_price:.2f} | "
                        f"200 EMA: ${ema_200_value:.2f} ({room_to_ema_pct:.1f}% room < {s.min_room_to_200ema_pct}%)"
                    )
                    if verbose:
                        print(f"{symbol}: Rejected - 200 EMA ${ema_200_value:.2f} is only {room_to_ema_pct:.1f}% above price (need {s.min_room_to_200ema_pct}%)")
                    return None
        
        # =========================================================================
        # BUILD CANDIDATE
        # =========================================================================
        atr = self.market_data.get_atr(symbol, period=14) or Decimal("1")
        
        # Check former runner status for score boost (but NOT as catalyst bypass)
        is_former_runner = self._is_former_runner(symbol)
        
        # Check HTB/ETB status from Alpaca (if broker available)
        # Ross Cameron: "If it's easy to borrow with no news, it's probably going to just drop right back down"
        hard_to_borrow = False
        easy_to_borrow = True  # Default assumption
        if self.alpaca_broker:
            try:
                asset_info = self.alpaca_broker.get_asset_info(symbol)
                hard_to_borrow = asset_info.get("hard_to_borrow", False)
                easy_to_borrow = asset_info.get("easy_to_borrow", True)
                # Debug: log borrow status for all stocks
                scan_logger.debug(f"BORROW CHECK | {symbol} | HTB={hard_to_borrow}, ETB={easy_to_borrow}")
                if hard_to_borrow:
                    scan_logger.info(f"HTB BONUS | {symbol} is Hard-to-Borrow (+1 score)")
            except Exception as e:
                scan_logger.debug(f"Could not get HTB status for {symbol}: {e}")
        else:
            scan_logger.debug(f"BROKER MISSING | {symbol} | No alpaca_broker wired")
        
        # Pure High Float Disqualifier - Ross Cameron methodology (does NOT rely on broker)
        # "30M+ float = choppy, institutionally-held, lots of shorts ready to flush it"
        # This is the primary gate since Alpaca ETB data is unreliable
        if float_shares and float_shares > s.high_float_threshold:
            tracker.record(
                symbol=symbol,
                scanner="warrior",
                reason=RejectionReason.ETB_HIGH_FLOAT,  # Reuse reason code
                values={"float": float_shares, "threshold": s.high_float_threshold},
            )
            scan_logger.info(
                f"FAIL | {symbol} | Reason: high_float | "
                f"{_format_float(float_shares)} float > {_format_float(s.high_float_threshold)} threshold"
            )
            if verbose:
                print(f"{symbol}: Rejected - High Float ({_format_float(float_shares)} > {_format_float(s.high_float_threshold)})")
            return None
        
        # ETB + Medium-High Float Disqualifier (secondary check when broker data available)
        # This catches stocks 10-30M that are also ETB
        if easy_to_borrow and float_shares and float_shares > s.etb_high_float_threshold:
            tracker.record(
                symbol=symbol,
                scanner="warrior",
                reason=RejectionReason.ETB_HIGH_FLOAT,
                values={"float": float_shares, "threshold": s.etb_high_float_threshold, "etb": True},
            )
            scan_logger.info(
                f"FAIL | {symbol} | Reason: etb_high_float | "
                f"ETB with {_format_float(float_shares)} float > {_format_float(s.etb_high_float_threshold)}"
            )
            if verbose:
                print(f"{symbol}: Rejected - ETB + High Float ({_format_float(float_shares)} > {_format_float(s.etb_high_float_threshold)})")
            return None
        
        # Check Reverse Split status - Ross Cameron Jan 21, 2026
        # "Some of the biggest winners in the last 6 weeks were stocks that recently did reverse splits"
        is_reverse_split = False
        split_date = None
        split_ratio = None
        try:
            from nexus2.domain.automation.reverse_split_service import get_reverse_split_service
            rsplit_service = get_reverse_split_service()
            rsplit_record = rsplit_service.is_recent_reverse_split(symbol)
            if rsplit_record:
                is_reverse_split = True
                split_date = rsplit_record.date
                split_ratio = rsplit_record.ratio
                scan_logger.info(f"RSPLIT BONUS | {symbol} has recent reverse split ({split_ratio} on {split_date}) +2 score")
        except Exception as e:
            scan_logger.debug(f"Could not check reverse split for {symbol}: {e}")
        
        candidate = WarriorCandidate(
            symbol=symbol,
            name=name,
            float_shares=float_shares,
            relative_volume=rvol,
            catalyst_type=catalyst_type,
            catalyst_description=catalyst_desc,
            catalyst_date=catalyst_date,  # For freshness scoring
            price=Decimal(str(last_price)),  # Use current quote price, not stale FMP price
            gap_percent=Decimal(str(gap_pct)),  # Recalculated gap
            is_ideal_float=is_ideal_float,
            is_ideal_rvol=is_ideal_rvol,
            is_ideal_gap=is_ideal_gap,
            is_former_runner=is_former_runner,
            hard_to_borrow=hard_to_borrow,
            easy_to_borrow=easy_to_borrow,
            is_reverse_split=is_reverse_split,  # Reverse split watchlist (Ross Jan 21)
            split_date=split_date,
            split_ratio=split_ratio,
            session_high=Decimal(str(session_high)),
            session_low=Decimal(str(session_low)),
            session_volume=session_volume,
            avg_volume=avg_volume,
            dollar_volume=dollar_vol,
            atr=atr,
            ema_200=ema_200_value,
            room_to_200_ema_pct=room_to_ema_pct,
            scanned_at=now_et(),
        )
        
        # =========================================================================
        # ICEBREAKER DECISION: Chinese stocks with high score pass with 50% size
        # =========================================================================
        if is_chinese:
            score = candidate.quality_score
            if score >= s.high_quality_threshold:
                # High score - allow as icebreaker with reduced size
                candidate.is_icebreaker = True
                scan_logger.info(
                    f"ICEBREAKER | {symbol} | Score: {score} >= {s.high_quality_threshold} | "
                    f"Chinese stock PASSES with 50% size"
                )
                if verbose:
                    print(f"🧊 {symbol}: ICEBREAKER - Chinese stock passes (score={score}, 50% size)")
            else:
                # Low score - reject
                tracker.record(
                    symbol=symbol,
                    scanner="warrior",
                    reason=RejectionReason.COUNTRY_EXCLUDED,
                    details=f"Chinese stock, score {score} < {s.high_quality_threshold} threshold",
                )
                scan_logger.info(f"FAIL | {symbol} | Reason: chinese_low_score | Score: {score} < {s.high_quality_threshold}")
                if verbose:
                    print(f"{symbol}: Rejected - Chinese stock, score {score} too low")
                return None
        
        # Calculate freshness bonus for logging
        freshness_note = ""
        if candidate.catalyst_date:
            from datetime import timezone as tz
            try:
                now = datetime.now(tz.utc)
                cat_date = candidate.catalyst_date
                if cat_date.tzinfo is None:
                    cat_date = cat_date.replace(tzinfo=tz.utc)
                hours_old = (now - cat_date).total_seconds() / 3600
                if hours_old <= 2:
                    freshness_note = " 🔴+3"  # Red flame
                elif hours_old <= 12:
                    freshness_note = " 🟠+2"  # Orange flame
                elif hours_old <= 24:
                    freshness_note = " 🟡+1"  # Yellow flame
            except Exception:
                pass
        
        if verbose:
            htb_note = " [HTB]" if hard_to_borrow else ""
            print(f"✅ {symbol}: Passed all 5 Pillars (score={candidate.quality_score}{freshness_note}){htb_note}")
        
        # Log to scan file with freshness info (consolidated from PILLARS + SCAN)
        scan_logger.info(
            f"[PILLARS] PASS | {symbol} | Gap:{change_percent:.1f}% | Score: {candidate.quality_score}{freshness_note} | "
            f"Catalyst: {catalyst_type} | Float: {_format_float(float_shares) if float_shares else 'N/A'} | RVOL: {rvol:.1f}x"
        )
        
        return candidate
    
    def _get_float_shares(self, symbol: str) -> Optional[int]:
        """
        Get float shares for a symbol.
        
        Uses FMP's stable/shares-float endpoint if available.
        Returns None if data unavailable (skip float check).
        """
        try:
            import httpx
            from nexus2 import config as app_config
            
            # FMP stable endpoint: https://financialmodelingprep.com/stable/shares-float?symbol=X
            response = httpx.get(
                "https://financialmodelingprep.com/stable/shares-float",
                params={"symbol": symbol, "apikey": app_config.FMP_API_KEY},
                timeout=5.0,
            )
            response.raise_for_status()
            data = response.json()
            if data and len(data) > 0:
                float_val = data[0].get("floatShares")
                if float_val:
                    return int(float_val)
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
    
    def _get_200_ema(self, symbol: str) -> Optional[Decimal]:
        """
        Get the 200-period EMA from daily chart.
        
        Uses Polygon daily bars (400 days to ensure 200 EMA is calculated properly).
        
        Returns:
            200 EMA value as Decimal, or None if unavailable
        """
        try:
            # Get 400 daily bars to ensure we have enough data for 200 EMA
            # The market_data adapter handles limit-aware calendar day calculations
            bars = self.market_data.polygon.get_daily_bars(symbol, limit=400)
            if not bars or len(bars) < 200:
                scan_logger.debug(f"200 EMA | {symbol} | Insufficient bars ({len(bars) if bars else 0} < 200)")
                return None
            
            # Extract closing prices (most recent first in the bars list)
            closes = [float(bar.close) for bar in bars if bar.close]
            if len(closes) < 200:
                return None
            
            # Calculate EMA with period 200
            # EMA formula: EMA_today = Close * k + EMA_yesterday * (1-k)
            # where k = 2 / (period + 1)
            period = 200
            k = 2 / (period + 1)
            
            # Start with SMA for the first period (seed the EMA)
            # Note: bars are typically most recent first, so we need to reverse
            closes_chronological = closes[::-1]  # Oldest to newest
            
            sma = sum(closes_chronological[:period]) / period
            ema = sma
            
            # Calculate EMA for remaining data points
            for close in closes_chronological[period:]:
                ema = close * k + ema * (1 - k)
            
            scan_logger.debug(f"200 EMA | {symbol} | Calculated: ${ema:.2f} from {len(closes)} bars")
            return Decimal(str(round(ema, 2)))
            
        except Exception as e:
            scan_logger.debug(f"200 EMA | {symbol} | Error: {e}")
            return None
    
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
        # Wire Alpaca broker for HTB/ETB lookups
        try:
            from nexus2.adapters.broker.alpaca_broker import AlpacaBroker
            alpaca_broker = AlpacaBroker()
        except Exception as e:
            scan_logger.warning(f"Could not create AlpacaBroker for ETB checks: {e}")
            alpaca_broker = None
        _warrior_scanner_service = WarriorScannerService(alpaca_broker=alpaca_broker)
    return _warrior_scanner_service
