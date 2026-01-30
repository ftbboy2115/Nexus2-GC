"""
Strategy Registry - Load, save, and list strategies.

Provides versioned, immutable strategy storage in YAML format.
"""

import logging
import yaml
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any

from .strategy_schema import StrategySpec, StrategyStatus
from nexus2.utils.time_utils import now_utc


logger = logging.getLogger(__name__)

# Strategy storage directory
STRATEGIES_DIR = Path(__file__).parent.parent.parent / "strategies"


class StrategyRegistry:
    """Registry for managing lab strategies.
    
    Strategies are stored as YAML files in:
    nexus2/strategies/{strategy_name}/v{version}.yaml
    """
    
    def __init__(self, base_dir: Path = None):
        self.base_dir = base_dir or STRATEGIES_DIR
        self.base_dir.mkdir(parents=True, exist_ok=True)
    
    def list_strategies(self) -> List[Dict[str, Any]]:
        """List all available strategies with their versions.
        
        Returns:
            List of dicts: [{"name": "warrior", "versions": ["1.0.0", "1.1.0"]}]
        """
        strategies = []
        
        if not self.base_dir.exists():
            return strategies
        
        for strategy_dir in self.base_dir.iterdir():
            if not strategy_dir.is_dir():
                continue
            
            versions = []
            for yaml_file in strategy_dir.glob("v*.yaml"):
                # Extract version from filename (v1.0.0.yaml -> 1.0.0)
                version = yaml_file.stem[1:]  # Remove leading 'v'
                versions.append(version)
            
            if versions:
                # Sort by semantic version
                versions.sort(key=lambda v: [int(x) for x in v.split(".")])
                strategies.append({
                    "name": strategy_dir.name,
                    "versions": versions,
                    "latest": versions[-1],
                })
        
        return strategies
    
    def load_strategy(
        self, 
        name: str, 
        version: Optional[str] = None
    ) -> Optional[StrategySpec]:
        """Load a strategy by name and optional version.
        
        Args:
            name: Strategy name (e.g., "warrior")
            version: Specific version or None for latest
            
        Returns:
            StrategySpec or None if not found
        """
        strategy_dir = self.base_dir / name
        
        if not strategy_dir.exists():
            logger.warning(f"Strategy directory not found: {name}")
            return None
        
        # Find version file
        if version:
            yaml_path = strategy_dir / f"v{version}.yaml"
        else:
            # Get latest version
            versions = list(strategy_dir.glob("v*.yaml"))
            if not versions:
                logger.warning(f"No versions found for strategy: {name}")
                return None
            
            # Sort and get latest
            versions.sort(key=lambda p: [int(x) for x in p.stem[1:].split(".")])
            yaml_path = versions[-1]
        
        if not yaml_path.exists():
            logger.warning(f"Strategy file not found: {yaml_path}")
            return None
        
        try:
            with open(yaml_path, "r") as f:
                data = yaml.safe_load(f)
            
            return StrategySpec(**data)
        except Exception as e:
            logger.error(f"Failed to load strategy {name}: {e}")
            return None
    
    def save_strategy(self, spec: StrategySpec) -> bool:
        """Save a strategy to disk.
        
        Creates directory if needed. Updates timestamps.
        
        Args:
            spec: Strategy specification to save
            
        Returns:
            True if saved successfully
        """
        strategy_dir = self.base_dir / spec.name
        strategy_dir.mkdir(parents=True, exist_ok=True)
        
        yaml_path = strategy_dir / f"v{spec.version}.yaml"
        
        # Check if version already exists (immutable)
        if yaml_path.exists():
            logger.error(f"Strategy version already exists: {spec.name} v{spec.version}")
            return False
        
        try:
            # Update timestamp
            spec.updated_at = now_utc()
            
            # Convert to dict for YAML
            data = spec.model_dump(mode="json")
            
            with open(yaml_path, "w") as f:
                yaml.dump(data, f, default_flow_style=False, sort_keys=False)
            
            logger.info(f"Saved strategy: {spec.name} v{spec.version}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save strategy {spec.name}: {e}")
            return False
    
    def get_strategy_path(self, name: str, version: str) -> Path:
        """Get the file path for a strategy version."""
        return self.base_dir / name / f"v{version}.yaml"
    
    def strategy_exists(self, name: str, version: str) -> bool:
        """Check if a specific strategy version exists."""
        return self.get_strategy_path(name, version).exists()
    
    def get_next_version(self, name: str) -> str:
        """Get the next version number for a strategy.
        
        If strategy doesn't exist, returns "1.0.0".
        If latest is "1.0.0", returns "2.0.0".
        """
        strategy_dir = self.base_dir / name
        if not strategy_dir.exists():
            return "1.0.0"
        
        versions = list(strategy_dir.glob("v*.yaml"))
        if not versions:
            return "1.0.0"
        
        # Get highest version
        versions.sort(key=lambda p: [int(x) for x in p.stem[1:].split(".")])
        latest = versions[-1].stem[1:]  # e.g., "1.0.0"
        major = int(latest.split(".")[0])
        return f"{major + 1}.0.0"


# Singleton instance
_registry: Optional[StrategyRegistry] = None


def get_registry() -> StrategyRegistry:
    """Get the singleton strategy registry."""
    global _registry
    if _registry is None:
        _registry = StrategyRegistry()
    return _registry
