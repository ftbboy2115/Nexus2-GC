---
description: Create Mock Market test cases from Ross Cameron trades
---

# Create Test Cases from Ross Cameron Trades

This workflow converts Ross Cameron's actual trades into high-fidelity test cases for the Mock Market historical replay system.

## Prerequisites
- Have the symbol, trade date, and catalyst type from Ross's video/transcript
- Alpaca API credentials must be configured in `.env`

## Steps

### 1. Identify Trade Details from Transcript/Video
Extract from Ross's daily recap:
- **Symbol**: e.g., PDYN
- **Date**: e.g., 2026-01-28
- **Catalyst**: e.g., news, earnings, reverse_split, fda, contract
- **Ross P&L**: (optional) for validation
- **Entry Price**: (approximate from video)

### 2. Fetch Historical 1-Minute Bars
// turbo
```bash
cd C:\Users\ftbbo\Nextcloud4\OneDrive Backup\Documents (sync'd)\Development\Nexus
python fetch_ross_test_cases.py SYMBOL DATE CATALYST
```

Example:
```bash
python fetch_ross_test_cases.py PDYN 2026-01-28 news
```

This creates:
- Transcript file in `.agent/knowledge/warrior_trading/{date}_transcript_{videoId}.md`
- Console output with video metadata (title, date)

### 2.5. Update Transcript Vault (MANDATORY)

After analyzing the transcript content, update the transcript vault at:
`C:\Users\ftbbo\.gemini\antigravity\knowledge\trading_methodologies\artifacts\warrior\intelligence\transcripts\transcript_vault.md`

> [!CAUTION]
> This step is **non-optional**. Skipping it causes data gaps that mislead other agents.

**Add a summary row** to the main table (keep chronological order, newest first):
```markdown
| **Mon DD** | Video Title | **SYMBOL** | +$XXk | One-line core lesson |
```

**Add a deep-dive section** at the bottom (before the version line) with:
- Symbol and P&L
- Strategy/setup type
- Entry price, share count (if stated)
- Scaling pattern (add levels)
- Exit criteria
- Bot alignment notes (if applicable)

**Data rules:**
- P&L must match what Ross states in the transcript — do NOT round or estimate
- Entry prices must be Ross's stated prices, not YAML `expected.entry_near`
- If the transcript doesn't state a detail, write "not stated" — do NOT invent

### 3. Verify Data Quality
Use `scripts/peek_bars.py` to inspect the bars:
```powershell
// turbo
python scripts/peek_bars.py nexus2/tests/test_cases/intraday/ross_SYMBOL_YYYYMMDD.json
```

Custom time range (e.g., to check a specific entry):
```powershell
python scripts/peek_bars.py <file> 09:30 10:00
```

Check the output for:
- [ ] Price range matches expected (not a ticker collision)
- [ ] Premarket High (PMH) aligns with Ross's entry
- [ ] Gap percent is reasonable
- [ ] Volume is significant (not empty data)

**If data looks wrong**, the ticker may have a collision with an old company. Mark as `BAD_DATA` in YAML.

### 4. Add Entry to warrior_setups.yaml
Edit `nexus2/tests/test_cases/warrior_setups.yaml`:

```yaml
  - id: ross_SYMBOL_YYYYMMDD
    symbol: SYMBOL
    setup_type: pmh  # or orb, flag, etc.
    outcome: winner  # or loser, missed
    ross_traded: true
    synthetic: false
    status: REAL_TRADE  # or USABLE, BAD_DATA, NO_FMP_DATA
    description: "Ross Cameron +$X,XXX - Brief description"
    trade_date: "YYYY-MM-DD"
    intraday_file: "intraday/ross_SYMBOL_YYYYMMDD.json"
    premarket_data:
      gap_percent: XX.X  # From fetch output
      premarket_high: X.XX  # From fetch output
      previous_close: X.XX  # From fetch output
      float_shares: XXXXXXX  # If known
      catalyst: "catalyst_type"
    expected:
      entry_near: X.XX  # Ross's approx entry from video
      stop_near: X.XX  # Logical stop level
    notes: "Any relevant notes about the trade"
```

### 5. Verify in Mock Market GUI
1. Open Frontend: http://localhost:3000/warrior
2. Navigate to **Mock Market** tab
3. Select the new test case from dropdown
4. Click **📊 Replay** (not Load)
5. Verify:
   - [ ] Clock resets to test case date
   - [ ] PMH displays correctly
   - [ ] Gap percent shows correctly
   - [ ] Bars advance properly with Step/Play

### 6. Scanner Pulse Check
// turbo
```bash
python scripts/scanner_pulse_check.py SYMBOL YYYY-MM-DD
```

Verify the VPS scanner detected this ticker on the trade date:
- **PASS**: Note quality score in YAML `notes`
- **FAIL**: Note rejection reason — this is a scanner gap to investigate
- **NOT_IN_DB**: Scanner may not have been running; note in YAML

### 7. Commit Changes
```bash
git add nexus2/tests/test_cases/
git commit -m "test: Add Ross SYMBOL trade from YYYY-MM-DD"
git push
```

### 8. Deploy to VPS
> [!CAUTION]
> Test cases live in the git repo. The VPS won't see new cases until you pull.

```powershell
ssh root@100.113.178.7 "cd ~/Nexus2 && git pull"
```

Then restart the backend on the VPS so the new test case appears in the GUI.

---

## Test Case Status Codes

| Status | Meaning |
|--------|---------|
| `REAL_TRADE` | Ross's actual trade with verified data |
| `USABLE` | Good data, but Ross didn't trade it |
| `MISSED_OPPORTUNITY` | Ross mentioned but didn't trade |
| `BAD_DATA` | FMP ticker collision (wrong company data) |
| `ESTIMATED` | Entry price never reached in data |
| `NO_FMP_DATA` | No intraday data available |
| `SYNTHETIC` | Manually created for unit testing |

---

## Troubleshooting

### Ticker Collision (Most Common Issue)
FMP sometimes returns data for OLD companies that reused the same ticker.
**Symptoms**: Price range is completely wrong (e.g., Ross traded $5 stock, data shows $50)
**Solution**: Mark as `BAD_DATA` and use alternate data source or skip

### Missing Premarket Data
If bars only start at 9:30, there's no premarket data.
**Solution**: Use Alpaca's premarket bars or estimate PMH from 9:30 open

### Test Case Not Appearing in GUI
- **Most common**: Haven't run `git pull` on the VPS — test cases are committed locally but not deployed
- Check JSON filename matches `id` in YAML exactly
- Ensure `intraday_file` path is correct
- Restart backend server

---

## Quick Reference: Common Catalysts

| Catalyst | Description |
|----------|-------------|
| `earnings` | Earnings beat/miss |
| `news` | General headline news |
| `reverse_split` | Stock reverse split |
| `fda` | FDA approval/rejection |
| `contract` | Major contract win |
| `partnership` | Partnership announcement |
| `offering` | Stock offering (usually negative) |
| `momentum` | No specific catalyst, pure momentum |
