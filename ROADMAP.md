# Nexus 2 Roadmap

Last updated: 2026-01-06

> **Note:** This roadmap syncs with the Knowledge Item at `~/.gemini/antigravity/knowledge/nexus2_core_systems/`. AI should keep both in sync when making updates.

## Legend
- [ ] Not started
- [/] In progress
- [x] Completed

---

## 🔧 Features

- [x] **HTF Simulation Testing** — Verified: scanner works, added configurable extended threshold
- [ ] **VPS Deployment** — Set up on DigitalOcean droplet
- [x] **Liquidate All Button** — Quick exit for paper mode testing
  - Backend: `POST /automation/liquidate-all` endpoint
  - GUI: Button in Quick Actions with confirmation modal
- [x] **Project README** — Startup instructions (backend, frontend, env setup)
- [ ] **User Guide / Wiki** — How to use the system, operational playbook

---

## 🛠 Technical Debt

- [x] **Graceful Shutdown** — Two-stage Ctrl+C, FMP rate limit interruptible
- [x] **Singleton Cleanup** — Removed duplicate `global _monitor`, use `get_monitor()`
- [x] **Extract `execute_callback`** — Moved to `execution_handler.py` + 3 more modules (65% reduction)
- [x] **`_sim_broker` thread safety** — Centralized in automation_state.py with threading.Lock

---

## 📋 Audit Items

- [/] **DB session context managers** — Add `with` blocks for automatic cleanup
  - ✅ Created `get_session()` in database.py
  - ✅ scheduler_routes.py refactored (3 instances)
  - ⏳ ~33 instances remaining across routes/
- [ ] **`orders_filled` increment timing** — Verify correct increment logic
- [ ] **API server restart** — Test ability to restart uvicorn from API without manual intervention
- [x] **Hardcoded values to settings** — max_trades_per_cycle, sim_initial_cash now configurable
- [ ] **Scanner version tracking** — Add `scanner_version` or `commit_hash` to positions table
  - Enables post-mortem timeline analysis (e.g., "was MA stacking enforced?")
  - Learned from Jan 7 post-mortem of pre-fix trades
- [ ] **Rejection logging** — Log WHY stocks are rejected (e.g., "sector blacklist: defense")
  - Currently scanner silently skips; diagnostics should record rejection reasons

---

## 📝 UI / UX

- [x] **API Usage card sync** — Verified: shows real FMP rate limit stats
- [x] **Total P&L % in Open Positions** — Already implemented (per-row + total)
- [ ] **Simulation Control Page** — Mock market GUI with clock, scenarios, event log → [Plan](docs/simulation_plan.md)
- [ ] **Countdown Timer to Next Scan** — Show time remaining until next scheduler cycle
- [ ] **Score Breakdown Display** — Show how each signal got its quality score (which criteria contributed)

---

## 🧪 Scanner Improvements

- [x] **RS percentile calculation** — Added 6M (126d) per KK methodology
- [ ] **Setup classification tags** — Each scanner tags its type: ep, breakout, htf, flag
- [ ] **Full E2E simulation test** — After fixing HTF signal conversion

---

## 🎯 Warrior Trading Strategy (Ross Cameron)

> Day trading methodology: Low-float momentum, gap-and-go setups. [Full Guide](~/.gemini/antigravity/knowledge/trading_strategies_reference/artifacts/strategies/warrior_trading/warrior_trading_strategy_guide.md)

- [ ] **WarriorScanner** — Low-float momentum scanner
  - [ ] Float filtering (requires FMP extension)
  - [ ] RVOL calculation (time-of-day adjusted)
  - [ ] Pre-market highs monitoring
  - [ ] MACD (12, 26, 9) indicator
  - [ ] VWAP for pullback entries
- [ ] **WarriorMonitor** — Day trade management (different from KK swing)
  - [ ] 1-minute ORB at 9:30 AM
  - [ ] Multi-session ORB (4am, 6am, 7am)
  - [ ] 10:00 AM exit time priority
  - [ ] First red 5-min candle exit signal
- [ ] **Multi-Account Support** — Alpaca Account B isolation for day trades

---

## 🧪 R&D Labs (Low Priority)

> Experimental multi-agent AI system for autonomous strategy discovery and optimization.

- [ ] **Strategy Discovery Engine** — Multi-Agent AI system with feedback loop
  - Autonomous exploration of alternative scan modes and strategies
  - Self-evaluating agents that test, score, and iterate on trading patterns
  - Feedback loop from live/sim results to refine discovery
- [ ] **User-Defined Momentum Screener** — TradingView-style filter (RSI>80, 1M>25%, stacked MAs)
  - [Spec](.agent/rules/user-defined-momentum-screener.md)
- [ ] **Backtesting Framework** — Historical signal validation with P&L simulation

---

## 🔮 Future / Low Priority

- [ ] **Equity Curve & Drawdown Charts** — Visualize portfolio performance over time
- [ ] **Calendar Heatmap** — Daily P&L visualization
- [ ] **Async RS Refresh** — Background job for RS universe refresh (non-blocking)

---

## ✅ Completed (Recent)

- [x] **MA Check Exit Logic** — Fixed order submission, broker reference, character change exits
- [x] **Position Enrichment Script** — `scripts/enrich_positions.py` repairs orphaned position metadata
- [x] **Simulation Entry Time Tracking** — MockPosition tracks actual opened_at for correct days_held
- [x] Sim mode display on page load
- [x] MA stacking filter in breakout scanner (price > SMA10 > SMA20 > SMA50)
- [x] Monitor auto-start with scheduler (await fix + singleton unification)
- [x] Button alignment on control cards (flexbox)
- [x] Graceful shutdown (Ctrl+C handling)
- [x] Singleton cleanup
- [x] EP Scanner infrastructure (catalyst patterns, CatalystType.NEWS, opening range)

