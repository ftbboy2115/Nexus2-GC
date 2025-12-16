"""
Project: The Trading Mission Control (Nexus Prime)
Version: 7.5.3
Author: Gemini (Assistant) & [Your Name]
Date: 2025-12-15

Changelog:
- v7.5.3: WATCHLIST BRIDGE.
          - Added Sidebar Section to run 'watchlist_manager.py'.
          - Displays "Last Update" time for watchlist.txt.
- v7.5.2: UI Restoration.
"""
import streamlit as st
import pandas as pd
import os
import json
import time
import datetime
import config
import utils

# Import Views
from views import daily_routine, momentum, episodic, lab, guide, analytics

DASHBOARD_VERSION = "7.5.3"
st.set_page_config(page_title="KK Mission Control", layout="wide", page_icon="📈")

# ==============================================================================
# CONFIG & STORAGE UTILS
# ==============================================================================
def core_script(filename): return os.path.join("core", filename)
SCHEDULER_FILE = os.path.join("data", "scheduler.json")

def load_config():
    defaults = {
        "max_position_size": 500,
        "max_account_risk": 2000,
        "notifications": True,
        "notify_scanner_done": True
    }
    try: return json.load(open(config.USER_CONFIG_FILE))
    except: return defaults

def save_config(cfg):
    with open(config.USER_CONFIG_FILE, "w") as f: json.dump(cfg, f)

def load_scheduler():
    # PRESERVED USER CUSTOM TIMES
    defaults = {
        "enabled_scanner": True, "scanner_time": "08:30", "last_scanner_run": "",
        "enabled_sniper": True,  "sniper_time": "09:35",  "last_sniper_run": "",
        "enabled_ep": True,      "ep_time": "08:45",      "last_ep_run": "",
        "enabled_htf": True,     "htf_time": "19:45",     "last_htf_run": ""
    }
    if not os.path.exists(SCHEDULER_FILE): return defaults
    try:
        with open(SCHEDULER_FILE, "r") as f:
            data = json.load(f)
            # Ensure new keys exist if loading old file
            for k, v in defaults.items():
                if k not in data: data[k] = v
            return data
    except: return defaults

def save_scheduler(data):
    with open(SCHEDULER_FILE, "w") as f: json.dump(data, f)

def get_portfolio_content():
    if not os.path.exists(config.PORTFOLIO_FILE): return "NVDA, TSLA"
    with open(config.PORTFOLIO_FILE, "r") as f: return f.read()

def save_portfolio_content(text):
    clean = ", ".join([t.strip().upper() for t in text.replace('\n', ',').split(',') if t.strip()])
    with open(config.PORTFOLIO_FILE, "w") as f: f.write(clean)

# ==============================================================================
# AUTOMATION HEARTBEAT
# ==============================================================================
def check_automation():
    sch = load_scheduler()
    now = datetime.datetime.now()
    today_str = now.strftime("%Y-%m-%d")
    updated = False

    def is_time_ready(target_str):
        try:
            h, m = map(int, target_str.split(":"))
            target = now.replace(hour=h, minute=m, second=0, microsecond=0)
            return now >= target
        except: return False

    # 1. STRUCTURE SCANNER
    if sch.get("enabled_scanner", True) and sch.get("last_scanner_run") != today_str:
        if is_time_ready(sch.get("scanner_time", "08:30")):
            utils.launch_scanner_background()
            st.toast(f"🤖 Auto-Scanner Launched!", icon="🌊")
            sch["last_scanner_run"] = today_str
            updated = True

    # 2. SNIPER
    if sch.get("enabled_sniper", True) and sch.get("last_sniper_run") != today_str:
        if is_time_ready(sch.get("sniper_time", "09:35")):
            utils.start_task("Sniper_Bot", core_script("sniper.py"))
            st.toast(f"🤖 Auto-Sniper Launched!", icon="🎯")
            sch["last_sniper_run"] = today_str
            updated = True

    # 3. EP RADAR
    if sch.get("enabled_ep", True) and sch.get("last_ep_run") != today_str:
        if is_time_ready(sch.get("ep_time", "08:45")):
            utils.launch_ep_scanner_background()
            st.toast(f"🤖 Auto-EP Scanner Launched!", icon="🚀")
            sch["last_ep_run"] = today_str
            updated = True

    # 4. HTF SCANNER
    if sch.get("enabled_htf", True) and sch.get("last_htf_run") != today_str:
        if is_time_ready(sch.get("htf_time", "19:45")):
            utils.launch_htf_background()
            st.toast(f"🤖 Auto-HTF Scanner Launched!", icon="🏁")
            sch["last_htf_run"] = today_str
            updated = True

    if updated: save_scheduler(sch)

