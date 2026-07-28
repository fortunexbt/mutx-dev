'use client'

import { motion, useReducedMotion } from 'framer-motion'
import { useLocale, useTranslations } from 'next-intl'
import { type FormEvent, useEffect, useMemo, useState } from 'react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'

import {
  classifyPicoSessionRuntime,
  PicoSessionBanner,
} from '@/components/pico/PicoSessionBanner'
import { PicoShell } from '@/components/pico/PicoShell'
import { PicoSignalDiagram } from '@/components/pico/PicoSignalDiagram'
import { PicoSurfaceCompass } from '@/components/pico/PicoSurfaceCompass'
import {
  picoClasses,
  picoEmber,
  picoInset,
  picoPanel,
  picoSoft,
} from '@/components/pico/picoTheme'
import { usePicoLessonWorkspace } from '@/components/pico/usePicoLessonWorkspace'
import { usePicoProgress } from '@/components/pico/usePicoProgress'
import { hasPicoPackagePlan, usePicoSession } from '@/components/pico/usePicoSession'
import { usePicoSetupState } from '@/components/pico/usePicoSetupState'
import { getLessonBySlug, PICO_TRACKS } from '@/lib/pico/academy'
import { localizePicoLesson, localizePicoTrack } from '@/lib/pico/content'
import { PICO_GENERATED_CONTENT } from '@/lib/pico/generatedContent'
import { usePicoHref } from '@/lib/pico/navigation'

const activationChecklist = PICO_GENERATED_CONTENT.onboarding.activationChecklist
const stackSpotlights = PICO_GENERATED_CONTENT.onboarding.stackSpotlights

const runtimeStatusOptions = [
  'client_required',
  'healthy',
  'degraded',
  'offline',
  'warning',
  'unknown',
] as const

const installMethodOptions = ['npm', 'brew', 'binary', 'manual'] as const

type RuntimeDraft = {
  label: string
  status: string
  installMethod: string
  gatewayUrl: string
  assistantName: string
  workspace: string
  model: string
}

function formatTimestamp(value: string | null | undefined, locale: string, notRecorded: string) {
  if (!value) return notRecorded
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return notRecorded

  return parsed.toLocaleString(locale, {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  })
}

function joinClasses(...classes: Array<string | false | null | undefined>) {
  return classes.filter(Boolean).join(' ')
}

