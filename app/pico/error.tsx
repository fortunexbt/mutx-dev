'use client'

import Link from 'next/link'
import { useTranslations } from 'next-intl'

export default function PicoError({
  error: _error,
  reset,
}: {
  error: Error & { digest?: string }
  reset: () => void
}) {
  const t = useTranslations('pico.routeStates.error')

  return (
    <main
      id="main-content"
      tabIndex={-1}
      data-boundary-surface="pico"
      data-boundary-kind="error"
      className="grid min-h-[100svh] place-items-center bg-[color:var(--pico-bg)] px-4 py-8 text-[color:var(--pico-text)] sm:px-6"
      aria-labelledby="pico-error-title"
    >
      <div
        className="w-full max-w-5xl border border-[color:var(--pico-red)] bg-[color:var(--pico-bg-panel)]"
        role="alert"
      >
        <header className="flex min-h-14 flex-wrap items-center justify-between gap-3 border-b border-[color:var(--pico-border)] px-5 font-[family:var(--font-mono)] text-[10px] font-semibold uppercase tracking-[0.18em] text-[color:var(--pico-text-muted)] sm:px-8">
          <span>{t('route')}</span>
          <span className="border border-[color:var(--pico-red)] px-2.5 py-1 text-[color:var(--pico-red)]">
            {t('step')}
          </span>
        </header>

        <div className="grid min-h-[30rem] lg:grid-cols-[minmax(0,1fr)_20rem]">
          <div className="flex flex-col justify-end px-5 py-10 sm:px-8 sm:py-14 lg:px-12">
            <p className="font-[family:var(--font-mono)] text-[10px] font-semibold uppercase tracking-[0.18em] text-[color:var(--pico-red)]">
              {t('eyebrow')}
            </p>
            <h1
              id="pico-error-title"
              className="mt-4 max-w-3xl font-[family:var(--font-site-body)] text-4xl font-semibold leading-[0.98] tracking-[-0.055em] sm:text-6xl"
            >
              {t('title')}
            </h1>
            <p className="mt-6 max-w-2xl text-sm leading-6 text-[color:var(--pico-text-secondary)] sm:text-base sm:leading-7">
              {t('body')}
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <button
                type="button"
                onClick={reset}
                className="inline-flex min-h-11 items-center justify-center border border-[color:var(--pico-accent)] bg-[color:var(--pico-accent)] px-5 font-[family:var(--font-mono)] text-[11px] font-semibold uppercase tracking-[0.08em] text-[color:var(--pico-accent-contrast)] transition-colors hover:bg-[color:var(--pico-text)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-[color:var(--pico-text)] motion-reduce:transition-none"
              >
                {t('retry')}
              </button>
              <Link
                href="/pico/support"
                className="inline-flex min-h-11 items-center justify-center border border-[color:var(--pico-border)] bg-transparent px-5 font-[family:var(--font-mono)] text-[11px] font-semibold uppercase tracking-[0.08em] text-[color:var(--pico-text)] transition-colors hover:border-[color:var(--pico-accent)] hover:text-[color:var(--pico-accent)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-[color:var(--pico-text)] motion-reduce:transition-none"
              >
                {t('support')}
              </Link>
            </div>
          </div>

          <aside className="border-t border-[color:var(--pico-border)] bg-[color:var(--pico-bg-raised)] p-6 lg:border-s lg:border-t-0 lg:p-8">
            <p className="font-[family:var(--font-mono)] text-[10px] font-semibold uppercase tracking-[0.18em] text-[color:var(--pico-text-muted)]">
              {t('scopeLabel')}
            </p>
            <p className="mt-5 font-[family:var(--font-site-body)] text-2xl font-semibold tracking-[-0.04em] text-[color:var(--pico-red)]">
              {t('scopeTitle')}
            </p>
            <p className="mt-4 text-sm leading-6 text-[color:var(--pico-text-muted)]">
              {t('scopeBody')}
            </p>
          </aside>
        </div>
      </div>
    </main>
  )
}
