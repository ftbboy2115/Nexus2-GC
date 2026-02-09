#!/usr/bin/env python3
"""Extract a specific case from batch results."""
import json
import sys

results_file = "/tmp/batch_results.json" if sys.platform != "win32" else "batch_results.json"

# Allow custom file path
if len(sys.argv) >= 3:
    results_file = sys.argv[2]

with open(results_file) as f:
    data = json.load(f)

filter_text = sys.argv[1] if len(sys.argv) >= 2 else ""

for r in data["results"]:
    case_id = r.get("case_id", "")
    if filter_text.lower() in case_id.lower():
        print(json.dumps(r, indent=2, default=str))
        print()
