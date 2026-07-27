import Link from 'next/link'
import { ArrowRight } from 'lucide-react'

import styles from './AuthNav.module.css'

type AuthNavProps = { hostVariant?: 'default' | 'pico' }

const accountLinks = [
  { href: '/ai-agent-control-plane', label: 'Product' },
  { href: '/docs', label: 'Docs' },
  { href: '/dashboard', label: 'Dashboard' },
] as const

export function AuthNav({ hostVariant = 'default' }: AuthNavProps) {
  const isPico = hostVariant === 'pico'

  return (
    <header className={styles.header} data-testid="public-auth-nav">
      <nav className={styles.nav} aria-label="Account navigation">
        <Link href="/" className={styles.brand} aria-label="MUTX home">
          <span className={styles.mark} aria-hidden="true">{isPico ? 'PX' : 'MX'}</span>
          <span className={styles.brandCopy}>
            <strong>{isPico ? 'Pico / MUTX' : 'MUTX'}</strong>
            <small>Identity checkpoint</small>
          </span>
        </Link>

        <div className={styles.links}>
          {accountLinks.map((link) => (
            <Link key={link.href} href={link.href}>{link.label}</Link>
          ))}
        </div>

        <Link href={isPico ? '/pico' : '/download'} className={styles.action}>
          {isPico ? 'Pico access' : 'Download'}
          <ArrowRight aria-hidden="true" />
        </Link>
      </nav>
    </header>
  )
}
