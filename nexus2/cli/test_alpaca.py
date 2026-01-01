"""
Alpaca Connectivity Test

Quick smoke test to verify Alpaca paper trading credentials work.
Run from project root: python -m nexus2.cli.test_alpaca
"""

import sys

def main():
    print("=" * 60)
    print("Alpaca Paper Trading Connectivity Test")
    print("=" * 60)
    
    # Check config
    from nexus2 import config as app_config
    
    print(f"\n[1] Checking credentials...")
    if not app_config.ALPACA_KEY or not app_config.ALPACA_SECRET:
        print("    ❌ ALPACA_KEY or ALPACA_SECRET not found in .env")
        print("    Set ALPACA_KEY and ALPACA_SECRET in your .env file")
        return 1
    
    print(f"    ✅ ALPACA_KEY: {app_config.ALPACA_KEY[:8]}...")
    print(f"    ✅ ALPACA_SECRET: {app_config.ALPACA_SECRET[:4]}...")
    
    # Test broker connection
    print(f"\n[2] Testing AlpacaBroker (paper mode)...")
    try:
        from nexus2.adapters.broker import AlpacaBroker, AlpacaBrokerConfig
        
        broker = AlpacaBroker(AlpacaBrokerConfig(
            api_key=app_config.ALPACA_KEY,
            api_secret=app_config.ALPACA_SECRET,
            paper=True,
        ))
        
        print("    ✅ AlpacaBroker created")
    except Exception as e:
        print(f"    ❌ Failed to create broker: {e}")
        return 1
    
    # Get account info
    print(f"\n[3] Getting account info...")
    try:
        account_value = broker.get_account_value()
        print(f"    ✅ Account value: ${account_value:,.2f}")
    except Exception as e:
        print(f"    ❌ Failed to get account: {e}")
        return 1
    
    # Get positions
    print(f"\n[4] Getting positions...")
    try:
        positions = broker.get_positions()
        if positions:
            print(f"    ✅ Found {len(positions)} open position(s):")
            for symbol, pos in positions.items():
                print(f"       - {symbol}: {pos.quantity} shares @ ${pos.avg_price:.2f}")
        else:
            print("    ✅ No open positions (fresh paper account)")
    except Exception as e:
        print(f"    ❌ Failed to get positions: {e}")
        return 1
    
    print("\n" + "=" * 60)
    print("✅ All connectivity tests passed!")
    print("   Alpaca paper trading is ready.")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
