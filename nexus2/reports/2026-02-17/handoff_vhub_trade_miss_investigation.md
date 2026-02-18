# Multi-Agent Investigation: VHUB Trade Miss (2026-02-17)

## Situation

Ross Cameron traded VHUB this morning for +$1,600. The Warrior bot detected VHUB as a valid BULL_FLAG but did NOT take the trade because the `TOP_X` concentration filter blocked it. We need to understand why VHUB ranked low and whether the ranking algorithm captures Ross's selection criteria.

---

## Verified Facts (with evidence)

### Fact 1: Ross's Trade
**Source:** `.agent/knowledge/warrior_trading/2026-02-17_transcript_NA90q8dBJkI.md`
- Entry: $3.33, 20,000 shares
- Exit: ~$3.41, +$1,600
- Alert time: ~7:30 AM ET
- Catalyst: News headline
- Setup: Recent IPO, blue sky above $40
- Pattern: Dip from $3.45 high → curl back up → bought the curl
- Ross explicitly avoided RIME ("crowded/thickly traded"), SUEN ("thickly traded"), GXAI ("thickly traded")

### Fact 2: Bot detected VHUB but blocked it
**Verified with:** `ssh root@100.113.178.7 "grep -i 'VHUB' ~/Nexus2/data/server.log | tail -30"`
**Output:**
```
14:59:05.785 | [Warrior Entry] VHUB: BULL FLAG at $3.00 (first green after 2 red candles, break of prev high $2.95)
14:59:06.275 | [Warrior Entry] VHUB: WINNER=BULL_FLAG score=0.584 (threshold=0.4), candidates=1
14:59:06.275 | [Warrior Entry] VHUB: TOP_3_ONLY - blocked (rank=11, dynamic=2) top pick is LFS (dynamic=11)
```

### Fact 3: TOP_X filter is in warrior_entry_guards.py, NOT warrior_engine_entry.py
**File:** `nexus2/domain/automation/warrior_entry_guards.py:63-81`
**Code:**
```python
    # TOP X PICKS - Ross Cameron (Jan 20 2026): "TWWG was the ONLY trade I took today"
    if engine.config.top_x_picks > 0:
        all_watched = sorted(
            engine._watchlist.values(),
            key=lambda w: w.dynamic_score,
            reverse=True
        )
        if all_watched:
            top_x_symbols = {w.candidate.symbol for w in all_watched[:engine.config.top_x_picks]}
            if watched.candidate.symbol not in top_x_symbols:
                top_pick = all_watched[0]
                our_rank = next((i+1 for i, w in enumerate(all_watched) if w.candidate.symbol == symbol), len(all_watched))
                reason = (
                    f"TOP_{engine.config.top_x_picks}_ONLY - blocked (rank={our_rank}, "
                    f"dynamic={watched.dynamic_score}) "
                    f"top pick is {top_pick.candidate.symbol} (dynamic={top_pick.dynamic_score})"
                )
                tml.log_warrior_guard_block(symbol, "top_x", reason, _trigger, _price)
                return False, reason
```
**Conclusion:** The ranking is based entirely on `w.dynamic_score`. VHUB had `dynamic_score=2`, LFS had `dynamic_score=11`. Only top `config.top_x_picks` (currently 3) symbols are allowed.

### Fact 4: Bot took 18 trades today (mostly losers) — Ross took 1 (winner)
**Verified with:** `ssh root@100.113.178.7 "curl -s 'http://localhost:8000/warrior/trades?limit=20'"`
**Output:** Bot traded FRGT(3x), SUNE(3x), LFS(3x), ATOM(2x), GVH(2x), EEIQ(2x), IBG, SIF, OLB — most losers.

### Fact 5: VWAP first_times show '?' marks
**Verified with:** server.log grep
```
14:57:23.778 | [Warrior VWAP] VHUB: All 487 bars passed filter (current_hour=14, bar_limit=667, first_times=['?', '?', '?'])
```
**File to investigate:** `nexus2/domain/automation/warrior_vwap_utils.py` — the `first_times` field

---

## Open Questions for Investigation

### Q1 — Strategy Agent
- Ross chose VHUB and **avoided** everything else as "thickly traded" or "crowded"
- Bot preferred LFS (dynamic_score=11) over VHUB (dynamic_score=2)
- **Does `dynamic_score` capture catalyst quality, blue sky, recent IPO status?**
- **Should Ross's selectivity criteria (news catalyst, float quality, blue sky) be weighted in ranking?**
- **Is `top_x_picks=3` too large?** Ross only took 1 trade because market was cold. Bot took 18.
- Read `.agent/strategies/warrior.md` for methodology reference
- Write findings to: `nexus2/reports/2026-02-17/strategy_vhub_trade_analysis.md`

### Q2 — Backend Planner
- **How is `dynamic_score` computed?** Search for `dynamic_score` in the engine/watchlist code.
- **What factors contribute to a high dynamic_score?** Why did LFS score 11 and VHUB score 2?
- **Where is `top_x_picks` configured?** What is the current value?
- **Why do VWAP first_times show '?'?** Check `warrior_vwap_utils.py` for the logging.
- Write findings to: `nexus2/reports/2026-02-17/planner_top3_filter_investigation.md`

---

## Agent Spawn Commands

### Strategy Expert
```
@agent-strategy-expert.md

Task: Analyze why Warrior bot missed Ross Cameron's VHUB trade on 2026-02-17
Handoff: nexus2/reports/2026-02-17/handoff_vhub_trade_miss_investigation.md
Transcript: .agent/knowledge/warrior_trading/2026-02-17_transcript_NA90q8dBJkI.md
Strategy: .agent/strategies/warrior.md

Focus on Q1 from the handoff. The core problem: bot preferred LFS (dynamic_score=11) 
over VHUB (dynamic_score=2), but Ross chose VHUB and avoided everything else.
Does the ranking capture Ross's actual selection criteria?
```

### Backend Planner
```
@agent-backend-planner.md

Task: Research dynamic_score computation and TOP_X filter in Warrior entry logic
Handoff: nexus2/reports/2026-02-17/handoff_vhub_trade_miss_investigation.md

Focus on Q2. Start in warrior_entry_guards.py:63-81 (TOP_X filter), then trace 
dynamic_score back to where it's set on WatchedCandidate. Also investigate 
first_times='?' in warrior_vwap_utils.py.
```
