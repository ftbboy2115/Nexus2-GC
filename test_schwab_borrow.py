#!/usr/bin/env python3
"""Test Schwab API for shortable/borrow data."""
from nexus2.adapters.market_data.schwab_adapter import get_schwab_adapter
import httpx
import json

schwab = get_schwab_adapter()
print('Authenticated:', schwab.is_authenticated())

if schwab.is_authenticated():
    # Get raw API response to see all fields
    response = httpx.get(
        'https://api.schwabapi.com/marketdata/v1/quotes',
        params={'symbols': 'PDYN', 'fields': 'quote,fundamental,extended'},
        headers={'Authorization': f'Bearer {schwab._access_token}'},
        timeout=10
    )
    print('Status:', response.status_code)
    print(json.dumps(response.json(), indent=2))
else:
    print('Not authenticated - cannot test')
