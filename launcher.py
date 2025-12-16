import os
import sys
import subprocess

# CONFIGURATION
DASHBOARD_PATH = os.path.join("core", "dashboard.py")


def main():
    print("--- NEXUS LAUNCHER ---")

    # Path Patching
    env = os.environ.copy()
    root_path = os.getcwd()

    if "PYTHONPATH" in env:
        env["PYTHONPATH"] = root_path + os.pathsep + env["PYTHONPATH"]
    else:
        env["PYTHONPATH"] = root_path

    print(f"Root: {root_path}")
    print(f"Target: {DASHBOARD_PATH}")

    # Launch Streamlit
    cmd = [sys.executable, "-m", "streamlit", "run", DASHBOARD_PATH]

    try:
        subprocess.run(cmd, env=env, check=False)
    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    main()