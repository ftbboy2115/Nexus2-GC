# Nexus 2 Roadmap

Last updated: 2026-01-03

> **Note:** This roadmap syncs with the Knowledge Item at `~/.gemini/antigravity/knowledge/nexus2_core_systems/`. AI should keep both in sync when making updates.

## Legend
- [ ] Not started
- [/] In progress
- [x] Completed

---

## 🔧 Features

- [x] **HTF Simulation Testing** — Verified: scanner works, added configurable extended threshold
- [ ] **VPS Deployment** — Set up on DigitalOcean droplet
- [ ] **Liquidate All Button** — Quick exit for paper mode testing
  - Backend: `POST /automation/liquidate-all` endpoint
  - GUI: Add button next to Emergency Stop, confirmation modal
- [ ] **Project README** — Startup instructions (backend, frontend, env setup)
- [ ] **User Guide / Wiki** — How to use the system, operational playbook

---

## 🛠 Technical Debt

- [x] **Graceful Shutdown** — Two-stage Ctrl+C, FMP rate limit interruptible
- [x] **Singleton Cleanup** — Removed duplicate `global _monitor`, use `get_monitor()`
- [x] **Extract `execute_callback`** — Moved to `execution_handler.py` + 3 more modules (65% reduction)
- [x] **`_sim_broker` thread safety** — Centralized in automation_state.py with threading.Lock

---

## 📋 Audit Items

- [ ] **DB session context managers** — Add `with` blocks for proper cleanup
- [ ] **`orders_filled` increment timing** — Verify correct increment logic
- [x] **Hardcoded values to settings** — max_trades_per_cycle, sim_initial_cash now configurable

---

## 📝 UI / UX

- [x] **API Usage card sync** — Verified: shows real FMP rate limit stats
- [ ] **Total P&L % in Open Positions** — Add to positions card

---

## 🧪 Scanner Improvements

- [x] **RS percentile calculation** — Added 6M (126d) per KK methodology
- [ ] **Setup classification tags** — Each scanner tags its type: ep, breakout, htf, flag
- [ ] **Full E2E simulation test** — After fixing HTF signal conversion

---

## 🔮 Future / Low Priority

- [ ] **Equity Curve & Drawdown Charts** — Visualize portfolio performance over time
- [ ] **Calendar Heatmap** — Daily P&L visualization
- [ ] **Async RS Refresh** — Background job for RS universe refresh (non-blocking)

---

## ✅ Completed (Recent)

- [x] Sim mode display on page load
- [x] MA stacking filter in breakout scanner (price > SMA10 > SMA20 > SMA50)
- [x] Monitor auto-start with scheduler (await fix + singleton unification)
- [x] Button alignment on control cards (flexbox)
- [x] Graceful shutdown (Ctrl+C handling)
- [x] Singleton cleanup
- [x] EP Scanner infrastructure (catalyst patterns, CatalystType.NEWS, opening range)
