'use client'

import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import Link from 'next/link'
import { useTranslations } from 'next-intl'
import { usePathname, useSearchParams } from 'next/navigation'

import {
  classifyPicoSessionRuntime,
  PicoSessionBanner,
} from '@/components/pico/PicoSessionBanner'
import { PicoShell } from '@/components/pico/PicoShell'
import { PicoSurfaceCompass } from '@/components/pico/PicoSurfaceCompass'
import {
  picoClasses,
  picoEmber,
  picoInset,
  picoPanel,
  picoSoft,
} from '@/components/pico/picoTheme'
import { getPicoTutorPromptChips } from '@/components/pico/picoTutorPrompts'
import { usePicoLessonWorkspace } from '@/components/pico/usePicoLessonWorkspace'
import { usePicoProgress } from '@/components/pico/usePicoProgress'
import { usePicoSession } from '@/components/pico/usePicoSession'
import { usePicoSetupState } from '@/components/pico/usePicoSetupState'
import { PICO_LESSONS } from '@/lib/pico/academy'
import { localizePicoLesson } from '@/lib/pico/content'
import { usePicoHref } from '@/lib/pico/navigation'
import {
  classifyTutorFailure,
  getPicoTutorAcademyGuidance,
  getPicoTutorPlanCapabilities,
  LatestTutorRequest,
  normalizeTutorConnectionPayload,
  normalizeTutorReplyPayload,
  type PicoTutorConnection,
  type PicoTutorFailure,
  type PicoTutorReply,
} from '@/lib/pico/tutor'
import { cn } from '@/lib/utils'

const RECENT_QUESTIONS_KEY = 'pico.tutor.recent.v1'
const TUTOR_QUESTION_ID = 'pico-tutor-question'
const TUTOR_QUESTION_HELP_ID = 'pico-tutor-question-help'
const TUTOR_QUESTION_ERROR_ID = 'pico-tutor-question-error'
const OPENAI_KEY_ID = 'pico-tutor-openai-key'
const OPENAI_CONNECTION_ERROR_ID = 'pico-tutor-openai-error'

function resolveTutorHref(toHref: ReturnType<typeof usePicoHref>, href: string) {
  if (
    href.startsWith('/pico') ||
    href.startsWith('/docs') ||
    href.startsWith('http://') ||
    href.startsWith('https://') ||
    href.startsWith('mailto:')
  ) {
    return href
  }
  return toHref(href)
}

function readRecentQuestions() {
  if (typeof window === 'undefined') {
    return []
  }

  try {
    const raw = window.localStorage.getItem(RECENT_QUESTIONS_KEY)
    if (!raw) {
      return []
    }

    const parsed = JSON.parse(raw)
    return Array.isArray(parsed)
      ? parsed
          .filter((item): item is string => typeof item === 'string' && item.trim().length > 0)
          .slice(0, 5)
      : []
  } catch {
    return []
  }
}

function writeRecentQuestions(nextQuestions: string[]) {
  if (typeof window === 'undefined') {
    return
  }

  window.localStorage.setItem(
    RECENT_QUESTIONS_KEY,
    JSON.stringify(nextQuestions.slice(0, 5)),
  )
}

