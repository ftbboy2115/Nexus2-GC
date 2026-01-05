"""
Unified Scanner Service

Orchestrates all scanners (EP, Breakout, HTF) into a single signal stream
for the automation engine.
"""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from enum import Enum
import logging

from nexus2.domain.automation.signals import Signal, SetupType, SignalGenerator
from nexus2.domain.scanner.ep_scanner_service import (
    EPScannerService,
    get_ep_scanner_service,
)
from nexus2.domain.scanner.breakout_scanner_service import (
    BreakoutScannerService,
    BreakoutStatus,
    get_breakout_scanner_service,
)
from nexus2.domain.scanner.htf_scanner_service import (
    HTFScannerService,
    HTFStatus,
    get_htf_scanner_service,
)


logger = logging.getLogger(__name__)


class ScanMode(Enum):
    """Which scanners to run."""
    ALL = "all"           # Run all scanners
    EP_ONLY = "ep"        # Only EP (Episodic Pivot)
    BREAKOUT_ONLY = "breakout"  # Only Breakout/Flag
    HTF_ONLY = "htf"      # Only High-Tight Flag


@dataclass
class UnifiedScanSettings:
    """Settings for unified scanning."""
    # Which scanners to run
    modes: List[ScanMode] = field(default_factory=lambda: [ScanMode.ALL])
    
    # Signal filtering
    min_quality_score: int = 7
    stop_mode: str = "atr"  # "atr" (KK-style) or "percent"
    max_stop_atr: float = 1.0  # KK uses 1.0-1.5 ATR
    max_stop_percent: float = 5.0  # Fallback for percent mode
    
    # Price filter (applied in individual scanners)
    min_price: float = 5.0  # Minimum stock price (default $5)
    
    # Limits per scanner
    ep_limit: int = 20
    breakout_limit: int = 20
    htf_limit: int = 20
    
    # Testing: include extended HTF candidates (not KK-recommended)
    include_extended_htf: bool = False  # Default: exclude extended


@dataclass
class ScanRejection:
    """Details about why a signal was rejected."""
    symbol: str
    reason: str  # quality_too_low, stop_too_wide_atr, stop_too_wide_percent
    threshold: float
    actual_value: float


@dataclass
class ScanDiagnostics:
    """Diagnostics for one scanner run."""
    scanner: str  # "ep", "breakout", "htf"
    enabled: bool = True
    candidates_found: int = 0
    candidates_passed: int = 0
    rejections: List[ScanRejection] = field(default_factory=list)
    error: Optional[str] = None


@dataclass
class UnifiedScanResult:
    """Result from unified scan across all scanners."""
    signals: List[Signal]
    
    # Breakdown by scanner
    ep_count: int = 0
    breakout_count: int = 0
    htf_count: int = 0
    
    # Stats
    total_processed: int = 0
    scan_duration_ms: int = 0
    scanned_at: datetime = field(default_factory=datetime.utcnow)
    
    # Diagnostics for visibility
    diagnostics: List[ScanDiagnostics] = field(default_factory=list)
    
    @property
    def total_signals(self) -> int:
        return len(self.signals)


