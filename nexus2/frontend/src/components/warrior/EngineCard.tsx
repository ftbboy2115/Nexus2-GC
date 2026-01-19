/**
 * EngineCard - Last Engine Scan results with sortable table
 */
import styles from '@/styles/Warrior.module.css'
import { CollapsibleCard } from './CollapsibleCard'
import { SortHeader } from './SortHeader'
import { sortData, toggleSort, SortConfig } from './formatters'

interface EngineCandidate {
    symbol: string
    gap_percent: number
    rvol: number
    price: number
    in_watchlist?: boolean
}

interface LastScanResult {
    processed_count: number
    candidates: EngineCandidate[]
}

interface EngineCardProps {
    lastScanResult?: LastScanResult | null
    engineScanSort: SortConfig
    setEngineScanSort: React.Dispatch<React.SetStateAction<SortConfig>>
    openChart: (symbol: string) => void
}

export function EngineCard({
    lastScanResult,
    engineScanSort,
    setEngineScanSort,
    openChart,
}: EngineCardProps) {
    return (
        <CollapsibleCard
            id="engineScan"
            title="📊 Last Engine Scan"
            badge={
                lastScanResult && (
                    <span className={styles.countBadge}>
                        {lastScanResult.candidates.length}
                    </span>
                )
            }
        >
            <div className={styles.cardBody}>
                {lastScanResult ? (
                    <>
                        <div className={styles.scanStats}>
                            <span>Processed: {lastScanResult.processed_count}</span>
                            <span>Found: {lastScanResult.candidates.length}</span>
                        </div>
                        {lastScanResult.candidates.length > 0 ? (
                            <div className={styles.candidateTable}>
                                <table>
                                    <thead>
                                        <tr>
                                            <SortHeader label="Symbol" sortKey="symbol" sortConfig={engineScanSort} onSort={() => toggleSort('symbol', engineScanSort, setEngineScanSort)} />
                                            <SortHeader label="Gap%" sortKey="gap_percent" sortConfig={engineScanSort} onSort={() => toggleSort('gap_percent', engineScanSort, setEngineScanSort)} />
                                            <SortHeader label="RVOL" sortKey="rvol" sortConfig={engineScanSort} onSort={() => toggleSort('rvol', engineScanSort, setEngineScanSort)} />
                                            <SortHeader label="Price" sortKey="price" sortConfig={engineScanSort} onSort={() => toggleSort('price', engineScanSort, setEngineScanSort)} />
                                            <th>Status</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {sortData(lastScanResult.candidates, engineScanSort).map((c) => (
                                            <tr key={c.symbol} className={c.in_watchlist ? styles.inWatchlist : ''}>
                                                <td className={styles.symbol}>
                                                    <span
                                                        className={styles.clickableSymbol}
                                                        onClick={() => openChart(c.symbol)}
                                                        title="Open TradingView chart"
                                                    >
                                                        {c.symbol}
                                                    </span>
                                                </td>
                                                <td className={c.gap_percent >= 10 ? styles.pnlPositive : ''}>{c.gap_percent.toFixed(1)}%</td>
                                                <td>{c.rvol.toFixed(1)}x</td>
                                                <td>${c.price.toFixed(2)}</td>
                                                <td>{c.in_watchlist ? '👁️' : '-'}</td>
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
                    <p className={styles.emptyMessage}>Engine hasn't scanned yet. Start the engine to begin.</p>
                )}
            </div>
        </CollapsibleCard>
    )
}
