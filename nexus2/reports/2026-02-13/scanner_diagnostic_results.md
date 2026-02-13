# Scanner Diagnostic Results

Generated: 2026-02-13 08:47:30

## Summary

| Symbol | Date | Gap% | Float | RVOL | Catalyst | Would Pass? | Fail Stage |
|--------|------|------|-------|------|----------|------------|------------|
| EVMN | 2026-02-10 | 73.7% | 12.5M | 55.3x | weak: positive_sentiment  | ❌ FAIL | Price ($29.52) |
| VELO | 2026-02-10 | 14.1% | 5.6M | 2.2x | 4 headlines, none classif | ❌ FAIL | Catalyst (4 headlines, none classified as positive) |
| BNRG | 2026-02-12 | -7.1% | 279.3K | 0.4x | 2 headlines, none classif | ❌ FAIL | Gap (-7.1%) |
| PRFX | 2026-02-12 | -9.7% | 76.8K | 0.2x | 1 headlines, none classif | ❌ FAIL | Gap (-9.7%) |
| PMI | 2026-02-12 | 42.9% | 26.1M | 229.8x | 20 headlines, none classi | ❌ FAIL | Catalyst (20 headlines, none classified as positive) |
| RDIB | 2026-02-13 | N/A | 747.0K | N/A | no headlines found | ❌ FAIL | Price (no data) |

**Total: 6 | Pass: 0 | Fail: 6**

## Detailed Results

## EVMN on 2026-02-10

### Data Source Presence
- FMP Gainers: UNAVAILABLE (live-only, cannot check historical)
- Polygon Gainers: UNAVAILABLE (live-only, cannot check historical)
- Alpaca Movers: UNAVAILABLE (live-only, cannot check historical)

### Market Data
| Metric | Value |
|--------|-------|
| Open Price | $29.52 |
| Close Price | $29.03 |
| Prev Close | $16.99 |
| Gap % | 73.7% |
| Day Volume | 15,984,311 |
| Float | 12.5M |
| Avg Volume (20d) | 289,160 |
| RVOL | 55.3x |
| 200 EMA | N/A |
| Country | US |

### News Headlines
- "Evommune's Stock Surges On Strong Results For New Eczema Drug" (2026-02-10)
- "Evommune Nearly Doubles — Has Dupixent Met Its Match In Eczema?" (2026-02-10)
- "Evommune Announces Positive Top-line Data from Phase 2a Proof-of-Concept Trial of EVO301 in Moderate" (2026-02-10)

### Filter Walkthrough
| # | Filter | Result | Detail |
|---|--------|--------|--------|
| 1 | Tradeable equity check | ✅ PASS |  |
| 2 | Price range ($1.50-$20) | ❌ FAIL | $29.52 |
| 3 | Gap % (min 4%) | ✅ PASS | 73.7% |
| 4 | Float (max 100M) | ✅ PASS | 12.5M |
| 5 | RVOL (min 2.0x) | ✅ PASS | 55.3x |
| 6 | Catalyst check | ❌ FAIL | weak: positive_sentiment (conf=0.50) |
| 7 | 200 EMA room | ✅ PASS | N/A (insufficient data = skip) |

**VERDICT:** ❌ **Would FAIL** at: Price ($29.52)

### Data Collection Issues
- ⚠️ Only 65 bars for 200 EMA (need 200)

---

## VELO on 2026-02-10

### Data Source Presence
- FMP Gainers: UNAVAILABLE (live-only, cannot check historical)
- Polygon Gainers: UNAVAILABLE (live-only, cannot check historical)
- Alpaca Movers: UNAVAILABLE (live-only, cannot check historical)

### Market Data
| Metric | Value |
|--------|-------|
| Open Price | $15.64 |
| Close Price | $13.44 |
| Prev Close | $13.70 |
| Gap % | 14.1% |
| Day Volume | 5,116,865 |
| Float | 5.6M |
| Avg Volume (20d) | 2,297,047 |
| RVOL | 2.2x |
| 200 EMA | N/A |
| Country | US |

