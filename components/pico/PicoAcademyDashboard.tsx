'use client'

import { type ReactNode, useEffect } from 'react'
import Link from 'next/link'
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
  getTrackBySlug,
  type PicoLesson,
} from '@/lib/pico/academy'
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
    >
      {children}
    </motion.div>
  )
}

function LessonStateStamp({ state }: { state: LessonState }) {
  const copy =
    state === 'done'
      ? 'cleared'
      : state === 'current'
        ? 'current'
        : state === 'ready'
          ? 'ready'
          : 'locked'

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

function formatSyncState(syncState: string, ready: boolean) {
  if (!ready) {
    return 'hydrating'
  }

  switch (syncState) {
    case 'synced':
      return 'live'
    case 'saving':
      return 'saving'
    case 'offline':
      return 'local only'
    default:
      return syncState
  }
}

function formatTimestamp(value?: string | null) {
  if (!value) {
    return 'not recorded'
  }

  const parsed = new Date(value)

  if (Number.isNaN(parsed.getTime())) {
    return 'not recorded'
  }

  return parsed.toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  })
}

export function PicoAcademyDashboard() {
  const pathname = usePathname()
  const session = usePicoSession()
  const { progress, derived, syncState, ready, actions } = usePicoProgress()
  const toHref = usePicoHref()
  const reduceMotion = useReducedMotion() ?? false

  const nextLesson = derived.nextLesson
  const installDone = progress.completedLessons.includes('install-hermes-locally')
  const firstRunDone = progress.completedLessons.includes('run-your-first-agent')
  const activationLessonSlug = firstRunDone
    ? (nextLesson?.slug ?? null)
    : installDone
      ? 'run-your-first-agent'
      : 'install-hermes-locally'
  const activationLesson = activationLessonSlug ? getLessonBySlug(activationLessonSlug) : null
  const fallbackTrack = PICO_TRACKS[0]
  const activeTrack = getTrackBySlug(progress.selectedTrack ?? fallbackTrack.slug) ?? fallbackTrack
  const activeTrackLessons = activeTrack.lessons
    .map((slug) => getLessonBySlug(slug))
    .filter((lesson): lesson is PicoLesson => Boolean(lesson))
  const activeTrackIndex = Math.max(
    PICO_TRACKS.findIndex((track) => track.slug === activeTrack.slug),
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
  const currentLevel = PICO_LEVELS.find((level) => level.id === derived.currentLevel)
  const allLessons = PICO_TRACKS.flatMap((track) => track.lessons)
    .map((slug) => getLessonBySlug(slug))
    .filter((lesson): lesson is PicoLesson => Boolean(lesson))
  const lockedLessonCount = allLessons.filter(
    (lesson) => !derived.unlockedLessonSlugs.includes(lesson.slug),
  ).length

  const activationLessonWorkspace = usePicoLessonWorkspace(
    activationLessonSlug ?? 'activation',
    activationLesson?.steps.length ?? 0,
    {
      progress,
      persistRemote: activationLessonSlug
        ? (lessonSlug, workspace) => actions.setLessonWorkspace(lessonSlug, workspace)
        : undefined,
    },
  )

  const focusedActivationStep =
    activationLesson && activationLessonWorkspace.workspace.activeStepIndex >= 0
      ? activationLesson.steps[activationLessonWorkspace.workspace.activeStepIndex] ?? null
      : null
  const workspaceCaptured = Boolean(activationLessonWorkspace.workspace.evidence.trim())
  const workspaceUpdatedAt = formatTimestamp(activationLessonWorkspace.workspace.updatedAt)
  const currentMissionTitle = activationLesson?.title ?? 'Open Autopilot'
  const currentMissionSummary = activationLesson
    ? activationLesson.objective
    : 'Open Autopilot after the first setup steps are complete.'
  const currentMissionValidation = activationLesson
    ? activationLesson.validation
    : 'Use the runtime when the question is no longer about reading the lesson.'
  const currentMissionPrimaryHref = activationLessonSlug
    ? toHref(`/academy/${activationLessonSlug}`)
    : toHref('/autopilot')
  const currentMissionPrimaryLabel = activationLessonSlug
    ? !installDone
      ? 'Install Hermes now'
      : !firstRunDone
        ? 'Run your first agent'
        : nextLesson
          ? `Continue with ${nextLesson.title}`
          : 'Open the next lesson'
    : 'Open Autopilot'
  const currentMissionSecondaryHref = toHref(
    `/tutor${activationLessonSlug ? `?lesson=${activationLessonSlug}` : ''}`,
  )
  const currentMissionSecondaryLabel = activationLessonSlug
    ? 'Ask tutor for the exact next step'
    : 'Ask tutor for setup help'
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
        ? 'verify host'
        : 'hosted attached'
      : session.status === 'unauthenticated'
        ? 'local only'
        : session.status === 'error'
          ? 'auth error'
          : 'checking'
  const hostedDetail =
    session.status === 'authenticated'
      ? session.user.email ?? session.user.name ?? 'user'
      : session.status === 'unauthenticated'
        ? 'sign in to persist'
        : session.status === 'error'
          ? session.error
          : 'reading host state'

  const missionStrip = [
    {
      label: 'Lesson state',
      value: workspaceCaptured
        ? 'saved'
        : activationLessonWorkspace.completedStepCount > 0
          ? 'in progress'
          : 'ready',
      detail: activationLesson
        ? `${activationLessonWorkspace.completedStepCount}/${activationLesson.steps.length} steps`
        : 'autopilot',
    },
    {
      label: 'Track progress',
      value: `${activeTrackCompletionPercent}%`,
      detail: `${activeTrackCompletedCount}/${activeTrackLessons.length} lessons`,
    },
    {
      label: 'Output',
      value: workspaceCaptured ? 'saved' : 'missing',
      detail: focusedActivationStep?.title ?? 'Pick the next visible step',
    },
    {
      label: 'Hosted',
      value: hostedStatus,
      detail: session.status === 'authenticated' ? formatSyncState(syncState, ready) : hostedDetail,
    },
  ]

  const studioMethod = [
    {
      label: '01 • Brief',
      title: 'Read the setup step',
      body: currentMissionSummary,
    },
    {
      label: '02 • Deliverable',
      title: 'Save one useful output',
      body: activationLesson?.expectedResult ?? currentMissionValidation,
    },
    {
      label: '03 • Critique',
      title: 'Use the validation as the check',
      body: currentMissionValidation,
    },
  ]

  const academyStandards = [
    {
      label: 'Track outcome',
      value: activeTrack.outcome,
    },
    {
      label: 'Level reward',
      value: currentLevel?.projectOutcome ?? 'Ship one working setup outcome.',
    },
    {
      label: 'Next standard',
      value: currentLevel?.recommendedNextStep ?? 'Keep the chapter narrow and practical.',
    },
  ]

  const chapterPreviewTracks = progress.platform.railCollapsed
    ? []
    : PICO_TRACKS.filter((track) => track.slug !== activeTrack.slug)

  useEffect(() => {
    if (progress.platform.activeSurface !== 'academy') {
      actions.setPlatform({ activeSurface: 'academy' })
    }
  }, [actions, progress.platform.activeSurface])

  return (
    <PicoShell
      mode="academy"
      eyebrow="Academy"
      title="Academy"
      description="One setup step, one saved output, one next move."
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
          className={picoCodexFrame('overflow-hidden px-6 py-6 sm:px-8 sm:py-8 lg:px-10 lg:py-10')}
          data-testid="pico-academy-mission-billboard"
        >
          <div className="grid gap-8 lg:grid-cols-[8rem,minmax(0,1fr)]">
            <div className="grid content-between gap-6 border-b border-[color:var(--pico-border)] pb-6 lg:border-b-0 lg:border-r lg:pb-0 lg:pr-8">
              <div className="grid gap-2">
                <p className={picoClasses.label}>Chapter</p>
                <p className="font-[family:var(--font-site-display)] text-7xl leading-none tracking-[-0.08em] text-[color:var(--pico-accent)] sm:text-8xl">
                  {activeTrackChapter}
                </p>
              </div>

              <div className="grid gap-2">
                <p className={picoClasses.label}>Track</p>
                <p className="font-[family:var(--font-site-display)] text-3xl tracking-[-0.05em] text-[color:var(--pico-text)]">
                  {activeTrack.title}
                </p>
                <p className="text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                  Stop {String(missionIndex).padStart(2, '0')} of {activeTrackLessons.length}
                </p>
              </div>
            </div>

            <div className="grid gap-6">
              <div className="flex flex-wrap items-center gap-2">
                <span className={picoCodex.stamp}>Current lesson</span>
                <span className={picoCodex.stamp}>{hostedStatus}</span>
                {session.status === 'authenticated' && session.user.plan ? (
                  <span className={picoCodex.stamp}>
                    {session.user.plan.toLowerCase()} plan
                  </span>
                ) : null}
                <span className={picoCodex.stamp}>{formatSyncState(syncState, ready)}</span>
              </div>

              <div className="grid gap-4">
                <h1 className="max-w-4xl font-[family:var(--font-site-display)] text-5xl leading-[0.92] tracking-[-0.08em] text-[color:var(--pico-text)] sm:text-7xl">
                  {currentMissionTitle}
                </h1>
                <p className="max-w-3xl text-lg leading-8 text-[color:var(--pico-text-secondary)]">
                  {currentMissionSummary}
                </p>
                <p className="max-w-3xl text-sm leading-6 text-[color:var(--pico-text-muted)]">
                  Validation: {currentMissionValidation}
                </p>
              </div>

              <div className="grid gap-3 sm:flex sm:flex-wrap">
                <Link href={currentMissionPrimaryHref} className={picoClasses.primaryButton}>
                  {currentMissionPrimaryLabel}
                </Link>
                <Link href={currentMissionSecondaryHref} className={picoClasses.secondaryButton}>
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
            className={picoCodexFrame('px-6 py-6 sm:px-8 sm:py-8')}
            data-testid="pico-academy-workspace-summary"
          >
            <div className="grid gap-6 lg:grid-cols-[minmax(0,1.1fr),minmax(18rem,0.9fr)]">
              <div className="grid gap-5">
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div>
                    <p className={picoClasses.label}>Active setup step</p>
                    <h2 className="mt-3 font-[family:var(--font-site-display)] text-4xl tracking-[-0.06em] text-[color:var(--pico-text)]">
                      {focusedActivationStep?.title ?? activationLesson.title}
                    </h2>
                  </div>
                  <span className={picoCodex.stamp}>
                    {activationLessonWorkspace.completedStepCount}/{activationLesson.steps.length} steps
                  </span>
                </div>

                <div className={picoCodexSheet('p-5')}>
                  <p className={picoClasses.label}>Resume from here</p>
                  <p className="mt-4 text-base leading-8 text-[color:var(--pico-text-secondary)]">
                    {focusedActivationStep?.body ??
                      'Open the lesson and finish the next setup step.'}
                  </p>
                  {focusedActivationStep?.command ? (
                    <pre className="mt-5 overflow-x-auto rounded-[22px] border border-[color:var(--pico-border)] bg-[color:var(--pico-bg-input)] p-4 text-sm text-[color:var(--pico-accent-bright)]">
                      <code>{focusedActivationStep.command}</code>
                    </pre>
                  ) : null}
                  <div className="mt-5 overflow-hidden rounded-full bg-[color:var(--pico-bg-input)]">
                    <div
                      className="h-2 rounded-full bg-[linear-gradient(90deg,var(--pico-accent),var(--pico-accent-bright))]"
                      style={{ width: `${activationLessonWorkspace.progressPercent}%` }}
                    />
                  </div>
                  <div className="mt-5 flex flex-wrap gap-3">
                    <Link href={currentMissionPrimaryHref} className={picoClasses.primaryButton}>
                      Resume lesson
                    </Link>
                    <Link href={currentMissionSecondaryHref} className={picoClasses.tertiaryButton}>
                      Ask tutor
                    </Link>
                  </div>
                </div>
              </div>

              <div className="grid gap-4">
                <div className={picoCodexInset('p-5')}>
                  <p className={picoClasses.label}>Output state</p>
                  <p className="mt-3 font-[family:var(--font-site-display)] text-3xl tracking-[-0.05em] text-[color:var(--pico-text)]">
                    {workspaceCaptured ? 'saved' : 'missing'}
                  </p>
                  <p className="mt-2 text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                    Updated {workspaceUpdatedAt}
                  </p>
                </div>

                <div className={picoCodexNote('p-5')}>
                  <p className={picoClasses.label}>Saved output</p>
                  <p className="mt-3 text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                    {workspaceCaptured
                      ? activationLessonWorkspace.workspace.evidence
                      : 'No output has been saved yet. Save the command result, transcript, or file path before moving on.'}
                  </p>
                </div>

                <div className={picoCodexInset('p-5')}>
                  <p className={picoClasses.label}>Hosted note</p>
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
          className={picoCodexFrame('px-6 py-6 sm:px-8 sm:py-8')}
          data-testid="pico-academy-studio-method"
        >
          <div className="grid gap-6 lg:grid-cols-[minmax(0,1.08fr),20rem]">
            <div>
              <div className="flex flex-wrap items-center justify-between gap-4">
                <div>
                  <p className={picoClasses.label}>Academy method</p>
                  <h2 className="mt-3 font-[family:var(--font-site-display)] text-4xl tracking-[-0.06em] text-[color:var(--pico-text)]">
                    Finish the setup in small steps
                  </h2>
                </div>
                <span className={picoCodex.stamp}>brief • output • check</span>
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
                <p className={picoClasses.label}>Track standards</p>
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
                <p className={picoClasses.label}>Chapter checklist</p>
                <div className="mt-4 grid gap-3">
                  {activeTrack.checklist.map((item) => (
                    <div key={item} className="flex items-start gap-3">
                      <span className="mt-1 inline-flex h-6 w-6 items-center justify-center rounded-full border border-[color:var(--pico-border)] bg-[rgba(var(--pico-accent-rgb),0.12)] text-[10px] font-semibold uppercase tracking-[0.16em] text-[color:var(--pico-accent)]">
                        ok
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
                <p className={picoClasses.label}>Chapter map</p>
                <h2 className="mt-3 max-w-4xl font-[family:var(--font-site-display)] text-4xl tracking-[-0.06em] text-[color:var(--pico-text)] sm:text-5xl">
                  Work on the current chapter first.
                </h2>
              </div>
              <span className={picoCodex.stamp}>
                {progress.platform.railCollapsed ? 'focus mode' : 'guided map'}
              </span>
            </div>
            <p className="mt-3 max-w-3xl text-sm leading-6 text-[color:var(--pico-text-secondary)]">
              Stay on the current track without losing sight of what comes next.
            </p>
          </div>

          <div className="grid gap-0 xl:grid-cols-[minmax(0,1.08fr),22rem]">
            <div className="px-6 py-6 sm:px-8 lg:px-10 lg:py-8">
              <motion.article
                initial={reduceMotion ? false : { opacity: 0, y: 14 }}
                animate={{ opacity: 1, y: 0 }}
                transition={reduceMotion ? { duration: 0 } : { duration: 0.45, delay: 0.04 }}
                className="grid gap-6"
              >
                <div className="grid gap-5 lg:grid-cols-[16rem,minmax(0,1fr)]">
                  <div className="grid gap-3">
                    <div className="flex items-center gap-3">
                      <span className={picoCodex.stamp}>
                        Track {String(activeTrackIndex + 1).padStart(2, '0')}
                      </span>
                      <span className={picoCodex.stamp}>Signal 02</span>
                    </div>
                    <h3 className="font-[family:var(--font-site-display)] text-5xl tracking-[-0.06em] text-[color:var(--pico-text)]">
                      {activeTrack.title}
                    </h3>
                    <p className="text-sm leading-6 text-[color:var(--pico-text-secondary)]">{activeTrack.outcome}</p>
                    <p className="text-sm leading-6 text-[color:var(--pico-text-muted)]">{activeTrack.intro}</p>
                    <div className="grid gap-3 pt-2">
                      <div className={picoCodexInset('p-4')}>
                        <p className={picoClasses.label}>Track state</p>
                        <p className="mt-2 text-lg font-medium text-[color:var(--pico-text)]">
                          {activeTrackCompletedCount}/{activeTrackLessons.length} cleared
                        </p>
                      </div>
                      <div className={picoCodexInset('p-4')}>
                        <p className={picoClasses.label}>Next stop</p>
                        <p className="mt-2 text-lg font-medium text-[color:var(--pico-text)]">
                          {activationLesson?.title ?? 'Open Autopilot'}
                        </p>
                      </div>
                    </div>
                  </div>

                  <div className="relative pl-6">
                    <div className="absolute left-2 top-1 bottom-1 w-px bg-[color:var(--pico-border)]" />

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
                              'relative block border-l pl-5 pr-2 py-1 transition',
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
                                'absolute -left-[0.42rem] top-4 h-3.5 w-3.5 rounded-full border bg-[color:var(--pico-bg)]',
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
                                  Stop {String(lessonIndex + 1).padStart(2, '0')} • level {lesson.level}
                                </p>
                                <p className="mt-1 font-[family:var(--font-site-display)] text-2xl tracking-[-0.05em] text-inherit">
                                  {lesson.title}
                                </p>
                              </div>
                              <LessonStateStamp state={state} />
                            </div>

                            {dominant ? (
                              <div className={picoCodexNote('mt-3 p-4')}>
                                <p className={picoClasses.label}>Current stop</p>
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

            <aside className="border-t border-[color:var(--pico-border)] bg-[rgba(5,14,8,0.62)] px-6 py-6 sm:px-8 xl:border-l xl:border-t-0">
              <div className="grid gap-4">
                <div className={picoCodexInset('p-5')}>
                  <p className={picoClasses.label}>Setup correction</p>
                  <p className="mt-3 text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                    The map is useful only when it brings you back to the current setup step.
                  </p>
                  <div className="mt-4 grid gap-3">
                    <Link href={currentMissionPrimaryHref} className={picoClasses.primaryButton}>
                      {currentMissionPrimaryLabel}
                    </Link>
                    <Link href={currentMissionSecondaryHref} className={picoClasses.tertiaryButton}>
                      {currentMissionSecondaryLabel}
                    </Link>
                  </div>
                </div>

                {!progress.platform.railCollapsed && chapterPreviewTracks.length > 0 ? (
                  <div className={picoCodexNote('p-5')}>
                    <p className={picoClasses.label}>Other chapters</p>
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
                                  Track {String(trackIndex + 2).padStart(2, '0')}
                                </p>
                                <h3 className="mt-2 font-[family:var(--font-site-display)] text-2xl tracking-[-0.05em] text-[color:var(--pico-text)]">
                                  {track.title}
                                </h3>
                              </div>
                              <span className={picoCodex.stamp}>{unlocked ? 'open' : 'locked'}</span>
                            </div>
                            <p className="text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                              {track.outcome}
                            </p>
                            <p className="text-xs uppercase tracking-[0.18em] text-[color:var(--pico-text-muted)]">
                              {completedCount}/{trackLessons.length} cleared
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
              <p className={picoClasses.label}>Reference and settings</p>
              <h2 className="mt-3 font-[family:var(--font-site-display)] text-3xl tracking-[-0.05em] text-[color:var(--pico-text)]">
                Open the deeper material only when you need it.
              </h2>
            </div>
            <span className={picoCodex.stamp}>
              {currentLevel ? currentLevel.title : 'Setup'} • {lockedLessonCount} locked
            </span>
          </div>

          <div className="mt-6 grid gap-6 xl:grid-cols-[minmax(0,1.04fr),minmax(0,0.96fr)]">
            <div className="grid gap-5">
              <div className={picoCodexInset('p-5')}>
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <p className={picoClasses.label}>Unlocked capabilities</p>
                    <p className="mt-2 text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                      The pieces that matter after the first setup work is complete.
                    </p>
                  </div>
                  <span className={picoCodex.stamp}>
                    {derived.unlockedCapabilities.length} live
                  </span>
                </div>
                <div className="mt-4 grid gap-4">
                  {derived.unlockedCapabilities.slice(0, 2).map((capability) => (
                    <div
                      key={capability.id}
                      className="grid gap-2 border-t border-[color:var(--pico-border)] pt-4 first:border-t-0 first:pt-0"
                    >
                      <div className="flex flex-wrap items-center justify-between gap-3">
                        <h3 className="font-[family:var(--font-site-display)] text-2xl tracking-[-0.05em] text-[color:var(--pico-text)]">
                          {capability.title}
                        </h3>
                        <span className={picoCodex.stamp}>live</span>
                      </div>
                      <p className="text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                        {capability.description}
                      </p>
                      <Link href={toHref(capability.href)} className={picoClasses.secondaryButton}>
                        {capability.actionLabel}
                      </Link>
                    </div>
                  ))}

                  {derived.unlockedCapabilities.length === 0 ? (
                    <p className="text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                      The first capability unlock lands only after the first lessons are cleared for real.
                    </p>
                  ) : null}
                </div>
              </div>

              <div className="grid gap-5 lg:grid-cols-2">
                {derived.nextCapability ? (
                  <div className={picoCodexNote('p-5')}>
                    <p className={picoClasses.label}>Next unlock</p>
                    <h3 className="mt-3 font-[family:var(--font-site-display)] text-2xl tracking-[-0.05em] text-[color:var(--pico-text)]">
                      {derived.nextCapability.title}
                    </h3>
                    <p className="mt-3 text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                      {derived.nextCapability.description}
                    </p>
                    <Link href={toHref(derived.nextCapability.href)} className={cn(picoClasses.primaryButton, 'mt-4')}>
                      {derived.nextCapability.actionLabel}
                    </Link>
                  </div>
                ) : null}

                <div className={picoCodexInset('p-5')}>
                  <p className={picoClasses.label}>Pattern archive</p>
                  <div className="mt-4 grid gap-4">
                    {PICO_SHOWCASE_PATTERNS.slice(0, 2).map((pattern) => (
                      <div
                        key={pattern.lessonSlug}
                        className="grid gap-2 border-t border-[color:var(--pico-border)] pt-4 first:border-t-0 first:pt-0"
                      >
                        <p className="font-[family:var(--font-site-display)] text-2xl tracking-[-0.05em] text-[color:var(--pico-text)]">
                          {pattern.title}
                        </p>
                        <p className="text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                          {pattern.summary}
                        </p>
                        <Link href={toHref(`/academy/${pattern.lessonSlug}`)} className={picoClasses.tertiaryButton}>
                          Open pattern lesson
                        </Link>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </div>

            <div className="grid gap-5">
              <div className={picoCodexInset('p-5')}>
                <p className={picoClasses.label}>Field notes</p>
                <div className="mt-4 grid gap-4">
                  {PICO_RELEASE_NOTES.slice(0, 2).map((note) => (
                    <div
                      key={`${note.date}-${note.title}`}
                      className="grid gap-2 border-t border-[color:var(--pico-border)] pt-4 first:border-t-0 first:pt-0"
                    >
                      <div className="flex flex-wrap items-center justify-between gap-3">
                        <p className="font-[family:var(--font-site-display)] text-2xl tracking-[-0.05em] text-[color:var(--pico-text)]">
                          {note.title}
                        </p>
                        <span className={picoCodex.stamp}>{note.date}</span>
                      </div>
                      <p className="text-sm leading-6 text-[color:var(--pico-text-secondary)]">{note.body}</p>
                    </div>
                  ))}
                </div>
              </div>

              <details className={picoCodexSheet('group p-5')}>
                <summary className="flex cursor-pointer list-none items-center justify-between gap-4 [&::-webkit-details-marker]:hidden">
                  <div>
                    <p className={picoClasses.label}>Platform settings</p>
                    <p className="mt-3 text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                      Manage Academy state, help, and saved progress.
                    </p>
                  </div>
                  <span className={picoCodex.stamp}>open</span>
                </summary>
                <div className="mt-5 border-t border-[color:var(--pico-border)] pt-5">
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
