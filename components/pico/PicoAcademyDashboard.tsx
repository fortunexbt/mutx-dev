'use client'

import { type ReactNode, useCallback, useEffect } from 'react'
import Link from 'next/link'
import { useLocale, useTranslations } from 'next-intl'
import { usePathname } from 'next/navigation'
import { motion, useReducedMotion } from 'framer-motion'

import { PicoPlatformSurface } from '@/components/pico/PicoPlatformSurface'
import { PicoShell } from '@/components/pico/PicoShell'
import {
  picoClasses,
  picoCodex,
  picoCodexFrame,
  picoCodexInset,
  picoCodexNote,
  picoCodexSheet,
} from '@/components/pico/picoTheme'
import { usePicoLessonWorkspace } from '@/components/pico/usePicoLessonWorkspace'
import { usePicoProgress } from '@/components/pico/usePicoProgress'
import { usePicoSession } from '@/components/pico/usePicoSession'
import {
  PICO_LEVELS,
  PICO_RELEASE_NOTES,
  PICO_SHOWCASE_PATTERNS,
  PICO_TRACKS,
  getLessonBySlug,
  getPicoLessonCompletionStatus,
  isPicoLessonEvidenceMeaningful,
  type PicoLesson,
} from '@/lib/pico/academy'
import {
  localizePicoCapability,
  localizePicoLesson,
  localizePicoLevel,
  localizePicoTrack,
} from '@/lib/pico/content'
import { formatPicoDateTime } from '@/lib/pico/locale'
import { usePicoHref } from '@/lib/pico/navigation'
import { cn } from '@/lib/utils'

type LessonState = 'done' | 'current' | 'ready' | 'locked'

function FadeIn({
  children,
  className,
  delay = 0,
  reduceMotion = false,
}: {
  children: ReactNode
  className?: string
  delay?: number
  reduceMotion?: boolean
}) {
  return (
    <motion.div
      initial={reduceMotion ? false : { opacity: 0, y: 22 }}
      animate={{ opacity: 1, y: 0 }}
      transition={reduceMotion ? { duration: 0 } : { duration: 0.55, ease: 'easeOut', delay }}
      className={className}
      data-motion={reduceMotion ? 'reduced' : 'full'}
      data-pico-academy-motion
    >
      {children}
    </motion.div>
  )
}

function LessonStateStamp({ state }: { state: LessonState }) {
  const t = useTranslations('pico.academyPage.lessonState')
  const copy =
    state === 'done'
      ? t('cleared')
      : state === 'current'
        ? t('current')
        : state === 'ready'
          ? t('ready')
          : t('locked')

  return (
    <span
      className={cn(
        picoCodex.stamp,
        state === 'done' && 'border-emerald-500/35 bg-emerald-500/10 text-emerald-100',
        state === 'current' && 'border-[color:var(--pico-accent)] bg-[rgba(var(--pico-accent-rgb),0.16)] text-[color:var(--pico-text)]',
        state === 'ready' && 'border-cyan-500/30 bg-cyan-500/10 text-cyan-100',
        state === 'locked' && 'border-[color:var(--pico-border)] bg-transparent text-[color:var(--pico-text-muted)]',
      )}
    >
      {copy}
    </span>
  )
}

function getLessonState(
  lesson: PicoLesson,
  completedLessons: string[],
  unlockedLessonSlugs: string[],
  currentLessonSlug: string | null,
): LessonState {
  if (completedLessons.includes(lesson.slug)) {
    return 'done'
  }

  if (currentLessonSlug === lesson.slug) {
    return 'current'
  }

  if (unlockedLessonSlugs.includes(lesson.slug)) {
    return 'ready'
  }

  return 'locked'
}

function getSyncStateKey(syncState: string, ready: boolean) {
  if (!ready) {
    return 'hydrating' as const
  }

  switch (syncState) {
    case 'synced':
      return 'live' as const
    case 'saving':
      return 'saving' as const
    case 'offline':
      return 'localOnly' as const
    default:
      return 'localOnly' as const
  }
}

function formatTimestamp(value: string | null | undefined, locale: string) {
  return value ? formatPicoDateTime(value, locale, {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  }) : null
}

