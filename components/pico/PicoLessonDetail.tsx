'use client'

import { motion, useReducedMotion } from 'framer-motion'
import { type KeyboardEvent, useCallback, useEffect, useState } from 'react'
import Link from 'next/link'
import { useTranslations } from 'next-intl'

import { PicoShell } from '@/components/pico/PicoShell'
import { PicoSurfaceCompass } from '@/components/pico/PicoSurfaceCompass'
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
  getLessonBySlug,
  getPicoLessonCompletionStatus,
  getTrackBySlug,
  isPicoLessonEvidenceMeaningful,
  type PicoLesson,
} from '@/lib/pico/academy'
import {
  localizePicoCapability,
  localizePicoLesson,
  localizePicoTrack,
} from '@/lib/pico/content'
import { usePicoHref } from '@/lib/pico/navigation'
import { cn } from '@/lib/utils'

type PicoLessonDetailProps = {
  lesson: PicoLesson
}

const revealTransition = {
  duration: 0.5,
  ease: [0.22, 1, 0.36, 1] as const,
}

export function PicoLessonDetail({ lesson: sourceLesson }: PicoLessonDetailProps) {
  const t = useTranslations('pico.lessonPage')
  const contentT = useTranslations('pico.content')
  const lesson = localizePicoLesson(sourceLesson, contentT)
  const session = usePicoSession()
  const { ready: progressReady, progress, derived, actions } = usePicoProgress(
    session.status === 'authenticated',
  )
  const toHref = usePicoHref()
  const [interactiveReady, setInteractiveReady] = useState(false)
  const reduceMotion = useReducedMotion() ?? false

  const started = progress.startedLessons.includes(lesson.slug)
  const completed = progress.completedLessons.includes(lesson.slug)
  const nextLessonSource = lesson.nextLesson ? getLessonBySlug(lesson.nextLesson) : null
  const nextLesson = nextLessonSource ? localizePicoLesson(nextLessonSource, contentT) : null
  const missingPrerequisite = lesson.prerequisites.find(
    (prerequisite) => !progress.completedLessons.includes(prerequisite),
  )
  const missingPrerequisiteSource = missingPrerequisite ? getLessonBySlug(missingPrerequisite) : null
  const missingPrerequisiteLesson = missingPrerequisiteSource
    ? localizePicoLesson(missingPrerequisiteSource, contentT)
    : null
  const approvalLesson = lesson.slug === 'add-an-approval-gate'
  const approvalSetupHref = toHref('/autopilot#approvals-section')
  const trackSource = getTrackBySlug(lesson.track)
  const track = trackSource ? localizePicoTrack(trackSource, contentT) : null
  const trackLessons =
    track?.lessons
      .map((slug) => getLessonBySlug(slug))
      .filter((entry): entry is PicoLesson => Boolean(entry))
      .map((entry) => localizePicoLesson(entry, contentT)) ?? []
  const lessonIndex = trackLessons.findIndex((item) => item.slug === lesson.slug)
  const previousLesson = lessonIndex > 0 ? trackLessons[lessonIndex - 1] ?? null : null

  const persistWorkspace = useCallback(
    (lessonSlug: string, nextWorkspace: Parameters<typeof actions.setLessonWorkspace>[1]) =>
      actions.setLessonWorkspace(lessonSlug, nextWorkspace),
    [actions],
  )

  const {
    ready: workspaceReady,
    workspace,
    completedStepCount,
    progressPercent,
    actions: workspaceActions,
  } = usePicoLessonWorkspace(lesson.slug, lesson.steps.length, {
    progress,
    persistRemote: persistWorkspace,
  })

  const activeStepIndex = workspace.activeStepIndex >= 0 ? workspace.activeStepIndex : 0
  const activeWorkspaceStep = lesson.steps[activeStepIndex] ?? lesson.steps[0] ?? null
  const completionStatus = getPicoLessonCompletionStatus(
    {
      ...progress,
      lessonWorkspaces: {
        ...progress.lessonWorkspaces,
        [lesson.slug]: workspace,
      },
    },
    lesson.slug,
  )
  const evidenceReady = isPicoLessonEvidenceMeaningful(workspace.evidence)
  const lessonControlsReady = interactiveReady && progressReady && workspaceReady
  const workspaceControlsReady = lessonControlsReady && !completed
  const canCompleteLesson = lessonControlsReady && completionStatus.canComplete
  const completionDescriptionId = `pico-completion-status-${lesson.slug}`
  const hostedStamp =
    session.status === 'authenticated'
      ? session.user.isEmailVerified === false
        ? t('shared.hostedStamp.verifyHost')
        : t('shared.hostedStamp.hostedAttached')
      : session.status === 'unauthenticated'
        ? t('shared.hostedStamp.localOnly')
        : session.status === 'error'
          ? t('shared.hostedStamp.authError')
        : t('shared.hostedStamp.checking')

  const studioReviewBoard = [
    {
      label: t('studio.cards.brief.label'),
      title: t('studio.cards.brief.title'),
      body: lesson.objective,
    },
    {
      label: t('studio.cards.deliverable.label'),
      title: t('studio.cards.deliverable.title'),
      body: lesson.expectedResult,
    },
    {
      label: t('studio.cards.critique.label'),
      title: t('studio.cards.critique.title'),
      body: lesson.validation,
    },
  ]

  const studioContext = [
    {
      label: t('studio.context.trackArc'),
      value: track?.outcome ?? t('studio.context.trackArcFallback'),
    },
    {
      label: t('studio.context.lessonOutcome'),
      value: lesson.outcome,
    },
    {
      label: t('studio.context.timeAndWeight'),
      value: t('studio.context.timeAndWeightValue', {
        minutes: lesson.estimatedMinutes,
        xp: lesson.xp,
        difficulty: t(`shared.difficulty.${lesson.difficulty}`),
      }),
    },
  ]
  const nextCapability = derived.nextCapability
    ? localizePicoCapability(derived.nextCapability, contentT)
    : null

  useEffect(() => {
    setInteractiveReady(true)
  }, [])

  useEffect(() => {
    if (!missingPrerequisiteLesson && !started && !completed) {
      actions.startLesson(lesson.slug)
    }
    if (
      progress.platform.activeSurface !== 'lesson' ||
      progress.platform.lastOpenedLessonSlug !== lesson.slug
    ) {
      actions.setPlatform({
        activeSurface: 'lesson',
        lastOpenedLessonSlug: lesson.slug,
      })
    }
  }, [
    actions,
    completed,
    lesson.slug,
    missingPrerequisiteLesson,
    progress.platform.activeSurface,
    progress.platform.lastOpenedLessonSlug,
    started,
  ])

  function completeLesson() {
    if (!canCompleteLesson) return
    actions.completeLesson(lesson.slug)
  }

  function getCompleteLabel() {
    if (lesson.slug === 'install-hermes-locally') return t('actions.completeLabel.installHermesLocally')
    if (lesson.slug === 'run-your-first-agent') return t('actions.completeLabel.runYourFirstAgent')
    return t('actions.completeLabel.default')
  }

  function getCompletedNextLabel() {
    if (!nextLesson) return t('actions.openAutopilot')
    if (nextLesson.slug === 'run-your-first-agent') return t('actions.runYourFirstAgentNow')
    return t('actions.openLesson', { lessonTitle: nextLesson.title })
  }

  function handleStepKeyDown(
    event: KeyboardEvent<HTMLButtonElement>,
    index: number,
    selector: 'mobile' | 'desktop',
  ) {
    const isRtl = event.currentTarget.closest('[dir]')?.getAttribute('dir') === 'rtl'
    let nextIndex: number | null = null

    if (event.key === 'Home') {
      nextIndex = 0
    } else if (event.key === 'End') {
      nextIndex = lesson.steps.length - 1
    } else if (event.key === 'ArrowDown' || event.key === (isRtl ? 'ArrowLeft' : 'ArrowRight')) {
      nextIndex = (index + 1) % lesson.steps.length
    } else if (event.key === 'ArrowUp' || event.key === (isRtl ? 'ArrowRight' : 'ArrowLeft')) {
      nextIndex = (index - 1 + lesson.steps.length) % lesson.steps.length
    }

    if (nextIndex === null || !lessonControlsReady) return
    event.preventDefault()
    workspaceActions.setActiveStep(nextIndex)
    document.getElementById(`pico-${selector}-step-${lesson.slug}-${nextIndex}`)?.focus()
  }

  function renderPrimaryLessonAction(buttonClassName: string) {
    if (missingPrerequisiteLesson) {
      return (
        <Link
          href={toHref(`/academy/${missingPrerequisiteLesson.slug}`)}
          className={cn(buttonClassName, 'motion-reduce:transition-none')}
        >
          {t('actions.completePrerequisiteFirst', { lessonTitle: missingPrerequisiteLesson.title })}
        </Link>
      )
    }

    if (completed) {
      return (
        <Link
          href={toHref(nextLesson ? `/academy/${nextLesson.slug}` : '/autopilot')}
          className={cn(buttonClassName, 'motion-reduce:transition-none')}
        >
          {getCompletedNextLabel()}
        </Link>
      )
    }

    if (approvalLesson) {
      return (
        <div className="grid gap-3 sm:flex sm:flex-wrap">
          <Link href={approvalSetupHref} className={cn(buttonClassName, 'motion-reduce:transition-none')}>
            {t('actions.openLiveApprovalSetup')}
          </Link>
          <button
            type="button"
            onClick={completeLesson}
            disabled={!canCompleteLesson}
            aria-describedby={completionDescriptionId}
            className={cn(
              picoClasses.secondaryButton,
              'motion-reduce:transition-none',
              !canCompleteLesson && 'disabled:cursor-not-allowed disabled:opacity-60',
            )}
          >
            {getCompleteLabel()}
          </button>
        </div>
      )
    }

    return (
      <button
        type="button"
        onClick={completeLesson}
        disabled={!canCompleteLesson}
        aria-describedby={completionDescriptionId}
        className={cn(
          buttonClassName,
          'motion-reduce:transition-none',
          !canCompleteLesson && 'disabled:cursor-not-allowed disabled:opacity-60',
        )}
      >
        {getCompleteLabel()}
      </button>
    )
  }

  return (
    <PicoShell
      mode="academy"
      eyebrow={t('shell.eyebrow', { number: String(Math.max(lessonIndex, 0) + 1).padStart(2, '0') })}
      title={lesson.title}
      description={lesson.summary}
      railCollapsed={progress.platform.railCollapsed}
      helpLaneOpen={progress.platform.helpLaneOpen}
      onToggleRail={() =>
        actions.setPlatform({ railCollapsed: !progress.platform.railCollapsed })
      }
      onToggleHelpLane={() =>
        actions.setPlatform({ helpLaneOpen: !progress.platform.helpLaneOpen })
      }
    >
      <motion.section
        initial={reduceMotion ? false : { opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={reduceMotion ? { duration: 0 } : revealTransition}
        className={picoCodexFrame('min-w-0 overflow-hidden px-4 py-6 sm:px-8 sm:py-8 lg:px-10 lg:py-10')}
        data-motion={reduceMotion ? 'reduced' : 'full'}
        data-pico-academy-motion
        data-testid="pico-lesson-campaign-hero"
      >
        <div className="grid min-w-0 gap-8 lg:grid-cols-[8rem,minmax(0,1fr)]">
          <div className="grid min-w-0 content-between gap-6 border-b border-[color:var(--pico-border)] pb-6 lg:border-b-0 lg:border-e lg:pb-0 lg:pe-8">
            <div className="grid gap-2">
              <p className={picoClasses.label}>{t('hero.lessonLabel')}</p>
              <p className="font-[family:var(--font-site-display)] text-7xl leading-none tracking-[-0.08em] text-[color:var(--pico-accent)] sm:text-8xl">
                {String(Math.max(lessonIndex, 0) + 1).padStart(2, '0')}
              </p>
            </div>

            <div className="grid gap-2">
              <p className={picoClasses.label}>{t('hero.trackLabel')}</p>
              <p className="font-[family:var(--font-site-display)] text-3xl tracking-[-0.05em] text-[color:var(--pico-text)]">
                {track?.title ?? t('hero.trackUnmapped')}
              </p>
              <p className="text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                {track && lessonIndex >= 0 ? `${lessonIndex + 1}/${trackLessons.length}` : t('hero.trackNotMapped')}
              </p>
            </div>
          </div>

          <div className="grid min-w-0 gap-6">
            <div className="flex flex-wrap items-center gap-2">
              <span className={picoCodex.stamp}>{t('hero.missionBrief')}</span>
              <span className={picoCodex.stamp}>{hostedStamp}</span>
              <span className={picoCodex.stamp}>
                {completed ? t('shared.chapterState.sealed') : started ? t('shared.chapterState.active') : t('shared.chapterState.ready')}
              </span>
            </div>

            <div className="grid gap-4">
              <h1 className="max-w-4xl break-words font-[family:var(--font-site-display)] text-5xl leading-[0.92] tracking-[-0.08em] text-[color:var(--pico-text)] sm:text-7xl">
                {lesson.title}
              </h1>
              <p className="max-w-3xl text-lg leading-8 text-[color:var(--pico-text-secondary)]">
                {lesson.objective}
              </p>
              <p className="max-w-3xl text-sm leading-6 text-[color:var(--pico-text-muted)]">
                {t('hero.expectedResult', { value: lesson.expectedResult })}
              </p>
            </div>

            <div className="grid gap-3 sm:flex sm:flex-wrap">
              {renderPrimaryLessonAction(picoClasses.primaryButton)}
              <Link
                href={toHref(`/tutor?lesson=${lesson.slug}`)}
                className={cn(
                  picoClasses.secondaryButton,
                  'scroll-mb-40 motion-reduce:transition-none',
                )}
              >
                {t('actions.askTutorAboutLesson')}
              </Link>
            </div>

            <div className="grid gap-3 border-t border-[color:var(--pico-border)] pt-5 sm:grid-cols-2 xl:grid-cols-4">
              <div className="grid gap-1">
                <p className={picoClasses.label}>{t('hero.metrics.state')}</p>
                <p className="font-[family:var(--font-site-display)] text-2xl tracking-[-0.05em] text-[color:var(--pico-text)]">
                  {missingPrerequisiteLesson ? t('shared.chapterState.blocked') : completed ? t('shared.chapterState.sealed') : t('shared.chapterState.active')}
                </p>
                <p className="text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                  {missingPrerequisiteLesson
                    ? t('hero.metrics.stateHintBlocked')
                    : completed
                      ? t('workspace.reviewState.sealedBody')
                      : t('hero.metrics.stateHintActive')}
                </p>
              </div>
              <div className="grid gap-1">
                <p className={picoClasses.label}>{t('hero.metrics.proof')}</p>
                <p className="font-[family:var(--font-site-display)] text-2xl tracking-[-0.05em] text-[color:var(--pico-text)]">
                  {evidenceReady ? t('shared.proofState.captured') : t('shared.proofState.pending')}
                </p>
                <p className="text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                  {activeWorkspaceStep?.title ?? t('hero.metrics.proofStepFallback')}
                </p>
              </div>
              <div className="grid gap-1">
                <p className={picoClasses.label}>{t('hero.metrics.progress')}</p>
                <p className="font-[family:var(--font-site-display)] text-2xl tracking-[-0.05em] text-[color:var(--pico-text)]">
                  {completedStepCount}/{lesson.steps.length}
                </p>
                <p className="text-sm leading-6 text-[color:var(--pico-text-secondary)]">{t('hero.metrics.stepsCleared')}</p>
              </div>
              <div className="grid gap-1">
                <p className={picoClasses.label}>{t('hero.metrics.telemetry')}</p>
                <p className="font-[family:var(--font-site-display)] text-2xl tracking-[-0.05em] text-[color:var(--pico-text)]">
                  {lesson.estimatedMinutes}m
                </p>
                <p className="text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                  {t('hero.metrics.telemetryDetail', { xp: lesson.xp, difficulty: t(`shared.difficulty.${lesson.difficulty}`) })}
                </p>
              </div>
            </div>
          </div>
        </div>
      </motion.section>

      <motion.section
        initial={reduceMotion ? false : { opacity: 0, y: 22 }}
        animate={{ opacity: 1, y: 0 }}
        transition={reduceMotion ? { duration: 0 } : { ...revealTransition, delay: 0.04 }}
        className={picoCodexFrame('min-w-0 px-4 py-6 sm:px-8 sm:py-8')}
        data-motion={reduceMotion ? 'reduced' : 'full'}
        data-pico-academy-motion
        data-testid="pico-lesson-studio-review"
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
              {studioReviewBoard.map((item) => (
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
              <p className={picoClasses.label}>{t('studio.context.title')}</p>
              <div className="mt-4 grid gap-4">
                {studioContext.map((item) => (
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
              <p className={picoClasses.label}>{t('studio.posture.title')}</p>
              <p className="mt-3 text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                {t('studio.posture.body')}
              </p>
            </div>
          </div>
        </div>
      </motion.section>

      <div className="xl:hidden">
        <div className="max-w-full overflow-x-auto pb-2" aria-label={t('chapterSpine.title')}>
          <div className="flex min-w-max gap-3" role="group" aria-label={t('chapterSpine.title')}>
            {lesson.steps.map((step, index) => {
              const active = activeStepIndex === index
              const done = workspace.completedStepIndexes.includes(index)

              return (
                <button
                  key={step.title}
                  type="button"
                  onClick={() => workspaceActions.setActiveStep(index)}
                  onKeyDown={(event) => handleStepKeyDown(event, index, 'mobile')}
                  disabled={!lessonControlsReady}
                  id={`pico-mobile-step-${lesson.slug}-${index}`}
                  aria-controls="pico-lesson-workspace-step"
                  aria-current={active ? 'step' : undefined}
                  aria-label={`${step.title}${done ? `, ${t('shared.stepState.done')}` : ''}`}
                  data-step-index={index}
                  data-step-selector="mobile"
                  className={cn(
                    'grid min-w-[13rem] gap-2 rounded-[24px] border px-4 py-4 text-start transition motion-reduce:transition-none',
                    active
                      ? 'border-[color:var(--pico-accent)] bg-[linear-gradient(180deg,rgba(var(--pico-accent-rgb),0.22),rgba(8,16,10,0.32))] text-[color:var(--pico-text)]'
                      : 'border-[color:var(--pico-border)] bg-[color:var(--pico-bg-surface)] text-[color:var(--pico-text-secondary)]',
                    !lessonControlsReady && 'disabled:cursor-not-allowed disabled:opacity-60',
                  )}
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <span className={picoCodex.stamp}>{String(index + 1).padStart(2, '0')}</span>
                    {done ? <span className={picoCodex.stamp}>{t('shared.stepState.done')}</span> : null}
                  </div>
                  <span className="font-[family:var(--font-site-display)] text-2xl tracking-[-0.05em]">
                    {step.title}
                  </span>
                </button>
              )
            })}
          </div>
        </div>
      </div>

      <motion.section
        initial={reduceMotion ? false : { opacity: 0, y: 24 }}
        animate={{ opacity: 1, y: 0 }}
        transition={reduceMotion ? { duration: 0 } : revealTransition}
        data-motion={reduceMotion ? 'reduced' : 'full'}
        data-pico-academy-motion
        className={cn(
          'grid min-w-0 gap-6',
          !progress.platform.railCollapsed && progress.platform.helpLaneOpen
            ? 'xl:grid-cols-[14rem,minmax(0,1fr),17rem]'
            : !progress.platform.railCollapsed
              ? 'xl:grid-cols-[14rem,minmax(0,1fr)]'
              : progress.platform.helpLaneOpen
                ? 'xl:grid-cols-[minmax(0,1fr),17rem]'
                : 'xl:grid-cols-[minmax(0,1fr)]',
        )}
      >
        {!progress.platform.railCollapsed ? (
          <aside className="hidden xl:block xl:sticky xl:top-6 xl:self-start">
            <section className={picoCodexFrame('p-5')}>
              <p className={picoClasses.label}>{t('chapterSpine.title')}</p>
              <div className="mt-4 grid gap-4" role="group" aria-label={t('chapterSpine.title')}>
                {lesson.steps.map((step, index) => {
                  const active = activeStepIndex === index
                  const done = workspace.completedStepIndexes.includes(index)

                  return (
                    <button
                      key={step.title}
                      type="button"
                      onClick={() => workspaceActions.setActiveStep(index)}
                      onKeyDown={(event) => handleStepKeyDown(event, index, 'desktop')}
                      disabled={!lessonControlsReady}
                      id={`pico-desktop-step-${lesson.slug}-${index}`}
                      aria-controls="pico-lesson-workspace-step"
                      aria-current={active ? 'step' : undefined}
                      aria-label={`${step.title}${done ? `, ${t('shared.stepState.done')}` : ''}`}
                      data-step-index={index}
                      data-step-selector="desktop"
                      className={cn(
                        'grid gap-2 border-s ps-4 text-start transition motion-reduce:transition-none',
                        active
                          ? 'border-[color:var(--pico-accent)] text-[color:var(--pico-text)]'
                          : 'border-[color:var(--pico-border)] text-[color:var(--pico-text-secondary)] hover:border-[color:var(--pico-border-hover)] hover:text-[color:var(--pico-text)]',
                        !lessonControlsReady && 'disabled:cursor-not-allowed disabled:opacity-60',
                      )}
                    >
                      <div className="flex flex-wrap items-center gap-2">
                        <span className={picoCodex.stamp}>{String(index + 1).padStart(2, '0')}</span>
                        {done ? <span className={picoCodex.stamp}>{t('shared.stepState.done')}</span> : null}
                        {active ? <span className={picoCodex.stamp}>{t('shared.stepState.active')}</span> : null}
                      </div>
                      <span className="font-[family:var(--font-site-display)] text-2xl tracking-[-0.05em]">
                        {step.title}
                      </span>
                    </button>
                  )
                })}
              </div>
            </section>
          </aside>
        ) : null}

        <section
          id="pico-lesson-workspace-step"
          aria-label={t('workspace.label')}
          className={picoCodexFrame('min-w-0 p-4 sm:p-7')}
          data-testid="pico-lesson-workspace"
        >
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <p className={picoClasses.label}>{t('workspace.label')}</p>
              <h2 className="mt-3 break-words font-[family:var(--font-site-display)] text-4xl tracking-[-0.06em] text-[color:var(--pico-text)]" aria-live="polite">
                {activeWorkspaceStep?.title ?? t('workspace.selectStep')}
              </h2>
            </div>
            <div className="grid gap-3 sm:flex sm:flex-wrap">
              <button
                type="button"
                onClick={() => workspaceActions.reset()}
                disabled={!workspaceControlsReady}
                className={cn(
                  picoClasses.tertiaryButton,
                  'motion-reduce:transition-none',
                  !workspaceControlsReady && 'disabled:cursor-not-allowed disabled:opacity-60',
                )}
              >
                {t('actions.resetWorkspace')}
              </button>
              <button
                type="button"
                onClick={() => workspaceActions.toggleStep(activeStepIndex)}
                disabled={!workspaceControlsReady}
                className={
                  cn(
                    workspace.completedStepIndexes.includes(activeStepIndex)
                      ? picoClasses.secondaryButton
                      : picoClasses.primaryButton,
                    'motion-reduce:transition-none',
                    !workspaceControlsReady && 'disabled:cursor-not-allowed disabled:opacity-60',
                  )
                }
                data-testid={activeStepIndex === 0 ? 'pico-step-toggle-first' : undefined}
              >
                {workspace.completedStepIndexes.includes(activeStepIndex)
                  ? t('actions.reopenStep')
                  : t('actions.markStepDone')}
              </button>
            </div>
          </div>

          <div className="mt-6 grid gap-5">
            <article className={picoCodexSheet('p-5')}>
              <p className={picoClasses.label}>{t('workspace.studioBrief')}</p>
              <p className="mt-4 text-base leading-8 text-[color:var(--pico-text-secondary)]">
                {activeWorkspaceStep?.body ??
                  t('workspace.chooseStepBody')}
              </p>
              {activeWorkspaceStep?.command ? (
                <pre className="mt-5 max-w-full overflow-x-auto rounded-[22px] border border-[color:var(--pico-border)] bg-[color:var(--pico-bg-input)] p-4 text-sm text-[color:var(--pico-accent-bright)]" dir="ltr">
                  <code>{activeWorkspaceStep.command}</code>
                </pre>
              ) : null}
              {activeWorkspaceStep?.note ? (
                <div className={picoCodexNote('mt-5 p-4')}>
                  <p className="text-sm leading-6 text-[color:var(--pico-text-secondary)]">{activeWorkspaceStep.note}</p>
                </div>
              ) : null}
            </article>

            <div id="pico-proof-composer" className="grid gap-4 lg:grid-cols-2">
              <label className={picoCodexInset('grid gap-3 p-4')}>
                <span className={picoClasses.label}>{t('workspace.deliverableArtifact')}</span>
                <textarea
                  value={workspace.evidence}
                  onChange={(event) => workspaceActions.setEvidence(event.target.value)}
                  disabled={!workspaceControlsReady}
                  aria-describedby={completionDescriptionId}
                  aria-invalid={workspace.evidence.trim().length > 0 && !evidenceReady}
                  placeholder={t('workspace.deliverablePlaceholder')}
                  className="min-h-40 rounded-[18px] border border-[color:var(--pico-border)] bg-[color:var(--pico-bg-input)] px-4 py-3 text-sm text-[color:var(--pico-text)] outline-none placeholder:text-[color:var(--pico-text-muted)] disabled:cursor-not-allowed disabled:opacity-60"
                  data-testid="pico-lesson-proof"
                />
              </label>

              <label className={picoCodexInset('grid gap-3 p-4')}>
                <span className={picoClasses.label}>{t('workspace.benchNotes')}</span>
                <textarea
                  value={workspace.notes}
                  onChange={(event) => workspaceActions.setNotes(event.target.value)}
                  disabled={!workspaceControlsReady}
                  placeholder={t('workspace.benchNotesPlaceholder')}
                  className="min-h-40 rounded-[18px] border border-[color:var(--pico-border)] bg-[color:var(--pico-bg-input)] px-4 py-3 text-sm text-[color:var(--pico-text)] outline-none placeholder:text-[color:var(--pico-text-muted)] disabled:cursor-not-allowed disabled:opacity-60"
                />
              </label>
            </div>

            <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr),18rem]">
              <div className={picoCodexNote('p-5')}>
                <div
                  id={completionDescriptionId}
                  role="status"
                  aria-live="polite"
                  data-testid="pico-lesson-completion-status"
                >
                  <p className={picoClasses.label}>{t('workspace.reviewState.label')}</p>
                  <p className="mt-3 font-[family:var(--font-site-display)] text-3xl tracking-[-0.05em] text-[color:var(--pico-text)]">
                    {completed ? t('shared.reviewState.sealed') : canCompleteLesson ? t('shared.reviewState.ready') : t('shared.reviewState.pending')}
                  </p>
                  <p className="mt-3 text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                    {completed
                      ? t('workspace.reviewState.sealedBody')
                      : !lessonControlsReady
                        ? t('workspace.reviewState.pendingBody')
                        : canCompleteLesson
                          ? t('workspace.reviewState.readyBody')
                          : t('workspace.reviewState.pendingBody')}
                  </p>
                  <p className="mt-3 text-xs leading-5 text-[color:var(--pico-text-muted)]">
                    {t('workspace.creativeDirection.body')}
                  </p>
                </div>
                <div className="mt-5">{renderPrimaryLessonAction(picoClasses.secondaryButton)}</div>
              </div>

              <div className="grid gap-4">
                <div className={picoCodexInset('p-4')}>
                  <p className={picoClasses.label}>{t('workspace.chapterCompletion')}</p>
                  <p className="mt-2 font-[family:var(--font-site-display)] text-3xl tracking-[-0.05em] text-[color:var(--pico-text)]">
                    {completedStepCount}/{lesson.steps.length}
                  </p>
                  <div
                    className="mt-4 overflow-hidden rounded-full bg-[color:var(--pico-bg-input)]"
                    role="progressbar"
                    aria-label={t('workspace.chapterCompletion')}
                    aria-valuemin={0}
                    aria-valuemax={lesson.steps.length}
                    aria-valuenow={completedStepCount}
                  >
                    <div
                      className="h-2 rounded-full bg-[linear-gradient(90deg,var(--pico-accent),var(--pico-accent-bright))]"
                      style={{ width: `${progressPercent}%` }}
                    />
                  </div>
                </div>

                <div className={picoCodexInset('p-4')}>
                  <p className={picoClasses.label}>{t('workspace.creativeDirection.title')}</p>
                  <p className="mt-2 text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                    {t('workspace.creativeDirection.body')}
                  </p>
                </div>
              </div>
            </div>
          </div>
        </section>

        {progress.platform.helpLaneOpen ? (
          <aside className="hidden xl:block xl:sticky xl:top-6 xl:self-start">
            <section className={picoCodexFrame('p-5')} data-testid="pico-help-lane-panel">
              <p className={picoClasses.label}>{t('helpLane.label')}</p>
              <div className="mt-4 grid gap-3">
                <div className={picoCodexInset('p-4')}>
                  <p className={picoClasses.label}>{t('helpLane.stayHereWhen')}</p>
                  <p className="mt-2 text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                    {t('helpLane.stayHereBody')}
                  </p>
                </div>
                <Link
                  href={toHref(`/tutor?lesson=${lesson.slug}`)}
                  className={picoCodexNote('p-4 transition motion-reduce:transition-none hover:border-[color:var(--pico-border-hover)]')}
                >
                  <p className={picoClasses.label}>{t('helpLane.exactBlocker')}</p>
                  <p className="mt-2 text-lg font-medium text-[color:var(--pico-text)]">{t('actions.askTutor')}</p>
                </Link>
                <Link
                  href={approvalLesson ? approvalSetupHref : toHref('/autopilot')}
                  className={picoCodexInset('p-4 transition motion-reduce:transition-none hover:border-[color:var(--pico-border-hover)] hover:text-[color:var(--pico-text)]')}
                >
                  <p className={picoClasses.label}>{t('helpLane.runtimeTruth')}</p>
                  <p className="mt-2 text-lg font-medium text-[color:var(--pico-text)]">
                    {approvalLesson ? t('actions.openLiveApprovalSetup') : t('actions.inspectAutopilot')}
                  </p>
                </Link>
                <Link
                  href={toHref('/support')}
                  className={picoCodexInset('p-4 transition motion-reduce:transition-none hover:border-[color:var(--pico-border-hover)] hover:text-[color:var(--pico-text)]')}
                >
                  <p className={picoClasses.label}>{t('helpLane.messyEdge')}</p>
                  <p className="mt-2 text-lg font-medium text-[color:var(--pico-text)]">{t('actions.openSupportLane')}</p>
                </Link>
              </div>
            </section>
          </aside>
        ) : null}
      </motion.section>

      <div id="pico-lesson-recovery">
        <PicoSurfaceCompass
          title={t('surfaceCompass.title')}
          body={t('surfaceCompass.body')}
          status={
            missingPrerequisiteLesson
              ? t('surfaceCompass.status.blockedByPrerequisite')
              : completed
                ? t('surfaceCompass.status.chapterSealed')
                : started
                  ? t('surfaceCompass.status.routeLaneActive')
                  : t('surfaceCompass.status.readyToExecute')
          }
          aside={t('surfaceCompass.aside')}
          items={[
            {
              href: toHref(`/tutor?lesson=${lesson.slug}`),
              label: t('surfaceCompass.items.askTutorLabel'),
              caption: t('surfaceCompass.items.askTutorCaption'),
              note: t('surfaceCompass.items.blocked'),
              tone: 'primary',
            },
            {
              href: missingPrerequisiteLesson
                ? toHref(`/academy/${missingPrerequisiteLesson.slug}`)
                : toHref('/academy'),
              label: missingPrerequisiteLesson
                ? t('actions.openLesson', { lessonTitle: missingPrerequisiteLesson.title })
                : t('surfaceCompass.items.returnToAcademyMap'),
              caption: t('surfaceCompass.items.returnCaption'),
              note: t('surfaceCompass.items.backtrack'),
            },
            {
              href: approvalLesson ? approvalSetupHref : toHref('/autopilot'),
              label: approvalLesson ? t('actions.openLiveApprovalSetup') : t('actions.inspectAutopilot'),
              caption: t('surfaceCompass.items.runtimeCaption'),
              note: t('surfaceCompass.items.runtime'),
              tone: 'soft',
            },
            {
              href: toHref('/support'),
              label: t('actions.openSupportLane'),
              caption: t('surfaceCompass.items.supportCaption'),
              note: t('surfaceCompass.items.messyEdge'),
            },
          ]}
        />
      </div>

      <motion.section
        initial={reduceMotion ? false : { opacity: 0, y: 24 }}
        animate={{ opacity: 1, y: 0 }}
        transition={reduceMotion ? { duration: 0 } : revealTransition}
        className="grid min-w-0 gap-6 xl:grid-cols-[minmax(0,1fr),18rem]"
        data-motion={reduceMotion ? 'reduced' : 'full'}
        data-pico-academy-motion
      >
        <section className={picoCodexFrame('p-6')}>
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <p className={picoClasses.label}>{t('troubleshooting.label')}</p>
              <h2 className="mt-3 font-[family:var(--font-site-display)] text-3xl tracking-[-0.06em] text-[color:var(--pico-text)]">
                {t('troubleshooting.title')}
              </h2>
            </div>
            <span className={picoCodex.stamp}>{t('troubleshooting.stepsCount', { count: lesson.steps.length })}</span>
          </div>

          <div className="mt-6 grid gap-4">
            {lesson.troubleshooting.map((item) => (
              <div key={item} className={picoCodexInset('px-4 py-4 text-sm leading-6 text-[color:var(--pico-text-secondary)]')}>
                {item}
              </div>
            ))}
          </div>
        </section>

        <aside className="space-y-6 xl:sticky xl:top-6 xl:self-start">
          {nextCapability ? (
            <section className={picoCodexFrame('p-5')}>
              <p className={picoClasses.label}>{t('troubleshooting.nextCapability')}</p>
              <div className={picoCodexNote('mt-4 p-5')}>
                <h3 className="font-[family:var(--font-site-display)] text-2xl tracking-[-0.05em] text-[color:var(--pico-text)]">
                  {nextCapability.title}
                </h3>
                <p className="mt-3 text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                  {nextCapability.description}
                </p>
                <Link
                  href={toHref(nextCapability.href)}
                  className={cn(picoClasses.primaryButton, 'mt-4 motion-reduce:transition-none')}
                >
                  {nextCapability.actionLabel}
                </Link>
              </div>
            </section>
          ) : null}

          <section className={picoCodexFrame('p-5')}>
            <p className={picoClasses.label}>{t('troubleshooting.routeMemory')}</p>
            <div className={picoCodexInset('mt-4 p-4')}>
              <div className="grid gap-3">
                {previousLesson ? (
                  <Link
                    href={toHref(`/academy/${previousLesson.slug}`)}
                    className={cn(picoClasses.tertiaryButton, 'motion-reduce:transition-none')}
                  >
                    {t('actions.previousLesson')}
                  </Link>
                ) : null}
                <Link
                  href={toHref('/academy')}
                  className={cn(picoClasses.secondaryButton, 'motion-reduce:transition-none')}
                >
                  {t('actions.backToAcademyMap')}
                </Link>
              </div>
            </div>
          </section>
        </aside>
      </motion.section>
    </PicoShell>
  )
}
