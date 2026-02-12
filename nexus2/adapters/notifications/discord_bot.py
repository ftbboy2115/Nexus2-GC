"""
Discord Bot for Quote Divergence Approvals

A background Discord bot that:
1. Sends divergence alerts with reaction options
2. Listens for reactions to resolve pending approvals
3. Supports skip durations from 10min to end of day

Requires: discord.py>=2.0
"""

import asyncio
import logging
from typing import Optional
from datetime import datetime

import discord
from discord import Client, Intents, Message, RawReactionActionEvent

from nexus2 import config as app_config
from nexus2.domain.audit.pending_approvals import (
    get_pending_queue,
    PendingApproval,
    ApprovalStatus,
)
from nexus2.domain.audit.symbol_blacklist import get_symbol_blacklist
from nexus2.utils.time_utils import now_utc

logger = logging.getLogger(__name__)

# Suppress discord.gateway heartbeat warnings — they embed full tracebacks
# containing strftime '%Y-%m-%d' patterns which crash Python's %-based log formatter
logging.getLogger("discord.gateway").setLevel(logging.ERROR)

# Reaction emoji mappings
REACTIONS = {
    "✅": ("approve", "FMP"),
    "❌": ("approve", "Alpaca"),
    "1️⃣": ("skip", "10min"),
    "2️⃣": ("skip", "30min"),
    "3️⃣": ("skip", "1hour"),
    "4️⃣": ("skip", "2hours"),
    "5️⃣": ("skip", "3hours"),
    "6️⃣": ("skip", "4hours"),
    "🚫": ("skip", "today"),
}

# All reaction emojis to add to messages
ALL_REACTIONS = list(REACTIONS.keys())


class DivergenceApprovalBot(Client):
    """
    Discord bot for handling quote divergence approvals.
    
    Sends rich embeds for divergence alerts and handles reaction responses.
    """
    
    def __init__(self, channel_id: int):
        intents = Intents.default()
        intents.message_content = True
        intents.reactions = True
        super().__init__(intents=intents)
        
        self.channel_id = channel_id
        self._channel: Optional[discord.TextChannel] = None
        self._message_to_symbol: dict[int, str] = {}  # message_id -> symbol
        
    async def on_ready(self):
        """Called when bot connects to Discord."""
        logger.info(f"[Discord Bot] Logged in as {self.user}")
        self._channel = self.get_channel(self.channel_id)
        if self._channel:
            logger.info(f"[Discord Bot] Connected to channel: {self._channel.name}")
        else:
            logger.warning(f"[Discord Bot] Channel {self.channel_id} not found!")
    
    async def send_divergence_alert(self, approval: PendingApproval) -> Optional[int]:
        """
        Send divergence alert to Discord channel.
        
        Returns message ID for reaction tracking.
        """
        if not self._channel:
            logger.warning("[Discord Bot] Channel not ready, cannot send alert")
            return None
        
        embed = discord.Embed(
            title="⚠️ Quote Divergence - Action Required",
            color=discord.Color.yellow(),
        )
        
        embed.add_field(
            name="Symbol",
            value=f"**{approval.symbol}** ({approval.time_window})",
            inline=False,
        )
        
        embed.add_field(
            name="Alpaca",
            value=f"${approval.alpaca_price:.2f}",
            inline=True,
        )
        
        embed.add_field(
            name="FMP",
            value=f"${approval.fmp_price:.2f}",
            inline=True,
        )
        
        embed.add_field(
            name="Divergence",
            value=f"**{approval.divergence_pct:.1f}%**",
            inline=True,
        )
        
        embed.add_field(
            name="Choose Source",
            value="✅ FMP  |  ❌ Alpaca",
            inline=False,
        )
        
        embed.add_field(
            name="Or Skip For",
            value="1️⃣ 10min | 2️⃣ 30min | 3️⃣ 1hr | 4️⃣ 2hr | 5️⃣ 3hr | 6️⃣ 4hr | 🚫 Today",
            inline=False,
        )
        
        embed.set_footer(text="Auto-selecting FMP in 30 seconds...")
        embed.timestamp = now_utc()
        
        try:
            message = await self._channel.send(embed=embed)
            
            # Add reactions
            for emoji in ALL_REACTIONS:
                await message.add_reaction(emoji)
            
            # Track message -> symbol mapping
            self._message_to_symbol[message.id] = approval.symbol
            
            # Store message ID in approval
            get_pending_queue().set_message_id(approval.symbol, message.id)
            
            logger.info(f"[Discord Bot] Sent divergence alert for {approval.symbol}")
            return message.id
            
        except Exception as e:
            logger.error(f"[Discord Bot] Failed to send alert: {e}")
            return None
    
    async def on_raw_reaction_add(self, payload: RawReactionActionEvent):
        """Handle reaction added to a message."""
        # Ignore bot's own reactions
        if payload.user_id == self.user.id:
            return
        
        # Check if this is a tracked message
        symbol = self._message_to_symbol.get(payload.message_id)
        if not symbol:
            return
        
        emoji = str(payload.emoji)
        action = REACTIONS.get(emoji)
        if not action:
            return
        
        action_type, value = action
        queue = get_pending_queue()
        blacklist = get_symbol_blacklist()
        
        approval = queue.get(symbol)
        if not approval or approval.status != ApprovalStatus.PENDING:
            return
        
        if action_type == "approve":
            # Approve with selected source
            queue.resolve(
                symbol,
                ApprovalStatus.APPROVED_FMP if value == "FMP" else ApprovalStatus.APPROVED_ALPACA,
                selected_source=value,
            )
            logger.info(f"[Discord Bot] {symbol}: Approved {value} via reaction")
            
            # Update message to show resolution
            await self._update_message_resolved(payload.message_id, f"✅ Using {value}")
            
        elif action_type == "skip":
            # Add to blacklist with duration
            blacklist.add(
                symbol=symbol,
                duration_key=value,
                reason="divergence",
                alpaca_price=approval.alpaca_price,
                fmp_price=approval.fmp_price,
                divergence_pct=approval.divergence_pct,
            )
            queue.resolve(symbol, ApprovalStatus.SKIPPED)
            logger.info(f"[Discord Bot] {symbol}: Skipped for {value} via reaction")
            
            # Update message to show resolution
            await self._update_message_resolved(payload.message_id, f"⏭️ Skipped for {value}")
        
        # Clean up tracking
        self._message_to_symbol.pop(payload.message_id, None)
    
    async def _update_message_resolved(self, message_id: int, resolution: str):
        """Update message to show it was resolved."""
        if not self._channel:
            return
        
        try:
            message = await self._channel.fetch_message(message_id)
            if message.embeds:
                embed = message.embeds[0]
                embed.color = discord.Color.green()
                embed.set_footer(text=resolution)
                await message.edit(embed=embed)
                # Clear reactions
                await message.clear_reactions()
        except Exception as e:
            logger.debug(f"[Discord Bot] Failed to update message: {e}")


