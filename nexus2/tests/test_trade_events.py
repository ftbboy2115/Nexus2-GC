"""
Tests for Trade Event Service

Tests the TradeEventService to ensure it:
1. Logs NAC and Warrior events correctly
2. Captures market context (SPY, VIX) in metadata
3. Maps exit reasons to correct event types
4. Retrieves events by position and strategy
"""

import json
from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest


class TestTradeEventServiceNACEntry:
    """Test NAC entry event logging."""
    
    def test_logs_nac_entry_event(self, db_session):
        """NAC entry should be logged with correct data."""
        from nexus2.domain.automation.trade_event_service import TradeEventService
        
        service = TradeEventService()
        
        with patch.object(service, "_get_market_context", return_value={}):
            event_id = service.log_nac_entry(
                position_id="pos-123",
                symbol="AAPL",
                entry_price=Decimal("150.00"),
                stop_price=Decimal("145.00"),
                shares=100,
                setup_type="EP",
                quality_score=85,
            )
        
        assert event_id is not None
    
    def test_nac_entry_includes_market_context(self, db_session):
        """NAC entry should capture market context in metadata."""
        from nexus2.domain.automation.trade_event_service import TradeEventService
        from nexus2.db.database import get_session
        from nexus2.db.models import TradeEventModel
        
        service = TradeEventService()
        
        mock_context = {
            "spy_price": 590.50,
            "spy_change_pct": -0.75,
            "vix": 18.5,
            "market_snapshot_time": "2026-01-10T10:30:00",
        }
        
        with patch.object(service, "_get_market_context", return_value=mock_context):
            event_id = service.log_nac_entry(
                position_id="pos-456",
                symbol="MSFT",
                entry_price=Decimal("400.00"),
                stop_price=Decimal("390.00"),
                shares=50,
                setup_type="BREAKOUT",
                quality_score=90,
            )
        
        # Verify market context is in metadata
        with get_session() as db:
            event = db.query(TradeEventModel).filter_by(id=event_id).first()
            metadata = json.loads(event.metadata_json)
            
            assert "spy_price" in metadata
            assert metadata["spy_price"] == 590.50
            assert "spy_change_pct" in metadata
            assert metadata["spy_change_pct"] == -0.75
            assert "vix" in metadata


class TestTradeEventServiceWarriorEntry:
    """Test Warrior entry event logging."""
    
    def test_logs_warrior_entry_event(self, db_session):
        """Warrior entry should be logged with trigger type."""
        from nexus2.domain.automation.trade_event_service import TradeEventService
        
        service = TradeEventService()
        
        with patch.object(service, "_get_market_context", return_value={}):
            event_id = service.log_warrior_entry(
                position_id="war-123",
                symbol="GOOG",
                entry_price=Decimal("180.00"),
                stop_price=Decimal("178.00"),
                shares=200,
                trigger_type="ORB",
            )
        
        assert event_id is not None
    
    def test_warrior_entry_default_trigger_type(self, db_session):
        """Warrior entry should default to ORB trigger type."""
        from nexus2.domain.automation.trade_event_service import TradeEventService
        from nexus2.db.database import get_session
        from nexus2.db.models import TradeEventModel
        
        service = TradeEventService()
        
        with patch.object(service, "_get_market_context", return_value={}):
            event_id = service.log_warrior_entry(
                position_id="war-456",
                symbol="META",
                entry_price=Decimal("500.00"),
                stop_price=Decimal("495.00"),
                shares=30,
            )
        
        with get_session() as db:
            event = db.query(TradeEventModel).filter_by(id=event_id).first()
            metadata = json.loads(event.metadata_json)
            
            assert metadata["trigger_type"] == "ORB"


class TestTradeEventServiceExitMapping:
    """Test exit event type mapping."""
    
    def test_nac_stop_hit_maps_correctly(self, db_session):
        """NAC stop_hit should map to NAC_STOP_HIT event type."""
        from nexus2.domain.automation.trade_event_service import TradeEventService
        from nexus2.db.database import get_session
        from nexus2.db.models import TradeEventModel
        
        service = TradeEventService()
        
        with patch.object(service, "_get_market_context", return_value={}):
            event_id = service.log_nac_exit(
                position_id="pos-789",
                symbol="NVDA",
                exit_price=Decimal("900.00"),
                exit_type="stop_hit",
                pnl=Decimal("-250.00"),
            )
        
        with get_session() as db:
            event = db.query(TradeEventModel).filter_by(id=event_id).first()
            assert event.event_type == "STOP_HIT"
    
    def test_warrior_mental_stop_maps_correctly(self, db_session):
        """Warrior mental_stop should map to MENTAL_STOP_EXIT event type."""
        from nexus2.domain.automation.trade_event_service import TradeEventService
        from nexus2.db.database import get_session
        from nexus2.db.models import TradeEventModel
        
        service = TradeEventService()
        
        with patch.object(service, "_get_market_context", return_value={}):
            event_id = service.log_warrior_exit(
                position_id="war-789",
                symbol="TSLA",
                exit_price=Decimal("250.00"),
                exit_reason="mental_stop",
                pnl=Decimal("-150.00"),
            )
        
        with get_session() as db:
            event = db.query(TradeEventModel).filter_by(id=event_id).first()
            assert event.event_type == "MENTAL_STOP_EXIT"
    
    def test_warrior_candle_under_candle_maps_correctly(self, db_session):
        """Warrior candle_under_candle should map correctly."""
        from nexus2.domain.automation.trade_event_service import TradeEventService
        from nexus2.db.database import get_session
        from nexus2.db.models import TradeEventModel
        
        service = TradeEventService()
        
        with patch.object(service, "_get_market_context", return_value={}):
            event_id = service.log_warrior_exit(
                position_id="war-abc",
                symbol="AMD",
                exit_price=Decimal("180.00"),
                exit_reason="candle_under_candle",
                pnl=Decimal("300.00"),
            )
        
        with get_session() as db:
            event = db.query(TradeEventModel).filter_by(id=event_id).first()
            assert event.event_type == "CANDLE_UNDER_CANDLE_EXIT"


