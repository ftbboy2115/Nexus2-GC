import requests
import config

print("Gainers:", len(requests.get(config.FMP_GAINERS_REGULAR).json()))
print("Actives:", len(requests.get(config.FMP_ACTIVES_REGULAR).json()))