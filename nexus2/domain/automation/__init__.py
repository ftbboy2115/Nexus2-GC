"""
Automation Domain Module
"""

from .engine import AutomationEngine
from .signals import Signal, SignalGenerator, SetupType
from .scheduler import AutomationScheduler
from .monitor import PositionMonitor, ExitSignal, ExitReason
from .services import create_scanner_callback, create_order_callback, create_position_callback
from .unified_scanner import (
    UnifiedScannerService,
    UnifiedScanSettings,
    UnifiedScanResult,
    ScanMode,
    get_unified_scanner_service,
)

__all__ = [
    "AutomationEngine", 
    "Signal", 
    "SignalGenerator",
    "SetupType",
    "AutomationScheduler",
    "PositionMonitor",
    "ExitSignal",
    "ExitReason",
    "create_scanner_callback",
    "create_order_callback", 
    "create_position_callback",
    # Unified Scanner
    "UnifiedScannerService",
    "UnifiedScanSettings",
    "UnifiedScanResult",
    "ScanMode",
    "get_unified_scanner_service",
]
