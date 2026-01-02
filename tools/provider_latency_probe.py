"""
File: /tools/worker_live_probe.py
Version: 1.0.0
Author: Nexus Project (Clay + Copilot)

Purpose:
    Live integration probe for WorkerController + Provider.
    - Calls provider.ping() in real time
    - Measures latency
    - Feeds results into WorkerController
    - Prints controller debug snapshots
    - Useful for validating integration behavior under real network conditions

Usage:
    python worker_live_probe.py
"""

import time
from datetime import datetime

# Adjust imports to match your project structure
from core.worker_controller import WorkerController
from nexus_pipeline.providers.alpaca_provider import AlpacaProvider


def log(msg: str):
    """Simple timestamped logger."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    print(f"[{ts}] {msg}")


def run_worker_live_probe(scanner_name: str = "EP", delay: float = 1.0):
    """
    Integration-level diagnostic:
    - Provider + WorkerController together
    - Real API calls
    - Real latency
    - Real controller state updates
    """
    provider = AlpacaProvider()
    controller = WorkerController(scanner_name=scanner_name)

    print("\n=== WorkerController Live Probe ===")
    print(f"Scanner: {scanner_name}")
    print(f"Provider: {provider.__class__.__name__}")
    print(f"Delay between iterations: {delay}s")
    print("Press Ctrl+C to stop.\n")

    iteration = 0

    try:
        while True:
            iteration += 1
            log(f"Iteration {iteration} — calling provider.ping()")

            start = time.time()
            status = provider.ping()
            latency = time.time() - start

            log(f"Status: {status}")
            log(f"Latency: {latency:.4f} sec")

            # Feed into WorkerController
            controller.record_api_call(latency, status)

            # Print controller snapshot
            snapshot = controller.debug_snapshot()
            print(snapshot)
            print("-" * 60)

            time.sleep(delay)

    except KeyboardInterrupt:
        print("\n=== Live Probe Stopped by User ===\n")


if __name__ == "__main__":
    run_worker_live_probe(scanner_name="EP", delay=1.0)