import Link from 'next/link';
import { useRouter } from 'next/router';
import styles from '@/styles/Navbar.module.css';

interface NavItem {
    label: string;
    href: string;
    icon?: string;
}

const navItems: NavItem[] = [
    { label: 'Dashboard', href: '/', icon: '📊' },
    { label: 'NAC', href: '/automation', icon: '🤖' },
    { label: 'Warrior', href: '/warrior', icon: '⚔️' },
    { label: 'Scanner', href: '/scanner', icon: '🔍' },
    { label: 'Analytics', href: '/analytics', icon: '📈' },
    { label: 'Simulation', href: '/simulation', icon: '🧪' },
];

export default function Navbar() {
    const router = useRouter();

    return (
        <nav className={styles.navbar}>
            <div className={styles.brand}>
                <span className={styles.logo}>⚡</span>
                <span className={styles.title}>Nexus 2</span>
            </div>

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

            <div className={styles.navSecondary}>
                <Link href="/orders" className={`${styles.navLink} ${styles.secondary} ${router.pathname === '/orders' ? styles.active : ''}`}>
                    Orders
                </Link>
                <Link href="/closed" className={`${styles.navLink} ${styles.secondary} ${router.pathname === '/closed' ? styles.active : ''}`}>
                    Closed
                </Link>
                <Link href="/docs" className={`${styles.navLink} ${styles.secondary} ${router.pathname === '/docs' ? styles.active : ''}`}>
                    Docs
                </Link>
            </div>
        </nav>
    );
}
