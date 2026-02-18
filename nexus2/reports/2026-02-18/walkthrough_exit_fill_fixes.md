# Walkthrough: Exit Fill Recording & P&L Fixes

## Problem
Exit fills were **never** recording actual Alpaca fill prices. Every exit used the limit price instead, causing inaccurate P&L. Entry fills had the same latent bug.

## Root Cause
Two naming mismatches between Alpaca's raw API and the `BrokerOrder` dataclass:

| API Layer | Raw Alpaca field | `BrokerOrder` attribute |
|-----------|-----------------|------------------------|
| Fill price | `filled_avg_price` | `avg_fill_price` |
| Fill qty | `filled_qty` | `filled_quantity` |

`get_filled_orders()` returns `FilledOrder` objects using Alpaca's raw names → **correct**.  
`get_order_status()` returns `BrokerOrder` using mapped names → code was using raw names → **always None**.

Additionally, exit poll called `alpaca.get_order()` which doesn't exist — `get_order_status()` is the correct method.

## Changes Made

### 1. [warrior_callbacks.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/api/routes/warrior_callbacks.py) — Exit fill poll
- `get_order()` → `get_order_status()` (fixes AttributeError)
- `filled_avg_price` → `avg_fill_price` (fixes hasattr always False)
- Retries: 4 → 8 (2s → 4s total polling window)
- Error handler: `break` → `continue` (retry on transient errors)
- Added warning log when falling back to limit price

### 2. [trade_event_service.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/domain/automation/trade_event_service.py) — Slippage labels
- For sells: positive slippage (actual > intended) = **better** (got more money)
- Labels were inverted — swapped "better" and "worse"

### 3. [warrior_entry_execution.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/domain/automation/warrior_entry_execution.py) — Entry fill poll
- `filled_avg_price` → `avg_fill_price`
- `filled_qty` → `filled_quantity`

### 4. [warrior_engine_entry.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/domain/automation/warrior_engine_entry.py) — Entry fill poll (duplicate path)
- Same attribute name fixes as #3

## Verification
- **Imports**: All 4 modified modules import cleanly ✅
- **Tests**: 149 passed, 7 failed (all pre-existing, unrelated to changes) ✅
  - Pre-existing failures: missing DB column `price`, removed `min_dollar_volume` attribute, changed defaults

## Impact
- Exit P&L will now use **actual broker fill prices** instead of limit prices
- Entry P&L will correctly capture fill price vs quote price slippage
- Slippage logs will correctly label better/worse for sell orders
- Polling is more resilient to transient broker API errors
