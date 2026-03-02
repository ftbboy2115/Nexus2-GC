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
    if "enable_partial_then_ride" in settings:
        monitor_settings_obj.enable_partial_then_ride = settings["enable_partial_then_ride"]
    if "trail_activation_pct" in settings:
        monitor_settings_obj.trail_activation_pct = settings["trail_activation_pct"]
    if "base_hit_profit_pct" in settings:
        monitor_settings_obj.base_hit_profit_pct = settings["base_hit_profit_pct"]
    # Fix 3: Structural profit levels
    if "enable_structural_levels" in settings:
        monitor_settings_obj.enable_structural_levels = settings["enable_structural_levels"]
    if "structural_level_increment" in settings:
        monitor_settings_obj.structural_level_increment = settings["structural_level_increment"]
    if "structural_level_min_distance_cents" in settings:
        monitor_settings_obj.structural_level_min_distance_cents = settings["structural_level_min_distance_cents"]
    # Fix 4: Improved home run trail
    if "enable_improved_home_run_trail" in settings:
        monitor_settings_obj.enable_improved_home_run_trail = settings["enable_improved_home_run_trail"]
    if "home_run_stop_after_partial" in settings:
        monitor_settings_obj.home_run_stop_after_partial = settings["home_run_stop_after_partial"]
    if "home_run_skip_topping_tail" in settings:
        monitor_settings_obj.home_run_skip_topping_tail = settings["home_run_skip_topping_tail"]
    if "home_run_candle_trail_enabled" in settings:
        monitor_settings_obj.home_run_candle_trail_enabled = settings["home_run_candle_trail_enabled"]
    if "home_run_candle_trail_lookback" in settings:
        monitor_settings_obj.home_run_candle_trail_lookback = settings["home_run_candle_trail_lookback"]
    # Fix 5: Improved scaling
    if "enable_improved_scaling" in settings:
        monitor_settings_obj.enable_improved_scaling = settings["enable_improved_scaling"]
    # Scaling v2: Level-break scaling
    if "enable_level_break_scaling" in settings:
        monitor_settings_obj.enable_level_break_scaling = settings["enable_level_break_scaling"]
    if "level_break_increment" in settings:
        monitor_settings_obj.level_break_increment = settings["level_break_increment"]
    if "level_break_min_distance_cents" in settings:
        monitor_settings_obj.level_break_min_distance_cents = settings["level_break_min_distance_cents"]
    if "level_break_macd_gate" in settings:
        monitor_settings_obj.level_break_macd_gate = settings["level_break_macd_gate"]
    if "level_break_macd_tolerance" in settings:
        monitor_settings_obj.level_break_macd_tolerance = settings["level_break_macd_tolerance"]
    # Fix 6: Re-entry quality gate
    if "block_reentry_after_loss" in settings:
        monitor_settings_obj.block_reentry_after_loss = settings["block_reentry_after_loss"]
    if "max_reentry_count" in settings:
        monitor_settings_obj.max_reentry_count = settings["max_reentry_count"]
    # Fix 7: Graduated re-entry gate
    if "max_reentry_after_loss" in settings:
        monitor_settings_obj.max_reentry_after_loss = settings["max_reentry_after_loss"]
    # Guard toggles (for GC param sweep)
    if "enable_profit_check_guard" in settings:
        monitor_settings_obj.enable_profit_check_guard = settings["enable_profit_check_guard"]
    # Live re-entry cooldown
    if "live_reentry_cooldown_minutes" in settings:
        monitor_settings_obj.live_reentry_cooldown_minutes = settings["live_reentry_cooldown_minutes"]
    
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
        "enable_partial_then_ride": monitor_settings_obj.enable_partial_then_ride,
        "trail_activation_pct": monitor_settings_obj.trail_activation_pct,
        "base_hit_profit_pct": monitor_settings_obj.base_hit_profit_pct,
        # Fix 3: Structural profit levels
        "enable_structural_levels": monitor_settings_obj.enable_structural_levels,
        "structural_level_increment": monitor_settings_obj.structural_level_increment,
        "structural_level_min_distance_cents": monitor_settings_obj.structural_level_min_distance_cents,
        # Fix 4: Improved home run trail
        "enable_improved_home_run_trail": monitor_settings_obj.enable_improved_home_run_trail,
        "home_run_stop_after_partial": monitor_settings_obj.home_run_stop_after_partial,
        "home_run_skip_topping_tail": monitor_settings_obj.home_run_skip_topping_tail,
        "home_run_candle_trail_enabled": monitor_settings_obj.home_run_candle_trail_enabled,
        "home_run_candle_trail_lookback": monitor_settings_obj.home_run_candle_trail_lookback,
        # Fix 5: Improved scaling
        "enable_improved_scaling": monitor_settings_obj.enable_improved_scaling,
        # Scaling v2: Level-break scaling
        "enable_level_break_scaling": monitor_settings_obj.enable_level_break_scaling,
        "level_break_increment": monitor_settings_obj.level_break_increment,
        "level_break_min_distance_cents": monitor_settings_obj.level_break_min_distance_cents,
        "level_break_macd_gate": monitor_settings_obj.level_break_macd_gate,
        "level_break_macd_tolerance": monitor_settings_obj.level_break_macd_tolerance,
        # Fix 6: Re-entry quality gate
        "block_reentry_after_loss": monitor_settings_obj.block_reentry_after_loss,
        "max_reentry_count": monitor_settings_obj.max_reentry_count,
        # Fix 7: Graduated re-entry gate
        "max_reentry_after_loss": monitor_settings_obj.max_reentry_after_loss,
        # Guard toggles (for GC param sweep)
        "enable_profit_check_guard": monitor_settings_obj.enable_profit_check_guard,
        # Live re-entry cooldown
        "live_reentry_cooldown_minutes": monitor_settings_obj.live_reentry_cooldown_minutes,
    }
