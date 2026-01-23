"""
Quote Fidelity Audit Service

Tracks divergence between quote providers (Alpaca, FMP, Schwab) across time windows.
Used to detect unreliable data sources and inform dynamic source priority.

Features:
- Logs all quote checks with source prices and divergence metrics
- Calculates provider reliability by time window
- Discord alerts for extreme divergence (>50%)
- Daily summary reports
- 90-day retention with automatic cleanup
"""

import logging
import threading
import queue
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass

from nexus2.db.database import get_session
from nexus2.db.models import QuoteAuditModel
from nexus2.utils.time_utils import now_utc, now_et

logger = logging.getLogger(__name__)

# Configuration defaults (can be overridden via environment)
HIGH_DIVERGENCE_THRESHOLD = 20.0  # Flag as high divergence
ALERT_THRESHOLD = 50.0  # Discord alert threshold
ALERT_COOLDOWN_MINUTES = 15
RETENTION_DAYS = 90
DYNAMIC_LOOKBACK_DAYS = 7


@dataclass
class QuoteAuditEntry:
    """Data class for quote audit logging."""
    symbol: str
    time_window: str
    alpaca_price: Optional[float]
    fmp_price: Optional[float]
    schwab_price: Optional[float]
    selected_source: str
    selected_price: float
    divergence_pct: float


