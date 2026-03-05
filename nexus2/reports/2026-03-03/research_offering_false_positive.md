# Research: NPT Offering False-Positive Rejection

**Date:** 2026-03-03  
**Author:** Backend Planner  
**Task:** Investigate why NPT was rejected by `negative_catalyst:offering` despite having a historical offering

---

## Executive Summary

**Root cause: TWO compounding bugs rejected NPT.**

### Bug 1: Finviz Has Zero Date Filtering

The **Finviz** headline source (`news_sources.py:60-91`) returns headlines with **no date filtering at all** — it calls `news_df["Title"].head(limit)` and ignores the `Date` column entirely. NPT's **IPO headlines** from weeks/months ago were included:

- `"Texxon Holding Limited Announces Closing of $9.5 Million Initial Public Offering"` ← matched "offering"
- `"Texxon Holding Limited Announces Pricing of $9.5 Million Initial Public Offering"` ← matched "offering"

### Bug 2: Negative Regex Fires Before Positive

In `CatalystClassifier.classify()` (line 232-240), **negative patterns are checked FIRST**. The word "offering" in "Initial Public Offering" hits the negative `offering` regex before the positive `ipo` regex gets a chance to match. So an **IPO** — a *positive* catalyst per Ross methodology — is misclassified as a *negative* offering/dilution catalyst.

### Impact

NPT was rejected 10+ times on 2026-03-03 with 52-61% gap, ~20x RVOL, 2.9M float. Ross traded it for +$8,312.

---

## Evidence

### Smoking Gun: Finviz Headlines

All 4 headline sources were queried for NPT:

| Source | Headlines Found | Offering Match? | Date Filtering? |
|--------|----------------|-----------------|------------------|
| FMP | 0 (empty) | N/A | ✅ `pub_date >= cutoff` |
| Yahoo | 0 (empty) | N/A | ✅ `providerPublishTime >= cutoff` |
| **Finviz** | **5** | **YES — 2 IPO headlines** | ❌ **NONE** |
| Alpaca/Benzinga | 10 (generic movers) | No | ✅ `days` param |

Finviz headlines for NPT:
```
[1] Texxon Holding Limited Completes Key Safety and Regulatory Milestones...
[2] Texxon Holding Limited Announces Financial Results for Fiscal Year 2025
[3] Texxon Holding Limited Announces Full Exercise of Underwriters' Over-Allotment Option
[4] Texxon Holding Limited Announces Closing of $9.5 Million Initial Public Offering  ← TRIGGERED
[5] Texxon Holding Limited Announces Pricing of $9.5 Million Initial Public Offering  ← TRIGGERED
```

**Verified with:** Direct API calls to all 4 sources from local environment.

### VPS Scan Log — 10+ Rejections on 2026-03-03

```
2026-03-03 19:53:08 | FAIL | NPT | Gap:52.7% | RVOL:21.2x | Float: 2.9M | Reason: negative_catalyst | Type: offering
2026-03-03 19:55:30 | FAIL | NPT | Gap:52.2% | RVOL:21.0x | Float: 2.9M | Reason: negative_catalyst | Type: offering
2026-03-03 20:06:07 | FAIL | NPT | Gap:55.2% | RVOL:20.4x | Float: 2.9M | Reason: negative_catalyst | Type: offering
2026-03-03 20:13:15 | FAIL | NPT | Gap:61.1% | RVOL:20.0x | Float: 2.9M | Reason: negative_catalyst | Type: offering
2026-03-03 20:15:39 | FAIL | NPT | Gap:61.7% | RVOL:19.9x | Float: 2.9M | Reason: negative_catalyst | Type: offering
```

**Verified with:** `ssh root@100.113.178.7 "grep 'NPT' ~/Nexus2/data/warrior_scan.log | grep '2026-03-03' | tail -20"`

NPT had **excellent metrics** — 52-61% gap, ~20x RVOL, 2.9M float — yet was blocked every scan cycle.

### Prior Days — NPT Passed as "momentum"

```
2026-02-28 through 2026-03-02: NPT consistently passed with catalyst type "momentum"
```

**Verified with:** `Select-String -Path "data\catalyst_audit.log" -Pattern "NPT" | Select-Object -Last 20`

This proves the offering headline either (a) entered the lookback window after Mar 2, or (b) came from a different news source that wasn't previously returning results.

### FMP Returns No Headlines for NPT

FMP `stock_news` API returned empty results for NPT. The offering headline came exclusively from **Finviz**, which has no date filtering.

---

## Complete Code Trace

### Step 1: Headlines Fetched — `_evaluate_symbol()` line 921

