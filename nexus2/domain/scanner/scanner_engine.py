"""
Scanner Engine

Core scanning logic that evaluates stocks against KK criteria.
Based on: scanner_architecture.md
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import List, Protocol

from nexus2.domain.scanner.models import (
    Stock,
    StockMetrics,
    ScannerResult,
    WatchlistTier,
    PatternType,
    QualityRating,
)
from nexus2.settings.scanner_settings import (
    ScannerSettings,
    DisqualifierSettings,
    QualityScoringSettings,
)


class MarketDataProvider(Protocol):
    """Protocol for market data providers."""
    
    def get_stock_universe(self) -> List[Stock]:
        """Get all eligible stocks for scanning."""
        ...
    
    def get_metrics(self, symbol: str) -> StockMetrics:
        """Get calculated metrics for a stock."""
        ...


class ScannerEngine:
    """
    Core scanning logic that evaluates stocks against criteria.
    
    Responsibilities:
    - Scan stock universe against KK criteria
    - Calculate quality scores
    - Check disqualifiers
    - Recommend watchlist tier
    """
    
    def __init__(
        self,
        settings: ScannerSettings,
        disqualifiers: DisqualifierSettings,
        scoring: QualityScoringSettings,
    ):
        self.settings = settings
        self.disqualifiers = disqualifiers
        self.scoring = scoring
    
    def scan_universe(
        self,
        stocks: List[Stock],
        metrics_provider: MarketDataProvider,
    ) -> List[ScannerResult]:
        """
        Scan all eligible stocks against KK criteria.
        
        Args:
            stocks: List of stocks to evaluate
            metrics_provider: Provider for stock metrics
            
        Returns:
            List of ScannerResult objects
        """
        results = []
        for stock in stocks:
            try:
                metrics = metrics_provider.get_metrics(stock.symbol)
                result = self.evaluate_stock(stock, metrics)
                results.append(result)
            except Exception as e:
                # Log error but continue scanning
                print(f"Error scanning {stock.symbol}: {e}")
        
        # Sort by quality score descending
        results.sort(key=lambda r: r.quality_score, reverse=True)
        return results
    
    def evaluate_stock(
        self,
        stock: Stock,
        metrics: StockMetrics,
    ) -> ScannerResult:
        """
        Evaluate single stock against all criteria.
        
        Args:
            stock: Stock entity
            metrics: Calculated metrics
            
        Returns:
            ScannerResult with pass/fail and quality score
        """
        failed_criteria = self.check_disqualifiers(stock, metrics)
        passes_filter = len(failed_criteria) == 0
        quality_score = self.calculate_quality_score(stock, metrics)
        tier = self._recommend_tier(quality_score, passes_filter)
        
        return ScannerResult(
            stock=stock,
            metrics=metrics,
            passes_filter=passes_filter,
            failed_criteria=failed_criteria,
            quality_score=quality_score,
            tier_recommendation=tier,
            patterns_detected=[],  # Set by PatternDetector
            scanned_at=datetime.now(),
        )
    
    def calculate_quality_score(
        self,
        stock: Stock,
        metrics: StockMetrics,
    ) -> int:
        """
        Calculate composite quality score (0-10).
        
        Each factor contributes 1 point when met:
        - Price > $5
        - Volume > 300K
        - Dollar Volume > $5M
        - Above 50-day MA
        - Above 200-day MA
        - RS > 50th percentile
        - Not extended (<20% above 20MA)
        - Tight consolidation
        - Volume contraction
        - Stop ≤ 1x ATR
        """
        score = 0
        s = self.settings
        w = self.scoring
        
        # Price
        if stock.price >= s.min_price:
            score += w.weight_price
        
        # Volume
        if stock.avg_volume_20d >= s.min_avg_volume:
            score += w.weight_volume
        
        # Dollar Volume
        if stock.dollar_volume >= s.min_dollar_volume:
            score += w.weight_dollar_volume
        
        # Above 50-day MA
        if metrics.price_vs_sma50 > Decimal("0"):
            score += w.weight_above_50ma
        
        # Above 200-day MA
        if metrics.price_vs_sma200 > Decimal("0"):
            score += w.weight_above_200ma
        
        # RS percentile > 50
        if metrics.rs_percentile > 50:
            score += w.weight_rs_percentile
        
        # Not extended (<20% above 20MA)
        if metrics.price_vs_sma20 < Decimal("20"):
            score += w.weight_not_extended
        
        # Volume contraction (in consolidation)
        if metrics.volume_contraction:
            score += w.weight_volume_contraction
        
        # Note: Tight consolidation and stop ATR checked separately
        # as they require pattern/setup context
        
        return min(score, 10)
    
    def check_disqualifiers(
        self,
        stock: Stock,
        metrics: StockMetrics,
    ) -> List[str]:
        """
        Return list of failed disqualifiers.
        
        Empty list means stock passes all criteria.
        """
        failed = []
        s = self.settings
        d = self.disqualifiers
        
        # Price too low
        if stock.price < s.abs_min_price:
            failed.append(f"Price ${stock.price} below absolute minimum ${s.abs_min_price}")
        elif stock.price < s.min_price:
            failed.append(f"Price ${stock.price} below preferred minimum ${s.min_price}")
        
        # Volume too low
        if stock.avg_volume_20d < s.min_avg_volume:
            failed.append(f"Volume {stock.avg_volume_20d:,} below minimum {s.min_avg_volume:,}")
        
        # Dollar volume too low
        if stock.dollar_volume < s.min_dollar_volume:
            failed.append(f"Dollar volume ${stock.dollar_volume:,} below minimum ${s.min_dollar_volume:,}")
        
        # Market cap too low
        if stock.market_cap < s.min_market_cap:
            failed.append(f"Market cap ${stock.market_cap:,} below minimum ${s.min_market_cap:,}")
        
        # ADR too low
        if metrics.adr_percent < s.min_adr_percent:
            failed.append(f"ADR {metrics.adr_percent}% below minimum {s.min_adr_percent}%")
        
        # Below required MAs
        if s.require_above_50ma and metrics.price_vs_sma50 < Decimal("0"):
            failed.append("Below 50-day MA")
        
        if s.require_above_200ma and metrics.price_vs_sma200 < Decimal("0"):
            failed.append("Below 200-day MA")
        
        # Extended from MAs
        if metrics.price_vs_sma20 > d.max_extension_pct:
            failed.append(f"Extended {metrics.price_vs_sma20}% above 20MA (max {d.max_extension_pct}%)")
        
        # OTC exchange
        from nexus2.domain.scanner.models import Exchange
        if stock.exchange == Exchange.OTC:
            failed.append("OTC exchange not allowed")
        
        return failed
    
    def _recommend_tier(self, quality_score: int, passes_filter: bool) -> WatchlistTier:
        """Recommend watchlist tier based on quality score."""
        if not passes_filter:
            return WatchlistTier.UNIVERSE
        
        if quality_score >= self.scoring.high_quality_min:
            return WatchlistTier.FOCUS
        elif quality_score >= self.scoring.medium_quality_min:
            return WatchlistTier.WIDE
        return WatchlistTier.UNIVERSE