### News Headlines
- "Here Are Wednesday’s Top Wall Street Analyst Research Calls: BP Plc., Cloudflare, Dick’s Sporting Go" (2026-02-11)
- "Velo3D Stock Climbs As US Army Taps Company As First Qualified 3D-Printing Vendor" (2026-02-10)
- "Velo3D Qualified as First Additive Manufacturing Vendor for U.S. Army Ground Vehicles" (2026-02-10)
- "The Drone Supercycle Wall Street Still Hasn’t Priced In" (2026-02-07)

### Filter Walkthrough
| # | Filter | Result | Detail |
|---|--------|--------|--------|
| 1 | Tradeable equity check | ✅ PASS |  |
| 2 | Price range ($1.50-$20) | ✅ PASS | $15.64 |
| 3 | Gap % (min 4%) | ✅ PASS | 14.1% |
| 4 | Float (max 100M) | ✅ PASS | 5.6M |
| 5 | RVOL (min 2.0x) | ✅ PASS | 2.2x |
| 6 | Catalyst check | ❌ FAIL | 4 headlines, none classified as positive |
| 7 | 200 EMA room | ✅ PASS | N/A (insufficient data = skip) |

**VERDICT:** ❌ **Would FAIL** at: Catalyst (4 headlines, none classified as positive)

### Data Collection Issues
- ⚠️ Only 121 bars for 200 EMA (need 200)

---

## BNRG on 2026-02-12

### Data Source Presence
- FMP Gainers: UNAVAILABLE (live-only, cannot check historical)
- Polygon Gainers: UNAVAILABLE (live-only, cannot check historical)
- Alpaca Movers: UNAVAILABLE (live-only, cannot check historical)

### Market Data
| Metric | Value |
|--------|-------|
| Open Price | $1.70 |
| Close Price | $1.52 |
| Prev Close | $1.83 |
| Gap % | -7.1% |
| Day Volume | 336,105 |
| Float | 279.3K |
| Avg Volume (20d) | 895,698 |
| RVOL | 0.4x |
| 200 EMA | $13.54 (-87.4%) |
| Country | IL |

### News Headlines
- "Brenmiller Energy Executes on Technology Roadmap with Early Launch of bGen ONE(TM)" (2026-02-11)
- "Diversified Energy (NYSE:DEC) vs. Brenmiller Energy (NASDAQ:BNRG) Head-To-Head Comparison" (2026-02-10)

### Filter Walkthrough
| # | Filter | Result | Detail |
|---|--------|--------|--------|
| 1 | Tradeable equity check | ✅ PASS |  |
| 2 | Price range ($1.50-$20) | ✅ PASS | $1.70 |
| 3 | Gap % (min 4%) | ❌ FAIL | -7.1% |
| 4 | Float (max 100M) | ✅ PASS | 279.3K |
| 5 | RVOL (min 2.0x) | ❌ FAIL | 0.4x |
| 6 | Catalyst check | ❌ FAIL | 2 headlines, none classified as positive |
| 7 | 200 EMA room | ✅ PASS | $13.54 (-87.4% room, enough) |

**VERDICT:** ❌ **Would FAIL** at: Gap (-7.1%)

---

## PRFX on 2026-02-12

### Data Source Presence
- FMP Gainers: UNAVAILABLE (live-only, cannot check historical)
- Polygon Gainers: UNAVAILABLE (live-only, cannot check historical)
- Alpaca Movers: UNAVAILABLE (live-only, cannot check historical)

### Market Data
| Metric | Value |
|--------|-------|
| Open Price | $2.89 |
| Close Price | $2.91 |
| Prev Close | $3.20 |
| Gap % | -9.7% |
| Day Volume | 269,870 |
| Float | 76.8K |
| Avg Volume (20d) | 1,524,614 |
| RVOL | 0.2x |
| 200 EMA | $6.65 (-56.5%) |
| Country | IL |

### News Headlines
- "PRF Technologies Wins Another European Utility-Scale Solar Deployment, Expanding DeepSolar's Install" (2026-02-11)