export function PicoOnboardingPageClient() {
  const pathname = usePathname()
  const locale = useLocale()
  const t = useTranslations('pico.onboardingPage')
  const contentT = useTranslations('pico.content')
  const prefersReducedMotion = useReducedMotion()
  const session = usePicoSession()
  const { progress, derived, actions, syncState } = usePicoProgress(
    session.status === 'authenticated',
  )
  const setup = usePicoSetupState(session.status === 'authenticated')
  const toHref = usePicoHref()
  const [runtimeDraft, setRuntimeDraft] = useState<RuntimeDraft>({
    label: 'OpenClaw',
    status: 'client_required',
    installMethod: 'manual',
    gatewayUrl: '',
    assistantName: '',
    workspace: '',
    model: '',
  })
  const [coachDraft, setCoachDraft] = useState('')

  const firstTrack = localizePicoTrack(PICO_TRACKS[0], contentT)
  const installLessonSlug = 'install-hermes-locally'
  const firstRunLessonSlug = 'run-your-first-agent'
  const installLessonSource = getLessonBySlug(installLessonSlug)
  const firstRunLessonSource = getLessonBySlug(firstRunLessonSlug)
  const installLesson = installLessonSource
    ? localizePicoLesson(installLessonSource, contentT)
    : undefined
  const firstRunLesson = firstRunLessonSource
    ? localizePicoLesson(firstRunLessonSource, contentT)
    : undefined
  const installDone = progress.completedLessons.includes(installLessonSlug)
  const firstRunDone = progress.completedLessons.includes(firstRunLessonSlug)
  const activeTrackSource = PICO_TRACKS.find((track) => track.slug === progress.selectedTrack)
  const activeTrack = activeTrackSource
    ? localizePicoTrack(activeTrackSource, contentT)
    : firstTrack
  const nextLesson = derived.nextLesson
    ? localizePicoLesson(derived.nextLesson, contentT)
    : undefined
  const activationLessonSlug = firstRunDone
    ? (derived.nextLesson?.slug ?? activeTrack.lessons[0])
    : installDone
      ? firstRunLessonSlug
      : installLessonSlug
  const installWorkspace = usePicoLessonWorkspace(installLessonSlug, installLesson?.steps.length ?? 0, {
    progress,
    persistRemote: (lessonSlug, workspace) => actions.setLessonWorkspace(lessonSlug, workspace),
  })
  const firstRunWorkspace = usePicoLessonWorkspace(firstRunLessonSlug, firstRunLesson?.steps.length ?? 0, {
    progress,
    persistRemote: (lessonSlug, workspace) => actions.setLessonWorkspace(lessonSlug, workspace),
  })
  const installFocusedStep =
    installWorkspace.workspace.activeStepIndex >= 0
      ? installLesson?.steps[installWorkspace.workspace.activeStepIndex]?.title ?? t('runtime.notRecorded')
      : t('runtime.notRecorded')
  const firstRunFocusedStep =
    firstRunWorkspace.workspace.activeStepIndex >= 0
      ? firstRunLesson?.steps[firstRunWorkspace.workspace.activeStepIndex]?.title ?? t('runtime.notRecorded')
      : t('runtime.notRecorded')
  const storyRailClass =
    'mt-6 grid grid-flow-col auto-cols-[minmax(16rem,82vw)] gap-4 overflow-x-auto pb-2 snap-x snap-mandatory md:grid-flow-row md:auto-cols-auto md:overflow-visible xl:grid-cols-3'
  const missionRailClass =
    'mt-6 grid grid-flow-col auto-cols-[minmax(18rem,88vw)] gap-4 overflow-x-auto pb-2 snap-x snap-mandatory md:grid-flow-row md:auto-cols-auto md:overflow-visible xl:grid-cols-2'
  const compactRailClass =
    'grid grid-flow-col auto-cols-[minmax(15rem,82vw)] gap-3 overflow-x-auto pb-2 snap-x snap-mandatory sm:grid-flow-row sm:auto-cols-auto sm:overflow-visible sm:grid-cols-2'
  const timelineRailClass =
    'grid grid-flow-col auto-cols-[minmax(15rem,82vw)] gap-3 overflow-x-auto pb-2 snap-x snap-mandatory md:grid-flow-row md:auto-cols-auto md:overflow-visible'
  const kickoffDoctrine = [
    {
      label: t('doctrine.items.install.label'),
      title: t('doctrine.brief'),
      body:
        installLesson?.objective ??
        t('doctrine.items.install.body'),
    },
    {
      label: t('doctrine.items.firstRun.label'),
      title: t('doctrine.deliverable'),
      body:
        firstRunLesson?.expectedResult ??
        t('doctrine.items.firstRun.body'),
    },
    {
      label: t('doctrine.items.packet.label'),
      title: t('doctrine.items.packet.title'),
      body:
        firstRunLesson?.validation ??
        t('doctrine.items.packet.body'),
    },
  ]

  const hostedCompletionRatio = useMemo(() => {
    if (!setup.onboarding || setup.onboarding.steps.length === 0) {
      return 0
    }

    const completedCount = setup.onboarding.steps.filter((step) => step.completed).length
    return Math.round((completedCount / setup.onboarding.steps.length) * 100)
  }, [setup.onboarding])

  const currentBinding = setup.runtime?.current_binding ?? setup.runtime?.bindings[0] ?? null
  const proofCaptured = firstRunWorkspace.workspace.evidence.trim().length > 0 || firstRunDone
  const completedLessonStepCount =
    installWorkspace.completedStepCount + firstRunWorkspace.completedStepCount
  const totalLessonStepCount = (installLesson?.steps.length ?? 0) + (firstRunLesson?.steps.length ?? 0)
  const chapterPulsePercent = useMemo(() => {
    if (totalLessonStepCount === 0) {
      return 0
    }

    return Math.round(
      (completedLessonStepCount / totalLessonStepCount) * 100,
    )
  }, [completedLessonStepCount, totalLessonStepCount])
  const runtimeSignal =
    session.status !== 'authenticated'
      ? t('runtime.localOnly')
      : setup.loading
        ? t('runtime.checking')
        : setup.runtime?.status ?? t('hero.runtimeNotAttached')
  const runtimeBannerState = classifyPicoSessionRuntime({
    loading: setup.loading,
    error: setup.error,
    status: setup.runtime?.status,
    stale: setup.runtime?.stale,
  })
  const nextMoveTitle = !installDone
    ? t('hero.trackInstallPrompt')
    : !proofCaptured
      ? t('mission.runBoundedPrompt')
      : !firstRunDone
        ? t('hero.saveFirstRun')
        : nextLesson
          ? t('hero.continueWith', { lessonTitle: nextLesson.title })
          : t('hero.openAutopilot')
  const activeFocusStep = !installDone ? installFocusedStep : firstRunFocusedStep
  const activeWorkspaceLabel =
    setup.onboarding?.workspace ?? currentBinding?.workspace ?? runtimeDraft.workspace ?? t('runtime.notRecorded')
  const heroEyebrow = !proofCaptured
    ? t('hero.installThenPacket')
    : !firstRunDone
      ? t('hero.saveThenPacket')
      : t('hero.firstRunReady')
  const hostedSyncLabel = session.status === 'authenticated' ? `${hostedCompletionRatio}%` : t('runtime.localOnly')
  const proofSignalLabel = proofCaptured
    ? firstRunDone
      ? t('runtime.ready')
      : t('mission.captured')
    : t('mission.missing')
  const runtimeSignalDetail =
    session.status !== 'authenticated'
      ? t('hero.hostedSyncOffline')
      : setup.loading
        ? t('hero.refreshingStatus')
        : setup.runtime?.gateway_url
          ? t('hero.gatewayLive')
          : t('hero.gatewayUnbound')
  const packagePlanReady =
    session.status === 'authenticated' && hasPicoPackagePlan(session.user.plan)
  const emailReady =
    session.status === 'authenticated' && session.user.isEmailVerified !== false
  const coachReady = setup.coachSession?.ready_for_package === true
  const orbitTransition = prefersReducedMotion
    ? undefined
    : { duration: 20, repeat: Infinity, ease: 'linear' as const }
  const ambientDriftTransition = prefersReducedMotion
    ? undefined
    : { duration: 10, repeat: Infinity, repeatType: 'mirror' as const, ease: 'easeInOut' as const }
  const slowFloatTransition = prefersReducedMotion
    ? undefined
    : { duration: 14, repeat: Infinity, repeatType: 'mirror' as const, ease: 'easeInOut' as const }

  const runtimeDraftDirty = useMemo(() => {
    const runtime = setup.runtime
    if (!runtime) {
      return runtimeDraft.gatewayUrl.length > 0 || runtimeDraft.workspace.length > 0
    }

    return (
      runtimeDraft.label !== (runtime.label ?? 'OpenClaw') ||
      runtimeDraft.status !== runtime.status ||
      runtimeDraft.installMethod !== (runtime.install_method ?? '') ||
      runtimeDraft.gatewayUrl !== (runtime.gateway_url ?? '') ||
      runtimeDraft.assistantName !== (currentBinding?.assistant_name ?? '') ||
      runtimeDraft.workspace !== (currentBinding?.workspace ?? '') ||
      runtimeDraft.model !== (currentBinding?.model ?? '')
    )
  }, [currentBinding?.assistant_name, currentBinding?.model, currentBinding?.workspace, runtimeDraft, setup.runtime])

  useEffect(() => {
    if (!progress.milestoneEvents.includes('account_created')) {
      actions.unlockMilestone('account_created')
    }
    if (!progress.selectedTrack) {
      actions.pickTrack('first-agent')
    }
    if (progress.platform.activeSurface !== 'onboarding') {
      actions.setPlatform({ activeSurface: 'onboarding' })
    }
  }, [actions, progress.milestoneEvents, progress.platform.activeSurface, progress.selectedTrack])

  useEffect(() => {
    const runtime = setup.runtime
    const binding = runtime?.current_binding ?? runtime?.bindings[0]

    setRuntimeDraft({
      label: runtime?.label ?? 'OpenClaw',
      status: runtime?.status ?? 'client_required',
      installMethod: runtime?.install_method ?? 'manual',
      gatewayUrl: runtime?.gateway_url ?? '',
      assistantName: binding?.assistant_name ?? '',
      workspace: binding?.workspace ?? setup.onboarding?.workspace ?? '',
      model: binding?.model ?? '',
    })
  }, [setup.onboarding?.workspace, setup.runtime])

  async function saveRuntimeSnapshot() {
    const binding =
      runtimeDraft.assistantName || runtimeDraft.workspace || runtimeDraft.model
        ? [
            {
              assistant_name: runtimeDraft.assistantName || null,
              workspace: runtimeDraft.workspace || null,
              model: runtimeDraft.model || null,
            },
          ]
        : []

    await setup.updateRuntimeSnapshot({
      label: runtimeDraft.label || 'OpenClaw',
      status: runtimeDraft.status || 'unknown',
      install_method: runtimeDraft.installMethod || null,
      gateway_url: runtimeDraft.gatewayUrl || null,
      bindings: binding,
      current_binding: binding[0] ?? null,
      binding_count: binding.length,
    })
  }

  async function submitCoachMessage(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const accepted = await setup.sendCoachMessage(coachDraft)
    if (accepted) {
      setCoachDraft('')
    }
  }

  return (
    <PicoShell
      eyebrow={t('hero.shellEyebrow')}
      title={t('hero.shellTitle')}
      description={t('hero.shellDescription')}
      heroContent={
        <div
          className="relative overflow-hidden rounded-[28px] border border-[color:var(--pico-border-hover)] bg-[linear-gradient(135deg,rgba(var(--pico-accent-rgb),0.16),rgba(9,16,11,0.88)_38%,rgba(255,255,255,0.03)_100%)] p-5 shadow-[0_24px_70px_rgba(0,0,0,0.28)] sm:p-6"
          data-testid="pico-onboarding-hero-signal"
        >
          <div
            aria-hidden="true"
            className="pointer-events-none absolute inset-0 bg-[linear-gradient(180deg,rgba(255,255,255,0.03),transparent_28%,transparent_72%,rgba(255,255,255,0.02))]"
          />
          <div
            aria-hidden="true"
            className="pointer-events-none absolute inset-x-0 top-0 h-px bg-[linear-gradient(90deg,transparent,rgba(255,255,255,0.28),transparent)]"
          />
          <motion.div
            aria-hidden="true"
            className="pointer-events-none absolute -start-8 top-10 h-40 w-40 rounded-full bg-[rgba(var(--pico-accent-rgb),0.16)] blur-3xl"
            animate={prefersReducedMotion ? undefined : { x: [-10, 18, -6], y: [0, 14, -4], scale: [1, 1.08, 0.96] }}
            transition={ambientDriftTransition}
          />
          <motion.div
            aria-hidden="true"
            className="pointer-events-none absolute bottom-0 end-0 h-52 w-52 rounded-full bg-[rgba(var(--pico-accent-rgb),0.12)] blur-3xl"
            animate={prefersReducedMotion ? undefined : { x: [12, -10, 8], y: [8, -12, 0], scale: [0.94, 1.06, 1] }}
            transition={slowFloatTransition}
          />
          <div className="relative grid gap-5 xl:grid-cols-[minmax(0,1fr),18rem]">
            <div className="grid gap-5">
              <div className="flex flex-wrap items-center gap-2">
                <span className={picoClasses.chip}>{t('hero.chip')}</span>
                <span className="inline-flex rounded-full border border-[color:var(--pico-border)] bg-[rgba(255,255,255,0.03)] px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-[color:var(--pico-text-secondary)]">
                  {activeTrack.title}
                </span>
              </div>
              <p className="font-[family:var(--font-site-display)] text-[clamp(1.9rem,4vw,2.9rem)] leading-[0.94] tracking-[-0.06em] text-[color:var(--pico-text)]">
                {heroEyebrow}
              </p>
              <p className="max-w-2xl text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                {t('hero.subtitle')}
              </p>

              <div className="grid gap-3 sm:grid-cols-3">
                <div className={picoSoft('p-4')}>
                  <p className={picoClasses.label}>{t('hero.chapterPulse')}</p>
                  <p className="mt-2 font-[family:var(--font-site-display)] text-3xl tracking-[-0.05em] text-[color:var(--pico-text)]">
                    {chapterPulsePercent}%
                  </p>
                  <p className="mt-2 text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                    {t('hero.stepsClear', { completed: completedLessonStepCount, total: totalLessonStepCount })}
                  </p>
                </div>

                <div className={picoSoft('p-4')}>
                  <p className={picoClasses.label}>{t('hero.proofState')}</p>
                  <p className="mt-2 font-[family:var(--font-site-display)] text-3xl tracking-[-0.05em] text-[color:var(--pico-text)]">
                    {proofSignalLabel}
                  </p>
                  <p className="mt-2 text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                    {proofCaptured ? t('hero.proofArtifactLogged') : t('hero.proofArtifactMissing')}
                  </p>
                </div>

                <div className={picoSoft('p-4')}>
                  <p className={picoClasses.label}>{t('hero.runtimeTruth')}</p>
                  <p className="mt-2 font-[family:var(--font-site-display)] text-3xl tracking-[-0.05em] text-[color:var(--pico-text)]">
                    {runtimeSignal}
                  </p>
                  <p className="mt-2 text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                    {runtimeSignalDetail}
                  </p>
                </div>
              </div>

              <div className={picoInset('grid gap-3 p-4 sm:grid-cols-[auto,minmax(0,1fr)] sm:items-center')}>
                <div className="flex h-14 w-14 items-center justify-center rounded-[20px] border border-[rgba(var(--pico-accent-rgb),0.24)] bg-[linear-gradient(180deg,rgba(var(--pico-accent-rgb),0.18),rgba(7,13,8,0.5))] shadow-[0_18px_40px_rgba(var(--pico-accent-rgb),0.12)]">
                  <span className="h-3 w-3 rounded-full bg-[color:var(--pico-accent-bright)] shadow-[0_0_18px_rgba(var(--pico-accent-rgb),0.5)]" />
                </div>
                <div className="min-w-0">
                  <p className={picoClasses.label}>{t('hero.nextIrreversibleMove')}</p>
                  <p className="mt-2 font-[family:var(--font-site-display)] text-2xl tracking-[-0.05em] text-[color:var(--pico-text)]">
                    {nextMoveTitle}
                  </p>
                  <p className="mt-2 text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                    {activeFocusStep} · {activeWorkspaceLabel}
                  </p>
                </div>
              </div>
            </div>

            <div className={picoInset('relative min-h-[20rem] overflow-hidden border-[color:rgba(var(--pico-accent-rgb),0.24)] bg-[radial-gradient(circle_at_50%_22%,rgba(var(--pico-accent-rgb),0.16),rgba(6,11,7,0.94)_54%,rgba(3,5,3,0.98)_100%)] p-4')}>
              <div
                aria-hidden="true"
                className="pointer-events-none absolute inset-0 opacity-[0.18] [background-image:linear-gradient(rgba(255,255,255,0.12)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,0.08)_1px,transparent_1px)] [background-size:28px_28px]"
              />
              <motion.div
                aria-hidden="true"
                className="pointer-events-none absolute left-1/2 top-1/2 h-[16rem] w-[16rem] -translate-x-1/2 -translate-y-1/2 rounded-full border border-[rgba(var(--pico-accent-rgb),0.16)]"
                animate={prefersReducedMotion ? undefined : { rotate: 360 }}
                transition={orbitTransition}
              />
              <motion.div
                aria-hidden="true"
                className="pointer-events-none absolute left-1/2 top-1/2 h-[11rem] w-[11rem] -translate-x-1/2 -translate-y-1/2 rounded-full border border-[rgba(var(--pico-accent-rgb),0.24)]"
                animate={prefersReducedMotion ? undefined : { rotate: -360, scale: [0.98, 1.03, 0.98] }}
                transition={prefersReducedMotion ? undefined : { duration: 16, repeat: Infinity, ease: 'linear' }}
              />
              <motion.div
                aria-hidden="true"
                className="pointer-events-none absolute left-1/2 top-1/2 h-40 w-40 -translate-x-1/2 -translate-y-1/2 rounded-full bg-[radial-gradient(circle,rgba(var(--pico-accent-rgb),0.28),rgba(var(--pico-accent-rgb),0.02)_62%,transparent_74%)] blur-2xl"
                animate={prefersReducedMotion ? undefined : { scale: [0.9, 1.08, 0.96], opacity: [0.35, 0.7, 0.45] }}
                transition={ambientDriftTransition}
              />

              <motion.div
                className="absolute start-4 top-4 max-w-[8.5rem] rounded-[18px] border border-[rgba(255,255,255,0.08)] bg-[rgba(4,8,5,0.62)] px-3 py-2 backdrop-blur-md"
                animate={prefersReducedMotion ? undefined : { y: [-2, 10, -2], x: [0, 6, 0] }}
                transition={ambientDriftTransition}
              >
                <p className={picoClasses.label}>{t('hero.proof')}</p>
                <p className="mt-1 font-medium text-[color:var(--pico-text)]">{proofSignalLabel}</p>
              </motion.div>

              <motion.div
                className="absolute end-4 top-7 max-w-[8.5rem] rounded-[18px] border border-[rgba(255,255,255,0.08)] bg-[rgba(4,8,5,0.62)] px-3 py-2 backdrop-blur-md"
                animate={prefersReducedMotion ? undefined : { y: [8, -6, 8], x: [0, -4, 0] }}
                transition={slowFloatTransition}
              >
                <p className={picoClasses.label}>{t('hero.runtime')}</p>
                <p className="mt-1 font-medium text-[color:var(--pico-text)]">{runtimeSignal}</p>
              </motion.div>

              <motion.div
                className="absolute bottom-4 start-5 max-w-[9rem] rounded-[18px] border border-[rgba(255,255,255,0.08)] bg-[rgba(4,8,5,0.62)] px-3 py-2 backdrop-blur-md"
                animate={prefersReducedMotion ? undefined : { y: [0, -10, 0], x: [-2, 6, -2] }}
                transition={ambientDriftTransition}
              >
                <p className={picoClasses.label}>{t('hero.focus')}</p>
                <p className="mt-1 text-sm font-medium text-[color:var(--pico-text)]">{activeFocusStep}</p>
              </motion.div>

              <motion.div
                className="absolute bottom-5 end-5 rounded-[18px] border border-[rgba(255,255,255,0.08)] bg-[rgba(4,8,5,0.62)] px-3 py-2 backdrop-blur-md"
                animate={prefersReducedMotion ? undefined : { y: [6, -4, 6], x: [0, -6, 0] }}
                transition={slowFloatTransition}
              >
                <p className={picoClasses.label}>{t('hero.sync')}</p>
                <p className="mt-1 font-medium text-[color:var(--pico-text)]">{hostedSyncLabel}</p>
              </motion.div>

              <div className="relative flex h-full items-center justify-center">
                <div className="w-full max-w-[11rem] rounded-[30px] border border-[rgba(var(--pico-accent-rgb),0.22)] bg-[linear-gradient(180deg,rgba(255,255,255,0.08),rgba(255,255,255,0.02))] p-4 text-center shadow-[0_22px_60px_rgba(0,0,0,0.32)] backdrop-blur-xl">
                  <p className={picoClasses.label}>{t('hero.signalCore')}</p>
                  <p className="mt-3 font-[family:var(--font-site-display)] text-5xl tracking-[-0.08em] text-[color:var(--pico-text)]">
                    {chapterPulsePercent}%
                  </p>
                  <div className="mt-4 overflow-hidden rounded-full bg-[rgba(255,255,255,0.07)]">
                    <div
                      className="h-2 rounded-full bg-[linear-gradient(90deg,var(--pico-accent),var(--pico-accent-bright))]"
                      style={{ width: `${chapterPulsePercent}%` }}
                    />
                  </div>
                  <p className="mt-3 text-xs uppercase tracking-[0.18em] text-[color:var(--pico-text-muted)]">
                    {t('hero.stepsClear', { completed: completedLessonStepCount, total: totalLessonStepCount })}
                  </p>
                </div>
              </div>
            </div>
          </div>
        </div>
      }
      railCollapsed={progress.platform.railCollapsed}
      helpLaneOpen={progress.platform.helpLaneOpen}
      onToggleRail={() =>
        actions.setPlatform({ railCollapsed: !progress.platform.railCollapsed })
      }
      onToggleHelpLane={() =>
        actions.setPlatform({ helpLaneOpen: !progress.platform.helpLaneOpen })
      }
        actions={
          <div className="grid gap-3 sm:flex sm:flex-wrap">
            <Link
            href={
              firstRunDone && !derived.nextLesson
                ? toHref('/autopilot')
                : toHref(`/academy/${activationLessonSlug}`)
            }
            className={picoClasses.primaryButton}
            >
              {!installDone
                ? t('hero.trackInstallPrompt')
                : !firstRunDone
                  ? t('mission.runBoundedPrompt')
                  : nextLesson
                    ? t('hero.continueWith', { lessonTitle: nextLesson.title })
                    : t('hero.openAutopilot')}
            </Link>
            <Link href={toHref(`/tutor?lesson=${activationLessonSlug}`)} className={picoClasses.secondaryButton}>
              {t('compass.askTutorAboutStep')}
            </Link>
            <Link href={toHref('/support')} className={picoClasses.tertiaryButton}>
              {t('compass.escalateToHumanHelp')}
            </Link>
          </div>
        }
    >
      <PicoSessionBanner
        session={session}
        nextPath={pathname}
        progressSyncState={syncState}
        runtimeSignal={{ label: runtimeSignal, state: runtimeBannerState }}
      />
      <PicoSurfaceCompass
        title={t('compass.title')}
        body={t('compass.body')}
        status={
          firstRunDone
            ? t('compass.statusFirstWinCleared')
            : installDone
              ? t('compass.statusInstallCleared')
              : t('compass.statusColdStart')
        }
        aside={t('compass.aside')}
        items={[
          {
            href: toHref(`/academy/${activationLessonSlug}`),
            label: !installDone ? t('compass.openInstallLesson') : !firstRunDone ? t('compass.runFirstPrompt') : t('compass.continueAcademyLane'),
            caption: t('compass.primaryCaption'),
            note: t('compass.nextMove'),
            tone: 'primary',
          },
          {
            href: toHref(`/tutor?lesson=${activationLessonSlug}`),
            label: t('compass.askTutorAboutStep'),
            caption: t('compass.tutorCaption'),
            note: t('compass.blocked'),
          },
          {
            href: toHref('/autopilot'),
            label: t('compass.inspectLiveControlRoom'),
            caption: t('compass.runtimeCaption'),
            note: t('compass.runtime'),
            tone: 'soft',
          },
          {
            href: toHref('/support'),
            label: t('compass.escalateToHumanHelp'),
            caption: t('compass.supportCaption'),
            note: t('compass.messyEdge'),
          },
        ]}
      />

      <section className={picoPanel('p-6 sm:p-7')} data-testid="pico-onboarding-kickoff-doctrine">
        <div className="grid gap-6 lg:grid-cols-[minmax(0,1.08fr),20rem]">
          <div>
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div>
                <p className={picoClasses.label}>{t('doctrine.label')}</p>
                <h2 className="mt-3 font-[family:var(--font-site-display)] text-4xl tracking-[-0.06em] text-[color:var(--pico-text)]">
                  {t('doctrine.title')}
                </h2>
              </div>
              <span className={picoClasses.chip}>{t('doctrine.chip')}</span>
            </div>

            <div className={storyRailClass}>
              {kickoffDoctrine.map((item) => (
                <article key={item.label} className={picoInset('snap-start flex h-full flex-col p-5')}>
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
            <div className={picoEmber('p-5')}>
              <p className={picoClasses.label}>{t('doctrine.postTitle')}</p>
              <p className="mt-3 text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                {t('doctrine.postBody')}
              </p>
            </div>

            <PicoSignalDiagram
              index="01"
              label={t('labels.guideMarker')}
              title={t('hero.nextMove')}
              caption={t('hero.shellDescription')}
              compact
            />

            <div className={picoInset('p-5')}>
              <p className={picoClasses.label}>{t('labels.trackChecklist')}</p>
              <div className="mt-4 grid gap-3">
                {activeTrack.checklist.map((item) => (
                  <div key={item} className="flex items-start gap-3">
                    <span className="mt-1 inline-flex h-6 w-6 items-center justify-center rounded-full border border-[color:var(--pico-border)] bg-[rgba(var(--pico-accent-rgb),0.12)] text-[10px] font-semibold uppercase tracking-[0.16em] text-[color:var(--pico-accent)]">
                      {t('runtime.done')}
                    </span>
                    <p className="text-sm leading-6 text-[color:var(--pico-text-secondary)]">{item}</p>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="grid gap-6 xl:grid-cols-[minmax(0,1.08fr),22rem]">
        <div className={picoPanel('overflow-hidden p-0')}>
          <div className="grid gap-0 border-b border-[color:var(--pico-border)] lg:grid-cols-[minmax(0,1fr),18rem]">
            <div className="p-6 sm:p-7">
              <p className={picoClasses.label}>{t('labels.chapterBrief')}</p>
              <h2 className="mt-3 font-[family:var(--font-site-display)] text-4xl tracking-[-0.06em] text-[color:var(--pico-text)] sm:text-5xl">
                {t('doctrine.brief')}
              </h2>
              <p className="mt-4 max-w-3xl text-sm leading-7 text-[color:var(--pico-text-secondary)] sm:text-base">
                {t('doctrine.items.install.body')}
              </p>

              <div className={joinClasses(picoEmber('mt-6 p-5 text-sm leading-7'), 'sm:p-6')}>
                <p className="font-medium text-[color:var(--pico-text)]">{t('labels.fastestPath')}</p>
                <p className="mt-2">
                  {firstRunDone
                    ? t('doctrine.fastestPath.cleared')
                    : installDone
                      ? t('doctrine.fastestPath.installed')
                      : t('doctrine.fastestPath.start')}
                </p>
              </div>

              <div className={picoInset('mt-6 grid gap-4 p-5 lg:grid-cols-3')}>
                <div>
                  <p className={picoClasses.label}>{t('labels.trackLocked')}</p>
                  <p className="mt-2 font-[family:var(--font-site-display)] text-3xl tracking-[-0.05em] text-[color:var(--pico-text)]">
                    {activeTrack.title}
                  </p>
                </div>
                <div>
                  <p className={picoClasses.label}>{t('hero.nextMove')}</p>
                  <p className="mt-2 text-lg font-medium text-[color:var(--pico-text)]">
                    {nextLesson?.title ?? t('runtime.notRecorded')}
                  </p>
                </div>
                <div>
                  <p className={picoClasses.label}>{t('labels.visibleSuccess')}</p>
                  <p className="mt-2 text-lg font-medium text-[color:var(--pico-text)]">
                    {firstRunWorkspace.workspace.evidence.trim() || firstRunDone
                      ? t('mission.captured')
                      : installDone
                        ? t('hero.onePromptAway')
                        : t('hero.trackInstallPrompt')}
                  </p>
                </div>
              </div>
            </div>

            <div className="border-t border-[color:var(--pico-border)] bg-[color:var(--pico-bg-surface)] p-6 lg:border-s lg:border-t-0">
              <p className={picoClasses.label}>{t('labels.studioLedger')}</p>
              <div className="mt-4 grid gap-3">
                <div className={picoSoft('p-4')}>
                  <p className="text-sm text-[color:var(--pico-text-muted)]">{t('labels.completedLessons')}</p>
                  <p className="mt-1 text-2xl font-semibold text-[color:var(--pico-text)]">
                    {derived.completedLessonCount}
                  </p>
                </div>
                <div className={picoSoft('p-4')}>
                  <p className="text-sm text-[color:var(--pico-text-muted)]">{t('labels.hostedSync')}</p>
                  <p className="mt-1 text-2xl font-semibold text-[color:var(--pico-text)]">
                    {session.status === 'authenticated' ? `${hostedCompletionRatio}%` : t('runtime.signInShort')}
                  </p>
                </div>
                <div className={picoSoft('p-4')}>
                  <p className="text-sm text-[color:var(--pico-text-muted)]">{t('labels.runtimeStatus')}</p>
                  <p className="mt-1 text-lg font-medium text-[color:var(--pico-text)]">
                    {setup.runtime?.status ?? t('hero.runtimeNotAttached')}
                  </p>
                </div>
                <div className={picoSoft('p-4')}>
                  <p className="text-sm text-[color:var(--pico-text-muted)]">{t('labels.workspace')}</p>
                  <p className="mt-1 text-lg font-medium text-[color:var(--pico-text)]">
                    {setup.onboarding?.workspace ?? currentBinding?.workspace ?? t('runtime.notRecorded')}
                  </p>
                </div>
              </div>

              <div className={picoInset('mt-4 p-4')}>
                <p className={picoClasses.label}>{t('labels.jumpStraightTo')}</p>
                <div className="mt-3 grid gap-2">
                  <Link href={toHref(`/academy/${installLessonSlug}`)} className={picoClasses.secondaryButton}>
                    {t('labels.installLesson')}
                  </Link>
                  <Link href={toHref(`/academy/${firstRunLessonSlug}`)} className={picoClasses.tertiaryButton}>
                    {t('labels.firstPromptLesson')}
                  </Link>
                  <Link href={toHref('/tutor')} className={picoClasses.tertiaryButton}>
                    {t('labels.askTutor')}
                  </Link>
                </div>
              </div>

              <div className={picoInset('mt-4 p-4')}>
                <p className={picoClasses.label}>{t('labels.operatingRule')}</p>
                <p className="mt-3 text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                  {t('doctrine.reviewLine')}
                </p>
              </div>
            </div>
          </div>
        </div>

        <aside className="space-y-6 xl:sticky xl:top-6 xl:self-start">
          <section className={picoPanel('p-5')}>
            <p className={picoClasses.label}>{t('labels.currentPressure')}</p>
            <div className="mt-4 grid gap-3">
              <div className={picoSoft('p-4')}>
                <p className="text-sm text-[color:var(--pico-text-muted)]">{t('labels.install')}</p>
                <p className="mt-1 text-lg font-medium text-[color:var(--pico-text)]">{installDone ? t('runtime.done') : t('runtime.pending')}</p>
              </div>
              <div className={picoSoft('p-4')}>
                <p className="text-sm text-[color:var(--pico-text-muted)]">{t('labels.firstPrompt')}</p>
                <p className="mt-1 text-lg font-medium text-[color:var(--pico-text)]">
                  {firstRunWorkspace.workspace.evidence.trim() || firstRunDone ? t('hero.proofArtifactLogged') : t('runtime.pending')}
                </p>
              </div>
            </div>
          </section>
        </aside>
      </section>

      <section className={picoPanel('mt-6 p-6 sm:p-7')} data-testid="pico-onboarding-proof-protocol">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
              <p className={picoClasses.label}>{t('labels.proofProtocol')}</p>
            <h2 className="mt-3 font-[family:var(--font-site-display)] text-3xl tracking-[-0.05em] text-[color:var(--pico-text)] sm:text-4xl">
              {t('protocol.title')}
            </h2>
            <p className="mt-3 max-w-3xl text-sm leading-6 text-[color:var(--pico-text-secondary)]">
              {t('protocol.body')}
            </p>
          </div>
          <span className={picoClasses.chip}>{t('protocol.chip')}</span>
        </div>

        <div className={storyRailClass}>
          {activationChecklist.map((item, index) => (
            <article key={item.title} className={picoInset('snap-start flex h-full flex-col p-5 sm:p-6')}>
              <div className="flex items-center justify-between gap-3">
                <span className="inline-flex h-11 w-11 items-center justify-center rounded-full border border-[color:var(--pico-border)] bg-[rgba(var(--pico-accent-rgb),0.12)] text-xs font-semibold uppercase tracking-[0.18em] text-[color:var(--pico-accent)]">
                  {item.chapter}
                </span>
                <span className={picoClasses.label}>{index === 0 ? t('labels.doThisNow') : t('labels.visibleMove')}</span>
              </div>
              <h3 className="mt-6 font-[family:var(--font-site-display)] text-3xl tracking-[-0.05em] text-[color:var(--pico-text)]">
                {t(`protocol.items.${index}.title`)}
              </h3>
              <p className="mt-4 text-sm leading-7 text-[color:var(--pico-text-secondary)]">{t(`protocol.items.${index}.body`)}</p>
            </article>
          ))}
        </div>
      </section>

      <section className={picoPanel('p-6 sm:p-7')} data-testid="pico-onboarding-stack-radar">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <p className={picoClasses.label}>{t('stack.label')}</p>
            <h2 className="mt-3 font-[family:var(--font-site-display)] text-3xl tracking-[-0.05em] text-[color:var(--pico-text)] sm:text-4xl">
              {t('stack.title')}
            </h2>
            <p className="mt-3 max-w-3xl text-sm leading-6 text-[color:var(--pico-text-secondary)]">
              {t('stack.body')}
            </p>
          </div>
          <Link href={toHref('/build-ledger#stack-notes')} className={picoClasses.secondaryButton}>
            {t('stack.openNotes')}
          </Link>
        </div>

        <div className={storyRailClass}>
          {stackSpotlights.map((stack) => (
            <article key={stack.id} className={picoInset('snap-start flex h-full flex-col p-5 sm:p-6')}>
              <div className="flex items-center justify-between gap-3">
                <span className={picoClasses.label}>{stack.name}</span>
                <span className={picoClasses.chip}>{t(`stack.items.${stack.id}.latestSignal`)}</span>
              </div>
              <p className="mt-6 font-[family:var(--font-site-display)] text-3xl tracking-[-0.05em] text-[color:var(--pico-text)]">
                {t(`stack.items.${stack.id}.whyNow`)}
              </p>
              <p className="mt-4 text-sm leading-7 text-[color:var(--pico-text-secondary)]">
                {t('stack.itemBody')}
              </p>
            </article>
          ))}
        </div>
      </section>

      <section className={picoPanel('p-6 sm:p-7')} data-testid="pico-onboarding-mission-board">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
              <p className={picoClasses.label}>{t('labels.missionBoard')}</p>
              <h2 className="mt-3 font-[family:var(--font-site-display)] text-3xl tracking-[-0.05em] text-[color:var(--pico-text)] sm:text-4xl">
              {t('mission.title')}
            </h2>
            <p className="mt-3 max-w-3xl text-sm leading-6 text-[color:var(--pico-text-secondary)]">
              {t('mission.body')}
            </p>
          </div>
          <span className={picoClasses.chip}>{t('mission.continuity')}</span>
        </div>

        <div className={missionRailClass}>
          <article className={picoInset('grid gap-4 p-5')} data-testid="pico-onboarding-install-mission">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className={picoClasses.label}>{t('labels.mission01')}</p>
                <h3 className="mt-2 font-[family:var(--font-site-display)] text-3xl tracking-[-0.05em] text-[color:var(--pico-text)]">
                  {t('mission.installHermes')}
                </h3>
              </div>
              <span className={picoClasses.chip}>
                {t('hero.stepsClear', { completed: installWorkspace.completedStepCount, total: installLesson?.steps.length ?? 0 })}
              </span>
            </div>
            <div className="overflow-hidden rounded-full bg-[color:var(--pico-bg-input)]">
              <div
                className="h-2 rounded-full bg-[linear-gradient(90deg,var(--pico-accent),var(--pico-accent-bright))]"
                style={{ width: `${installWorkspace.progressPercent}%` }}
              />
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <div className={picoSoft('p-4')}>
                <p className="text-sm text-[color:var(--pico-text-muted)]">{t('mission.focusedStep')}</p>
                <p className="mt-1 text-lg font-medium text-[color:var(--pico-text)]">{installFocusedStep}</p>
              </div>
              <div className={picoSoft('p-4')}>
                <p className="text-sm text-[color:var(--pico-text-muted)]">{t('mission.proofState')}</p>
                <p className="mt-1 text-lg font-medium text-[color:var(--pico-text)]">
                  {installWorkspace.workspace.evidence.trim() ? t('mission.captured') : installDone ? t('mission.completed') : t('mission.missing')}
                </p>
              </div>
            </div>
            <div className="grid gap-3 sm:flex sm:flex-wrap">
              <Link href={toHref(`/academy/${installLessonSlug}`)} className={picoClasses.secondaryButton}>
                {t('mission.resumeInstall')}
              </Link>
              <Link href={toHref(`/tutor?lesson=${installLessonSlug}`)} className={picoClasses.tertiaryButton}>
                {t('labels.askTutor')}
              </Link>
            </div>
          </article>

          <article className={picoInset('grid gap-4 p-5')} data-testid="pico-onboarding-first-run-mission">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className={picoClasses.label}>{t('labels.mission02')}</p>
                <h3 className="mt-2 font-[family:var(--font-site-display)] text-3xl tracking-[-0.05em] text-[color:var(--pico-text)]">
                  {t('mission.runBoundedPrompt')}
                </h3>
              </div>
              <span className={picoClasses.chip}>
                {t('hero.stepsClear', { completed: firstRunWorkspace.completedStepCount, total: firstRunLesson?.steps.length ?? 0 })}
              </span>
            </div>
            <div className="overflow-hidden rounded-full bg-[color:var(--pico-bg-input)]">
              <div
                className="h-2 rounded-full bg-[linear-gradient(90deg,var(--pico-accent),var(--pico-accent-bright))]"
                style={{ width: `${firstRunWorkspace.progressPercent}%` }}
              />
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <div className={picoSoft('p-4')}>
                <p className="text-sm text-[color:var(--pico-text-muted)]">{t('mission.focusedStep')}</p>
                <p className="mt-1 text-lg font-medium text-[color:var(--pico-text)]">{firstRunFocusedStep}</p>
              </div>
              <div className={picoSoft('p-4')}>
                <p className="text-sm text-[color:var(--pico-text-muted)]">{t('mission.proofState')}</p>
                <p className="mt-1 text-lg font-medium text-[color:var(--pico-text)]">
                  {firstRunWorkspace.workspace.evidence.trim() ? t('mission.captured') : firstRunDone ? t('mission.completed') : t('mission.missing')}
                </p>
              </div>
            </div>
            <div className="grid gap-3 sm:flex sm:flex-wrap">
              <Link href={toHref(`/academy/${firstRunLessonSlug}`)} className={picoClasses.secondaryButton}>
                {t('mission.resumePrompt')}
              </Link>
              <Link href={toHref(`/tutor?lesson=${firstRunLessonSlug}`)} className={picoClasses.tertiaryButton}>
                {t('labels.askTutor')}
              </Link>
            </div>
          </article>
        </div>
      </section>

      <section className={picoPanel('p-6 sm:p-7')} data-testid="pico-onboarding-coach">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className={picoClasses.label}>{t('coach.label')}</p>
            <h2 className="mt-3 font-[family:var(--font-site-display)] text-3xl tracking-[-0.05em] text-[color:var(--pico-text)] sm:text-4xl">
              {t('coach.title')}
            </h2>
            <p className="mt-3 max-w-3xl text-sm leading-6 text-[color:var(--pico-text-secondary)]">
              {t('coach.body')}
            </p>
          </div>
          {setup.coachSession ? (
            <span className={picoClasses.chip} data-testid="pico-coach-session-id">
              {t('coach.session', { sessionId: setup.coachSession.session_id.slice(0, 8) })}
            </span>
          ) : null}
        </div>

        {session.status === 'loading' ? (
          <div className={picoSoft('mt-6 p-5')}>
            <p className={picoClasses.body}>{t('coach.checkingSession')}</p>
          </div>
        ) : session.status === 'error' ? (
          <div className={picoEmber('mt-6 grid gap-3 p-5')}>
            <p className={picoClasses.body}>{t('coach.errorDetail', { detail: session.error })}</p>
            <button type="button" onClick={session.retry} className={picoClasses.secondaryButton}>
              {t('coach.retryHostedSession')}
            </button>
          </div>
        ) : session.status === 'unauthenticated' ? (
          <div className={picoSoft('mt-6 p-5')}>
            <p className={picoClasses.body}>
              {t('coach.signInFirst')}
            </p>
          </div>
        ) : (
          <div className="mt-6 grid gap-6 xl:grid-cols-[minmax(0,1fr),22rem]">
            <div className="grid gap-4">
              {setup.coachLoading && !setup.coachSession ? (
                <div className={picoSoft('p-5')} data-testid="pico-coach-loading">
                  <p className={picoClasses.body}>{t('coach.loadingHistory')}</p>
                </div>
              ) : null}

              {setup.coachError ? (
                <div className={picoEmber('grid gap-3 p-5')} role="alert">
                  <p className={picoClasses.body}>{t('coach.errorDetail', { detail: setup.coachError })}</p>
                  <div className="flex flex-wrap gap-2">
                    {setup.coachAuthRequired ? (
                      <button type="button" onClick={session.retry} className={picoClasses.secondaryButton}>
                        {t('coach.refreshSignIn')}
                      </button>
                    ) : setup.coachExpired ? (
                      <button
                        type="button"
                        onClick={() => void setup.startNewCoachSession()}
                        className={picoClasses.secondaryButton}
                      >
                        {t('coach.startNewSession')}
                      </button>
                    ) : (
                      <button
                        type="button"
                        onClick={() => void setup.refreshCoachSession(setup.coachSession?.session_id)}
                        className={picoClasses.secondaryButton}
                      >
                        {t('coach.retryHistory')}
                      </button>
                    )}
                  </div>
                </div>
              ) : null}

              <div
                className={picoInset('grid max-h-[28rem] min-h-[12rem] gap-3 overflow-y-auto p-4')}
                aria-live="polite"
                data-testid="pico-coach-history"
              >
                {setup.coachSession?.history.length ? (
                  setup.coachSession.history.map((message, index) => (
                    <article
                      key={`${message.role}-${index}`}
                      className={message.role === 'assistant' ? picoSoft('p-4') : picoEmber('p-4')}
                    >
                      <p className={picoClasses.label}>{message.role === 'assistant' ? t('coach.picoCoach') : t('coach.you')}</p>
                      <p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                        {message.content}
                      </p>
                    </article>
                  ))
                ) : (
                  <div className={picoSoft('p-4')}>
                    <p className={picoClasses.body}>
                      {t('coach.emptyHistory')}
                    </p>
                  </div>
                )}
              </div>

              <form className={picoInset('grid gap-3 p-4')} onSubmit={submitCoachMessage}>
                <label className="grid gap-2 text-sm text-[color:var(--pico-text-secondary)]">
                  <span className={picoClasses.label}>{t('coach.continueSetup')}</span>
                  <textarea
                    value={coachDraft}
                    onChange={(event) => setCoachDraft(event.target.value)}
                    maxLength={6000}
                    rows={4}
                    className="resize-y rounded-[20px] border border-[color:var(--pico-border)] bg-[color:var(--pico-bg-input)] px-4 py-3 text-[color:var(--pico-text)] outline-none placeholder:text-[color:var(--pico-text-muted)]"
                    placeholder={t('coach.placeholder')}
                  />
                </label>
                <div className="flex flex-wrap gap-2">
                  <button
                    type="submit"
                    className={picoClasses.primaryButton}
                    disabled={!coachDraft.trim() || setup.coachPending || setup.packagePending}
                  >
                    {setup.coachPending ? t('coach.savingTurn') : t('coach.send')}
                  </button>
                  {setup.coachSession ? (
                    <button
                      type="button"
                      onClick={() => void setup.startNewCoachSession()}
                      className={picoClasses.tertiaryButton}
                      disabled={setup.coachPending || setup.packagePending}
                    >
                      {t('coach.startOver')}
                    </button>
                  ) : null}
                </div>
              </form>
            </div>

            <aside className={picoInset('grid content-start gap-4 p-5')} data-testid="pico-package-readiness">
              <div>
                <p className={picoClasses.label}>{t('coach.readiness')}</p>
                <p className="mt-2 font-[family:var(--font-site-display)] text-3xl tracking-[-0.05em] text-[color:var(--pico-text)]">
                  {coachReady ? t('runtime.ready') : t('coach.needsDetails')}
                </p>
              </div>
              {(['stack', 'os', 'provider', 'goal'] as const).map((field) => (
                <div key={field} className={picoSoft('flex items-center justify-between gap-3 p-3')}>
                  <span className="text-sm text-[color:var(--pico-text-muted)]">{t(`coach.fields.${field}`)}</span>
                  <span className="text-sm font-medium text-[color:var(--pico-text)]">
                    {setup.coachSession?.onboarding_state[field] ?? t('coach.notConfirmed')}
                  </span>
                </div>
              ))}
              {!emailReady ? (
                <p className="text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                  {t('coach.verifyEmail')}
                </p>
              ) : !packagePlanReady ? (
                <div className="grid gap-2">
                  <p className="text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                    {t('coach.planRequired')}
                  </p>
                  <Link href={toHref('/pricing')} className={picoClasses.secondaryButton}>
                    {t('coach.comparePlans')}
                  </Link>
                </div>
              ) : null}
              <button
                type="button"
                onClick={() => void setup.downloadPackage()}
                className={picoClasses.primaryButton}
                disabled={!coachReady || !emailReady || !packagePlanReady || setup.packagePending || setup.coachPending}
              >
                {setup.packagePending ? t('coach.preparingPackage') : t('coach.downloadPackage')}
              </button>
              {setup.packageError ? (
                <div className={picoEmber('grid gap-3 p-4')} role="alert">
                  <p className="text-sm leading-6 text-[color:var(--pico-text-secondary)]">{t('coach.errorDetail', { detail: setup.packageError })}</p>
                  {setup.coachAuthRequired ? (
                    <button type="button" onClick={session.retry} className={picoClasses.secondaryButton}>
                      {t('coach.refreshSignIn')}
                    </button>
                  ) : setup.coachExpired ? (
                    <button
                      type="button"
                      onClick={() => void setup.startNewCoachSession()}
                      className={picoClasses.secondaryButton}
                    >
                      {t('coach.startNewSession')}
                    </button>
                  ) : setup.packageUpgradeRequired ? (
                    <Link href={toHref('/pricing')} className={picoClasses.secondaryButton}>
                      {t('coach.upgradePlan')}
                    </Link>
                  ) : coachReady && !setup.coachExpired ? (
                    <button
                      type="button"
                      onClick={() => void setup.downloadPackage()}
                      className={picoClasses.secondaryButton}
                      disabled={setup.packagePending}
                    >
                      {t('coach.retryPackage')}
                    </button>
                  ) : null}
                </div>
              ) : null}
            </aside>
          </div>
        )}
      </section>

      <section className={picoPanel('p-6 sm:p-7')} data-testid="pico-onboarding-operator-record">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <p className={picoClasses.label}>{t('labels.operatorRecord')}</p>
            <h2 className="mt-3 font-[family:var(--font-site-display)] text-3xl tracking-[-0.05em] text-[color:var(--pico-text)] sm:text-4xl">
              {t('operatorRecord.title')}
            </h2>
            <p className="mt-3 max-w-3xl text-sm leading-6 text-[color:var(--pico-text-secondary)]">
              {t('operatorRecord.body')}
            </p>
          </div>
          {session.status === 'authenticated' ? (
            <button
              type="button"
              onClick={() => void setup.refresh()}
              className={picoClasses.tertiaryButton}
            >
              {t('labels.refreshSync')}
            </button>
          ) : null}
        </div>

        <div className="mt-6 grid gap-6 xl:grid-cols-[minmax(0,1.08fr),22rem]">
          <div className="grid gap-4">
            {session.status !== 'authenticated' ? (
              <div className={picoSoft('p-5')}>
                <p className={picoClasses.body}>
                  {t('operatorRecord.signIn')}
                </p>
              </div>
            ) : setup.loading ? (
              <div className={picoSoft('p-5')}>
                <p className={picoClasses.body}>{t('runtime.loading')}</p>
              </div>
            ) : setup.error ? (
              <div className={picoEmber('p-5')}>
                <p className={picoClasses.body}>{t('operatorRecord.errorDetail', { detail: setup.error })}</p>
              </div>
            ) : (
              <>
                {setup.onboarding ? (
                  <div className={compactRailClass}>
                    {(setup.onboarding.providers ?? []).map((provider) => {
                      const active = provider.id === setup.onboarding?.provider
                      return (
                        <article
                          key={provider.id}
                          className={joinClasses(
                            picoInset('snap-start grid gap-2 p-4'),
                            active && 'border-[color:var(--pico-border-hover)] bg-[rgba(var(--pico-accent-rgb),0.09)]',
                            !provider.enabled && 'opacity-70',
                          )}
                        >
                          <div className="flex items-center justify-between gap-3">
                            <div className="flex items-center gap-3">
                              <span className="text-xl">{provider.cue ?? '•'}</span>
                              <div>
                                <p className="font-medium text-[color:var(--pico-text)]">{provider.label}</p>
                                <p className="text-xs uppercase tracking-[0.18em] text-[color:var(--pico-text-muted)]">
                                  {active ? t('runtime.currentProvider') : provider.enabled ? t('runtime.availableSoon') : t('runtime.locked')}
                                </p>
                              </div>
                            </div>
                            <span className={picoClasses.chip}>{provider.enabled ? t('runtime.ready') : t('runtime.later')}</span>
                          </div>
                          <p className="text-sm leading-6 text-[color:var(--pico-text-secondary)]">{provider.summary}</p>
                        </article>
                      )
                    })}
                  </div>
                ) : null}

                <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
                  <div className={picoInset('p-4')}>
                    <p className="text-sm text-[color:var(--pico-text-muted)]">{t('runtime.wizardProgress')}</p>
                    <p className="mt-1 text-2xl font-semibold text-[color:var(--pico-text)]">
                      {setup.onboarding ? `${hostedCompletionRatio}%` : t('runtime.notStarted')}
                    </p>
                  </div>
                  <div className={picoInset('p-4')}>
                    <p className="text-sm text-[color:var(--pico-text-muted)]">{t('runtime.currentStep')}</p>
                    <p className="mt-1 text-lg font-medium text-[color:var(--pico-text)]">
                      {setup.onboarding?.current_step ?? t('runtime.notRecorded')}
                    </p>
                  </div>
                  <div className={picoInset('p-4')}>
                    <p className="text-sm text-[color:var(--pico-text-muted)]">{t('labels.runtimeStatus')}</p>
                    <p className="mt-1 text-lg font-medium text-[color:var(--pico-text)]">
                      {setup.runtime?.status ?? t('hero.runtimeNotAttached')}
                    </p>
                  </div>
                  <div className={picoInset('p-4')}>
                    <p className="text-sm text-[color:var(--pico-text-muted)]">{t('labels.currentBinding')}</p>
                    <p className="mt-1 text-lg font-medium text-[color:var(--pico-text)]">
                      {currentBinding?.assistant_name ?? currentBinding?.assistant_id ?? t('runtime.currentBindingNotRecorded')}
                    </p>
                  </div>
                </div>

                {setup.onboarding ? (
                  <div className={picoInset('grid gap-4 p-5')}>
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <div>
                        <p className={picoClasses.label}>{t('runtime.hostedKickoffReview')}</p>
                        <h3 className="mt-2 font-[family:var(--font-site-display)] text-2xl tracking-[-0.05em] text-[color:var(--pico-text)]">
                          {setup.onboarding.status}
                        </h3>
                      </div>
                      <span className={picoClasses.chip}>
                        {setup.onboarding.checklist_dismissed ? t('runtime.checklistDismissed') : t('runtime.checklistVisible')}
                      </span>
                    </div>

                    {setup.onboarding.last_error ? (
                      <p className="text-sm leading-6 text-[color:var(--pico-accent)]">{t('operatorRecord.errorDetail', { detail: setup.onboarding.last_error })}</p>
                    ) : null}

                    <div className={timelineRailClass}>
                      {setup.onboarding.steps.map((step) => {
                        const active = step.id === setup.onboarding?.current_step
                        const failed = step.id === setup.onboarding?.failed_step
                        return (
                          <div
                            key={step.id}
                            className={joinClasses(
                              picoInset('snap-start flex items-center justify-between gap-4 px-4 py-3'),
                              active && 'border-[color:var(--pico-border-hover)] bg-[rgba(var(--pico-accent-rgb),0.08)]',
                            )}
                          >
                            <div>
                              <p className="text-sm font-medium text-[color:var(--pico-text)]">{step.title}</p>
                              <p className="mt-1 text-xs uppercase tracking-[0.2em] text-[color:var(--pico-text-muted)]">
                                {step.id}
                              </p>
                            </div>
                            <span className={picoClasses.chip}>
                              {failed ? t('runtime.failed') : step.completed ? t('runtime.done') : active ? t('runtime.active') : t('runtime.pending')}
                            </span>
                          </div>
                        )
                      })}
                    </div>
                  </div>
                ) : (
                  <div className={picoSoft('p-5')}>
                    <p className={picoClasses.body}>{t('runtime.noHostedState')}</p>
                  </div>
                )}

                <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr),18rem]">
                  <div className={picoInset('p-5')}>
                    <p className={picoClasses.label}>{t('runtime.operatorHostSnapshot')}</p>
                    {setup.runtime ? (
                      <div className="mt-4 grid gap-3 sm:grid-cols-2">
                        <div>
                          <p className="text-sm text-[color:var(--pico-text-muted)]">{t('runtime.gateway')}</p>
                          <p className="mt-1 text-lg font-medium text-[color:var(--pico-text)]">
                            {setup.runtime.gateway_url ?? t('runtime.notRecorded')}
                          </p>
                        </div>
                        <div>
                          <p className="text-sm text-[color:var(--pico-text-muted)]">{t('runtime.installMethod')}</p>
                          <p className="mt-1 text-lg font-medium text-[color:var(--pico-text)]">
                            {setup.runtime.install_method ?? t('runtime.notRecorded')}
                          </p>
                        </div>
                        <div>
                          <p className="text-sm text-[color:var(--pico-text-muted)]">{t('runtime.lastSeen')}</p>
                          <p className="mt-1 text-lg font-medium text-[color:var(--pico-text)]">
                            {formatTimestamp(setup.runtime.last_seen_at, locale, t('runtime.notRecorded'))}
                          </p>
                        </div>
                        <div>
                          <p className="text-sm text-[color:var(--pico-text-muted)]">{t('runtime.bindings')}</p>
                          <p className="mt-1 text-lg font-medium text-[color:var(--pico-text)]">
                            {setup.runtime.binding_count}
                          </p>
                        </div>
                      </div>
                    ) : (
                      <p className="mt-3 text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                        {t('runtime.noRuntimeSnapshot')}
                      </p>
                    )}
                  </div>

                  <div className={picoEmber('p-5')}>
                    <p className={picoClasses.label}>{t('runtime.gatewayHealth')}</p>
                    <p className="mt-2 text-lg text-[color:var(--pico-text)]">
                      {setup.runtime?.gateway?.status ?? t('runtime.unknown')}
                    </p>
                    <p className="mt-3 text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                      {typeof setup.runtime?.gateway?.doctor_summary === 'string'
                        ? setup.runtime.gateway.doctor_summary
                        : t('runtime.noDoctorSummary')}
                    </p>
                  </div>
                </div>
              </>
            )}
          </div>

          <aside className="space-y-6 xl:sticky xl:top-6 xl:self-start">
            <section className={picoPanel('p-5')}>
              <p className={picoClasses.label}>{t('labels.activationTrack')}</p>
              <article className={picoInset('mt-4 grid gap-4 p-5')}>
                <div className="flex flex-col gap-3">
                  <div className="flex flex-wrap items-center gap-3">
                    <span className={picoClasses.chip}>{t('labels.doThisFirst')}</span>
                    <span className={picoClasses.chip}>{t('labels.outcomeDriven')}</span>
                  </div>
                  <h2 className="font-[family:var(--font-site-display)] text-3xl tracking-[-0.05em] text-[color:var(--pico-text)]">
                    {firstTrack.title}
                  </h2>
                  <p className={picoClasses.body}>{firstTrack.intro}</p>
                  <p className="text-sm text-[color:var(--pico-accent)]">{t('labels.outcome')} {firstTrack.outcome}</p>
                </div>
                <div className="grid gap-3">
                  {firstTrack.checklist.map((item) => (
                    <div key={item} className={picoInset('px-4 py-3 text-sm text-[color:var(--pico-text-secondary)]')}>
                      {item}
                    </div>
                  ))}
                </div>
                <div className={picoSoft('p-4')}>
                  <p className={picoClasses.body}>
                    {firstRunDone
                      ? t('operatorRecord.trackStatus.firstRunSaved')
                      : installDone
                        ? t('operatorRecord.trackStatus.installed')
                        : t('operatorRecord.trackStatus.start')}
                  </p>
                </div>
              </article>
            </section>

            <section className={picoPanel('p-5')}>
              <p className={picoClasses.label}>{t('labels.operatingRule')}</p>
              <p className="mt-3 text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                {t('doctrine.postBody')}
              </p>
              {firstRunDone ? (
                <div className="mt-4 grid gap-3">
                  {PICO_TRACKS.slice(1).map((track) => {
                    const localizedTrack = localizePicoTrack(track, contentT)
                    const selected = progress.selectedTrack === track.slug
                    const unlocked = derived.unlockedTrackSlugs.includes(track.slug)
                    return (
                      <article key={track.slug} className={picoInset('grid gap-3 p-4')}>
                        <div className="flex items-start justify-between gap-3">
                          <div>
                            <h3 className="font-[family:var(--font-site-display)] text-2xl tracking-[-0.05em] text-[color:var(--pico-text)]">
                              {localizedTrack.title}
                            </h3>
                            <p className="mt-2 text-sm leading-6 text-[color:var(--pico-text-secondary)]">{localizedTrack.intro}</p>
                          </div>
                          <button
                            type="button"
                            onClick={() => actions.pickTrack(track.slug)}
                            disabled={!unlocked}
                            className={picoClasses.tertiaryButton}
                          >
                            {selected ? t('operatorRecord.track.active') : unlocked ? t('operatorRecord.track.select') : t('runtime.locked')}
                          </button>
                        </div>
                      </article>
                    )
                  })}
                </div>
              ) : null}
            </section>
          </aside>
        </div>
      </section>

      <section className="grid gap-6 xl:grid-cols-[minmax(0,1.04fr),22rem]">
        <section className={picoPanel('p-6 sm:p-7')}>
          <p className={picoClasses.label}>{t('labels.hostedRuntimeEditor')}</p>
          <h2 className="mt-3 font-[family:var(--font-site-display)] text-3xl tracking-[-0.05em] text-[color:var(--pico-text)] sm:text-4xl">
            {t('runtimeEditor.title')}
          </h2>
          <p className="mt-3 max-w-2xl text-sm leading-6 text-[color:var(--pico-text-secondary)]">
            {t('runtimeEditor.body')}
          </p>

          {session.status !== 'authenticated' ? (
            <div className={picoSoft('mt-5 p-5')}>
              <p className={picoClasses.body}>{t('runtime.signInFirst')}</p>
            </div>
          ) : (
            <div className="mt-5 grid gap-4">
              <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                <label className="grid gap-2 text-sm text-[color:var(--pico-text-secondary)]">
                  <span className={picoClasses.label}>{t('labels.runtimeLabel')}</span>
                  <input
                    value={runtimeDraft.label}
                    onChange={(event) =>
                      setRuntimeDraft((current) => ({ ...current, label: event.target.value }))
                    }
                    className="rounded-[20px] border border-[color:var(--pico-border)] bg-[color:var(--pico-bg-surface)] px-4 py-3 text-[color:var(--pico-text)] outline-none placeholder:text-[color:var(--pico-text-muted)]"
                    placeholder="OpenClaw"
                  />
                </label>

                <label className="grid gap-2 text-sm text-[color:var(--pico-text-secondary)]">
                  <span className={picoClasses.label}>{t('labels.runtimeStatusField')}</span>
                  <select
                    value={runtimeDraft.status}
                    onChange={(event) =>
                      setRuntimeDraft((current) => ({ ...current, status: event.target.value }))
                    }
                    className="rounded-[20px] border border-[color:var(--pico-border)] bg-[color:var(--pico-bg-input)] px-4 py-3 text-[color:var(--pico-text)] outline-none"
                  >
                    {runtimeStatusOptions.map((status) => (
                      <option key={status} value={status}>
                        {t(`runtime.statusOptions.${status}`)}
                      </option>
                    ))}
                  </select>
                </label>

                <label className="grid gap-2 text-sm text-[color:var(--pico-text-secondary)]">
                  <span className={picoClasses.label}>{t('labels.installMethod')}</span>
                  <select
                    value={runtimeDraft.installMethod}
                    onChange={(event) =>
                      setRuntimeDraft((current) => ({ ...current, installMethod: event.target.value }))
                    }
                    className="rounded-[20px] border border-[color:var(--pico-border)] bg-[color:var(--pico-bg-input)] px-4 py-3 text-[color:var(--pico-text)] outline-none"
                  >
                    {installMethodOptions.map((method) => (
                      <option key={method} value={method}>
                        {t(`runtime.installMethods.${method}`)}
                      </option>
                    ))}
                  </select>
                </label>

                <label className="grid gap-2 text-sm text-[color:var(--pico-text-secondary)]">
                  <span className={picoClasses.label}>{t('labels.gatewayUrl')}</span>
                  <input
                    value={runtimeDraft.gatewayUrl}
                    onChange={(event) =>
                      setRuntimeDraft((current) => ({ ...current, gatewayUrl: event.target.value }))
                    }
                    className="rounded-[20px] border border-[color:var(--pico-border)] bg-[color:var(--pico-bg-surface)] px-4 py-3 text-[color:var(--pico-text)] outline-none placeholder:text-[color:var(--pico-text-muted)]"
                    placeholder="http://127.0.0.1:4111"
                  />
                </label>

                <label className="grid gap-2 text-sm text-[color:var(--pico-text-secondary)]">
                  <span className={picoClasses.label}>{t('labels.assistantName')}</span>
                  <input
                    value={runtimeDraft.assistantName}
                    onChange={(event) =>
                      setRuntimeDraft((current) => ({ ...current, assistantName: event.target.value }))
                    }
                    className="rounded-[20px] border border-[color:var(--pico-border)] bg-[color:var(--pico-bg-surface)] px-4 py-3 text-[color:var(--pico-text)] outline-none placeholder:text-[color:var(--pico-text-muted)]"
                    placeholder="Pico Starter"
                  />
                </label>

                <label className="grid gap-2 text-sm text-[color:var(--pico-text-secondary)]">
                  <span className={picoClasses.label}>{t('labels.workspaceField')}</span>
                  <input
                    value={runtimeDraft.workspace}
                    onChange={(event) =>
                      setRuntimeDraft((current) => ({ ...current, workspace: event.target.value }))
                    }
                    className="rounded-[20px] border border-[color:var(--pico-border)] bg-[color:var(--pico-bg-surface)] px-4 py-3 text-[color:var(--pico-text)] outline-none placeholder:text-[color:var(--pico-text-muted)]"
                    placeholder="founder-lab"
                  />
                </label>
              </div>

              <label className="grid gap-2 text-sm text-[color:var(--pico-text-secondary)]">
                <span className={picoClasses.label}>{t('labels.modelField')}</span>
                <input
                  value={runtimeDraft.model}
                  onChange={(event) =>
                    setRuntimeDraft((current) => ({ ...current, model: event.target.value }))
                  }
                  className="rounded-[20px] border border-[color:var(--pico-border)] bg-[color:var(--pico-bg-surface)] px-4 py-3 text-[color:var(--pico-text)] outline-none placeholder:text-[color:var(--pico-text-muted)]"
                  placeholder="gpt-5.4-mini"
                />
              </label>

              <div className={picoSoft('p-4')}>
                <div className="grid gap-3 sm:flex sm:flex-wrap">
                  <button
                    type="button"
                    onClick={() => void saveRuntimeSnapshot()}
                    className={picoClasses.primaryButton}
                    disabled={setup.pendingAction !== null || !runtimeDraftDirty}
                  >
                    {setup.pendingAction === 'runtime' ? t('runtimeEditor.savingSnapshot') : t('labels.saveSnapshot')}
                  </button>
                  <Link href={toHref('/academy/install-hermes-locally')} className={picoClasses.secondaryButton}>
                    {t('labels.openInstallLesson')}
                  </Link>
                </div>
                <p className="mt-3 text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                  {t('labels.saveOnlyTruth')}
                </p>
              </div>
            </div>
          )}
        </section>

        <aside className="space-y-6 xl:sticky xl:top-6 xl:self-start">
          <section className={picoPanel('p-5')}>
            <p className={picoClasses.label}>{t('labels.currentBindingTitle')}</p>
            <div className="mt-4 grid gap-3">
              <div className={picoSoft('p-4')}>
                <p className="text-sm text-[color:var(--pico-text-muted)]">{t('labels.assistant')}</p>
                <p className="mt-1 text-lg font-medium text-[color:var(--pico-text)]">
                  {currentBinding?.assistant_name ?? currentBinding?.assistant_id ?? t('runtime.notRecorded')}
                </p>
              </div>
              <div className={picoSoft('p-4')}>
                <p className="text-sm text-[color:var(--pico-text-muted)]">{t('labels.workspace')}</p>
                <p className="mt-1 text-lg font-medium text-[color:var(--pico-text)]">
                  {currentBinding?.workspace ?? setup.onboarding?.workspace ?? t('runtime.notRecorded')}
                </p>
              </div>
              <div className={picoSoft('p-4')}>
                <p className="text-sm text-[color:var(--pico-text-muted)]">{t('labels.model')}</p>
                <p className="mt-1 text-lg font-medium text-[color:var(--pico-text)]">
                  {currentBinding?.model ?? t('runtime.notRecorded')}
                </p>
              </div>
            </div>
          </section>

          {session.status === 'authenticated' && setup.onboarding ? (
            <section className={picoPanel('p-5')}>
              <p className={picoClasses.label}>{t('labels.hostedActions')}</p>
              <div className="mt-4 grid gap-3">
                <button
                  type="button"
                  onClick={() => void setup.completeCurrentStep()}
                  className={picoClasses.primaryButton}
                  disabled={setup.pendingAction !== null}
                >
                  {setup.pendingAction === 'complete_step' ? t('labels.updateStep') : t('labels.completeStep')}
                </button>
                <button
                  type="button"
                  onClick={() => void setup.dismissChecklist()}
                  className={picoClasses.secondaryButton}
                  disabled={setup.pendingAction !== null || setup.onboarding.checklist_dismissed}
                >
                  {setup.onboarding.checklist_dismissed ? t('labels.checklistDismissed') : t('runtimeEditor.dismissChecklist')}
                </button>
                <button
                  type="button"
                  onClick={() => void setup.completeAll()}
                  className={picoClasses.tertiaryButton}
                  disabled={setup.pendingAction !== null}
                >
                  {t('labels.completeWizard')}
                </button>
                <button
                  type="button"
                  onClick={() => void setup.resetWizard()}
                  className={picoClasses.tertiaryButton}
                  disabled={setup.pendingAction !== null}
                >
                  {t('labels.resetWizard')}
                </button>
              </div>
            </section>
          ) : null}
        </aside>
      </section>
    </PicoShell>
  )
}