# ==============================================================================
# SIDEBAR CONTROLLER
# ==============================================================================
with st.sidebar:
    st.title("🚀 Mission Control")
    st.caption(f"v{DASHBOARD_VERSION} (Nexus Prime)")

    check_automation()
    cfg = load_config()

    # 2. SYSTEM LOGS
    if 'system_log' in st.session_state and st.session_state['system_log']:
        with st.expander("📝 System Logs", expanded=True):
            if st.session_state.get('log_type') == 'error': st.error("Failed")
            else: st.success("Complete")
            st.code(st.session_state['system_log'], language="text")
            if st.button("Clear Log"): st.session_state['system_log'] = None; st.rerun()
    st.markdown("---")

    # 3. WATCHLIST BRIDGE (NEW)
    with st.expander("🌉 Watchlist Bridge", expanded=True):
        # Check Timestamp
        last_update = "Never"
        if os.path.exists(config.WATCHLIST_FILE):
            ts = os.path.getmtime(config.WATCHLIST_FILE)
            last_update = datetime.datetime.fromtimestamp(ts).strftime('%m-%d %H:%M')

        st.caption(f"Last Focus List Update: {last_update}")

        if st.button("🔄 Build Focus List", help="Aggregates EP+HTF+Momentum -> Watchlist"):
            s, l = utils.run_script(core_script("watchlist_manager.py"), "Watchlist Manager")
            st.session_state['system_log'] = l
            st.session_state['log_type'] = "success" if s else "error"
            st.rerun()

    # 4. CONFIGURATION
    with st.expander("⚙️ System & Risk"):
        new_pos = st.number_input("Max Size ($)", value=cfg.get("max_position_size", 500))
        new_risk = st.number_input("Max Account ($)", value=cfg.get("max_account_risk", 2000))
        st.markdown("---")
        notif_discord = st.checkbox("🔔 Discord Alerts", value=cfg.get("notifications", True))
        notif_toast = st.checkbox("🍞 Browser Toasts", value=cfg.get("notify_scanner_done", True))

        if st.button("💾 Save Config"):
            cfg.update({
                "max_position_size": new_pos,
                "max_account_risk": new_risk,
                "notifications": notif_discord,
                "notify_scanner_done": notif_toast
            })
            save_config(cfg)
            st.success("Configuration Saved!")

    # 5. SCHEDULER
    with st.expander("🤖 Automation & Scheduler"):
        sch = load_scheduler()

        # 1. Structure
        c1, c2 = st.columns([3, 2])
        c1.checkbox("🌊 Structure", value=sch.get("enabled_scanner", True), key="tog_scan")
        t_scan = c2.time_input("T1", value=datetime.datetime.strptime(sch.get("scanner_time", "08:30"), "%H:%M").time(), label_visibility="collapsed", key="time_scan", step=60)

        # 2. Sniper
        c3, c4 = st.columns([3, 2])
        c3.checkbox("🎯 Sniper", value=sch.get("enabled_sniper", True), key="tog_snip")
        t_snip = c4.time_input("T2", value=datetime.datetime.strptime(sch.get("sniper_time", "09:35"), "%H:%M").time(), label_visibility="collapsed", key="time_snip", step=60)

        # 3. EP Radar
        c5, c6 = st.columns([3, 2])
        c5.checkbox("🚀 EP Radar", value=sch.get("enabled_ep", True), key="tog_ep")
        t_ep = c6.time_input("T3", value=datetime.datetime.strptime(sch.get("ep_time", "08:45"), "%H:%M").time(), label_visibility="collapsed", key="time_ep", step=60)

        # 4. HTF Scanner
        c7, c8 = st.columns([3, 2])
        c7.checkbox("🏁 HTF Scan", value=sch.get("enabled_htf", True), key="tog_htf")
        t_htf = c8.time_input("T4", value=datetime.datetime.strptime(sch.get("htf_time", "19:45"), "%H:%M").time(), label_visibility="collapsed", key="time_htf", step=60)

        if st.button("💾 Save Schedule"):
            sch["enabled_scanner"] = st.session_state.tog_scan
            sch["scanner_time"] = t_scan.strftime("%H:%M")
            sch["enabled_sniper"] = st.session_state.tog_snip
            sch["sniper_time"] = t_snip.strftime("%H:%M")
            sch["enabled_ep"] = st.session_state.tog_ep
            sch["ep_time"] = t_ep.strftime("%H:%M")
            sch["enabled_htf"] = st.session_state.tog_htf
            sch["htf_time"] = t_htf.strftime("%H:%M")

            save_scheduler(sch)
            st.success("Schedule Updated!")

    st.markdown("---")

    # 6. NAVIGATION
    st.header("📍 Navigation")
    page = st.radio("Go to:", ["📋 Daily Routine", "💥 Episodic Pivots", "🌊 Daily Structure", "🧪 Strategy Lab", "📊 Performance", "📚 User Guide"], label_visibility="collapsed")
    st.markdown("---")

    if page == "📋 Daily Routine":
        with st.expander("💼 Portfolio"):
            cur = get_portfolio_content()
            new = st.text_area("Tickers:", value=cur)
            if st.button("Save"): save_portfolio_content(new); st.success("Saved!")

    # 7. OPERATIONS
    st.header("⚡ Operations")

    # 1. STRUCTURE
    status_mom = utils.get_task_status("Momentum_Scanner")
    if status_mom == "running":
        if st.button("🛑 STOP Structure Scan", type="primary", use_container_width=True):
            utils.stop_task("Momentum_Scanner")
            st.rerun()
        st.caption("Status: 🟢 Running (Check Window)")
    else:
        if st.button("🌊 Scan Structure (Manual)", use_container_width=True):
            utils.launch_scanner_background()
            st.rerun()

    # 2. EP SCANNER
    status_ep = utils.get_task_status("EP_Scanner")
    if status_ep == "running":
        if st.button("🛑 STOP EP Scanner", type="primary", use_container_width=True):
            utils.stop_task("EP_Scanner")
            st.rerun()
        st.caption("Status: 🟢 Running (Check Window)")
    else:
        if st.button("🚀 Scan EP (Manual)", use_container_width=True):
            utils.launch_ep_scanner_background()
            st.rerun()

    # 3. HTF SCANNER
    status_htf = utils.get_task_status("HTF_Scanner")
    if status_htf == "running":
        if st.button("🛑 STOP HTF Scanner", type="primary", use_container_width=True):
            utils.stop_task("HTF_Scanner")
            st.rerun()
        st.caption("Status: 🟢 Running (Check Window)")
    else:
        if st.button("🏁 Scan HTF (Manual)", use_container_width=True):
            utils.launch_htf_background()
            st.rerun()

    st.markdown("---")

    # RISK MANAGER
    if st.button("🛡️ Check Risk", use_container_width=True):
        s, l = utils.run_script(core_script("portfolio_manager.py"), "Risk Manager")
        st.session_state['system_log']=l; st.session_state['log_type']="success" if s else "error"; st.rerun()

    st.markdown("---")

    # KILL SWITCH
    if os.path.exists(config.KILL_SWITCH_FILE):
        if st.button("🔓 UNLOCK SYSTEM", type="primary", use_container_width=True):
            s, l = utils.run_script(core_script("paper_trader.py"), "UNLOCK", args=["--unlock"])
            st.session_state['system_log'] = l; st.rerun()
    else:
        c_stop, c_kill = st.columns(2)
        with c_stop:
            if st.button("🛑 DISABLE", use_container_width=True):
                with open(config.KILL_SWITCH_FILE, "w") as f: f.write("DISABLED")
                st.rerun()
        with c_kill:
            if st.button("🚨 LIQUIDATE ALL", type="primary", use_container_width=True):
                s, l = utils.run_script(core_script("paper_trader.py"), "LIQUIDATION", args=["--close-all"])
                st.session_state['system_log'] = l; st.rerun()

    if st.button("🔄 Refresh State", use_container_width=True): st.rerun()

# ==============================================================================
# MAIN ROUTER
# ==============================================================================
if page == "📋 Daily Routine": daily_routine.render()
elif page == "💥 Episodic Pivots": episodic.render()
elif page == "🌊 Daily Structure": momentum.render()
elif page == "🧪 Strategy Lab": lab.render()
elif page == "📊 Performance": analytics.render()
elif page == "📚 User Guide": guide.render()