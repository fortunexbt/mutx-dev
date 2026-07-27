'use client'

import { type ReactNode, useEffect, useState } from 'react'
import Image from 'next/image'
import Link from 'next/link'
import { usePathname } from 'next/navigation'

import {
  picoClasses,
  picoCodex,
  picoCodexFrame,
  picoCodexInset,
  picoCodexNote,
  picoPanel,
} from '@/components/pico/picoTheme'
import { PicoFooter } from '@/components/pico/PicoFooter'
import { getPicoRouteSignal, PicoSignalDiagram } from '@/components/pico/PicoSignalDiagram'
import { PicoWelcomeTour } from '@/components/pico/PicoWelcomeTour'
import { picoHref } from '@/lib/pico/navigation'
import { cn } from '@/lib/utils'

const navItems = [
  { href: '/onboarding', label: 'Start', chapter: '01', note: 'first visible win' },
  { href: '/academy', label: 'Lessons', chapter: '02', note: 'the working path' },
  { href: '/tutor', label: 'Tutor', chapter: '03', note: 'one grounded answer' },
  { href: '/autopilot', label: 'Autopilot', chapter: '04', note: 'live control room' },
  { href: '/support', label: 'Human help', chapter: '05', note: 'the messy edge' },
] as const

const PICO_WELCOME_TOUR_STORAGE_KEY = 'pico.welcome-tour.dismissed.v2'

type PicoShellProps = {
  eyebrow?: string
  title: string
  description: string
  heroContent?: ReactNode
  actions?: ReactNode
  mode?: 'default' | 'academy'
  railCollapsed?: boolean
  helpLaneOpen?: boolean
  preferencesReady?: boolean
  onToggleRail?: () => void
  onToggleHelpLane?: () => void
  children: ReactNode
}

function routeIsActive(pathname: string, href: string) {
  const absoluteHref = `/pico${href}`
  return pathname === absoluteHref || pathname.startsWith(`${absoluteHref}/`)
}

function ShellBackground({ academyMode: _academyMode }: { academyMode: boolean }) {
  return (
    <div aria-hidden="true" className="pointer-events-none absolute inset-0 bg-[color:var(--pico-bg)]" />
  )
}

function PicoWordmark({ pathname }: { pathname: string }) {
  return (
    <Link href={picoHref(pathname, '/onboarding')} className="inline-flex items-center gap-3">
      <span className="inline-flex h-12 w-12 items-center justify-center overflow-hidden border border-[color:var(--pico-border)] bg-[color:var(--pico-bg-raised)]">
        <Image src="/pico/logo.png" alt="PicoMUTX logo" width={28} height={28} priority />
      </span>
      <span className="grid gap-1">
        <span className="text-[11px] font-semibold uppercase tracking-[0.26em] text-[color:var(--pico-text-muted)]">
          PicoMUTX
        </span>
        <span className="font-[family:var(--font-site-display)] text-2xl tracking-[-0.05em] text-[color:var(--pico-text)]">
          operator atlas
        </span>
      </span>
    </Link>
  )
}

