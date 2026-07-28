'use client'

import Image from 'next/image'
import Link from 'next/link'
import { useTranslations } from 'next-intl'
import { usePathname } from 'next/navigation'

import { PicoLangSwitcher } from '@/components/pico/PicoLangSwitcher'
import { picoHref } from '@/lib/pico/navigation'
import { cn } from '@/lib/utils'

const SITE = 'https://mutx.dev'

export function PicoFooter({ className }: { className?: string }) {
  const pathname = usePathname()
  const t = useTranslations('pico.shell.footer')

  return (
    <footer
      data-testid="pico-footer"
      className={cn(
        'border-t border-[color:var(--pico-border)] bg-[color:var(--pico-bg)] px-4 py-8 sm:px-6 lg:px-8',
        className,
      )}
      style={{ fontFamily: 'var(--font-site-body), sans-serif' }}
    >
      <div className="mx-auto max-w-[var(--pico-shell,72rem)]">
        <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
          <Link
            href={picoHref(pathname, '/')}
            className="inline-flex min-h-11 min-w-11 items-center justify-center gap-2 text-sm text-[color:var(--pico-text-secondary)] no-underline transition hover:text-[color:var(--pico-text)]"
          >
            <span className="inline-flex h-6 w-6 items-center justify-center rounded bg-[rgba(var(--pico-accent-rgb),0.1)]">
              <Image src="/pico/logo.png" alt={t('logoAlt')} width={14} height={14} />
            </span>
            PicoMUTX
          </Link>

          <a
            href={`${SITE}/releases`}
            className="inline-flex min-h-11 min-w-11 items-center justify-center text-sm text-[color:var(--pico-text-muted)] no-underline transition hover:text-[color:var(--pico-text-secondary)]"
          >
            {t('links.releases')}
          </a>
          <a
            href={`${SITE}/docs`}
            className="inline-flex min-h-11 min-w-11 items-center justify-center text-sm text-[color:var(--pico-text-muted)] no-underline transition hover:text-[color:var(--pico-text-secondary)]"
          >
            {t('links.docs')}
          </a>
          <a
            href="https://github.com/mutx-dev/mutx-dev"
            className="inline-flex min-h-11 min-w-11 items-center justify-center text-sm text-[color:var(--pico-text-muted)] no-underline transition hover:text-[color:var(--pico-text-secondary)]"
          >
            {t('links.github')}
          </a>
          <a
            href={`${SITE}/download`}
            className="inline-flex min-h-11 min-w-11 items-center justify-center text-sm text-[color:var(--pico-text-muted)] no-underline transition hover:text-[color:var(--pico-text-secondary)]"
          >
            {t('links.download')}
          </a>
          <a
            href={`${SITE}/privacy-policy`}
            className="inline-flex min-h-11 min-w-11 items-center justify-center text-sm text-[color:var(--pico-text-muted)] no-underline transition hover:text-[color:var(--pico-text-secondary)]"
          >
            {t('links.privacy')}
          </a>
          <span className="ms-auto max-w-full">
            <PicoLangSwitcher />
          </span>
        </div>

        <p className="mt-5 text-xs leading-5 text-[color:var(--pico-text-muted)]">
          {t('copyright', { year: new Date().getFullYear() })}
        </p>
      </div>
    </footer>
  )
}
