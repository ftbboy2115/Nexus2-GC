/**
 * ScannerCard - Manual scanner with results table + RVOL threshold setting
 */
import { useState, useEffect, useRef } from 'react'
import styles from '@/styles/Warrior.module.css'
import { CollapsibleCard } from './CollapsibleCard'
import { formatFloat } from './formatters'

interface ScanCandidate {
    symbol: string
    price: number
    gap_percent: number
    relative_volume: number
    float_shares: number | null
    catalyst_type?: string
    catalyst_description?: string
    quality_score: number
    is_ideal_gap?: boolean
    is_ideal_rvol?: boolean
    is_ideal_float?: boolean
}

interface ScanResult {
    processed_count: number
    candidates: ScanCandidate[]
    avg_rvol: number
    avg_gap: number
}

interface ScannerCardProps {
    scanResult: ScanResult | null
    runScan: () => void
    openChart: (symbol: string) => void
    actionLoading: string | null
}

export function ScannerCard({ scanResult, runScan, openChart, actionLoading }: ScannerCardProps) {
    const [minRvol, setMinRvol] = useState<number>(2.0)
    const [settingsLoaded, setSettingsLoaded] = useState(false)
    const [saving, setSaving] = useState(false)
    const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

    // Fetch current scanner settings on mount
    useEffect(() => {
        const fetchSettings = async () => {
            try {
                const res = await fetch('/warrior/scanner/settings')
                if (res.ok) {
                    const data = await res.json()
                    if (data.min_rvol !== undefined && data.min_rvol !== null) {
                        setMinRvol(Number(data.min_rvol))
                    }
                    setSettingsLoaded(true)
                }
            } catch (err) {
                console.error('Failed to fetch scanner settings:', err)
                setSettingsLoaded(true) // Use default on error
            }
        }
        fetchSettings()
    }, [])

    // Save scanner settings (debounced)
    const saveRvol = (value: number) => {
        setMinRvol(value)
        if (debounceRef.current) clearTimeout(debounceRef.current)
        debounceRef.current = setTimeout(async () => {
            setSaving(true)
            try {
                await fetch('/warrior/scanner/settings', {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ min_rvol: value }),
                })
            } catch (err) {
                console.error('Failed to save RVOL setting:', err)
            } finally {
                setSaving(false)
            }
        }, 400)
    }

    // Increment/decrement by 0.1, clamped to [0.5, 10.0]
    const adjustRvol = (delta: number) => {
        const next = Math.round((minRvol + delta) * 10) / 10
        const clamped = Math.max(0.5, Math.min(10.0, next))
        saveRvol(clamped)
    }

    // Color the RVOL value based on threshold level
    const getRvolColor = (val: number): string => {
        if (val >= 5.0) return '#22c55e'   // Green - Ross's ideal
        if (val >= 2.0) return '#eab308'   // Yellow - default
        return '#f97316'                    // Orange - aggressive/low
    }

    return (
        <CollapsibleCard
            id="scanner"
            title="🔍 Scanner"
            badge={
                <button
                    onClick={(e) => { e.stopPropagation(); runScan(); }}
                    className={styles.btnSmall}
                    disabled={actionLoading === 'scan'}
                >
                    {actionLoading === 'scan' ? '...' : 'Run Scan'}
                </button>
            }
        >
            <div className={styles.cardBody}>
                {/* Scanner Settings: RVOL Threshold */}
                <div style={{
                    padding: '0.75rem 1rem',
                    background: 'rgba(255, 255, 255, 0.02)',
                    borderRadius: '8px',
                    border: '1px solid rgba(255, 255, 255, 0.06)',
                    marginBottom: '1rem',
                }}>
                    <div style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                        marginBottom: '0.5rem',
                    }}>
                        <label
                            style={{ fontSize: '0.85rem', color: '#888', cursor: 'help' }}
                            title="Minimum RVOL threshold for scanner candidates. Ross's ideal is 5x. Lower values (1.5x) catch news-driven momentum with less volume confirmation. Default: 2.0x"
                        >
                            Min Relative Volume
                            <span style={{ fontSize: '0.7rem', marginLeft: '4px', opacity: 0.6 }}>ℹ️</span>
                        </label>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                            <button
                                onClick={() => adjustRvol(-0.5)}
                                className={styles.btnSmall}
                                title="Decrease by 0.5"
                            >
                                ▼▼
                            </button>
                            <button
                                onClick={() => adjustRvol(-0.1)}
                                className={styles.btnSmall}
                                title="Decrease by 0.1"
                            >
                                −
                            </button>
                            <span style={{
                                minWidth: '3.5rem',
                                textAlign: 'center',
                                fontWeight: 700,
                                fontSize: '1.1rem',
                                color: getRvolColor(minRvol),
                                fontFamily: "'Consolas', 'Monaco', monospace",
                                transition: 'color 0.3s ease',
                            }}>
                                {minRvol.toFixed(1)}x
                            </span>
                            <button
                                onClick={() => adjustRvol(0.1)}
                                className={styles.btnSmall}
                                title="Increase by 0.1"
                            >
                                +
                            </button>
                            <button
                                onClick={() => adjustRvol(0.5)}
                                className={styles.btnSmall}
                                title="Increase by 0.5"
                            >
                                ▲▲
                            </button>
                        </div>
                    </div>

                    {/* Range Slider */}
                    <div style={{ position: 'relative' }}>
                        <input
                            type="range"
                            min={0.5}
                            max={10.0}
                            step={0.1}
                            value={minRvol}
                            onChange={(e) => saveRvol(parseFloat(e.target.value))}
                            style={{
                                width: '100%',
                                height: '6px',
                                borderRadius: '3px',
                                appearance: 'none',
                                WebkitAppearance: 'none',
                                background: `linear-gradient(to right, #f97316 0%, #eab308 ${((2.0 - 0.5) / 9.5) * 100}%, #22c55e ${((5.0 - 0.5) / 9.5) * 100}%, #22c55e 100%)`,
                                outline: 'none',
                                cursor: 'pointer',
                                opacity: settingsLoaded ? 1 : 0.5,
                            }}
                            disabled={!settingsLoaded}
                        />
                        {/* Scale markers */}
                        <div style={{
                            display: 'flex',
                            justifyContent: 'space-between',
                            marginTop: '2px',
                            fontSize: '0.65rem',
                            color: '#666',
                        }}>
                            <span>0.5x</span>
                            <span style={{ color: '#eab308' }}>2.0x</span>
                            <span style={{ color: '#22c55e' }}>5.0x</span>
                            <span>10x</span>
                        </div>
                    </div>
                    {saving && (
                        <div style={{ fontSize: '0.7rem', color: '#6366f1', marginTop: '4px', textAlign: 'right' }}>
                            Saving...
                        </div>
                    )}
                </div>

                {/* Scan Results */}
                {scanResult ? (
                    <>
                        <div className={styles.scanStats}>
                            <span>Processed: {scanResult.processed_count}</span>
                            <span>Passed: {scanResult.candidates.length}</span>
                            <span>Avg RVOL: {scanResult.avg_rvol.toFixed(1)}x</span>
                            <span>Avg Gap: {scanResult.avg_gap.toFixed(1)}%</span>
                        </div>

                        {scanResult.candidates.length > 0 ? (
                            <div className={styles.candidateTable}>
                                <table>
                                    <thead>
                                        <tr>
                                            <th>Symbol</th>
                                            <th>Price</th>
                                            <th>Gap%</th>
                                            <th>RVOL</th>
                                            <th>Float</th>
                                            <th>Catalyst</th>
                                            <th>Score</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {scanResult.candidates.slice(0, 10).map((c) => (
                                            <tr key={c.symbol}>
                                                <td className={styles.symbol}>
                                                    <span
                                                        className={styles.clickableSymbol}
                                                        onClick={() => openChart(c.symbol)}
                                                        title="Open TradingView chart"
                                                    >
                                                        {c.symbol}
                                                    </span>
                                                </td>
                                                <td>${c.price.toFixed(2)}</td>
                                                <td className={c.is_ideal_gap ? styles.ideal : ''}>
                                                    {c.gap_percent.toFixed(1)}%
                                                </td>
                                                <td className={c.is_ideal_rvol ? styles.ideal : ''}>
                                                    {c.relative_volume.toFixed(1)}x
                                                </td>
                                                <td className={c.is_ideal_float ? styles.ideal : ''}>
                                                    {formatFloat(c.float_shares)}
                                                </td>
                                                <td title={c.catalyst_description}>
                                                    {c.catalyst_type === 'earnings' ? '📊' :
                                                        c.catalyst_type === 'news' ? '📰' :
                                                            c.catalyst_type === 'former_runner' ? '🏃' : '-'}
                                                </td>
                                                <td className={styles.score}>
                                                    <span className={`${styles.scoreBar} ${styles[`score${Math.min(10, Math.max(0, c.quality_score))}`]}`}>
                                                        {c.quality_score}/10
                                                    </span>
                                                </td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        ) : (
                            <p className={styles.emptyMessage}>No candidates found</p>
                        )}
                    </>
                ) : (
                    <p className={styles.emptyMessage}>Click "Run Scan" to find candidates</p>
                )}
            </div>
        </CollapsibleCard>
    )
}
