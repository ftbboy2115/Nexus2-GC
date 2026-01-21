"""
Unit tests for R&D Lab strategy schema and registry.
"""

import pytest
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
import tempfile
import shutil

from nexus2.domain.lab import (
    StrategySpec,
    StrategyStatus,
    ScannerConfig,
    EngineConfig,
    MonitorConfig,
)
from nexus2.domain.lab.strategy_registry import StrategyRegistry


class TestStrategySchema:
    """Test strategy schema Pydantic models."""
    
    def test_scanner_config_defaults(self):
        """Test ScannerConfig has sensible defaults."""
        config = ScannerConfig()
        
        assert config.min_price == Decimal("2.00")
        assert config.min_volume == 500_000
        assert config.min_rvol == 2.0
        assert config.require_catalyst is True
    
    def test_engine_config_defaults(self):
        """Test EngineConfig has sensible defaults."""
        config = EngineConfig()
        
        assert config.entry_triggers == ["ORB", "PMH_BREAK"]
        assert config.trading_start == "09:30"
        assert config.trading_end == "11:30"
        assert config.max_positions == 3
    
    def test_monitor_config_defaults(self):
        """Test MonitorConfig has sensible defaults."""
        config = MonitorConfig()
        
        assert config.stop_mode == "mental"
        assert config.stop_cents == 15
        assert config.target_r == 2.0
        assert config.scaling_enabled is True
    
    def test_strategy_spec_minimal(self):
        """Test creating StrategySpec with minimal required fields."""
        spec = StrategySpec(name="test_strategy", version="1.0.0")
        
        assert spec.name == "test_strategy"
        assert spec.version == "1.0.0"
        assert spec.status == StrategyStatus.DRAFT
        assert isinstance(spec.scanner, ScannerConfig)
        assert isinstance(spec.engine, EngineConfig)
        assert isinstance(spec.monitor, MonitorConfig)
    
    def test_strategy_spec_full(self):
        """Test creating StrategySpec with all fields."""
        spec = StrategySpec(
            name="lab_warrior",
            version="1.1.0",
            description="Experimental Warrior variant",
            author="Clay",
            status=StrategyStatus.TESTING,
            based_on="warrior",
            based_on_version="1.0.0",
            scanner=ScannerConfig(min_price=Decimal("3.00")),
            engine=EngineConfig(max_positions=5),
            monitor=MonitorConfig(stop_cents=20),
            hypothesis="Testing tighter stops",
        )
        
        assert spec.name == "lab_warrior"
        assert spec.based_on == "warrior"
        assert spec.scanner.min_price == Decimal("3.00")
        assert spec.engine.max_positions == 5
        assert spec.monitor.stop_cents == 20
    
    def test_strategy_spec_json_serialization(self):
        """Test StrategySpec can be serialized to JSON."""
        spec = StrategySpec(name="test", version="1.0.0")
        
        json_data = spec.model_dump(mode="json")
        
        assert json_data["name"] == "test"
        assert json_data["version"] == "1.0.0"
        assert "scanner" in json_data
        assert "engine" in json_data
        assert "monitor" in json_data


class TestStrategyRegistry:
    """Test strategy registry load/save operations."""
    
    @pytest.fixture
    def temp_registry(self, tmp_path):
        """Create a registry with temporary directory."""
        registry = StrategyRegistry(base_dir=tmp_path / "strategies")
        return registry
    
    def test_list_strategies_empty(self, temp_registry):
        """Test listing strategies when none exist."""
        strategies = temp_registry.list_strategies()
        assert strategies == []
    
    def test_save_and_load_strategy(self, temp_registry):
        """Test saving and loading a strategy."""
        spec = StrategySpec(
            name="test_strat",
            version="1.0.0",
            description="Test strategy",
        )
        
        # Save
        success = temp_registry.save_strategy(spec)
        assert success is True
        
        # Load
        loaded = temp_registry.load_strategy("test_strat", "1.0.0")
        assert loaded is not None
        assert loaded.name == "test_strat"
        assert loaded.version == "1.0.0"
    
    def test_list_strategies_after_save(self, temp_registry):
        """Test listing strategies after saving."""
        spec = StrategySpec(name="my_strat", version="1.0.0")
        temp_registry.save_strategy(spec)
        
        strategies = temp_registry.list_strategies()
        
        assert len(strategies) == 1
        assert strategies[0]["name"] == "my_strat"
        assert strategies[0]["latest"] == "1.0.0"
    
    def test_load_latest_version(self, temp_registry):
        """Test loading latest version when multiple exist."""
        # Save v1.0.0
        spec1 = StrategySpec(name="versioned", version="1.0.0")
        temp_registry.save_strategy(spec1)
        
        # Save v1.1.0
        spec2 = StrategySpec(name="versioned", version="1.1.0")
        temp_registry.save_strategy(spec2)
        
        # Load without version = latest
        loaded = temp_registry.load_strategy("versioned")
        assert loaded.version == "1.1.0"
    
    def test_save_duplicate_version_fails(self, temp_registry):
        """Test that saving duplicate version fails (immutable)."""
        spec = StrategySpec(name="immutable", version="1.0.0")
        
        # First save succeeds
        assert temp_registry.save_strategy(spec) is True
        
        # Second save fails
        assert temp_registry.save_strategy(spec) is False
    
    def test_load_nonexistent_strategy(self, temp_registry):
        """Test loading a strategy that doesn't exist."""
        loaded = temp_registry.load_strategy("nonexistent")
        assert loaded is None
    
    def test_strategy_exists(self, temp_registry):
        """Test checking if strategy version exists."""
        spec = StrategySpec(name="exists_test", version="1.0.0")
        temp_registry.save_strategy(spec)
        
        assert temp_registry.strategy_exists("exists_test", "1.0.0") is True
        assert temp_registry.strategy_exists("exists_test", "2.0.0") is False
        assert temp_registry.strategy_exists("other", "1.0.0") is False


class TestProductionStrategies:
    """Test loading production baseline strategies."""
    
    def test_load_warrior_baseline(self):
        """Test loading the Warrior v1.0.0 baseline."""
        from nexus2.domain.lab.strategy_registry import get_registry
        
        registry = get_registry()
        warrior = registry.load_strategy("warrior", "1.0.0")
        
        assert warrior is not None
        assert warrior.name == "warrior"
        assert warrior.version == "1.0.0"
        assert warrior.status == StrategyStatus.PRODUCTION
    
    def test_load_kk_ep_baseline(self):
        """Test loading the KK EP v1.0.0 baseline."""
        from nexus2.domain.lab.strategy_registry import get_registry
        
        registry = get_registry()
        kk_ep = registry.load_strategy("kk_ep", "1.0.0")
        
        assert kk_ep is not None
        assert kk_ep.name == "kk_ep"
        assert kk_ep.version == "1.0.0"
        assert kk_ep.status == StrategyStatus.PRODUCTION