function ShellHelpLane({
  pathname,
  currentItem,
  nextItem,
}: {
  pathname: string
  currentItem: (typeof navItems)[number]
  nextItem: (typeof navItems)[number] | null
}) {
  return (
    <div className="grid gap-4 lg:grid-cols-3" data-testid="pico-help-lane-panel">
      <div className={picoCodexInset('p-4')}>
        <p className={picoClasses.label}>Stay here when</p>
        <p className="mt-3 text-sm leading-6 text-[color:var(--pico-text-secondary)]">
          the next move is still inside{' '}
          <span className="text-[color:var(--pico-text)]">{currentItem.label}</span>.
        </p>
      </div>
      <Link
        href={picoHref(pathname, '/support')}
        className={picoCodexNote(
          'p-4 transition duration-200 hover:border-[color:var(--pico-border-hover)] hover:bg-[rgba(var(--pico-accent-rgb),0.16)]',
        )}
      >
        <p className={picoClasses.label}>Recovery route</p>
        <p className="mt-3 font-[family:var(--font-site-display)] text-2xl tracking-[-0.05em] text-[color:var(--pico-text)]">
          Open support lane
        </p>
        <p className="mt-2 text-sm leading-6 text-[color:var(--pico-text-secondary)]">
          Use this when the product route is no longer honest about the blocker.
        </p>
      </Link>
      <Link
        href={picoHref(pathname, nextItem?.href ?? '/support')}
        className={picoCodexInset(
          'p-4 transition duration-200 hover:border-[color:var(--pico-border-hover)] hover:bg-[rgba(255,255,255,0.03)]',
        )}
      >
        <p className={picoClasses.label}>Continue sequence</p>
        <p className="mt-3 font-[family:var(--font-site-display)] text-2xl tracking-[-0.05em] text-[color:var(--pico-text)]">
          {nextItem ? nextItem.label : 'Human help'}
        </p>
        <p className="mt-2 text-sm leading-6 text-[color:var(--pico-text-secondary)]">
          Keep momentum if the next chapter is already the right tool.
        </p>
      </Link>
    </div>
  )
}

