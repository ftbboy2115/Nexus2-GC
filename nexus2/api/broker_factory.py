"""
Broker Factory

Creates broker instances based on type and account settings.
Separated from main.py to avoid circular imports.
"""

from nexus2.adapters.broker import (
    PaperBroker,
    PaperBrokerConfig,
    AlpacaBroker,
    AlpacaBrokerConfig,
)
from nexus2 import config as app_config


def create_broker_by_type(broker_type: str, active_account: str = "A"):
    """
    Create broker based on broker_type setting.
    
    This can be called at runtime to switch brokers.
    
    Args:
        broker_type: "paper" or "alpaca_paper"
        active_account: "A" or "B" for Alpaca accounts
    
    Returns:
        Broker instance
    """
    import os
    
    # Force paper broker in tests
    if os.environ.get("FORCE_PAPER_BROKER", "").lower() == "true":
        print("[Broker] Mode: paper (forced by FORCE_PAPER_BROKER)")
        return PaperBroker(PaperBrokerConfig())
    
    # Get credentials for the specified account
    if active_account.upper() == "B":
        api_key = app_config.ALPACA_KEY_B
        api_secret = app_config.ALPACA_SECRET_B
    else:
        api_key = app_config.ALPACA_KEY
        api_secret = app_config.ALPACA_SECRET
    
    if broker_type == "paper":
        print("[Broker] Mode: paper (PaperBroker - local simulation)")
        return PaperBroker(PaperBrokerConfig())
    
    if broker_type == "alpaca_paper":
        if not api_key or not api_secret:
            print(f"[Broker] WARNING: Alpaca credentials not found for Account {active_account}, falling back to paper")
            return PaperBroker(PaperBrokerConfig())
        
        print(f"[Broker] Mode: alpaca_paper (Account {active_account})")
        return AlpacaBroker(AlpacaBrokerConfig(
            api_key=api_key,
            api_secret=api_secret,
            paper=True,
        ))
    
    # Unknown or disabled type - default to paper
    print(f"[Broker] Unknown broker_type '{broker_type}', defaulting to paper")
    return PaperBroker(PaperBrokerConfig())
