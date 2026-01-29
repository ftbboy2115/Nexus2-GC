/**
 * ChartPanel - TradingView-style candlestick chart for Mock Market replay
 * 
 * Uses lightweight-charts (TradingView's open-source library) to display
 * historical price data bar-by-bar as the simulation clock advances.
 */
import { useEffect, useRef, useMemo } from 'react'
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

interface ChartPanelProps {
    bars: BarData[]              // All visible bars up to current time
    currentBarIndex: number      // Index of the current bar
    symbol: string
    orders?: OrderMarker[]       // Entry/exit markers to display
    height?: number              // Chart height in pixels (default 350)
}

export function ChartPanel({
    bars,
    currentBarIndex,
    symbol,
    orders = [],
    height = 350,
}: ChartPanelProps) {
    const containerRef = useRef<HTMLDivElement>(null)
    const chartRef = useRef<IChartApi | null>(null)
    const candleSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null)
    const volumeSeriesRef = useRef<ISeriesApi<'Histogram'> | null>(null)

    // Convert time strings to Unix timestamps for lightweight-charts
    // Using today's date as base since we only have HH:MM format
    const convertToTimestamp = (timeStr: string): Time => {
        const [hours, minutes] = timeStr.split(':').map(Number)
        // Create a date object for today with the given time
        const date = new Date()
        date.setHours(hours, minutes, 0, 0)
        // Return as Unix timestamp (seconds)
        return Math.floor(date.getTime() / 1000) as Time
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
            crosshair: {
                mode: 1, // Normal crosshair
            },
            rightPriceScale: {
                borderColor: '#3a3a5a',
            },
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
            priceFormat: {
                type: 'volume',
            },
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
                chartRef.current.applyOptions({
                    width: containerRef.current.clientWidth,
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
    }, [height])

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

    // Add order markers when orders change
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

    return (
        <div className={styles.chartPanel}>
            <div className={styles.chartHeader}>
                <span className={styles.chartSymbol}>{symbol}</span>
                <span className={styles.chartBarCount}>
                    {currentBarIndex + 1} / {bars.length} bars
                </span>
            </div>
            <div ref={containerRef} className={styles.chartContainer} />
        </div>
    )
}
