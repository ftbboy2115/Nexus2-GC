"""Check Discord webhook configuration."""
from nexus2 import config

webhook = getattr(config, 'DISCORD_WEBHOOK_URL', None)
print(f"DISCORD_WEBHOOK_URL: {webhook if webhook else 'NOT SET'}")
print(f"Enabled: {bool(webhook)}")
