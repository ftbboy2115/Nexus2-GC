"""
Warrior Trading Settings Persistence

Saves and loads Warrior engine configuration to/from a JSON file.
"""

import json
from pathlib import Path
from decimal import Decimal
from typing import Optional


# Settings file location
SETTINGS_FILE = Path(__file__).parent.parent.parent / "data" / "warrior_settings.json"


def save_warrior_settings(config: dict) -> bool:
    """Save Warrior engine settings to JSON file.
    
    Args:
        config: Dictionary of settings to save
        
    Returns:
        True if saved successfully
    """
    try:
        # Ensure data directory exists
        SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        
        # Convert Decimals to floats for JSON
        serializable = {}
        for key, value in config.items():
            if isinstance(value, Decimal):
                serializable[key] = float(value)
            elif isinstance(value, set):
                serializable[key] = list(value)
            else:
                serializable[key] = value
        
        with open(SETTINGS_FILE, 'w') as f:
            json.dump(serializable, f, indent=2)
        
        print(f"[Warrior Settings] Saved to {SETTINGS_FILE}")
        return True
        
    except Exception as e:
        print(f"[Warrior Settings] Save failed: {e}")
        return False


def load_warrior_settings() -> Optional[dict]:
    """Load Warrior engine settings from JSON file.
    
    Returns:
        Dictionary of settings, or None if file doesn't exist
    """
    try:
        if not SETTINGS_FILE.exists():
            print(f"[Warrior Settings] No settings file found")
            return None
        
        with open(SETTINGS_FILE, 'r') as f:
            settings = json.load(f)
        
        # Convert lists back to sets where needed
        if 'static_blacklist' in settings and isinstance(settings['static_blacklist'], list):
            settings['static_blacklist'] = set(settings['static_blacklist'])
        
        print(f"[Warrior Settings] Loaded from {SETTINGS_FILE}")
        return settings
        
    except Exception as e:
        print(f"[Warrior Settings] Load failed: {e}")
        return None


def get_config_dict(config) -> dict:
    """Convert WarriorEngineConfig to a saveable dictionary.
    
    Args:
        config: WarriorEngineConfig dataclass instance
        
    Returns:
        Dictionary of settings
    """
    return {
        "max_positions": config.max_positions,
        "max_daily_loss": float(config.max_daily_loss),
        "risk_per_trade": float(config.risk_per_trade),
        "max_capital": float(config.max_capital),
        "max_candidates": config.max_candidates,
        "scanner_interval_minutes": config.scanner_interval_minutes,
        "orb_enabled": config.orb_enabled,
        "pmh_enabled": config.pmh_enabled,
        "max_shares_per_trade": config.max_shares_per_trade,
        "max_value_per_trade": float(config.max_value_per_trade) if config.max_value_per_trade else None,
        "static_blacklist": list(config.static_blacklist),
    }


def apply_settings_to_config(config, settings: dict) -> None:
    """Apply loaded settings to a WarriorEngineConfig instance.
    
    Args:
        config: WarriorEngineConfig dataclass instance to update
        settings: Dictionary of settings to apply
    """
    if "max_positions" in settings:
        config.max_positions = settings["max_positions"]
    if "max_daily_loss" in settings:
        config.max_daily_loss = Decimal(str(settings["max_daily_loss"]))
    if "risk_per_trade" in settings:
        config.risk_per_trade = Decimal(str(settings["risk_per_trade"]))
    if "max_capital" in settings:
        config.max_capital = Decimal(str(settings["max_capital"]))
    if "max_candidates" in settings:
        config.max_candidates = settings["max_candidates"]
    if "scanner_interval_minutes" in settings:
        config.scanner_interval_minutes = settings["scanner_interval_minutes"]
    if "orb_enabled" in settings:
        config.orb_enabled = settings["orb_enabled"]
    if "pmh_enabled" in settings:
        config.pmh_enabled = settings["pmh_enabled"]
    if "max_shares_per_trade" in settings:
        config.max_shares_per_trade = settings["max_shares_per_trade"]
    if "max_value_per_trade" in settings and settings["max_value_per_trade"] is not None:
        config.max_value_per_trade = Decimal(str(settings["max_value_per_trade"]))
    if "static_blacklist" in settings:
        config.static_blacklist = set(settings["static_blacklist"])
    
    print(f"[Warrior Settings] Applied: max_positions={config.max_positions}, max_shares={config.max_shares_per_trade}")
