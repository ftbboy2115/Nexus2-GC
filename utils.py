"""
Project: Nexus Core Utilities
Filename: utils.py (ROOT DIRECTORY)
Version: 3.8.9
Changelog:
- v3.8.9: PYTHONPATH INJECTION.
          - run_script() now explicitly adds BASE_DIR to PYTHONPATH.
          - Solves ModuleNotFoundError for subprocesses (HTF Scanner fix).
- v3.8.8: Encoding Fix.
"""

import os
import sys
import json
import subprocess
import datetime
from colorama import init

init(autoreset=True)

# --- CONFIGURATION ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
PROCESS_REGISTRY_FILE = os.path.join(DATA_DIR, "active_processes.json")

if not os.path.exists(DATA_DIR): os.makedirs(DATA_DIR)

# ==============================================================================
# 1. PROCESS MANAGEMENT
# ==============================================================================
def _load_registry():
    if not os.path.exists(PROCESS_REGISTRY_FILE): return {}
    try:
        with open(PROCESS_REGISTRY_FILE, "r") as f: return json.load(f)
    except: return {}

def _save_registry(data):
    with open(PROCESS_REGISTRY_FILE, "w") as f: json.dump(data, f, indent=4)

def start_task(script_name, script_path):
    registry = _load_registry()

    if script_name in registry:
        old_pid = registry[script_name]['pid']
        if is_process_running(old_pid):
            return old_pid
        else:
            del registry[script_name]

    print(f"[LAUNCH] Spawning {script_name} in new window...")

    try:
        full_script_path = os.path.join(BASE_DIR, script_path)
        cmd = f'start "{script_name}" cmd /k ""{sys.executable}" "{full_script_path}""'

        process = subprocess.Popen(cmd, shell=True)

        registry[script_name] = {
            "pid": process.pid,
            "start_time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "path": full_script_path
        }
        _save_registry(registry)
        return process.pid

    except Exception as e:
        print(f"[ERROR] Launch failed: {e}")
        return None

def stop_task(script_name):
    registry = _load_registry()
    if script_name not in registry: return False
    del registry[script_name]
    _save_registry(registry)
    return True

def get_task_status(script_name):
    registry = _load_registry()
    if script_name in registry: return "running"
    return "stopped"

def is_process_running(pid): return True

# ==============================================================================
# 2. FILE & LOGGING UTILS
# ==============================================================================
def print_metadata(name, version):
    print("=" * 60)
    print(f"[SCRIPT]:   {name}")
    print(f"[VERSION]:  {version}")
    print(f"[TIME]:     {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

def clean_folder(folder_path):
    if not os.path.exists(folder_path): os.makedirs(folder_path)
    for filename in os.listdir(folder_path):
        file_path = os.path.join(folder_path, filename)
        try:
            if os.path.isfile(file_path): os.unlink(file_path)
        except: pass

# ==============================================================================
# 3. LEGACY WRAPPERS (BLOCKING)
# ==============================================================================
def run_script(script_path, name, args=None):
    """
    Runs a script (blocking) and captures output.
    INJECTS PYTHONPATH to ensure imports (config, utils) always work.
    """
    cmd = [sys.executable, script_path]
    if args: cmd.extend(args)

    # --- ENVIRONMENT INJECTION ---
    env = os.environ.copy()
    # Add the Project Root (Nexus/) to the python path
    env["PYTHONPATH"] = BASE_DIR + os.pathsep + env.get("PYTHONPATH", "")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=BASE_DIR,
            encoding='utf-8',
            errors='replace',
            env=env  # <--- PASS THE MODIFIED ENVIRONMENT
        )

        stdout = result.stdout if result.stdout else ""
        stderr = result.stderr if result.stderr else ""

        return result.returncode == 0, stdout + stderr

    except Exception as e:
        return False, f"Subprocess Critical Error: {str(e)}"

# ==============================================================================
# 4. BACKGROUND LAUNCHERS
# ==============================================================================
def launch_ep_scanner_background():
    return start_task("EP_Scanner", os.path.join("core", "scan_ep.py"))

def launch_scanner_background():
    return start_task("Momentum_Scanner", os.path.join("core", "scan_trend_daily.py"))

def launch_htf_background():
    return start_task("HTF_Scanner", os.path.join("core", "scan_htf.py"))

def launch_sniper():
    return start_task("Sniper_Bot", os.path.join("core", "sniper.py"))

# ==============================================================================
# 5. MARKET UTILS
# ==============================================================================
def check_catalyst(symbol): return True