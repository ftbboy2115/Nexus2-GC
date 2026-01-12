import styles from '@/styles/Automation.module.css'
import { ScanResult, Signal } from '@/types/automation'

interface SignalsCardProps {
    signalStream: ScanResult | null
}

export default function SignalsCard({ signalStream }: SignalsCardProps) {
    if (!signalStream) return null

    return (
        <div className={`${styles.card} ${styles.signalCard}`}>
            <div className={styles.cardHeader}>
                <h2>📡 Signal Stream</h2>
                <span className={styles.scanTime}>
                    {new Date(signalStream.scanned_at).toLocaleTimeString()}
                </span>
            </div>
            <div className={styles.signalBreakdown}>
                <span className={styles.breakdownItem}>EP: {signalStream.breakdown.ep}</span>
                <span className={styles.breakdownItem}>Breakout: {signalStream.breakdown.breakout}</span>
                <span className={styles.breakdownItem}>HTF: {signalStream.breakdown.htf}</span>
                <span className={styles.breakdownItem}>Total: {signalStream.total_signals}</span>
            </div>
            {signalStream.signals.length > 0 ? (
                <>
                    <div className={styles.signalTable}>
                        <table>
                            <thead>
                                <tr>
                                    <th>Symbol</th>
                                    <th>Type</th>
                                    <th>Quality</th>
                                    <th>Tier</th>
                                    <th>Entry</th>
                                    <th>Stop</th>
                                    <th>Stop%</th>
                                    <th>Shares</th>
                                    <th>Risk</th>
                                </tr>
                            </thead>
                            <tbody>
                                {signalStream.signals.map((sig) => (
                                    <tr key={sig.symbol} className={sig.tier === 'FOCUS' ? styles.focusTier : ''}>
                                        <td className={styles.symbol}>{sig.symbol}</td>
                                        <td>{sig.setup_type.toUpperCase()}</td>
                                        <td>{sig.quality_score}/10</td>
                                        <td className={sig.tier === 'FOCUS' ? styles.tierFocus : styles.tierWide}>
                                            {sig.tier}
                                        </td>
                                        <td>${parseFloat(sig.entry_price).toFixed(2)}</td>
                                        <td>${parseFloat(sig.tactical_stop).toFixed(2)}</td>
                                        <td className={styles.stopPct}>{sig.stop_percent.toFixed(1)}%</td>
                                        <td>{sig.shares}</td>
                                        <td>${sig.risk_amount}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                    <div className={styles.signalHint}>
                        ⚡ These are proposed trades based on current scan. Click "Dry Run" to preview execution.
                    </div>
                </>
            ) : (
                <div className={styles.emptySignals}>
                    <p>No qualifying signals found</p>
                    <span className={styles.emptyHint}>
                        Filters: Quality ≥7, Stop ≤5%. Try during market hours for live data.
                    </span>
                </div>
            )}
        </div>
    )
}
