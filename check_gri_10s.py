import json

# Load 10s bar data for GRI
with open(r'nexus2\tests\test_cases\intraday\gri_20260128_10s.json', 'r') as f:
    data = json.load(f)

# Filter bars between 08:44-08:46
bars = [b for b in data['bars'] if '08:44' <= b['t'] <= '08:46']
print(f'Found {len(bars)} bars between 08:44-08:46')

for b in bars[:30]:
    print(f"{b['t']}: ${b['c']:.2f}")
