/**
 * SettingsCard - Config settings with numeric controls and toggles
 */
import styles from '@/styles/Warrior.module.css'
import { CollapsibleCard } from './CollapsibleCard'

interface WarriorConfig {
    max_candidates?: number
    scanner_interval_minutes?: number
    risk_per_trade?: number
    max_positions?: number
    max_shares_per_trade?: number
    orb_enabled?: boolean
    pmh_enabled?: boolean
}

interface SettingsCardProps {
    config?: WarriorConfig
    updateConfig: (key: string, value: number | boolean) => void
}

export function SettingsCard({ config, updateConfig }: SettingsCardProps) {
    return (
        <CollapsibleCard id="settings" title="⚙️ Settings">
            <div className={styles.cardBody}>
                <div className={styles.settingsGrid}>
                    <div className={styles.settingItem}>
                        <label>Max Candidates</label>
                        <div className={styles.settingControl}>
                            <button
                                onClick={() => updateConfig('max_candidates', Math.max(1, (config?.max_candidates || 5) - 1))}
                                className={styles.btnSmall}
                            >-</button>
                            <span>{config?.max_candidates || 5}</span>
                            <button
                                onClick={() => updateConfig('max_candidates', Math.min(20, (config?.max_candidates || 5) + 1))}
                                className={styles.btnSmall}
                            >+</button>
                        </div>
                    </div>
                    <div className={styles.settingItem}>
                        <label>Scan Interval (min)</label>
                        <div className={styles.settingControl}>
                            <button
                                onClick={() => updateConfig('scanner_interval_minutes', Math.max(1, (config?.scanner_interval_minutes || 5) - 1))}
                                className={styles.btnSmall}
                            >-</button>
                            <span>{config?.scanner_interval_minutes || 5}</span>
                            <button
                                onClick={() => updateConfig('scanner_interval_minutes', Math.min(30, (config?.scanner_interval_minutes || 5) + 1))}
                                className={styles.btnSmall}
                            >+</button>
                        </div>
                    </div>
                    <div className={styles.settingItem}>
                        <label>Risk/Trade ($)</label>
                        <div className={styles.settingControl}>
                            <button
                                onClick={() => updateConfig('risk_per_trade', Math.max(25, (config?.risk_per_trade || 100) - 25))}
                                className={styles.btnSmall}
                            >-</button>
                            <span>${config?.risk_per_trade || 100}</span>
                            <button
                                onClick={() => updateConfig('risk_per_trade', Math.min(500, (config?.risk_per_trade || 100) + 25))}
                                className={styles.btnSmall}
                            >+</button>
                        </div>
                    </div>
                    <div className={styles.settingItem}>
                        <label>Max Positions</label>
                        <div className={styles.settingControl}>
                            <button
                                onClick={() => updateConfig('max_positions', Math.max(1, (config?.max_positions || 3) - 1))}
                                className={styles.btnSmall}
                            >-</button>
                            <span>{config?.max_positions || 3}</span>
                            <button
                                onClick={() => updateConfig('max_positions', Math.min(20, (config?.max_positions || 3) + 1))}
                                className={styles.btnSmall}
                            >+</button>
                        </div>
                    </div>
                    <div className={styles.settingItem}>
                        <label>Max Shares/Trade</label>
                        <div className={styles.settingControl}>
                            <button
                                onClick={() => updateConfig('max_shares_per_trade', Math.max(10, (config?.max_shares_per_trade || 100) - 10))}
                                className={styles.btnSmall}
                            >-</button>
                            <span>{config?.max_shares_per_trade || 100}</span>
                            <button
                                onClick={() => updateConfig('max_shares_per_trade', Math.min(1000, (config?.max_shares_per_trade || 100) + 10))}
                                className={styles.btnSmall}
                            >+</button>
                        </div>
                    </div>
                </div>

                {/* Entry Mode Toggles */}
                <div className={styles.entryModeToggles}>
                    <button
                        onClick={() => updateConfig('orb_enabled', !config?.orb_enabled)}
                        className={config?.orb_enabled ? styles.btnToggleOn : styles.btnToggleOff}
                    >
                        {config?.orb_enabled ? '✅' : '❌'} ORB
                    </button>
                    <button
                        onClick={() => updateConfig('pmh_enabled', !config?.pmh_enabled)}
                        className={config?.pmh_enabled ? styles.btnToggleOn : styles.btnToggleOff}
                    >
                        {config?.pmh_enabled ? '✅' : '❌'} PMH
                    </button>
                </div>
            </div>
        </CollapsibleCard>
    )
}
