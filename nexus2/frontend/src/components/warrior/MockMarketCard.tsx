/**
 * MockMarketCard - Test case selector and price simulation controls
 * 
 * Includes historical replay with time-based playback controls.
 */
import { useState, useEffect, useRef } from 'react'
import styles from '@/styles/Warrior.module.css'
import { CollapsibleCard } from './CollapsibleCard'

interface TestCase {
    id: string
    symbol: string
    description: string
}

interface ClockState {
    time_string: string
    is_market_hours: boolean
    speed: number
}

interface MockOrder {
    id: string
    symbol: string
    side: string
    qty: number
    order_type: string
    status: string
    limit_price: number | null
    stop_price: number | null
    avg_fill_price: number | null
    filled_qty: number
    created_at: string | null
    filled_at: string | null
    exit_mode?: string | null  // "base_hit" or "home_run"
    sim_time?: string | null   // Sim clock time when order was placed (e.g. "10:45")
}

interface MockMarketCardProps {
    testCases: TestCase[]
    selectedTestCase: string
    setSelectedTestCase: (id: string) => void
    loadedTestCase: { symbol: string; price: number } | null
    loadTestCase: () => void
    setMockPrice: (symbol: string, price: number) => void
    actionLoading: string | null
    // Historical replay props
    clockState?: ClockState | null
    onLoadHistorical?: () => void
    onStep?: (minutes: number) => void
    onStepBack?: (minutes: number) => void
    onResetClock?: () => void
    onSetSpeed?: (speed: number) => void
    // Orders visibility
    orders?: MockOrder[]
}

const SPEEDS = [1, 2, 5, 10]

