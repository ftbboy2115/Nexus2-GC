"""
View: Daily Routine
Version: 3.2.2 (The "Heartbeat" Update)
Author: Gemini (Assistant) & [Your Name]
Date: 2025-12-11

Changelog:
- v3.2.2: Fixed Status Logic. Now uses 'Time Since Last Log' (Heartbeat) to determine Active/Idle.
- v3.2.1: Fixed 'Clear Log' to delete file.
"""
import streamlit as st
import pandas as pd
import os
import sys
import time
import datetime
import market_stats
import config
import utils

# --- HELPER: RETRY LOGIC ---
def safe_read_csv(filepath, retries=5, delay=0.1):
    if not os.path.exists(filepath): return pd.DataFrame()
    for _ in range(retries):
        try:
            df = pd.read_csv(filepath)
            return df
        except Exception: time.sleep(delay)
    return pd.DataFrame()

def render():
    import altair as alt

    st.header("🕓 The Trader's Schedule")

    # 1. HEATMAP (Protected)
    try:
        df_sectors = market_stats.get_sector_performance()
        if not df_sectors.empty:
            st.subheader("🌍 Groups in Play")
            c = alt.Chart(df_sectors).mark_bar().encode(
                x='Sector', y='Change (%)',
                color=alt.condition(alt.datum['Change (%)']>0, alt.value("green"), alt.value("red"))
            ).properties(height=300)
            st.altair_chart(c, theme="streamlit")
    except Exception as e:
        st.error(f"Market Data Error: {e}")

    st.markdown("---")

    # 2. SCHEDULE & SNIPER CONTROLS
    c1, c2 = st.columns([1, 2])
    with c1:
        st.info("**🌅 Morning Scan (Auto)**")
        if st.button("🎯 Launch Sniper"):
            if utils.launch_sniper(): st.toast("Sniper Launched (Background)")
            else: st.error("Launch Failed")

    with c2:
        st.info("**Closing Bell (3:45 PM)**\n1. Check Risk\n2. Trim/Close")

    st.markdown("---")

    # 3. SNIPER LIVE FEED (HEARTBEAT LOGIC)
    log_path = os.path.abspath("sniper.log")
    exists = os.path.exists(log_path)

    is_active = False
    last_mod_msg = "Never"

    if exists:
        try:
            mtime = os.path.getmtime(log_path)
            age = time.time() - mtime
            # If log updated in last 60 seconds, assume Active
            if age < 60:
                is_active = True

            # Format "Last Updated" text
            if age < 60: last_mod_msg = "Just now"
            elif age < 3600: last_mod_msg = f"{int(age/60)}m ago"
            else: last_mod_msg = f"{int(age/3600)}h ago"
        except:
            pass

    # Visual Status Indicators
    status_icon = "🟢" if is_active else "⚪"
    status_text = "Active" if is_active else "Idle"

    with st.expander(f"🎯 Sniper Live Feed ({status_icon} {status_text} - Last: {last_mod_msg})", expanded=False):

        c_refresh, c_clear = st.columns([1, 1])

        with c_refresh:
            auto_refresh = st.toggle("🔄 Auto-Refresh (5s)", value=False)

        with c_clear:
            if st.button("🗑️ Clear Log"):
                if os.path.exists(log_path):
                    try:
                        os.remove(log_path)
                        st.toast("Log Deleted")
                        time.sleep(0.5)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Could not delete log: {e}")

        log_content = "Waiting for sniper logs..."
        if exists:
            try:
                with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                    lines = f.readlines()
                    if not lines: log_content = "[Log file is empty]"
                    else: log_content = "".join(lines[-50:])
            except Exception as e: log_content = f"❌ Error reading log: {e}"
        else:
            log_content = "❌ Log file not found. Launch Sniper to generate it."

        st.code(log_content, language="text")

        if auto_refresh:
            time.sleep(5)
            st.rerun()

    st.markdown("---")

    # 4. EXECUTION LOG
    st.subheader("📜 Execution Log")
    df_log = safe_read_csv(config.TRADE_LOG_FILE)
    if not df_log.empty:
        try:
            def status_color(val): return 'color: green' if val == 'FILLED' else 'color: red'
            st.dataframe(df_log.sort_index(ascending=False).style.map(status_color, subset=['Status']), width="stretch", height=150)
        except Exception as e: st.error(f"Display Error: {e}")
    else: st.info("No trades yet.")

    # ==========================================================================
    # 5. RISK REPORT (COMMANDER)
    # ==========================================================================
    st.markdown("### 🛡️ Risk Commander")
    df_risk = safe_read_csv(config.RISK_REPORT_CSV)

    if not df_risk.empty:

        # --- A. TIMESTAMP & METADATA ---
        if 'Last_Updated' in df_risk.columns:
            last_up = df_risk.iloc[0]['Last_Updated']
            st.caption(f"Last Scanned: {last_up} (Local Time)")
        else:
            st.caption("Last Scanned: N/A")

        # --- B. SORT & FILTER CONTROLS ---
        with st.expander("🌪️ Sort & Filter", expanded=True):
            f_col1, f_col2, f_col3 = st.columns(3)

            with f_col1:
                all_statuses = df_risk['Status'].unique().tolist()
                sel_statuses = st.multiselect("Filter Status:", all_statuses, default=all_statuses)

            with f_col2:
                min_days = int(df_risk['DaysHeld'].min())
                max_days = int(df_risk['DaysHeld'].max())

                if min_days < max_days:
                    val_days = st.slider("Min Days Held:", min_days, max_days, min_days)
                else:
                    st.write(f"**Days Held:** All positions {min_days} days.")
                    val_days = min_days

            with f_col3:
                sort_opt = st.selectbox("Sort By:", [
                    "Urgency (Default)",
                    "PnL (%) Highest",
                    "PnL (%) Lowest",
                    "PnL ($) Highest",
                    "PnL ($) Lowest",
                    "Days Held",
                    "Ticker A-Z"
                ])

        # --- C. APPLY FILTERS ---
        df_view = df_risk[df_risk['Status'].isin(sel_statuses)]
        df_view = df_view[df_view['DaysHeld'] >= val_days]

        if sort_opt == "PnL (%) Highest": df_view = df_view.sort_values("PL_Pct", ascending=False)
        elif sort_opt == "PnL (%) Lowest": df_view = df_view.sort_values("PL_Pct", ascending=True)
        elif sort_opt == "PnL ($) Highest": df_view = df_view.sort_values("PL_Dol", ascending=False)
        elif sort_opt == "PnL ($) Lowest": df_view = df_view.sort_values("PL_Dol", ascending=True)
        elif sort_opt == "Days Held": df_view = df_view.sort_values("DaysHeld", ascending=False)
        elif sort_opt == "Ticker A-Z": df_view = df_view.sort_values("Symbol", ascending=True)

        # --- D. MASTER TOGGLE (OUTSIDE FORM) ---
        c_spacer, c_chk = st.columns([6, 2])

        def toggle_all():
            new_state = st.session_state.master_toggle
            for sym in df_view['Symbol']:
                st.session_state[f"sel_{sym}"] = new_state

        with c_chk:
            st.checkbox("Select/Unselect All", key="master_toggle", on_change=toggle_all)

        # --- E. BATCH FORM RENDER ---
        with st.form("risk_batch_form"):
            # Action Bar
            c_btn1, c_btn2, c_spacer = st.columns([1.5, 1.5, 4])
            with c_btn1:
                do_trim = st.form_submit_button("💰 Trim Selected", help="Sell 1/3")
            with c_btn2:
                do_sell = st.form_submit_button("🚨 Sell Selected", help="Liquidate Position")

            st.divider()

            selected_tickers = []
            today_str = datetime.datetime.now().strftime("%Y-%m-%d")

            if df_view.empty:
                st.info("No positions match your filters.")

            for i, row in df_view.iterrows():
                symbol = row['Symbol']

                # Layout: Checkbox | Card
                c_check, c_card = st.columns([0.5, 10])

                with c_check:
                    st.write("")
                    st.write("")
                    is_checked = st.session_state.get(f"sel_{symbol}", False)
                    if st.checkbox(f"Select {symbol}", key=f"sel_{symbol}", value=is_checked, label_visibility="collapsed"):
                        selected_tickers.append(symbol)

                # Render Card Details
                status = row['Status']
                price = row['Price']
                avg_price = row.get('AvgPrice', 0.0)
                pl_val = row.get('PL_Dol', 0.0)
                pl_pct = row.get('PL_Pct', 0.0) * 100
                days_held = int(row.get('DaysHeld', 0))
                cost_basis = row.get('CostBasis', 0.0)
                mkt_val = row.get('MarketVal', 0.0)
                qty = int(row.get('Qty', 0))
                init_qty = int(row.get('InitQty', qty))

                qty_str = f"{init_qty} ➔ **{qty}**" if qty < init_qty else f"{qty} / {init_qty}"
                pl_color = "green" if pl_val >= 0 else "red"
                pl_str = f":{pl_color}[${pl_val:,.2f} ({pl_pct:+.2f}%)]"
                days_str = f"🔥 **{days_held} Days**" if (3 <= days_held <= 5) else f"{days_held} Days"

                with c_card:
                    with st.container(border=True):
                        # Top
                        r1c1, r1c2, r1c3 = st.columns([2, 2, 2])
                        r1c1.markdown(f"### {symbol}")
                        r1c2.markdown(f"**{status}**")
                        r1c3.write(f"Price: **${price:.2f}**")
                        # Middle
                        r2c1, r2c2, r2c3, r2c4 = st.columns([2, 2, 1, 1])
                        r2c1.caption(f"Cost: ${cost_basis:,.0f} | Mkt: ${mkt_val:,.0f}")
                        r2c2.markdown(f"P/L: {pl_str}")
                        r2c3.markdown(f"Held: {days_str}")
                        r2c4.markdown(f"Qty: {qty_str}")
                        # Bottom
                        r3c1, r3c2 = st.columns([5, 1])
                        r3c1.caption(f"Reason: {row['Reason']}")
                        if row.get('EntryDate', '') == today_str:
                            r3c2.info("🔒 New")

            # --- F. SUBMIT LOGIC ---
            if do_trim:
                if selected_tickers:
                    st.info(f"Trimming: {', '.join(selected_tickers)}...")
                    utils.run_script("portfolio_manager.py", "Batch Trim", args=["--trim"] + selected_tickers)
                    time.sleep(1)
                    st.rerun()
                else:
                    st.warning("⚠️ No tickers selected.")

            if do_sell:
                if selected_tickers:
                    st.error(f"Selling: {', '.join(selected_tickers)}...")
                    utils.run_script("portfolio_manager.py", "Batch Sell", args=["--sell"] + selected_tickers)
                    time.sleep(1)
                    st.rerun()
                else:
                    st.warning("⚠️ No tickers selected.")

    else:
        st.info("Portfolio Empty or Syncing...")