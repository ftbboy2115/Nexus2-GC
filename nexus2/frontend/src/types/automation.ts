// Automation page types - extracted from automation.tsx for modularity

// Engine status from /automation/status
export interface EngineStatus {
    state: string
    sim_only: boolean
    is_market_hours: boolean
    trading_mode: string
    mode_description: string
    broker_available: boolean
    broker_type: string
    broker_display: string
    active_account: string
    settings_risk_per_trade: number
    config: {
        scanner_interval: number
        min_quality: number
        max_positions: number
        risk_per_trade: string
        daily_loss_limit: string
    }
    stats: {
        started_at: string | null
        scans_run: number
        signals_generated: number
        orders_submitted: number
        orders_filled: number
        daily_pnl: string
        last_scan_at: string | null
        last_error: string | null
    }
}

// Scheduler status from /automation/scheduler/status
export interface SchedulerStatus {
    running: boolean
    interval_minutes: number
    auto_execute: boolean
    is_market_hours: boolean
    cycles_run: number
    last_run: string | null
    next_run: string | null
    last_error: string | null
}

// Monitor status from /automation/monitor/status
export interface MonitorStatus {
    running: boolean
    check_interval_seconds: number
    checks_run: number
    exits_triggered: number
    last_check: string | null
    last_error: string | null
}

// API rate limit stats from /automation/api-stats
export interface ApiStats {
    status: string
    provider: string
    calls_this_minute: number
    limit_per_minute: number
    remaining: number
    usage_percent: number
}

// Signal from scanner
export interface Signal {
    symbol: string
    setup_type: string
    quality_score: number
    tier: string
    entry_price: string
    tactical_stop: string
    stop_percent: number
    rs_percentile: number
    shares: number
    risk_amount: string
    found_at?: string  // Timestamp when signal was found
}

// Scan result from /automation/scheduler/signals
export interface ScanResult {
    status: string
    total_signals: number
    breakdown: { ep: number; breakout: number; htf: number }
    scanned_at: string
    signals: Signal[]
}

// Individual rejection in scanner diagnostics
export interface ScanRejection {
    symbol: string
    reason: string
    threshold: number
    actual_value: number
}

// Scanner diagnostic for one scanner type
export interface ScannerDiagnostic {
    scanner: string
    enabled: boolean
    candidates_found: number
    candidates_passed: number
    rejections: ScanRejection[]
    error: string | null
}

// Full scan diagnostics from /automation/scheduler/diagnostics
export interface ScanDiagnostics {
    available: boolean
    message?: string
    scanned_at?: string
    duration_ms?: number
    total_signals?: number
    total_processed?: number
    ep_count?: number
    breakout_count?: number
    htf_count?: number
    diagnostics?: ScannerDiagnostic[]
}

// Broker position from Alpaca
export interface BrokerPosition {
    symbol: string
    qty: number
    avg_price: number
    market_value: number
    unrealized_pnl: number
    pnl_percent: number
    // Expanded columns for maximized view
    side?: string           // 'long' or 'short'
    current_price?: number  // Current market price
    stop_price?: number     // Current stop price
    today_pnl?: number      // Today's P/L in dollars
    change_today?: number   // Today's % change
    days_held?: number      // Days position has been held
}

// Positions data from /automation/positions
export interface PositionsData {
    status: string
    positions: BrokerPosition[]
    count: number
    total_value: number
    total_pnl: number
}

// Simulation position from MockBroker
export interface SimPosition {
    symbol: string
    qty: number
    avg_price: number
    market_value: number
    unrealized_pnl: number
    pnl_percent: number
    stop_price?: number
}

// Simulation positions data from /automation/simulation/positions
export interface SimPositionsData {
    status: string
    positions: SimPosition[]
    count: number
    account?: {
        cash: number
        portfolio_value: number
        buying_power: number
        realized_pnl: number
        unrealized_pnl: number
        position_count: number
    }
}

// Quick Actions scanner settings (local UI state)
export interface ScannerSettings {
    preset: 'strict' | 'relaxed' | 'custom'
    minQuality: number
    stopMode: 'atr' | 'percent'  // KK uses ATR
    maxStopAtr: number           // Default: 1.0 ATR
    maxStopPercent: number       // Fallback option
    scanModes: string[]          // Which scanners to run: ep, breakout, htf
    htfFrequency: 'every_cycle' | 'market_open'  // How often to run HTF
}

// Scheduler settings from /automation/scheduler/settings
export interface SchedulerSettingsData {
    adopt_quick_actions: boolean
    preset: 'strict' | 'relaxed' | 'custom'
    min_quality: number
    stop_mode: 'atr' | 'percent'
    max_stop_atr: number
    max_stop_percent: number
    scan_modes: string[]  // ["ep", "breakout", "htf"]
    htf_frequency: 'every_cycle' | 'market_open'
    max_position_value: number | null  // Automation-specific capital limit (null = use global)
    nac_max_positions: number | null  // Max concurrent positions for NAC (null = unlimited)
    auto_start_enabled: boolean  // Enable auto-start for headless operation
    auto_start_time: string | null  // HH:MM format (ET timezone)
    auto_execute: boolean  // Auto-execute trades when scheduler runs
    nac_broker_type: string  // alpaca_paper, alpaca_live
    nac_account: string  // A or B (default A for Automation)
    sim_mode: boolean  // Enable simulation mode (uses MockBroker)
    min_price: number  // Minimum stock price filter ($2-10)
    min_rvol: number  // Minimum relative volume (default 1.5x)
    discord_alerts_enabled: boolean  // Enable Discord notifications
}

// Preset defaults for Quick Actions
export const PRESET_MODES: Record<string, ScannerSettings> = {
    strict: { preset: 'strict', minQuality: 7, stopMode: 'atr', maxStopAtr: 1.0, maxStopPercent: 5, scanModes: ['ep', 'breakout'], htfFrequency: 'market_open' },
    relaxed: { preset: 'relaxed', minQuality: 5, stopMode: 'atr', maxStopAtr: 1.5, maxStopPercent: 8, scanModes: ['ep', 'breakout', 'htf'], htfFrequency: 'market_open' },
    custom: { preset: 'custom', minQuality: 6, stopMode: 'atr', maxStopAtr: 1.0, maxStopPercent: 6, scanModes: ['ep', 'breakout'], htfFrequency: 'market_open' },
}

// Preset defaults for Scheduler settings
export const SCHEDULER_PRESET_DEFAULTS: Record<string, Partial<SchedulerSettingsData>> = {
    strict: { min_quality: 7, stop_mode: 'atr', max_stop_atr: 1.0, max_stop_percent: 5 },
    relaxed: { min_quality: 5, stop_mode: 'percent', max_stop_atr: 1.5, max_stop_percent: 8 },
}