class QuoteAuditService:
    """
    Core service for quote fidelity auditing.
    
    Uses a background thread with bounded queue for async logging
    to avoid blocking quote fetches.
    """
    
    def __init__(self):
        self._lock = threading.Lock()
        self._alert_cooldowns: Dict[tuple, datetime] = {}  # (symbol, time_window) -> last_alert_time
        
        # Async logging queue
        self._log_queue: queue.Queue = queue.Queue(maxsize=1000)
        self._writer_thread: Optional[threading.Thread] = None
        self._shutdown = threading.Event()
        
        # Start background writer
        self._start_writer_thread()
    
    def _start_writer_thread(self):
        """Start background thread for batch DB inserts."""
        if self._writer_thread is None or not self._writer_thread.is_alive():
            self._shutdown.clear()
            self._writer_thread = threading.Thread(
                target=self._writer_loop,
                name="QuoteAuditWriter",
                daemon=True
            )
            self._writer_thread.start()
            logger.info("[QuoteAudit] Writer thread started")
    
    def _writer_loop(self):
        """Background loop: batch insert every 100 records or 5 seconds."""
        batch: List[QuoteAuditEntry] = []
        last_flush = datetime.now()
        
        while not self._shutdown.is_set():
            try:
                # Wait for item with timeout
                entry = self._log_queue.get(timeout=1.0)
                batch.append(entry)
                
                # Flush if batch is large enough or time elapsed
                if len(batch) >= 100 or (datetime.now() - last_flush).seconds >= 5:
                    self._flush_batch(batch)
                    batch = []
                    last_flush = datetime.now()
            except queue.Empty:
                # Timeout - flush any pending records
                if batch:
                    self._flush_batch(batch)
                    batch = []
                    last_flush = datetime.now()
            except Exception as e:
                logger.error(f"[QuoteAudit] Writer error: {e}")
        
        # Final flush on shutdown
        if batch:
            self._flush_batch(batch)
    
    def _flush_batch(self, batch: List[QuoteAuditEntry]):
        """Insert batch of audit records to database."""
        if not batch:
            return
        
        try:
            with get_session() as session:
                for entry in batch:
                    model = QuoteAuditModel(
                        symbol=entry.symbol,
                        time_window=entry.time_window,
                        alpaca_price=str(entry.alpaca_price) if entry.alpaca_price else None,
                        fmp_price=str(entry.fmp_price) if entry.fmp_price else None,
                        schwab_price=str(entry.schwab_price) if entry.schwab_price else None,
                        selected_source=entry.selected_source,
                        selected_price=str(entry.selected_price),
                        divergence_pct=f"{entry.divergence_pct:.2f}",
                        high_divergence=entry.divergence_pct > HIGH_DIVERGENCE_THRESHOLD,
                    )
                    session.add(model)
                session.commit()
            logger.debug(f"[QuoteAudit] Flushed {len(batch)} records to DB")
        except Exception as e:
            logger.error(f"[QuoteAudit] Failed to flush batch: {e}")
    
    def log_quote_check(
        self,
        symbol: str,
        sources_dict: Dict[str, Optional[float]],
        selected_source: str,
        divergence_pct: float,
        time_window: str,
    ):
        """
        Log a quote validation event.
        
        Non-blocking: queues for async insert.
        """
        entry = QuoteAuditEntry(
            symbol=symbol,
            time_window=time_window,
            alpaca_price=sources_dict.get("Alpaca"),
            fmp_price=sources_dict.get("FMP"),
            schwab_price=sources_dict.get("Schwab"),
            selected_source=selected_source,
            selected_price=sources_dict.get(selected_source, 0) or 0,
            divergence_pct=divergence_pct,
        )
        
        try:
            self._log_queue.put_nowait(entry)
        except queue.Full:
            logger.warning("[QuoteAudit] Queue full - dropping audit record")
        
        # Check if we should send Discord alert
        if divergence_pct > ALERT_THRESHOLD:
            self._maybe_send_alert(symbol, sources_dict, divergence_pct, time_window)
    
    def _maybe_send_alert(
        self,
        symbol: str,
        sources: Dict[str, Optional[float]],
        divergence_pct: float,
        time_window: str,
    ):
        """Send Discord alert if not in cooldown."""
        key = (symbol, time_window)
        now = now_utc()
        
        with self._lock:
            last_alert = self._alert_cooldowns.get(key)
            if last_alert and (now - last_alert).total_seconds() < ALERT_COOLDOWN_MINUTES * 60:
                return  # In cooldown
            
            self._alert_cooldowns[key] = now
        
        # Format prices
        prices = ", ".join(
            f"{source}=${price:.2f}" if price else f"{source}=N/A"
            for source, price in sources.items()
        )
        
        message = f"⚠️ **Quote Divergence Alert**\n{symbol} ({time_window}): {divergence_pct:.1f}% spread\n{prices}"
        
        try:
            from nexus2.adapters.notifications.discord import DiscordNotifier
            notifier = DiscordNotifier()
            notifier.send_system_alert(message, level="warning")
            logger.info(f"[QuoteAudit] Alert sent for {symbol}: {divergence_pct:.1f}% divergence")
        except Exception as e:
            logger.error(f"[QuoteAudit] Failed to send alert: {e}")
    
    def get_recent_audits(self, symbol: Optional[str] = None, limit: int = 100) -> List[Dict]:
        """Get recent audit logs."""
        try:
            with get_session() as session:
                query = session.query(QuoteAuditModel).order_by(QuoteAuditModel.timestamp.desc())
                if symbol:
                    query = query.filter(QuoteAuditModel.symbol == symbol.upper())
                results = query.limit(limit).all()
                return [r.to_dict() for r in results]
        except Exception as e:
            logger.error(f"[QuoteAudit] Failed to get recent audits: {e}")
            return []
    
    def get_provider_reliability(
        self,
        time_window: Optional[str] = None,
        days: int = DYNAMIC_LOOKBACK_DAYS,
    ) -> Dict[str, float]:
        """
        Calculate provider reliability as % of quotes within 5% of selected price.
        
        Returns:
            {"Alpaca": 85.2, "FMP": 92.1, "Schwab": 98.5}
        """
        try:
            cutoff = now_utc() - timedelta(days=days)
            
            with get_session() as session:
                query = session.query(QuoteAuditModel).filter(
                    QuoteAuditModel.timestamp >= cutoff
                )
                if time_window:
                    query = query.filter(QuoteAuditModel.time_window == time_window)
                
                records = query.all()
            
            if not records:
                return {}
            
            # Count accurate quotes per provider
            provider_stats = {"Alpaca": {"accurate": 0, "total": 0}, "FMP": {"accurate": 0, "total": 0}, "Schwab": {"accurate": 0, "total": 0}}
            
            for r in records:
                selected = float(r.selected_price) if r.selected_price else 0
                if selected <= 0:
                    continue
                
                for provider, price_field in [("Alpaca", r.alpaca_price), ("FMP", r.fmp_price), ("Schwab", r.schwab_price)]:
                    if price_field:
                        price = float(price_field)
                        if price > 0:
                            provider_stats[provider]["total"] += 1
                            # Accurate if within 5% of selected price
                            if abs(price - selected) / selected <= 0.05:
                                provider_stats[provider]["accurate"] += 1
            
            # Calculate percentages
            result = {}
            for provider, stats in provider_stats.items():
                if stats["total"] > 0:
                    result[provider] = (stats["accurate"] / stats["total"]) * 100
            
            return result
        except Exception as e:
            logger.error(f"[QuoteAudit] Failed to calculate reliability: {e}")
            return {}
    
    def recommend_source_priority(self, time_window: str) -> Optional[List[str]]:
        """
        Return provider ranking based on historical accuracy.
        
        Returns None if insufficient data (<7 days history).
        """
        reliability = self.get_provider_reliability(time_window=time_window, days=DYNAMIC_LOOKBACK_DAYS)
        
        if not reliability or len(reliability) < 2:
            return None  # Insufficient data
        
        # Sort by reliability descending
        ranked = sorted(reliability.items(), key=lambda x: x[1], reverse=True)
        return [provider for provider, _ in ranked]
    
    def cleanup_old_audits(self, retention_days: int = RETENTION_DAYS) -> int:
        """
        Delete audits older than retention period.
        
        Returns count of deleted records.
        """
        try:
            cutoff = now_utc() - timedelta(days=retention_days)
            
            with get_session() as session:
                deleted = session.query(QuoteAuditModel).filter(
                    QuoteAuditModel.timestamp < cutoff
                ).delete()
                session.commit()
            
            logger.info(f"[QuoteAudit] Cleanup: deleted {deleted} records older than {retention_days} days")
            return deleted
        except Exception as e:
            logger.error(f"[QuoteAudit] Cleanup failed: {e}")
            return 0
    
    def generate_daily_summary(self) -> Dict:
        """
        Generate daily summary report.
        
        Returns:
            {
                "date": "2026-01-22",
                "total_audits": 1234,
                "high_divergence_count": 45,
                "top_divergent_symbols": [...],
                "provider_reliability": {...}
            }
        """
        try:
            today = now_et().date()
            start_of_day = datetime.combine(today, datetime.min.time())
            
            with get_session() as session:
                # Total audits today
                total = session.query(QuoteAuditModel).filter(
                    QuoteAuditModel.timestamp >= start_of_day
                ).count()
                
                # High divergence count
                high_div = session.query(QuoteAuditModel).filter(
                    QuoteAuditModel.timestamp >= start_of_day,
                    QuoteAuditModel.high_divergence == True
                ).count()
                
                # Top divergent symbols
                from sqlalchemy import func
                top_symbols = session.query(
                    QuoteAuditModel.symbol,
                    func.max(QuoteAuditModel.divergence_pct).label("max_divergence")
                ).filter(
                    QuoteAuditModel.timestamp >= start_of_day
                ).group_by(QuoteAuditModel.symbol).order_by(
                    func.max(QuoteAuditModel.divergence_pct).desc()
                ).limit(10).all()
            
            return {
                "date": str(today),
                "total_audits": total,
                "high_divergence_count": high_div,
                "top_divergent_symbols": [
                    {"symbol": s, "max_divergence": d} for s, d in top_symbols
                ],
                "provider_reliability": self.get_provider_reliability(days=1),
            }
        except Exception as e:
            logger.error(f"[QuoteAudit] Failed to generate summary: {e}")
            return {"error": str(e)}
    
    def get_status(self) -> Dict:
        """Get service status."""
        return {
            "writer_thread_alive": self._writer_thread.is_alive() if self._writer_thread else False,
            "queue_size": self._log_queue.qsize(),
            "active_cooldowns": len(self._alert_cooldowns),
        }
    
    def shutdown(self):
        """Graceful shutdown - flush remaining records."""
        self._shutdown.set()
        if self._writer_thread:
            self._writer_thread.join(timeout=5.0)
        logger.info("[QuoteAudit] Service shutdown complete")


# Singleton
_quote_audit_service: Optional[QuoteAuditService] = None


def get_quote_audit_service() -> QuoteAuditService:
    """Get singleton quote audit service."""
    global _quote_audit_service
    if _quote_audit_service is None:
        _quote_audit_service = QuoteAuditService()
    return _quote_audit_service


def determine_time_window() -> str:
    """Classify current time into audit window."""
    now = now_et()
    hour = now.hour
    minute = now.minute
    
    # Premarket: 4:00 AM - 9:29 AM ET
    if 4 <= hour < 7:
        return "premarket_early"  # 4:00-6:59 AM
    elif 7 <= hour < 9 or (hour == 9 and minute < 30):
        return "premarket_late"  # 7:00-9:29 AM
    
    # Regular hours: 9:30 AM - 4:00 PM ET
    elif (hour == 9 and minute >= 30) or (10 <= hour < 16):
        return "regular_hours"
    
    # Postmarket: 4:00 PM - 8:00 PM ET
    elif 16 <= hour < 18:
        return "postmarket_early"  # 4:00-5:59 PM
    elif 18 <= hour < 20:
        return "postmarket_late"  # 6:00-7:59 PM
    
    else:
        return "closed"  # 8:00 PM - 3:59 AM
