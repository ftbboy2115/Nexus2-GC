import styles from '@/styles/Automation.module.css'
import { ScannerSettings, PRESET_MODES } from '@/types/automation'

interface QuickActionsCardProps {
    scannerSettings: ScannerSettings
    actionLoading: string | null
    onUpdateSettings: (settings: ScannerSettings) => void
    onRunScan: () => void
    onDryRun: () => void
    onCheckPositions: () => void
    onLiquidateAll: () => void
}

export default function QuickActionsCard({
    scannerSettings,
    actionLoading,
    onUpdateSettings,
    onRunScan,
    onDryRun,
    onCheckPositions,
    onLiquidateAll,
}: QuickActionsCardProps) {
    return (
        <div className={`${styles.card} ${styles.actionsCard}`}>
            <div className={styles.cardHeader}>
                <h2>🎯 Quick Actions</h2>
            </div>
            <div className={styles.cardBody}>
                {/* Scanner Settings */}
                <div className={styles.scannerSettings}>
                    <div className={styles.presetButtons}>
                        <button
                            className={`${styles.presetBtn} ${scannerSettings.preset === 'strict' ? styles.presetActive : ''}`}
                            onClick={() => onUpdateSettings(PRESET_MODES.strict)}
                            title="KK-style: Quality ≥7, Stop ≤5%"
                        >
                            🎯 Strict
                        </button>
                        <button
                            className={`${styles.presetBtn} ${scannerSettings.preset === 'relaxed' ? styles.presetActive : ''}`}
                            onClick={() => onUpdateSettings(PRESET_MODES.relaxed)}
                            title="Relaxed: Quality ≥5, Stop ≤8%"
                        >
                            🔓 Relaxed
                        </button>
                        <button
                            className={`${styles.presetBtn} ${scannerSettings.preset === 'custom' ? styles.presetActive : ''}`}
                            onClick={() => onUpdateSettings({ ...scannerSettings, preset: 'custom' })}
                            title="Custom settings"
                        >
                            ⚙️ Custom
                        </button>
                    </div>
                    {scannerSettings.preset === 'custom' && (
                        <div className={styles.customSettings}>
                            <div className={styles.settingRow}>
                                <label>Min Quality: {scannerSettings.minQuality}</label>
                                <input
                                    type="range"
                                    min="1"
                                    max="10"
                                    value={scannerSettings.minQuality}
                                    onChange={(e) => onUpdateSettings({
                                        ...scannerSettings,
                                        minQuality: parseInt(e.target.value)
                                    })}
                                />
                            </div>
                            <div className={styles.settingRow}>
                                <label>Stop Filter:</label>
                                <div className={styles.toggleButtons}>
                                    <button
                                        className={`${styles.toggleBtn} ${scannerSettings.stopMode === 'atr' ? styles.toggleActive : ''}`}
                                        onClick={() => onUpdateSettings({ ...scannerSettings, stopMode: 'atr' })}
                                        title="KK-style: Stop distance in ATR units"
                                    >
                                        ATR
                                    </button>
                                    <button
                                        className={`${styles.toggleBtn} ${scannerSettings.stopMode === 'percent' ? styles.toggleActive : ''}`}
                                        onClick={() => onUpdateSettings({ ...scannerSettings, stopMode: 'percent' })}
                                        title="Simple percentage-based stop filter"
                                    >
                                        %
                                    </button>
                                </div>
                            </div>
                            {scannerSettings.stopMode === 'atr' ? (
                                <div className={styles.settingRow}>
                                    <label>Max Stop: {scannerSettings.maxStopAtr} ATR</label>
                                    <input
                                        type="range"
                                        min="0.5"
                                        max="3"
                                        step="0.1"
                                        value={scannerSettings.maxStopAtr}
                                        onChange={(e) => onUpdateSettings({
                                            ...scannerSettings,
                                            maxStopAtr: parseFloat(e.target.value)
                                        })}
                                    />
                                </div>
                            ) : (
                                <div className={styles.settingRow}>
                                    <label>Max Stop: {scannerSettings.maxStopPercent}%</label>
                                    <input
                                        type="range"
                                        min="1"
                                        max="15"
                                        value={scannerSettings.maxStopPercent}
                                        onChange={(e) => onUpdateSettings({
                                            ...scannerSettings,
                                            maxStopPercent: parseInt(e.target.value)
                                        })}
                                    />
                                </div>
                            )}
                        </div>
                    )}
                    <div className={styles.currentSettings}>
                        Quality ≥{scannerSettings.minQuality} • Stop ≤{scannerSettings.stopMode === 'atr'
                            ? `${scannerSettings.maxStopAtr} ATR`
                            : `${scannerSettings.maxStopPercent}%`}
                    </div>

                    {/* Scanner Mode Selection */}
                    <div style={{ marginTop: '12px', padding: '10px', backgroundColor: 'rgba(255,255,255,0.03)', borderRadius: '6px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '16px', flexWrap: 'wrap' }}>
                            <span style={{ fontSize: '12px', color: '#9ca3af' }}>Scanners:</span>
                            <span style={{ fontSize: '12px', color: '#22c55e' }}>✓ EP</span>
                            <span style={{ fontSize: '12px', color: '#22c55e' }}>✓ Breakout</span>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                                <span style={{ fontSize: '12px', color: '#9ca3af' }}>HTF:</span>
                                <select
                                    value={scannerSettings.scanModes?.includes('htf')
                                        ? (scannerSettings.htfFrequency || 'market_open')
                                        : 'off'}
                                    onChange={(e) => {
                                        const val = e.target.value
                                        if (val === 'off') {
                                            const newModes = (scannerSettings.scanModes || ['ep', 'breakout']).filter(m => m !== 'htf')
                                            onUpdateSettings({ ...scannerSettings, scanModes: newModes, preset: 'custom' })
                                        } else {
                                            const currentModes = scannerSettings.scanModes || ['ep', 'breakout']
                                            const newModes = currentModes.includes('htf') ? currentModes : [...currentModes, 'htf']
                                            onUpdateSettings({
                                                ...scannerSettings,
                                                scanModes: newModes,
                                                htfFrequency: val as 'every_cycle' | 'market_open',
                                                preset: 'custom'
                                            })
                                        }
                                    }}
                                    style={{ padding: '4px 8px', fontSize: '12px', borderRadius: '4px', backgroundColor: '#1f2937', border: '1px solid #374151', color: '#fff' }}
                                >
                                    <option value="off">Off</option>
                                    <option value="market_open">Once/day (9am)</option>
                                    <option value="every_cycle">Every cycle</option>
                                </select>
                            </div>
                        </div>
                    </div>
                </div>

                <div className={styles.actionButtons}>
                    <button
                        onClick={onRunScan}
                        className={styles.btnSecondary}
                        disabled={actionLoading === 'scan'}
                        title={`Run EP, Breakout, and HTF scanners with current settings (Quality ≥${scannerSettings.minQuality}, Stop ≤${scannerSettings.maxStopPercent}%)`}
                    >
                        {actionLoading === 'scan' ? '...' : '🔍 Run Scan (All)'}
                    </button>
                    <button
                        onClick={onDryRun}
                        className={styles.btnSecondary}
                        disabled={actionLoading === 'dry-run'}
                        title="[Not implemented yet] Will scan for signals AND simulate execution"
                    >
                        {actionLoading === 'dry-run' ? '...' : '🧪 Dry Run'}
                    </button>
                    <button
                        onClick={onCheckPositions}
                        className={styles.btnSecondary}
                        disabled={actionLoading === 'check'}
                        title="Check all open positions against their stops"
                    >
                        {actionLoading === 'check' ? '...' : '🔎 Check Positions'}
                    </button>
                    <button
                        onClick={onLiquidateAll}
                        className={styles.btnDanger}
                        disabled={actionLoading === 'liquidate'}
                        title="Sell all open positions with market orders"
                    >
                        {actionLoading === 'liquidate' ? '...' : '💥 Liquidate All'}
                    </button>
                </div>
            </div>
        </div>
    )
}
