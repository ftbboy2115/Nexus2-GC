"""
Project: Discord Webhook Tester
Version: 1.0.0
Author: Gemini (Assistant) & [Your Name]
"""
import requests
import os
import matplotlib.pyplot as plt
from dotenv import load_dotenv

# 1. Load Key
load_dotenv()
DISCORD_URL = os.environ.get("DISCORD_WEBHOOK")

if not DISCORD_URL:
    print("❌ ERROR: DISCORD_WEBHOOK not found in .env file.")
    exit()

print(f"Testing Webhook: {DISCORD_URL[:30]}...")

# 2. Generate a Fake Chart (to test image upload)
print("Generating test chart...")
plt.figure(figsize=(10, 5))
plt.plot([10, 20, 15, 25, 30], label="Fake Price")
plt.title("TEST CHART: NVDA Episodic Pivot")
plt.legend()
plt.savefig("test_chart.png")

# 3. Send Payload
print("Sending alert...")

embed = {
    "title": "🚨 TEST ALERT: NVDA",
    "description": "This is a test of the Episodic Pivot notification system.",
    "color": 5763719,  # Green
    "fields": [
        {"name": "Price", "value": "$145.50", "inline": True},
        {"name": "Gap %", "value": "+12.5%", "inline": True},
        {"name": "Vol Ratio", "value": "3.5x Avg", "inline": True},
        {"name": "Catalyst", "value": "Q3 Earnings Beat + AI Guidance Raise", "inline": False}
    ]
}

try:
    # Send Text
    r1 = requests.post(DISCORD_URL, json={"embeds": [embed]})
    r1.raise_for_status()
    print("✅ Text Payload Sent.")

    # Send Image
    with open("test_chart.png", "rb") as f:
        r2 = requests.post(DISCORD_URL, files={"file": f})
    r2.raise_for_status()
    print("✅ Image Payload Sent.")

    print("\n🎉 SUCCESS! Check your Discord channel now.")

except Exception as e:
    print(f"\n❌ FAILED: {e}")

# Cleanup
if os.path.exists("test_chart.png"):
    os.remove("test_chart.png")