class UnifiedScannerService:
    """
    Unified Scanner Service.
    
    Orchestrates EP, Breakout, and HTF scanners into a single signal stream.
    Deduplicates signals (same symbol from multiple scanners).
    Prioritizes by setup quality.
    """
    
    def __init__(
        self,
        settings: Optional[UnifiedScanSettings] = None,
        ep_scanner: Optional[EPScannerService] = None,
        breakout_scanner: Optional[BreakoutScannerService] = None,
        htf_scanner: Optional[HTFScannerService] = None,
    ):
        self.settings = settings or UnifiedScanSettings()
        
        # Use provided scanners or get singletons
        self._ep_scanner = ep_scanner
        self._breakout_scanner = breakout_scanner
        self._htf_scanner = htf_scanner
        
        # Signal generator
        self._signal_gen = SignalGenerator(
            min_quality=self.settings.min_quality_score,
            max_stop_percent=self.settings.max_stop_percent,
        )
    
    @property
    def ep_scanner(self) -> EPScannerService:
        if self._ep_scanner is None:
            self._ep_scanner = get_ep_scanner_service()
        return self._ep_scanner
    
    @property
    def breakout_scanner(self) -> BreakoutScannerService:
        if self._breakout_scanner is None:
            self._breakout_scanner = get_breakout_scanner_service()
        return self._breakout_scanner
    
    @property
    def htf_scanner(self) -> HTFScannerService:
        if self._htf_scanner is None:
            self._htf_scanner = get_htf_scanner_service()
        return self._htf_scanner
    
    def scan(
        self,
        modes: Optional[List[ScanMode]] = None,
        verbose: bool = False,
    ) -> UnifiedScanResult:
        """
        Run unified scan across all configured scanners.
        
        Args:
            modes: Which scanners to run. None = use settings.modes
            verbose: Print verbose output
            
        Returns:
            UnifiedScanResult with all signals
        """
        import time
        start_time = time.time()
        
        modes = modes or self.settings.modes
        if ScanMode.ALL in modes:
            modes = [ScanMode.EP_ONLY, ScanMode.BREAKOUT_ONLY, ScanMode.HTF_ONLY]
        
        all_signals = []
        ep_count = 0
        breakout_count = 0
        htf_count = 0
        total_processed = 0
        
        # Track seen symbols to deduplicate
        seen_symbols = set()
        
        # Run EP Scanner
        if ScanMode.EP_ONLY in modes:
            try:
                if verbose:
                    print("[Unified] Running EP scanner...")
                ep_signals, ep_processed = self._run_ep_scan(verbose)
                total_processed += ep_processed
                for sig in ep_signals:
                    if sig.symbol not in seen_symbols:
                        all_signals.append(sig)
                        seen_symbols.add(sig.symbol)
                        ep_count += 1
                if verbose:
                    print(f"  EP: {ep_count} signals from {ep_processed} scanned")
            except Exception as e:
                logger.error(f"EP scan failed: {e}")
                if verbose:
                    print(f"  EP: FAILED - {e}")
        
        # Run Breakout Scanner
        if ScanMode.BREAKOUT_ONLY in modes:
            try:
                if verbose:
                    print("[Unified] Running Breakout scanner...")
                breakout_signals, bo_processed = self._run_breakout_scan(verbose)
                total_processed += bo_processed
                for sig in breakout_signals:
                    if sig.symbol not in seen_symbols:
                        all_signals.append(sig)
                        seen_symbols.add(sig.symbol)
                        breakout_count += 1
                if verbose:
                    print(f"  Breakout: {breakout_count} signals from {bo_processed} scanned")
            except Exception as e:
                logger.error(f"Breakout scan failed: {e}")
                if verbose:
                    print(f"  Breakout: FAILED - {e}")
        
        # Run HTF Scanner
        if ScanMode.HTF_ONLY in modes:
            try:
                if verbose:
                    print("[Unified] Running HTF scanner...")
                htf_signals, htf_processed = self._run_htf_scan(verbose)
                total_processed += htf_processed
                for sig in htf_signals:
                    if sig.symbol not in seen_symbols:
                        all_signals.append(sig)
                        seen_symbols.add(sig.symbol)
                        htf_count += 1
                if verbose:
                    print(f"  HTF: {htf_count} signals from {htf_processed} scanned")
            except Exception as e:
                logger.error(f"HTF scan failed: {e}")
                if verbose:
                    print(f"  HTF: FAILED - {e}")
        
        # Filter signals based on settings and track rejections
        filtered_signals = []
        all_rejections = []
        
        for sig in all_signals:
            rejection = sig.get_rejection_reason(
                min_quality=self.settings.min_quality_score,
                stop_mode=self.settings.stop_mode,
                max_stop_atr=self.settings.max_stop_atr,
                max_stop_percent=self.settings.max_stop_percent,
            )
            if rejection is None:
                filtered_signals.append(sig)
            else:
                reason, threshold, actual = rejection
                all_rejections.append(ScanRejection(
                    symbol=sig.symbol,
                    reason=reason,
                    threshold=float(threshold) if isinstance(threshold, (int, float)) else 0,
                    actual_value=float(actual) if isinstance(actual, (int, float)) else 0,
                ))
        
        if verbose and len(filtered_signals) < len(all_signals):
            print(f"[Unified] Filtered: {len(all_signals)} -> {len(filtered_signals)} signals")
            for rej in all_rejections[:3]:  # Show first 3 rejections
                print(f"  Rejected {rej.symbol}: {rej.reason} (threshold={rej.threshold}, actual={rej.actual_value})")
        
        # Sort by quality score (highest first)
        filtered_signals.sort(key=lambda s: s.quality_score, reverse=True)
        
        duration_ms = int((time.time() - start_time) * 1000)
        
        if verbose:
            print(f"[Unified] Complete: {len(filtered_signals)} total signals in {duration_ms}ms")
        
        # Build diagnostics for each scanner
        diagnostics = []
        
        # EP diagnostics
        ep_rejections = [r for r in all_rejections 
                         if any(s.symbol == r.symbol and s.setup_type.value == "ep" for s in all_signals)]
        diagnostics.append(ScanDiagnostics(
            scanner="ep",
            enabled=ScanMode.EP_ONLY in modes,
            candidates_found=ep_count + len([r for r in all_rejections 
                                              if any(s.symbol == r.symbol and s.setup_type.value == "ep" for s in all_signals)]),
            candidates_passed=sum(1 for s in filtered_signals if s.setup_type.value == "ep"),
            rejections=ep_rejections[:10],  # Limit rejections to avoid huge response
        ))
        
        # Breakout diagnostics
        bo_rejections = [r for r in all_rejections 
                         if any(s.symbol == r.symbol and s.setup_type.value == "breakout" for s in all_signals)]
        diagnostics.append(ScanDiagnostics(
            scanner="breakout",
            enabled=ScanMode.BREAKOUT_ONLY in modes,
            candidates_found=breakout_count + len([r for r in all_rejections 
                                                    if any(s.symbol == r.symbol and s.setup_type.value == "breakout" for s in all_signals)]),
            candidates_passed=sum(1 for s in filtered_signals if s.setup_type.value == "breakout"),
            rejections=bo_rejections[:10],
        ))
        
        # HTF diagnostics
        htf_rejections = [r for r in all_rejections 
                          if any(s.symbol == r.symbol and s.setup_type.value == "htf" for s in all_signals)]
        diagnostics.append(ScanDiagnostics(
            scanner="htf",
            enabled=ScanMode.HTF_ONLY in modes,
            candidates_found=htf_count + len([r for r in all_rejections 
                                               if any(s.symbol == r.symbol and s.setup_type.value == "htf" for s in all_signals)]),
            candidates_passed=sum(1 for s in filtered_signals if s.setup_type.value == "htf"),
            rejections=htf_rejections[:10],
        ))
        
        return UnifiedScanResult(
            signals=filtered_signals,
            ep_count=sum(1 for s in filtered_signals if s.setup_type.value == "ep"),
            breakout_count=sum(1 for s in filtered_signals if s.setup_type.value == "breakout"),
            htf_count=sum(1 for s in filtered_signals if s.setup_type.value == "htf"),
            total_processed=total_processed,
            scan_duration_ms=duration_ms,
            diagnostics=diagnostics,
        )
    
    def _run_ep_scan(self, verbose: bool = False) -> tuple[List[Signal], int]:
        """Run EP scanner and convert to signals."""
        result = self.ep_scanner.scan(verbose=verbose)
        
        signals = []
        for candidate in result.candidates:
            signal = self._ep_candidate_to_signal(candidate)
            if signal:
                signals.append(signal)
        
        return signals, result.processed_count
    
    def _run_breakout_scan(self, verbose: bool = False) -> tuple[List[Signal], int]:
        """Run Breakout scanner and convert to signals."""
        result = self.breakout_scanner.scan(verbose=verbose)
        
        signals = []
        for candidate in result.candidates:
            # Only include consolidating or breaking_out status
            if candidate.status in (BreakoutStatus.CONSOLIDATING, BreakoutStatus.BREAKING_OUT):
                signal = self._breakout_candidate_to_signal(candidate)
                if signal:
                    signals.append(signal)
        
        return signals, result.processed_count
    
    def _run_htf_scan(self, verbose: bool = False) -> tuple[List[Signal], int]:
        """Run HTF scanner and convert to signals."""
        result = self.htf_scanner.scan(verbose=verbose)
        
        signals = []
        for candidate in result.candidates:
            # Filter by status:
            # - COMPLETE/FORMING are always included
            # - EXTENDED only if include_extended_htf is True
            valid_statuses = [HTFStatus.COMPLETE, HTFStatus.FORMING]
            if self.settings.include_extended_htf:
                valid_statuses.append(HTFStatus.EXTENDED)
            
            if candidate.status in valid_statuses:
                signal = self._htf_candidate_to_signal(candidate)
                if signal:
                    signals.append(signal)
        
        return signals, result.processed_count
    
    def _ep_candidate_to_signal(self, candidate) -> Optional[Signal]:
        """Convert EP candidate to Signal."""
        try:
            # EP has its own entry/stop levels
            # Use current_price or open_price (EPCandidate doesn't have 'price')
            entry_price = candidate.current_price or candidate.open_price
            entry_price = Decimal(str(entry_price))
            
            # Use tactical stop if available (opening range low), else 3% default
            if candidate.tactical_stop:
                tactical_stop = Decimal(str(candidate.tactical_stop))
            elif candidate.opening_range:
                tactical_stop = Decimal(str(candidate.opening_range.low))
            else:
                tactical_stop = entry_price * Decimal("0.97")  # 3% default stop
            
            # Calculate quality score based on EP metrics
            quality = 5  # Base score
            if candidate.relative_volume and candidate.relative_volume > Decimal("2"):
                quality += 2
            if candidate.gap_percent and candidate.gap_percent > Decimal("5"):
                quality += 1
            if candidate.catalyst_type:
                quality += 2
            quality = min(10, quality)
            
            return Signal(
                symbol=candidate.symbol,
                setup_type=SetupType.EP,
                entry_price=entry_price,
                tactical_stop=tactical_stop,
                quality_score=quality,
                tier="FOCUS" if quality >= 8 else "WIDE" if quality >= 6 else "SKIP",
                rs_percentile=getattr(candidate, 'rs_percentile', 70),
                adr_percent=float(getattr(candidate, 'adr_percent', 3.0)),
                scanner_mode="ep",
            )
        except Exception as e:
            logger.error(f"Failed to convert EP candidate {candidate.symbol}: {e}")
            return None
    
    def _breakout_candidate_to_signal(self, candidate) -> Optional[Signal]:
        """Convert Breakout candidate to Signal."""
        try:
            entry_price = candidate.entry_price or candidate.price
            entry_price = Decimal(str(entry_price))  # Ensure Decimal
            tactical_stop = candidate.stop_price
            tactical_stop = Decimal(str(tactical_stop)) if tactical_stop else (entry_price * Decimal("0.95"))
            
            # Calculate quality based on breakout metrics
            quality = 5
            if candidate.tightness_score > Decimal("0.7"):
                quality += 2
            if candidate.ma_stacked:
                quality += 1
            if candidate.rs_percentile >= 70:
                quality += 1
            if candidate.status == BreakoutStatus.BREAKING_OUT:
                quality += 1
            quality = min(10, quality)
            
            return Signal(
                symbol=candidate.symbol,
                setup_type=SetupType.BREAKOUT if candidate.status == BreakoutStatus.BREAKING_OUT else SetupType.FLAG,
                entry_price=entry_price,
                tactical_stop=tactical_stop,
                quality_score=quality,
                tier="FOCUS" if quality >= 8 else "WIDE" if quality >= 6 else "SKIP",
                rs_percentile=candidate.rs_percentile,
                adr_percent=3.0,  # Default if not available
                scanner_mode="breakout",
            )
        except Exception as e:
            logger.error(f"Failed to convert Breakout candidate {candidate.symbol}: {e}")
            return None
    
    def _htf_candidate_to_signal(self, candidate) -> Optional[Signal]:
        """Convert HTF candidate to Signal."""
        try:
            entry_price = candidate.entry_price or candidate.price
            entry_price = Decimal(str(entry_price))  # Ensure Decimal
            
            # HTF scanner now provides stop_price (flag low)
            # Fallback uses current price (not entry_price) for safety
            if candidate.stop_price:
                tactical_stop = Decimal(str(candidate.stop_price))
            else:
                # Fallback: 3% below current price (not entry_price to avoid stop > current)
                current_price = Decimal(str(candidate.price))
                tactical_stop = current_price * Decimal("0.97")
            
            # Calculate quality based on HTF metrics
            quality = 6  # HTF patterns start higher quality
            if candidate.move_pct > Decimal("120"):
                quality += 1
            if candidate.pullback_pct < Decimal("15"):
                quality += 1
            if candidate.status == HTFStatus.COMPLETE:
                quality += 2
            elif candidate.status == HTFStatus.EXTENDED:
                quality -= 2  # Penalty for extended (not KK-recommended)
            quality = max(4, min(10, quality))  # Clamp 4-10
            
            # Get actual RS percentile from RS service
            from nexus2.domain.scanner.rs_service import get_rs_service
            rs_percentile = get_rs_service().get_rs_percentile(candidate.symbol)
            
            return Signal(
                symbol=candidate.symbol,
                setup_type=SetupType.HTF,
                entry_price=entry_price,
                tactical_stop=tactical_stop,
                quality_score=quality,
                tier="FOCUS" if quality >= 8 else "WIDE" if quality >= 6 else "SKIP",
                rs_percentile=rs_percentile,
                adr_percent=5.0,  # HTF stocks tend to be volatile
                scanner_mode="htf",
            )
        except Exception as e:
            logger.error(f"Failed to convert HTF candidate {candidate.symbol}: {e}")
            return None


# =============================================================================
# SINGLETON
# =============================================================================

_unified_scanner: Optional[UnifiedScannerService] = None


def get_unified_scanner_service() -> UnifiedScannerService:
    """Get singleton unified scanner service."""
    global _unified_scanner
    if _unified_scanner is None:
        _unified_scanner = UnifiedScannerService()
    return _unified_scanner
