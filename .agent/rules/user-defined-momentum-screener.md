---
trigger: model_decision
description: This is secondary to KK's strategy and to the platform, but one I have found success with in manual trades. Thus, I would like to carve out funcitonal incorporation of this when appropriate. Do not mix up the main goal with this one. 
---

You are operating in USER-DEFINED MOMENTUM SCREENER MODE for the [PROJECT_NAME] Nexus platform.

This mode defines a user-specified screening filter derived from TradingView settings that have demonstrated empirical success for the user. This screener is NOT a KK-style rule and must remain logically separate from KK-style scanning, setup detection, and trading logic. It is an optional, additive filter that can be used for discovery, ranking, or watchlist generation.

────────────────────────────────────────
PRIMARY OBJECTIVE
────────────────────────────────────────

Apply the following screening criteria to identify high-momentum U.S. equities that meet the user’s preferred TradingView-style filter.

────────────────────────────────────────
SCREENER CRITERIA (USER-DEFINED)
────────────────────────────────────────

1. PRICE FILTERS
   - Price > 2 USD

2. MARKET / EXCHANGE FILTERS
   - Market: United States
   - Exchange: NASDAQ or NYSE
   - Security Type: Common Stock only

3. LIQUIDITY FILTERS
   - Average Dollar Volume (20–50 day): > 2,000,000 USD
   - ADR (Average Daily Range): > 5%
     (ADR = (High - Low) / Close)

4. TREND STRUCTURE FILTERS
   - Price > SMA 10
   - SMA 10 > SMA 20
   - SMA 20 > SMA 50
   (Enforces a clean, stacked moving-average uptrend)

5. MOMENTUM FILTERS
   - RSI (14, 1D) > 80
   - 1-Month Performance > 25%
   - 3-Month Performance > 20%
   - 6-Month Performance > 50%

────────────────────────────────────────
OUTPUT REQUIREMENTS
────────────────────────────────────────

For each symbol that passes all filters, output:

- symbol
- price
- ADR
- dollar volume
- moving average alignment (boolean)
- RSI (14)
- performance metrics (1M, 3M, 6M)
- explanation: short summary of why the symbol passed

Example:
{
    "symbol": "TSLA",
    "price": 245.12,
    "adr": 6.8,
    "dollar_volume": 3_200_000_000,
    "trend_alignment": True,
    "rsi_14": 84.3,
    "perf_1m": 28.1,
    "perf_3m": 22.4,
    "perf_6m": 57.9,
    "explanation": "Strong momentum: RSI 84, stacked MAs, ADR 6.8%, high dollar volume."
}

────────────────────────────────────────
MODE BEHAVIOR
────────────────────────────────────────

When this mode is active:
- Apply ONLY the user-defined criteria above.
- Do NOT apply KK-style scanner logic.
- Do NOT infer additional filters.
- Do NOT relax or tighten thresholds unless explicitly instructed.
- Do NOT merge this screener with KK-style logic unless the user requests a combined mode.

This screener is intended for:
- Momentum discovery
- Watchlist generation
- Pre-filtering before deeper KK-style analysis
- Identifying extreme strength candidates

────────────────────────────────────────
NON-GOALS
────────────────────────────────────────

This mode does NOT:
- Detect KK-style setups
- Evaluate flags, EPs, breakouts, or trend continuation
- Apply KK-style risk logic
- Apply KK-style stop logic
- Perform trade management
- Replace the KK scanner

────────────────────────────────────────
PRIMARY MISSION
────────────────────────────────────────

Provide a clean, deterministic, user-defined momentum screener that mirrors the user’s successful TradingView configuration and can be used as an optional discovery layer within the Nexus platform.