/**
 * Warrior Trading Type Definitions
 */

export interface WarriorStatus {
    state: string
    trading_window: boolean
    market_hours: boolean
    watchlist_count: number
    watchlist: WatchedCandidate[]
    stats: {
        started_at: string | null
        scans_run: number
        candidates_found: number
        entries_triggered: number
        orders_submitted: number
        daily_pnl: number
        last_scan_at: string | null
        next_scan: string | null
        last_error: string | null
    }
    monitor: {
        running: boolean
        positions_count: number
        check_interval_seconds: number
        checks_run: number
        exits_triggered: number
        partials_triggered: number
        last_check: string | null
        last_error: string | null
        settings: {
            mental_stop_cents: number
            profit_target_r: number
            partial_exit_fraction: number
            candle_under_candle: boolean
            topping_tail: boolean
        }
    }
    config: {
        sim_only: boolean
        risk_per_trade: number
        max_positions: number
        max_candidates: number
        scanner_interval_minutes: number
        max_daily_loss: number
        orb_enabled: boolean
        pmh_enabled: boolean
        max_shares_per_trade?: number
    }
    auto_enable?: boolean
    last_scan_result?: {
        scan_time: string
        processed_count: number
        candidates: {
            symbol: string
            gap_percent: number
            rvol: number
            float_shares: number
            price: number
            in_watchlist: boolean
        }[]
    }
}

export interface WatchedCandidate {
    symbol: string
    gap_percent: number
    rvol: number
    pmh: number
    orb_high: number | null
    orb_established: boolean
    entry_triggered: boolean
    indicators?: Record<string, { status: string; tooltip: string }>
}

export interface WarriorCandidate {
    symbol: string
    name: string
    price: number
    gap_percent: number
    relative_volume: number
    float_shares: number | null
    catalyst_type: string
    catalyst_description: string
    quality_score: number
    is_ideal_float: boolean
    is_ideal_rvol: boolean
    is_ideal_gap: boolean
}

export interface ScanResult {
    candidates: WarriorCandidate[]
    processed_count: number
    filtered_count: number
    avg_rvol: number
    avg_gap: number
}

export interface WarriorPosition {
    position_id: string
    symbol: string
    entry_price: number
    shares: number
    current_stop: number
    profit_target: number
    partial_taken: boolean
    high_since_entry: number
    entry_time: string | null
    current_price?: number  // For Current/P&L display
}

export interface PositionHealthIndicator {
    name: string
    status: 'green' | 'yellow' | 'red' | 'gray'
    value: number
    tooltip: string
}

export interface PositionHealth {
    macd: PositionHealthIndicator
    ema9: PositionHealthIndicator
    ema20: PositionHealthIndicator
    ema200: PositionHealthIndicator
    vwap: PositionHealthIndicator
    volume: PositionHealthIndicator
    stop: PositionHealthIndicator
    target: PositionHealthIndicator
}

export interface SimStatus {
    sim_enabled: boolean
    message?: string
    account?: {
        cash: number
        portfolio_value: number
        unrealized_pnl: number
        realized_pnl: number
    }
    positions?: Array<{
        symbol: string
        qty: number
        avg_price: number
        market_value: number
        unrealized_pnl: number
        pnl_percent: number
        stop_price: number
    }>
    position_count?: number
}

export interface BrokerStatus {
    broker_enabled: boolean
    paper_mode?: boolean
    account_value?: number
    positions_count?: number
    realized_pnl_today?: number
    unrealized_pnl?: number
    total_daily_pnl?: number
    invested_capital?: number
    peak_exposure?: number
    total_capital_deployed?: number
    daily_pnl_percent?: number
    error?: string
}

export interface CollapsibleCardProps {
    id: string
    title: string
    badge?: React.ReactNode
    children: React.ReactNode
    defaultCollapsed?: boolean
}

export interface MonitorSettings {
    enable_scaling: boolean
    enable_after_hours_exit: boolean
    [key: string]: boolean | number | string
}

export interface TradeHistory {
    id: string
    symbol: string
    entry_price: string
    exit_price: string | null
    quantity: number
    entry_time: string
    exit_time: string | null
    exit_reason: string | null
    realized_pnl: string
    status: string
}

export interface TradeAnalysis {
    symbol: string
    summary: string
    grades?: Record<string, string>
    what_went_well?: string[]
    lessons_learned?: string[]
}

export interface TestCase {
    id: string
    symbol: string
    description: string
}

export interface LoadedTestCase {
    symbol: string
    price: number
}
