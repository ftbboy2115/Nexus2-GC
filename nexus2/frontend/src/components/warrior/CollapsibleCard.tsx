/**
 * Collapsible Card Component
 * Reusable card with localStorage persistence for collapsed state
 */
import { useState } from 'react'
import styles from '@/styles/Warrior.module.css'
import type { CollapsibleCardProps } from './types'

const getCollapsedState = (): Record<string, boolean> => {
    if (typeof window !== 'undefined') {
        try {
            const saved = localStorage.getItem('warrior-collapsed-cards')
            return saved ? JSON.parse(saved) : {}
        } catch {
            return {}
        }
    }
    return {}
}

const setCollapsedState = (cardId: string, collapsed: boolean) => {
    if (typeof window !== 'undefined') {
        const current = getCollapsedState()
        current[cardId] = collapsed
        localStorage.setItem('warrior-collapsed-cards', JSON.stringify(current))
    }
}

export function CollapsibleCard({ id, title, badge, children, defaultCollapsed = false }: CollapsibleCardProps) {
    const [collapsed, setCollapsed] = useState(() => {
        const saved = getCollapsedState()
        return saved[id] ?? defaultCollapsed
    })

    const toggle = () => {
        const newState = !collapsed
        setCollapsed(newState)
        setCollapsedState(id, newState)
    }

    return (
        <div className={styles.card}>
            <div
                className={styles.cardHeader}
                onClick={toggle}
                style={{
                    cursor: 'pointer',
                    borderBottom: collapsed ? 'none' : undefined
                }}
            >
                <h2>{title}</h2>
                <div className={styles.headerRight}>
                    {badge}
                    <span className={styles.collapseToggle}>{collapsed ? '▶' : '▼'}</span>
                </div>
            </div>
            {!collapsed && children}
        </div>
    )
}
