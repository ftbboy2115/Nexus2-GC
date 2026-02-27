/**
 * L2DepthCard - Real-time Level 2 order book depth visualization
 * Shows bid/ask depth ladder, signal badges, and imbalance bar
 */
import { useState, useEffect, useRef, useCallback } from 'react'
import styles from '@/styles/Warrior.module.css'
import { CollapsibleCard } from './CollapsibleCard'
import type { L2BookSnapshot, L2Status } from './types'

const API_BASE = ''
const POLL_INTERVAL_MS = 2000

export function L2DepthCard() {
    const [l2Status, setL2Status] = useState<L2Status | null>(null)
    const [book, setBook] = useState<L2BookSnapshot | null>(null)
    const [selectedSymbol, setSelectedSymbol] = useState<string>('')
    const [error, setError] = useState<string | null>(null)
    const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

    // Fetch L2 subsystem status on mount
    useEffect(() => {
        const fetchStatus = async () => {
            try {
                const res = await fetch(`${API_BASE}/warrior/l2/status`)
                if (res.ok) {
                    const data: L2Status = await res.json()
                    setL2Status(data)
                    // Auto-select first subscription if none selected
                    if (data.subscriptions.length > 0 && !selectedSymbol) {
                        setSelectedSymbol(data.subscriptions[0])
                    }
                    setError(null)
                } else if (res.status === 404) {
                    setError('L2 endpoints not available')
                } else {
                    setError('Failed to fetch L2 status')
                }
            } catch {
                setError('L2 not available')
            }
        }
        fetchStatus()
        const interval = setInterval(fetchStatus, 10000) // Refresh status every 10s
        return () => clearInterval(interval)
    }, []) // eslint-disable-line react-hooks/exhaustive-deps

    // Fetch book snapshot for selected symbol
    const fetchBook = useCallback(async () => {
        if (!selectedSymbol || !l2Status?.enabled) return
        try {
            const res = await fetch(`${API_BASE}/warrior/l2/${selectedSymbol}`)
            if (res.ok) {
                const data: L2BookSnapshot = await res.json()
                setBook(data)
            }
        } catch {
            // Silently fail on poll — status check will surface errors
        }
    }, [selectedSymbol, l2Status?.enabled])

    // Poll book data every 2s
    useEffect(() => {
        if (pollRef.current) clearInterval(pollRef.current)
        if (!selectedSymbol || !l2Status?.enabled || !l2Status?.connected) {
            setBook(null)
            return
        }
        fetchBook()
        pollRef.current = setInterval(fetchBook, POLL_INTERVAL_MS)
        return () => {
            if (pollRef.current) clearInterval(pollRef.current)
        }
    }, [selectedSymbol, l2Status?.enabled, l2Status?.connected, fetchBook])

    // ========================================================================
    // Helpers
    // ========================================================================

    const qualityColor = (quality: string) => {
        switch (quality) {
            case 'tight': return '#28a745'
            case 'normal': return '#ffc107'
            case 'wide': return '#dc3545'
            default: return '#888'
        }
    }

    const formatVolume = (vol: number) => {
        if (vol >= 10000) return `${(vol / 1000).toFixed(1)}K`
        if (vol >= 1000) return `${(vol / 1000).toFixed(1)}K`
        return vol.toString()
    }

    // ========================================================================
    // Render states
    // ========================================================================

    const renderDisabledState = () => (
        <div className={styles.cardBody}>
            <p className={styles.emptyMessage}>
                {error || 'L2 Disabled — Enable L2 streaming in backend configuration'}
            </p>
        </div>
    )

    const renderDisconnectedState = () => (
        <div className={styles.cardBody}>
            <p className={styles.emptyMessage}>
                ⚡ L2 stream disconnected — waiting for reconnection...
            </p>
        </div>
    )

    const renderNoSubscriptions = () => (
        <div className={styles.cardBody}>
            <p className={styles.emptyMessage}>
                No L2 subscriptions active — start the scanner to subscribe to symbols
            </p>
        </div>
    )

    // ========================================================================
    // Main render
    // ========================================================================

    const connectionBadge = l2Status ? (
        <span className={`${styles.badge} ${l2Status.connected ? styles.badgeGreen : styles.badgeGray}`}
            style={{ fontSize: '0.7rem', padding: '0.2rem 0.5rem' }}>
            {l2Status.connected ? '● Connected' : '○ Disconnected'}
        </span>
    ) : null

    return (
        <CollapsibleCard
            id="l2-depth"
            title="📊 L2 Order Book"
            badge={connectionBadge}
            defaultCollapsed={true}
        >
            {/* Error / disabled states */}
            {(!l2Status || !l2Status.enabled) && renderDisabledState()}
            {l2Status?.enabled && !l2Status.connected && renderDisconnectedState()}
            {l2Status?.enabled && l2Status.connected && l2Status.subscriptions.length === 0 && renderNoSubscriptions()}

            {/* Active state */}
            {l2Status?.enabled && l2Status.connected && l2Status.subscriptions.length > 0 && (
                <div className={styles.cardBody}>
                    {/* Symbol selector */}
                    <div className={styles.l2SymbolSelector}>
                        <select
                            className={styles.selectInput}
                            value={selectedSymbol}
                            onChange={(e) => setSelectedSymbol(e.target.value)}
                            style={{ minWidth: '120px', flex: 'unset', maxWidth: '160px' }}
                        >
                            {l2Status.subscriptions.map(sym => (
                                <option key={sym} value={sym}>{sym}</option>
                            ))}
                        </select>
                        <button
                            className={styles.refreshBtn}
                            onClick={fetchBook}
                            style={{ padding: '0.4rem 0.6rem', fontSize: '0.8rem' }}
                        >
                            🔄
                        </button>
                        {book && (
                            <span style={{ fontSize: '0.7rem', color: '#666', marginLeft: 'auto' }}>
                                {new Date(book.timestamp).toLocaleTimeString()}
                            </span>
                        )}
                    </div>

                    {book ? (
                        <>
                            {/* Spread & Quality info row */}
                            <div className={styles.l2InfoRow}>
                                <span>
                                    Spread: <strong>${book.spread.toFixed(2)}</strong>
                                    {book.signals?.spread_quality && (
                                        <span style={{ color: '#888' }}> ({book.signals.spread_quality.spread_bps.toFixed(1)} bps)</span>
                                    )}
                                </span>
                                {book.signals?.spread_quality && (
                                    <span>
                                        Quality: <span style={{ color: qualityColor(book.signals.spread_quality.quality) }}>●</span>
                                        {' '}{book.signals.spread_quality.quality.charAt(0).toUpperCase() + book.signals.spread_quality.quality.slice(1)}
                                    </span>
                                )}
                            </div>

                            {/* Imbalance bar */}
                            {book.signals?.spread_quality && (
                                <div className={styles.l2ImbalanceContainer}>
                                    <span className={styles.l2ImbalanceLabel}>Imbalance</span>
                                    <div className={styles.l2ImbalanceBar}>
                                        <div
                                            className={styles.l2ImbalanceFill}
                                            style={{
                                                width: `${Math.abs(book.signals.spread_quality.imbalance) * 50}%`,
                                                marginLeft: book.signals.spread_quality.imbalance >= 0 ? '50%' : `${50 - Math.abs(book.signals.spread_quality.imbalance) * 50}%`,
                                                background: book.signals.spread_quality.imbalance >= 0
                                                    ? 'linear-gradient(90deg, rgba(40, 167, 69, 0.3), rgba(40, 167, 69, 0.7))'
                                                    : 'linear-gradient(90deg, rgba(220, 53, 69, 0.7), rgba(220, 53, 69, 0.3))',
                                            }}
                                        />
                                        <div className={styles.l2ImbalanceCenter} />
                                    </div>
                                    <span className={styles.l2ImbalanceValue} style={{
                                        color: book.signals.spread_quality.imbalance >= 0 ? '#28a745' : '#dc3545'
                                    }}>
                                        {book.signals.spread_quality.imbalance >= 0 ? '+' : ''}
                                        {book.signals.spread_quality.imbalance.toFixed(2)}
                                        {' '}{book.signals.spread_quality.imbalance >= 0 ? 'Buyers' : 'Sellers'}
                                    </span>
                                </div>
                            )}

                            {/* Depth Ladder */}
                            <div className={styles.l2DepthLadder}>
                                {/* Header */}
                                <div className={styles.l2LadderHeader}>
                                    <span>Vol</span>
                                    <span>Bid</span>
                                    <span>Ask</span>
                                    <span>Vol</span>
                                </div>

                                {/* Rows — merge bids and asks side by side */}
                                {Array.from({ length: Math.max(book.bids.length, book.asks.length, 1) }).map((_, i) => {
                                    const bid = book.bids[i]
                                    const ask = book.asks[i]
                                    const maxVol = Math.max(
                                        ...book.bids.map(b => b.volume),
                                        ...book.asks.map(a => a.volume),
                                        1
                                    )
                                    const isBidWall = book.signals?.bid_wall && bid && Math.abs(bid.price - book.signals.bid_wall.price) < 0.01
                                    const isAskWall = book.signals?.ask_wall && ask && Math.abs(ask.price - book.signals.ask_wall.price) < 0.01

                                    return (
                                        <div key={i} className={styles.l2Row}>
                                            {/* Bid side */}
                                            <div className={`${styles.l2BidSide} ${isBidWall ? styles.l2WallHighlight : ''}`}>
                                                {bid ? (
                                                    <>
                                                        <span className={styles.l2Volume}>{formatVolume(bid.volume)}</span>
                                                        <div className={styles.l2BarContainer}>
                                                            <div
                                                                className={styles.l2BidBar}
                                                                style={{ width: `${(bid.volume / maxVol) * 100}%` }}
                                                            />
                                                        </div>
                                                        <span className={styles.l2Price} style={{ color: '#28a745' }}>
                                                            {bid.price.toFixed(2)}
                                                            {isBidWall && ' 🧱'}
                                                        </span>
                                                    </>
                                                ) : (
                                                    <span className={styles.l2Empty}>—</span>
                                                )}
                                            </div>

                                            {/* Ask side */}
                                            <div className={`${styles.l2AskSide} ${isAskWall ? styles.l2WallHighlight : ''}`}>
                                                {ask ? (
                                                    <>
                                                        <span className={styles.l2Price} style={{ color: '#dc3545' }}>
                                                            {isAskWall && '🧱 '}{ask.price.toFixed(2)}
                                                        </span>
                                                        <div className={styles.l2BarContainer}>
                                                            <div
                                                                className={styles.l2AskBar}
                                                                style={{ width: `${(ask.volume / maxVol) * 100}%` }}
                                                            />
                                                        </div>
                                                        <span className={styles.l2Volume}>{formatVolume(ask.volume)}</span>
                                                    </>
                                                ) : (
                                                    <span className={styles.l2Empty}>—</span>
                                                )}
                                            </div>
                                        </div>
                                    )
                                })}
                            </div>

                            {/* Signal Badges */}
                            <div className={styles.l2SignalBadges}>
                                {book.signals?.bid_wall && (
                                    <span className={`${styles.l2SignalBadge} ${styles.l2BadgeBid}`}>
                                        🧱 Bid Wall @ ${book.signals.bid_wall.price.toFixed(2)} ({formatVolume(book.signals.bid_wall.volume)})
                                    </span>
                                )}
                                {book.signals?.ask_wall && (
                                    <span className={`${styles.l2SignalBadge} ${styles.l2BadgeAsk}`}>
                                        🧱 Ask Wall @ ${book.signals.ask_wall.price.toFixed(2)} ({formatVolume(book.signals.ask_wall.volume)})
                                    </span>
                                )}
                                {book.signals?.thin_ask ? (
                                    <span className={`${styles.l2SignalBadge} ${styles.l2BadgeWarn}`}>
                                        ⚠️ Thin Ask ({book.signals.thin_ask.levels_count} lvls, {formatVolume(book.signals.thin_ask.total_volume)})
                                    </span>
                                ) : book.signals && (
                                    <span className={`${styles.l2SignalBadge} ${styles.l2BadgeOk}`}>
                                        ✅ Ask Depth OK
                                    </span>
                                )}
                            </div>
                        </>
                    ) : (
                        <p className={styles.emptyMessage}>Loading book data...</p>
                    )}
                </div>
            )}
        </CollapsibleCard>
    )
}
