/**
 * TradingModeCard - Simulation/Broker mode with account stats and controls
 */
import styles from '@/styles/Warrior.module.css'
import { CollapsibleCard } from './CollapsibleCard'
import { formatCurrency, formatPnL } from './formatters'

interface SimPosition {
    symbol: string
    qty: number
    avg_price: number
    unrealized_pnl: number
}

interface SimAccount {
    cash: number
    portfolio_value: number
    unrealized_pnl: number
    realized_pnl: number
    max_capital_deployed?: number
    max_shares_held?: number
}

interface SimStatus {
    sim_enabled?: boolean
    account?: SimAccount
    positions?: SimPosition[]
    position_count?: number
}

interface BrokerStatus {
    broker_enabled?: boolean
}

interface TradingModeCardProps {
    simStatus?: SimStatus | null
    brokerStatus?: BrokerStatus | null
    autoEnable?: boolean
    actionLoading: string | null
    enableSim: () => void
    disableSim: () => void
    resetSim: () => void
    enableBroker: () => void
    toggleAutoEnable: () => void
}

export function TradingModeCard({
    simStatus,
    brokerStatus,
    autoEnable,
    actionLoading,
    enableSim,
    disableSim,
    resetSim,
    enableBroker,
    toggleAutoEnable,
}: TradingModeCardProps) {
    return (
        <CollapsibleCard
            id="simulation"
            title="🧪 Trading Mode"
            badge={
                <>
                    {brokerStatus?.broker_enabled && (
                        <span className={`${styles.badge} ${styles.badgeBlue}`} style={{ marginRight: '4px' }}>
                            📈 Broker
                        </span>
                    )}
                    <span className={`${styles.badge} ${simStatus?.sim_enabled ? styles.badgeGreen : styles.badgeGray}`}>
                        {simStatus?.sim_enabled ? '🧪 Sim' : 'Off'}
                    </span>
                </>
            }
        >
            <div className={styles.cardBody}>
                {simStatus?.sim_enabled && simStatus.account ? (
                    <>
                        <div className={styles.statsGrid}>
                            <div className={styles.statBox}>
                                <div className={styles.statValue}>{formatCurrency(simStatus.account.cash)}</div>
                                <div className={styles.statLabel}>Cash</div>
                            </div>
                            <div className={styles.statBox}>
                                <div className={styles.statValue}>{formatCurrency(simStatus.account.portfolio_value)}</div>
                                <div className={styles.statLabel}>Equity</div>
                            </div>
                            <div className={styles.statBox}>
                                <div className={`${styles.statValue} ${simStatus.account.unrealized_pnl >= 0 ? styles.pnlPositive : styles.pnlNegative}`}>
                                    {formatPnL(simStatus.account.unrealized_pnl)}
                                </div>
                                <div className={styles.statLabel}>Unrealized</div>
                            </div>
                            <div className={styles.statBox}>
                                <div className={`${styles.statValue} ${simStatus.account.realized_pnl >= 0 ? styles.pnlPositive : styles.pnlNegative}`}>
                                    {formatPnL(simStatus.account.realized_pnl)}
                                </div>
                                <div className={styles.statLabel}>Realized</div>
                            </div>
                        </div>

                        {/* Capital metrics for scaling analysis */}
                        <div className={styles.statsGrid} style={{ marginTop: '8px' }}>
                            <div className={styles.statBox}>
                                <div className={styles.statValue} style={{ color: '#60a5fa' }}>
                                    {formatCurrency(simStatus.account.max_capital_deployed || 0)}
                                </div>
                                <div className={styles.statLabel}>Max Capital</div>
                            </div>
                            <div className={styles.statBox}>
                                <div className={styles.statValue} style={{ color: '#60a5fa' }}>
                                    {simStatus.account.max_shares_held || 0}
                                </div>
                                <div className={styles.statLabel}>Max Shares</div>
                            </div>
                        </div>

                        {simStatus.positions && simStatus.positions.length > 0 && (
                            <div className={styles.simPositions}>
                                <h4>Sim Positions ({simStatus.position_count})</h4>
                                <table>
                                    <thead>
                                        <tr>
                                            <th>Symbol</th>
                                            <th>Qty</th>
                                            <th>Avg</th>
                                            <th>P&L</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {simStatus.positions.map((p) => (
                                            <tr key={p.symbol}>
                                                <td className={styles.symbol}>{p.symbol}</td>
                                                <td>{p.qty}</td>
                                                <td>${p.avg_price.toFixed(2)}</td>
                                                <td className={p.unrealized_pnl >= 0 ? styles.pnlPositive : styles.pnlNegative}>
                                                    {formatPnL(p.unrealized_pnl)}
                                                </td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        )}
                    </>
                ) : (
                    <p className={styles.emptyMessage}>Simulation not active. Click Enable to start.</p>
                )}

                {/* Auto-enable on startup toggle */}
                <div style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    padding: '10px 0',
                    borderTop: '1px solid rgba(255,255,255,0.1)',
                    marginTop: '12px'
                }}>
                    <div>
                        <span style={{ color: '#e5e7eb' }}>Auto-start on restart</span>
                        <span style={{ color: '#9ca3af', fontSize: '0.8em', marginLeft: '8px' }}>
                            (Wire broker on server startup)
                        </span>
                    </div>
                    <button
                        onClick={toggleAutoEnable}
                        className={autoEnable ? styles.btnSuccess : styles.btnSecondary}
                        disabled={actionLoading === 'autoEnable'}
                        style={{ padding: '4px 12px', fontSize: '0.9em' }}
                    >
                        {actionLoading === 'autoEnable' ? '...' : (autoEnable ? '✅ ON' : '❌ OFF')}
                    </button>
                </div>
            </div>
            <div className={styles.cardActions}>
                {!simStatus?.sim_enabled ? (
                    <>
                        <button
                            onClick={enableSim}
                            className={styles.btnPrimary}
                            disabled={actionLoading !== null}
                        >
                            {actionLoading === 'Enable Sim' ? '...' : '🚀 Enable Sim'}
                        </button>
                        <button
                            onClick={enableBroker}
                            className={styles.btnSuccess}
                            disabled={actionLoading !== null}
                            title="Enable Alpaca Paper for live trading"
                        >
                            {actionLoading === 'Enable Broker' ? '...' : '📈 Enable Broker'}
                        </button>
                    </>
                ) : (
                    <>
                        <button
                            onClick={resetSim}
                            className={styles.btnSecondary}
                            disabled={actionLoading !== null}
                        >
                            {actionLoading === 'Reset Sim' ? '...' : '🔄 Reset Sim'}
                        </button>
                        <button
                            onClick={disableSim}
                            className={styles.btnDanger}
                            disabled={actionLoading !== null}
                        >
                            {actionLoading === 'Disable Sim' ? '...' : '🛑 Disable Sim'}
                        </button>
                    </>
                )}
            </div>
        </CollapsibleCard>
    )
}
