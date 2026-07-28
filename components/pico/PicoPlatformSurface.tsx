'use client'

import Link from 'next/link'
import { useLocale, useTranslations } from 'next-intl'

import {
  PICO_PLAN_MATRIX,
  type PicoDerivedProgress,
  type PicoPlan,
  type PicoProgressState,
} from '@/lib/pico/academy'
import { usePicoHref } from '@/lib/pico/navigation'
import { formatPicoDateTime } from '@/lib/pico/locale'
import { type PicoSessionState } from '@/components/pico/usePicoSession'
import { picoClasses, picoEmber, picoInset, picoPanel, picoSoft } from '@/components/pico/picoTheme'
import { cn } from '@/lib/utils'

type PicoPlatformSurfaceProps = {
  session: PicoSessionState
  progress: PicoProgressState
  derived: PicoDerivedProgress
  syncState: string
  ready: boolean
  onSave: (patch: Partial<PicoProgressState['platform']>) => void
  onReset: () => void
  currentPath: string
}

const surfaceIds: Array<NonNullable<PicoProgressState['platform']['activeSurface']>> = [
  'onboarding',
  'academy',
  'lesson',
  'tutor',
  'autopilot',
  'support',
]

function toPlan(value: string | null | undefined): PicoPlan {
  return value === 'starter' || value === 'pro' ? value : 'free'
}

function formatTimestamp(value: string | null | undefined, locale: string) {
  return value ? formatPicoDateTime(value, locale, {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  }) : null
}

function getSyncStateKey(syncState: string, ready: boolean) {
  if (!ready) {
    return 'hydrating'
  }

  switch (syncState) {
    case 'synced':
      return 'live'
    case 'saving':
      return 'saving'
    case 'offline':
      return 'localOnly'
    default:
      return 'localOnly'
  }
}

