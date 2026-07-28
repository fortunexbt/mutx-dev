import Link from 'next/link'
import { ArrowRight } from 'lucide-react'
import { useTranslations } from 'next-intl'

import styles from './AuthNav.module.css'

type AuthNavProps = { hostVariant?: 'default' | 'pico' }

const accountLinks = [
  { href: '/ai-agent-control-plane', label: 'Product' },
  { href: '/docs', label: 'Docs' },
  { href: '/dashboard', label: 'Dashboard' },
] as const

export const PICO_AUTH_CROSS_HOST_LINKS = [
  { href: 'https://mutx.dev/releases', labelKey: 'releases' },
  { href: 'https://mutx.dev/docs', labelKey: 'docs' },
  { href: 'https://app.mutx.dev', labelKey: 'dashboard' },
] as const

export function AuthNav({ hostVariant = 'default' }: AuthNavProps) {
  const isPico = hostVariant === 'pico'
  const picoAuthT = useTranslations('pico.auth')
  const picoFooterT = useTranslations('pico.footer.links')
  const picoNavT = useTranslations('pico.nav')
  const visibleLinks = isPico
    ? PICO_AUTH_CROSS_HOST_LINKS.map((link) => ({
        href: link.href,
        label: picoFooterT(link.labelKey),
      }))
    : accountLinks

  return (
    <header className={styles.header} data-testid="public-auth-nav">
      <nav className={styles.nav} aria-label={isPico ? picoAuthT('eyebrow') : 'Account navigation'}>
        <Link href="/" className={styles.brand} aria-label="MUTX home">
          <span className={styles.mark} aria-hidden="true">{isPico ? 'PX' : 'MX'}</span>
          <span className={styles.brandCopy}>
            <strong>{isPico ? 'Pico / MUTX' : 'MUTX'}</strong>
            <small>{isPico ? picoAuthT('eyebrow') : 'Identity checkpoint'}</small>
          </span>
        </Link>

        <div className={styles.links}>
          {visibleLinks.map((link) => (
            <Link key={link.href} href={link.href}>{link.label}</Link>
          ))}
        </div>

        <Link href={isPico ? '/onboarding' : '/download'} className={styles.action}>
          {isPico ? picoNavT('cta') : 'Download'}
          <ArrowRight className={styles.directionalIcon} aria-hidden="true" />
        </Link>
      </nav>
    </header>
  )
}
