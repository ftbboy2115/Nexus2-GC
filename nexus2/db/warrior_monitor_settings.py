"""
Warrior Monitor Settings Persistence

Saves and loads Warrior monitor settings (including scaling) to/from a JSON file.
"""

import json
from pathlib import Path
from decimal import Decimal
from typing import Optional


# Settings file location
MONITOR_SETTINGS_FILE = Path(__file__).parent.parent.parent / "data" / "warrior_monitor_settings.json"


def save_monitor_settings(settings: dict) -> bool:
    """Save monitor settings to JSON file.
    
    Returns:
        True if saved successfully
    """
    try:
        # Ensure data directory exists
        MONITOR_SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        
        # Convert Decimals to floats for JSON
        serializable = {}
        for key, value in settings.items():
            if isinstance(value, Decimal):
                serializable[key] = float(value)
            else:
                serializable[key] = value
        
        with open(MONITOR_SETTINGS_FILE, 'w') as f:
            json.dump(serializable, f, indent=2)
        
        print(f"[Warrior Monitor Settings] Saved to {MONITOR_SETTINGS_FILE}")
        return True
        
    except Exception as e:
        print(f"[Warrior Monitor Settings] Save failed: {e}")
        return False


def load_monitor_settings() -> Optional[dict]:
    """Load monitor settings from JSON file.
    
    Returns:
        Dictionary of settings, or None if file doesn't exist
    """
    try:
        if not MONITOR_SETTINGS_FILE.exists():
            return None
        
        with open(MONITOR_SETTINGS_FILE, 'r') as f:
            return json.load(f)
        
    except Exception as e:
        print(f"[Warrior Monitor Settings] Load failed: {e}")
        return None


def apply_monitor_settings(monitor_settings_obj, settings: dict) -> None:
    """Apply loaded settings to a WarriorMonitorSettings instance.
    
    Args:
        monitor_settings_obj: WarriorMonitorSettings dataclass instance
        settings: Dictionary of settings to apply
    """
    # Core settings
    if "mental_stop_cents" in settings:
        monitor_settings_obj.mental_stop_cents = Decimal(str(settings["mental_stop_cents"]))
    if "profit_target_r" in settings:
        monitor_settings_obj.profit_target_r = settings["profit_target_r"]
    if "profit_target_cents" in settings:
        monitor_settings_obj.profit_target_cents = Decimal(str(settings["profit_target_cents"]))
    if "partial_exit_fraction" in settings:
        monitor_settings_obj.partial_exit_fraction = settings["partial_exit_fraction"]
    
    # Scaling settings (Ross Cameron methodology)
    if "enable_scaling" in settings:
        monitor_settings_obj.enable_scaling = settings["enable_scaling"]
    if "max_scale_count" in settings:
        monitor_settings_obj.max_scale_count = settings["max_scale_count"]
    if "scale_size_pct" in settings:
        monitor_settings_obj.scale_size_pct = settings["scale_size_pct"]
    if "min_rvol_for_scale" in settings:
        monitor_settings_obj.min_rvol_for_scale = settings["min_rvol_for_scale"]
    if "allow_scale_below_entry" in settings:
        monitor_settings_obj.allow_scale_below_entry = settings["allow_scale_below_entry"]
    if "move_stop_to_breakeven_after_scale" in settings:
        monitor_settings_obj.move_stop_to_breakeven_after_scale = settings["move_stop_to_breakeven_after_scale"]
    
    print(f"[Warrior Monitor Settings] Applied: enable_scaling={monitor_settings_obj.enable_scaling}")


def get_monitor_settings_dict(monitor_settings_obj) -> dict:
    """Convert WarriorMonitorSettings to a saveable dictionary."""
    return {
        "mental_stop_cents": float(monitor_settings_obj.mental_stop_cents),
        "profit_target_r": monitor_settings_obj.profit_target_r,
        "profit_target_cents": float(monitor_settings_obj.profit_target_cents),
        "partial_exit_fraction": monitor_settings_obj.partial_exit_fraction,
        "use_technical_stop": monitor_settings_obj.use_technical_stop,
        # NOTE: move_stop_to_breakeven REMOVED (KK methodology, not Ross Cameron)
        "enable_candle_under_candle": monitor_settings_obj.enable_candle_under_candle,
        "enable_topping_tail": monitor_settings_obj.enable_topping_tail,
        "topping_tail_threshold": monitor_settings_obj.topping_tail_threshold,
        "check_interval_seconds": monitor_settings_obj.check_interval_seconds,
        # Scaling settings
        "enable_scaling": monitor_settings_obj.enable_scaling,
        "max_scale_count": monitor_settings_obj.max_scale_count,
        "scale_size_pct": monitor_settings_obj.scale_size_pct,
        "min_rvol_for_scale": monitor_settings_obj.min_rvol_for_scale,
        "allow_scale_below_entry": monitor_settings_obj.allow_scale_below_entry,
        "move_stop_to_breakeven_after_scale": monitor_settings_obj.move_stop_to_breakeven_after_scale,
    }
