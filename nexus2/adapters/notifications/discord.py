"""
Discord Notification Adapter

Sends alerts to Discord via webhook.
"""

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import httpx

from nexus2 import config as app_config


class DiscordError(Exception):
    """Discord notification error."""
    pass


@dataclass
class DiscordConfig:
    """Discord webhook configuration."""
    webhook_url: str
    username: str = "Nexus 2"
    avatar_url: Optional[str] = None
    enabled: bool = True


class DiscordNotifier:
    """
    Discord notification service.
    
    Sends formatted alerts to a Discord channel via webhook.
    """
    
    # Emoji for different alert types
    EMOJI = {
        "entry": "🎯",
        "partial": "💰",
        "exit": "🚪",
        "stop": "🛑",
        "warning": "⚠️",
        "error": "❌",
        "success": "✅",
        "scanner": "🔍",
        "info": "ℹ️",
    }
    
    # Colors for embeds (Discord uses decimal)
    COLORS = {
        "green": 5763719,   # #57F287
        "red": 15548997,    # #ED4245
        "yellow": 16776960, # #FFFF00
        "blue": 5793266,    # #5865F2
        "gray": 9807270,    # #95A5A6
    }
    
    def __init__(self, config: Optional[DiscordConfig] = None):
        if config:
            self.config = config
        else:
            # Load from app config if available
            webhook_url = getattr(app_config, 'DISCORD_WEBHOOK_URL', None) or ""
            self.config = DiscordConfig(
                webhook_url=webhook_url,
                enabled=bool(webhook_url),
            )
    
    def _send_webhook(self, payload: dict) -> bool:
        """Send payload to Discord webhook."""
        if not self.config.enabled or not self.config.webhook_url:
            return False
        
        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.post(
                    self.config.webhook_url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                )
                response.raise_for_status()
                return True
        except Exception as e:
            # Log but don't raise - notifications shouldn't break trading
            print(f"Discord notification failed: {e}")
            return False
    
    def _build_embed(
        self,
        title: str,
        description: str,
        color: str = "blue",
        fields: Optional[list] = None,
    ) -> dict:
        """Build Discord embed object."""
        embed = {
            "title": title,
            "description": description,
            "color": self.COLORS.get(color, self.COLORS["blue"]),
            "timestamp": datetime.utcnow().isoformat(),
        }
        
        if fields:
            embed["fields"] = fields
        
        return embed
    
    def send_trade_alert(self, message: str, trade_id: str) -> None:
        """Send trade alert to Discord."""
        # Determine emoji based on message content
        emoji = self.EMOJI["info"]
        color = "blue"
        
        if "PARTIAL" in message.upper():
            emoji = self.EMOJI["partial"]
            color = "green"
        elif "CLOSED" in message.upper() or "EXIT" in message.upper():
            emoji = self.EMOJI["exit"]
            color = "gray"
        elif "STOP" in message.upper():
            emoji = self.EMOJI["stop"]
            color = "red"
        elif "ENTRY" in message.upper() or "SIGNAL" in message.upper():
            emoji = self.EMOJI["entry"]
            color = "green"
        
        embed = self._build_embed(
            title=f"{emoji} Trade Alert",
            description=message,
            color=color,
            fields=[{"name": "Trade ID", "value": f"`{trade_id[:8]}...`", "inline": True}],
        )
        
        payload = {
            "username": self.config.username,
            "embeds": [embed],
        }
        
        if self.config.avatar_url:
            payload["avatar_url"] = self.config.avatar_url
        
        self._send_webhook(payload)
    
    def send_scanner_alert(self, message: str) -> None:
        """Send scanner alert to Discord."""
        embed = self._build_embed(
            title=f"{self.EMOJI['scanner']} Scanner Alert",
            description=message,
            color="blue",
        )
        
        payload = {
            "username": self.config.username,
            "embeds": [embed],
        }
        
        self._send_webhook(payload)
    
    def send_system_alert(self, message: str, level: str = "info") -> None:
        """Send system alert to Discord."""
        emoji = self.EMOJI.get(level, self.EMOJI["info"])
        color_map = {
            "info": "blue",
            "warning": "yellow",
            "error": "red",
            "success": "green",
        }
        color = color_map.get(level, "blue")
        
        embed = self._build_embed(
            title=f"{emoji} System Alert",
            description=message,
            color=color,
        )
        
        payload = {
            "username": self.config.username,
            "embeds": [embed],
        }
        
        self._send_webhook(payload)
    
    def send_position_summary(
        self,
        symbol: str,
        entry_price: float,
        current_price: float,
        pnl: float,
        pnl_pct: float,
        r_multiple: float,
    ) -> None:
        """Send position summary to Discord."""
        emoji = self.EMOJI["success"] if pnl > 0 else self.EMOJI["error"]
        color = "green" if pnl > 0 else "red"
        
        fields = [
            {"name": "Symbol", "value": symbol, "inline": True},
            {"name": "Entry", "value": f"${entry_price:.2f}", "inline": True},
            {"name": "Current", "value": f"${current_price:.2f}", "inline": True},
            {"name": "P&L", "value": f"${pnl:.2f} ({pnl_pct:.1f}%)", "inline": True},
            {"name": "R-Multiple", "value": f"{r_multiple:.1f}R", "inline": True},
        ]
        
        embed = self._build_embed(
            title=f"{emoji} Position Update: {symbol}",
            description="",
            color=color,
            fields=fields,
        )
        
        payload = {
            "username": self.config.username,
            "embeds": [embed],
        }
        
        self._send_webhook(payload)


class ConsoleNotifier:
    """
    Console notification service.
    
    Prints alerts to console. Useful for testing.
    """
    
    def send_trade_alert(self, message: str, trade_id: str) -> None:
        """Print trade alert."""
        print(f"[TRADE ALERT] {message} (ID: {trade_id[:8]})")
    
    def send_scanner_alert(self, message: str) -> None:
        """Print scanner alert."""
        print(f"[SCANNER] {message}")
    
    def send_system_alert(self, message: str, level: str = "info") -> None:
        """Print system alert."""
        print(f"[{level.upper()}] {message}")
