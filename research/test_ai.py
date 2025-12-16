import utils
import os
from dotenv import load_dotenv

# Load API keys from your .env file
load_dotenv()

# Check if keys exist
print(f"FMP KEY: {'✅ Found' if os.environ.get('FMP_API_KEY') else '❌ Missing'}")
print(f"GEMINI KEY: {'✅ Found' if os.environ.get('GOOGLE_API_KEY') else '❌ Missing'}")

print("\n--- TEST 1: High Profile Stock (Expect TRUE) ---")
# NVDA usually has news/earnings/analyst notes
result_good = utils.check_catalyst("NVDA")
print(f"FINAL DECISION: {result_good}")

print("\n--- TEST 2: Boring/Random Stock (Expect FALSE) ---")
# A random utility or REIT often lacks "Explosive" catalysts
result_bad = utils.check_catalyst("ED") # Consolidated Edison
print(f"FINAL DECISION: {result_bad}")