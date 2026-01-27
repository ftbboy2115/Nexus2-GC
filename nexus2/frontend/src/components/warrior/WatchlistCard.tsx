/**
 * WatchlistCard - Watchlist display with sortable table and quality indicators
 */
import styles from '@/styles/Warrior.module.css'
import { CollapsibleCard } from './CollapsibleCard'
import { SortHeader } from './SortHeader'
import { sortData, toggleSort, SortConfig } from './formatters'

interface WatchlistItem {
    symbol: string
    gap_percent: number
    rvol: number
    pmh: number
    orb_high?: number | null
    entry_triggered?: boolean  // Entry was attempted (may be blocked)
    position_opened?: boolean  // Order was actually submitted (use this for "Entered")
    orb_established?: boolean
    catalyst_type?: string
    catalyst_description?: string
}

interface WatchlistCardProps {
    watchlist?: WatchlistItem[]
    watchlistCount: number
    watchlistSort: SortConfig
    setWatchlistSort: React.Dispatch<React.SetStateAction<SortConfig>>
    openChart: (symbol: string) => void
}

export function WatchlistCard({
    watchlist,
    watchlistCount,
    watchlistSort,
    setWatchlistSort,
    openChart,
}: WatchlistCardProps) {
    return (
        <CollapsibleCard
            id="watchlist"
            title="👁️ Watchlist"
            badge={<span className={styles.countBadge}>{watchlistCount}</span>}
        >
            <div className={styles.cardBody}>
                {watchlist && watchlist.length > 0 ? (
                    <div className={styles.watchlistTable}>
                        <table>
                            <thead>
                                <tr>
                                    <SortHeader label="Symbol" sortKey="symbol" sortConfig={watchlistSort} onSort={() => toggleSort('symbol', watchlistSort, setWatchlistSort)} />
                                    <th>Catalyst</th>
                                    <th title="Quality indicators: Gap, RVol, Entry">Quality</th>
                                    <SortHeader label="RVOL" sortKey="rvol" sortConfig={watchlistSort} onSort={() => toggleSort('rvol', watchlistSort, setWatchlistSort)} />
                                    <SortHeader label="PMH" sortKey="pmh" sortConfig={watchlistSort} onSort={() => toggleSort('pmh', watchlistSort, setWatchlistSort)} />
                                    <th>ORB High</th>
                                    <th>Status</th>
                                </tr>
                            </thead>
                            <tbody>
                                {sortData(watchlist, watchlistSort).map((w) => (
                                    <tr key={w.symbol} className={w.position_opened ? styles.triggered : ''}>
                                        <td className={styles.symbol}>
                                            <span
                                                className={styles.clickableSymbol}
                                                onClick={() => openChart(w.symbol)}
                                                title="Open TradingView chart"
                                            >
                                                {w.symbol}
                                            </span>
                                        </td>
                                        <td title={w.catalyst_description || ''}>
                                            {w.catalyst_type === 'earnings' ? '📊' :
                                                w.catalyst_type === 'fda' ? '💊' :
                                                    w.catalyst_type === 'contract' ? '📝' :
                                                        w.catalyst_type === 'acquisition' ? '🤝' :
                                                            w.catalyst_type === 'news' ? '📰' :
                                                                w.catalyst_type === 'former_runner' ? '🏃' : '-'}
                                        </td>
                                        <td>
                                            <div className={styles.indicatorRow}>
                                                <span className={`${styles.indicatorDot} ${w.gap_percent >= 15 ? styles.dotGreen : w.gap_percent >= 10 ? styles.dotYellow : styles.dotRed}`} title={`Gap: +${w.gap_percent.toFixed(1)}%`}>●</span>
                                                <span className={`${styles.indicatorDot} ${w.rvol >= 3 ? styles.dotGreen : w.rvol >= 2 ? styles.dotYellow : styles.dotRed}`} title={`RVol: ${w.rvol.toFixed(1)}x`}>●</span>
                                                <span className={`${styles.indicatorDot} ${w.position_opened ? styles.dotGreen : w.orb_established ? styles.dotYellow : styles.dotRed}`} title={w.position_opened ? 'Entered' : w.orb_established ? 'Watching' : 'Setup'}>●</span>
                                            </div>
                                        </td>
                                        <td>{w.rvol.toFixed(1)}x</td>
                                        <td>${w.pmh.toFixed(2)}</td>
                                        <td>{w.orb_high ? `$${w.orb_high.toFixed(2)}` : '-'}</td>
                                        <td>
                                            {w.position_opened ? '✅ Entered' :
                                                w.orb_established ? '⏳ Watching' : '📊 Setup'}
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                ) : (
                    <p className={styles.emptyMessage}>No symbols being watched</p>
                )}
            </div>
        </CollapsibleCard>
    )
}