# Singleton
_bot: Optional[DivergenceApprovalBot] = None
_bot_task: Optional[asyncio.Task] = None


def get_divergence_bot() -> Optional[DivergenceApprovalBot]:
    """Get singleton divergence bot instance."""
    return _bot


async def start_divergence_bot() -> bool:
    """
    Start the Discord bot in background.
    
    Requires DISCORD_BOT_TOKEN and DISCORD_CHANNEL_ID in config.
    """
    global _bot, _bot_task
    
    token = getattr(app_config, 'DISCORD_BOT_TOKEN', None)
    channel_id = getattr(app_config, 'DISCORD_CHANNEL_ID', None)
    
    if not token:
        logger.warning("[Discord Bot] DISCORD_BOT_TOKEN not configured - bot disabled")
        return False
    
    if not channel_id:
        logger.warning("[Discord Bot] DISCORD_CHANNEL_ID not configured - bot disabled")
        return False
    
    try:
        channel_id = int(channel_id)
    except ValueError:
        logger.error("[Discord Bot] DISCORD_CHANNEL_ID must be an integer")
        return False
    
    _bot = DivergenceApprovalBot(channel_id)
    
    async def run_bot():
        try:
            await _bot.start(token)
        except Exception as e:
            logger.error(f"[Discord Bot] Failed to start: {e}")
    
    _bot_task = asyncio.create_task(run_bot())
    logger.info("[Discord Bot] Starting in background...")
    return True


async def stop_divergence_bot():
    """Stop the Discord bot."""
    global _bot, _bot_task
    
    if _bot:
        await _bot.close()
        _bot = None
    
    if _bot_task:
        _bot_task.cancel()
        try:
            await _bot_task
        except asyncio.CancelledError:
            pass
        _bot_task = None
    
    logger.info("[Discord Bot] Stopped")


async def send_divergence_alert(approval: PendingApproval) -> Optional[int]:
    """
    Send divergence alert via bot.
    
    Returns message ID for tracking, or None if bot not available.
    """
    if not _bot:
        logger.warning("[Discord Bot] Bot not running, cannot send alert")
        return None
    
    return await _bot.send_divergence_alert(approval)
