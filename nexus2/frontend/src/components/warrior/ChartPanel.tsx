/**
 * ChartPanel - TradingView-style candlestick chart for Mock Market replay
 * 
 * Uses lightweight-charts (TradingView's open-source library) to display
 * historical price data bar-by-bar as the simulation clock advances.
 */
import { useEffect, useRef, useMemo, useState } from 'react'
import { createChart, IChartApi, ISeriesApi, CandlestickData, HistogramData, Time } from 'lightweight-charts'
import styles from '@/styles/Warrior.module.css'

export interface BarData {
    time: string      // e.g., "09:35"
    open: number
    high: number
    low: number
    close: number
    volume?: number
}

export interface OrderMarker {
    time: string
    price: number
    side: 'buy' | 'sell'
    qty: number
}

export interface SimPosition {
    symbol: string
    qty: number
    avg: number
    pnl: number
}

export interface ClockState {
    time_string: string
    is_market_hours: boolean
    speed: number
}

type ChartSizeMode = 'small' | 'theater' | 'fullscreen'

interface ChartPanelProps {
    bars: BarData[]              // All visible bars up to current time
    currentBarIndex: number      // Index of the current bar
    symbol: string
    orders?: OrderMarker[]       // Entry/exit markers to display
    // Fullscreen overlay props
    clockState?: ClockState | null
    isPlaying?: boolean
    onStep?: (minutes: number) => void
    onStepBack?: (minutes: number) => void
    onResetClock?: () => void
    onSetSpeed?: (speed: number) => void
    onTogglePlay?: () => void
    simPositions?: SimPosition[]
    currentPrice?: number
    realizedPnl?: number
}

const SIZE_HEIGHTS: Record<ChartSizeMode, number> = {
    small: 250,
    theater: 450,
    fullscreen: 0, // Calculated dynamically
}

const SPEEDS = [1, 2, 5, 10, 20, 30, 40, 50, 60]

