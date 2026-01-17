/**
 * QualityIndicator Component
 * 
 * Displays traffic light indicators (🟢🟡🔴) for Warrior Trading quality criteria.
 * Each dot has a tooltip showing the actual value on hover.
 */

import React from 'react'
import styles from '@/styles/Warrior.module.css'

interface Indicator {
  name: string
  status: 'green' | 'yellow' | 'red' | 'gray'
  value: number
  tooltip: string
}

interface QualityIndicatorProps {
  indicators: Record<string, Indicator>
  compact?: boolean  // Show only dots without labels
}

export function QualityIndicator({ indicators, compact = true }: QualityIndicatorProps) {
  if (!indicators) return null
  
  const indicatorList = Object.values(indicators)
  
  return (
    <div className={styles.indicatorRow}>
      {indicatorList.map((ind) => (
        <span
          key={ind.name}
          className={`${styles.indicatorDot} ${styles[`dot${ind.status.charAt(0).toUpperCase()}${ind.status.slice(1)}`]}`}
          title={ind.tooltip}
        >
          ●
        </span>
      ))}
    </div>
  )
}

export default QualityIndicator
