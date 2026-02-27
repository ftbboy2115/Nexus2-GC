# Session Handoff — Feb 26, 2026 @ 10:47 PM ET

## Current State
- **VPS**: Running commit `2f3bc93`, aligned with local
- **Batch test**: VPS=$383K, Local=$384K — **aligned** (88.4% capture, 47.1% fidelity)
- **All changes committed and pushed** — nothing in-flight

## What Was Done Today

### Scaling v2
- Structural exits: enabled (+7.6% P&L improvement)
- Level-break scaling: code ready, **disabled** (A/B test showed -$91K regression)
- AIDX test case added

### Server Admin Card (commit `404b7a0` → `7b0ade9`)
- Health endpoint: added `commit_date`, `memory_total_mb`, `pycache_cleared`, `settings_modified_at`
- AdminCard.tsx: version/deploy row, memory used/total, pycache badge, settings sync, enriched copy button
- Pycache marker: uses `admin_config.json` timestamp instead of scanning for `__pycache__` dirs

### VPS Alignment Fix (commit `6c13d2a` → `2f3bc93`)
- Root cause: `warrior_settings.json` diverged (VPS had live safety limits: 10 shares, $50 risk)
- Fix: `gc_quick_test.py` now sends `BATCH_CONFIG_OVERRIDES` with sim-scale params
- Bug fix: float/Decimal type mismatch silently killed entries when config_overrides were passed
- `sim_context.py`: auto-converts to Decimal when existing field is Decimal type

## Open Items (Priority Order)
1. **GWAV regression** — bot loses $6.5K on $4K Ross winner (largest negative delta after structural issues)
2. **Level-break scaling guardrails** — needs max 1-2 adds, min profit threshold before re-enabling
3. **MNTS regression** — bot loses $15.5K, Ross made $9K
4. **RDIB/RVSN** — bot losers where Ross was flat/profitable
5. **Engine persistence** — verify engine_enabled correctly resumes after restart
6. **ROADMAP.md** — update with today's progress