export function ChartPanel({
    bars,
    currentBarIndex,
    symbol,
    orders = [],
    // Fullscreen overlay props
    clockState,
    isPlaying = false,
    onStep,
    onStepBack,
    onResetClock,
    onSetSpeed,
    onTogglePlay,
    simPositions = [],
    currentPrice = 0,
    realizedPnl = 0,
}: ChartPanelProps) {
    const containerRef = useRef<HTMLDivElement>(null)
    const chartRef = useRef<IChartApi | null>(null)
    const candleSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null)
    const volumeSeriesRef = useRef<ISeriesApi<'Histogram'> | null>(null)

    // Chart size mode: small (default), theater, fullscreen
    const [sizeMode, setSizeMode] = useState<ChartSizeMode>('small')

    // Calculate actual height based on mode
    const height = sizeMode === 'fullscreen'
        ? (typeof window !== 'undefined' ? window.innerHeight - 180 : 600)
        : SIZE_HEIGHTS[sizeMode]

    // Convert HH:MM time string (in Eastern Time) to Unix timestamp
    // The bar.time values from simulation are in ET format
    // Use UTC methods to avoid local timezone interpretation issues
    const convertToTimestamp = (timeStr: string): Time => {
        const [hours, minutes] = timeStr.split(':').map(Number)
        const today = new Date()
        // Create UTC timestamp using the ET hours directly
        // This ensures lightweight-charts displays the intended ET time
        const utcDate = Date.UTC(
            today.getFullYear(),
            today.getMonth(),
            today.getDate(),
            hours,
            minutes,
            0
        )
        return Math.floor(utcDate / 1000) as Time
    }

    // Memoize converted data to avoid recalculation
    const chartData = useMemo(() => {
        return bars.slice(0, currentBarIndex + 1).map((bar, idx) => {
            const isCurrentBar = idx === currentBarIndex
            return {
                candle: {
                    time: convertToTimestamp(bar.time),
                    open: bar.open,
                    high: bar.high,
                    low: bar.low,
                    close: bar.close,
                    // Highlight current candle with different color
                    color: isCurrentBar ? '#ffeb3b' : (bar.close >= bar.open ? '#26a69a' : '#ef5350'),
                    borderColor: isCurrentBar ? '#ffc107' : undefined,
                    wickColor: isCurrentBar ? '#ffc107' : undefined,
                } as CandlestickData<Time>,
                volume: {
                    time: convertToTimestamp(bar.time),
                    value: bar.volume || 0,
                    color: bar.close >= bar.open ? 'rgba(38, 166, 154, 0.5)' : 'rgba(239, 83, 80, 0.5)',
                } as HistogramData<Time>,
            }
        })
    }, [bars, currentBarIndex])

    // Initialize chart on mount
    useEffect(() => {
        if (!containerRef.current) return

        const chart = createChart(containerRef.current, {
            width: containerRef.current.clientWidth,
            height: height,
            layout: {
                background: { color: '#1a1a2e' },
                textColor: '#d1d4dc',
            },
            grid: {
                vertLines: { color: '#2a2a4a' },
                horzLines: { color: '#2a2a4a' },
            },
            crosshair: { mode: 1 },
            rightPriceScale: { borderColor: '#3a3a5a' },
            timeScale: {
                borderColor: '#3a3a5a',
                timeVisible: true,
                secondsVisible: false,
            },
        })

        // Create price series (candlesticks)
        const candleSeries = chart.addCandlestickSeries({
            upColor: '#26a69a',
            downColor: '#ef5350',
            borderUpColor: '#26a69a',
            borderDownColor: '#ef5350',
            wickUpColor: '#26a69a',
            wickDownColor: '#ef5350',
        })

        // Create volume series (histogram at bottom)
        const volumeSeries = chart.addHistogramSeries({
            color: '#26a69a',
            priceFormat: { type: 'volume' },
            priceScaleId: '', // Overlay on main chart
        })

        // Configure volume to be 20% of chart height at bottom
        volumeSeries.priceScale().applyOptions({
            scaleMargins: {
                top: 0.8, // 80% for price chart
                bottom: 0, // Volume at bottom
            },
        })

        chartRef.current = chart
        candleSeriesRef.current = candleSeries
        volumeSeriesRef.current = volumeSeries

        // Handle resize
        const handleResize = () => {
            if (containerRef.current && chartRef.current) {
                const newHeight = sizeMode === 'fullscreen'
                    ? window.innerHeight - 180
                    : SIZE_HEIGHTS[sizeMode]
                chartRef.current.applyOptions({
                    width: containerRef.current.clientWidth,
                    height: newHeight,
                })
            }
        }

        window.addEventListener('resize', handleResize)
        return () => {
            window.removeEventListener('resize', handleResize)
            chart.remove()
            chartRef.current = null
            candleSeriesRef.current = null
            volumeSeriesRef.current = null
        }
    }, []) // Only initialize chart once on mount

    // Update data when bars change
    useEffect(() => {
        if (!candleSeriesRef.current || !volumeSeriesRef.current) return
        const candles = chartData.map(d => d.candle)
        const volumes = chartData.map(d => d.volume)
        candleSeriesRef.current.setData(candles)
        volumeSeriesRef.current.setData(volumes)

        // Auto-scroll to keep current bar visible
        if (chartRef.current && candles.length > 0) {
            chartRef.current.timeScale().scrollToRealTime()
        }
    }, [chartData])

    // Resize chart when sizeMode changes
    useEffect(() => {
        if (!containerRef.current || !chartRef.current) return
        const newHeight = sizeMode === 'fullscreen'
            ? window.innerHeight - 180
            : SIZE_HEIGHTS[sizeMode]
        chartRef.current.applyOptions({
            width: containerRef.current.clientWidth,
            height: newHeight,
        })
    }, [sizeMode])

    // Add order markers
    useEffect(() => {
        if (!candleSeriesRef.current) return

        // Create markers for buy/sell orders
        const markers = orders.map(order => ({
            time: convertToTimestamp(order.time),
            position: order.side === 'buy' ? 'belowBar' as const : 'aboveBar' as const,
            color: order.side === 'buy' ? '#26a69a' : '#ef5350',
            shape: order.side === 'buy' ? 'arrowUp' as const : 'arrowDown' as const,
            text: `${order.side.toUpperCase()} ${order.qty}`,
        }))
        candleSeriesRef.current.setMarkers(markers)
    }, [orders])

    // Handle ESC key to exit fullscreen
    useEffect(() => {
        const handleKeyDown = (e: KeyboardEvent) => {
            if (e.key === 'Escape' && sizeMode === 'fullscreen') {
                setSizeMode('theater')
            }
        }
        window.addEventListener('keydown', handleKeyDown)
        return () => window.removeEventListener('keydown', handleKeyDown)
    }, [sizeMode])

    // Calculate total P&L (unrealized from positions + realized)
    const totalPnl = simPositions.reduce((sum, p) => sum + p.pnl, 0) + realizedPnl

    return (
        <div className={`${styles.chartPanel} ${sizeMode === 'fullscreen' ? styles.chartFullscreen : ''}`}>
            {/* Fullscreen overlay header with controls */}
            {sizeMode === 'fullscreen' && clockState && (
                <div className={styles.fsOverlay}>
                    <div className={styles.fsControlsRow}>
                        <div className={styles.fsClockDisplay}>
                            <span className={styles.fsClockTime}>{clockState.time_string}</span>
                            <span className={styles.fsClockSpeed}>{clockState.speed}x</span>
                            {isPlaying && <span className={styles.playingIndicator}>▶</span>}
                        </div>

                        <div className={styles.fsPlaybackButtons}>
                            <button className={styles.btnPlayback} onClick={() => onStepBack?.(5)} title="-5 min">⏪</button>
                            <button className={styles.btnPlayback} onClick={() => onStepBack?.(1)} title="-1 min">◀</button>
                            <button
                                className={`${styles.btnPlayback} ${isPlaying ? styles.btnPlaybackActive : ''}`}
                                onClick={onTogglePlay}
                                title={isPlaying ? 'Pause' : 'Play'}
                            >
                                {isPlaying ? '⏸' : '▶'}
                            </button>
                            <button className={styles.btnPlayback} onClick={() => onStep?.(1)} title="+1 min">⏵</button>
                            <button className={styles.btnPlayback} onClick={() => onStep?.(5)} title="+5 min">⏩</button>
                            <button className={styles.btnPlayback} onClick={onResetClock} title="Reset">↻</button>
                        </div>

                        <div className={styles.fsSpeedSelector}>
                            {SPEEDS.filter(s => [1, 5, 10, 20, 50].includes(s)).map(speed => (
                                <button
                                    key={speed}
                                    className={`${styles.btnSpeed} ${clockState.speed === speed ? styles.btnSpeedActive : ''}`}
                                    onClick={() => onSetSpeed?.(speed)}
                                >
                                    {speed}x
                                </button>
                            ))}
                        </div>
                    </div>

                    <div className={styles.fsPositionRow}>
                        {simPositions.length > 0 ? (
                            simPositions.map((pos, idx) => (
                                <div key={idx} className={styles.fsPositionCard}>
                                    <span className={styles.fsPositionSymbol}>{pos.symbol}</span>
                                    <span className={styles.fsPositionQty}>{pos.qty} shs</span>
                                    <span className={styles.fsPositionAvg}>@ ${pos.avg.toFixed(2)}</span>
                                    <span className={`${styles.fsPositionPnl} ${pos.pnl >= 0 ? styles.pnlPositive : styles.pnlNegative}`}>
                                        {pos.pnl >= 0 ? '+' : ''}${pos.pnl.toFixed(2)}
                                    </span>
                                </div>
                            ))
                        ) : (
                            <div className={styles.fsNoPosition}>No open positions</div>
                        )}

                        <div className={styles.fsTotalPnl}>
                            <span className={styles.fsTotalLabel}>Total P&L:</span>
                            <span className={`${styles.fsTotalValue} ${totalPnl >= 0 ? styles.pnlPositive : styles.pnlNegative}`}>
                                {totalPnl >= 0 ? '+' : ''}${totalPnl.toFixed(2)}
                            </span>
                        </div>

                        <div className={styles.fsPrice}>
                            <span className={styles.fsPriceLabel}>Price:</span>
                            <span className={styles.fsPriceValue}>${currentPrice.toFixed(2)}</span>
                        </div>
                    </div>
                </div>
            )}

            <div className={styles.chartHeader}>
                <span
                    className={styles.chartSymbol}
                    onClick={() => window.open(`https://www.tradingview.com/chart/D7F9NNnO/?symbol=${symbol}`, '_blank')}
                    style={{ cursor: 'pointer' }}
                    title={`Open ${symbol} on TradingView`}
                >
                    {symbol}
                </span>
                <span className={styles.chartBarCount}>
                    {currentBarIndex + 1} / {bars.length} bars
                </span>
                <div className={styles.chartSizeButtons}>
                    <button
                        className={`${styles.chartSizeBtn} ${sizeMode === 'small' ? styles.active : ''}`}
                        onClick={() => setSizeMode('small')}
                        title="Small view"
                    >
                        ▫
                    </button>
                    <button
                        className={`${styles.chartSizeBtn} ${sizeMode === 'theater' ? styles.active : ''}`}
                        onClick={() => setSizeMode('theater')}
                        title="Theater mode"
                    >
                        ▬
                    </button>
                    <button
                        className={`${styles.chartSizeBtn} ${sizeMode === 'fullscreen' ? styles.active : ''}`}
                        onClick={() => setSizeMode('fullscreen')}
                        title="Fullscreen (ESC to exit)"
                    >
                        ⛶
                    </button>
                </div>
            </div>
            <div ref={containerRef} className={styles.chartContainer} />
            <div className={styles.chartAttribution}>
                <span className={styles.tvLogo}>TV</span>
            </div>
        </div>
    )
}
