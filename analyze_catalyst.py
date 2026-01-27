#!/usr/bin/env python3
"""Analyze catalyst comparison log for agreement rates."""
import json

data = []
with open('/root/Nexus2/data/catalyst_comparison.jsonl') as f:
    for line in f:
        try:
            data.append(json.loads(line))
        except:
            pass

total = len(data)
if total == 0:
    print("No data found")
    exit()

regex_pass = sum(1 for d in data if d['regex']['type'] is not None and d['regex']['conf'] >= 0.6)
flash_pass = sum(1 for d in data if d['models'].get('flash_lite', {}).get('valid', False))
pro_called = sum(1 for d in data if 'pro' in d['models'])

both_pass = sum(1 for d in data if (d['regex']['type'] is not None and d['regex']['conf'] >= 0.6) and d['models'].get('flash_lite', {}).get('valid', False))
both_fail = sum(1 for d in data if (d['regex']['type'] is None or d['regex']['conf'] < 0.6) and not d['models'].get('flash_lite', {}).get('valid', False))
regex_only = sum(1 for d in data if (d['regex']['type'] is not None and d['regex']['conf'] >= 0.6) and not d['models'].get('flash_lite', {}).get('valid', False))
flash_only = sum(1 for d in data if (d['regex']['type'] is None or d['regex']['conf'] < 0.6) and d['models'].get('flash_lite', {}).get('valid', False))

print(f'=== Catalyst Comparison Report ===')
print(f'Total headlines analyzed: {total}')
print(f'')
print(f'Regex PASS: {regex_pass} ({100*regex_pass/total:.1f}%)')
print(f'Flash PASS: {flash_pass} ({100*flash_pass/total:.1f}%)')
print(f'Pro tiebreaker called: {pro_called} ({100*pro_called/total:.1f}%)')
print(f'')
print(f'=== Agreement Analysis ===')
print(f'Both PASS:  {both_pass} ({100*both_pass/total:.1f}%)')
print(f'Both FAIL:  {both_fail} ({100*both_fail/total:.1f}%)')
print(f'Agreement:  {both_pass + both_fail} ({100*(both_pass+both_fail)/total:.1f}%)')
print(f'')
print(f'=== Disagreements ===')
print(f'Regex PASS, Flash FAIL: {regex_only} - Regex false positives?')
print(f'Regex FAIL, Flash PASS: {flash_only} - Regex gaps to fix!')
print(f'')
print(f'=== Flash-only PASS samples (regex gaps) ===')
count = 0
for d in data:
    if (d['regex']['type'] is None or d['regex']['conf'] < 0.6) and d['models'].get('flash_lite', {}).get('valid', False):
        print(f"  {d['symbol']}: {d['headline'][:55]}... -> {d['models']['flash_lite']['type']}")
        count += 1
        if count >= 15:
            break