**File:** [warrior_scanner_service.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/scanner/warrior_scanner_service.py#L921-L924)

```python
headlines = self.market_data.get_merged_headlines(
    symbol, 
    days=s.catalyst_lookback_days,  # Default: 5
    alpaca_broker=self.alpaca_broker,
)
```

### Step 2: Headlines Merged — `get_merged_headlines()` line 860

**File:** [unified.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/adapters/market_data/unified.py#L860-L932)

Returns `List[str]` — **plain text, no dates**. Aggregates from 4 sources:

| Source | Date Filtering | What It Returns |
|--------|---------------|------------------|
| FMP `get_recent_headlines()` | ✅ `pub_date >= cutoff` (L923) | `List[str]` (titles only) |
| Alpaca/Benzinga | ✅ `days` param to API | `List[str]` (headlines) |
| Yahoo Finance | ✅ `providerPublishTime >= cutoff` (L42) | `List[str]` (headlines) |
| **Finviz** | ❌ **NONE** — `head(limit)` only (L81) | `List[str]` (headlines) |

**Finviz is the outlier:** It has a `Date` column in `news_df` but **completely ignores it** — no date filtering whatsoever.

### Step 3: Negative Catalyst Check — `_evaluate_catalyst_pillar()` line 1380

**File:** [warrior_scanner_service.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/scanner/warrior_scanner_service.py#L1380-L1430)

```python
has_negative, neg_type, neg_headline = classifier.has_negative_catalyst(headlines)
if has_negative:
    # ... bypass checks (reverse split, momentum override) ...
    if not should_bypass:
        # REJECTION — no date check before rejecting
        return "negative_catalyst"
```

### Step 4: Regex Classifier — `has_negative_catalyst()` line 322

**File:** [catalyst_classifier.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/catalyst_classifier.py#L322-L334)

```python
def has_negative_catalyst(self, headlines: List[str]):
    for h in headlines:
        match = self.classify(h)
        if not match.is_positive and match.catalyst_type and match.confidence >= 0.9:
            return True, match.catalyst_type, match.headline
    return False, None, None
```

**Zero date awareness.** Pure regex match on headline text.

### Step 4b: CRITICAL — Negative Patterns Checked FIRST in `classify()`

**File:** [catalyst_classifier.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/catalyst_classifier.py#L232-L260)

```python
def classify(self, headline: str) -> CatalystMatch:
    # Check negative patterns first (to avoid bad trades)  ← LINE 232
    for ctype, pattern in self.negative_patterns.items():
        if pattern.search(h):
            return CatalystMatch(headline=h, catalyst_type=ctype, confidence=0.9, is_positive=False)
    
    # ... exclusion patterns ...
    
    # Check positive patterns (Tier 1 - primary catalysts)  ← LINE 252
    for ctype, pattern in self.positive_patterns.items():
        if pattern.search(h):  # "ipo" pattern would match here, but never reached!
            return CatalystMatch(headline=h, catalyst_type=ctype, confidence=0.9, is_positive=True)
```

**The `ipo` positive pattern (`\b(ipo|initial\s+public\s+offering|...)\b`) WOULD match** on "Initial Public Offering" — but the negative `offering` pattern fires first and short-circuits. The headline "Announces Pricing of $9.5 Million Initial Public Offering" is classified as negative `offering` (0.9 confidence) instead of positive `ipo`.

### Step 5: Offering Regex — line 179

```python
"offering": re.compile(
    r"\b(offerings?|public\s+offering|registered\s+direct|at-the-market|atm\s+offering|dilution)\b",
    re.IGNORECASE,
),
```

This matches **any** headline containing the word "offering" — extremely broad.

### Step 6: Bypass Conditions — lines 1384-1413

Two bypass paths exist, but **neither helps NPT**:

| Bypass | Condition | NPT Result |
|--------|-----------|-------------|
| Reverse split | `allow_offering_for_reverse_splits=True` AND symbol has recent RS | NPT has no RS → ❌ |
| Momentum override | RVOL ≥ 50x AND gap ≥ 30% | NPT had ~20x RVOL → ❌ (needs 50x) |

**Note:** The momentum override thresholds are extremely high — RVOL ≥ 50x essentially never triggers.

---

## The Asymmetry: Positive Path HAS Date Awareness

The positive catalyst path at line 1369-1375 **does** fetch dates for freshness scoring:

```python
news_with_dates = self.market_data.fmp.get_news_with_dates(
    ctx.symbol, days=s.catalyst_lookback_days
)
for headline, pub_date in news_with_dates:
    if headline == best_headline or headline[:50] == best_headline[:50]:
        ctx.catalyst_date = pub_date
        break
```

This data is used for the freshness "flame" indicator (🔴/🟠/🟡) but is **never consulted for negative catalyst decisions**.

---

## Logging Gap Found

Negative catalyst rejections do **NOT** call `log_headline_evaluation()`. Only PASS results (line 1064) and no_catalyst rejections (line 946) are logged to the catalyst audit log. This means **we cannot see which headline triggered the rejection** from the audit log alone.

**Verified with:** Both local and VPS catalyst audit logs have no NPT entries for 2026-03-03.

---

## Recommended Fix Approach

### Fix 1: Add Date Filtering to Finviz (LOW RISK — do first)

Finviz's `news_df` already has a `Date` column — it's just ignored.

**File:** [news_sources.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/adapters/market_data/news_sources.py#L60-L91)

```python
# Current (line 81):
headlines = news_df["Title"].head(limit).tolist()

# Fix: Filter by date like Yahoo and FMP do
cutoff = now_et() - timedelta(days=days)  # Need to add `days` param
filtered = news_df[news_df["Date"] >= cutoff]
headlines = filtered["Title"].head(limit).tolist()
```

**Also need to:** Add `days` param to `get_finviz_headlines()` signature and thread it through from `get_merged_headlines()` at `unified.py:924`.

### Fix 2: Exclude IPO From Negative Offering Regex (LOW RISK)

The offering regex should NOT match "Initial Public Offering" — IPOs are a positive catalyst.

**File:** [catalyst_classifier.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/catalyst_classifier.py#L179-L181)

```python
# Current:
"offering": re.compile(
    r"\b(offerings?|public\s+offering|registered\s+direct|at-the-market|atm\s+offering|dilution)\b",
    re.IGNORECASE,
),

# Fix: Use negative lookbehind to exclude "initial public offering"
"offering": re.compile(
    r"(?<!initial\s)\b(offerings?|public\s+offering|registered\s+direct|at-the-market|atm\s+offering|dilution)\b",
    re.IGNORECASE,
),
```

**Note:** Python regex doesn't support variable-length lookbehinds. Alternative approach — add an IPO exclusion check BEFORE negative pattern matching:

```python
# In classify(), before negative patterns:
if re.search(r'\binitial\s+public\s+offering\b|\bipo\b', h, re.IGNORECASE):
    # Skip negative patterns for IPO headlines — check positive first
    ...
```

### Fix 3: Add Negative Catalyst Audit Logging (OBSERVABILITY)

Add `log_headline_evaluation()` call for negative catalyst rejections so we can see the triggering headline in future investigations.

### Priority Order

1. **Fix 1** (Finviz date filtering) — prevents the root cause
2. **Fix 2** (IPO exclusion) — prevents the semantic false positive
3. **Fix 3** (logging) — observability for future issues

---

## Change Surface (for Backend Specialist)

| # | File | Change | Location |
|---|------|--------|----------|
| 1 | `news_sources.py` | Add `days` param and date filtering to `get_finviz_headlines()` | L60-91 |
| 2 | `unified.py` | Pass `days` param to `get_finviz_headlines()` (currently only passes `limit=5`) | L924 |
| 3 | `catalyst_classifier.py` | Add IPO exclusion before negative pattern check in `classify()` | L232-240 |
| 4 | `warrior_scanner_service.py` | Add `log_headline_evaluation()` for negative rejections | `_evaluate_catalyst_pillar()` L1415-1430 |

---

## Answers to Handoff Questions

1. **Where are headlines fetched?** `get_merged_headlines()` in `unified.py:860` — aggregates FMP, Alpaca, Yahoo, Finviz with `days=catalyst_lookback_days=5`
2. **Does recency logic exist?** **Partially.** FMP, Yahoo, and Alpaca filter by date. **Finviz does NOT** — it returns headlines from any date regardless of lookback setting.
3. **What headlines did NPT have?** **Found.** Finviz returned 5 headlines including 2 IPO announcements: "Announces Closing of $9.5 Million Initial Public Offering" and "Announces Pricing of $9.5 Million Initial Public Offering". These matched the `offering` negative regex.
4. **Is the recency gap in the negative path specifically?** **It's both.** (a) Finviz has no date filtering for ANY path, and (b) the `classify()` method checks negative regex BEFORE positive, so "Initial Public Offering" hits `offering` instead of `ipo`.
5. **Is there a stale headline cache?** No — headlines are fetched fresh. The issue is Finviz specifically ignoring dates, not a cache problem.
