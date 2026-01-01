"""
Pre-Market Alpaca Order Test

Verifies the full order flow works by:
1. Checking Alpaca API connectivity
2. Submitting a test limit order
3. Immediately canceling it

Safe to run pre-market - no trades will execute.
"""
import requests
import time

API_BASE = "http://localhost:8000"

print("=" * 60)
print("ALPACA ORDER FLOW TEST (Pre-Market)")
print("=" * 60)

# 1. Check broker status
print("\n1️⃣ Checking broker configuration...")
try:
    r = requests.get(f"{API_BASE}/settings", timeout=10)
    if r.status_code == 200:
        settings = r.json()
        broker = settings.get("broker_type", "?")
        account = settings.get("active_account", "?")
        print(f"   Broker: {broker}")
        print(f"   Account: {account}")
        if broker != "alpaca_paper":
            print("   ⚠️ WARNING: Not using alpaca_paper broker!")
    else:
        print(f"   Error: {r.status_code}")
except Exception as e:
    print(f"   Error: {e}")

# 2. Check Alpaca connection by getting account info
print("\n2️⃣ Testing Alpaca API connectivity...")
try:
    # The broker should be able to get positions (empty is fine)
    r = requests.get(f"{API_BASE}/positions", timeout=10)
    if r.status_code == 200:
        data = r.json()
        print(f"   ✅ Connected to Alpaca!")
        print(f"   Current positions: {len(data.get('positions', []))}")
    else:
        print(f"   Error: {r.status_code} - {r.text[:100]}")
except Exception as e:
    print(f"   Error: {e}")

# 3. Submit a test limit order (very low price so it won't fill)
print("\n3️⃣ Creating test order (DRAFT)...")
test_order = {
    "symbol": "SPY",
    "side": "buy",
    "quantity": 1,  # API uses 'quantity' not 'qty'
    "order_type": "limit",
    "limit_price": 100.00,  # Well below market - won't fill
    "time_in_force": "day"
}

order_id = None
try:
    r = requests.post(f"{API_BASE}/orders", json=test_order, timeout=15)
    if r.status_code == 200 or r.status_code == 201:
        data = r.json()
        order_id = data.get("order_id") or data.get("id")
        status = data.get("status", "?")
        print(f"   ✅ Order created!")
        print(f"   Order ID: {order_id}")
        print(f"   Status: {status}")
    else:
        print(f"   Error: {r.status_code} - {r.text[:200]}")
except Exception as e:
    print(f"   Error: {e}")

# 3b. Submit order to broker (execute=true sends to Alpaca)
if order_id:
    print("\n3️⃣b Submitting order to Alpaca broker...")
    try:
        r = requests.post(f"{API_BASE}/orders/{order_id}/submit", 
                         json={"execute": True}, timeout=15)
        if r.status_code == 200:
            data = r.json()
            status = data.get("status", "?")
            print(f"   ✅ Order submitted to Alpaca!")
            print(f"   Status: {status}")
        else:
            print(f"   Error: {r.status_code} - {r.text[:200]}")
    except Exception as e:
        print(f"   Error: {e}")

# 4. Cancel the test order
if order_id:
    print("\n4️⃣ Canceling test order...")
    time.sleep(1)  # Brief pause
    try:
        r = requests.delete(f"{API_BASE}/orders/{order_id}", timeout=15)
        if r.status_code == 200:
            print(f"   ✅ Order canceled successfully!")
        else:
            print(f"   Warning: Cancel returned {r.status_code} - {r.text[:100]}")
            print("   (Order may have been rejected pre-market)")
    except Exception as e:
        print(f"   Error: {e}")

print("\n" + "=" * 60)
print("TEST COMPLETE")
print("=" * 60)
print("\nIf you saw ✅ for steps 1-4, the order flow is working!")
print("At market open, auto_execute will submit real orders to Alpaca.")