export function PicoTutorPageClient() {
  const pathname = usePathname()
  const t = useTranslations('pico.tutorPage')
  const contentT = useTranslations('pico.content')
  const session = usePicoSession()
  const setup = usePicoSetupState(session.status === 'authenticated')
  const { progress, derived, actions, syncState } = usePicoProgress(
    session.status === 'authenticated',
  )
  const toHref = usePicoHref()
  const searchParams = useSearchParams()
  const lessonFromQuery = searchParams.get('lesson')
  const defaultLessonSlug =
    (lessonFromQuery && PICO_LESSONS.some((lesson) => lesson.slug === lessonFromQuery)
      ? lessonFromQuery
      : null) ??
    (progress.selectedTrack
      ? PICO_LESSONS.find((lesson) => lesson.track === progress.selectedTrack)?.slug ?? ''
      : '')
  const [question, setQuestion] = useState('')
  const [lessonSlug, setLessonSlug] = useState(defaultLessonSlug)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<PicoTutorFailure | null>(null)
  const [reply, setReply] = useState<PicoTutorReply | null>(null)
  const [recentQuestions, setRecentQuestions] = useState<string[]>([])
  const [formReady, setFormReady] = useState(false)
  const [openAIConnection, setOpenAIConnection] = useState<PicoTutorConnection | null>(null)
  const [openAIConnectionLoading, setOpenAIConnectionLoading] = useState(false)
  const [openAIConnectionSaving, setOpenAIConnectionSaving] = useState(false)
  const [openAIConnectionError, setOpenAIConnectionError] = useState<string | null>(null)
  const [openAIApiKey, setOpenAIApiKey] = useState('')
  const runtimeBannerLabel = setup.runtime?.status ?? t('form.packet.notSynced')
  const runtimeBannerState = classifyPicoSessionRuntime({
    loading: setup.loading,
    error: setup.error,
    status: setup.runtime?.status,
    stale: setup.runtime?.stale,
  })
  const chatRequests = useRef(new LatestTutorRequest())
  const connectionReads = useRef(new LatestTutorRequest())
  const connectionMutations = useRef(new LatestTutorRequest())
  const sessionPlan = session.status === 'authenticated' ? session.user.plan : null
  const sessionCapabilities = useMemo(
    () => getPicoTutorPlanCapabilities(sessionPlan),
    [sessionPlan],
  )
  const availableLessons = useMemo(
    () => PICO_LESSONS.map((lesson) => localizePicoLesson(lesson, contentT)),
    [contentT],
  )
  const selectedLesson = useMemo(
    () => availableLessons.find((lesson) => lesson.slug === lessonSlug) ?? null,
    [availableLessons, lessonSlug],
  )
  const nextLesson = useMemo(
    () => availableLessons.find((lesson) => lesson.slug === derived.nextLesson?.slug) ?? null,
    [availableLessons, derived.nextLesson?.slug],
  )
  const lessonWorkspace = usePicoLessonWorkspace(selectedLesson?.slug ?? 'tutor', selectedLesson?.steps.length ?? 0, {
    progress,
    persistRemote: selectedLesson
      ? (lessonSlug, workspace) => actions.setLessonWorkspace(lessonSlug, workspace)
      : undefined,
  })
  const tutorMethod = [
    {
      label: t('method.cards.frame.label'),
      title: t('method.cards.frame.title'),
      body: selectedLesson
        ? t('method.cards.frame.bodyWithLesson', { lessonTitle: selectedLesson.title })
        : t('method.cards.frame.bodyWithoutLesson'),
    },
    {
      label: t('method.cards.evidence.label'),
      title: t('method.cards.evidence.title'),
      body: t('method.cards.evidence.body'),
    },
    {
      label: t('method.cards.exit.label'),
      title: t('method.cards.exit.title'),
      body: t('method.cards.exit.body'),
    },
  ]
  const questionProtocol = ([0, 1, 2] as const).map((index) =>
    t(`form.questionProtocol.${index}`),
  )
  const lessonReviewBoard = selectedLesson
    ? [
        {
          label: t('method.lessonReviewBoard.lessonBrief'),
          value: selectedLesson.objective,
        },
        {
          label: t('method.lessonReviewBoard.deliverable'),
          value: selectedLesson.expectedResult,
        },
        {
          label: t('method.lessonReviewBoard.critiqueLine'),
          value: selectedLesson.validation,
        },
      ]
    : []
  const promptChips = useMemo(
    () => getPicoTutorPromptChips(
      selectedLesson,
      ([0, 1, 2] as const).map((index) => t(`form.examplePrompts.${index}`)),
      sessionCapabilities.tutorAccess,
    ),
    [selectedLesson, sessionCapabilities.tutorAccess, t],
  )
  const authoritativeTutorAccess = Boolean(
    openAIConnection?.entitlement.tutorAccess && openAIConnection.providerAvailable,
  )
  const academyGuidance = useMemo(
    () =>
      getPicoTutorAcademyGuidance(
        selectedLesson,
        lessonWorkspace.workspace.activeStepIndex >= 0
          ? lessonWorkspace.workspace.activeStepIndex
          : 0,
      ),
    [lessonWorkspace.workspace.activeStepIndex, selectedLesson],
  )
  const tutorSignal = reply
    ? t('hero.signal.answerReady')
    : loading
      ? t('hero.signal.reviewingBlocker')
      : selectedLesson
        ? t('hero.signal.lessonAttached')
        : t('hero.signal.awaitingBlocker')
  const connectionSignal =
    session.status !== 'authenticated'
      ? t('hero.signal.localOnly')
      : openAIConnectionLoading
        ? t('hero.signal.checking')
        : openAIConnection?.status === 'connected'
          ? t('hero.signal.openaiConnected')
          : openAIConnection?.status === 'platform'
            ? t('hero.signal.platformAccess')
            : openAIConnection?.status === 'disconnected'
              ? t('hero.signal.providerMissing')
              : sessionCapabilities.tutorAccess
                ? t('hero.signal.statusUnavailable')
                : t('hero.signal.academyOnly')
  const tutorCanSubmit =
    session.status === 'authenticated' &&
    sessionCapabilities.tutorAccess &&
    authoritativeTutorAccess &&
    !openAIConnectionLoading &&
    !openAIConnectionSaving
  const tutorAvailabilityMessage =
    session.status === 'loading'
      ? t('availability.checkingEntitlement')
      : session.status !== 'authenticated'
        ? t('availability.signIn')
        : !sessionCapabilities.tutorAccess
          ? t('availability.readOnly')
          : openAIConnectionLoading
            ? t('availability.checkingProvider')
            : !openAIConnection?.providerAvailable
              ? openAIConnection?.message
                ? t('availability.providerDetail', { detail: openAIConnection.message })
                : t('availability.providerUnavailable')
              : t('availability.readyThrough', {
                  provider: openAIConnection.source === 'user'
                    ? t('availability.validatedKey')
                    : t('availability.platformProvider'),
                })
  const lessonSignal = selectedLesson
    ? t('hero.signal.lessonSteps', { completed: lessonWorkspace.completedStepCount, total: selectedLesson.steps.length })
    : t('hero.signal.attachLesson')
  const focusedStepLabel =
    selectedLesson && lessonWorkspace.workspace.activeStepIndex >= 0
      ? selectedLesson.steps[lessonWorkspace.workspace.activeStepIndex]?.title ?? t('hero.signal.notSet')
      : t('hero.signal.notSet')
  const tutorPacketPreview = [
    t('hero.packetPreview.lane', { value: selectedLesson?.title ?? t('hero.packetPreview.noneAttached') }),
    t('hero.packetPreview.state', { value: tutorSignal }),
    t('hero.packetPreview.focus', { value: focusedStepLabel }),
    t('hero.packetPreview.output', { value: t('hero.packetPreview.groundedMove') }),
  ].join('\n')

  useEffect(() => {
    setLessonSlug(defaultLessonSlug)
  }, [defaultLessonSlug])

  useEffect(() => {
    setRecentQuestions(readRecentQuestions())
    setFormReady(true)
  }, [])

  useEffect(() => {
    if (
      progress.platform.activeSurface !== 'tutor' ||
      (selectedLesson && progress.platform.lastOpenedLessonSlug !== selectedLesson.slug)
    ) {
      actions.setPlatform({
        activeSurface: 'tutor',
        ...(selectedLesson ? { lastOpenedLessonSlug: selectedLesson.slug } : {}),
      })
    }
  }, [
    actions,
    progress.platform.activeSurface,
    progress.platform.lastOpenedLessonSlug,
    selectedLesson,
  ])

  useEffect(() => {
    if (progress.platform.activeSurface !== 'tutor') {
      actions.setPlatform({ activeSurface: 'tutor' })
    }
  }, [actions, progress.platform.activeSurface])

  const loadConnection = useCallback(async (): Promise<PicoTutorConnection | null> => {
    const lease = connectionReads.current.begin()
    setOpenAIConnectionLoading(true)
    setOpenAIConnectionError(null)

    try {
      const response = await fetch('/api/pico/tutor/openai', {
        credentials: 'include',
        cache: 'no-store',
        signal: lease.signal,
      })
      const payload: unknown = await response.json().catch(() => null)
      if (!connectionReads.current.isCurrent(lease)) return null
      if (!response.ok) {
        const failure = classifyTutorFailure(response.status, payload)
        setOpenAIConnection(null)
        setOpenAIConnectionError(failure.message)
        return null
      }

      const connection = normalizeTutorConnectionPayload(payload)
      if (!connection) {
        setOpenAIConnection(null)
        setOpenAIConnectionError(t('errors.providerStatusUnverified'))
        return null
      }

      setOpenAIConnection(connection)
      return connection
    } catch (loadError) {
      if (loadError instanceof Error && loadError.name === 'AbortError') return null
      if (connectionReads.current.isCurrent(lease)) {
        setOpenAIConnection(null)
        setOpenAIConnectionError(
          loadError instanceof Error ? loadError.message : t('errors.loadOpenAIConnection'),
        )
      }
      return null
    } finally {
      if (connectionReads.current.isCurrent(lease)) {
        connectionReads.current.finish(lease)
        setOpenAIConnectionLoading(false)
      }
    }
  }, [t])

  useEffect(() => {
    connectionReads.current.cancel()
    connectionMutations.current.cancel()
    chatRequests.current.cancel()
    setLoading(false)
    setReply(null)
    setError(null)
    setOpenAIConnectionSaving(false)

    if (session.status === 'authenticated' && sessionCapabilities.tutorAccess) {
      void loadConnection()
    } else {
      setOpenAIConnection(null)
      setOpenAIConnectionLoading(false)
      setOpenAIConnectionError(null)
      setOpenAIApiKey('')
    }

    return () => {
      connectionReads.current.cancel()
      connectionMutations.current.cancel()
      chatRequests.current.cancel()
    }
  }, [loadConnection, session.status, sessionPlan, sessionCapabilities.tutorAccess])

  useEffect(() => {
    chatRequests.current.cancel()
    setLoading(false)
    setReply(null)
    setError(null)
  }, [openAIConnection?.source, openAIConnection?.status, openAIConnection?.validatedAt])

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!question.trim()) return

    if (session.status !== 'authenticated') {
      setError({
        kind: 'unauthenticated',
        message: t('errors.signInForLiveTutor'),
        retryable: false,
      })
      return
    }
    if (!sessionCapabilities.tutorAccess || !openAIConnection?.entitlement.tutorAccess) {
      setError({
        kind: 'plan_denied',
        message: t('errors.planRequired'),
        retryable: false,
      })
      return
    }
    if (!authoritativeTutorAccess) {
      setError({
        kind: 'provider_required',
        message: openAIConnection.message,
        retryable: false,
      })
      return
    }

    const lease = chatRequests.current.begin()
    setLoading(true)
    setError(null)
    setReply(null)
    try {
      const response = await fetch('/api/pico/tutor', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          question,
          lessonSlug: lessonSlug || null,
          progress,
          setupContext: {
            onboarding: setup.onboarding
              ? {
                  provider: setup.onboarding.provider,
                  status: setup.onboarding.status,
                  current_step: setup.onboarding.current_step,
                  completed_steps: setup.onboarding.completed_steps,
                  assistant_id: setup.onboarding.assistant_id,
                  workspace: setup.onboarding.workspace,
                  gateway_url: setup.onboarding.gateway_url,
                }
              : null,
            runtime: setup.runtime
              ? {
                  provider: setup.runtime.provider,
                  status: setup.runtime.status,
                  gateway_url: setup.runtime.gateway_url,
                  binding_count: setup.runtime.binding_count,
                  version: setup.runtime.version,
                  current_binding: setup.runtime.current_binding,
                }
              : null,
            currentSurface: 'tutor',
          },
        }),
        signal: lease.signal,
      })
      const payload: unknown = await response.json().catch(() => null)
      if (!chatRequests.current.isCurrent(lease)) return
      if (!response.ok) {
        setError(classifyTutorFailure(response.status, payload))
        return
      }

      const normalizedReply = normalizeTutorReplyPayload(payload)
      if (
        !normalizedReply ||
        normalizedReply.entitlement.plan !== openAIConnection.entitlement.plan ||
        normalizedReply.generation.source !== openAIConnection.source
      ) {
        setError({
          kind: 'malformed_response',
          message: t('errors.unverifiedResponse'),
          retryable: true,
        })
        return
      }

      const normalizedQuestion = question.trim()
      setReply(normalizedReply)
      setRecentQuestions((currentQuestions) => {
        const nextQuestions = [
          normalizedQuestion,
          ...currentQuestions.filter((item) => item !== normalizedQuestion),
        ].slice(0, 5)
        writeRecentQuestions(nextQuestions)
        return nextQuestions
      })
      actions.recordTutorQuestion()
    } catch (submitError) {
      if (submitError instanceof Error && submitError.name === 'AbortError') return
      if (chatRequests.current.isCurrent(lease)) {
        setReply(null)
        setError({
          kind: 'model_unavailable',
          message: submitError instanceof Error ? submitError.message : t('errors.tutorRequestFailed'),
          retryable: true,
        })
      }
    } finally {
      if (chatRequests.current.isCurrent(lease)) {
        chatRequests.current.finish(lease)
        setLoading(false)
      }
    }
  }

  function cancelTutorRequest() {
    chatRequests.current.cancel()
    setLoading(false)
    setError({
      kind: 'unknown',
      message: t('errors.requestCanceled'),
      retryable: true,
    })
  }

  async function connectOpenAI() {
    if (!openAIApiKey.trim()) {
      setOpenAIConnectionError(t('errors.pasteOpenAIKeyFirst'))
      return
    }
    if (!openAIConnection?.canConnect) {
      setOpenAIConnectionError(t('errors.proPlanRequired'))
      return
    }

    const lease = connectionMutations.current.begin()
    chatRequests.current.cancel()
    setLoading(false)
    setReply(null)
    setOpenAIConnectionSaving(true)
    setOpenAIConnectionError(null)
    try {
      const response = await fetch('/api/pico/tutor/openai', {
        method: 'PUT',
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ apiKey: openAIApiKey.trim() }),
        signal: lease.signal,
      })
      const payload: unknown = await response.json().catch(() => null)

      if (!connectionMutations.current.isCurrent(lease)) return
      if (!response.ok) {
        throw new Error(classifyTutorFailure(response.status, payload).message)
      }

      const canonical = await loadConnection()
      if (
        !connectionMutations.current.isCurrent(lease) ||
        canonical?.status !== 'connected' ||
        canonical.source !== 'user'
      ) {
        throw new Error(t('errors.keyUpdateUnconfirmed'))
      }
      setOpenAIApiKey('')
    } catch (connectError) {
      if (!(connectError instanceof Error && connectError.name === 'AbortError')) {
        setOpenAIConnectionError(
          connectError instanceof Error ? connectError.message : t('errors.connectOpenAIKey'),
        )
      }
    } finally {
      if (connectionMutations.current.isCurrent(lease)) {
        connectionMutations.current.finish(lease)
        setOpenAIConnectionSaving(false)
      }
    }
  }

  async function disconnectOpenAI() {
    if (!openAIConnection?.canConnect) return
    const lease = connectionMutations.current.begin()
    chatRequests.current.cancel()
    setLoading(false)
    setReply(null)
    setOpenAIConnectionSaving(true)
    setOpenAIConnectionError(null)
    try {
      const response = await fetch('/api/pico/tutor/openai', {
        method: 'DELETE',
        credentials: 'include',
        signal: lease.signal,
      })
      const payload: unknown = await response.json().catch(() => null)

      if (!connectionMutations.current.isCurrent(lease)) return
      if (!response.ok) {
        throw new Error(classifyTutorFailure(response.status, payload).message)
      }

      const canonical = await loadConnection()
      if (
        !connectionMutations.current.isCurrent(lease) ||
        !canonical ||
        canonical.status === 'connected' ||
        canonical.source === 'user'
      ) {
        throw new Error(t('errors.disconnectUnconfirmed'))
      }
    } catch (disconnectError) {
      if (!(disconnectError instanceof Error && disconnectError.name === 'AbortError')) {
        setOpenAIConnectionError(
          disconnectError instanceof Error
            ? disconnectError.message
            : t('errors.disconnectOpenAIKey'),
        )
      }
    } finally {
      if (connectionMutations.current.isCurrent(lease)) {
        connectionMutations.current.finish(lease)
        setOpenAIConnectionSaving(false)
      }
    }
  }

  return (
    <PicoShell
      eyebrow={t('shell.eyebrow')}
      title={t('shell.title')}
      description={t('shell.description')}
      heroContent={
        <div
          className="relative overflow-hidden rounded-[28px] border border-[color:var(--pico-border-hover)] bg-[linear-gradient(135deg,rgba(var(--pico-accent-rgb),0.14),rgba(8,14,9,0.92)_36%,rgba(255,255,255,0.02)_100%)] p-5 shadow-[0_24px_70px_rgba(0,0,0,0.28)] sm:p-6"
          data-testid="pico-tutor-hero-signal"
        >
          <div
            aria-hidden="true"
            className="pointer-events-none absolute inset-0 bg-[linear-gradient(180deg,rgba(255,255,255,0.03),transparent_30%,transparent_72%,rgba(255,255,255,0.02))]"
          />
          <div
            aria-hidden="true"
            className="pointer-events-none absolute -start-10 top-8 h-40 w-40 rounded-full bg-[rgba(var(--pico-accent-rgb),0.12)] blur-3xl"
          />
          <div
            aria-hidden="true"
            className="pointer-events-none absolute bottom-0 end-0 h-48 w-48 rounded-full bg-[rgba(var(--pico-accent-rgb),0.1)] blur-3xl"
          />
          <div className="relative grid gap-5 xl:grid-cols-[minmax(0,1fr),18rem]">
            <div className="grid gap-5">
              <div className="flex flex-wrap items-center gap-2">
                <span className={picoClasses.chip}>{t('hero.badge')}</span>
                <span className="inline-flex rounded-full border border-[color:var(--pico-border)] bg-[rgba(255,255,255,0.03)] px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-[color:var(--pico-text-secondary)]">
                  {tutorSignal}
                </span>
              </div>
              <h2 className="font-[family:var(--font-site-display)] text-[clamp(1.9rem,4vw,2.9rem)] leading-[0.94] tracking-[-0.06em] text-[color:var(--pico-text)]">
                {t('hero.title')}
              </h2>
              <p className="max-w-2xl text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                {t('hero.body')}
              </p>

              <div className="grid gap-3 sm:grid-cols-3">
                <div className={picoSoft('p-4')}>
                  <p className={picoClasses.label}>{t('hero.lessonLane.label')}</p>
                  <p className="mt-2 font-[family:var(--font-site-display)] text-3xl tracking-[-0.05em] text-[color:var(--pico-text)]">
                    {lessonSignal}
                  </p>
                  <p className="mt-2 text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                    {selectedLesson ? selectedLesson.title : t('hero.lessonLane.connectBlockedLesson')}
                  </p>
                </div>

                <div className={picoSoft('p-4')}>
                  <p className={picoClasses.label}>{t('hero.replyState.label')}</p>
                  <p className="mt-2 font-[family:var(--font-site-display)] text-3xl tracking-[-0.05em] text-[color:var(--pico-text)]">
                    {tutorSignal}
                  </p>
                  <p className="mt-2 text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                    {reply ? t('hero.replyState.readyToActOn') : t('hero.replyState.waitingForPreciseBlocker')}
                  </p>
                </div>

                <div className={picoSoft('p-4')}>
                  <p className={picoClasses.label}>{t('hero.connection.label')}</p>
                  <p className="mt-2 font-[family:var(--font-site-display)] text-3xl tracking-[-0.05em] text-[color:var(--pico-text)]">
                    {connectionSignal}
                  </p>
                  <p className="mt-2 text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                    {tutorAvailabilityMessage}
                  </p>
                </div>
              </div>

              <div className={picoInset('grid gap-3 p-4 sm:grid-cols-[auto,minmax(0,1fr)] sm:items-center')}>
                <div className="flex h-14 w-14 items-center justify-center rounded-[20px] border border-[rgba(var(--pico-accent-rgb),0.24)] bg-[linear-gradient(180deg,rgba(var(--pico-accent-rgb),0.18),rgba(7,13,8,0.5))] shadow-[0_18px_40px_rgba(var(--pico-accent-rgb),0.12)]">
                  <span className="h-3 w-3 rounded-full bg-[color:var(--pico-accent-bright)] shadow-[0_0_18px_rgba(var(--pico-accent-rgb),0.5)]" />
                </div>
                <div className="min-w-0">
                  <p className={picoClasses.label}>{t('hero.focusedStep.label')}</p>
                  <p className="mt-2 font-[family:var(--font-site-display)] text-2xl tracking-[-0.05em] text-[color:var(--pico-text)]">
                    {focusedStepLabel}
                  </p>
                  <p className="mt-2 text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                    {t('hero.focusedStep.body')}
                  </p>
                </div>
              </div>
            </div>

            <div className={picoInset('grid gap-4 overflow-hidden border-[color:rgba(var(--pico-accent-rgb),0.24)] bg-[radial-gradient(circle_at_50%_20%,rgba(var(--pico-accent-rgb),0.16),rgba(6,11,7,0.94)_54%,rgba(3,5,3,0.98)_100%)] p-4')}>
              <div className={picoSoft('p-4')}>
                <p className={picoClasses.label}>{t('hero.packetPreview.label')}</p>
                <pre className="mt-3 whitespace-pre-wrap text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                  <code>{tutorPacketPreview}</code>
                </pre>
              </div>
              <div className={picoSoft('p-4')}>
                <p className={picoClasses.label}>{t('hero.recentPressure.label')}</p>
                <p className="mt-3 text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                  {recentQuestions[0]
                    ? recentQuestions[0]
                    : t('hero.recentPressure.empty')}
                </p>
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
            href={selectedLesson ? toHref(`/academy/${selectedLesson.slug}`) : toHref('/academy')}
            className={picoClasses.secondaryButton}
          >
            {selectedLesson ? t('actions.backToLesson') : t('actions.openAcademy')}
          </Link>
          <Link href={toHref('/support')} className={picoClasses.primaryButton}>
            {t('actions.escalateToHumanHelp')}
          </Link>
        </div>
      }
    >
      <PicoSessionBanner
        session={session}
        nextPath={pathname}
        progressSyncState={syncState}
        runtimeSignal={{ label: runtimeBannerLabel, state: runtimeBannerState }}
      />
      <PicoSurfaceCompass
        title={t('compass.title')}
        body={t('compass.body')}
        status={
          reply
            ? t('compass.status.answerReady')
            : selectedLesson
              ? t('compass.status.lessonContextAttached')
              : t('compass.status.awaitingBlocker')
        }
        aside={t('compass.aside')}
        items={[
          {
            href: selectedLesson
              ? toHref(`/academy/${selectedLesson.slug}`)
              : nextLesson
                ? toHref(`/academy/${nextLesson.slug}`)
                : toHref('/academy'),
            label: selectedLesson
              ? t('compass.items.returnToBlockedLesson')
              : nextLesson
                ? t('shared.openLesson', { lessonTitle: nextLesson.title })
                : t('compass.items.returnToAcademy'),
            caption: t('compass.items.returnCaption'),
            note: t('compass.items.resumeLane'),
            tone: 'primary',
          },
          {
            href: toHref('/autopilot'),
            label: t('compass.items.inspectLiveControlRoom'),
            caption: t('compass.items.inspectCaption'),
            note: t('compass.items.runtime'),
            tone: 'soft',
          },
          {
            href: toHref('/support'),
            label: t('compass.items.openSupportLane'),
            caption: t('compass.items.escalateCaption'),
            note: t('compass.items.escalate'),
          },
        ]}
      />

      <section className={picoPanel('p-6 sm:p-7')} data-testid="pico-tutor-crit-desk">
        <div className="grid gap-6 lg:grid-cols-[minmax(0,1.08fr),20rem]">
          <div>
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div>
                <p className={picoClasses.label}>{t('method.label')}</p>
                <h2 className="mt-3 font-[family:var(--font-site-display)] text-4xl tracking-[-0.06em] text-[color:var(--pico-text)]">
                  {t('method.title')}
                </h2>
              </div>
              <span className={picoClasses.chip}>{t('method.chip')}</span>
            </div>

            <div className="mt-6 grid gap-4 xl:grid-cols-3">
              {tutorMethod.map((item) => (
                <article key={item.label} className={picoInset('flex h-full flex-col p-5')}>
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
              <p className={picoClasses.label}>{t('method.deskPosture.label')}</p>
              <p className="mt-3 text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                {t('method.deskPosture.body')}
              </p>
            </div>
            <div className={picoInset('p-5')}>
              <p className={picoClasses.label}>{t('method.attachedLane.label')}</p>
              <p className="mt-3 text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                {selectedLesson
                  ? t('method.attachedLane.bodyWithLesson', { lessonTitle: selectedLesson.title })
                  : t('method.attachedLane.bodyWithoutLesson')}
              </p>
            </div>
          </div>
        </div>
      </section>

      <section className="grid gap-6 xl:grid-cols-[minmax(0,1.08fr),22rem]">
        <div className={picoPanel('overflow-hidden p-0')}>
          <div className="grid gap-0 border-b border-[color:var(--pico-border)] lg:grid-cols-[minmax(0,1fr),18rem]">
            <form onSubmit={submit} aria-busy={loading} className="p-6 sm:p-7">
              <p className={picoClasses.label}>{t('form.label')}</p>
              <div className="mt-3 flex items-center gap-4">
                <span
                  aria-hidden="true"
                  className="inline-flex h-12 w-12 shrink-0 items-center justify-center border border-[color:var(--pico-accent)] font-[family:var(--font-mono)] text-xs font-semibold tracking-[0.14em] text-[color:var(--pico-accent)]"
                >
                  03
                </span>
                <h2 className="font-[family:var(--font-site-display)] text-4xl tracking-[-0.06em] text-[color:var(--pico-text)] sm:text-5xl">
                  {t('form.title')}
                </h2>
              </div>
              <p className="mt-4 max-w-3xl text-sm leading-7 text-[color:var(--pico-text-secondary)] sm:text-base">
                {t('form.body')}
              </p>
              <p className="mt-3 text-xs uppercase tracking-[0.18em] text-[color:var(--pico-text-muted)]">
                {tutorAvailabilityMessage}
              </p>

              {!tutorCanSubmit ? (
                <div
                  role="status"
                  aria-live="polite"
                  className={picoInset('mt-5 p-4 text-sm leading-6 text-[color:var(--pico-text-secondary)]')}
                  data-testid="pico-tutor-read-only-notice"
                >
                  <p>{tutorAvailabilityMessage}</p>
                  <div className="mt-3 flex flex-col gap-2 sm:flex-row sm:flex-wrap">
                    <Link href={toHref('/academy')} className={cn(picoClasses.secondaryButton, 'w-full sm:w-auto')}>
                      {t('actions.openAcademy')}
                    </Link>
                    {session.status === 'authenticated' && !sessionCapabilities.tutorAccess ? (
                      <Link href={toHref('/pricing')} className={cn(picoClasses.tertiaryButton, 'w-full sm:w-auto')}>
                        {t('form.comparePlans')}
                      </Link>
                    ) : null}
                  </div>
                </div>
              ) : null}

              {selectedLesson ? (
                <div className={picoEmber('mt-6 p-5')}>
                  <p className="font-medium text-[color:var(--pico-text)]">{t('form.whereYouAre.label')}</p>
                  <p className="mt-2 text-sm leading-6">
                    {t('form.whereYouAre.body', { lessonTitle: selectedLesson.title })}
                  </p>
                  <div className="mt-4 grid gap-3 xl:grid-cols-5">
                    {lessonReviewBoard.map((item) => (
                      <div key={item.label} className={picoInset('p-4')}>
                        <p className={picoClasses.label}>{item.label}</p>
                        <p className="mt-3 text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                          {item.value}
                        </p>
                      </div>
                    ))}
                  </div>
                  <div className="mt-4 grid gap-3 sm:grid-cols-2">
                    <div className={picoInset('p-4')}>
                      <p className="text-sm text-[color:var(--pico-text-muted)]">{t('form.whereYouAre.lessonSteps')}</p>
                      <p className="mt-1 text-lg font-medium text-[color:var(--pico-text)]">
                        {lessonWorkspace.completedStepCount}/{selectedLesson.steps.length}
                      </p>
                    </div>
                    <div className={picoInset('p-4')}>
                      <p className="text-sm text-[color:var(--pico-text-muted)]">{t('form.whereYouAre.focusedStep')}</p>
                      <p className="mt-1 text-lg font-medium text-[color:var(--pico-text)]">
                        {lessonWorkspace.workspace.activeStepIndex >= 0
                          ? selectedLesson.steps[lessonWorkspace.workspace.activeStepIndex]?.title ?? t('hero.signal.notSet')
                          : t('hero.signal.notSet')}
                      </p>
                    </div>
                  </div>
                  <Link
                    href={toHref(`/academy/${selectedLesson.slug}`)}
                    className="mt-4 inline-flex text-sm font-medium text-[color:var(--pico-text)] underline decoration-[color:rgba(var(--pico-accent-rgb),0.38)] underline-offset-4"
                  >
                    {t('form.whereYouAre.backToLesson')}
                  </Link>
                </div>
              ) : null}

              <div className={picoInset('mt-6 grid gap-4 p-5')}>
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <p className={picoClasses.label}>{t('form.packet.label')}</p>
                    <p
                      id={TUTOR_QUESTION_HELP_ID}
                      className="mt-2 text-sm leading-6 text-[color:var(--pico-text-secondary)]"
                    >
                      {t('form.packet.body')}
                    </p>
                  </div>
                  <span className={picoClasses.chip}>{t('form.packet.chip')}</span>
                </div>

                <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
                  <div className={picoSoft('p-4')}>
                    <p className="text-sm text-[color:var(--pico-text-muted)]">{t('form.packet.currentTrack')}</p>
                    <p className="mt-1 text-lg font-medium text-[color:var(--pico-text)]">
                      {progress.selectedTrack ? contentT(`tracks.${progress.selectedTrack}.title`) : t('form.packet.currentTrackNotChosenYet')}
                    </p>
                  </div>
                  <div className={picoSoft('p-4')}>
                    <p className="text-sm text-[color:var(--pico-text-muted)]">{t('form.packet.nextLesson')}</p>
                    <p className="mt-1 text-lg font-medium text-[color:var(--pico-text)]">
                      {nextLesson?.title ?? t('form.packet.nextLessonNone')}
                    </p>
                  </div>
                  <div className={picoSoft('p-4')}>
                    <p className="text-sm text-[color:var(--pico-text-muted)]">{t('form.packet.hostedOnboardingStep')}</p>
                    <p className="mt-1 text-lg font-medium text-[color:var(--pico-text)]">
                      {setup.onboarding?.current_step ?? t('form.packet.sessionRequired')}
                    </p>
                  </div>
                  <div className={picoSoft('p-4')}>
                    <p className="text-sm text-[color:var(--pico-text-muted)]">{t('form.packet.runtimeStatus')}</p>
                    <p className="mt-1 text-lg font-medium text-[color:var(--pico-text)]">
                      {setup.runtime?.status ?? t('form.packet.notSynced')}
                    </p>
                  </div>
                </div>

                <div className="grid gap-3 lg:grid-cols-3">
                  {questionProtocol.map((item, index) => (
                    <div key={item} className={picoSoft('p-4')}>
                      <div className="flex items-start gap-3">
                        <span className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-full border border-[color:var(--pico-border)] bg-[rgba(var(--pico-accent-rgb),0.12)] text-[11px] font-semibold uppercase tracking-[0.18em] text-[color:var(--pico-accent)]">
                          {String(index + 1).padStart(2, '0')}
                        </span>
                        <p className="pt-1 text-sm leading-6 text-[color:var(--pico-text-secondary)]">{item}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              <label htmlFor={TUTOR_QUESTION_ID} className="sr-only">
                {t('form.questionLabel')}
              </label>
              <textarea
                id={TUTOR_QUESTION_ID}
                value={question}
                onChange={(event) => setQuestion(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Escape' && loading) {
                    event.preventDefault()
                    cancelTutorRequest()
                  } else if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) {
                    event.preventDefault()
                    event.currentTarget.form?.requestSubmit()
                  }
                }}
                enterKeyHint="send"
                disabled={!formReady || loading || !tutorCanSubmit}
                aria-invalid={Boolean(error)}
                aria-describedby={
                  error
                    ? `${TUTOR_QUESTION_HELP_ID} ${TUTOR_QUESTION_ERROR_ID}`
                    : TUTOR_QUESTION_HELP_ID
                }
                placeholder={t('form.questionPlaceholder')}
                className="mt-6 min-h-[240px] w-full rounded-[28px] border border-[color:var(--pico-border)] bg-[color:var(--pico-bg-surface)] px-5 py-5 text-sm leading-7 text-[color:var(--pico-text-secondary)] outline-none placeholder:text-[color:var(--pico-text-muted)] focus-visible:border-[color:var(--pico-border-hover)] focus-visible:ring-2 focus-visible:ring-[rgba(var(--pico-accent-rgb),0.35)]"
              />

              <div className="mt-5 grid gap-4 lg:grid-cols-[minmax(0,1fr),auto] lg:items-end">
                <label className="block text-sm text-[color:var(--pico-text-secondary)]">
                  <span className={picoClasses.label}>{t('form.blockedLessonLabel')}</span>
                  <select
                    value={lessonSlug}
                    onChange={(event) => setLessonSlug(event.target.value)}
                    disabled={!formReady || loading}
                    className="mt-3 w-full rounded-[22px] border border-[color:var(--pico-border)] bg-[color:var(--pico-bg-surface)] px-4 py-3 text-sm text-[color:var(--pico-text-secondary)] outline-none focus-visible:border-[color:var(--pico-border-hover)] focus-visible:ring-2 focus-visible:ring-[rgba(var(--pico-accent-rgb),0.35)]"
                  >
                    <option value="">{t('form.noLessonSelected')}</option>
                    {availableLessons.map((lesson) => (
                      <option key={lesson.slug} value={lesson.slug}>
                        {lesson.title}
                      </option>
                    ))}
                  </select>
                </label>
                <div className="flex flex-col gap-2 sm:flex-row">
                  <button
                    type="submit"
                    disabled={!formReady || loading || !tutorCanSubmit}
                    className={cn(picoClasses.primaryButton, 'w-full sm:w-auto')}
                  >
                    {loading ? t('form.submitLoading') : t('form.submitIdle')}
                  </button>
                  {loading ? (
                    <button
                      type="button"
                      onClick={cancelTutorRequest}
                      className={cn(picoClasses.secondaryButton, 'w-full sm:w-auto')}
                    >
                      {t('form.cancelRequest')}
                    </button>
                  ) : null}
                </div>
              </div>

              {promptChips.length ? (
                <div className="mt-5 grid gap-2 sm:flex sm:flex-wrap">
                  {promptChips.map((prompt) => (
                    <button
                      key={prompt}
                      type="button"
                      onClick={() => setQuestion(prompt)}
                      disabled={!formReady || loading || !tutorCanSubmit}
                      className={picoClasses.tertiaryButton}
                    >
                      {prompt}
                    </button>
                  ))}
                </div>
              ) : null}
            </form>

            <div className="border-t border-[color:var(--pico-border)] bg-[color:var(--pico-bg-surface)] p-6 lg:border-s lg:border-t-0">
              <p className={picoClasses.label}>{t('rail.label')}</p>
              <div className="mt-4 grid gap-3">
                <div className={picoSoft('p-4')}>
                  <p className="text-sm text-[color:var(--pico-text-muted)]">{t('rail.questionsAsked')}</p>
                  <p className="mt-1 text-2xl font-semibold text-[color:var(--pico-text)]">{progress.tutorQuestions}</p>
                </div>
                <div className={picoSoft('p-4')}>
                  <p className="text-sm text-[color:var(--pico-text-muted)]">{t('rail.liveAnswerState')}</p>
                  <p className="mt-1 text-lg font-medium text-[color:var(--pico-text)]">
                    {reply ? reply.confidence : loading ? t('rail.thinking') : t('rail.waiting')}
                  </p>
                </div>
              </div>

              {recentQuestions.length > 0 ? (
                <div className={picoInset('mt-4 p-4')}>
                  <p className={picoClasses.label}>{t('rail.recentQuestions')}</p>
                  <div className="mt-3 grid gap-2">
                    {recentQuestions.map((item) => (
                      <button
                        key={item}
                        type="button"
                        onClick={() => setQuestion(item)}
                        disabled={loading || !tutorCanSubmit}
                        className={cn(
                          picoClasses.tertiaryButton,
                          'w-full justify-start rounded-[18px] px-3 py-2 text-start',
                        )}
                      >
                        {item}
                      </button>
                    ))}
                  </div>
                </div>
              ) : null}

              <div className={picoInset('mt-4 p-4')}>
                <div
                  data-testid="pico-openai-connect-panel"
                  aria-busy={openAIConnectionLoading || openAIConnectionSaving}
                >
                  <p className={picoClasses.label}>{t('rail.connection.label')}</p>
                  <div className="mt-3 rounded-[18px] border border-[color:var(--pico-border)] bg-[color:var(--pico-bg-surface)] p-4">
                    <p
                      role="status"
                      aria-live="polite"
                      className="text-sm leading-6 text-[color:var(--pico-text-secondary)]"
                      data-testid="pico-openai-connect-status"
                    >
                      {session.status !== 'authenticated'
                        ? t('rail.connection.authPrompt')
                        : !sessionCapabilities.tutorAccess
                          ? t('availability.readOnly')
                          : openAIConnectionLoading
                          ? t('rail.connection.checking')
                          : openAIConnection?.message
                            ? t('availability.providerDetail', { detail: openAIConnection.message })
                            : t('availability.providerUnavailable')}
                    </p>
                    {session.status === 'authenticated' && sessionCapabilities.tutorAccess ? (
                      <div className="mt-4 grid gap-3">
                        {openAIConnection?.status === 'connected' ? (
                          <div className={picoSoft('p-4')}>
                            <p className="font-medium text-[color:var(--pico-text)]">
                              {t('rail.connection.connectedAs', { maskedKey: openAIConnection.maskedKey ?? t('rail.connection.personalKey') })}
                            </p>
                            <p className="mt-2 text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                              {t('rail.connection.connectedBody')}
                            </p>
                            <div className="mt-3 flex flex-wrap gap-2">
                              <span className={picoClasses.chip}>{openAIConnection.model}</span>
                              <span className={picoClasses.chip}>{t('rail.connection.source', { value: openAIConnection.source })}</span>
                            </div>
                            <p className="mt-3 text-xs leading-6 text-[color:var(--pico-text-muted)]">
                              {t('rail.connection.validatedAt', { value: openAIConnection.validatedAt ?? t('hero.signal.notSet') })}
                            </p>
                            <button
                              type="button"
                              onClick={() => void disconnectOpenAI()}
                              disabled={openAIConnectionSaving}
                              className={cn(picoClasses.secondaryButton, 'mt-4 w-full sm:w-auto')}
                            >
                              {openAIConnectionSaving ? t('rail.connection.disconnecting') : t('rail.connection.disconnect')}
                            </button>
                          </div>
                        ) : openAIConnection?.canConnect ? (
                          <>
                            <label
                              htmlFor={OPENAI_KEY_ID}
                              className="block text-sm text-[color:var(--pico-text-secondary)]"
                            >
                              <span className={picoClasses.label}>{t('rail.connection.bringYourOwnKey')}</span>
                              <input
                                id={OPENAI_KEY_ID}
                                type="password"
                                value={openAIApiKey}
                                onChange={(event) => setOpenAIApiKey(event.target.value)}
                                aria-invalid={Boolean(openAIConnectionError)}
                                aria-describedby={
                                  openAIConnectionError ? OPENAI_CONNECTION_ERROR_ID : undefined
                                }
                                autoComplete="off"
                                placeholder={t('rail.connection.apiKeyPlaceholder')}
                                className="mt-3 w-full rounded-[18px] border border-[color:var(--pico-border)] bg-[color:var(--pico-bg-surface)] px-4 py-3 text-sm text-[color:var(--pico-text-secondary)] outline-none placeholder:text-[color:var(--pico-text-muted)] focus-visible:border-[color:var(--pico-border-hover)] focus-visible:ring-2 focus-visible:ring-[rgba(var(--pico-accent-rgb),0.35)]"
                              />
                            </label>
                            <button
                              type="button"
                              onClick={() => void connectOpenAI()}
                              disabled={openAIConnectionSaving}
                              className={cn(picoClasses.secondaryButton, 'w-full sm:w-auto')}
                            >
                              {openAIConnectionSaving ? t('rail.connection.connecting') : t('rail.connection.connect')}
                            </button>
                          </>
                        ) : null}
                        {openAIConnection?.status === 'platform' ? (
                          <p className="text-xs leading-6 text-[color:var(--pico-text-muted)]">
                            {openAIConnection.canConnect
                              ? t('rail.connection.platformHint')
                              : t('rail.connection.platformStarterHint')}
                          </p>
                        ) : null}
                      </div>
                    ) : null}
                    {openAIConnectionError ? (
                      <p
                        id={OPENAI_CONNECTION_ERROR_ID}
                        role="alert"
                        className="mt-3 text-sm leading-6 text-rose-200"
                      >
                        {t('errors.detail', { detail: openAIConnectionError })}
                      </p>
                    ) : null}
                  </div>
                </div>
              </div>

              <div className={picoInset('mt-4 p-4')}>
                <p className={picoClasses.label}>{t('rail.escalationRule.label')}</p>
                <p className="mt-3 text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                  {t('rail.escalationRule.body')}
                </p>
                <Link href={toHref('/support')} className={cn(picoClasses.secondaryButton, 'mt-4')}>
                  {t('rail.escalationRule.cta')}
                </Link>
              </div>
            </div>
          </div>
        </div>

        <aside className="space-y-6 xl:sticky xl:top-6 xl:self-start">
          <section
            aria-busy={loading}
            aria-labelledby="pico-tutor-answer-heading"
            className={picoPanel('p-5')}
          >
            <p id="pico-tutor-answer-heading" className={picoClasses.label}>{t('critique.label')}</p>
            <p className="sr-only" role="status" aria-live="polite" aria-atomic="true">
              {loading ? t('critique.loadingAnnouncement') : reply ? t('critique.readyAnnouncement') : ''}
            </p>
            {error ? (
              <div
                id={TUTOR_QUESTION_ERROR_ID}
                role="alert"
                className="mt-4 rounded-[24px] border border-rose-400/20 bg-rose-400/10 p-5 text-sm leading-6 text-rose-50"
              >
                <p>{t('errors.detail', { detail: error.message })}</p>
                {error.retryable ? (
                  <p className="mt-2 text-xs text-rose-100/80">
                    {t('critique.retryHint')}
                  </p>
                ) : null}
              </div>
            ) : null}

            {reply ? (
              <div className="mt-4 grid gap-4">
                <div className={picoEmber('p-5')}>
                  <div className="flex flex-wrap items-center gap-2">
                    <span className={picoClasses.chip}>{reply.title}</span>
                    <span className={picoClasses.chip}>{t('critique.chips.confidence', { value: reply.confidence })}</span>
                    <span className={picoClasses.chip}>{reply.intent}</span>
                    <span className={picoClasses.chip}>{reply.skillLevel}</span>
                    <span className={picoClasses.chip}>{t('rail.connection.source', { value: reply.generation.source })}</span>
                    <span className={picoClasses.chip}>{reply.generation.model}</span>
                    {reply.usedOfficialFallback ? <span className={picoClasses.chip}>{t('critique.chips.officialFallback')}</span> : null}
                    {reply.escalate ? <span className={picoClasses.chip}>{t('critique.chips.humanEscalationLikely')}</span> : null}
                  </div>
                  <div className={picoInset('mt-4 p-4')}>
                    <p className={picoClasses.label}>{t('critique.singleNextMove')}</p>
                    <p className="mt-3 font-[family:var(--font-site-display)] text-2xl leading-8 tracking-[-0.05em] text-[color:var(--pico-text)]">
                      {reply.structured.steps[0] ?? reply.title}
                    </p>
                  </div>
                  <p className="mt-3 break-all text-xs leading-6 text-[color:var(--pico-text-muted)]">
                    {t('critique.generationProof', { responseId: reply.generation.responseId, completedAt: reply.generation.completedAt })}
                  </p>
                  <div className="mt-4 grid gap-4">
                    <div>
                      <p className={picoClasses.label}>{t('critique.situation')}</p>
                      <p className="mt-2 text-sm leading-7 text-[color:var(--pico-text-secondary)]">{reply.structured.situation}</p>
                    </div>
                    <div>
                      <p className={picoClasses.label}>{t('critique.diagnosis')}</p>
                      <p className="mt-2 text-sm leading-7 text-[color:var(--pico-text-secondary)]">{reply.structured.diagnosis}</p>
                    </div>
                  </div>
                </div>

                <div className={picoSoft('p-5')}>
                  <p className="font-medium text-[color:var(--pico-text)]">{t('critique.steps')}</p>
                  <div className="mt-3 grid gap-3">
                    {reply.structured.steps.map((item, index) => (
                      <div key={item} className={picoInset('px-4 py-3 text-sm leading-6 text-[color:var(--pico-text-secondary)]')}>
                        <span className="me-3 text-[color:var(--pico-accent)]">{String(index + 1).padStart(2, '0')}</span>
                        {item}
                      </div>
                    ))}
                  </div>
                </div>

                {reply.structured.commands.length ? (
                  <div className={picoSoft('p-5')}>
                    <p className="font-medium text-[color:var(--pico-text)]">{t('critique.commands')}</p>
                    <div className="mt-3 grid gap-3">
                      {reply.structured.commands.map((command) => (
                        <div key={`${command.label}-${command.code}`} className={picoInset('p-4')}>
                          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[color:var(--pico-text-muted)]">
                            {command.label}
                          </p>
                          <pre className="mt-3 overflow-x-auto rounded-[18px] border border-[color:var(--pico-border)] bg-[color:var(--pico-bg-input)] p-4 text-xs leading-6 text-[color:var(--pico-text-secondary)]" dir="ltr">
                            <code>{command.code}</code>
                          </pre>
                          {command.note ? (
                            <p className="mt-3 text-sm leading-6 text-[color:var(--pico-text-secondary)]">{command.note}</p>
                          ) : null}
                        </div>
                      ))}
                    </div>
                  </div>
                ) : null}

                {reply.structured.verify.length ? (
                  <div className={picoSoft('p-5')}>
                    <p className="font-medium text-[color:var(--pico-text)]">{t('critique.reviewLine')}</p>
                    <div className="mt-3 grid gap-3">
                      {reply.structured.verify.map((item) => (
                        <div key={item} className={picoInset('px-4 py-3 text-sm leading-6 text-[color:var(--pico-text-secondary)]')}>
                          {item}
                        </div>
                      ))}
                    </div>
                  </div>
                ) : null}

                {reply.structured.ifThisFails.length ? (
                  <div className={picoSoft('p-5')}>
                    <p className="font-medium text-[color:var(--pico-text)]">{t('critique.fallbackRoute')}</p>
                    <div className="mt-3 grid gap-3">
                      {reply.structured.ifThisFails.map((item) => (
                        <div key={item} className={picoInset('px-4 py-3 text-sm leading-6 text-[color:var(--pico-text-secondary)]')}>
                          {item}
                        </div>
                      ))}
                    </div>
                  </div>
                ) : null}
              </div>
            ) : academyGuidance ? (
              <div className={picoSoft('mt-4 p-5')} data-testid="pico-tutor-academy-guidance">
                <div className="flex flex-wrap items-center gap-2">
                  <span className={picoClasses.chip}>{t('critique.academyGuidance')}</span>
                  <span className={picoClasses.chip}>{t('critique.readOnly')}</span>
                </div>
                <p className="mt-4 font-medium text-[color:var(--pico-text)]">
                  {academyGuidance.title}
                </p>
                <p className="mt-3 text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                  {academyGuidance.objective}
                </p>
                <div className={picoInset('mt-4 p-4')}>
                  <p className={picoClasses.label}>{t('critique.nextLessonStep')}</p>
                  <p className="mt-2 text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                    {academyGuidance.nextStep}
                  </p>
                </div>
                <div className={picoInset('mt-3 p-4')}>
                  <p className={picoClasses.label}>{t('critique.lessonValidation')}</p>
                  <p className="mt-2 text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                    {academyGuidance.validation}
                  </p>
                </div>
                <Link
                  href={toHref(academyGuidance.href)}
                  className={cn(picoClasses.secondaryButton, 'mt-4 w-full sm:w-auto')}
                >
                  {t('critique.openLesson')}
                </Link>
              </div>
            ) : (
              <div className={picoSoft('mt-4 p-5')}>
                <p className={picoClasses.body}>
                  {t('critique.academyGuidanceEmpty')}
                </p>
              </div>
            )}
          </section>

          {reply?.lessons.length ? (
            <section className={picoPanel('p-5')}>
              <p className={picoClasses.label}>{t('matches.label')}</p>
              <div className="mt-4 grid gap-3">
                {reply.lessons.map((lesson, index) => (
                  <Link
                    key={lesson.id}
                    href={resolveTutorHref(toHref, lesson.href)}
                    className={cn(
                      picoInset('flex items-center justify-between gap-4 px-4 py-3 text-sm text-[#f2e0cb]'),
                      index === 0 && 'border-[color:var(--pico-border-hover)] bg-[rgba(var(--pico-accent-rgb),0.08)]',
                    )}
                  >
                    <span>{lesson.title}</span>
                    <span className={picoClasses.chip}>{index === 0 ? t('matches.bestMatch') : t('matches.alternative')}</span>
                  </Link>
                ))}
              </div>
            </section>
          ) : null}

          {reply?.structured.sources.length ? (
            <section className={picoPanel('p-5')}>
              <p className={picoClasses.label}>{t('evidence.label')}</p>
              <div className="mt-4 grid gap-3">
                {reply.structured.sources.map((source) => (
                  <div
                    key={`${source.kind}-${source.sourcePath}-${source.href ?? source.title}`}
                    className={cn(picoInset('px-4 py-3'), 'text-sm text-[#f2e0cb]')}
                  >
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <span>{source.title}</span>
                      <span className="text-xs uppercase tracking-[0.18em] text-[color:var(--pico-text-muted)]">
                        {source.kind.replace('_', ' ')}
                      </span>
                    </div>
                    <p className="mt-2 text-xs leading-6 text-[#bfa58c]">{source.sourcePath}</p>
                    {source.excerpt ? (
                      <p className="mt-2 text-sm leading-6 text-[color:var(--pico-text-secondary)]">{source.excerpt}</p>
                    ) : null}
                    {source.href ? (
                      <Link
                        href={resolveTutorHref(toHref, source.href)}
                        className="mt-3 inline-flex text-sm font-medium text-[color:var(--pico-text)] underline decoration-[color:rgba(var(--pico-accent-rgb),0.38)] underline-offset-4"
                      >
                        {t('evidence.openSource')}
                      </Link>
                    ) : null}
                  </div>
                ))}
              </div>
            </section>
          ) : null}

          {reply?.structured.officialLinks.length ? (
            <section className={picoPanel('p-5')}>
              <p className={picoClasses.label}>{t('officialLinks.label')}</p>
              <div className="mt-4 grid gap-3">
                {reply.structured.officialLinks.map((doc) => (
                  <Link
                    key={`${doc.sourcePath}-${doc.href}`}
                    href={resolveTutorHref(toHref, doc.href)}
                    className={cn(
                      picoInset('flex items-center justify-between gap-4 px-4 py-3'),
                      'text-sm text-[#f2e0cb]',
                    )}
                  >
                    <span>{doc.label}</span>
                    <span className="text-xs uppercase tracking-[0.18em] text-[color:var(--pico-text-muted)]">
                      {doc.sourcePath}
                    </span>
                  </Link>
                ))}
              </div>
            </section>
          ) : null}

          <section className={picoPanel('p-5')}>
            <p className={picoClasses.label}>{t('exitRoute.label')}</p>
            <div className="mt-4 grid gap-3">
              <Link
                href={
                  selectedLesson
                    ? toHref(`/academy/${selectedLesson.slug}`)
                    : nextLesson
                      ? toHref(`/academy/${nextLesson.slug}`)
                      : toHref('/academy')
                }
                className={picoClasses.secondaryButton}
              >
                {selectedLesson
                  ? t('exitRoute.returnToBlockedLesson')
                  : nextLesson
                    ? t('shared.openLesson', { lessonTitle: nextLesson.title })
                    : t('exitRoute.returnToAcademy')}
              </Link>
              <Link href={toHref('/autopilot')} className={picoClasses.tertiaryButton}>
                {t('exitRoute.openAutopilot')}
              </Link>
              <Link href={toHref('/support')} className={picoClasses.tertiaryButton}>
                {t('exitRoute.openSupportLane')}
              </Link>
            </div>
            <div className={picoSoft('mt-4 p-4')}>
              <p className={picoClasses.body}>
                {t('exitRoute.body')}
              </p>
            </div>
          </section>

          {reply?.escalationReason ? (
            <section className={picoPanel('p-5')}>
              <p className={picoClasses.label}>{t('escalationNote.label')}</p>
              <div className="mt-4 rounded-[24px] border border-amber-400/20 bg-amber-400/10 p-5 text-sm text-amber-50">
                {reply.escalationReason}
                <div className="mt-4">
                  <Link href={toHref('/support')} className={picoClasses.primaryButton}>
                    {t('escalationNote.getHumanHelp')}
                  </Link>
                </div>
              </div>
            </section>
          ) : null}

          {reply?.structured.nextQuestion ? (
            <section className={picoPanel('p-5')}>
              <p className={picoClasses.label}>{t('nextQuestion.label')}</p>
              <div className={picoSoft('mt-4 p-4')}>
                <p className={picoClasses.body}>{reply.structured.nextQuestion}</p>
              </div>
            </section>
          ) : null}
        </aside>
      </section>
    </PicoShell>
  )
}
