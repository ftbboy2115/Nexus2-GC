"""
Warrior Scanner Settings Persistence

Saves and loads Warrior scanner settings to/from a JSON file.
Follows the same pattern as warrior_monitor_settings.py.
"""

import json
from pathlib import Path
from decimal import Decimal
from typing import Optional


# Settings file location
SCANNER_SETTINGS_FILE = Path(__file__).parent.parent.parent / "data" / "warrior_scanner_settings.json"


def save_scanner_settings(settings: dict) -> bool:
    """Save scanner settings to JSON file.
    
    Returns:
        True if saved successfully
    """
    try:
        # Ensure data directory exists
        SCANNER_SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        
        # Convert Decimals to floats for JSON
        serializable = {}
        for key, value in settings.items():
            if isinstance(value, Decimal):
                serializable[key] = float(value)
            elif isinstance(value, list):
                serializable[key] = value
            else:
                serializable[key] = value
        
        with open(SCANNER_SETTINGS_FILE, 'w') as f:
            json.dump(serializable, f, indent=2)
        
        print(f"[Warrior Scanner Settings] Saved to {SCANNER_SETTINGS_FILE}")
        return True
        
    except Exception as e:
        print(f"[Warrior Scanner Settings] Save failed: {e}")
        return False


def load_scanner_settings() -> Optional[dict]:
    """Load scanner settings from JSON file.
    
    Returns:
        Dictionary of settings, or None if file doesn't exist
    """
    try:
        if not SCANNER_SETTINGS_FILE.exists():
            return None
        
        with open(SCANNER_SETTINGS_FILE, 'r') as f:
            return json.load(f)
        
    except Exception as e:
        print(f"[Warrior Scanner Settings] Load failed: {e}")
        return None


def apply_scanner_settings(scan_settings_obj, settings: dict) -> None:
    """Apply loaded settings to a WarriorScanSettings instance.
    
    Args:
        scan_settings_obj: WarriorScanSettings dataclass instance
        settings: Dictionary of settings to apply
    """
    # Pillar 1: Float
    if "max_float" in settings:
        scan_settings_obj.max_float = settings["max_float"]
    if "ideal_float" in settings:
        scan_settings_obj.ideal_float = settings["ideal_float"]
    
    # Pillar 2: Relative Volume
    if "min_rvol" in settings:
        scan_settings_obj.min_rvol = Decimal(str(settings["min_rvol"]))
    if "ideal_rvol" in settings:
        scan_settings_obj.ideal_rvol = Decimal(str(settings["ideal_rvol"]))
    
    # Pillar 4: Price Range
    if "min_price" in settings:
        scan_settings_obj.min_price = Decimal(str(settings["min_price"]))
    if "max_price" in settings:
        scan_settings_obj.max_price = Decimal(str(settings["max_price"]))
    
    # Pillar 5: Gap
    if "min_gap" in settings:
        scan_settings_obj.min_gap = Decimal(str(settings["min_gap"]))
    if "ideal_gap" in settings:
        scan_settings_obj.ideal_gap = Decimal(str(settings["ideal_gap"]))
    
    # Additional filters
    if "require_catalyst" in settings:
        scan_settings_obj.require_catalyst = settings["require_catalyst"]
    if "exclude_chinese_stocks" in settings:
        scan_settings_obj.exclude_chinese_stocks = settings["exclude_chinese_stocks"]
    
    print(f"[Warrior Scanner Settings] Applied: min_rvol={scan_settings_obj.min_rvol}, max_price={scan_settings_obj.max_price}")


def get_scanner_settings_dict(scan_settings_obj) -> dict:
    """Convert WarriorScanSettings to a saveable dictionary."""
    return {
        "max_float": scan_settings_obj.max_float,
        "ideal_float": scan_settings_obj.ideal_float,
        "min_rvol": float(scan_settings_obj.min_rvol),
        "ideal_rvol": float(scan_settings_obj.ideal_rvol),
        "min_gap": float(scan_settings_obj.min_gap),
        "ideal_gap": float(scan_settings_obj.ideal_gap),
        "min_price": float(scan_settings_obj.min_price),
        "max_price": float(scan_settings_obj.max_price),
        "require_catalyst": scan_settings_obj.require_catalyst,
        "exclude_chinese_stocks": scan_settings_obj.exclude_chinese_stocks,
    }
