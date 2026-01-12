import styles from '@/styles/Automation.module.css'
import { PositionsData, SimPositionsData, SchedulerSettingsData, BrokerPosition, SimPosition } from '@/types/automation'

interface ColumnConfig {
    id: string
    label: string
    visible: boolean
}

interface PositionSort {
    column: string
    direction: 'asc' | 'desc'
}

interface PositionsCardProps {
    schedulerSettings: SchedulerSettingsData | null
    positions: PositionsData | null
    simPositions: SimPositionsData | null
    positionsMaximized: boolean
    positionSort: PositionSort
    columns: ColumnConfig[]
    allColumns: ColumnConfig[]
    onMaximizeToggle: () => void
    onSortChange: (sort: PositionSort) => void
    onExportCsv: () => void
    onOpenColumnEditor: () => void
}

export default function PositionsCard({
    schedulerSettings,
    positions,
    simPositions,
    positionsMaximized,
    positionSort,
    columns,
    allColumns,
    onMaximizeToggle,
    onSortChange,
    onExportCsv,
    onOpenColumnEditor,
}: PositionsCardProps) {
    const isSimMode = schedulerSettings?.sim_mode
    const displayColumns = positionsMaximized ? allColumns : columns

    const handleSort = (columnId: string) => {
        onSortChange({
            column: columnId,
            direction: positionSort.column === columnId && positionSort.direction === 'desc' ? 'asc' : 'desc'
        })
    }

    const sortPositions = <T extends BrokerPosition | SimPosition>(positions: T[]): T[] => {
        return [...positions].sort((a, b) => {
            const key = positionSort.column as keyof T
            const aVal = a[key] ?? 0
            const bVal = b[key] ?? 0
            if (typeof aVal === 'string' && typeof bVal === 'string') {
                return positionSort.direction === 'asc'
                    ? aVal.localeCompare(bVal)
                    : bVal.localeCompare(aVal)
            }
            return positionSort.direction === 'asc'
                ? (aVal as number) - (bVal as number)
                : (bVal as number) - (aVal as number)
        })
    }

    const renderCellValue = (pos: BrokerPosition, colId: string) => {
        switch (colId) {
            case 'symbol':
                return <td key={colId} className={styles.symbol}>{pos.symbol}</td>
            case 'qty':
                return <td key={colId}>{pos.qty}</td>
            case 'side':
                return <td key={colId}>{pos.side?.toUpperCase() || 'LONG'}</td>
            case 'avg_price':
                return <td key={colId}>${pos.avg_price.toFixed(2)}</td>
            case 'current_price':
                return <td key={colId}>${pos.current_price?.toFixed(2) || '-'}</td>
            case 'stop_price':
                return <td key={colId} style={{ color: '#f59e0b' }}>${pos.stop_price?.toFixed(2) || '-'}</td>
            case 'market_value':
                return <td key={colId}>${pos.market_value.toFixed(0)}</td>
            case 'unrealized_pnl':
                return (
                    <td key={colId} style={{ color: pos.unrealized_pnl > 0 ? '#22c55e' : pos.unrealized_pnl < 0 ? '#ef4444' : '#9ca3af' }}>
                        {pos.unrealized_pnl >= 0 ? '+' : ''}${pos.unrealized_pnl.toFixed(2)}
                    </td>
                )
            case 'pnl_percent':
                return (
                    <td key={colId} style={{ color: pos.pnl_percent > 0 ? '#22c55e' : pos.pnl_percent < 0 ? '#ef4444' : '#9ca3af' }}>
                        {pos.pnl_percent >= 0 ? '+' : ''}{pos.pnl_percent.toFixed(1)}%
                    </td>
                )
            case 'today_pnl':
                const todayPnl = pos.today_pnl || 0
                return (
                    <td key={colId} style={{ color: todayPnl > 0 ? '#22c55e' : todayPnl < 0 ? '#ef4444' : '#9ca3af' }}>
                        {todayPnl >= 0 ? '+' : ''}${todayPnl.toFixed(2)}
                    </td>
                )
            case 'change_today':
                const changeToday = pos.change_today || 0
                return (
                    <td key={colId} style={{ color: changeToday > 0 ? '#22c55e' : changeToday < 0 ? '#ef4444' : '#9ca3af' }}>
                        {changeToday >= 0 ? '+' : ''}{changeToday.toFixed(1)}%
                    </td>
                )
            case 'days_held':
                return <td key={colId}>{pos.days_held || 0}d</td>
            default:
                return <td key={colId}>-</td>
        }
    }

    const renderTotalCell = (colId: string) => {
        if (!positions) return <td key={colId}></td>

        switch (colId) {
            case 'symbol':
                return <td key={colId} style={{ color: '#9ca3af' }}>TOTAL ({positions.positions.length})</td>
            case 'qty':
                const totalQty = positions.positions.reduce((sum, p) => sum + p.qty, 0)
                return <td key={colId}>{totalQty}</td>
            case 'avg_price':
                const costBasis = positions.positions.reduce((sum, p) => sum + (p.qty * p.avg_price), 0)
                return <td key={colId} style={{ color: '#9ca3af' }}>${costBasis.toFixed(0)}</td>
            case 'market_value':
                return <td key={colId}>${positions.total_value.toFixed(0)}</td>
            case 'unrealized_pnl':
                return (
                    <td key={colId} style={{ color: positions.total_pnl >= 0 ? '#22c55e' : '#ef4444' }}>
                        {positions.total_pnl >= 0 ? '+' : ''}${positions.total_pnl.toFixed(2)}
                    </td>
                )
            case 'pnl_percent':
                const totalPnlPct = positions.total_value > 0
                    ? (positions.total_pnl / (positions.total_value - positions.total_pnl)) * 100
                    : 0
                return (
                    <td key={colId} style={{ color: totalPnlPct >= 0 ? '#22c55e' : '#ef4444' }}>
                        {totalPnlPct >= 0 ? '+' : ''}{totalPnlPct.toFixed(1)}%
                    </td>
                )
            case 'today_pnl':
                const totalTodayPnl = positions.positions.reduce((sum, p) => sum + (p.today_pnl || 0), 0)
                return (
                    <td key={colId} style={{ color: totalTodayPnl >= 0 ? '#22c55e' : '#ef4444' }}>
                        {totalTodayPnl >= 0 ? '+' : ''}${totalTodayPnl.toFixed(2)}
                    </td>
                )
            default:
                return <td key={colId}></td>
        }
    }

    return (
        <>
            {/* Maximized overlay backdrop */}
            {positionsMaximized && (
                <div
                    style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, zIndex: 99, backgroundColor: 'rgba(0, 0, 0, 0.8)', backdropFilter: 'blur(4px)' }}
                    onClick={onMaximizeToggle}
                />
            )}

            <div className={styles.card} style={positionsMaximized ? { position: 'fixed', top: '70px', left: '20px', right: '20px', bottom: '20px', zIndex: 100, margin: 0, borderRadius: '12px', display: 'flex', flexDirection: 'column', overflow: 'hidden' } : {}}>
                <div className={styles.cardHeader} style={{ display: 'flex', flexDirection: 'column', gap: '8px', flexShrink: 0 }}>
                    {/* Title row with window controls */}
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', width: '100%' }}>
                        <h2 style={{ margin: 0 }}>
                            {isSimMode ? '🧪 Sim Positions' : '📊 Open Positions'}
                        </h2>
                        <div style={{ display: 'flex', gap: '4px' }}>
                            <button
                                onClick={onExportCsv}
                                style={{ padding: '4px 8px', fontSize: '14px', background: 'transparent', border: '1px solid #4b5563', borderRadius: '4px', cursor: 'pointer', color: '#9ca3af' }}
                                title="Export to CSV"
                            >
                                📥
                            </button>
                            <button
                                onClick={onOpenColumnEditor}
                                style={{ padding: '4px 8px', fontSize: '14px', background: 'transparent', border: '1px solid #4b5563', borderRadius: '4px', cursor: 'pointer', color: '#9ca3af' }}
                                title="Configure columns"
                            >
                                ⚙️
                            </button>
                            <button
                                onClick={onMaximizeToggle}
                                style={{ width: '24px', height: '24px', padding: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'transparent', border: '1px solid #4b5563', borderRadius: '4px', cursor: 'pointer' }}
                                title={positionsMaximized ? 'Restore' : 'Maximize'}
                            >
                                {positionsMaximized ? (
                                    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="#9ca3af" strokeWidth="1.5">
                                        <path d="M5 1v4H1M9 13v-4h4M5 5L1 1M9 9l4 4" />
                                    </svg>
                                ) : (
                                    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="#9ca3af" strokeWidth="1.5">
                                        <path d="M1 5V1h4M13 9v4H9M1 1l4 4M13 13l-4-4" />
                                    </svg>
                                )}
                            </button>
                        </div>
                    </div>
                    {/* Badge row */}
                    {isSimMode ? (
                        <span className={`${styles.badge}`} style={{ backgroundColor: '#8b5cf6', color: '#fff', alignSelf: 'flex-start' }}>
                            {simPositions?.count || 0} positions • ${simPositions?.account?.portfolio_value?.toFixed(0) || '100,000'}
                        </span>
                    ) : positions?.count ? (
                        <span className={`${styles.badge}`} style={{ backgroundColor: positions.total_pnl >= 0 ? '#22c55e' : '#ef4444', color: '#fff', alignSelf: 'flex-start' }}>
                            {positions.count} positions • {positions.total_pnl >= 0 ? '+' : ''}${positions.total_pnl.toFixed(2)}
                        </span>
                    ) : null}
                </div>

                <div className={styles.cardBody} style={positionsMaximized ? { flex: 1, overflow: 'auto' } : {}}>
                    {/* SIM MODE */}
                    {isSimMode ? (
                        simPositions?.positions && simPositions.positions.length > 0 ? (
                            <div style={{ overflowX: 'auto', width: '100%' }}>
                                <table className={styles.signalTable}>
                                    <thead>
                                        <tr>
                                            <th>Symbol</th>
                                            <th>Qty</th>
                                            <th>Avg</th>
                                            <th>Value</th>
                                            <th>Stop</th>
                                            <th>P/L%</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {simPositions.positions.map((pos) => (
                                            <tr key={pos.symbol}>
                                                <td className={styles.symbol}>{pos.symbol}</td>
                                                <td>{pos.qty}</td>
                                                <td>${pos.avg_price.toFixed(2)}</td>
                                                <td>${pos.market_value.toFixed(0)}</td>
                                                <td style={{ color: '#f59e0b' }}>${pos.stop_price?.toFixed(2) || '-'}</td>
                                                <td style={{ color: pos.pnl_percent >= 0 ? '#22c55e' : '#ef4444' }}>
                                                    {pos.pnl_percent >= 0 ? '+' : ''}{pos.pnl_percent.toFixed(1)}%
                                                </td>
                                            </tr>
                                        ))}
                                    </tbody>
                                    <tfoot style={{ borderTop: '2px solid #374151' }}>
                                        <tr style={{ fontWeight: 600 }}>
                                            <td style={{ color: '#9ca3af' }}>TOTAL ({simPositions.positions.length})</td>
                                            <td colSpan={2} style={{ color: '#9ca3af' }}>Cost Basis: ${simPositions.positions.reduce((sum, p) => sum + (p.qty * p.avg_price), 0).toFixed(0)}</td>
                                            <td>${simPositions.positions.reduce((sum, p) => sum + p.market_value, 0).toFixed(0)}</td>
                                            <td></td>
                                            <td style={{ color: (simPositions.account?.unrealized_pnl ?? 0) >= 0 ? '#22c55e' : '#ef4444' }}>
                                                {(simPositions.account?.unrealized_pnl ?? 0) >= 0 ? '+' : ''}{((simPositions.account?.unrealized_pnl || 0) / (simPositions.positions.reduce((sum, p) => sum + p.market_value, 0) - (simPositions.account?.unrealized_pnl || 0)) * 100).toFixed(1)}%
                                            </td>
                                        </tr>
                                    </tfoot>
                                </table>
                                {simPositions.account && (
                                    <div style={{ marginTop: '12px', padding: '8px 12px', backgroundColor: 'rgba(139,92,246,0.1)', borderRadius: '6px', display: 'flex', justifyContent: 'space-between' }}>
                                        <span style={{ color: '#a78bfa' }}>Cash: <strong>${simPositions.account.cash?.toFixed(0)}</strong></span>
                                        <span style={{ color: '#a78bfa' }}>Portfolio: <strong>${simPositions.account.portfolio_value?.toFixed(0)}</strong></span>
                                    </div>
                                )}
                            </div>
                        ) : (
                            <div className={styles.emptySignals}>
                                <p>No sim positions yet</p>
                                <span className={styles.emptyHint}>
                                    Start scheduler in sim mode to execute mock trades.
                                </span>
                            </div>
                        )
                    ) : (
                        /* LIVE MODE */
                        positions?.positions && positions.positions.length > 0 ? (
                            <div className={`${styles.scrollableTable} ${positionsMaximized ? styles.scrollableTableMaximized : ''}`} style={{
                                overflowX: 'auto',
                                maxHeight: positionsMaximized ? 'calc(100vh - 200px)' : '300px',
                                overflowY: positionsMaximized ? 'scroll' : 'auto',
                                width: '100%',
                            }}>
                                <table className={styles.signalTable} style={positionsMaximized ? { width: '100%', tableLayout: 'fixed' } : {}}>
                                    <thead style={{ position: 'sticky', top: 0, backgroundColor: '#1f2937', zIndex: 10 }}>
                                        <tr>
                                            {displayColumns.map(col => (
                                                <th
                                                    key={col.id}
                                                    onClick={() => handleSort(col.id)}
                                                    style={{ cursor: 'pointer', userSelect: 'none' }}
                                                    title={`Sort by ${col.label}`}
                                                >
                                                    {col.label}
                                                    {positionSort.column === col.id && (
                                                        <span style={{ marginLeft: '4px' }}>
                                                            {positionSort.direction === 'desc' ? '▼' : '▲'}
                                                        </span>
                                                    )}
                                                </th>
                                            ))}
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {sortPositions(positions.positions).map((pos) => (
                                            <tr key={pos.symbol}>
                                                {displayColumns.map((col) => renderCellValue(pos, col.id))}
                                            </tr>
                                        ))}
                                    </tbody>
                                    <tfoot style={{ borderTop: '2px solid #374151', position: 'sticky', bottom: 0, backgroundColor: '#1f2937' }}>
                                        <tr style={{ fontWeight: 600 }}>
                                            {displayColumns.map((col) => renderTotalCell(col.id))}
                                        </tr>
                                    </tfoot>
                                </table>
                                <div style={{ marginTop: '12px', padding: '8px 12px', backgroundColor: 'rgba(255,255,255,0.03)', borderRadius: '6px', display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: '8px' }}>
                                    <span style={{ color: '#9ca3af' }}>Total Value: <strong>${positions.total_value.toFixed(0)}</strong></span>
                                    <span style={{ color: positions.total_pnl >= 0 ? '#22c55e' : '#ef4444' }}>
                                        Total P&L ($): <strong>{positions.total_pnl >= 0 ? '+' : ''}${positions.total_pnl.toFixed(2)}</strong>
                                    </span>
                                    <span style={{ color: positions.total_value > 0 ? (positions.total_pnl >= 0 ? '#22c55e' : '#ef4444') : '#9ca3af' }}>
                                        Total P&L (%): <strong>{positions.total_value > 0 ? `${positions.total_pnl >= 0 ? '+' : ''}${((positions.total_pnl / (positions.total_value - positions.total_pnl)) * 100).toFixed(2)}%` : '0.00%'}</strong>
                                    </span>
                                </div>
                            </div>
                        ) : (
                            <div className={styles.emptySignals}>
                                <p>No open positions</p>
                                <span className={styles.emptyHint}>
                                    Positions opened via automation will appear here.
                                </span>
                            </div>
                        )
                    )}
                </div>
            </div>
        </>
    )
}
