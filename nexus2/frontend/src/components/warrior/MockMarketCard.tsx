/**
 * MockMarketCard - Test case selector and price simulation controls
 * 
 * Includes historical replay with time-based playback controls.
 */
import { useState, useEffect } from 'react'
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
}: MockMarketCardProps) {
    const [isHistoricalMode, setIsHistoricalMode] = useState(false)
    const [isPlaying, setIsPlaying] = useState(false)

    // Auto-play effect - advances clock automatically when playing
    useEffect(() => {
        if (!isPlaying || !onStep || !clockState) return

        // Calculate interval based on speed: 1x=1000ms, 2x=500ms, 5x=200ms, 10x=100ms
        const intervalMs = Math.round(1000 / clockState.speed)

        const interval = setInterval(() => {
            onStep(1)  // Step 1 minute
        }, intervalMs)

        return () => clearInterval(interval)
    }, [isPlaying, clockState?.speed, onStep])

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

