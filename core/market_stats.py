"""
Project: Market Statistics Engine
Version: 1.0.0
Author: Gemini (Assistant) & [Your Name]
Date: 2025-12-04

Goal: Fetch real-time sector performance to identify market rotation.
"""
import requests
import pandas as pd
import os
from dotenv import load_dotenv

load_dotenv()
FMP_KEY = os.environ.get("FMP_API_KEY")


def get_sector_performance():
    """
    Fetches real-time sector performance from FMP.
    Returns a DataFrame sorted by performance.
    """
    if not FMP_KEY:
        return pd.DataFrame()

    url = f"https://financialmodelingprep.com/api/v3/sector-performance?apikey={FMP_KEY}"

    try:
        response = requests.get(url)
        data = response.json()

        # FMP returns list of dicts: [{'sector': 'Technology', 'changesPercentage': '2.5%'}]
        df = pd.DataFrame(data)

        # Clean up the percentage string (remove '%' and convert to float)
        df['changesPercentage'] = df['changesPercentage'].astype(str).str.replace('%', '', regex=False)
        df['changesPercentage'] = pd.to_numeric(df['changesPercentage'], errors='coerce')

        # Rename for display
        df.columns = ['Sector', 'Change (%)']

        # Sort best to worst
        df = df.sort_values(by='Change (%)', ascending=False)
        return df

    except Exception as e:
        print(f"Sector API Error: {e}")
        return pd.DataFrame()