export function PicoAcademyDashboard() {
  const pathname = usePathname()
  const locale = useLocale()
  const t = useTranslations('pico.academyPage')
  const contentT = useTranslations('pico.content')
  const session = usePicoSession()
  const { progress, derived, syncState, ready, actions } = usePicoProgress(
    session.status === 'authenticated',
  )
  const toHref = usePicoHref()
  const reduceMotion = useReducedMotion() ?? false

  const localizedTracks = PICO_TRACKS.map((track) => localizePicoTrack(track, contentT))
  const getLocalizedLesson = (slug: string) => {
    const lesson = getLessonBySlug(slug)
    return lesson ? localizePicoLesson(lesson, contentT) : null
  }
  const nextLesson = derived.nextLesson
    ? localizePicoLesson(derived.nextLesson, contentT)
    : null
  const installDone = progress.completedLessons.includes('install-hermes-locally')
  const firstRunDone = progress.completedLessons.includes('run-your-first-agent')
  const activationLessonSlug = firstRunDone
    ? (nextLesson?.slug ?? null)
    : installDone
      ? 'run-your-first-agent'
      : 'install-hermes-locally'
  const activationLesson = activationLessonSlug ? getLocalizedLesson(activationLessonSlug) : null
  const fallbackTrack = localizedTracks[0]
  const activeTrack = localizedTracks.find((track) => track.slug === progress.selectedTrack) ?? fallbackTrack
  const activeTrackLessons = activeTrack.lessons
    .map((slug) => getLocalizedLesson(slug))
    .filter((lesson): lesson is PicoLesson => Boolean(lesson))
  const activeTrackIndex = Math.max(
    localizedTracks.findIndex((track) => track.slug === activeTrack.slug),
    0,
  )
  const activeTrackChapter = String(activeTrackIndex + 1).padStart(2, '0')
  const activeTrackCompletedCount = activeTrackLessons.filter((lesson) =>
    progress.completedLessons.includes(lesson.slug),
  ).length
  const activeTrackCompletionPercent =
    activeTrackLessons.length > 0
      ? Math.round((activeTrackCompletedCount / activeTrackLessons.length) * 100)
      : 0
  const currentLevelSource = PICO_LEVELS.find((level) => level.id === derived.currentLevel)
  const currentLevel = currentLevelSource ? localizePicoLevel(currentLevelSource, contentT) : null
  const allLessons = localizedTracks.flatMap((track) => track.lessons)
    .map((slug) => getLocalizedLesson(slug))
    .filter((lesson): lesson is PicoLesson => Boolean(lesson))
  const lockedLessonCount = allLessons.filter(
    (lesson) => !derived.unlockedLessonSlugs.includes(lesson.slug),
  ).length

  const persistActivationWorkspace = useCallback(
    (lessonSlug: string, workspace: Parameters<typeof actions.setLessonWorkspace>[1]) =>
      actions.setLessonWorkspace(lessonSlug, workspace),
    [actions],
  )

  const activationLessonWorkspace = usePicoLessonWorkspace(
    activationLessonSlug ?? 'activation',
    activationLesson?.steps.length ?? 0,
    {
      progress,
      persistRemote: activationLessonSlug
        ? persistActivationWorkspace
        : undefined,
    },
  )

  const focusedActivationStep =
    activationLesson && activationLessonWorkspace.resumeStepIndex >= 0
      ? activationLesson.steps[activationLessonWorkspace.resumeStepIndex] ?? null
      : null
  const workspaceCaptured = isPicoLessonEvidenceMeaningful(
    activationLessonWorkspace.workspace.evidence,
  )
  const activationCompletionStatus = activationLesson
    ? getPicoLessonCompletionStatus(
        {
          ...progress,
          lessonWorkspaces: {
            ...progress.lessonWorkspaces,
            [activationLesson.slug]: activationLessonWorkspace.workspace,
          },
        },
        activationLesson.slug,
      )
    : null
  const workspaceUpdatedAt = formatTimestamp(activationLessonWorkspace.workspace.updatedAt, locale) ?? t('shared.notRecorded')
  const currentMissionTitle = activationLesson?.title ?? t('mission.titleFallback')
  const currentMissionSummary = activationLesson
    ? activationLesson.objective
    : t('mission.summaryFallback')
  const currentMissionValidation = activationLesson
    ? activationLesson.validation
    : t('mission.validationFallback')
  const currentMissionPrimaryHref = activationLessonSlug
    ? toHref(`/academy/${activationLessonSlug}`)
    : toHref('/autopilot')
  const currentMissionPrimaryLabel = activationLessonSlug
    ? !installDone
      ? t('mission.primary.installHermesNow')
      : !firstRunDone
        ? t('mission.primary.runFirstAgent')
        : nextLesson
          ? t('shared.continueWithNextLesson', { title: nextLesson.title })
          : t('mission.primary.openNextChapter')
    : t('mission.primary.openAutopilot')
  const currentMissionSecondaryHref = toHref(
    `/tutor${activationLessonSlug ? `?lesson=${activationLessonSlug}` : ''}`,
  )
  const currentMissionSecondaryLabel = activationLessonSlug
    ? t('shared.askTutorNextStep')
    : t('shared.askTutorRouteCorrection')
  const missionIndex =
    activationLesson && activeTrackLessons.length > 0
      ? Math.max(
          activeTrackLessons.findIndex((lesson) => lesson.slug === activationLesson.slug),
          0,
        ) + 1
      : 1

  const hostedStatus =
    session.status === 'authenticated'
      ? session.user.isEmailVerified === false
        ? t('shared.verifyHost')
        : t('shared.hostedAttached')
      : session.status === 'unauthenticated'
        ? t('syncState.localOnly')
        : session.status === 'error'
          ? t('shared.authError')
          : t('shared.checking')
  const hostedDetail =
    session.status === 'authenticated'
      ? session.user.email ?? session.user.name ?? t('shared.operator')
      : session.status === 'unauthenticated'
        ? t('shared.signInToPersist')
        : session.status === 'error'
          ? session.error
          : t('shared.readingHostState')
  const syncStateLabel = t(`syncState.${getSyncStateKey(syncState, ready)}`)

  const missionStrip = [
    {
      label: t('strip.missionState'),
      value: activationCompletionStatus?.isComplete
        ? t('shared.cleared')
        : activationCompletionStatus?.canComplete
          ? t('shared.ready')
          : activationLessonWorkspace.completedStepCount > 0
            ? t('shared.inProgress')
            : t('shared.ready'),
      detail: activationLesson
        ? t('shared.steps', { completed: activationLessonWorkspace.completedStepCount, total: activationLesson.steps.length })
        : t('shared.controlRoom'),
    },
    {
      label: t('strip.trackProgress'),
      value: `${activeTrackCompletionPercent}%`,
      detail: t('shared.lessons', { completed: activeTrackCompletedCount, total: activeTrackLessons.length }),
    },
    {
      label: t('strip.proof'),
      value: workspaceCaptured ? t('shared.captured') : t('shared.missing'),
      detail: focusedActivationStep?.title ?? t('shared.previewStep'),
    },
    {
      label: t('strip.hosted'),
      value: hostedStatus,
      detail: session.status === 'authenticated' ? syncStateLabel : hostedDetail,
    },
  ]

  const studioMethod = [
    {
      label: t('studio.steps.0.label'),
      title: t('studio.steps.0.title'),
      body: currentMissionSummary,
    },
    {
      label: t('studio.steps.1.label'),
      title: t('studio.steps.1.title'),
      body: activationLesson?.expectedResult ?? currentMissionValidation,
    },
    {
      label: t('studio.steps.2.label'),
      title: t('studio.steps.2.title'),
      body: currentMissionValidation,
    },
  ]

  const academyStandards = [
    {
      label: t('standards.trackOutcome'),
      value: activeTrack.outcome,
    },
    {
      label: t('standards.levelReward'),
      value: currentLevel?.projectOutcome ?? t('standards.levelRewardFallback'),
    },
    {
      label: t('standards.nextStandard'),
      value: currentLevel?.recommendedNextStep ?? t('standards.nextStandardFallback'),
    },
  ]

  const chapterPreviewTracks = progress.platform.railCollapsed
    ? []
    : localizedTracks.filter((track) => track.slug !== activeTrack.slug)
  const unlockedCapabilities = derived.unlockedCapabilities.map((capability) =>
    localizePicoCapability(capability, contentT),
  )
  const nextCapability = derived.nextCapability
    ? localizePicoCapability(derived.nextCapability, contentT)
    : null

  useEffect(() => {
    if (progress.platform.activeSurface !== 'academy') {
      actions.setPlatform({ activeSurface: 'academy' })
    }
  }, [actions, progress.platform.activeSurface])

  return (
    <PicoShell
      mode="academy"
      eyebrow={t('shell.eyebrow')}
      title={t('shell.title')}
      description={t('shell.description')}
      railCollapsed={progress.platform.railCollapsed}
      helpLaneOpen={progress.platform.helpLaneOpen}
      preferencesReady={ready}
      onToggleRail={() =>
        actions.setPlatform({ railCollapsed: !progress.platform.railCollapsed })
      }
      onToggleHelpLane={() =>
        actions.setPlatform({ helpLaneOpen: !progress.platform.helpLaneOpen })
      }
    >
      <FadeIn reduceMotion={reduceMotion}>
        <section
          className={picoCodexFrame('min-w-0 overflow-hidden px-4 py-6 sm:px-8 sm:py-8 lg:px-10 lg:py-10')}
          data-testid="pico-academy-mission-billboard"
        >
          <div className="grid min-w-0 gap-8 lg:grid-cols-[8rem,minmax(0,1fr)]">
            <div className="grid min-w-0 content-between gap-6 border-b border-[color:var(--pico-border)] pb-6 lg:border-b-0 lg:border-e lg:pb-0 lg:pe-8">
              <div className="grid gap-2">
                <p className={picoClasses.label}>{t('billboard.chapterLabel')}</p>
                <p className="font-[family:var(--font-site-display)] text-7xl leading-none tracking-[-0.08em] text-[color:var(--pico-accent)] sm:text-8xl">
                  {activeTrackChapter}
                </p>
              </div>

              <div className="grid gap-2">
                <p className={picoClasses.label}>{t('billboard.trackLabel')}</p>
                <p className="font-[family:var(--font-site-display)] text-3xl tracking-[-0.05em] text-[color:var(--pico-text)]">
                  {activeTrack.title}
                </p>
                <p className="text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                  {t('billboard.stopOf', { current: String(missionIndex).padStart(2, '0'), total: activeTrackLessons.length })}
                </p>
              </div>
            </div>

            <div className="grid min-w-0 gap-6">
              <div className="flex flex-wrap items-center gap-2">
                <span className={picoCodex.stamp}>{t('billboard.currentMission')}</span>
                <span className={picoCodex.stamp}>{hostedStatus}</span>
                {session.status === 'authenticated' && session.user.plan ? (
                  <span className={picoCodex.stamp}>
                    {t('shared.plan', { plan: session.user.plan.toLowerCase() })}
                  </span>
                ) : null}
                <span className={picoCodex.stamp}>{syncStateLabel}</span>
              </div>

              <div className="grid gap-4">
                <h1 className="max-w-4xl break-words font-[family:var(--font-site-display)] text-5xl leading-[0.92] tracking-[-0.08em] text-[color:var(--pico-text)] sm:text-7xl">
                  {currentMissionTitle}
                </h1>
                <p className="max-w-3xl text-lg leading-8 text-[color:var(--pico-text-secondary)]">
                  {currentMissionSummary}
                </p>
                <p className="max-w-3xl text-sm leading-6 text-[color:var(--pico-text-muted)]">
                  {t('billboard.validationPrefix')} {currentMissionValidation}
                </p>
              </div>

              <div className="grid gap-3 sm:flex sm:flex-wrap">
                <Link
                  href={currentMissionPrimaryHref}
                  className={cn(picoClasses.primaryButton, 'motion-reduce:transition-none')}
                >
                  {currentMissionPrimaryLabel}
                </Link>
                <Link
                  href={currentMissionSecondaryHref}
                  className={cn(picoClasses.secondaryButton, 'motion-reduce:transition-none')}
                >
                  {currentMissionSecondaryLabel}
                </Link>
              </div>

              <div
                className="grid gap-3 border-t border-[color:var(--pico-border)] pt-5 sm:grid-cols-2 xl:grid-cols-4"
                data-testid="pico-academy-progress-strip"
              >
                {missionStrip.map((item) => (
                  <div key={item.label} className="grid gap-1">
                    <p className={picoClasses.label}>{item.label}</p>
                    <p className="font-[family:var(--font-site-display)] text-2xl tracking-[-0.05em] text-[color:var(--pico-text)]">
                      {item.value}
                    </p>
                    <p className="text-sm leading-6 text-[color:var(--pico-text-secondary)]">{item.detail}</p>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </section>
      </FadeIn>

      {activationLesson ? (
        <FadeIn delay={0.08} reduceMotion={reduceMotion}>
          <section
            id="pico-academy-workspace-summary"
            className={picoCodexFrame('min-w-0 px-4 py-6 sm:px-8 sm:py-8')}
            data-testid="pico-academy-workspace-summary"
          >
            <div className="grid gap-6 lg:grid-cols-[minmax(0,1.1fr),minmax(18rem,0.9fr)]">
              <div className="grid gap-5">
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div>
                    <p className={picoClasses.label}>{t('workspace.activeProofLane')}</p>
                    <h2 className="mt-3 font-[family:var(--font-site-display)] text-4xl tracking-[-0.06em] text-[color:var(--pico-text)]">
                      {focusedActivationStep?.title ?? activationLesson.title}
                    </h2>
                  </div>
                  <span className={picoCodex.stamp}>
                    {t('shared.steps', { completed: activationLessonWorkspace.completedStepCount, total: activationLesson.steps.length })}
                  </span>
                </div>

                <div className={picoCodexSheet('p-5')}>
                  <p className={picoClasses.label}>{t('workspace.resumeFromHere')}</p>
                  <p className="mt-4 text-base leading-8 text-[color:var(--pico-text-secondary)]">
                    {focusedActivationStep?.body ??
                      t('shared.resumeBody')}
                  </p>
                  {focusedActivationStep?.command ? (
                    <pre className="mt-5 max-w-full overflow-x-auto rounded-[22px] border border-[color:var(--pico-border)] bg-[color:var(--pico-bg-input)] p-4 text-sm text-[color:var(--pico-accent-bright)]" dir="ltr">
                      <code>{focusedActivationStep.command}</code>
                    </pre>
                  ) : null}
                  <div
                    className="mt-5 overflow-hidden rounded-full bg-[color:var(--pico-bg-input)]"
                    role="progressbar"
                    aria-label={t('workspace.activeProofLane')}
                    aria-valuemin={0}
                    aria-valuemax={activationLesson.steps.length}
                    aria-valuenow={activationLessonWorkspace.completedStepCount}
                  >
                    <div
                      className="h-2 rounded-full bg-[linear-gradient(90deg,var(--pico-accent),var(--pico-accent-bright))]"
                      style={{ width: `${activationLessonWorkspace.progressPercent}%` }}
                    />
                  </div>
                  <div className="mt-5 flex flex-wrap gap-3">
                    <Link
                      href={currentMissionPrimaryHref}
                      className={cn(picoClasses.primaryButton, 'motion-reduce:transition-none')}
                    >
                      {t('shared.resumeMission')}
                    </Link>
                    <Link
                      href={currentMissionSecondaryHref}
                      className={cn(picoClasses.tertiaryButton, 'motion-reduce:transition-none')}
                    >
                      {t('shared.askTutor')}
                    </Link>
                  </div>
                </div>
              </div>

              <div className="grid gap-4">
                <div className={picoCodexInset('p-5')}>
                  <p className={picoClasses.label}>{t('workspace.proofState')}</p>
                  <p className="mt-3 font-[family:var(--font-site-display)] text-3xl tracking-[-0.05em] text-[color:var(--pico-text)]">
                    {workspaceCaptured ? t('workspace.proofCaptured') : t('workspace.proofMissing')}
                  </p>
                  <p className="mt-2 text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                    {t('shared.updated', { timestamp: workspaceUpdatedAt })}
                  </p>
                </div>

                <div className={picoCodexNote('p-5')}>
                  <p className={picoClasses.label}>{t('workspace.capturedProof')}</p>
                  <p className="mt-3 break-words text-sm leading-6 text-[color:var(--pico-text-secondary)] [overflow-wrap:anywhere]">
                    {workspaceCaptured
                      ? activationLessonWorkspace.workspace.evidence
                      : t('shared.noProofLogged')}
                  </p>
                </div>

                <div className={picoCodexInset('p-5')} role="status" aria-live="polite">
                  <p className={picoClasses.label}>{t('workspace.proofState')}</p>
                  <p className="mt-3 text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                    {activationCompletionStatus?.canComplete
                      ? t('shared.ready')
                      : t('shared.steps', { completed: activationLessonWorkspace.completedStepCount, total: activationLesson.steps.length })}
                  </p>
                </div>

                <div className={picoCodexInset('p-5')}>
                  <p className={picoClasses.label}>{t('workspace.hostedNote')}</p>
                  <p className="mt-3 text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                    {hostedDetail}
                  </p>
                </div>
              </div>
            </div>
          </section>
        </FadeIn>
      ) : null}

      <FadeIn delay={0.1} reduceMotion={reduceMotion}>
        <section
          className={picoCodexFrame('min-w-0 px-4 py-6 sm:px-8 sm:py-8')}
          data-testid="pico-academy-studio-method"
        >
          <div className="grid gap-6 lg:grid-cols-[minmax(0,1.08fr),20rem]">
            <div>
              <div className="flex flex-wrap items-center justify-between gap-4">
                <div>
                  <p className={picoClasses.label}>{t('studio.label')}</p>
                  <h2 className="mt-3 font-[family:var(--font-site-display)] text-4xl tracking-[-0.06em] text-[color:var(--pico-text)]">
                    {t('studio.title')}
                  </h2>
                </div>
                <span className={picoCodex.stamp}>{t('studio.stamp')}</span>
              </div>

              <div className="mt-6 grid gap-4 xl:grid-cols-3">
                {studioMethod.map((item) => (
                  <article key={item.label} className={picoCodexInset('flex h-full flex-col p-5')}>
                    <p className={picoClasses.label}>{item.label}</p>
                    <h3 className="mt-5 font-[family:var(--font-site-display)] text-3xl tracking-[-0.05em] text-[color:var(--pico-text)]">
                      {item.title}
                    </h3>
                    <p className="mt-4 text-sm leading-7 text-[color:var(--pico-text-secondary)]">
                      {item.body}
                    </p>
                  </article>
                ))}
              </div>
            </div>

            <div className="grid gap-4">
              <div className={picoCodexNote('p-5')}>
                <p className={picoClasses.label}>{t('standards.label')}</p>
                <div className="mt-4 grid gap-4">
                  {academyStandards.map((item) => (
                    <div
                      key={item.label}
                      className="grid gap-2 border-t border-[color:var(--pico-border)] pt-4 first:border-t-0 first:pt-0"
                    >
                      <p className={picoClasses.label}>{item.label}</p>
                      <p className="text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                        {item.value}
                      </p>
                    </div>
                  ))}
                </div>
              </div>

              <div className={picoCodexInset('p-5')}>
                <p className={picoClasses.label}>{t('chapterLedger.chapterChecklist')}</p>
                <div className="mt-4 grid gap-3">
                  {activeTrack.checklist.map((item) => (
                    <div key={item} className="flex items-start gap-3">
                      <span className="mt-1 inline-flex h-6 w-6 items-center justify-center rounded-full border border-[color:var(--pico-border)] bg-[rgba(var(--pico-accent-rgb),0.12)] text-[10px] font-semibold uppercase tracking-[0.16em] text-[color:var(--pico-accent)]">
                        {t('shared.ok')}
                      </span>
                      <p className="text-sm leading-6 text-[color:var(--pico-text-secondary)]">{item}</p>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </section>
      </FadeIn>

      <FadeIn delay={0.12} reduceMotion={reduceMotion}>
        <section
          className={picoCodexFrame('overflow-hidden')}
          data-testid="pico-academy-campaign-map"
        >
          <div className="border-b border-[color:var(--pico-border)] px-6 py-6 sm:px-8 lg:px-10">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <p className={picoClasses.label}>{t('chapterLedger.label')}</p>
                <h2 className="mt-3 max-w-4xl font-[family:var(--font-site-display)] text-4xl tracking-[-0.06em] text-[color:var(--pico-text)] sm:text-5xl">
                  {t('chapterLedger.title')}
                </h2>
              </div>
              <span className={picoCodex.stamp}>
                {progress.platform.railCollapsed ? t('chapterLedger.focusMode') : t('chapterLedger.guidedAtlas')}
              </span>
            </div>
            <p className="mt-3 max-w-3xl text-sm leading-6 text-[color:var(--pico-text-secondary)]">
              {t('chapterLedger.body')}
            </p>
          </div>

          <div className="grid gap-0 xl:grid-cols-[minmax(0,1.08fr),22rem]">
            <div className="px-6 py-6 sm:px-8 lg:px-10 lg:py-8">
              <motion.article
                initial={reduceMotion ? false : { opacity: 0, y: 14 }}
                animate={{ opacity: 1, y: 0 }}
                transition={reduceMotion ? { duration: 0 } : { duration: 0.45, delay: 0.04 }}
                className="grid gap-6"
                data-motion={reduceMotion ? 'reduced' : 'full'}
                data-pico-academy-motion
              >
                <div className="grid gap-5 lg:grid-cols-[16rem,minmax(0,1fr)]">
                  <div className="grid gap-3">
                    <div className="flex items-center gap-3">
                      <span className={picoCodex.stamp}>
                        {t('shared.track', { number: String(activeTrackIndex + 1).padStart(2, '0') })}
                      </span>
                      <span className={picoCodex.stamp}>{t('chapterLedger.dominantStop')}</span>
                    </div>
                    <h3 className="font-[family:var(--font-site-display)] text-5xl tracking-[-0.06em] text-[color:var(--pico-text)]">
                      {activeTrack.title}
                    </h3>
                    <p className="text-sm leading-6 text-[color:var(--pico-text-secondary)]">{activeTrack.outcome}</p>
                    <p className="text-sm leading-6 text-[color:var(--pico-text-muted)]">{activeTrack.intro}</p>
                    <div className="grid gap-3 pt-2">
                      <div className={picoCodexInset('p-4')}>
                        <p className={picoClasses.label}>{t('chapterLedger.routeState')}</p>
                        <p className="mt-2 text-lg font-medium text-[color:var(--pico-text)]">
                          {t('shared.clearedCount', { completed: activeTrackCompletedCount, total: activeTrackLessons.length })}
                        </p>
                      </div>
                      <div className={picoCodexInset('p-4')}>
                        <p className={picoClasses.label}>{t('chapterLedger.nextDominantStop')}</p>
                        <p className="mt-2 text-lg font-medium text-[color:var(--pico-text)]">
                          {activationLesson?.title ?? t('chapterLedger.openAutopilot')}
                        </p>
                      </div>
                    </div>
                  </div>

                  <div className="relative ps-6">
                    <div className="absolute start-2 top-1 bottom-1 w-px bg-[color:var(--pico-border)]" />

                    <div className="grid gap-5">
                      {activeTrackLessons.map((lesson, lessonIndex) => {
                        const state = getLessonState(
                          lesson,
                          progress.completedLessons,
                          derived.unlockedLessonSlugs,
                          activationLessonSlug,
                        )
                        const dominant =
                          lesson.slug === activationLessonSlug ||
                          state === 'current' ||
                          (state === 'ready' && lessonIndex === 0)

                        return (
                          <Link
                            key={lesson.slug}
                            href={toHref(`/academy/${lesson.slug}`)}
                            className={cn(
                              'relative block border-s py-1 pe-2 ps-5 transition motion-reduce:transition-none',
                              state === 'locked'
                                ? 'border-[color:var(--pico-border)] text-[color:var(--pico-text-muted)]'
                                : dominant
                                  ? 'border-[color:var(--pico-accent)] text-[color:var(--pico-text)]'
                                  : state === 'done'
                                    ? 'border-[color:var(--pico-border-hover)] text-[color:var(--pico-text-secondary)]'
                                    : 'border-[color:var(--pico-border)] text-[color:var(--pico-text-secondary)] hover:border-[color:var(--pico-border-hover)] hover:text-[color:var(--pico-text)]',
                            )}
                          >
                            <span
                              className={cn(
                                'absolute -start-[0.42rem] top-4 h-3.5 w-3.5 rounded-full border bg-[color:var(--pico-bg)]',
                                state === 'done' && 'border-emerald-400 bg-emerald-500/20',
                                state === 'current' &&
                                  'border-[color:var(--pico-accent)] bg-[rgba(var(--pico-accent-rgb),0.2)]',
                                state === 'ready' && 'border-cyan-400 bg-cyan-400/15',
                                state === 'locked' && 'border-[color:var(--pico-border)]',
                              )}
                            />

                            <div className="flex flex-wrap items-start justify-between gap-3">
                              <div className="min-w-0">
                                <p className="font-[family:var(--font-mono)] text-[11px] uppercase tracking-[0.22em] text-[color:var(--pico-text-muted)]">
                                  {t('chapterLedger.stopLevel', { number: String(lessonIndex + 1).padStart(2, '0'), level: lesson.level })}
                                </p>
                                <p className="mt-1 font-[family:var(--font-site-display)] text-2xl tracking-[-0.05em] text-inherit">
                                  {lesson.title}
                                </p>
                              </div>
                              <LessonStateStamp state={state} />
                            </div>

                            {dominant ? (
                              <div className={picoCodexNote('mt-3 p-4')}>
                                <p className={picoClasses.label}>{t('chapterLedger.dominantStop')}</p>
                                <p className="mt-3 text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                                  {lesson.expectedResult}
                                </p>
                              </div>
                            ) : (
                              <p className="mt-2 text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                                {lesson.summary}
                              </p>
                            )}
                          </Link>
                        )
                      })}
                    </div>
                  </div>
                </div>
              </motion.article>
            </div>

            <aside className="border-t border-[color:var(--pico-border)] bg-[rgba(5,14,8,0.62)] px-6 py-6 sm:px-8 xl:border-s xl:border-t-0">
              <div className="grid gap-4">
                <div className={picoCodexInset('p-5')}>
                  <p className={picoClasses.label}>{t('chapterLedger.missionCorrection')}</p>
                  <p className="mt-3 text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                    {t('chapterLedger.missionCorrectionBody')}
                  </p>
                  <div className="mt-4 grid gap-3">
                    <Link
                      href={currentMissionPrimaryHref}
                      className={cn(picoClasses.primaryButton, 'motion-reduce:transition-none')}
                    >
                      {currentMissionPrimaryLabel}
                    </Link>
                    <Link
                      href={currentMissionSecondaryHref}
                      className={cn(picoClasses.tertiaryButton, 'motion-reduce:transition-none')}
                    >
                      {currentMissionSecondaryLabel}
                    </Link>
                  </div>
                </div>

                {!progress.platform.railCollapsed && chapterPreviewTracks.length > 0 ? (
                  <div className={picoCodexNote('p-5')}>
                    <p className={picoClasses.label}>{t('chapterLedger.otherChapters')}</p>
                    <div className="mt-4 grid gap-3">
                      {chapterPreviewTracks.map((track, trackIndex) => {
                        const trackLessons = track.lessons
                          .map((slug) => getLessonBySlug(slug))
                          .filter((lesson): lesson is PicoLesson => Boolean(lesson))
                        const completedCount = trackLessons.filter((lesson) =>
                          progress.completedLessons.includes(lesson.slug),
                        ).length
                        const unlocked = derived.unlockedTrackSlugs.includes(track.slug)

                        return (
                          <article key={track.slug} className={picoCodexInset('grid gap-3 p-4')}>
                            <div className="flex items-start justify-between gap-3">
                              <div>
                                <p className={picoClasses.label}>
                                  {t('shared.track', { number: String(trackIndex + 2).padStart(2, '0') })}
                                </p>
                                <h3 className="mt-2 font-[family:var(--font-site-display)] text-2xl tracking-[-0.05em] text-[color:var(--pico-text)]">
                                  {track.title}
                                </h3>
                              </div>
                              <span className={picoCodex.stamp}>{unlocked ? t('shared.open') : t('shared.locked')}</span>
                            </div>
                            <p className="text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                              {track.outcome}
                            </p>
                            <p className="text-xs uppercase tracking-[0.18em] text-[color:var(--pico-text-muted)]">
                              {t('shared.clearedCount', { completed: completedCount, total: trackLessons.length })}
                            </p>
                          </article>
                        )
                      })}
                    </div>
                  </div>
                ) : null}
              </div>
            </aside>
          </div>
        </section>
      </FadeIn>

      <FadeIn delay={0.18} reduceMotion={reduceMotion}>
        <section className={picoCodexFrame('px-6 py-6 sm:px-8')}>
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <p className={picoClasses.label}>{t('referenceAnnex.label')}</p>
              <h2 className="mt-3 font-[family:var(--font-site-display)] text-3xl tracking-[-0.05em] text-[color:var(--pico-text)]">
                {t('referenceAnnex.title')}
              </h2>
            </div>
            <span className={picoCodex.stamp}>
              {currentLevel ? currentLevel.title : contentT('levels.0.title')} • {lockedLessonCount} {t('referenceAnnex.locked')}
            </span>
          </div>

          <div className="mt-6 grid gap-6 xl:grid-cols-[minmax(0,1.04fr),minmax(0,0.96fr)]">
            <div className="grid gap-5">
              <div className={picoCodexInset('p-5')}>
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <p className={picoClasses.label}>{t('capabilities.label')}</p>
                    <p className="mt-2 text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                      {t('capabilities.body')}
                    </p>
                  </div>
                  <span className={picoCodex.stamp}>
                    {unlockedCapabilities.length} {t('capabilities.liveSuffix')}
                  </span>
                </div>
                <div className="mt-4 grid gap-4">
                  {unlockedCapabilities.slice(0, 2).map((capability) => (
                    <div
                      key={capability.id}
                      className="grid gap-2 border-t border-[color:var(--pico-border)] pt-4 first:border-t-0 first:pt-0"
                    >
                      <div className="flex flex-wrap items-center justify-between gap-3">
                        <h3 className="font-[family:var(--font-site-display)] text-2xl tracking-[-0.05em] text-[color:var(--pico-text)]">
                          {capability.title}
                        </h3>
                        <span className={picoCodex.stamp}>{t('capabilities.live')}</span>
                      </div>
                      <p className="text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                        {capability.description}
                      </p>
                      <Link
                        href={toHref(capability.href)}
                        className={cn(picoClasses.secondaryButton, 'motion-reduce:transition-none')}
                      >
                        {capability.actionLabel}
                      </Link>
                    </div>
                  ))}

                  {unlockedCapabilities.length === 0 ? (
                    <p className="text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                      {t('capabilities.firstUnlockEmpty')}
                    </p>
                  ) : null}
                </div>
              </div>

              <div className="grid gap-5 lg:grid-cols-2">
                {nextCapability ? (
                  <div className={picoCodexNote('p-5')}>
                    <p className={picoClasses.label}>{t('capabilities.nextUnlock')}</p>
                    <h3 className="mt-3 font-[family:var(--font-site-display)] text-2xl tracking-[-0.05em] text-[color:var(--pico-text)]">
                      {nextCapability.title}
                    </h3>
                    <p className="mt-3 text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                      {nextCapability.description}
                    </p>
                    <Link
                      href={toHref(nextCapability.href)}
                      className={cn(
                        picoClasses.primaryButton,
                        'mt-4 motion-reduce:transition-none',
                      )}
                    >
                      {nextCapability.actionLabel}
                    </Link>
                  </div>
                ) : null}

                <div className={picoCodexInset('p-5')}>
                  <p className={picoClasses.label}>{t('capabilities.patternArchive')}</p>
                  <div className="mt-4 grid gap-4">
                    {PICO_SHOWCASE_PATTERNS.slice(0, 2).map((pattern, patternIndex) => (
                      <div
                        key={pattern.lessonSlug}
                        className="grid gap-2 border-t border-[color:var(--pico-border)] pt-4 first:border-t-0 first:pt-0"
                      >
                        <p className="font-[family:var(--font-site-display)] text-2xl tracking-[-0.05em] text-[color:var(--pico-text)]">
                          {contentT(`showcasePatterns.${patternIndex}.title`)}
                        </p>
                        <p className="text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                          {contentT(`showcasePatterns.${patternIndex}.summary`)}
                        </p>
                        <Link
                          href={toHref(`/academy/${pattern.lessonSlug}`)}
                          className={cn(picoClasses.tertiaryButton, 'motion-reduce:transition-none')}
                        >
                          {t('capabilities.openPatternLesson')}
                        </Link>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </div>

            <div className="grid gap-5">
              <div className={picoCodexInset('p-5')}>
                <p className={picoClasses.label}>{t('capabilities.fieldNotes')}</p>
                <div className="mt-4 grid gap-4">
                  {PICO_RELEASE_NOTES.slice(0, 2).map((note, noteIndex) => (
                    <div
                      key={`${note.date}-${note.title}`}
                      className="grid gap-2 border-t border-[color:var(--pico-border)] pt-4 first:border-t-0 first:pt-0"
                    >
                      <div className="flex flex-wrap items-center justify-between gap-3">
                        <p className="font-[family:var(--font-site-display)] text-2xl tracking-[-0.05em] text-[color:var(--pico-text)]">
                          {contentT(`releaseNotes.${noteIndex}.title`)}
                        </p>
                        <span className={picoCodex.stamp}>{note.date}</span>
                      </div>
                      <p className="text-sm leading-6 text-[color:var(--pico-text-secondary)]">{contentT(`releaseNotes.${noteIndex}.body`)}</p>
                    </div>
                  ))}
                </div>
              </div>

              <details className={picoCodexSheet('group p-5')}>
                <summary
                  aria-controls="pico-academy-platform-settings"
                  className="flex cursor-pointer list-none items-center justify-between gap-4 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-[color:var(--pico-text)] [&::-webkit-details-marker]:hidden"
                >
                  <div>
                    <p className={picoClasses.label}>{t('referenceAnnex.setup')}</p>
                    <p className="mt-3 text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                      {t('referenceAnnex.body')}
                    </p>
                  </div>
                  <span className={picoCodex.stamp}>{t('shared.open')}</span>
                </summary>
                <div
                  id="pico-academy-platform-settings"
                  role="region"
                  aria-label={t('referenceAnnex.setup')}
                  className="mt-5 border-t border-[color:var(--pico-border)] pt-5"
                >
                  <PicoPlatformSurface
                    session={session}
                    progress={progress}
                    derived={derived}
                    syncState={syncState}
                    ready={ready}
                    onSave={(patch) => actions.setPlatform(patch)}
                    onReset={() =>
                      actions.setPlatform({
                        activeSurface: 'academy',
                        lastOpenedLessonSlug: null,
                        railCollapsed: false,
                        helpLaneOpen: false,
                      })
                    }
                    currentPath={pathname}
                  />
                </div>
              </details>
            </div>
          </div>
        </section>
      </FadeIn>
    </PicoShell>
  )
}
