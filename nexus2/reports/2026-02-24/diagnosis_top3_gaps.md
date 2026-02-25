### NPT (ross_npt_20260203)
*   **Bot P&L:** $17,538.56
*   **Ross P&L:** $81,000.00
*   **Delta:** $-63,461.44
*   **Guards:** Not the primary issue.
*   **Exit Trigger:** Technical stop hit.
*   **Biggest Reason for P&L Gap:** The bot's *technical stop* was hit, leading to a significant loss compared to Ross, who managed to capture a large profit. This suggests the stop was either too tight or placed incorrectly relative to the price action.
*   **Code Change Recommendation:**
    *   **File:** `nexus2/strategies/warrior.py`
    *   **Function:** `_apply_technical_stop()`
    *   **Change:** Re-evaluate the logic for setting the technical stop for `NPT` specifically, or for similar high-volatility setups. Consider dynamic stop placement based on recent volatility (e.g., ATR-based stops) rather than a fixed percentage or consolidation low.

### MLEC (ross_mlec_20260213)
*   **Bot P&L:** $-2,997.38
*   **Ross P&L:** $43,000.00
*   **Delta:** $-45,997.38
*   **Guard Blocks:** 1072 re-entry attempts were blocked by various guards (primarily MACD, reentry_loss, and position guards).
*   **Exit Trigger:** Technical stop hit.
*   **Position Size:** Oversized at $58,026.
*   **Biggest Reason for P&L Gap:** A combination of aggressive guard blocking and an oversized position contributed to the substantial loss. When the bot's re-entry attempts were continuously blocked, it missed significant upside, and the eventual stop-out on an oversized position exacerbated the loss.
*   **Code Change Recommendation:**
    *   **File:** `nexus2/strategies/warrior_guards.py`
    *   **Function:** `_check_macd_guard()`, `_check_reentry_loss_guard()`, `_check_position_guard()`
    *   **Change:** Review the parameters and thresholds for these guards. For `MLEC`, they appear to be overly restrictive, preventing valid re-entry. Consider a more dynamic or adaptive guard strategy that loosens after an initial stop-out in strong trends. Also, adjust the position sizing logic to be more conservative for setups like `MLEC` if consistent guard blocking is observed.

### PAVM (ross_pavm_20260121)
*   **Bot P&L:** $105.11
*   **Ross P&L:** $43,950.00
*   **Delta:** $-43,844.89
*   **Guard Blocks:** 272 re-entry attempts were blocked.
*   **Exit Trigger:** Technical stop hit.
*   **Biggest Reason for P&L Gap:** The guards blocked a significant number of re-entry attempts and the technical stop was hit. This prevented the bot from participating in the upside captured by Ross.
*   **Code Change Recommendation:**
    *   **File:** `nexus2/strategies/warrior_guards.py`
    *   **Function:** `_global_entry_cooldown_guard()` or `_entry_timing_guard()`
    *   **Change:** Investigate if the entry timing or cooldown guards are too strict immediately after an initial entry or stop-out. For `PAVM`, these guards (likely `macd` or `reentry_loss` based on the batch report) are preventing re-entry into a potentially profitable trend. Consider making cooldown periods or MACD guard thresholds more permissive if the overall market context is bullish.