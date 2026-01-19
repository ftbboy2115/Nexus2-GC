/**
 * ScannerCard - Manual scanner with results table
 */
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
