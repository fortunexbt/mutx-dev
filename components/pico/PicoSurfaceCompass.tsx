'use client'

import Link from 'next/link'
import { useTranslations } from 'next-intl'

import { picoClasses, picoEmber, picoInset, picoPanel, picoSoft } from '@/components/pico/picoTheme'
import { cn } from '@/lib/utils'

type PicoSurfaceCompassTone = 'primary' | 'secondary' | 'soft'

export type PicoSurfaceCompassItem = {
  href: string
  label: string
  caption: string
  note: string
  tone?: PicoSurfaceCompassTone
}

type PicoSurfaceCompassProps = {
  title: string
  body: string
  status?: string
  items: PicoSurfaceCompassItem[]
  aside?: string
}

function itemClasses(tone: PicoSurfaceCompassTone = 'secondary') {
  if (tone === 'primary') {
    return picoEmber('group grid gap-3 p-5 transition hover:border-[color:var(--pico-accent)] hover:bg-[linear-gradient(180deg,rgba(117,64,33,0.28),rgba(45,27,16,0.32))]')
  }

  if (tone === 'soft') {
    return picoSoft('group grid gap-3 p-5 transition hover:border-[color:var(--pico-border-hover)] hover:bg-[rgba(22,16,12,0.86)]')
  }

  return picoInset('group grid gap-3 p-5 transition hover:border-[color:var(--pico-border-hover)] hover:bg-[color:var(--pico-bg-surface-hover)]')
}

export function PicoSurfaceCompass({
  title,
  body,
  status,
  items,
  aside,
}: PicoSurfaceCompassProps) {
  const t = useTranslations('pico.surfaceCompass')
  const itemGridClass = cn(
    'mt-5 grid grid-flow-col auto-cols-[minmax(16rem,84vw)] gap-4 overflow-x-auto pb-2 snap-x snap-mandatory md:grid-flow-row md:auto-cols-auto md:overflow-visible',
    items.length === 2 && 'md:grid-cols-2',
    items.length === 3 && 'md:grid-cols-3',
    items.length >= 4 && 'md:grid-cols-2 2xl:grid-cols-4',
  )

  return (
    <section className={picoPanel('p-5 sm:p-6')} data-testid="pico-surface-compass">
      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr),22rem] lg:items-start">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <span className={picoClasses.label}>{t('label')}</span>
            {status ? <span className={picoClasses.chip}>{status}</span> : null}
          </div>
          <h2 className="mt-3 font-[family:var(--font-site-display)] text-3xl tracking-[-0.05em] text-[color:var(--pico-text)] sm:text-4xl">
            {title}
          </h2>
          <p className="mt-3 max-w-3xl text-sm leading-6 text-[color:var(--pico-text-secondary)] sm:text-base sm:leading-7">
            {body}
          </p>
        </div>

        {aside ? (
          <div className={picoSoft('p-4 sm:p-5')}>
            <p className={picoClasses.label}>{t('operatingRule')}</p>
            <p className="mt-3 text-sm leading-6 text-[color:var(--pico-text-secondary)]">{aside}</p>
          </div>
        ) : null}
      </div>

      <div className={itemGridClass}>
        {items.map((item) => (
          <Link
            key={`${item.href}-${item.label}`}
            href={item.href}
            className={cn(itemClasses(item.tone), 'snap-start')}
          >
            <div className="flex items-start justify-between gap-3">
              <span className="text-[11px] font-semibold uppercase tracking-[0.22em] text-[color:var(--pico-text-muted)]">
                {item.note}
              </span>
              <span className="text-sm text-[color:var(--pico-accent)]" aria-hidden="true">
                {t('forwardSymbol')}
              </span>
            </div>
            <p className="font-[family:var(--font-site-display)] text-2xl tracking-[-0.05em] text-[color:var(--pico-text)]">
              {item.label}
            </p>
            <p className="text-sm leading-6 text-[color:var(--pico-text-secondary)]">{item.caption}</p>
          </Link>
        ))}
      </div>
    </section>
  )
}