export function PicoPlatformSurface({
  session,
  progress,
  derived: _derived,
  syncState,
  ready,
  onSave,
  onReset,
  currentPath,
}: PicoPlatformSurfaceProps) {
  const locale = useLocale()
  const t = useTranslations('pico.platformSurface')
  const contentT = useTranslations('pico.content')
  const toHref = usePicoHref()
  const plan = toPlan(session.status === 'authenticated' ? session.user.plan : null)
  const planMatrix = PICO_PLAN_MATRIX[plan]
  const lastOpenedLesson = progress.platform.lastOpenedLessonSlug
  const activeSurface = progress.platform.activeSurface
  const surfaceOptions = surfaceIds.map((surface) => ({
    surface,
    label: t(`surfaceOptions.${surface}.label`),
    note: t(`surfaceOptions.${surface}.note`),
  }))
  const syncStateLabel = t(`syncState.${getSyncStateKey(syncState, ready)}`)

  function setActiveSurface(surface: NonNullable<PicoProgressState['platform']['activeSurface']>) {
    onSave({ activeSurface: surface })
  }

  return (
    <section className={picoPanel('p-6 sm:p-7')} data-testid="pico-platform-surface">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <p className={picoClasses.label}>{t('header.label')}</p>
          <h2 className="mt-3 font-[family:var(--font-site-display)] text-3xl tracking-[-0.06em] text-[color:var(--pico-text)] sm:text-4xl">
            {t('header.title')}
          </h2>
          <p className="mt-3 max-w-3xl text-sm leading-6 text-[color:var(--pico-text-secondary)]">
            {t('header.body')}
          </p>
        </div>
        <span className={picoClasses.chip}>{syncStateLabel}</span>
      </div>

      <div className="mt-6 grid gap-6 xl:grid-cols-[minmax(0,1.05fr),minmax(0,0.95fr)]">
        <div className="grid gap-4">
          <div className={picoInset('grid gap-4 p-5')}>
            <div className="grid gap-4 sm:grid-cols-3">
              <div>
                <p className="text-sm text-[color:var(--pico-text-muted)]">{t('summary.plan')}</p>
                <p className="mt-1 text-lg font-medium text-[color:var(--pico-text)]">{plan.toUpperCase()}</p>
              </div>
              <div>
                <p className="text-sm text-[color:var(--pico-text-muted)]">{t('summary.verification')}</p>
                <p className="mt-1 text-lg font-medium text-[color:var(--pico-text)]">
                  {session.status === 'authenticated'
                    ? session.user.isEmailVerified === false
                      ? t('summary.verificationState.pending')
                      : session.user.isEmailVerified === true
                        ? t('summary.verificationState.verified')
                        : t('summary.verificationState.unknown')
                    : t('summary.verificationState.signIn')}
                </p>
              </div>
              <div>
                <p className="text-sm text-[color:var(--pico-text-muted)]">{t('summary.workspaceSaves')}</p>
                <p className="mt-1 text-lg font-medium text-[color:var(--pico-text)]">
                  {Object.keys(progress.lessonWorkspaces).length}
                </p>
              </div>
            </div>

            <div className="grid gap-3">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <p className={picoClasses.label}>{t('routeMemory.label')}</p>
                  <p className="mt-1 text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                    {t('routeMemory.body')}
                  </p>
                </div>
                <span className={picoClasses.chip} data-testid="pico-platform-active-surface">
                  {activeSurface ?? t('shared.notRecorded')}
                </span>
              </div>

              <div className="grid gap-3" data-testid="pico-platform-surface-memory">
                {surfaceOptions.map((option) => {
                  const selected = activeSurface === option.surface
                  return (
                    <button
                      key={option.surface}
                      type="button"
                      onClick={() => setActiveSurface(option.surface)}
                      aria-pressed={selected}
                      className={picoSoft(
                        `grid gap-3 rounded-[24px] px-4 py-4 text-start transition sm:grid-cols-[minmax(0,1fr),auto] sm:items-center hover:border-[color:var(--pico-border-hover)] hover:bg-[color:var(--pico-bg-surface-hover)] ${
                          selected
                            ? 'border-[color:var(--pico-accent)] bg-[rgba(var(--pico-accent-rgb),0.1)]'
                            : ''
                        }`,
                      )}
                    >
                      <div>
                        <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[color:var(--pico-text-muted)]">
                          {option.note}
                        </p>
                        <p className="mt-2 text-xl font-medium text-[color:var(--pico-text)]">{option.label}</p>
                      </div>
                      <span className={cn(picoClasses.chip, selected && 'text-[color:var(--pico-text)]')}>
                        {selected ? t('surfaceOptions.activeNow') : t('surfaceOptions.setRoute')}
                      </span>
                    </button>
                  )
                })}
              </div>
            </div>

            <div className="grid gap-4 md:grid-cols-2">
              <div className={picoSoft('p-4')}>
                  <p className={picoClasses.label}>{t('routeMemory.currentSurface.label')}</p>
                <p className="mt-2 text-lg font-medium text-[color:var(--pico-text)]">
                  {activeSurface ?? t('shared.notRecorded')}
                </p>
                <p className="mt-2 text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                  {t('routeMemory.currentSurface.body')}
                </p>
              </div>

              <div className={picoSoft('p-4')}>
                <p className={picoClasses.label}>{t('routeMemory.lastLessonContext.label')}</p>
                <p className="mt-2 text-lg font-medium text-[color:var(--pico-text)]">
                  {lastOpenedLesson ?? t('shared.notRecorded')}
                </p>
                <p className="mt-2 text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                  {t('routeMemory.lastLessonContext.body')}
                </p>
              </div>
            </div>

            <div className="grid gap-4 md:grid-cols-2">
              <label className="flex items-start gap-3 rounded-[24px] border border-[color:var(--pico-border)] bg-[color:var(--pico-bg-surface)] px-4 py-4 text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                <input
                  type="checkbox"
                  checked={progress.platform.railCollapsed}
                  onChange={(event) => onSave({ railCollapsed: event.target.checked })}
                  className="mt-1 h-4 w-4 rounded border-[color:var(--pico-border)] bg-transparent text-[color:var(--pico-accent)] accent-[color:var(--pico-accent)]"
                />
                <span>
                  <span className="block font-medium text-[color:var(--pico-text)]">{t('toggles.collapseRail.label')}</span>
                  <span className="block text-[color:var(--pico-text-secondary)]">
                    {t('toggles.collapseRail.body')}
                  </span>
                </span>
              </label>

              <label className="flex items-start gap-3 rounded-[24px] border border-[color:var(--pico-border)] bg-[color:var(--pico-bg-surface)] px-4 py-4 text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                <input
                  type="checkbox"
                  checked={progress.platform.helpLaneOpen}
                  onChange={(event) => onSave({ helpLaneOpen: event.target.checked })}
                  className="mt-1 h-4 w-4 rounded border-[color:var(--pico-border)] bg-transparent text-[color:var(--pico-accent)] accent-[color:var(--pico-accent)]"
                />
                <span>
                  <span className="block font-medium text-[color:var(--pico-text)]">{t('toggles.keepHelpLaneOpen.label')}</span>
                  <span className="block text-[color:var(--pico-text-secondary)]">
                    {t('toggles.keepHelpLaneOpen.body')}
                  </span>
                </span>
              </label>
            </div>

            <div className="flex flex-wrap gap-3">
              {lastOpenedLesson ? (
                <Link href={toHref(`/academy/${lastOpenedLesson}`)} className={picoClasses.primaryButton}>
                  {t('actions.resumeLastLesson')}
                </Link>
              ) : (
                <Link href={toHref('/academy')} className={picoClasses.primaryButton}>
                  {t('actions.openAcademy')}
                </Link>
              )}
              {lastOpenedLesson ? (
                <button
                  type="button"
                  onClick={() => onSave({ lastOpenedLessonSlug: null })}
                  className={picoClasses.secondaryButton}
                >
                  {t('actions.clearLessonMemory')}
                </button>
              ) : null}
              <button type="button" onClick={onReset} className={picoClasses.secondaryButton}>
                {t('actions.resetPlatformMemory')}
              </button>
              <Link href={toHref('/autopilot')} className={picoClasses.tertiaryButton}>
                {t('actions.openLiveControlRoom')}
              </Link>
            </div>
          </div>

          <div className={picoEmber('p-5')}>
            <p className={picoClasses.label}>{t('entitlements.label')}</p>
            <div className="mt-4 grid gap-3">
              {(Object.entries(planMatrix) as Array<[keyof typeof planMatrix, string]>).map(([feature]) => (
                <div
                  key={feature}
                  className="flex items-start justify-between gap-4 border-b border-[color:var(--pico-border)] pb-3 last:border-b-0 last:pb-0"
                >
                  <span className="text-sm uppercase tracking-[0.18em] text-[color:var(--pico-text-muted)]">
                    {t(`entitlements.featureLabels.${feature}`)}
                  </span>
                  <span className="max-w-[14rem] text-end text-sm leading-6 text-[color:var(--pico-text)]">
                    {contentT(`planMatrix.${plan}.${feature}`)}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="grid gap-4">
          <div className={picoInset('p-5')}>
            <p className={picoClasses.label}>{t('routeLedger.label')}</p>
            <div className="mt-4 grid gap-3">
              <div className={picoSoft('p-4')}>
                <p className="text-sm text-[color:var(--pico-text-muted)]">{t('routeLedger.currentPath')}</p>
                <p className="mt-1 text-lg font-medium text-[color:var(--pico-text)]">{currentPath}</p>
              </div>
              <div className={picoSoft('p-4')}>
                <p className="text-sm text-[color:var(--pico-text-muted)]">{t('routeLedger.platformStateUpdated')}</p>
                <p className="mt-1 text-lg font-medium text-[color:var(--pico-text)]">
                  {formatTimestamp(progress.platform.updatedAt, locale) ?? t('shared.notRecorded')}
                </p>
              </div>
              <div className={picoSoft('p-4')}>
                <p className="text-sm text-[color:var(--pico-text-muted)]">{t('routeLedger.syncConfidence')}</p>
                <p className="mt-1 text-lg font-medium text-[color:var(--pico-text)]">
                  {syncStateLabel}
                </p>
              </div>
            </div>
          </div>

          <div className={picoInset('p-5')}>
            <p className={picoClasses.label}>{t('operatorTruth.label')}</p>
            <p className="mt-3 text-sm leading-6 text-[color:var(--pico-text-secondary)]">
              {t('operatorTruth.body')}
            </p>
          </div>
        </div>
      </div>
    </section>
  )
}