class TestTradeEventServiceMarketContext:
    """Test market context capture."""
    
    def test_market_context_captures_spy(self, db_session):
        """Market context should capture SPY price and change."""
        from nexus2.domain.automation.trade_event_service import TradeEventService
        
        service = TradeEventService()
        
        # Mock UnifiedMarketData
        mock_quote = MagicMock()
        mock_quote.price = 590.50
        mock_quote.open = 592.00  # Down from open
        
        mock_vix_quote = MagicMock()
        mock_vix_quote.price = 18.5
        
        mock_umd = MagicMock()
        mock_umd.get_quote.side_effect = lambda sym: mock_quote if sym == "SPY" else mock_vix_quote
        
        with patch("nexus2.domain.automation.trade_event_service.UnifiedMarketData", return_value=mock_umd):
            context = service._get_market_context()
        
        assert "spy_price" in context
        assert context["spy_price"] == 590.50
        assert "spy_change_pct" in context
        # (590.50 - 592.00) / 592.00 * 100 = -0.25%
        assert abs(context["spy_change_pct"] - (-0.25)) < 0.01
    
    def test_market_context_handles_missing_data(self, db_session):
        """Market context should return empty dict on failure."""
        from nexus2.domain.automation.trade_event_service import TradeEventService
        
        service = TradeEventService()
        
        mock_umd = MagicMock()
        mock_umd.get_quote.return_value = None  # No data
        
        with patch("nexus2.domain.automation.trade_event_service.UnifiedMarketData", return_value=mock_umd):
            context = service._get_market_context()
        
        # Should not crash, just return partial context
        assert isinstance(context, dict)


class TestTradeEventServiceQueries:
    """Test event query methods."""
    
    def test_get_events_for_position(self, db_session):
        """Should retrieve all events for a specific position."""
        from nexus2.domain.automation.trade_event_service import TradeEventService
        
        service = TradeEventService()
        position_id = "test-pos-query"
        
        with patch.object(service, "_get_market_context", return_value={}):
            # Log entry
            service.log_nac_entry(
                position_id=position_id,
                symbol="TEST",
                entry_price=Decimal("100.00"),
                stop_price=Decimal("95.00"),
                shares=50,
            )
            
            # Log stop move
            service.log_nac_stop_moved(
                position_id=position_id,
                symbol="TEST",
                old_stop=Decimal("95.00"),
                new_stop=Decimal("98.00"),
                reason="Breakeven",
            )
        
        events = service.get_events_for_position(position_id)
        
        assert len(events) == 2
        assert events[0]["event_type"] == "ENTRY"
        assert events[1]["event_type"] == "STOP_MOVED"
    
    def test_get_recent_events_filters_by_strategy(self, db_session):
        """Should filter recent events by strategy."""
        from nexus2.domain.automation.trade_event_service import TradeEventService
        
        service = TradeEventService()
        
        with patch.object(service, "_get_market_context", return_value={}):
            # Log NAC entry
            service.log_nac_entry(
                position_id="nac-pos",
                symbol="NAC_STOCK",
                entry_price=Decimal("100.00"),
                stop_price=Decimal("95.00"),
                shares=50,
            )
            
            # Log Warrior entry
            service.log_warrior_entry(
                position_id="war-pos",
                symbol="WAR_STOCK",
                entry_price=Decimal("50.00"),
                stop_price=Decimal("48.00"),
                shares=100,
            )
        
        nac_events = service.get_recent_events(strategy="NAC", limit=10)
        warrior_events = service.get_recent_events(strategy="WARRIOR", limit=10)
        all_events = service.get_recent_events(limit=10)
        
        assert len(nac_events) == 1
        assert nac_events[0]["symbol"] == "NAC_STOCK"
        
        assert len(warrior_events) == 1
        assert warrior_events[0]["symbol"] == "WAR_STOCK"
        
        assert len(all_events) == 2
