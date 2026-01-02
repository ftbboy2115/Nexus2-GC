import requests

url = "https://scanner.tradingview.com/america/scan"

fields_to_test = [
    "premarket_price",
    "premarket_change",
    "premarket_change_percent",
    "premarket_volume",
    "premarket_close",
    "premarket",
]

for field in fields_to_test:
    payload = {
        "symbols": {"tickers": [], "query": {"types": []}},
        "columns": ["name", field],
        "sort": {"sortBy": "name", "sortOrder": "asc"},
        "range": [0, 1]
    }

    resp = requests.post(url, json=payload)
    print(field, "=>", resp.status_code)
    if resp.status_code != 200:
        print(resp.text[:200])
    print()