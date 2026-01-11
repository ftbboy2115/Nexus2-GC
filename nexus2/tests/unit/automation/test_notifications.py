"""
Tests for Notification Adapters
"""

import pytest
from unittest.mock import MagicMock, patch

from nexus2.adapters.notifications import (
    DiscordNotifier,
    DiscordConfig,
    ConsoleNotifier,
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def discord_config():
    """Discord config with test webhook."""
    return DiscordConfig(
        webhook_url="https://discord.com/api/webhooks/test/token",
        username="Test Bot",
        enabled=True,
    )


@pytest.fixture
def disabled_config():
    """Disabled Discord config."""
    return DiscordConfig(
        webhook_url="",
        enabled=False,
    )


@pytest.fixture
def console_notifier():
    """Console notifier."""
    return ConsoleNotifier()


# ============================================================================
# DiscordNotifier Tests
# ============================================================================

class TestDiscordNotifier:
    """Tests for DiscordNotifier."""
    
    def test_disabled_notifier_doesnt_send(self, disabled_config):
        """Disabled notifier doesn't attempt to send."""
        notifier = DiscordNotifier(disabled_config)
        
        # Should not raise, just return silently
        notifier.send_trade_alert("Test message", "test-id-123")
        notifier.send_scanner_alert("Scanner message")
        notifier.send_system_alert("System message")
    
    @patch("nexus2.adapters.notifications.discord.httpx.Client")
    def test_trade_alert_sends_webhook(self, mock_client_class, discord_config):
        """Trade alert sends webhook request."""
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.return_value = MagicMock(status_code=204)
        mock_client_class.return_value = mock_client
        
        notifier = DiscordNotifier(discord_config)
        notifier.send_trade_alert("PARTIAL EXIT: NVDA", "abc123")
        
        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args
        assert "discord.com" in call_args[0][0]
    
    @patch("nexus2.adapters.notifications.discord.httpx.Client")
    def test_scanner_alert_sends_webhook(self, mock_client_class, discord_config):
        """Scanner alert sends webhook request."""
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.return_value = MagicMock(status_code=204)
        mock_client_class.return_value = mock_client
        
        notifier = DiscordNotifier(discord_config)
        notifier.send_scanner_alert("Found 5 EP setups")
        
        mock_client.post.assert_called_once()
    
    def test_build_embed_structure(self, discord_config):
        """Embed has correct structure."""
        notifier = DiscordNotifier(discord_config)
        embed = notifier._build_embed(
            title="Test Title",
            description="Test Description",
            color="green",
        )
        
        assert embed["title"] == "Test Title"
        assert embed["description"] == "Test Description"
        assert embed["color"] == notifier.COLORS["green"]
        assert "timestamp" in embed


# ============================================================================
# ConsoleNotifier Tests
# ============================================================================

class TestConsoleNotifier:
    """Tests for ConsoleNotifier."""
    
    def test_trade_alert_prints(self, console_notifier, capsys):
        """Trade alert prints to console."""
        console_notifier.send_trade_alert("Test trade", "abc123def")
        
        captured = capsys.readouterr()
        assert "TRADE ALERT" in captured.out
        assert "Test trade" in captured.out
    
    def test_scanner_alert_prints(self, console_notifier, capsys):
        """Scanner alert prints to console."""
        console_notifier.send_scanner_alert("Found setups")
        
        captured = capsys.readouterr()
        assert "SCANNER" in captured.out
        assert "Found setups" in captured.out
    
    def test_system_alert_prints(self, console_notifier, capsys):
        """System alert prints to console."""
        console_notifier.send_system_alert("System message", level="warning")
        
        captured = capsys.readouterr()
        assert "WARNING" in captured.out
        assert "System message" in captured.out
