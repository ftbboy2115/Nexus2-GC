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
from typing import List, Optional, Dict, Any, Tuple

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
from nexus2.utils.time_utils import now_et, now_utc_factory, now_utc
from nexus2.db.telemetry_db import get_telemetry_session, WarriorScanResult as WarriorScanResultDB


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
    # "Easy to borrow + high float = choppy, fake-outs, shorts will flush it"
    etb_high_float_threshold: int = 35_000_000  # Reject ETB stocks with float > 35M
    
    # Pure High Float Disqualifier (does NOT rely on broker ETB data)
    # Ross Cameron prefers sub-20M float; anything >100M is choppy/institutionally-held
    # This triggers REGARDLESS of borrow status since Alpaca ETB data is unreliable
    high_float_threshold: int = 100_000_000  # Hard reject if float > 100M
    
    # Pillar 2: Relative Volume
    min_rvol: Decimal = Decimal("2.0")  # 2x minimum
    ideal_rvol: Decimal = Decimal("3.0")  # 3-5x ideal
    rvol_lookback_days: int = 10  # Days for average volume calculation
    
    # Pillar 3: Catalyst - handled via has_recent_catalyst()
    catalyst_lookback_days: int = 5
    
    # Pillar 4: Price Range
    min_price: Decimal = Decimal("1.50")
    max_price: Decimal = Decimal("40.0")  # Editable in settings
    
    # Pillar 5: Gap %
    min_gap: Decimal = Decimal("4.0")  # 4% minimum
    ideal_gap: Decimal = Decimal("5.0")  # 5-10% ideal
    
    # Additional Filters
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
    
    # Momentum Override Thresholds (Ross: "trade them, manage risk")
    # Bypass offering rejection for exceptional momentum (NPT, GRI, PAVM case studies)
    momentum_override_rvol: float = 50.0    # Override if RVOL >= this
    momentum_override_gap: float = 30.0     # AND gap_percent >= this
    momentum_override_size_reduction: float = 0.25  # Reduce position size by 25%
    
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
    
    # 200 EMA Resistance Check (Nexus supplementary filter, NOT a Ross-defined pillar)
    # NOTE: Ross defines exactly 5 Pillars. This is an additional Nexus technical check.
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
    
    # 52-week high for Blue Sky detection (no overhead resistance)
    year_high: Optional[Decimal] = None
    
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
# EVALUATION CONTEXT (for helper function extraction)
# =============================================================================