export function MockMarketCard({
    testCases,
    selectedTestCase,
    setSelectedTestCase,
    loadedTestCase,
    loadTestCase,
    setMockPrice,
    actionLoading,
    clockState,
    onLoadHistorical,
    onStep,
    onStepBack,
    onResetClock,
    onSetSpeed,
    orders = [],
}: MockMarketCardProps) {
    const [isHistoricalMode, setIsHistoricalMode] = useState(false)
    const [isPlaying, setIsPlaying] = useState(false)

    // Helper to get status indicator
    const getStatusIcon = (status: string) => {
        switch (status.toLowerCase()) {
            case 'pending': return '🟡'
            case 'filled': return '🟢'
            case 'cancelled': return '🔴'
            case 'rejected': return '⚠️'
            default: return '⚪'
        }
    }

    // Track speed in a ref to avoid effect re-running on every clockState change
    const speedRef = useRef(clockState?.speed ?? 1)

    // Update ref when speed actually changes
    useEffect(() => {
        if (clockState?.speed !== undefined) {
            speedRef.current = clockState.speed
        }
    }, [clockState?.speed])

    // Auto-play effect - advances clock automatically when playing
    // Uses setTimeout chain instead of setInterval to prevent race conditions
    // (waits for each API call to complete before scheduling the next)
    useEffect(() => {
        if (!isPlaying || !onStep || !clockState) return

        let cancelled = false
        let timeoutId: NodeJS.Timeout

        const step = async () => {
            if (cancelled) return
            await onStep(1)  // Wait for step to complete
            if (!cancelled) {
                const delayMs = Math.round(1000 / speedRef.current)
                timeoutId = setTimeout(step, delayMs)
            }
        }

        // Start the chain
        step()

        return () => {
            cancelled = true
            if (timeoutId) clearTimeout(timeoutId)
        }
    }, [isPlaying, onStep])  // Removed clockState?.speed - using ref instead

    // Stop playing when clock state is lost
    useEffect(() => {
        if (!clockState) setIsPlaying(false)
    }, [clockState])

    return (
        <CollapsibleCard
            id="mockmarket"
            title="🎮 Mock Market"
            badge={loadedTestCase ? <span className={styles.badge}>{loadedTestCase.symbol}</span> : undefined}
        >
            <div className={styles.cardBody}>
                {/* Test Case Selector */}
                <div className={styles.testCaseSelector}>
                    <select
                        value={selectedTestCase}
                        onChange={(e) => setSelectedTestCase(e.target.value)}
                        className={styles.selectInput}
                        title={testCases.find(tc => tc.id === selectedTestCase)?.description || ''}
                    >
                        <option value="">Select a test case...</option>
                        {testCases.map((tc) => (
                            <option key={tc.id} value={tc.id}>
                                {tc.symbol} - {tc.description.length > 40 ? tc.description.slice(0, 40) + '...' : tc.description}
                            </option>
                        ))}
                    </select>
                    <button
                        onClick={loadTestCase}
                        className={styles.btnPrimary}
                        disabled={!selectedTestCase || actionLoading === 'loadTest'}
                        style={{ flexShrink: 0 }}
                    >
                        {actionLoading === 'loadTest' ? '...' : '📦 Load'}
                    </button>
                    {onLoadHistorical && (
                        <button
                            onClick={() => { onLoadHistorical(); setIsHistoricalMode(true) }}
                            className={styles.btnSecondary}
                            disabled={!selectedTestCase || actionLoading === 'loadHistorical'}
                            style={{ flexShrink: 0 }}
                            title="Load with historical bar data for time-based replay"
                        >
                            {actionLoading === 'loadHistorical' ? '...' : '📊 Replay'}
                        </button>
                    )}
                </div>

                {/* Playback Controls - Only show when historical bars loaded */}
                {clockState && isHistoricalMode && (
                    <div className={styles.playbackControls}>
                        {/* Time Display */}
                        <div className={styles.clockDisplay}>
                            <span className={styles.clockTime}>{clockState.time_string}</span>
                            <span className={styles.clockSpeed}>{clockState.speed}x</span>
                            {isPlaying && <span className={styles.playingIndicator}>▶</span>}
                        </div>

                        {/* Playback Buttons */}
                        <div className={styles.playbackButtons}>
                            <button
                                onClick={() => { onResetClock?.(); setIsPlaying(false) }}
                                className={styles.btnPlayback}
                                title="Reset to 9:30 AM"
                            >
                                ⏮️
                            </button>
                            <button
                                onClick={() => { onStepBack?.(5); setIsPlaying(false) }}
                                className={styles.btnPlayback}
                                title="Step back 5 min"
                            >
                                ⏪
                            </button>
                            <button
                                onClick={() => { onStepBack?.(1); setIsPlaying(false) }}
                                className={styles.btnPlayback}
                                title="Step back 1 min"
                            >
                                ◀️
                            </button>
                            {/* Play/Pause Toggle */}
                            <button
                                onClick={() => setIsPlaying(!isPlaying)}
                                className={`${styles.btnPlayback} ${isPlaying ? styles.btnPlaybackActive : ''}`}
                                title={isPlaying ? "Pause" : "Play (auto-advance)"}
                            >
                                {isPlaying ? '⏸️' : '▶️'}
                            </button>
                            <button
                                onClick={() => { onStep?.(5); setIsPlaying(false) }}
                                className={styles.btnPlayback}
                                title="Step forward 5 min"
                            >
                                ⏩
                            </button>
                            <button
                                onClick={() => { onStep?.(30); setIsPlaying(false) }}
                                className={styles.btnPlayback}
                                title="Jump 30 min"
                            >
                                ⏭️
                            </button>
                        </div>

                        {/* Speed Selector */}
                        <div className={styles.speedSelector}>
                            {SPEEDS.map(speed => (
                                <button
                                    key={speed}
                                    onClick={() => onSetSpeed?.(speed)}
                                    className={`${styles.btnSpeed} ${clockState.speed === speed ? styles.btnSpeedActive : ''}`}
                                >
                                    {speed}x
                                </button>
                            ))}
                        </div>
                    </div>
                )}

                {/* Orders Panel - Show when in historical mode and orders exist */}
                {isHistoricalMode && orders.length > 0 && (
                    <div className={styles.ordersPanel}>
                        <div className={styles.ordersPanelHeader}>📋 Orders</div>
                        <div className={styles.ordersList}>
                            {orders.map(order => (
                                <div key={order.id} className={styles.orderRow}>
                                    <span className={styles.orderStatus}>
                                        {getStatusIcon(order.status)}
                                    </span>
                                    {/* Sim timestamp */}
                                    {order.sim_time && (
                                        <span className={styles.orderTime} title="Sim clock time">
                                            {order.sim_time}
                                        </span>
                                    )}
                                    <span className={`${styles.orderSide} ${order.side === 'buy' ? styles.orderSideBuy : styles.orderSideSell}`}>
                                        {order.side.toUpperCase()}
                                    </span>
                                    <span className={styles.orderQty}>
                                        {order.qty}x
                                    </span>
                                    <span className={styles.orderSymbol}>
                                        {order.symbol}
                                    </span>
                                    <span className={styles.orderPrice}>
                                        @ ${order.order_type === 'limit'
                                            ? order.limit_price?.toFixed(2)
                                            : order.order_type === 'stop'
                                                ? order.stop_price?.toFixed(2)
                                                : order.avg_fill_price?.toFixed(2) || '???'
                                        }
                                    </span>
                                    <span className={styles.orderType}>
                                        {order.order_type}
                                    </span>
                                    {/* Exit mode badge */}
                                    {order.exit_mode && order.side === 'buy' && (
                                        <span
                                            className={`${styles.exitModeBadge} ${order.exit_mode === 'home_run' ? styles.homeRun : styles.baseHit}`}
                                            title={order.exit_mode === 'home_run' ? 'Home Run: trailing stops, partials' : 'Base Hit: fixed target exit'}
                                        >
                                            {order.exit_mode === 'home_run' ? '🚀' : '⚾'}
                                        </span>
                                    )}
                                    <span className={`${styles.orderStatusBadge} ${styles['status' + order.status.charAt(0).toUpperCase() + order.status.slice(1)]}`}>
                                        {order.status.toUpperCase()}
                                    </span>
                                </div>
                            ))}
                        </div>
                    </div>
                )}

                {/* Price Controls */}
                {loadedTestCase && loadedTestCase.price != null && (
                    <div className={styles.priceControls}>
                        <div className={styles.priceDisplay}>
                            <span className={styles.priceLabel}>Price:</span>
                            <span className={styles.priceValue}>${loadedTestCase.price.toFixed(2)}</span>
                        </div>
                        <div className={styles.priceButtons}>
                            <button onClick={() => setMockPrice(loadedTestCase.symbol, loadedTestCase.price - 0.10)} className={styles.btnSmall}>-10¢</button>
                            <button onClick={() => setMockPrice(loadedTestCase.symbol, loadedTestCase.price - 0.05)} className={styles.btnSmall}>-5¢</button>
                            <button onClick={() => setMockPrice(loadedTestCase.symbol, loadedTestCase.price + 0.05)} className={styles.btnSmall}>+5¢</button>
                            <button onClick={() => setMockPrice(loadedTestCase.symbol, loadedTestCase.price + 0.10)} className={styles.btnSmall}>+10¢</button>
                            <button onClick={() => setMockPrice(loadedTestCase.symbol, loadedTestCase.price + 0.25)} className={styles.btnPrimary}>+25¢ 🚀</button>
                        </div>
                    </div>
                )}

                {!loadedTestCase && !selectedTestCase && (
                    <p className={styles.emptyMessage}>
                        Select a test case to simulate price movements
                    </p>
                )}
            </div>
        </CollapsibleCard>
    )
}