export function PicoShell({
  eyebrow,
  title,
  description,
  heroContent,
  actions,
  mode = 'default',
  railCollapsed = false,
  helpLaneOpen = false,
  preferencesReady = true,
  onToggleRail,
  onToggleHelpLane,
  children,
}: PicoShellProps) {
  const pathname = usePathname()
  const [tourOpen, setTourOpen] = useState(false)
  const [tourReady, setTourReady] = useState(false)
  const academyMode = mode === 'academy'
  const currentItem = navItems.find((item) => routeIsActive(pathname, item.href)) ?? navItems[0]
  const routeSignal = getPicoRouteSignal(pathname, academyMode)
  const currentIndex = navItems.findIndex((item) => item.href === currentItem.href)
  const previousItem = currentIndex > 0 ? navItems[currentIndex - 1] : null
  const nextItem = currentIndex < navItems.length - 1 ? navItems[currentIndex + 1] : null
  const isAcademyLessonRoute = pathname.startsWith('/pico/academy/')

  useEffect(() => {
    if (typeof window === 'undefined') {
      return
    }

    const dismissed = window.localStorage.getItem(PICO_WELCOME_TOUR_STORAGE_KEY) === 'dismissed'
    setTourOpen(false)
    setTourReady(true)
    if (dismissed) {
      return
    }
  }, [pathname])

  function closeTour() {
    if (typeof window !== 'undefined') {
      window.localStorage.setItem(PICO_WELCOME_TOUR_STORAGE_KEY, 'dismissed')
    }
    setTourOpen(false)
  }

  if (academyMode) {
    return (
      <div className="relative min-h-screen overflow-hidden bg-[color:var(--pico-bg)] text-[color:var(--pico-text)]">
        <ShellBackground academyMode />

        <div className="relative mx-auto max-w-[98rem] px-4 pb-32 pt-5 sm:px-6 lg:px-8 lg:pb-12">
          <header className={picoCodexFrame('overflow-hidden px-5 py-5 sm:px-6 lg:px-8')}>
            <div className="flex flex-wrap items-center justify-between gap-4">
              <PicoWordmark pathname={pathname} />

              <div className="flex flex-wrap items-center gap-2">
                <span className={picoCodex.stamp}>Chapter {currentItem.chapter}</span>
                <div className="hidden sm:flex sm:flex-wrap sm:items-center sm:gap-2">
                  <button
                    type="button"
                    onClick={() => setTourOpen(true)}
                    disabled={!tourReady}
                    className={picoClasses.tertiaryButton}
                    data-testid="pico-open-tour"
                  >
                    How this works
                  </button>
                  {onToggleRail ? (
                    <button
                      type="button"
                      onClick={onToggleRail}
                      disabled={!preferencesReady}
                      aria-pressed={!railCollapsed}
                      className={cn(
                        picoClasses.tertiaryButton,
                        !railCollapsed &&
                          'border-[color:var(--pico-border-hover)] bg-[rgba(var(--pico-accent-rgb),0.08)] text-[color:var(--pico-text)]',
                      )}
                    >
                      Map
                    </button>
                  ) : null}
                  {onToggleHelpLane ? (
                    <button
                      type="button"
                      onClick={onToggleHelpLane}
                      disabled={!preferencesReady}
                      aria-pressed={helpLaneOpen}
                      className={cn(
                        picoClasses.tertiaryButton,
                        helpLaneOpen &&
                          'border-[color:var(--pico-border-hover)] bg-[rgba(var(--pico-accent-rgb),0.08)] text-[color:var(--pico-text)]',
                      )}
                    >
                      Help
                    </button>
                  ) : null}
                </div>
              </div>
            </div>

            <div className="mt-5 grid gap-5 border-t border-[color:var(--pico-border)] pt-5 lg:grid-cols-[minmax(0,1fr),22rem] lg:items-end">
              <div className="grid gap-2">
                <div className="sm:hidden">
                  <button
                    type="button"
                    onClick={() => setTourOpen(true)}
                    disabled={!tourReady}
                    className={picoClasses.tertiaryButton}
                    data-testid="pico-open-tour-mobile"
                  >
                    How this works
                  </button>
                </div>
                <p className={picoClasses.label}>{eyebrow ?? `Chapter ${currentItem.chapter}`}</p>
                <p className="font-[family:var(--font-site-display)] text-3xl tracking-[-0.05em] text-[color:var(--pico-text)] sm:text-4xl">
                  {title}
                </p>
                <p className="max-w-3xl text-sm leading-6 text-[color:var(--pico-text-secondary)] sm:text-base">
                  {description}
                </p>
                {heroContent ? <div className="mt-5">{heroContent}</div> : null}
              </div>

              <div className="grid gap-4">
                <div className={picoCodexInset('grid gap-3 p-4 lg:p-5')}>
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <p className={picoClasses.label}>Route mode</p>
                    <span className={picoCodex.stamp}>{currentItem.label}</span>
                  </div>
                  <p className="text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                    {currentItem.note}. {railCollapsed ? 'Focus mode is active.' : 'The map stays open.'}
                  </p>
                  <div className="grid gap-1 text-[11px] uppercase tracking-[0.22em] text-[color:var(--pico-text-muted)]">
                    <span>{previousItem ? `Previous: ${previousItem.label}` : 'Start of sequence'}</span>
                    <span>{nextItem ? `Next: ${nextItem.label}` : 'Final chapter'}</span>
                  </div>
                </div>
                <PicoSignalDiagram {...routeSignal} compact />
              </div>
            </div>

            {helpLaneOpen && !isAcademyLessonRoute ? (
              <div className="mt-5 border-t border-[color:var(--pico-border)] pt-5">
                <ShellHelpLane pathname={pathname} currentItem={currentItem} nextItem={nextItem} />
              </div>
            ) : null}
          </header>

          <main id="main-content" className="mt-6 space-y-8">{children}</main>
        </div>

        <PicoFooter />

        <nav
          aria-label="Pico mobile navigation"
          className="fixed inset-x-4 bottom-4 z-40 lg:hidden"
          data-testid="pico-mobile-product-nav"
        >
          <div className={picoCodexFrame('px-3 py-3')}>
            <div className="grid grid-cols-3 gap-2">
              {isAcademyLessonRoute ? (
                <>
                  <Link
                    href={picoHref(pathname, '/academy')}
                    className="inline-flex min-h-11 items-center justify-center rounded-[18px] border border-[color:var(--pico-border)] px-3 text-xs font-semibold uppercase tracking-[0.18em] text-[color:var(--pico-text-secondary)]"
                  >
                    Back to map
                  </Link>
                  <a
                    href="#pico-proof-composer"
                    className="inline-flex min-h-11 items-center justify-center rounded-[18px] border border-[color:var(--pico-border-hover)] bg-[rgba(var(--pico-accent-rgb),0.08)] px-3 text-xs font-semibold uppercase tracking-[0.18em] text-[color:var(--pico-text)]"
                  >
                    Proof
                  </a>
                  <a
                    href="#pico-lesson-recovery"
                    className="inline-flex min-h-11 items-center justify-center rounded-[18px] border border-[color:var(--pico-border)] px-3 text-xs font-semibold uppercase tracking-[0.18em] text-[color:var(--pico-text-secondary)]"
                  >
                    Help
                  </a>
                </>
              ) : (
                <>
                  <a
                    href="#pico-academy-workspace-summary"
                    className="inline-flex min-h-11 items-center justify-center rounded-[18px] border border-[color:var(--pico-border-hover)] bg-[rgba(var(--pico-accent-rgb),0.08)] px-3 text-xs font-semibold uppercase tracking-[0.18em] text-[color:var(--pico-text)]"
                  >
                    Open mission
                  </a>
                  <button
                    type="button"
                    onClick={onToggleRail}
                    disabled={!preferencesReady}
                    className="inline-flex min-h-11 items-center justify-center rounded-[18px] border border-[color:var(--pico-border)] px-3 text-xs font-semibold uppercase tracking-[0.18em] text-[color:var(--pico-text-secondary)]"
                  >
                    Map
                  </button>
                  <button
                    type="button"
                    onClick={onToggleHelpLane}
                    disabled={!preferencesReady}
                    className="inline-flex min-h-11 items-center justify-center rounded-[18px] border border-[color:var(--pico-border)] px-3 text-xs font-semibold uppercase tracking-[0.18em] text-[color:var(--pico-text-secondary)]"
                  >
                    Help
                  </button>
                </>
              )}
            </div>
          </div>
        </nav>

        <PicoWelcomeTour
          open={tourOpen}
          onClose={closeTour}
          currentItem={currentItem}
          previousItem={previousItem}
          nextItem={nextItem}
          pageTitle={title}
        />
      </div>
    )
  }

  return (
    <div className="relative min-h-screen overflow-hidden bg-[color:var(--pico-bg)] text-[color:var(--pico-text)]">
      <ShellBackground academyMode={false} />

      <div className="relative mx-auto max-w-[106rem] px-4 py-5 pb-28 sm:px-6 lg:px-8 lg:pb-4">
        <div className="grid grid-cols-[minmax(0,1fr)] gap-6 lg:grid-cols-[18rem,minmax(0,1fr)]">
          <aside className="hidden lg:block lg:sticky lg:top-4 lg:self-start">
            <div className={picoPanel('overflow-hidden')}>
              <div className="border-b border-[color:var(--pico-border)] p-5">
                <PicoWordmark pathname={pathname} />
              </div>

              <div className="border-b border-[color:var(--pico-border)] px-5 py-4">
                <p className={picoClasses.label}>Current chapter</p>
                <p className="mt-3 font-[family:var(--font-site-display)] text-3xl tracking-[-0.05em] text-[color:var(--pico-text)]">
                  {currentItem.label}
                </p>
                <p className="mt-2 text-sm text-[color:var(--pico-text-secondary)]">{currentItem.note}</p>
              </div>

              <nav className="grid gap-2 p-4">
                {navItems.map((item) => {
                  const active = routeIsActive(pathname, item.href)
                  return (
                    <Link
                      key={item.href}
                      href={picoHref(pathname, item.href)}
                      className={cn(
                        'grid gap-1 rounded-[22px] border px-4 py-3 transition duration-200',
                        active
                          ? 'border-[color:var(--pico-border-hover)] bg-[linear-gradient(180deg,rgba(var(--pico-accent-rgb),0.16),rgba(10,19,11,0.38))] text-[color:var(--pico-text)] shadow-[0_18px_42px_rgba(var(--pico-accent-rgb),0.08)]'
                          : 'border-[color:rgba(255,255,255,0.05)] bg-[rgba(255,255,255,0.015)] text-[color:var(--pico-text-secondary)] hover:border-[color:var(--pico-border)] hover:bg-[rgba(255,255,255,0.03)] hover:text-[color:var(--pico-text)]',
                      )}
                    >
                      <span className="text-[10px] font-semibold uppercase tracking-[0.24em] text-[color:var(--pico-text-muted)]">
                        {item.chapter}
                      </span>
                      <span className="font-medium">{item.label}</span>
                      <span className="text-xs text-[color:var(--pico-text-muted)]">{item.note}</span>
                    </Link>
                  )
                })}
              </nav>
            </div>
          </aside>

          <div className="min-w-0 space-y-6">
            <header className={picoPanel('overflow-hidden')}>
              <div className="border-b border-[color:var(--pico-border)] px-6 py-4 sm:px-7">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="flex flex-wrap items-center gap-3">
                    <span className="inline-flex rounded-full border border-[color:var(--pico-border)] bg-[rgba(255,255,255,0.02)] px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.22em] text-[color:var(--pico-accent-bright)]">
                      Chapter {currentItem.chapter}
                    </span>
                    <span className="text-[11px] font-semibold uppercase tracking-[0.24em] text-[color:var(--pico-text-muted)]">
                      {currentItem.note}
                    </span>
                  </div>

                  <div className="hidden sm:flex sm:flex-wrap sm:gap-2">
                    <button
                      type="button"
                      onClick={() => setTourOpen(true)}
                      disabled={!tourReady}
                      className={picoClasses.tertiaryButton}
                      data-testid="pico-open-tour"
                    >
                      Quick help
                    </button>
                    {previousItem ? (
                      <Link
                        href={picoHref(pathname, previousItem.href)}
                        aria-label={`Go to previous chapter: ${previousItem.label}`}
                        className={picoClasses.tertiaryButton}
                      >
                        Previous chapter
                      </Link>
                    ) : null}
                    {nextItem ? (
                      <Link
                        href={picoHref(pathname, nextItem.href)}
                        aria-label={`Go to next chapter: ${nextItem.label}`}
                        className={picoClasses.tertiaryButton}
                      >
                        Next chapter
                      </Link>
                    ) : null}
                    {onToggleHelpLane ? (
                      <button type="button" onClick={onToggleHelpLane} className={picoClasses.tertiaryButton}>
                        {helpLaneOpen ? 'Hide recovery' : 'Show recovery'}
                      </button>
                    ) : null}
                  </div>
                </div>
              </div>

              <div className="grid grid-cols-[minmax(0,1fr)] gap-5 px-6 py-6 sm:px-7 lg:grid-cols-[minmax(0,1fr),20rem] lg:items-start">
                <div className="grid min-w-0 gap-4">
                  <div className="sm:hidden">
                    <button
                      type="button"
                      onClick={() => setTourOpen(true)}
                      disabled={!tourReady}
                      className={picoClasses.tertiaryButton}
                      data-testid="pico-open-tour-mobile"
                    >
                      Quick help
                    </button>
                  </div>
                  {eyebrow ? (
                    <span className="text-[11px] font-semibold uppercase tracking-[0.24em] text-[color:var(--pico-text-muted)]">
                      {eyebrow}
                    </span>
                  ) : null}
                  <h1 className="max-w-[11ch] font-[family:var(--font-site-display)] text-[clamp(2.6rem,10vw,4rem)] leading-[0.92] tracking-[-0.06em] text-[color:var(--pico-text)] sm:max-w-4xl sm:text-6xl">
                    {title}
                  </h1>
                  <p className="max-w-3xl text-sm leading-7 text-[color:var(--pico-text-secondary)] sm:text-base">
                    {description}
                  </p>
                  {heroContent ? <div className="pt-1">{heroContent}</div> : null}
                </div>

                <div className="grid min-w-0 gap-4">
                  <PicoSignalDiagram {...routeSignal} compact />
                  <div className={picoCodexInset('p-5')}>
                    <p className={picoClasses.label}>Chapter note</p>
                    <p className="mt-3 font-[family:var(--font-site-display)] text-2xl tracking-[-0.05em] text-[color:var(--pico-text)]">
                      {currentItem.note}
                    </p>
                    <p className="mt-3 text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                      Use this chapter to cut uncertainty quickly and identify the next irreversible action.
                    </p>
                  </div>
                  {actions ? (
                    <div className="grid w-full min-w-0 gap-3 [&>*]:min-w-0 [&>*]:w-full sm:flex sm:flex-wrap sm:[&>*]:w-auto">
                      {actions}
                    </div>
                  ) : null}
                </div>
              </div>

              {helpLaneOpen ? (
                <div className="border-t border-[color:var(--pico-border)] px-6 py-5 sm:px-7">
                  <ShellHelpLane pathname={pathname} currentItem={currentItem} nextItem={nextItem} />
                </div>
              ) : null}
            </header>

            <main id="main-content" className="space-y-6">{children}</main>
          </div>
        </div>
      </div>

      <PicoFooter />

      <nav
        aria-label="Pico mobile navigation"
        className="fixed inset-x-4 bottom-4 z-40 lg:hidden"
        data-testid="pico-mobile-product-nav"
      >
        <div className="grid grid-cols-[auto,1fr,auto,auto] items-center gap-2 rounded-[24px] border border-[color:var(--pico-border)] bg-[rgba(6,12,8,0.94)] p-2 shadow-[0_24px_60px_rgba(0,0,0,0.4)] backdrop-blur">
          <Link
            href={picoHref(pathname, previousItem?.href ?? '/onboarding')}
            aria-label={previousItem ? `Go to previous chapter: ${previousItem.label}` : 'Go to onboarding'}
            className="inline-flex min-h-11 items-center justify-center rounded-[18px] border border-[color:var(--pico-border)] px-3 text-xs font-medium uppercase tracking-[0.16em] text-[color:var(--pico-text-secondary)]"
          >
            Prev
          </Link>

          <div className="min-w-0 px-2">
            <p className="truncate text-[11px] font-semibold uppercase tracking-[0.22em] text-[color:var(--pico-text-muted)]">
              Chapter {currentItem.chapter}
            </p>
            <p className="truncate font-[family:var(--font-site-display)] text-xl tracking-[-0.05em] text-[color:var(--pico-text)]">
              {currentItem.label}
            </p>
          </div>

          <Link
            href={picoHref(pathname, nextItem?.href ?? '/support')}
            aria-label={nextItem ? `Go to next chapter: ${nextItem.label}` : 'Go to support'}
            className="inline-flex min-h-11 items-center justify-center rounded-[18px] border border-[color:var(--pico-border)] px-3 text-xs font-medium uppercase tracking-[0.16em] text-[color:var(--pico-text-secondary)]"
          >
            Next
          </Link>

          <Link
            href={picoHref(pathname, currentItem.href === '/support' ? '/academy' : '/support')}
            aria-label={currentItem.href === '/support' ? 'Open academy map' : 'Open help lane'}
            className="inline-flex min-h-11 items-center justify-center rounded-[18px] border border-[color:rgba(var(--pico-accent-rgb),0.28)] bg-[linear-gradient(135deg,var(--pico-accent-bright)_0%,var(--pico-accent)_48%,var(--pico-accent-deep)_100%)] px-3 text-xs font-semibold uppercase tracking-[0.16em] text-[color:var(--pico-accent-contrast)]"
          >
            {currentItem.href === '/support' ? 'Map' : 'Help'}
          </Link>
        </div>
      </nav>

      <PicoWelcomeTour
        open={tourOpen}
        onClose={closeTour}
        currentItem={currentItem}
        previousItem={previousItem}
        nextItem={nextItem}
        pageTitle={title}
      />
    </div>
  )
}