### Filter Walkthrough
| # | Filter | Result | Detail |
|---|--------|--------|--------|
| 1 | Tradeable equity check | ✅ PASS |  |
| 2 | Price range ($1.50-$20) | ✅ PASS | $2.89 |
| 3 | Gap % (min 4%) | ❌ FAIL | -9.7% |
| 4 | Float (max 100M) | ✅ PASS | 76.8K |
| 5 | RVOL (min 2.0x) | ❌ FAIL | 0.2x |
| 6 | Catalyst check | ❌ FAIL | 1 headlines, none classified as positive |
| 7 | 200 EMA room | ✅ PASS | $6.65 (-56.5% room, enough) |

**VERDICT:** ❌ **Would FAIL** at: Gap (-9.7%)

---

## PMI on 2026-02-12

### Data Source Presence
- FMP Gainers: UNAVAILABLE (live-only, cannot check historical)
- Polygon Gainers: UNAVAILABLE (live-only, cannot check historical)
- Alpaca Movers: UNAVAILABLE (live-only, cannot check historical)

### Market Data
| Metric | Value |
|--------|-------|
| Open Price | $2.30 |
| Close Price | $1.59 |
| Prev Close | $1.61 |
| Gap % | 42.9% |
| Day Volume | 34,833,446 |
| Float | 26.1M |
| Avg Volume (20d) | 151,554 |
| RVOL | 229.8x |
| 200 EMA | N/A |
| Country | US |

### News Headlines
- "PMI Investors Have Opportunity to Lead Picard Medical, Inc. Securities Fraud Lawsuit" (2026-02-12)
- "INVESTOR ALERT: Pomerantz Law Firm Reminds Investors with Losses on their Investment in Picard Medic" (2026-02-12)
- "Investors who lost money on Picard Medical, Inc.(PMI) should contact Levi & Korsinsky about pending " (2026-02-12)
- "The Gross Law Firm Reminds Picard Medical, Inc. Investors of the Pending Class Action Lawsuit with a" (2026-02-12)
- "Deadline Alert: Picard Medical, Inc. (PMI) Shareholders Who Lost Money Urged To Contact Glancy Prong" (2026-02-12)

### Filter Walkthrough
| # | Filter | Result | Detail |
|---|--------|--------|--------|
| 1 | Tradeable equity check | ✅ PASS |  |
| 2 | Price range ($1.50-$20) | ✅ PASS | $2.30 |
| 3 | Gap % (min 4%) | ✅ PASS | 42.9% |
| 4 | Float (max 100M) | ✅ PASS | 26.1M |
| 5 | RVOL (min 2.0x) | ✅ PASS | 229.8x |
| 6 | Catalyst check | ❌ FAIL | 20 headlines, none classified as positive |
| 7 | 200 EMA room | ✅ PASS | N/A (insufficient data = skip) |

**VERDICT:** ❌ **Would FAIL** at: Catalyst (20 headlines, none classified as positive)

### Data Collection Issues
- ⚠️ Only 115 bars for 200 EMA (need 200)

---

## RDIB on 2026-02-13

### Data Source Presence
- FMP Gainers: UNAVAILABLE (live-only, cannot check historical)
- Polygon Gainers: UNAVAILABLE (live-only, cannot check historical)
- Alpaca Movers: UNAVAILABLE (live-only, cannot check historical)

### Market Data
| Metric | Value |
|--------|-------|
| Open Price | N/A |
| Close Price | N/A |
| Prev Close | $12.18 |
| Gap % | N/A |
| Day Volume | N/A |
| Float | 747.0K |
| Avg Volume (20d) | 67,739 |
| RVOL | N/A |
| 200 EMA | N/A |
| Country | US |

### Filter Walkthrough
| # | Filter | Result | Detail |
|---|--------|--------|--------|
| 1 | Tradeable equity check | ✅ PASS |  |
| 2 | Price range ($1.50-$20) | ❌ FAIL | NO DATA |
| 3 | Gap % (min 4%) | ❌ FAIL | NO DATA |
| 4 | Float (max 100M) | ✅ PASS | 747.0K |
| 5 | RVOL (min 2.0x) | ❌ FAIL | NO DATA |
| 6 | Catalyst check | ❌ FAIL | no headlines found |
| 7 | 200 EMA room | ✅ PASS | N/A (insufficient data = skip) |

**VERDICT:** ❌ **Would FAIL** at: Price (no data)

### Data Collection Issues
- ⚠️ No Polygon daily bars for 2026-02-13

---
