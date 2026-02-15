"""
Unified Market Data Provider

Combines FMP (primary) and Alpaca (intraday/fallback) into a single interface.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Dict, List, Optional

from nexus2.adapters.market_data.protocol import (
    OHLCV,
    Quote,
    StockInfo,
)
from nexus2.adapters.market_data.fmp_adapter import FMPAdapter, FMPConfig, get_fmp_adapter
from nexus2.adapters.market_data.alpaca_adapter import AlpacaAdapter, AlpacaConfig
from nexus2.adapters.market_data.polygon_adapter import PolygonAdapter, get_polygon_adapter


@dataclass
class UnifiedConfig:
    """Configuration for unified market data."""
    fmp_config: Optional[FMPConfig] = None
    alpaca_config: Optional[AlpacaConfig] = None
    use_fmp_singleton: bool = True  # Use shared FMP for rate limiting


class UnifiedMarketData:
    """
    Unified Market Data Provider.
    
    Strategy:
    - Polygon for real-time quotes (fastest, streaming capable)
    - FMP for screening, fundamentals, float data, daily data
    - Alpaca for intraday bars and fallback quotes
    - Schwab for NBBO tie-breaker
    - Automatic fallback between providers
    """
    
    def __init__(self, config: Optional[UnifiedConfig] = None):
        config = config or UnifiedConfig()
        
        # Use singleton FMP adapter to share rate limiting across all services
        if config.use_fmp_singleton:
            self.fmp = get_fmp_adapter()
        else:
            self.fmp = FMPAdapter(config.fmp_config)
        
        self.alpaca = AlpacaAdapter(config.alpaca_config)
        
        # Polygon adapter (singleton for quote consistency)
        self.polygon = get_polygon_adapter()
    
    # =========================================================================
    # Combined Methods
    # =========================================================================
    
    def get_quote(self, symbol: str) -> Optional[Quote]:
        """
        Get quote with 3-source cross-validation.
        
        Priority:
        1. If all sources agree (within 10%), use Alpaca (real-time)
        2. If Alpaca and FMP diverge >20%, use Schwab as tie-breaker
        3. If Schwab not available, prefer Schwab > FMP > Alpaca based on availability
        
        This prevents acting on stale/corrupt data from any single source.
        All quote checks are logged to the audit service for reliability tracking.
        
        NOTE: During simulation mode, returns MockBroker price to avoid external API calls.
        """
        import logging
        from decimal import Decimal
        logger = logging.getLogger(__name__)
        
        # Skip external API calls during simulation mode - use MockBroker price
        try:
            from nexus2.api.routes.warrior_sim_routes import get_warrior_sim_broker
            sim_broker = get_warrior_sim_broker()
            if sim_broker is not None:
                price = sim_broker.get_price(symbol)
                if price:
                    return Quote(
                        symbol=symbol,
                        price=Decimal(str(price)),
                        change=Decimal("0"),
                        change_percent=Decimal("0"),
                        volume=0,
                        timestamp=None,
                    )
                return None
        except Exception:
            pass  # If import fails, continue with normal path
        
        # Check if symbol is blacklisted (due to prior divergence issue)
        try:
            from nexus2.domain.audit.symbol_blacklist import get_symbol_blacklist
            if get_symbol_blacklist().is_blacklisted(symbol):
                logger.info(f"[Quote] {symbol}: Skipped - on divergence blacklist")
                return None
        except Exception:
            pass  # Blacklist not critical, continue if import fails
        
        # Collect quotes - use lazy evaluation to avoid unnecessary API calls
        # Polygon is primary (unlimited calls, fastest), only call others if needed
        polygon_quote = self.polygon.get_quote(symbol) if hasattr(self, 'polygon') else None
        polygon_price = float(polygon_quote.price) if polygon_quote and polygon_quote.price > 0 else None
        
        # If Polygon returns a valid quote, we may skip Alpaca/FMP to save rate limits
        # Only fetch from other sources for validation or if Polygon fails
        alpaca_quote = None
        alpaca_price = None
        fmp_quote = None
        fmp_price = None
        
        # Get Schwab for tie-breaking (real-time pre-market bid/ask)
        schwab_price = None
        schwab_unavailable = False
        try:
            from nexus2.adapters.market_data.schwab_adapter import get_schwab_adapter
            schwab = get_schwab_adapter()
            if schwab.is_authenticated():
                schwab_data = schwab.get_quote(symbol)
                if schwab_data and schwab_data.get("price") and schwab_data["price"] > 0:
                    schwab_price = float(schwab_data["price"])
            else:
                schwab_unavailable = True
                logger.info(f"[Quote] {symbol}: Schwab unavailable (tokens expired - re-authenticate)")
        except Exception as e:
            schwab_unavailable = True
            logger.warning(f"[Quote] {symbol}: Schwab lookup failed: {e}")
        
        # If Polygon and Schwab agree (within 10%), no need for other sources
        if polygon_price and schwab_price:
            price_diff = abs(polygon_price - schwab_price) / min(polygon_price, schwab_price) * 100
            if price_diff <= 10:
                # They agree - use Polygon, skip Alpaca/FMP rate limits
                logger.debug(f"[Quote] {symbol}: Polygon+Schwab agree ({price_diff:.1f}%) - skipping Alpaca/FMP")
                # Inline audit logging for early return
                try:
                    from nexus2.domain.audit.quote_audit_service import get_quote_audit_service, determine_time_window
                    audit = get_quote_audit_service()
                    audit.log_quote_check(
                        symbol=symbol,
                        sources_dict={"Polygon": polygon_price, "Schwab": schwab_price},
                        selected_source="Polygon",
                        divergence_pct=price_diff,
                        time_window=determine_time_window(),
                    )
                except Exception:
                    pass
                return polygon_quote
        
        # Need validation - fetch from Alpaca and FMP (may hit rate limits)
        alpaca_quote = self.alpaca.get_quote(symbol)
        fmp_quote = self.fmp.get_quote(symbol)
        alpaca_price = float(alpaca_quote.price) if alpaca_quote and alpaca_quote.price > 0 else None
        fmp_price = float(fmp_quote.price) if fmp_quote and fmp_quote.price > 0 else None
        
        # Build price dict for comparison and audit logging
        prices = {}
        if polygon_price: prices["Polygon"] = polygon_price
        if alpaca_price: prices["Alpaca"] = alpaca_price
        if fmp_price: prices["FMP"] = fmp_price
        if schwab_price: prices["Schwab"] = schwab_price
        
        # Helper to log audit and return result
        def _log_and_return(result_quote: Optional[Quote], selected_source: str, divergence: float) -> Optional[Quote]:
            try:
                from nexus2.domain.audit.quote_audit_service import get_quote_audit_service, determine_time_window
                from nexus2.utils.time_utils import is_market_hours
                
                audit = get_quote_audit_service()
                time_window = determine_time_window()
                
                # Track which FMP endpoint was used based on market hours
                # FMP uses aftermarket-quote during extended hours, regular quote during market hours
                fmp_endpoint = "quote" if is_market_hours() else "aftermarket-quote"
                
                audit.log_quote_check(
                    symbol=symbol,
                    sources_dict={
                        "Polygon": polygon_price,
                        "Alpaca": alpaca_price,
                        "FMP": fmp_price,
                        "Schwab": schwab_price,
                    },
                    selected_source=selected_source,
                    divergence_pct=divergence,
                    time_window=time_window,
                    fmp_endpoint=fmp_endpoint if fmp_price else None,
                )
            except Exception as e:
                logger.debug(f"[Quote] {symbol}: Audit logging failed: {e}")
            return result_quote
        
        if not prices:
            logger.warning(f"[Quote] {symbol}: No valid quotes from any source!")
            # Log failed quotes to audit for observability
            try:
                from nexus2.domain.audit.quote_audit_service import get_quote_audit_service, determine_time_window
                audit = get_quote_audit_service()
                audit.log_quote_check(
                    symbol=symbol,
                    sources_dict={
                        "Polygon": None,
                        "Alpaca": None,
                        "FMP": None,
                        "Schwab": None,
                    },
                    selected_source="FAILED",
                    divergence_pct=0.0,
                    time_window=determine_time_window(),
                )
            except Exception:
                pass
            return None
        
        # If only one source, use it
        if len(prices) == 1:
            source, price = list(prices.items())[0]
            logger.debug(f"[Quote] {symbol}: Only {source} available (${price:.2f})")
            if source == "Polygon":
                return _log_and_return(polygon_quote, "Polygon", 0.0)
            if source == "Alpaca": 
                return _log_and_return(alpaca_quote, "Alpaca", 0.0)
            if source == "FMP": 
                return _log_and_return(fmp_quote, "FMP", 0.0)
            # Schwab returns dict, not Quote - convert it
            if source == "Schwab":
                schwab_quote = Quote(
                    symbol=symbol,
                    price=Decimal(str(schwab_price)),
                    change=Decimal("0"),
                    change_percent=Decimal("0"),
                    volume=0,
                    timestamp=None,
                )
                return _log_and_return(schwab_quote, "Schwab", 0.0)
        
        # Calculate max divergence between any two sources
        price_list = list(prices.values())
        min_price = min(price_list)
        max_price = max(price_list)
        divergence_pct = ((max_price - min_price) / min_price * 100) if min_price > 0 else 0
        
        # If all sources agree (within 20%), use Polygon as primary (fastest, includes pre-market)
        # Polygon Developer tier ($200/mo) includes real-time extended hours data
        if divergence_pct <= 20:
            if polygon_price:
                logger.debug(f"[Quote] {symbol}: Sources agree ({divergence_pct:.1f}% spread) - using Polygon")
                return _log_and_return(polygon_quote, "Polygon", divergence_pct)
            elif schwab_price:
                # Fallback to Schwab (accurate broker bid/ask)
                from nexus2.domain.audit.quote_audit_service import determine_time_window
                time_window = determine_time_window()
                logger.debug(f"[Quote] {symbol}: Polygon unavailable, using Schwab ({time_window})")
                schwab_quote = Quote(symbol=symbol, price=Decimal(str(schwab_price)), change=Decimal("0"), change_percent=Decimal("0"), volume=0, timestamp=None)
                return _log_and_return(schwab_quote, "Schwab", divergence_pct)
            elif alpaca_price:
                logger.debug(f"[Quote] {symbol}: Using Alpaca fallback")
                return _log_and_return(alpaca_quote, "Alpaca", divergence_pct)
            else:
                return _log_and_return(fmp_quote, "FMP", divergence_pct)
        
        # Major divergence - need to pick the best source based on market phase
        logger.warning(
            f"[Quote] {symbol}: DIVERGENCE! "
            f"Polygon=${polygon_price or 'N/A'}, Alpaca=${alpaca_price or 'N/A'}, FMP=${fmp_price or 'N/A'}, Schwab=${schwab_price or 'N/A'} "
            f"({divergence_pct:.1f}% spread)"
        )
        
        # Time-aware priority selection:
        # - Extended hours (pre/post market): Trust Polygon (real-time extended hours data)
        # - Regular hours: Trust Schwab (broker NBBO is most accurate)
        from nexus2.utils.time_utils import is_market_hours
        
        # Polygon-first always - maximizes $200/mo subscription value
        # Developer tier provides real-time consolidated quotes for ALL market phases
        if polygon_price:
            logger.info(f"[Quote] {symbol}: Using Polygon (${polygon_price:.2f}) - divergence, primary source")
            return _log_and_return(polygon_quote, "Polygon", divergence_pct)
        elif schwab_price:
            # Fallback to Schwab if Polygon unavailable
            logger.info(f"[Quote] {symbol}: Using Schwab (${schwab_price:.2f}) - Polygon unavailable")
            schwab_quote = Quote(
                symbol=symbol,
                price=Decimal(str(schwab_price)),
                change=Decimal("0"),
                change_percent=Decimal("0"),
                volume=0,
                timestamp=None,
            )
            return _log_and_return(schwab_quote, "Schwab", divergence_pct)
        
        # Fallback: median of available prices if primary sources unavailable
        if len(prices) >= 2:
            sorted_prices = sorted(price_list)
            median_price = sorted_prices[len(sorted_prices) // 2]
            # Find which source has the median price
            for source, price in prices.items():
                if price == median_price:
                    logger.info(f"[Quote] {symbol}: Using {source} (${price:.2f}) as median fallback")
                    if source == "Polygon":
                        return _log_and_return(polygon_quote, "Polygon", divergence_pct)
                    if source == "Alpaca": 
                        return _log_and_return(alpaca_quote, "Alpaca", divergence_pct)
                    if source == "FMP": 
                        return _log_and_return(fmp_quote, "FMP", divergence_pct)
        
        # Final fallback: FMP > Alpaca
        if fmp_price:
            return _log_and_return(fmp_quote, "FMP", divergence_pct)
        return _log_and_return(alpaca_quote, "Alpaca", divergence_pct)
    
    def get_quotes_batch(self, symbols: List[str]) -> Dict[str, Quote]:
        """Get quotes for multiple symbols - Polygon primary, FMP fallback."""
        # Try Polygon first (unlimited calls, fastest)
        if hasattr(self, 'polygon'):
            quotes = self.polygon.get_quotes_batch(symbols)
            if quotes and len(quotes) >= len(symbols) * 0.8:  # Got 80%+ of symbols
                return quotes
        # Fallback to FMP if Polygon failed or incomplete
        return self.fmp.get_quotes_batch(symbols)
    
    def get_daily_bars(
        self, 
        symbol: str, 
        limit: int = 60
    ) -> Optional[List[OHLCV]]:
        """
        Get daily bars, FMP primary, Alpaca fallback.
        """
        bars = self.fmp.get_daily_bars(symbol, limit)
        # Accept FMP data if we got at least 10 bars or half the requested limit
        min_bars = min(10, limit // 2) if limit > 0 else 10
        if bars and len(bars) >= min_bars:
            return bars
        return self.alpaca.get_daily_bars(symbol, limit)
    
    def get_intraday_bars(
        self, 
        symbol: str, 
        timeframe: str = "1Min",
        limit: int = 1000
    ) -> Optional[List[OHLCV]]:
        """Get intraday bars - Polygon primary, Alpaca fallback.
        
        NOTE: This is the SYNC general-purpose version.
        For Warrior engine (async + simulation mode), see:
        warrior_callbacks.py:create_get_intraday_bars()
        
        Returns OHLCV objects with Decimal prices.
        """
        # Polygon primary: Convert timeframe (e.g., "1Min" -> "1")
        polygon_tf = timeframe.replace("Min", "").replace("min", "")
        bars = self.polygon.get_intraday_bars(symbol, timeframe=polygon_tf, limit=limit)
        if bars and len(bars) >= 5:
            return bars
        # Alpaca fallback
        return self.alpaca.get_intraday_bars(symbol, timeframe, limit)
    
    def get_stock_info(self, symbol: str) -> Optional[StockInfo]:
        """Get stock info from FMP."""
        return self.fmp.get_stock_info(symbol)
    
    def get_prev_close(self, symbol: str) -> Optional[Decimal]:
        """Get previous close, FMP primary."""
        close = self.fmp.get_prev_close(symbol)
        if close:
            return close
        return self.alpaca.get_prev_close(symbol)
    
    def get_atr(self, symbol: str, period: int = 14) -> Optional[Decimal]:
        """Calculate ATR, FMP primary."""
        atr = self.fmp.get_atr(symbol, period)
        if atr:
            return atr
        return self.alpaca.get_atr(symbol, period)
    
    def get_sma(self, symbol: str, period: int) -> Optional[Decimal]:
        """Get SMA, FMP primary."""
        sma = self.fmp.get_sma(symbol, period)
        if sma:
            return sma
        return self.alpaca.get_sma(symbol, period)
    
    def get_ema(self, symbol: str, period: int) -> Optional[Decimal]:
        """Get EMA, FMP primary."""
        ema = self.fmp.get_ema(symbol, period)
        if ema:
            return ema
        return self.alpaca.get_ema(symbol, period)
    
    def get_adr_percent(self, symbol: str, period: int = 14) -> Optional[Decimal]:
        """
        Calculate Average Daily Range as percentage.
        
        ADR% = (Average of (High - Low)) / Close * 100
        """
        bars = self.get_daily_bars(symbol, limit=period + 5)
        if not bars or len(bars) < period:
            return None
        
        recent_bars = bars[-period:]
        ranges = [(b.high - b.low) for b in recent_bars]
        avg_range = sum(ranges) / len(ranges)
        
        last_close = bars[-1].close
        if last_close > 0:
            return (avg_range / last_close) * 100
        return None
    
    def get_opening_range(
        self,
        symbol: str,
        timeframe_minutes: int = 5,
        date: Optional[str] = None,
    ) -> Optional[tuple[Decimal, Decimal]]:
        """
        Get the opening range (high, low) for the first N minutes of trading.
        
        Used for EP tactical stop calculation.
        
        Args:
            symbol: Stock symbol
            timeframe_minutes: Opening range timeframe (1, 5, 15, 30)
            date: Date in YYYY-MM-DD format (defaults to today)
            
        Returns:
            (opening_range_high, opening_range_low) or None if unavailable
        """
        return self.fmp.get_opening_range(symbol, timeframe_minutes, date)
    
    def get_average_volume(self, symbol: str, period: int = 20) -> Optional[int]:
        """Get average volume over period."""
        bars = self.get_daily_bars(symbol, limit=period + 5)
        if not bars or len(bars) < period:
            return None
        
        recent_bars = bars[-period:]
        volumes = [b.volume for b in recent_bars]
        return int(sum(volumes) / len(volumes))
    
    def get_historical_bars(self, symbol: str, days: int = 60) -> Optional[List[OHLCV]]:
        """
        Get historical daily bars for affinity analysis.
        
        Alias for get_daily_bars, used by MA affinity callback.
        Returns OHLCV objects (not dicts) for backward compatibility.
        
        Args:
            symbol: Stock symbol
            days: Number of days of history
            
        Returns:
            List of OHLCV objects or None
        """
        return self.get_daily_bars(symbol, limit=days + 10)
    
    # =========================================================================
    # EP-Specific Methods
    # =========================================================================
    
    def build_session_snapshot(
        self,
        symbol: str,
        rvol_lookback: int = 50,
    ) -> Optional[Dict]:
        """
        Build EP session snapshot using Polygon (primary) or FMP (fallback).
        
        Uses Polygon snapshot for session OHLV and prev_close (single API call).
        Uses daily bars for avg volume and yesterday close (needed for RVOL).
        
        Returns:
            {
                "yesterday_close": Decimal,
                "avg_daily_volume": int,
                "session_open": Decimal,
                "session_high": Decimal,
                "session_low": Decimal,
                "last_price": Decimal,
                "session_volume": int,
            }
        """
        # --- Session data: Try Polygon snapshot first (1 API call) ---
        session_open = None
        session_high = None
        session_low = None
        session_volume = 0
        last_price = None
        polygon_prev_close = None
        
        try:
            snap = self.polygon.get_session_snapshot(symbol)
            if snap:
                session_open = Decimal(str(snap["session_open"])) if snap["session_open"] else None
                session_high = Decimal(str(snap["session_high"])) if snap["session_high"] else None
                session_low = Decimal(str(snap["session_low"])) if snap["session_low"] else None
                session_volume = snap["session_volume"]
                last_price = Decimal(str(snap["last_price"])) if snap["last_price"] else None
                polygon_prev_close = Decimal(str(snap["prev_close"])) if snap["prev_close"] else None
            else:
                logger.warning(f"[Unified] Polygon snapshot returned None for {symbol} — falling back to FMP")
        except Exception as e:
            logger.warning(f"[Unified] Polygon snapshot FAILED for {symbol}: {e} — falling back to FMP")
        
        # --- Fallback to FMP if Polygon didn't provide session data ---
        if not session_open or not last_price:
            try:
                quote_data = self.fmp._get(f"quote/{symbol}")
                if quote_data and len(quote_data) > 0:
                    q = quote_data[0]
                    session_open = session_open or Decimal(str(q.get("open", 0)))
                    session_high = session_high or Decimal(str(q.get("dayHigh", 0)))
                    session_low = session_low or Decimal(str(q.get("dayLow", 0)))
                    session_volume = session_volume or int(q.get("volume", 0))
                    if not last_price:
                        last_price = Decimal(str(q.get("price", 0)))
            except Exception as e:
                logger.debug(f"[Unified] FMP quote fallback failed for {symbol}: {e}")
        
        # --- Get Alpaca real-time price (highest priority for last_price) ---
        try:
            alpaca_quote = self.alpaca.get_quote(symbol)
            if alpaca_quote and alpaca_quote.price > 0:
                last_price = alpaca_quote.price
        except Exception:
            pass
        
        if not session_open or not last_price or session_open <= 0 or last_price <= 0:
            return None
        
        # --- Daily bars for yesterday close and avg volume (RVOL calc) ---
        daily = self.get_daily_bars(symbol, limit=rvol_lookback + 5)
        if not daily or len(daily) < 2:
            return None
        
        # Determine yesterday's close
        from datetime import date
        last_bar_date = daily[-1].timestamp.date()
        today = date.today()
        
        if last_bar_date < today:
            # Pre-market: most recent bar IS yesterday
            yesterday_close = daily[-1].close
            hist_bars = daily[:-1]
        else:
            # During market hours: most recent is today
            yesterday_close = daily[-2].close
            hist_bars = daily[:-2]
        
        # Use Polygon prev_close if daily bars didn't produce a value
        if not yesterday_close and polygon_prev_close:
            yesterday_close = polygon_prev_close
        
        if len(hist_bars) < 10:
            return None
        
        hist_volumes = [b.volume for b in hist_bars[-rvol_lookback:]] if len(hist_bars) >= rvol_lookback else [b.volume for b in hist_bars]
        avg_daily_volume = sum(hist_volumes) // len(hist_volumes) if hist_volumes else 0
        
        if avg_daily_volume <= 0:
            return None
        
        return {
            "yesterday_close": yesterday_close,
            "avg_daily_volume": avg_daily_volume,
            "session_open": session_open,
            "session_high": session_high,
            "session_low": session_low,
            "last_price": last_price,
            "session_volume": session_volume,
        }
    
    # =========================================================================
    # Screening Methods
    # =========================================================================
    
    def screen_stocks(
        self,
        min_market_cap: int = 50_000_000,
        min_price: float = 4.0,
        min_volume: int = 50_000,
        limit: int = 2000,
    ) -> List[Dict]:
        """Screen stocks using FMP screener."""
        return self.fmp.screen_stocks(
            min_market_cap=min_market_cap,
            min_price=min_price,
            min_volume=min_volume,
            limit=limit,
        )
    
    def filter_movers(
        self,
        symbols: List[str],
        min_change_pct: float = 3.0,
    ) -> List[str]:
        """Filter symbols by change percentage."""
        return self.fmp.filter_by_change(symbols, min_change_pct)
    
    def get_gainers(self) -> List[Dict]:
        """
        Get top gainers for today (real-time, refreshed every ~1 min).
        
        Falls back to pre-market gainers if regular market data is empty.
        """
        gainers = self.fmp.get_gainers()
        if gainers:
            return gainers
        # Fallback to pre-market gainers when market is closed
        return self.fmp.get_premarket_gainers()
    
    def get_actives(self) -> List[Dict]:
        """Get most active stocks by volume (real-time)."""
        return self.fmp.get_actives()
    
    def get_premarket_gainers(self, min_change_pct: float = 4.0) -> List[Dict]:
        """
        Get pre-market gainers for Warrior-style momentum scanning.
        
        Uses FMP's pre_post_market/gainers endpoint which returns stocks
        actually gapping up in pre-market (unlike stock_market/gainers).
        
        Args:
            min_change_pct: Minimum gap % to include (default 4% per Ross Cameron)
            
        Returns:
            List of pre-market gainers sorted by change_percent descending
        """
        return self.fmp.get_premarket_gainers(min_change_pct=min_change_pct)
    
    def get_alpaca_movers(self, top: int = 50, min_change_pct: float = 4.0) -> List[Dict]:
        """
        Get top movers from Alpaca's screener API.
        
        Alpaca's screener updates faster than FMP in pre-market, making it
        a valuable secondary source for detecting early movers.
        
        Note: Filters out warrants (symbols ending in W) as they're not
        tradable for momentum strategies.
        
        Args:
            top: Number of top gainers to fetch
            min_change_pct: Minimum change % to include
            
        Returns:
            List of movers with symbol, name, price, change, change_percent
        """
        import os
        import requests
        import logging
        from decimal import Decimal
        
        logger = logging.getLogger(__name__)
        
        try:
            key = os.environ.get('APCA_API_KEY_ID')
            secret = os.environ.get('APCA_API_SECRET_KEY')
            
            if not key or not secret:
                logger.debug("[Alpaca Movers] API keys not configured")
                return []
            
            headers = {'APCA-API-KEY-ID': key, 'APCA-API-SECRET-KEY': secret}
            resp = requests.get(
                f'https://data.alpaca.markets/v1beta1/screener/stocks/movers?top={top}',
                headers=headers,
                timeout=10,
            )
            
            if resp.status_code != 200:
                logger.warning(f"[Alpaca Movers] API returned {resp.status_code}")
                return []
            
            data = resp.json()
            gainers = data.get('gainers', [])
            
            movers = []
            for item in gainers:
                symbol = item.get('symbol', '')
                pct = item.get('percent_change', 0)
                
                # Filter out warrants (not tradable for momentum)
                if symbol.endswith('W'):
                    continue
                
                # Filter by minimum change
                if pct < min_change_pct:
                    continue
                
                movers.append({
                    "symbol": symbol,
                    "name": "",  # Alpaca doesn't provide name
                    "price": Decimal(str(item.get('price', 0))),
                    "change": Decimal("0"),  # Not provided
                    "change_percent": Decimal(str(pct)),
                })
            
            logger.info(f"[Alpaca Movers] Found {len(movers)} stocks with >{min_change_pct}% change")
            return movers
            
        except Exception as e:
            logger.warning(f"[Alpaca Movers] Error: {e}")
            return []
    
    def get_trend_leaders(self, limit: int = 100) -> List[str]:
        """
        Get trend leaders - stocks with strong momentum for HTF scanning.
        
        Uses FMP gainers (current day momentum) as proxy for trend leaders.
        These are stocks likely to have made big moves recently.
        
        Args:
            limit: Maximum number of symbols to return
            
        Returns:
            List of stock symbols
        """
        try:
            gainers = self.fmp.get_gainers()
            symbols = [g.get("symbol", "") for g in gainers if g.get("symbol")]
            return symbols[:limit]
        except Exception:
            # Fallback to basic screen if gainers endpoint fails
            try:
                stocks = self.screen_stocks(
                    min_market_cap=100_000_000,
                    min_price=5.0,
                    min_volume=100_000,
                    limit=limit,
                )
                return [s.get("symbol", "") for s in stocks if s.get("symbol")]
            except Exception:
                return []
    
    def get_company_name(self, symbol: str) -> Optional[str]:
        """
        Get company name for a symbol.
        
        Args:
            symbol: Stock symbol
            
        Returns:
            Company name or None if unavailable
        """
        try:
            info = self.fmp.get_stock_info(symbol)
            if info:
                return info.name
        except Exception:
            pass
        return None
    
    def get_historical_prices(
        self, 
        symbol: str, 
        days: int = 90
    ) -> Optional[List[Dict]]:
        """
        Get historical daily prices as list of dicts.
        
        Format compatible with HTF scanner expectations:
        [{"open": x, "high": x, "low": x, "close": x, "volume": x}, ...]
        
        Args:
            symbol: Stock symbol
            days: Number of days of history
            
        Returns:
            List of price dicts or None
        """
        bars = self.get_daily_bars(symbol, limit=days + 10)
        if not bars:
            return None
        
        # Convert OHLCV objects to dicts
        return [
            {
                "open": float(b.open),
                "high": float(b.high),
                "low": float(b.low),
                "close": float(b.close),
                "volume": b.volume,
            }
            for b in bars[-days:]
        ]
    
    def has_recent_catalyst(
        self,
        symbol: str,
        days: int = 3,
    ) -> tuple[bool, str, str]:
        """
        Check if symbol has a recent catalyst (earnings or material news).
        
        Used by EP scanner to filter out stocks without legitimate catalysts.
        
        Args:
            symbol: Stock symbol
            days: Days to look back
            
        Returns:
            (has_catalyst, catalyst_type, catalyst_description)
            - catalyst_type: "earnings", "news", or "none"
            - catalyst_description: Brief description of the catalyst
        """
        return self.fmp.has_recent_catalyst(symbol, days=days)
    
    def has_upcoming_earnings(
        self,
        symbol: str,
        days: int = 5,
    ) -> tuple[bool, str]:
        """
        Check if symbol has UPCOMING earnings (risk check).
        
        KK Rule: Don't trade stocks with earnings in the next 5 days.
        
        Args:
            symbol: Stock symbol
            days: Days to look ahead
            
        Returns:
            (has_upcoming, earnings_date)
        """
        return self.fmp.has_upcoming_earnings(symbol, days=days)
    
    def get_merged_headlines(
        self,
        symbol: str,
        days: int = 5,
        alpaca_broker=None,
    ) -> List[str]:
        """
        Get headlines from FMP + Alpaca (Benzinga) merged and deduplicated.
        
        Alpaca provides Benzinga-powered news with better micro-cap coverage.
        The AQMS "battery supply agreement" was in Alpaca but not FMP.
        
        Args:
            symbol: Stock symbol
            days: Number of days to look back
            alpaca_broker: Optional AlpacaBroker instance for news; pass from caller
            
        Returns:
            List of unique headline strings
        """
        headlines_set = set()
        headlines_list = []
        
        # 1. FMP headlines (existing source)
        try:
            fmp_headlines = self.fmp.get_recent_headlines(symbol, days=days)
            for headline in fmp_headlines:
                # Normalize for deduplication
                normalized = headline.strip().lower()
                if normalized and normalized not in headlines_set:
                    headlines_set.add(normalized)
                    headlines_list.append(headline.strip())
        except Exception as e:
            print(f"[Unified] FMP headlines error for {symbol}: {e}")
        
        # 2. Alpaca headlines (Benzinga-powered, better micro-cap coverage)
        if alpaca_broker:
            try:
                alpaca_news = alpaca_broker.get_news(symbol, limit=10, days=days)
                for item in alpaca_news:
                    headline = item.get("headline", "").strip()
                    if not headline:
                        continue
                    normalized = headline.lower()
                    if normalized not in headlines_set:
                        headlines_set.add(normalized)
                        headlines_list.append(headline)
            except Exception as e:
                print(f"[Unified] Alpaca headlines error for {symbol}: {e}")
        
        # 3. Yahoo Finance headlines (broad coverage)
        try:
            from nexus2.adapters.market_data.news_sources import get_yahoo_headlines
            for headline in get_yahoo_headlines(symbol, days=days):
                normalized = headline.strip().lower()
                if normalized and normalized not in headlines_set:
                    headlines_set.add(normalized)
                    headlines_list.append(headline.strip())
        except Exception as e:
            print(f"[Unified] Yahoo headlines error for {symbol}: {e}")
        
        # 4. Finviz headlines (strong micro-cap coverage)
        try:
            from nexus2.adapters.market_data.news_sources import get_finviz_headlines
            for headline in get_finviz_headlines(symbol, limit=5):
                normalized = headline.strip().lower()
                if normalized and normalized not in headlines_set:
                    headlines_set.add(normalized)
                    headlines_list.append(headline.strip())
        except Exception as e:
            print(f"[Unified] Finviz headlines error for {symbol}: {e}")
        
        return headlines_list

