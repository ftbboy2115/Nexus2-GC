"""
Execution Handler Module

Extracted from automation.py for better maintainability.
Contains the execute_callback factory function which creates the
async callback used by the scheduler to execute trades.
"""

import logging
from datetime import datetime
from decimal import Decimal
from typing import Callable, Optional
from uuid import uuid4

from nexus2.adapters.notifications import DiscordNotifier
from nexus2.domain.automation.automation_logger import (
    log_scan_start, log_scan_result, log_execution_decision,
    log_position_sizing, log_cycle_summary,
)

logger = logging.getLogger(__name__)


def create_execute_callback(
    engine,
    scheduler,
    broker,
    get_sim_broker: Callable,
    set_sim_broker: Callable,
    req,
):
    """
    Factory function that creates an execute_callback closure.
    
    Args:
        engine: AutomationEngine instance
        scheduler: Scheduler instance
        broker: Broker instance (Alpaca or None)
        get_sim_broker: Function to get MockBroker singleton
        set_sim_broker: Function to set MockBroker singleton
        req: SchedulerStartRequest with initial settings
    
    Returns:
        Async execute_callback function
    """
    
    async def execute_callback():
        """
        Execute top signal using broker bracket orders.
        
        Safety checks:
        - Position limit (max_positions)
        - Daily loss limit
        - SIM mode enforcement
        """
        from nexus2.db import SessionLocal, PositionRepository, SchedulerSettingsRepository
        from nexus2.domain.automation.services import create_unified_scanner_callback
        
        print(f"🤖 [{datetime.now().strftime('%H:%M:%S')}] [AutoExec] Starting execute_callback...")
        
        # =============================
        # DYNAMIC SETTINGS RELOAD
        # Read fresh settings each cycle so changes take effect immediately
        # =============================
        db_settings = SessionLocal()
        try:
            settings_repo = SchedulerSettingsRepository(db_settings)
            sched_settings = settings_repo.get()
            
            min_quality = sched_settings.min_quality
            stop_mode = sched_settings.stop_mode or "atr"
            max_stop_atr = float(sched_settings.max_stop_atr) if sched_settings.max_stop_atr else 1.0
            max_stop_percent = float(sched_settings.max_stop_percent) if sched_settings.max_stop_percent else 5.0
            scan_modes = sched_settings.scan_modes.split(",") if sched_settings.scan_modes else ["ep", "breakout", "htf"]
            htf_frequency = sched_settings.htf_frequency or "every_cycle"
            
            # Check sim_mode setting
            sim_mode_setting = getattr(sched_settings, 'sim_mode', False)
            sim_mode = sim_mode_setting == "true" if isinstance(sim_mode_setting, str) else bool(sim_mode_setting)
            
            # Get min_price from settings (default $5 if not set)
            min_price_setting = getattr(sched_settings, 'min_price', None)
            min_price = float(min_price_setting) if min_price_setting else 5.0
            
            # Get discord_alerts_enabled (default True if not set)
            discord_alerts_setting = getattr(sched_settings, 'discord_alerts_enabled', 'true')
            discord_alerts_enabled = discord_alerts_setting == "true" if isinstance(discord_alerts_setting, str) else bool(discord_alerts_setting)
            
            # Reconfigure engine scanner with fresh settings + sim_mode
            preset = sched_settings.preset or "strict"
            engine._scanner_func = await create_unified_scanner_callback(
                min_quality=min_quality,
                max_stop_percent=max_stop_percent,
                stop_mode=stop_mode,
                max_stop_atr=max_stop_atr,
                scan_modes=scan_modes,
                htf_frequency=htf_frequency,
                sim_mode=sim_mode,
                preset=preset,
                min_price=min_price,
            )
            print(f"🔄 [AutoExec] Reloaded settings: min_quality={min_quality}, stop_mode={stop_mode}, sim_mode={sim_mode}, min_price=${min_price}")
            
            # Log scan start to persistent file
            log_scan_start(scan_modes, {
                "min_quality": min_quality, "stop_mode": stop_mode,
                "max_stop_atr": max_stop_atr, "min_price": min_price,
            })
        finally:
            db_settings.close()
        
        # Run scan to get signals (with timing)
        import time
        scan_start = time.time()
        signals = await engine.run_scan_cycle()
        scan_duration = time.time() - scan_start
        print(f"🤖 [{datetime.now().strftime('%H:%M:%S')}] [AutoExec] Scan returned {len(signals) if signals else 0} signals (took {scan_duration:.1f}s)")
        
        # Store signals in scheduler for UI display (even in auto_execute mode)
        scheduler.last_signals = signals if signals else []
        scheduler.last_signals_at = datetime.now()
        
        # Log summary of all signals received for diagnostics
        if signals:
            print(f"📋 [{datetime.now().strftime('%H:%M:%S')}] [AutoExec] Signal Summary:")
            for i, sig in enumerate(signals[:10], 1):
                setup_name = sig.setup_type.value if hasattr(sig.setup_type, 'value') else str(sig.setup_type)
                print(f"   {i}. {sig.symbol:6} | Score: {sig.quality_score} | Type: {setup_name:8} | Mode: {sig.scanner_mode} | Tier: {sig.tier}")
            
            # Log scan results to persistent file
            log_scan_result(
                total_signals=len(signals),
                ep_count=sum(1 for s in signals if hasattr(s, 'setup_type') and getattr(s.setup_type, 'value', '') == 'ep'),
                breakout_count=sum(1 for s in signals if hasattr(s, 'setup_type') and getattr(s.setup_type, 'value', '') in ('breakout', 'flag')),
                htf_count=sum(1 for s in signals if hasattr(s, 'setup_type') and getattr(s.setup_type, 'value', '') == 'htf'),
                duration_ms=int(scan_duration * 1000),
                signals=signals,
            )
        
        if not signals:
            logger.info("[AutoExec] No signals from scan")
            print("🤖 [AutoExec] No signals found - returning")
            return {"status": "no_signals"}
        
        # =============================
        # PROCESS ALL QUALIFIED SIGNALS
        # Execute up to max_trades_per_cycle from settings
        # =============================
        from nexus2.api.routes.settings import get_settings
        from nexus2.db import SessionLocal, SchedulerSettingsRepository
        
        settings = get_settings()
        MAX_TRADES_PER_CYCLE = settings.max_trades_per_cycle  # From settings (default: 10)
        
        # Get sim_broker reference
        _sim_broker = get_sim_broker()
        
        # Check scheduler-specific max_position_value first, fall back to global
        scheduler_max = None
        try:
            db = SessionLocal()
            scheduler_settings = SchedulerSettingsRepository(db).get()
            if scheduler_settings.max_position_value:
                scheduler_max = Decimal(scheduler_settings.max_position_value)
                print(f"📐 [AutoExec] Using scheduler max_position_value: ${scheduler_max}")
            db.close()
        except Exception as e:
            logger.warning(f"[AutoExec] Could not read scheduler settings: {e}")
        
        max_per_symbol = scheduler_max if scheduler_max else Decimal(str(settings.max_per_symbol))
        
        # Get existing positions to avoid adding to existing positions
        existing_symbols = set()
        
        # In sim_mode, check MockBroker positions
        if sim_mode and _sim_broker is not None:
            try:
                sim_positions = _sim_broker.get_positions()
                for pos in sim_positions:
                    existing_symbols.add(pos['symbol'].upper())
                if existing_symbols:
                    print(f"📍 [SIM] Already holding in MockBroker: {', '.join(sorted(existing_symbols))}")
            except Exception as e:
                logger.warning(f"[AutoExec] Could not fetch sim positions: {e}")
        elif broker:
            # In live mode, check Alpaca positions
            try:
                positions = broker.get_positions()
                existing_symbols = {symbol.upper() for symbol in positions.keys()}
                if existing_symbols:
                    print(f"📍 [AutoExec] Already holding: {', '.join(sorted(existing_symbols))}")
            except Exception as e:
                logger.warning(f"[AutoExec] Could not fetch positions: {e}")
        
        executed = []
        skipped = []
        errors = []
        
        for signal in signals[:MAX_TRADES_PER_CYCLE]:
            # Skip if we already hold this symbol (no adds on existing - KK-style)
            if signal.symbol.upper() in existing_symbols:
                print(f"⏭️ [AutoExec] Skipping {signal.symbol} - already holding position")
                skipped.append({"symbol": signal.symbol, "reason": "Already holding position"})
                continue
            
            # Safety check: Can we open a new position?
            if not engine.can_open_position():
                logger.warning(f"[AutoExec] Position limit reached, stopping at {len(executed)} trades")
                break
            
            # Calculate position size based on risk
            shares = signal.calculate_shares(engine.config.risk_per_trade)
            
            # Cap position size to max_per_symbol setting
            if signal.entry_price > 0:
                max_shares_from_cap = int(float(max_per_symbol) / float(signal.entry_price))
                print(f"📊 [DEBUG] {signal.symbol}: entry_price={signal.entry_price}, max_per_symbol={max_per_symbol}, max_shares={max_shares_from_cap}")
                if shares > max_shares_from_cap:
                    print(f"🔒 [AutoExec] Capping {signal.symbol} shares from {shares} to {max_shares_from_cap} (max ${max_per_symbol})")
                    log_position_sizing(
                        signal.symbol, float(signal.entry_price), shares, max_shares_from_cap,
                        float(max_per_symbol), reason="exceeds max_per_symbol cap"
                    )
                    shares = max_shares_from_cap
            
            if shares < 1:
                logger.warning(f"[AutoExec] Position too small for {signal.symbol}: {shares} shares")
                skipped.append({"symbol": signal.symbol, "reason": "Position size < 1 share"})
                log_execution_decision(signal.symbol, 0, 0, "SKIPPED", reason="Position size < 1 share")
                continue
            
            # Check if broker is available
            if broker is None and not sim_mode:
                logger.error("[AutoExec] No broker configured!")
                return {"status": "failed", "error": "No broker configured", "executed": executed}
            
            # In sim_mode, use MockBroker instead of live broker
            if sim_mode:
                from nexus2.adapters.simulation import get_mock_market_data
                from nexus2.adapters.simulation.mock_broker import MockBroker
                
                # Get or create global MockBroker
                _sim_broker = get_sim_broker()
                if _sim_broker is None:
                    _sim_broker = MockBroker(initial_cash=100_000.0)
                    set_sim_broker(_sim_broker)
                    logger.info("[SIM] Created new MockBroker with $100k initial cash")
                
                # Set current price from MockMarketData for each symbol
                mock_data = get_mock_market_data()
                current_price = mock_data.get_last_price(signal.symbol)
                if current_price:
                    _sim_broker.set_price(signal.symbol, float(current_price))
                else:
                    print(f"⚠️ [SIM] No price available for {signal.symbol} - skipping")
                    skipped.append({"symbol": signal.symbol, "reason": "No sim price available"})
                    continue
                
                active_broker = _sim_broker
                print(f"🧪 [SIM] Using MockBroker for {signal.symbol}")
            else:
                active_broker = broker
            
            # Submit bracket order through broker
            try:
                client_order_id = uuid4()
                
                # KK methodology: stop = LOD (Low of Day so far)
                # Get today's low from FMP quote
                from nexus2.adapters.market_data.fmp_adapter import FMPAdapter
                fmp = FMPAdapter()
                quote = fmp.get_quote(signal.symbol)
                
                if quote and quote.day_low and quote.day_low > 0:
                    stop_price = quote.day_low
                    print(f"📍 [AutoExec] Using LOD stop: ${stop_price} (today's low)")
                else:
                    # Fallback to signal's tactical stop
                    stop_price = Decimal(str(signal.tactical_stop))
                    print(f"⚠️ [AutoExec] LOD unavailable, using tactical_stop: ${stop_price}")
                
                # Log signal details for diagnostics
                setup_name = signal.setup_type.value if hasattr(signal.setup_type, 'value') else str(signal.setup_type)
                print(f"📊 [AutoExec] Signal: {signal.symbol} | Score: {signal.quality_score} | Type: {setup_name} | Mode: {signal.scanner_mode} | Tier: {signal.tier}")
                print(f"🤖 [AutoExec] Submitting bracket order: {signal.symbol} x {shares} @ stop ${stop_price}")
                
                result = active_broker.submit_bracket_order(
                    client_order_id=client_order_id,
                    symbol=signal.symbol,
                    quantity=shares,
                    stop_loss_price=stop_price,
                )
            except Exception as e:
                logger.error(f"[AutoExec] Bracket order failed for {signal.symbol}: {e}")
                errors.append({"symbol": signal.symbol, "error": str(e)})
                continue
            
            # Check if order was accepted
            if result and result.status.value in ("accepted", "filled", "pending"):
                # Create position record
                db = SessionLocal()
                try:
                    position_repo = PositionRepository(db)
                    position = position_repo.create({
                        "id": str(uuid4()),
                        "symbol": signal.symbol,
                        "setup_type": signal.setup_type.value,
                        "status": "open",
                        "entry_price": str(result.avg_fill_price or result.limit_price or signal.entry_price),
                        "shares": shares,
                        "remaining_shares": shares,
                        "initial_stop": str(stop_price),
                        "current_stop": str(stop_price),
                        "realized_pnl": "0",
                        "opened_at": datetime.utcnow(),
                        "source": "nac",
                        "quality_score": signal.quality_score,
                        "tier": signal.tier,
                        "rs_percentile": signal.rs_percentile,
                        "adr_percent": str(signal.adr_percent) if signal.adr_percent else None,
                    })
                    
                    # Update engine stats
                    engine.stats.orders_submitted += 1
                    engine.stats.orders_filled += 1
                    
                    logger.info(f"[AutoExec] SUCCESS: {signal.symbol} x {shares} @ stop ${stop_price}")
                    print(f"✅ [AutoExec] Executed: {signal.symbol} x {shares}")
                    
                    # Log to persistent file
                    log_execution_decision(
                        signal.symbol, shares, float(stop_price), "EXECUTED",
                        order_id=str(result.broker_order_id)
                    )
                    
                    # Send Discord notification (if enabled)
                    if discord_alerts_enabled:
                        try:
                            discord = DiscordNotifier()
                            setup_name = signal.setup_type.value if hasattr(signal.setup_type, 'value') else str(signal.setup_type)
                            entry_price = float(signal.entry_price)
                            order_total = entry_price * shares
                            mode_label = "🧪 SIM" if sim_mode else "🔴 LIVE"
                            discord.send_trade_alert(
                                message=f"{mode_label} | ENTRY: {signal.symbol} x {shares} @ ${entry_price:.2f} = ${order_total:.2f}\n{setup_name.upper()} | Stop ${stop_price:.2f} | Score: {signal.quality_score}",
                                trade_id=str(result.broker_order_id)
                            )
                        except Exception as e:
                            logger.warning(f"Discord notification failed: {e}")
                    
                    executed.append({
                        "symbol": signal.symbol,
                        "shares": shares,
                        "stop_price": float(stop_price),
                        "order_id": str(result.broker_order_id),
                        "position_id": position.id,
                    })
                finally:
                    db.close()
            else:
                logger.error(f"[AutoExec] Order not accepted for {signal.symbol}: {result}")
                errors.append({"symbol": signal.symbol, "error": "Order not accepted by broker"})
                log_execution_decision(signal.symbol, shares, float(stop_price), "ERROR", reason="Order not accepted by broker")
        
        # Log cycle summary to persistent file
        log_cycle_summary(
            executed_count=len(executed),
            skipped_count=len(skipped),
            error_count=len(errors),
            executed_symbols=[e["symbol"] for e in executed],
            skipped_symbols=[s["symbol"] for s in skipped],
        )
        
        print(f"🤖 [{datetime.now().strftime('%H:%M:%S')}] [AutoExec] Cycle complete: {len(executed)} executed, {len(skipped)} skipped, {len(errors)} errors")
        
        return {
            "status": "executed" if executed else "no_trades",
            "executed": executed,
            "skipped": skipped if skipped else None,
            "errors": errors if errors else None,
        }
    
    return execute_callback
