import styles from '@/styles/Automation.module.css'
import { ApiStats } from '@/types/automation'

interface ApiUsageCardProps {
    apiStats: ApiStats | null
}

export default function ApiUsageCard({ apiStats }: ApiUsageCardProps) {
    const usagePercent = apiStats?.usage_percent || 0

    return (
        <div className={styles.card}>
            <div className={styles.cardHeader}>
                <h2>📡 API Usage</h2>
                <span className={`${styles.statusBadge} ${usagePercent > 80 ? styles.statusPaused :
                    usagePercent > 50 ? styles.statusRunning : styles.statusStopped
                    }`}>
                    {usagePercent}%
                </span>
            </div>
            <div className={styles.cardBody}>
                <div className={styles.usageBar}>
                    <div
                        className={styles.usageProgress}
                        style={{
                            width: `${Math.min(usagePercent, 100)}%`,
                            background: usagePercent > 80 ? '#ff6b6b' :
                                usagePercent > 50 ? '#ffc800' : '#00ff88'
                        }}
                    />
                </div>
                <div className={styles.stat}>
                    <span>Calls/min:</span>
                    <strong>{apiStats?.calls_this_minute || 0} / {apiStats?.limit_per_minute || 300}</strong>
                </div>
                <div className={styles.stat}>
                    <span>Remaining:</span>
                    <strong style={{ color: (apiStats?.remaining || 300) < 50 ? '#ff6b6b' : undefined }}>
                        {apiStats?.remaining ?? 300}
                    </strong>
                </div>
                <div className={styles.stat}>
                    <span>Provider:</span>
                    <strong>{apiStats?.provider || 'FMP'}</strong>
                </div>
            </div>
        </div>
    )
}
