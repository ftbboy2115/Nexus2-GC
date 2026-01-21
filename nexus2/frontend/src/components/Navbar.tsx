import Link from 'next/link';
import { useRouter } from 'next/router';
import { useState, useEffect } from 'react';
import styles from '@/styles/Navbar.module.css';

interface NavItem {
    label: string;
    href: string;
    icon?: string;
}

interface Settings {
    broker_type: string;
    active_account: string;
    trading_mode: string;
}

interface HealthStatus {
    status: string;
    version: string;
    mode: string;
}

const navItems: NavItem[] = [
    { label: 'Dashboard', href: '/', icon: '📊' },
    { label: 'NAC', href: '/automation', icon: '🤖' },
    { label: 'Warrior', href: '/warrior', icon: '⚔️' },
    { label: 'Scanner', href: '/scanner', icon: '🔍' },
    { label: 'Analytics', href: '/analytics', icon: '📈' },
    { label: 'Simulation', href: '/simulation', icon: '🧪' },
    { label: 'Lab', href: '/lab', icon: '🔬' },
];

const secondaryItems: NavItem[] = [
    { label: 'Orders', href: '/orders' },
    { label: 'Closed', href: '/closed' },
    { label: 'Docs', href: '/docs' },
];

export default function Navbar() {
    const router = useRouter();
    const [settings, setSettings] = useState<Settings | null>(null);
    const [health, setHealth] = useState<HealthStatus | null>(null);
    const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

    useEffect(() => {
        async function fetchData() {
            try {
                const [settingsRes, healthRes] = await Promise.all([
                    fetch('/api/settings'),
                    fetch('/api/health')
                ]);
                if (settingsRes.ok) setSettings(await settingsRes.json());
                if (healthRes.ok) setHealth(await healthRes.json());
            } catch (err) {
                console.error('Navbar fetch error:', err);
            }
        }
        fetchData();
    }, []);

    // Close menu on route change
    useEffect(() => {
        setMobileMenuOpen(false);
    }, [router.pathname]);

    const updateSettings = async (updates: Partial<Settings>) => {
        try {
            const response = await fetch('/api/settings', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(updates),
            });
            if (response.ok) {
                setSettings(await response.json());
            }
        } catch (err) {
            console.error('Failed to update settings:', err);
        }
    };

    return (
        <nav className={styles.navbar}>
            <div className={styles.brand}>
                <span className={styles.logo}>⚡</span>
                <span className={styles.title}>Nexus 2</span>
            </div>

            {/* Hamburger button - visible on mobile */}
            <button
                className={styles.hamburger}
                onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
                aria-label="Toggle menu"
            >
                <span className={mobileMenuOpen ? styles.hamburgerOpen : ''}></span>
            </button>

            {/* Desktop nav links */}
            <div className={styles.navLinks}>
                {navItems.map((item) => (
                    <Link
                        key={item.href}
                        href={item.href}
                        className={`${styles.navLink} ${router.pathname === item.href ? styles.active : ''}`}
                    >
                        <span className={styles.navIcon}>{item.icon}</span>
                        <span className={styles.navLabel}>{item.label}</span>
                    </Link>
                ))}
            </div>

            <div className={styles.navControls}>
                {settings && (
                    <>
                        {settings.broker_type.startsWith('alpaca') && (
                            <select
                                className={styles.controlSelect}
                                value={settings.active_account}
                                onChange={(e) => updateSettings({ active_account: e.target.value })}
                                title="Switch Alpaca Account"
                            >
                                <option value="A">Acct A</option>
                                <option value="B">Acct B</option>
                            </select>
                        )}
                        <select
                            className={styles.controlSelect}
                            value={settings.broker_type}
                            onChange={(e) => updateSettings({ broker_type: e.target.value })}
                            title="Broker Type"
                        >
                            <option value="paper">📄 Paper</option>
                            <option value="alpaca_paper">🅰️ Alpaca</option>
                        </select>
                    </>
                )}
                {health && (
                    <div className={styles.status}>
                        <span className={styles.statusDot} data-status={health.status}></span>
                        <span className={styles.statusText}>{settings?.trading_mode || health.mode}</span>
                    </div>
                )}
                <button
                    className={styles.settingsBtn}
                    onClick={() => window.dispatchEvent(new CustomEvent('openSettings'))}
                    title="Settings"
                >
                    ⚙️
                </button>
            </div>

            <div className={styles.navSecondary}>
                {secondaryItems.map((item) => (
                    <Link
                        key={item.href}
                        href={item.href}
                        className={`${styles.navLink} ${styles.secondary} ${router.pathname === item.href ? styles.active : ''}`}
                    >
                        {item.label}
                    </Link>
                ))}
            </div>

            {/* Mobile menu overlay */}
            {mobileMenuOpen && (
                <div className={styles.mobileMenu}>
                    <div className={styles.mobileMenuContent}>
                        {navItems.map((item) => (
                            <Link
                                key={item.href}
                                href={item.href}
                                className={`${styles.mobileLink} ${router.pathname === item.href ? styles.active : ''}`}
                            >
                                <span>{item.icon}</span>
                                <span>{item.label}</span>
                            </Link>
                        ))}
                        <div className={styles.mobileDivider}></div>
                        {secondaryItems.map((item) => (
                            <Link
                                key={item.href}
                                href={item.href}
                                className={`${styles.mobileLink} ${styles.secondary} ${router.pathname === item.href ? styles.active : ''}`}
                            >
                                {item.label}
                            </Link>
                        ))}
                    </div>
                </div>
            )}
        </nav>
    );
}
