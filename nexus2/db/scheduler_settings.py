"""
NAC Scheduler Settings Persistence

Saves and loads automation scheduler configuration to/from a JSON file.
"""

import json
from pathlib import Path
from typing import Optional


# Settings file location
SETTINGS_FILE = Path(__file__).parent.parent.parent / "data" / "scheduler_settings.json"


def save_scheduler_settings(settings: dict) -> bool:
    """Save scheduler settings to JSON file.
    
    Args:
        settings: Dictionary of settings to save
        
    Returns:
        True if saved successfully
    """
    try:
        # Ensure data directory exists
        SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        
        with open(SETTINGS_FILE, 'w') as f:
            json.dump(settings, f, indent=2)
        
        print(f"[Scheduler Settings] Saved to {SETTINGS_FILE}")
        return True
        
    except Exception as e:
        print(f"[Scheduler Settings] Save failed: {e}")
        return False


def load_scheduler_settings() -> Optional[dict]:
    """Load scheduler settings from JSON file.
    
    Returns:
        Dictionary of settings, or None if file doesn't exist
    """
    try:
        if not SETTINGS_FILE.exists():
            print(f"[Scheduler Settings] No settings file found")
            return None
        
        with open(SETTINGS_FILE, 'r') as f:
            settings = json.load(f)
        
        print(f"[Scheduler Settings] Loaded: {settings}")
        return settings
        
    except Exception as e:
        print(f"[Scheduler Settings] Load failed: {e}")
        return None


def get_scheduler_settings_dict(scheduler) -> dict:
    """Convert scheduler state to a saveable dictionary.
    
    Args:
        scheduler: AutomationScheduler instance
        
    Returns:
        Dictionary of settings
    """
    return {
        "interval_minutes": scheduler.interval_minutes,
        "auto_execute": scheduler.auto_execute,
    }
