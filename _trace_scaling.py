"""
Trace scaling behavior for specific test cases.
Runs single cases in-process with log capture to file.
"""
import asyncio
import logging
import sys
import os

# Set up file logging BEFORE any imports
log_file = os.path.join(os.path.dirname(__file__), "scaling_trace.log")
file_handler = logging.FileHandler(log_file, mode='w', encoding='utf-8')
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(logging.Formatter('%(name)s - %(message)s'))

# Configure root logger to capture everything
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)
root_logger.addHandler(file_handler)

# Also add console handler for key events
console = logging.StreamHandler(sys.stdout)
console.setLevel(logging.WARNING)
root_logger.addHandler(console)

# Now import project modules
from nexus2.adapters.simulation.sim_context import _run_case_sync

import yaml


def run_case(case_id: str):
    """Run a single case with logging."""
    yaml_path = os.path.join(os.path.dirname(__file__), "nexus2", "tests", "test_cases", "warrior_setups.yaml")
    with open(yaml_path, 'r') as f:
        yaml_data = yaml.safe_load(f)
    
    # Find the case
    cases = yaml_data.get("test_cases", [])
    target = None
    for c in cases:
        if c.get("id") == case_id:
            target = c
            break
    
    if not target:
        print(f"Case {case_id} not found. Available: {[c['id'] for c in cases]}")
        return
    
    print(f"Running case: {case_id} ({target.get('symbol')})")
    print(f"Logging to: {log_file}")
    
    result = _run_case_sync((target, yaml_data))
    
    print(f"\nResult: P&L = ${result.get('total_pnl', 0):.2f}")
    print(f"Ross P&L = ${result.get('ross_pnl', 0):.2f}")
    print(f"Trades: {len(result.get('trades', []))}")
    
    # Count trace lines
    with open(log_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    trace_lines = [l for l in content.split('\n') if 'Warrior Scale TRACE' in l]
    scale_exec_lines = [l for l in content.split('\n') if 'SCALE EXECUTED' in l]
    checkpoint_lines = [l for l in content.split('\n') if 'CHECKPOINT' in l]
    
    print(f"\nTrace summary:")
    print(f"  CHECKPOINT events: {len(checkpoint_lines)}")
    print(f"  SCALE EXECUTED events: {len(scale_exec_lines)}")
    print(f"  Total TRACE lines: {len(trace_lines)}")
    
    if scale_exec_lines:
        print(f"\nScale execution details:")
        for line in scale_exec_lines:
            print(f"  {line.strip()}")


if __name__ == "__main__":
    # Run the worst regression cases
    cases_to_test = [
        "ross_vero_20260116",   # -$1,667 regression
        "ross_rolr_20260114",   # -$1,026 regression  
        "ross_batl_20260127",   # -$488 regression
    ]
    
    case_id = cases_to_test[0]  # Start with VERO
    if len(sys.argv) > 1:
        case_id = sys.argv[1]
    
    run_case(case_id)
