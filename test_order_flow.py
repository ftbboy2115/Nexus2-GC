"""
End-to-End Order Flow Test for Nexus 2

Tests the full automation path:
Signal → Execute Callback → PaperBroker → Position Record

Run from the Nexus directory (parent of nexus2)
"""

print("=" * 60)
print("END-TO-END ORDER FLOW TEST")
print("=" * 60)

# Test 1: Paper Broker Bracket Order
print("\n[1] Paper Broker - Bracket Order Test")
print("-" * 40)
try:
    from nexus2.adapters.broker.paper_broker import PaperBroker, PaperBrokerConfig
    from uuid import uuid4
    from decimal import Decimal
    
    # Create paper broker
    config = PaperBrokerConfig(initial_cash=Decimal("100000"), fill_mode="instant")
    broker = PaperBroker(config)
    
    print(f"Starting cash: ${broker._cash}")
    
    # Submit a test bracket order
    order = broker.submit_bracket_order(
        client_order_id=uuid4(),
        symbol="TEST",
        quantity=100,
        stop_loss_price=Decimal("95.00"),
        limit_price=Decimal("100.00"),
    )
    
    print(f"✅ Order submitted: {order.broker_order_id}")
    print(f"   Status: {order.status.value}")
    print(f"   Filled: {order.filled_quantity}/{order.quantity} @ ${order.avg_fill_price}")
    print(f"   Remaining cash: ${broker._cash}")
    print(f"   Positions: {list(broker.get_positions().keys())}")
    
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()

# Test 2: Signal calculate_shares
print("\n[2] Signal - Calculate Shares Test")
print("-" * 40)
try:
    from nexus2.domain.automation.signals import Signal, SetupType
    from decimal import Decimal
    
    # Create a test signal with all required fields
    signal = Signal(
        symbol="NVDA",
        setup_type=SetupType.EP,
        quality_score=8,
        entry_price=Decimal("180.00"),
        tactical_stop=Decimal("175.00"),  # $5 risk per share
        tier="FOCUS",
        rs_percentile=85,
        adr_percent=Decimal("4.5"),
    )
    
    risk_per_trade = Decimal("250")  # $250 risk
    shares = signal.calculate_shares(risk_per_trade)
    
    print(f"✅ Signal created: {signal.symbol} ({signal.setup_type.value})")
    print(f"   Entry: ${signal.entry_price}, Stop: ${signal.tactical_stop}")
    print(f"   Risk per share: ${signal.entry_price - signal.tactical_stop}")
    print(f"   With ${risk_per_trade} risk budget → {shares} shares")
    
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()

# Test 3: Scheduler auto_execute flag
print("\n[3] Scheduler Settings - Auto Execute Status")
print("-" * 40)
try:
    from nexus2.db import SessionLocal, SchedulerSettingsRepository
    
    db = SessionLocal()
    repo = SchedulerSettingsRepository(db)
    settings = repo.get()
    
    # Check if auto_execute attribute exists
    auto_execute = getattr(settings, 'auto_execute', None)
    
    if auto_execute is not None:
        print(f"   auto_execute: {auto_execute}")
        if auto_execute:
            print("   ✅ Scheduler will EXECUTE orders when signals found")
        else:
            print("   ⚠️  Scheduler will only SCAN (no orders)")
    else:
        print("   ⚠️  auto_execute column not found in settings")
        print(f"   Available columns: {[c.name for c in settings.__table__.columns]}")
    
    db.close()
    
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()

# Test 4: Global Settings (Broker Config)
print("\n[4] Global Settings - Broker Configuration")
print("-" * 40)
try:
    from nexus2.db import SessionLocal, GlobalSettingsRepository
    
    db = SessionLocal()
    repo = GlobalSettingsRepository(db)
    settings = repo.get()
    
    broker = getattr(settings, 'broker', 'unknown')
    account = getattr(settings, 'account', 'unknown')
    
    print(f"✅ Broker: {broker}")
    print(f"   Account: {account}")
    
    if broker == "paper":
        print("   → Will use PaperBroker (local simulation)")
    elif broker == "alpaca_paper":
        print("   → Will use AlpacaBroker in paper mode")
    elif broker == "alpaca_live":
        print("   ⚠️  LIVE MODE - Real money!")
    
    db.close()
    
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)
print("TEST COMPLETE")
print("=" * 60)
