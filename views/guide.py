"""
Module: User Guide (The Field Manual)
Version: 2.2.0
Author: Gemini (Assistant) & [Your Name]
Date: 2025-12-14

Changelog:
- v2.2.0: Added "End-of-Day Drill" (Risk Management).
          - Defines Soft Stop (10 EMA) and Hard Stop (20 SMA).
- v2.1.0: Strategic Correction (EP -> Sniper -> Structure Scan).
"""
import streamlit as st

def render():
    st.markdown("""
    # 📘 Nexus Prime Field Manual (v7.1.0)
    
    **Architecture:** Nexus Core (Modular)  
    **Data Engine:** Financial Modeling Prep (FMP) + Alpaca  
    **Objective:** Capture institutional momentum while strictly managing risk.

    ---

    ### ⏰ Section 1: The Optimized Daily Workflow (KK Method)

    **09:00 AM | The Hunt (Pre-Market)**
    1. **Run "💥 Episodic Pivots" (EP Scanner):**
       * **Goal:** Find stocks gapping up >8% on News/Earnings *before* the open.
       * **Action:** Review the charts. If valid, the system auto-adds them to your Watchlist.

    **09:15 AM | The Setup Scan (Daily Structure)**
    1. **Run "🌊 Momentum Setups" (Structure Scanner):**
       * **Goal:** Find stocks with perfect Daily Structure ("Surfing" 10EMA or "Coiling").
       * **Action:** It populates a CSV list. The Sniper picks these up if they break out.

    **09:20 AM | Arm the System**
    1. **Go to "📋 Daily Routine".**
    2. **Click "Launch Sniper".**
       * **Status:** The Sniper watches both your EP Gaps and your Momentum Setups.

    **09:30 AM | Market Open**
    * **DO NOTHING.** The system calculates the Opening Range (ORB-5).

    **09:35 AM - 10:30 AM | The Kill Zone**
    * If a target breaks its range + volume + uptrend, the **Sniper** fires.
    * **Action:** Verify trade in Alpaca. You manage the exit.

    **03:45 PM | The End-of-Day Drill (CRITICAL)**
    * **Goal:** Kill weak stocks *before* the close. Don't hold losers overnight.
    * **Action:** Click **"🛡️ Check Risk"** and look at the Status column.
    * **The Rules:**
        * **⚠️ WARN (Below 10 EMA):** The "Soft Stop." The sprint is slowing down.
            * *Decision:* Trim position if you want to lock gains, or hold if you have cushion.
        * **🚨 SELL (Below 20 SMA):** The "Hard Stop." The trend is broken.
            * *Decision:* **LIQUIDATE.** Do not hold this overnight. It is now a falling knife.

    **04:05 PM | Post-Market Review**
    1. Click **"📊 Performance"**.
    2. Review your grades (Win Rate, R-Multiple).
    3. **Shutdown:** Close the terminal window.

    ---

    ### 🖥️ Section 2: Mission Control (Tabs Overview)

    #### **1. 💥 Episodic Pivots (The Hunter)**
    * **Function:** Scans for **Gaps** (Open > Prev Close + 8%) and **High Volume**.
    * **Output:** Updates `watchlist.txt` with high-probability gap plays.

    #### **2. 🌊 Momentum Setups (The Structure Scanner)**
    * **Function:** Scans 100 days of history to find "Perfect" setups.
    * **The Criteria:**
        * **Surfing:** Riding the 10 EMA (Strong Trend).
        * **Coiling:** Low volatility compression (Ready to explode).
    * **Telemetry:** `Stocks/Sec` is system speed, not market speed.
    * **Output:** Saves a list of candidates to `momentum_results.csv`.

    #### **3. 📋 Daily Routine**
    * **Function:** The Command Center.
    * **Key Features:**
        * **Launcher:** Starts the Sniper.
        * **Portfolio:** A "Sticky Note" that syncs with your actual Alpaca holdings.

    #### **4. 📊 Performance (The Mirror)**
    * **Function:** Your brutally honest report card.
    * **Grades:**
        * **Win Rate:** Target **30-50%**.
        * **Avg Gain:** Winners should be **10%+**.
        * **Avg Loss:** Losers must be **< 1%**.

    ---

    ### 🛡️ Section 3: Safety Systems

    1. **Trend Guard (20 SMA):** Rejects any stock trading below its 20-day SMA.
    2. **Gap Filter (Green Day):** Rejects stocks trading below yesterday's close.
    3. **Liquidity Floor:** EP Scanner ignores stocks with < $10M volume.
    4. **Kill Switch:** **🚨 LIQUIDATE** button in sidebar instantly closes ALL positions.

    ---
    
    ### 🔧 Section 4: Troubleshooting

    | Issue | Diagnosis | Fix |
    | :--- | :--- | :--- |
    | **"Connecting..." forever** | Python server down. | Close browser. Restart "Nexus Trader". |
    | **"Portfolio Empty"** | No trade history yet. | Wait for first completed trade. |
    | **"API Limit Reached"** | FMP Free Tier exhausted. | Wait 24h or upgrade key. |

    **Status:** ALL SYSTEMS GO.  
    *Good luck on the markets.*
    """)