@dataclass
class EvaluationContext:
    """
    Context object passed between _evaluate_symbol helper functions.
    
    This enables clean extraction of the god function without excessive parameters.
    All intermediate state is stored here and passed between extraction helpers.
    """
    # Input parameters
    symbol: str
    name: str
    price: Decimal
    change_percent: Decimal
    verbose: bool
    
    # Settings reference
    settings: WarriorScanSettings = None
    
    # Session snapshot data
    session_volume: int = 0
    avg_volume: int = 0
    session_high: Decimal = Decimal("0")
    session_low: Decimal = Decimal("0")
    session_open: Optional[Decimal] = None
    last_price: Decimal = Decimal("0")
    yesterday_close: Optional[Decimal] = None
    
    # Float data
    float_shares: Optional[int] = None
    is_ideal_float: bool = False
    
    # RVOL data
    rvol: Decimal = Decimal("0")
    is_ideal_rvol: bool = False
    
    # Catalyst data
    has_catalyst: bool = False
    catalyst_type: str = "none"
    catalyst_desc: str = "No catalyst found"
    catalyst_confidence: float = 0.0
    catalyst_date: Optional[datetime] = None
    
    # Gap data
    gap_pct: Decimal = Decimal("0")
    opening_gap_pct: Optional[float] = None  # Gap at open (open vs prev close)
    live_gap_pct: Optional[float] = None     # Gap now (live price vs prev close)
    is_ideal_gap: bool = False
    
    # Chinese stock data
    is_chinese: bool = False
    country: Optional[str] = None
    
    # Borrow status
    hard_to_borrow: bool = False
    easy_to_borrow: bool = True
    
    # Reverse split data
    is_reverse_split: bool = False
    split_date: Optional[str] = None
    split_ratio: Optional[str] = None
    
    # 200 EMA data
    ema_200_value: Optional[Decimal] = None
    room_to_ema_pct: Optional[float] = None
    
        
    # Former runner
    is_former_runner: bool = False
    
    # Momentum override (Ross: "trade them, manage risk" for offering stocks)
    momentum_override: bool = False
    position_size_multiplier: float = 1.0


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
        self._cache: Dict[str, Tuple[Any, datetime]] = {}
    
    def _cached(self, key: str, ttl_seconds: int, fetch_fn) -> Any:
        """Return cached value if within TTL, otherwise fetch and cache."""
        now = datetime.now()
        if key in self._cache:
            value, cached_at = self._cache[key]
            if (now - cached_at).total_seconds() < ttl_seconds:
                scan_logger.debug(f"CACHE HIT | {key}")
                return value
        value = fetch_fn()
        self._cache[key] = (value, now)
        scan_logger.debug(f"CACHE MISS | {key}")
        return value
    
    def _write_scan_result_to_db(
        self,
        symbol: str,
        passed: bool,
        ctx: Optional['EvaluationContext'] = None,
        candidate: Optional['WarriorCandidate'] = None,
        rejection_reason: Optional[str] = None,
    ):
        """
        Write scan result to telemetry DB for Data Explorer query.
        
        Args:
            symbol: Stock symbol
            passed: True if passed all pillars
            ctx: EvaluationContext with gap_pct, rvol, float_shares, catalyst_type
            candidate: WarriorCandidate (only for PASS, has quality_score)
            rejection_reason: Reason for rejection (only for FAIL)
        """
        try:
            with get_telemetry_session() as db:
                db.add(WarriorScanResultDB(
                    timestamp=now_utc(),  # IMPORTANT: Use now_utc() not datetime.now()
                    symbol=symbol,
                    result="PASS" if passed else "FAIL",
                    gap_pct=float(ctx.gap_pct) if ctx and ctx.gap_pct else None,
                    rvol=float(ctx.rvol) if ctx and ctx.rvol else None,
                    score=candidate.quality_score if candidate else None,
                    float_shares=ctx.float_shares if ctx else None,
                    reason=rejection_reason if not passed else None,
                    catalyst_type=ctx.catalyst_type if ctx else None,
                    # Extended telemetry columns
                    price=float(ctx.last_price) if ctx and ctx.last_price else None,
                    country=ctx.country if ctx else None,
                    ema_200=float(ctx.ema_200_value) if ctx and ctx.ema_200_value else None,
                    room_to_ema_pct=float(ctx.room_to_ema_pct) if ctx and ctx.room_to_ema_pct else None,
                    is_etb=str(ctx.easy_to_borrow) if ctx else None,
                    name=ctx.name if ctx else None,
                ))
                db.commit()
        except Exception as e:
            # Use module logger, not scan_logger (avoid cluttering scan logs)
            logging.getLogger(__name__).warning(f"Failed to write scan result to DB: {e}")
    
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
        
        # Polygon gainers first (real-time, $200/mo Advanced tier)
        try:
            polygon_gainers = self.market_data.polygon.get_gainers()
            scan_logger.info(f"POLYGON GAINERS | Found: {len(polygon_gainers)} stocks")
            for g in polygon_gainers:
                sym = g["symbol"]
                if sym not in seen:
                    seen.add(sym)
                    all_movers.append(g)
        except Exception as e:
            scan_logger.warning(f"POLYGON GAINERS | Error: {e}")
        
        # FMP gainers second (has name)
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
                    # Get previousClose from Polygon snapshot (was FMP)
                    snap = self.market_data.polygon.get_session_snapshot(symbol)
                    if not snap:
                        scan_logger.warning(f"GAP RECALC | {symbol}: Polygon snapshot returned None — skipping recalc")
                        continue
                    prev_close = snap["prev_close"]
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
                scan_logger.warning(f"GAP RECALC | {symbol}: Error - {e}")
        
        # Pre-filter by price and gap (Pillars 4 & 5)
        filtered_movers = [
            g for g in all_movers
            if g["price"] >= self.settings.min_price
            and g["price"] <= self.settings.max_price
            and g["change_percent"] >= self.settings.min_gap
        ]
        
        # Exclude ETFs
        etf_set = self._cached("etf_set", 86400, lambda: self.market_data.fmp.get_etf_symbols())
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
                and not self._is_likely_chinese(g.get("name", ""))
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
        
        Refactored to use extracted helper methods for maintainability.
        Each pillar check is now a separate method that modifies EvaluationContext.
        
        Returns:
            WarriorCandidate if passes all criteria, None otherwise
        """
        tracker = get_rejection_tracker()
        s = self.settings
        
        # Build evaluation context
        ctx = EvaluationContext(
            symbol=symbol,
            name=name,
            price=price,
            change_percent=change_percent,
            verbose=verbose,
            settings=s,
        )
        
        # Get session snapshot for volume and range data
        snapshot = self.market_data.build_session_snapshot(symbol)
        if not snapshot:
            tracker.record(
                symbol=symbol,
                scanner="warrior",
                reason=RejectionReason.SNAPSHOT_FAILED,
                details="Failed to build session snapshot",
            )
            scan_logger.info(f"FAIL | {symbol} | Gap:{change_percent:.1f}% | Reason: snapshot_failed")
            return None
        
        # Populate context from snapshot
        ctx.session_volume = snapshot["session_volume"]
        ctx.avg_volume = snapshot["avg_daily_volume"]
        ctx.session_high = Decimal(str(snapshot["session_high"]))
        ctx.session_low = Decimal(str(snapshot["session_low"]))
        ctx.session_open = Decimal(str(snapshot["session_open"])) if snapshot.get("session_open") else None
        ctx.last_price = Decimal(str(snapshot["last_price"]))
        ctx.yesterday_close = Decimal(str(snapshot["yesterday_close"])) if snapshot.get("yesterday_close") else None
        
        # =========================================================================
        # CHINESE STOCK CHECK (early exit if icebreaker not enabled)
        # =========================================================================
        if s.exclude_chinese_stocks:
            ctx.country = self._cached(f"country:{symbol}", 2592000, lambda: self._get_country(symbol))
            if self._is_likely_chinese(name, country=ctx.country):
                ctx.is_chinese = True
                if not s.chinese_icebreaker_enabled:
                    tracker.record(
                        symbol=symbol,
                        scanner="warrior",
                        reason=RejectionReason.COUNTRY_EXCLUDED,
                        details=f"Chinese/HK stock excluded (country={ctx.country})",
                    )
                    scan_logger.info(f"FAIL | {symbol} | Gap:{change_percent:.1f}% | Reason: chinese_stock | Country: {ctx.country}")
                    if verbose:
                        print(f"{symbol}: Rejected - Chinese/HK stock (country={ctx.country})")
                    self._write_scan_result_to_db(symbol, False, ctx, rejection_reason="chinese_stock")
                    return None
        
        # =========================================================================
        # PILLAR 1: Float
        # =========================================================================
        if self._check_float_pillar(ctx, tracker):
            return None
        
        # =========================================================================
        # PILLAR 2: Relative Volume
        # =========================================================================
        if self._calculate_rvol_pillar(ctx, tracker):
            return None
        
        # =========================================================================
        # PILLAR 3: Price (moved before catalyst - cheap check)
        # =========================================================================
        if self._check_price_pillar(ctx, tracker):
            return None
        
        # =========================================================================
        # PILLAR 4: Gap (moved before catalyst - cheap check)
        # =========================================================================
        if self._calculate_gap_pillar(ctx, tracker):
            return None
        
        # =========================================================================
        # PILLAR 5: Catalyst (expensive - moved after cheap numeric checks)
        # =========================================================================
        headlines = self.market_data.get_merged_headlines(
            symbol, 
            days=s.catalyst_lookback_days,
            alpaca_broker=self.alpaca_broker,
        )
        
        if self._evaluate_catalyst_pillar(ctx, tracker, headlines):
            return None
        
        # Run multi-model validation if enabled
        self._run_multi_model_catalyst_validation(ctx, headlines)
        
        # Run legacy AI fallback if multi-model disabled
        self._run_legacy_ai_fallback(ctx, headlines)
        
        # Final catalyst requirement check
        if s.require_catalyst and not ctx.has_catalyst:
            tracker.record(
                symbol=symbol,
                scanner="warrior",
                reason=RejectionReason.NO_CATALYST,
                details=ctx.catalyst_desc,
            )
            scan_logger.info(f"FAIL | {symbol} | Gap:{change_percent:.1f}% | RVOL:{ctx.rvol:.1f}x | Float: {_format_float(ctx.float_shares) if ctx.float_shares else '?'} | Reason: no_catalyst | {ctx.catalyst_desc}")
            if headlines:
                from nexus2.domain.automation.catalyst_classifier import log_headline_evaluation
                log_headline_evaluation(symbol, headlines, "FAIL", None)
            if verbose:
                print(f"{symbol}: Rejected - {ctx.catalyst_desc}")
            # Write FAIL to telemetry DB
            self._write_scan_result_to_db(symbol, False, ctx, rejection_reason="no_catalyst")
            return None
        
        # =========================================================================
        # DILUTION CHECK
        # =========================================================================
        if ctx.catalyst_desc:
            catalyst_lower = ctx.catalyst_desc.lower()
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
                    # Write FAIL to telemetry DB
                    self._write_scan_result_to_db(symbol, False, ctx, rejection_reason=f"dilution:{dilution_kw}")
                    return None
        

        
        # =========================================================================
        # 200 EMA CHECK (NOT a Ross-defined pillar, but a metric he uses)
        # NOTE: Ross defines exactly 5 Pillars. If below, he sees if there's room to run to the 200 EMA.
        # =========================================================================
        if self._check_200_ema(ctx, tracker):
            return None
        

        # =========================================================================
        # FORMER RUNNER CHECK (for score boost)
        # =========================================================================
        ctx.is_former_runner = self._cached(f"runner:{symbol}", 21600, lambda: self._is_former_runner(symbol))
        
        # =========================================================================
        # BORROW STATUS AND FLOAT DISQUALIFIERS
        # =========================================================================
        if self._check_borrow_and_float_disqualifiers(ctx, tracker):
            return None
        
        # =========================================================================
        # REVERSE SPLIT CHECK (for score bonus)
        # =========================================================================
        self._check_reverse_split(ctx)
        
        # =========================================================================
        # BUILD CANDIDATE
        # =========================================================================
        candidate = self._build_candidate(ctx)
        
        # =========================================================================
        # ICEBREAKER DECISION FOR CHINESE STOCKS
        # =========================================================================
        if ctx.is_chinese:
            score = candidate.quality_score
            if score >= s.high_quality_threshold:
                candidate.is_icebreaker = True
                scan_logger.info(
                    f"ICEBREAKER | {symbol} | Score: {score} >= {s.high_quality_threshold} | "
                    f"Chinese stock PASSES with 50% size"
                )
                if verbose:
                    print(f"🧊 {symbol}: ICEBREAKER - Chinese stock passes (score={score}, 50% size)")
            else:
                tracker.record(
                    symbol=symbol,
                    scanner="warrior",
                    reason=RejectionReason.COUNTRY_EXCLUDED,
                    details=f"Chinese stock, score {score} < {s.high_quality_threshold} threshold",
                )
                scan_logger.info(f"FAIL | {symbol} | Reason: chinese_low_score | Score: {score} < {s.high_quality_threshold}")
                if verbose:
                    print(f"{symbol}: Rejected - Chinese stock, score {score} too low")
                # Write FAIL to telemetry DB (candidate exists, includes score)
                self._write_scan_result_to_db(
                    symbol, False, ctx, candidate=candidate, 
                    rejection_reason=f"chinese_low_score:{score}"
                )
                return None
        
        # =========================================================================
        # FINAL LOGGING
        # =========================================================================
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
                    freshness_note = " 🔴+3"
                elif hours_old <= 12:
                    freshness_note = " 🟠+2"
                elif hours_old <= 24:
                    freshness_note = " 🟡+1"
            except Exception:
                pass
        
        if verbose:
            htb_note = " [HTB]" if ctx.hard_to_borrow else ""
            print(f"✅ {symbol}: Passed all 5 Pillars (score={candidate.quality_score}{freshness_note}){htb_note}")
        
        scan_logger.info(
            f"[PILLARS] PASS | {symbol} | Gap:{change_percent:.1f}% | Score: {candidate.quality_score}{freshness_note} | "
            f"Catalyst: {ctx.catalyst_type} | Float: {_format_float(ctx.float_shares) if ctx.float_shares else 'N/A'} | RVOL: {ctx.rvol:.1f}x"
        )
        
        from nexus2.domain.automation.catalyst_classifier import log_headline_evaluation
        log_headline_evaluation(symbol, [f"PILLARS pass: {ctx.catalyst_type}"], "PASS", ctx.catalyst_type)
        
        # Write PASS to telemetry DB
        self._write_scan_result_to_db(
            symbol=symbol,
            passed=True,
            ctx=ctx,
            candidate=candidate,
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
            bars = self.market_data.polygon.get_daily_bars(symbol, limit=90)
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
    
    # =========================================================================
    # EXTRACTED HELPERS (from _evaluate_symbol god function refactor)
    # =========================================================================
    
    def _check_float_pillar(
        self, ctx: EvaluationContext, tracker
    ) -> Optional[str]:
        """
        Pillar 1: Float check (<100M, ideal <20M).
        
        Returns rejection reason string if failed, None if passed.
        """
        ctx.float_shares = self._cached(f"float:{ctx.symbol}", 86400, lambda: self._get_float_shares(ctx.symbol))
        s = ctx.settings
        
        if ctx.float_shares is not None and ctx.float_shares > s.max_float:
            tracker.record(
                symbol=ctx.symbol,
                scanner="warrior",
                reason=RejectionReason.FLOAT_TOO_HIGH,
                values={"float": ctx.float_shares, "max": s.max_float},
            )
            scan_logger.info(
                f"FAIL | {ctx.symbol} | Gap:{ctx.change_percent:.1f}% | "
                f"Reason: float_too_high | Float: {_format_float(ctx.float_shares)} > {_format_float(s.max_float)}"
            )
            if ctx.verbose:
                print(f"{ctx.symbol}: Rejected - Float {ctx.float_shares:,} > {s.max_float:,}")
            self._write_scan_result_to_db(ctx.symbol, False, ctx, rejection_reason="float_too_high")
            return "float_too_high"
        
        ctx.is_ideal_float = ctx.float_shares is not None and ctx.float_shares < s.ideal_float
        return None
    
    def _calculate_rvol_pillar(
        self, ctx: EvaluationContext, tracker
    ) -> Optional[str]:
        """
        Pillar 2: Relative Volume (>2x, ideal 3-5x).
        Time-adjusted projection for pre-market and regular hours.
        
        Returns rejection reason string if failed, None if passed.
        """
        s = ctx.settings
        
        if ctx.avg_volume > 0:
            et_tz = pytz.timezone('America/New_York')
            current_et = datetime.now(et_tz)
            market_open_today = current_et.replace(hour=9, minute=30, second=0, microsecond=0)
            premarket_start_today = current_et.replace(hour=4, minute=0, second=0, microsecond=0)
            
            trading_minutes_per_day = 390
            
            if current_et > market_open_today:
                # Regular market hours
                minutes_since_open = (current_et - market_open_today).total_seconds() / 60
                time_factor = trading_minutes_per_day / max(minutes_since_open, 1)
                time_factor = min(time_factor, 20.0)
                projected_volume = Decimal(ctx.session_volume) * Decimal(str(time_factor))
                ctx.rvol = projected_volume / Decimal(ctx.avg_volume)
            else:
                # Pre-market
                minutes_since_premarket = max((current_et - premarket_start_today).total_seconds() / 60, 1)
                premarket_minutes = 330
                premarket_factor = premarket_minutes / minutes_since_premarket
                premarket_factor = min(premarket_factor, 50.0)
                projected_premarket_volume = Decimal(ctx.session_volume) * Decimal(str(premarket_factor))
                daily_equivalent_factor = 10.0
                projected_daily = projected_premarket_volume * Decimal(str(daily_equivalent_factor))
                ctx.rvol = projected_daily / Decimal(ctx.avg_volume)
        else:
            ctx.rvol = Decimal("0")
        
        if ctx.rvol < s.min_rvol:
            tracker.record(
                symbol=ctx.symbol,
                scanner="warrior",
                reason=RejectionReason.RVOL_TOO_LOW,
                values={"rvol": round(float(ctx.rvol), 2), "min": float(s.min_rvol)},
            )
            scan_logger.info(
                f"FAIL | {ctx.symbol} | Gap:{ctx.change_percent:.1f}% | RVOL:{ctx.rvol:.1f}x | "
                f"Float: {_format_float(ctx.float_shares) if ctx.float_shares else '?'} | "
                f"Reason: rvol_too_low | RVOL: {ctx.rvol:.1f}x < {s.min_rvol}x"
            )
            if ctx.verbose:
                print(f"{ctx.symbol}: Rejected - RVOL {ctx.rvol:.1f}x < {s.min_rvol}x")
            self._write_scan_result_to_db(ctx.symbol, False, ctx, rejection_reason="rvol_too_low")
            return "rvol_too_low"
        
        ctx.is_ideal_rvol = ctx.rvol >= s.ideal_rvol
        return None
    
    def _evaluate_catalyst_pillar(
        self, ctx: EvaluationContext, tracker, headlines: List[str]
    ) -> Optional[str]:
        """
        Pillar 3: Catalyst evaluation (news/earnings/former runner).
        
        Handles: classifier, AI validation, headline cache, negative catalysts.
        Returns rejection reason string if failed, None if passed.
        """
        s = ctx.settings
        classifier = get_classifier()
        
        # Check headlines with classifier (confidence-based)
        if headlines:
            if ctx.verbose:
                print(f"[Catalyst Debug] {ctx.symbol}: Found {len(headlines)} headlines")
                for i, h in enumerate(headlines[:2]):
                    print(f"[Catalyst Debug] {ctx.symbol}: [{i+1}] {h[:80]}...")
            
            has_positive, best_type, best_headline = classifier.has_positive_catalyst(headlines)
            if has_positive and best_type:
                match = classifier.classify(best_headline)
                ctx.catalyst_confidence = match.confidence
                
                if ctx.verbose:
                    print(f"[Catalyst Debug] {ctx.symbol}: type={best_type}, conf={ctx.catalyst_confidence:.2f}")
                
                if ctx.catalyst_confidence >= 0.6:
                    ctx.has_catalyst = True
                    ctx.catalyst_type = best_type
                    ctx.catalyst_desc = best_headline[:80] if best_headline else ""
                    # Get publish date for freshness scoring
                    news_with_dates = self.market_data.fmp.get_news_with_dates(
                        ctx.symbol, days=s.catalyst_lookback_days
                    )
                    for headline, pub_date in news_with_dates:
                        if headline == best_headline or headline[:50] == best_headline[:50]:
                            ctx.catalyst_date = pub_date
                            break
                else:
                    ctx.catalyst_desc = f"Weak catalyst (confidence {ctx.catalyst_confidence:.1f})"
            
            # Check for negative catalysts
            has_negative, neg_type, neg_headline = classifier.has_negative_catalyst(headlines)
            if has_negative:
                should_bypass = False
                
                if s.allow_offering_for_reverse_splits and neg_type == "offering":
                    try:
                        from nexus2.domain.automation.reverse_split_service import get_reverse_split_service
                        rs_service = get_reverse_split_service()
                        rs_record = rs_service.is_recent_reverse_split(ctx.symbol)
                        if rs_record:
                            ctx.is_reverse_split = True
                            if ctx.has_catalyst and ctx.catalyst_type not in ("none", "", None):
                                should_bypass = True
                                scan_logger.info(
                                    f"🔄 BYPASS | {ctx.symbol} | RS+Offering allowed | "
                                    f"RS: {rs_record.date} ({rs_record.ratio}) | "
                                    f"Catalyst: {ctx.catalyst_type}"
                                )
                    except Exception as e:
                        scan_logger.debug(f"[RS Check] {ctx.symbol}: Error - {e}")
                
                # Momentum Override - Ross's "trade them, manage risk" philosophy
                # Bypass offering rejection for exceptional momentum (RVOL >= 50x AND gap >= 30%)
                if not should_bypass and neg_type in ("offering", "shelf_registration"):
                    if ctx.rvol >= s.momentum_override_rvol and ctx.change_percent >= s.momentum_override_gap:
                        should_bypass = True
                        ctx.momentum_override = True
                        ctx.position_size_multiplier = 1.0 - s.momentum_override_size_reduction
                        scan_logger.warning(
                            f"⚡ MOMENTUM_OVERRIDE | {ctx.symbol} | "
                            f"RVOL:{ctx.rvol:.0f}x >= {s.momentum_override_rvol:.0f} | "
                            f"Gap:{ctx.change_percent:.1f}% >= {s.momentum_override_gap:.0f}% | "
                            f"Type: {neg_type} | Size reduced by {s.momentum_override_size_reduction*100:.0f}%"
                        )
                
                if not should_bypass:
                    tracker.record(
                        symbol=ctx.symbol,
                        scanner="warrior",
                        reason=RejectionReason.CATALYST_DILUTION,
                        details=f"Negative catalyst: {neg_type} - {neg_headline[:50]}",
                    )
                    scan_logger.info(
                        f"FAIL | {ctx.symbol} | Gap:{ctx.change_percent:.1f}% | RVOL:{ctx.rvol:.1f}x | "
                        f"Float: {_format_float(ctx.float_shares) if ctx.float_shares else '?'} | "
                        f"Reason: negative_catalyst | Type: {neg_type}"
                    )
                    if ctx.verbose:
                        print(f"{ctx.symbol}: Rejected - Negative catalyst: {neg_type}")
                    self._write_scan_result_to_db(ctx.symbol, False, ctx, rejection_reason=f"negative_catalyst:{neg_type}")
                    return "negative_catalyst"
        
        # Check for recent earnings as backup
        if not ctx.has_catalyst:
            has_earnings, earnings_date = self.market_data.fmp.has_recent_earnings(
                ctx.symbol, days=s.catalyst_lookback_days
            )
            if has_earnings:
                ctx.has_catalyst = True
                ctx.catalyst_type = "earnings"
                ctx.catalyst_desc = f"Earnings {earnings_date}"
                ctx.catalyst_confidence = 0.9
                from nexus2.domain.automation.catalyst_classifier import log_headline_evaluation
                log_headline_evaluation(ctx.symbol, [f"Recent earnings on {earnings_date}"], "PASS", "earnings")
        
        # Check former runner
        if s.require_catalyst and not ctx.has_catalyst and s.include_former_runners:
            if self._is_former_runner(ctx.symbol):
                ctx.has_catalyst = True
                ctx.catalyst_type = "former_runner"
                ctx.catalyst_desc = "History of big moves"
                ctx.catalyst_confidence = 0.7
        
        return None  # Catalyst check is handled separately with require_catalyst
    
    def _run_multi_model_catalyst_validation(
        self, ctx: EvaluationContext, headlines: List[str]
    ) -> None:
        """
        Run sync dual catalyst validation (HeadlineCache + Regex + Flash-Lite).
        Modifies ctx in place with catalyst results.
        """
        s = ctx.settings
        if not headlines or not s.enable_multi_model_comparison:
            return
        
        headline_cache = get_headline_cache()
        
        # Check cache first
        cached_valid, cached_type = headline_cache.has_valid_catalyst(ctx.symbol)
        if cached_valid and not ctx.has_catalyst:
            ctx.has_catalyst = True
            ctx.catalyst_type = f"cached_{cached_type}"
            ctx.catalyst_desc = f"Cached: {cached_type}"
            ctx.catalyst_confidence = 0.85
            from nexus2.domain.automation.catalyst_classifier import log_headline_evaluation
            log_headline_evaluation(ctx.symbol, [f"Cache hit: {cached_type}"], "PASS", cached_type)
            if ctx.verbose:
                print(f"[Headline Cache] {ctx.symbol}: HIT - valid catalyst from cache ({cached_type})")
            return
        
        # Filter to new headlines
        new_headlines = headline_cache.get_new_headlines(ctx.symbol, headlines)
        
        if new_headlines and not ctx.has_catalyst:
            multi_validator = get_multi_validator()
            classifier = get_classifier()
            
            # Build headline→URL lookup from FMP (for logging with URLs)
            headline_url_map = {}
            try:
                news_with_urls = self.market_data.fmp.get_headlines_with_urls(
                    ctx.symbol, days=ctx.settings.catalyst_lookback_days
                )
                for item in news_with_urls:
                    headline_url_map[item.get("headline", "")] = item.get("url", "")
            except Exception:
                pass  # URL lookup is optional, proceed without if it fails
            
            for headline in new_headlines[:3]:
                try:
                    regex_match = classifier.classify(headline)
                    regex_valid = regex_match.is_positive and regex_match.confidence >= 0.6
                    regex_type_h = regex_match.catalyst_type if regex_valid else None
                    
                    # Look up URL for this headline
                    article_url = headline_url_map.get(headline)
                    
                    final_valid, final_type, _, flash_passed, method = multi_validator.validate_sync(
                        headline=headline,
                        symbol=ctx.symbol,
                        regex_passed=regex_valid,
                        regex_type=regex_type_h,
                        article_url=article_url,
                    )
                    
                    headline_cache.add(
                        symbol=ctx.symbol,
                        headline=headline,
                        is_valid=final_valid,
                        catalyst_type=final_type,
                        regex_passed=regex_valid,
                        flash_passed=flash_passed,
                        method=method,
                    )
                    
                    if final_valid and not ctx.has_catalyst:
                        ctx.has_catalyst = True
                        ctx.catalyst_type = final_type
                        ctx.catalyst_desc = f"{method}: {headline[:50]}"
                        ctx.catalyst_confidence = 0.85
                        from nexus2.domain.automation.catalyst_classifier import log_headline_evaluation
                        log_headline_evaluation(ctx.symbol, new_headlines, "PASS", final_type)
                        break
                        
                except Exception as e:
                    if ctx.verbose:
                        print(f"[Catalyst Debug] {ctx.symbol}: Validation error - {e}")
                    headline_cache.add(
                        symbol=ctx.symbol,
                        headline=headline,
                        is_valid=False,
                        catalyst_type=None,
                        regex_passed=False,
                        flash_passed=None,
                        method="error",
                    )
    
    def _run_legacy_ai_fallback(
        self, ctx: EvaluationContext, headlines: List[str]
    ) -> None:
        """
        Legacy single-model AI fallback when multi-model is disabled.
        Modifies ctx in place.
        """
        s = ctx.settings
        if not headlines or not s.use_ai_catalyst_fallback or ctx.has_catalyst:
            return
        if s.enable_multi_model_comparison:
            return  # Multi-model takes precedence
        
        catalyst_cache = get_catalyst_cache()
        cached = catalyst_cache.get(ctx.symbol)
        if cached:
            if not ctx.has_catalyst and cached.is_valid:
                ctx.has_catalyst = True
                ctx.catalyst_type = f"cached_{cached.catalyst_type}"
                ctx.catalyst_desc = cached.description
                ctx.catalyst_confidence = 0.8
        else:
            try:
                ai_validator = get_ai_validator()
                ai_valid, ai_type, ai_headline = ai_validator.validate_headlines(headlines, ctx.symbol)
                catalyst_cache.set(
                    ctx.symbol, ai_valid, ai_type, 
                    ai_headline[:80] if ai_headline else f"AI: {ai_type}"
                )
                if ai_valid:
                    ctx.has_catalyst = True
                    ctx.catalyst_type = f"ai_{ai_type}"
                    ctx.catalyst_desc = f"AI: {ai_headline}" if ai_headline else f"AI: {ai_type}"
                    ctx.catalyst_confidence = 0.8
            except Exception as e:
                if ctx.verbose:
                    print(f"[Catalyst Debug] {ctx.symbol}: AI fallback error - {e}")
    
    def _check_price_pillar(
        self, ctx: EvaluationContext, tracker
    ) -> Optional[str]:
        """
        Pillar 4: Price range check ($1.50 - $20).
        
        Returns rejection reason string if failed, None if passed.
        """
        s = ctx.settings
        if ctx.price < s.min_price or ctx.price > s.max_price:
            tracker.record(
                symbol=ctx.symbol,
                scanner="warrior",
                reason=RejectionReason.PRICE_OUT_OF_RANGE,
                values={"price": float(ctx.price), "min": float(s.min_price), "max": float(s.max_price)},
            )
            self._write_scan_result_to_db(ctx.symbol, False, ctx, rejection_reason="price_out_of_range")
            scan_logger.info(f"REJECT {ctx.symbol} | price_out_of_range | price=${ctx.price} range=[${s.min_price}-${s.max_price}]")
            return "price_out_of_range"
        return None
    
    def _calculate_gap_pillar(
        self, ctx: EvaluationContext, tracker
    ) -> Optional[str]:
        """
        Pillar 5: Gap % check (>4%, ideal 5-10%).
        
        Dual-gate (Option C): Pass if EITHER opening gap OR live gap >= min_gap.
        - Opening gap = session_open vs yesterday_close (the actual gap at open)
        - Live gap = last_price vs yesterday_close (current gap, may have faded)
        
        This prevents valid gappers from being rejected just because 
        their live price faded after the gap-up.
        
        Returns rejection reason string if failed, None if passed.
        """
        s = ctx.settings
        
        # Calculate opening gap (open price vs yesterday close)
        if ctx.session_open and ctx.yesterday_close and ctx.yesterday_close > 0:
            ctx.opening_gap_pct = float(((ctx.session_open - ctx.yesterday_close) / ctx.yesterday_close) * 100)
        else:
            ctx.opening_gap_pct = float(ctx.change_percent)
        
        # Calculate live gap (current price vs yesterday close)
        if ctx.yesterday_close and ctx.yesterday_close > 0:
            ctx.live_gap_pct = float(((ctx.last_price - ctx.yesterday_close) / ctx.yesterday_close) * 100)
        else:
            ctx.live_gap_pct = float(ctx.change_percent)
        
        # Use the HIGHER of opening gap or live gap for the pillar check (Option C dual-gate)
        # This ensures a stock that gapped 30% but faded to 3% still passes on opening gap
        ctx.gap_pct = Decimal(str(max(ctx.opening_gap_pct, ctx.live_gap_pct)))
        
        if ctx.gap_pct < s.min_gap:
            tracker.record(
                symbol=ctx.symbol,
                scanner="warrior",
                reason=RejectionReason.GAP_TOO_LOW,
                values={"gap": round(float(ctx.gap_pct), 1), "min": float(s.min_gap)},
            )
            if ctx.verbose:
                print(f"{ctx.symbol}: Rejected - Gap {ctx.gap_pct:.1f}% < {s.min_gap}% (open={ctx.opening_gap_pct:.1f}%, live={ctx.live_gap_pct:.1f}%)")
            self._write_scan_result_to_db(ctx.symbol, False, ctx, rejection_reason="gap_too_low")
            scan_logger.info(
                f"REJECT {ctx.symbol} | gap_too_low | "
                f"opening_gap={ctx.opening_gap_pct:.1f}% live_gap={ctx.live_gap_pct:.1f}% min={s.min_gap}%"
            )
            return "gap_too_low"
        
        ctx.is_ideal_gap = ctx.gap_pct >= s.ideal_gap
        
        # Log when dual-gate saved a stock from rejection
        if ctx.live_gap_pct < float(s.min_gap) <= ctx.opening_gap_pct:
            scan_logger.info(
                f"DUAL-GATE SAVE | {ctx.symbol} | "
                f"Live gap {ctx.live_gap_pct:.1f}% would have been rejected, "
                f"but opening gap {ctx.opening_gap_pct:.1f}% passes"
            )
        
        return None
    
    # _check_dollar_volume removed — dead code per scanner audit (2026-02-13)
    
    def _check_200_ema(
        self, ctx: EvaluationContext, tracker
    ) -> Optional[str]:
        """
        200 EMA resistance check. Reject if 200 EMA is too close overhead.
        (Ross uses 200 EMA as a key resistance level, but it's not one of the 5 Pillars)
        
        Returns rejection reason string if failed, None if passed.
        """
        s = ctx.settings
        if not s.check_200_ema:
            return None
        
        ctx.ema_200_value = self._cached(f"ema200:{ctx.symbol}", 21600, lambda: self._get_200_ema(ctx.symbol))
        if ctx.ema_200_value and ctx.ema_200_value > 0 and float(ctx.last_price) > 0:
            ctx.room_to_ema_pct = ((float(ctx.last_price) - float(ctx.ema_200_value)) / float(ctx.ema_200_value)) * 100
            
            # Reject if price is below EMA but not far enough below (e.g., -10% = too close to ceiling)
            # Negative % means price is below EMA; we want at least -15% room
            if ctx.room_to_ema_pct < 0 and ctx.room_to_ema_pct > -s.min_room_to_200ema_pct:
                tracker.record(
                    symbol=ctx.symbol,
                    scanner="warrior",
                    reason=RejectionReason.EMA_200_CEILING,
                    values={
                        "price": round(float(ctx.last_price), 2),
                        "ema_200": round(float(ctx.ema_200_value), 2),
                        "room_pct": round(ctx.room_to_ema_pct, 1),
                        "min_room": s.min_room_to_200ema_pct,
                    },
                )
                scan_logger.info(
                    f"FAIL | {ctx.symbol} | Gap:{ctx.gap_pct:.1f}% | RVOL:{ctx.rvol:.1f}x | "
                    f"Reason: ema_200_ceiling | Price: ${ctx.last_price:.2f} | "
                    f"200 EMA: ${ctx.ema_200_value:.2f} ({ctx.room_to_ema_pct:.1f}% room < {s.min_room_to_200ema_pct}%)"
                )
                if ctx.verbose:
                    print(
                        f"{ctx.symbol}: Rejected - 200 EMA ${ctx.ema_200_value:.2f} is only "
                        f"{ctx.room_to_ema_pct:.1f}% above price (need {s.min_room_to_200ema_pct}%)"
                    )
                self._write_scan_result_to_db(ctx.symbol, False, ctx, rejection_reason="ema_200_ceiling")
                return "ema_200_ceiling"
        return None
    
    def _check_borrow_and_float_disqualifiers(
        self, ctx: EvaluationContext, tracker
    ) -> Optional[str]:
        """
        Check HTB/ETB status and high-float disqualifiers.
        
        Returns rejection reason string if failed, None if passed.
        """
        s = ctx.settings
        
        # Get borrow status from Alpaca
        if self.alpaca_broker:
            try:
                asset_info = self.alpaca_broker.get_asset_info(ctx.symbol)
                ctx.hard_to_borrow = asset_info.get("hard_to_borrow", False)
                ctx.easy_to_borrow = asset_info.get("easy_to_borrow", True)
                scan_logger.debug(f"BORROW CHECK | {ctx.symbol} | HTB={ctx.hard_to_borrow}, ETB={ctx.easy_to_borrow}")
                if ctx.hard_to_borrow:
                    scan_logger.info(f"HTB BONUS | {ctx.symbol} is Hard-to-Borrow (+1 score)")
            except Exception as e:
                scan_logger.debug(f"Could not get HTB status for {ctx.symbol}: {e}")
        else:
            scan_logger.debug(f"BROKER MISSING | {ctx.symbol} | No alpaca_broker wired")
        
        # Pure high float disqualifier
        if ctx.float_shares and ctx.float_shares > s.high_float_threshold:
            tracker.record(
                symbol=ctx.symbol,
                scanner="warrior",
                reason=RejectionReason.ETB_HIGH_FLOAT,
                values={"float": ctx.float_shares, "threshold": s.high_float_threshold},
            )
            scan_logger.info(
                f"FAIL | {ctx.symbol} | Reason: high_float | "
                f"{_format_float(ctx.float_shares)} float > {_format_float(s.high_float_threshold)} threshold"
            )
            if ctx.verbose:
                print(f"{ctx.symbol}: Rejected - High Float ({_format_float(ctx.float_shares)} > {_format_float(s.high_float_threshold)})")
            self._write_scan_result_to_db(ctx.symbol, False, ctx, rejection_reason="high_float")
            return "high_float"
        
        # ETB + medium-high float disqualifier
        if ctx.easy_to_borrow and ctx.float_shares and ctx.float_shares > s.etb_high_float_threshold:
            tracker.record(
                symbol=ctx.symbol,
                scanner="warrior",
                reason=RejectionReason.ETB_HIGH_FLOAT,
                values={"float": ctx.float_shares, "threshold": s.etb_high_float_threshold, "etb": True},
            )
            scan_logger.info(
                f"FAIL | {ctx.symbol} | Reason: etb_high_float | "
                f"ETB with {_format_float(ctx.float_shares)} float > {_format_float(s.etb_high_float_threshold)}"
            )
            if ctx.verbose:
                print(f"{ctx.symbol}: Rejected - ETB + High Float ({_format_float(ctx.float_shares)} > {_format_float(s.etb_high_float_threshold)})")
            self._write_scan_result_to_db(ctx.symbol, False, ctx, rejection_reason="etb_high_float")
            return "etb_high_float"
        
        return None
    
    def _check_reverse_split(self, ctx: EvaluationContext) -> None:
        """
        Check reverse split status for score bonus.
        Modifies ctx in place.
        """
        try:
            from nexus2.domain.automation.reverse_split_service import get_reverse_split_service
            rsplit_service = get_reverse_split_service()
            rsplit_record = rsplit_service.is_recent_reverse_split(ctx.symbol)
            if rsplit_record:
                ctx.is_reverse_split = True
                ctx.split_date = rsplit_record.date
                ctx.split_ratio = rsplit_record.ratio
                scan_logger.info(
                    f"RSPLIT BONUS | {ctx.symbol} has recent reverse split "
                    f"({ctx.split_ratio} on {ctx.split_date}) +2 score"
                )
        except Exception as e:
            scan_logger.debug(f"Could not check reverse split for {ctx.symbol}: {e}")
    
    def _build_candidate(self, ctx: EvaluationContext) -> WarriorCandidate:
        """
        Build the final WarriorCandidate from evaluation context.
        """
        return WarriorCandidate(
            symbol=ctx.symbol,
            name=ctx.name,
            float_shares=ctx.float_shares,
            relative_volume=ctx.rvol,
            catalyst_type=ctx.catalyst_type,
            catalyst_description=ctx.catalyst_desc,
            catalyst_date=ctx.catalyst_date,
            price=Decimal(str(ctx.last_price)),
            gap_percent=Decimal(str(ctx.gap_pct)),
            is_ideal_float=ctx.is_ideal_float,
            is_ideal_rvol=ctx.is_ideal_rvol,
            is_ideal_gap=ctx.is_ideal_gap,
            is_former_runner=ctx.is_former_runner,
            hard_to_borrow=ctx.hard_to_borrow,
            easy_to_borrow=ctx.easy_to_borrow,
            is_reverse_split=ctx.is_reverse_split,
            split_date=ctx.split_date,
            split_ratio=ctx.split_ratio,
            session_high=Decimal(str(ctx.session_high)),
            session_low=Decimal(str(ctx.session_low)),
            session_volume=ctx.session_volume,
            avg_volume=ctx.avg_volume,
            ema_200=ctx.ema_200_value,
            room_to_200_ema_pct=ctx.room_to_ema_pct,
            scanned_at=now_et(),
        )


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
