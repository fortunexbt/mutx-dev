'use client'

import { FormEvent, useEffect, useMemo, useState } from 'react'
import Link from 'next/link'
import { usePathname, useSearchParams } from 'next/navigation'

import { PicoSessionBanner } from '@/components/pico/PicoSessionBanner'
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
import { PICO_GENERATED_CONTENT } from '@/lib/pico/generatedContent'
import { usePicoHref } from '@/lib/pico/navigation'
import { normalizeTutorReplyPayload, type PicoTutorReply } from '@/lib/pico/tutor'
import { cn } from '@/lib/utils'

const examplePrompts = PICO_GENERATED_CONTENT.tutor.examplePrompts

const questionProtocol = PICO_GENERATED_CONTENT.tutor.questionProtocol

const RECENT_QUESTIONS_KEY = 'pico.tutor.recent.v1'
const TUTOR_QUESTION_ID = 'pico-tutor-question'
const TUTOR_QUESTION_HELP_ID = 'pico-tutor-question-help'
const TUTOR_QUESTION_ERROR_ID = 'pico-tutor-question-error'
const OPENAI_KEY_ID = 'pico-tutor-openai-key'
const OPENAI_CONNECTION_ERROR_ID = 'pico-tutor-openai-error'

type TutorApiResponse = Partial<PicoTutorReply> & {
  detail?: string
  reply?: PicoTutorReply
}

type TutorOpenAIConnection = {
  provider: string
  status: 'connected' | 'platform' | 'disconnected' | 'error'
  source: 'user' | 'platform' | 'none'
  connected: boolean
  model: string
  maskedKey?: string | null
  connectedAt?: string | null
  validatedAt?: string | null
  message: string
}

type TutorOpenAIConnectionApiResponse = Partial<TutorOpenAIConnection> & {
  detail?: string
  error?: {
    message?: string
  }
}
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

function readApiErrorMessage(payload: TutorApiResponse | TutorOpenAIConnectionApiResponse | null | undefined) {
  if (typeof payload?.detail === 'string' && payload.detail) {
    return payload.detail
  }

  const errorValue = (payload as { error?: string | { message?: string } | null } | null | undefined)?.error
  if (typeof errorValue === 'string' && errorValue) {
    return errorValue
  }

  if (
    errorValue &&
    typeof errorValue === 'object' &&
    typeof errorValue.message === 'string' &&
    errorValue.message
  ) {
    return errorValue.message
  }

  return null
}
export function PicoTutorPageClient() {
  const pathname = usePathname()
  const session = usePicoSession()
  const setup = usePicoSetupState(session.status === 'authenticated')
  const { progress, derived, actions } = usePicoProgress(session.status === 'authenticated')
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
  const [error, setError] = useState<string | null>(null)
  const [reply, setReply] = useState<PicoTutorReply | null>(null)
  const [recentQuestions, setRecentQuestions] = useState<string[]>([])
  const [formReady, setFormReady] = useState(false)
  const [openAIConnection, setOpenAIConnection] = useState<TutorOpenAIConnection | null>(null)
  const [openAIConnectionLoading, setOpenAIConnectionLoading] = useState(false)
  const [openAIConnectionSaving, setOpenAIConnectionSaving] = useState(false)
  const [openAIConnectionError, setOpenAIConnectionError] = useState<string | null>(null)
  const [openAIApiKey, setOpenAIApiKey] = useState('')
  const availableLessons = useMemo(() => PICO_LESSONS, [])
  const selectedLesson = useMemo(
    () => availableLessons.find((lesson) => lesson.slug === lessonSlug) ?? null,
    [availableLessons, lessonSlug],
  )
  const lessonWorkspace = usePicoLessonWorkspace(selectedLesson?.slug ?? 'tutor', selectedLesson?.steps.length ?? 0, {
    progress,
    persistRemote: selectedLesson
      ? (lessonSlug, workspace) => actions.setLessonWorkspace(lessonSlug, workspace)
      : undefined,
  })
  const tutorMethod = [
    {
      label: '01 • Frame',
      title: 'Bring one blocked step',
      body: selectedLesson
        ? `Tie the question to ${selectedLesson.title}. Tutor works best when the lesson is attached.`
        : 'Name the exact step, command, or approval state that stopped you.',
    },
    {
      label: '02 • Evidence',
      title: 'Bring what actually happened',
      body: 'Paste the command, transcript, error, or runtime status so the answer can stay specific.',
    },
    {
      label: '03 • Exit',
      title: 'Leave with one move',
      body: 'A good tutor answer gives one next action, one verification line, and a clear handoff when setup needs help.',
    },
  ]
  const lessonReviewBoard = selectedLesson
    ? [
        {
          label: 'Lesson brief',
          value: selectedLesson.objective,
        },
        {
          label: 'Deliverable',
          value: selectedLesson.expectedResult,
        },
        {
          label: 'Critique line',
          value: selectedLesson.validation,
        },
      ]
    : []
  const promptChips = useMemo(
    () => getPicoTutorPromptChips(selectedLesson, examplePrompts),
    [selectedLesson],
  )
  const tutorSignal = reply
    ? 'answer ready'
    : loading
      ? 'reviewing blocker'
      : selectedLesson
        ? 'lesson attached'
        : 'awaiting blocker'
  const connectionSignal =
    session.status !== 'authenticated'
      ? 'local only'
      : openAIConnectionLoading
        ? 'checking'
        : openAIConnection?.status === 'connected'
          ? 'openai connected'
          : openAIConnection?.status === 'platform'
            ? 'platform access'
            : 'setup mode'
  const lessonSignal = selectedLesson
    ? `${lessonWorkspace.completedStepCount}/${selectedLesson.steps.length} steps`
    : 'attach lesson'
  const focusedStepLabel =
    selectedLesson && lessonWorkspace.workspace.activeStepIndex >= 0
      ? selectedLesson.steps[lessonWorkspace.workspace.activeStepIndex]?.title ?? 'not set'
      : 'not set'
  const tutorPacketPreview = [
    `Lesson ${selectedLesson?.title ?? 'none attached'}`,
    `State ${tutorSignal}`,
    `Focus ${focusedStepLabel}`,
    `Output one next step`,
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

  useEffect(() => {
    if (session.status !== 'authenticated') {
      setOpenAIConnection(null)
      setOpenAIConnectionLoading(false)
      setOpenAIConnectionError(null)
      return
    }

    let cancelled = false
    setOpenAIConnectionLoading(true)
    setOpenAIConnectionError(null)

    async function loadConnection() {
      try {
        const response = await fetch('/api/pico/tutor/openai', {
          credentials: 'include',
          cache: 'no-store',
        })
        const payload = (await response.json().catch(() => null)) as TutorOpenAIConnectionApiResponse | null

        if (cancelled) {
          return
        }

        if (!response.ok) {
          throw new Error(readApiErrorMessage(payload) || 'Failed to load OpenAI connection')
        }

        setOpenAIConnection(payload as TutorOpenAIConnection)
      } catch (loadError) {
        if (!cancelled) {
          setOpenAIConnection(null)
          setOpenAIConnectionError(
            loadError instanceof Error ? loadError.message : 'Failed to load OpenAI connection',
          )
        }
      } finally {
        if (!cancelled) {
          setOpenAIConnectionLoading(false)
        }
      }
    }

    void loadConnection()

    return () => {
      cancelled = true
    }
  }, [session.status])
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!question.trim()) return

    setLoading(true)
    setError(null)
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
      })
      const payload = (await response.json()) as TutorApiResponse
      if (!response.ok) {
        throw new Error(readApiErrorMessage(payload) || 'Tutor request failed')
      }

      const normalizedReply = normalizeTutorReplyPayload(payload)
      if (!normalizedReply) {
        throw new Error('Tutor response came back malformed')
      }

      const normalizedQuestion = question.trim()
      const nextRecentQuestions = [
        normalizedQuestion,
        ...recentQuestions.filter((item) => item !== normalizedQuestion),
      ].slice(0, 5)

      setReply(normalizedReply)
      setRecentQuestions(nextRecentQuestions)
      writeRecentQuestions(nextRecentQuestions)
      actions.recordTutorQuestion()
    } catch (submitError) {
      setReply(null)
      setError(submitError instanceof Error ? submitError.message : 'Tutor request failed')
    } finally {
      setLoading(false)
    }
  }

  async function connectOpenAI() {
    if (!openAIApiKey.trim()) {
      setOpenAIConnectionError('Paste an OpenAI API key first')
      return
    }

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
      })
      const payload = (await response.json().catch(() => null)) as TutorOpenAIConnectionApiResponse | null

      if (!response.ok) {
        throw new Error(readApiErrorMessage(payload) || 'Failed to connect the OpenAI key')
      }

      setOpenAIConnection(payload as TutorOpenAIConnection)
      setOpenAIApiKey('')
    } catch (connectError) {
      setOpenAIConnectionError(
        connectError instanceof Error ? connectError.message : 'Failed to connect the OpenAI key',
      )
    } finally {
      setOpenAIConnectionSaving(false)
    }
  }

  async function disconnectOpenAI() {
    setOpenAIConnectionSaving(true)
    setOpenAIConnectionError(null)
    try {
      const response = await fetch('/api/pico/tutor/openai', {
        method: 'DELETE',
        credentials: 'include',
      })
      const payload = (await response.json().catch(() => null)) as TutorOpenAIConnectionApiResponse | null

      if (!response.ok) {
        throw new Error(readApiErrorMessage(payload) || 'Failed to disconnect the OpenAI key')
      }

      setOpenAIConnection(payload as TutorOpenAIConnection)
    } catch (disconnectError) {
      setOpenAIConnectionError(
        disconnectError instanceof Error
          ? disconnectError.message
          : 'Failed to disconnect the OpenAI key',
      )
    } finally {
      setOpenAIConnectionSaving(false)
    }
  }

  return (
    <PicoShell
      eyebrow="Grounded tutor"
      title="Ask for the exact next step"
      description="Bring one concrete blocker, get one next step back, and return to the lesson, runtime, or support path."
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
            className="pointer-events-none absolute -left-10 top-8 h-40 w-40 rounded-full bg-[rgba(var(--pico-accent-rgb),0.12)] blur-3xl"
          />
          <div
            aria-hidden="true"
            className="pointer-events-none absolute bottom-0 right-0 h-48 w-48 rounded-full bg-[rgba(var(--pico-accent-rgb),0.1)] blur-3xl"
          />
          <div className="relative grid gap-5 xl:grid-cols-[minmax(0,1fr),18rem]">
            <div className="grid gap-5">
              <div className="flex flex-wrap items-center gap-2">
                <span className={picoClasses.chip}>Tutor status</span>
                <span className="inline-flex rounded-full border border-[color:var(--pico-border)] bg-[rgba(255,255,255,0.03)] px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-[color:var(--pico-text-secondary)]">
                  {tutorSignal}
                </span>
              </div>
              <h2 className="font-[family:var(--font-site-display)] text-[clamp(1.9rem,4vw,2.9rem)] leading-[0.94] tracking-[-0.06em] text-[color:var(--pico-text)]">
                Attach the blocked lesson and narrow the answer to one move.
              </h2>
              <p className="max-w-2xl text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                Route the question through the lesson, command, or runtime step that failed. Tutor should send you back into action.
              </p>

              <div className="grid gap-3 sm:grid-cols-3">
                <div className={picoSoft('p-4')}>
                  <p className={picoClasses.label}>Lesson</p>
                  <p className="mt-2 font-[family:var(--font-site-display)] text-3xl tracking-[-0.05em] text-[color:var(--pico-text)]">
                    {lessonSignal}
                  </p>
                  <p className="mt-2 text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                    {selectedLesson ? selectedLesson.title : 'Connect the blocked lesson'}
                  </p>
                </div>

                <div className={picoSoft('p-4')}>
                  <p className={picoClasses.label}>Reply state</p>
                  <p className="mt-2 font-[family:var(--font-site-display)] text-3xl tracking-[-0.05em] text-[color:var(--pico-text)]">
                    {tutorSignal}
                  </p>
                  <p className="mt-2 text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                    {reply ? 'ready to act on' : 'waiting for a precise blocker'}
                  </p>
                </div>

                <div className={picoSoft('p-4')}>
                  <p className={picoClasses.label}>Connection</p>
                  <p className="mt-2 font-[family:var(--font-site-display)] text-3xl tracking-[-0.05em] text-[color:var(--pico-text)]">
                    {connectionSignal}
                  </p>
                  <p className="mt-2 text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                    {session.status === 'authenticated' ? 'hosted context available' : 'hosted context missing'}
                  </p>
                </div>
              </div>

              <div className={picoInset('grid gap-3 p-4 sm:grid-cols-[auto,minmax(0,1fr)] sm:items-center')}>
                <div className="flex h-14 w-14 items-center justify-center rounded-[20px] border border-[rgba(var(--pico-accent-rgb),0.24)] bg-[linear-gradient(180deg,rgba(var(--pico-accent-rgb),0.18),rgba(7,13,8,0.5))] shadow-[0_18px_40px_rgba(var(--pico-accent-rgb),0.12)]">
                  <span className="h-3 w-3 rounded-full bg-[color:var(--pico-accent-bright)] shadow-[0_0_18px_rgba(var(--pico-accent-rgb),0.5)]" />
                </div>
                <div className="min-w-0">
                  <p className={picoClasses.label}>Focused step</p>
                  <p className="mt-2 font-[family:var(--font-site-display)] text-2xl tracking-[-0.05em] text-[color:var(--pico-text)]">
                    {focusedStepLabel}
                  </p>
                  <p className="mt-2 text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                    If the answer does not make this step clearer, leave Tutor and use the better path.
                  </p>
                </div>
              </div>
            </div>

            <div className={picoInset('grid gap-4 overflow-hidden border-[color:rgba(var(--pico-accent-rgb),0.24)] bg-[radial-gradient(circle_at_50%_20%,rgba(var(--pico-accent-rgb),0.16),rgba(6,11,7,0.94)_54%,rgba(3,5,3,0.98)_100%)] p-4')}>
              <div className={picoSoft('p-4')}>
                <p className={picoClasses.label}>Question packet</p>
                <pre className="mt-3 whitespace-pre-wrap text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                  <code>{tutorPacketPreview}</code>
                </pre>
              </div>
              <div className={picoSoft('p-4')}>
                <p className={picoClasses.label}>Recent pressure</p>
                <p className="mt-3 text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                  {recentQuestions[0]
                    ? recentQuestions[0]
                    : 'No recent question saved yet. Bring the first blocked step instead of a broad description of the whole project.'}
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
            {selectedLesson ? 'Back to lesson' : 'Open academy'}
          </Link>
          <Link href={toHref('/support')} className={picoClasses.primaryButton}>
            Escalate to human help
          </Link>
        </div>
      }
    >
      <PicoSessionBanner session={session} nextPath={pathname} />
      <PicoSurfaceCompass
        title="Tutor should return you to setup"
        body="Use Tutor for one blocked command, file path, provider setting, or validation step. Return to the lesson when the answer is enough, inspect Autopilot for runtime state, and get human help when keys, hosting, or implementation decisions are involved."
        status={
          reply
            ? 'answer ready'
            : selectedLesson
              ? 'lesson context attached'
              : 'awaiting blocker'
        }
        aside="A good tutor answer ends in one move. If it does not, return to the lesson, runtime, or support."
        items={[
          {
            href: selectedLesson
              ? toHref(`/academy/${selectedLesson.slug}`)
              : derived.nextLesson
                ? toHref(`/academy/${derived.nextLesson.slug}`)
                : toHref('/academy'),
            label: selectedLesson
              ? 'Return to blocked lesson'
              : derived.nextLesson
                ? `Open ${derived.nextLesson.title}`
                : 'Return to academy',
            caption: 'Go back here when the tutor answer unblocks the lesson step.',
            note: 'Resume lesson',
            tone: 'primary',
          },
          {
            href: toHref('/autopilot'),
            label: 'Inspect runtime state',
            caption: 'Open this when the problem has shifted from knowable lesson logic to runtime state.',
            note: 'Runtime',
            tone: 'soft',
          },
          {
            href: toHref('/support'),
            label: 'Get human help',
            caption: 'Use this for API keys, hosting, integrations, or custom implementation.',
            note: 'Support',
          },
        ]}
      />

      <section className={picoPanel('p-6 sm:p-7')} data-testid="pico-tutor-crit-desk">
        <div className="grid gap-6 lg:grid-cols-[minmax(0,1.08fr),20rem]">
          <div>
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div>
                <p className={picoClasses.label}>Tutor method</p>
                <h2 className="mt-3 font-[family:var(--font-site-display)] text-4xl tracking-[-0.06em] text-[color:var(--pico-text)]">
                  Keep each question narrow
                </h2>
              </div>
              <span className={picoClasses.chip}>frame • evidence • exit</span>
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
              <p className={picoClasses.label}>Tutor rule</p>
              <p className="mt-3 text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                This is not general chat. Use it to turn one setup blocker into one next move.
              </p>
            </div>
            <div className={picoInset('p-5')}>
              <p className={picoClasses.label}>Attached lesson</p>
              <p className="mt-3 text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                {selectedLesson
                  ? `${selectedLesson.title} is attached, so the tutor can answer against the real lesson brief instead of guessing.`
                  : 'No lesson is attached yet. Connect the blocked lesson if you want the answer tied to the setup path.'}
              </p>
            </div>
          </div>
        </div>
      </section>

      <section className="grid gap-6 xl:grid-cols-[minmax(0,1.08fr),22rem]">
        <div className={picoPanel('overflow-hidden p-0')}>
          <div className="grid gap-0 border-b border-[color:var(--pico-border)] lg:grid-cols-[minmax(0,1fr),18rem]">
            <form onSubmit={submit} aria-busy={loading} className="p-6 sm:p-7">
              <p className={picoClasses.label}>Tutor desk</p>
              <div className="mt-3 flex items-center gap-4">
                <span
                  aria-hidden="true"
                  className="inline-flex h-12 w-12 shrink-0 items-center justify-center border border-[color:var(--pico-accent)] font-[family:var(--font-mono)] text-xs font-semibold tracking-[0.14em] text-[color:var(--pico-accent)]"
                >
                  03
                </span>
                <h2 className="font-[family:var(--font-site-display)] text-4xl tracking-[-0.06em] text-[color:var(--pico-text)] sm:text-5xl">
                  Bring one blocker to the desk
                </h2>
              </div>
              <p className="mt-4 max-w-3xl text-sm leading-7 text-[color:var(--pico-text-secondary)] sm:text-base">
                Ask only when the lesson path is blocked. The answer should send you back into action, not into another loop of reading.
              </p>
              <p className="mt-3 text-xs uppercase tracking-[0.18em] text-[color:var(--pico-text-muted)]">
                {session.status === 'authenticated'
                  ? 'Hosted identity and runtime context attached'
                  : 'Read-only tutor mode. Hosted session context is missing until you sign in.'}
              </p>

              {selectedLesson ? (
                <div className={picoEmber('mt-6 p-5')}>
                  <p className="font-medium text-[color:var(--pico-text)]">Where you are</p>
                  <p className="mt-2 text-sm leading-6">
                    You are asking about {selectedLesson.title}. Keep the question tied to the step that is actually blocked.
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
                      <p className="text-sm text-[color:var(--pico-text-muted)]">Lesson steps</p>
                      <p className="mt-1 text-lg font-medium text-[color:var(--pico-text)]">
                        {lessonWorkspace.completedStepCount}/{selectedLesson.steps.length}
                      </p>
                    </div>
                    <div className={picoInset('p-4')}>
                      <p className="text-sm text-[color:var(--pico-text-muted)]">Focused step</p>
                      <p className="mt-1 text-lg font-medium text-[color:var(--pico-text)]">
                        {lessonWorkspace.workspace.activeStepIndex >= 0
                          ? selectedLesson.steps[lessonWorkspace.workspace.activeStepIndex]?.title ?? 'not set'
                          : 'not set'}
                      </p>
                    </div>
                  </div>
                  <Link
                    href={toHref(`/academy/${selectedLesson.slug}`)}
                    className="mt-4 inline-flex text-sm font-medium text-[color:var(--pico-text)] underline decoration-[color:rgba(var(--pico-accent-rgb),0.38)] underline-offset-4"
                  >
                    Back to lesson
                  </Link>
                </div>
              ) : null}

              <div className={picoInset('mt-6 grid gap-4 p-5')}>
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <p className={picoClasses.label}>Question packet</p>
                    <p
                      id={TUTOR_QUESTION_HELP_ID}
                      className="mt-2 text-sm leading-6 text-[color:var(--pico-text-secondary)]"
                    >
                      Bring just enough context for a useful answer: page, failure, and expected result.
                    </p>
                  </div>
                  <span className={picoClasses.chip}>page • failure • expected result</span>
                </div>

                <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
                  <div className={picoSoft('p-4')}>
                    <p className="text-sm text-[color:var(--pico-text-muted)]">Current track</p>
                    <p className="mt-1 text-lg font-medium text-[color:var(--pico-text)]">
                      {progress.selectedTrack ?? 'not chosen yet'}
                    </p>
                  </div>
                  <div className={picoSoft('p-4')}>
                    <p className="text-sm text-[color:var(--pico-text-muted)]">Next lesson</p>
                    <p className="mt-1 text-lg font-medium text-[color:var(--pico-text)]">
                      {derived.nextLesson?.title ?? 'none'}
                    </p>
                  </div>
                  <div className={picoSoft('p-4')}>
                    <p className="text-sm text-[color:var(--pico-text-muted)]">Hosted onboarding step</p>
                    <p className="mt-1 text-lg font-medium text-[color:var(--pico-text)]">
                      {setup.onboarding?.current_step ?? 'session required'}
                    </p>
                  </div>
                  <div className={picoSoft('p-4')}>
                    <p className="text-sm text-[color:var(--pico-text-muted)]">Runtime status</p>
                    <p className="mt-1 text-lg font-medium text-[color:var(--pico-text)]">
                      {setup.runtime?.status ?? 'not synced'}
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
                Describe your setup blocker
              </label>
              <textarea
                id={TUTOR_QUESTION_ID}
                value={question}
                onChange={(event) => setQuestion(event.target.value)}
                disabled={!formReady || loading}
                aria-invalid={Boolean(error)}
                aria-describedby={
                  error
                    ? `${TUTOR_QUESTION_HELP_ID} ${TUTOR_QUESTION_ERROR_ID}`
                    : TUTOR_QUESTION_HELP_ID
                }
                placeholder="Describe the blocker, the exact step, and what you expected to happen."
                className="mt-6 min-h-[240px] w-full rounded-[28px] border border-[color:var(--pico-border)] bg-[color:var(--pico-bg-surface)] px-5 py-5 text-sm leading-7 text-[color:var(--pico-text-secondary)] outline-none placeholder:text-[color:var(--pico-text-muted)]"
              />

              <div className="mt-5 grid gap-4 lg:grid-cols-[minmax(0,1fr),auto] lg:items-end">
                <label className="block text-sm text-[color:var(--pico-text-secondary)]">
                  <span className={picoClasses.label}>Blocked lesson</span>
                  <select
                    value={lessonSlug}
                    onChange={(event) => setLessonSlug(event.target.value)}
                    disabled={!formReady || loading}
                    className="mt-3 w-full rounded-[22px] border border-[color:var(--pico-border)] bg-[color:var(--pico-bg-surface)] px-4 py-3 text-sm text-[color:var(--pico-text-secondary)] outline-none"
                  >
                    <option value="">No lesson selected</option>
                    {availableLessons.map((lesson) => (
                      <option key={lesson.slug} value={lesson.slug}>
                        {lesson.title}
                      </option>
                    ))}
                  </select>
                </label>
                <button type="submit" disabled={!formReady || loading} className={picoClasses.primaryButton}>
                  {loading ? 'Finding the next step...' : 'Get next step'}
                </button>
              </div>

              {promptChips.length ? (
                <div className="mt-5 grid gap-2 sm:flex sm:flex-wrap">
                  {promptChips.map((prompt) => (
                    <button
                      key={prompt}
                      type="button"
                      onClick={() => setQuestion(prompt)}
                      disabled={!formReady || loading}
                      className={picoClasses.tertiaryButton}
                    >
                      {prompt}
                    </button>
                  ))}
                </div>
              ) : null}
            </form>

            <div className="border-t border-[color:var(--pico-border)] bg-[color:var(--pico-bg-surface)] p-6 lg:border-l lg:border-t-0">
              <p className={picoClasses.label}>Tutor rail</p>
              <div className="mt-4 grid gap-3">
                <div className={picoSoft('p-4')}>
                  <p className="text-sm text-[color:var(--pico-text-muted)]">Questions asked</p>
                  <p className="mt-1 text-2xl font-semibold text-[color:var(--pico-text)]">{progress.tutorQuestions}</p>
                </div>
                <div className={picoSoft('p-4')}>
                  <p className="text-sm text-[color:var(--pico-text-muted)]">Live answer state</p>
                  <p className="mt-1 text-lg font-medium text-[color:var(--pico-text)]">
                    {reply ? reply.confidence : loading ? 'thinking' : 'waiting'}
                  </p>
                </div>
              </div>

              {recentQuestions.length > 0 ? (
                <div className={picoInset('mt-4 p-4')}>
                  <p className={picoClasses.label}>Recent questions</p>
                  <div className="mt-3 grid gap-2">
                    {recentQuestions.map((item) => (
                      <button
                        key={item}
                        type="button"
                        onClick={() => setQuestion(item)}
                        className={cn(
                          picoClasses.tertiaryButton,
                          'w-full justify-start rounded-[18px] px-3 py-2 text-left',
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
                  <p className={picoClasses.label}>OpenAI connection</p>
                  <div className="mt-3 rounded-[18px] border border-[color:var(--pico-border)] bg-[color:var(--pico-bg-surface)] p-4">
                    <p
                      role="status"
                      aria-live="polite"
                      className="text-sm leading-6 text-[color:var(--pico-text-secondary)]"
                      data-testid="pico-openai-connect-status"
                    >
                      {session.status !== 'authenticated'
                        ? 'Sign in to attach your own OpenAI key. Tutor still works in read-only mode without a personal connection.'
                        : openAIConnectionLoading
                          ? 'Checking whether your OpenAI key is already connected.'
                          : openAIConnection?.message ??
                            'Connect an OpenAI key if you want your own live Tutor quota and model access.'}
                    </p>
                    {session.status === 'authenticated' ? (
                      <div className="mt-4 grid gap-3">
                        {openAIConnection?.status === 'connected' ? (
                          <div className={picoSoft('p-4')}>
                            <p className="font-medium text-[color:var(--pico-text)]">
                              Connected {openAIConnection.maskedKey ? `as ${openAIConnection.maskedKey}` : 'key'}
                            </p>
                            <p className="mt-2 text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                              Live Tutor answers now prefer your own OpenAI access before any platform fallback.
                            </p>
                            <div className="mt-3 flex flex-wrap gap-2">
                              <span className={picoClasses.chip}>{openAIConnection.model}</span>
                              <span className={picoClasses.chip}>source: {openAIConnection.source}</span>
                            </div>
                            <button
                              type="button"
                              onClick={() => void disconnectOpenAI()}
                              disabled={openAIConnectionSaving}
                              className={cn(picoClasses.secondaryButton, 'mt-4')}
                            >
                              {openAIConnectionSaving ? 'Disconnecting...' : 'Disconnect OpenAI'}
                            </button>
                          </div>
                        ) : (
                          <>
                            <label
                              htmlFor={OPENAI_KEY_ID}
                              className="block text-sm text-[color:var(--pico-text-secondary)]"
                            >
                              <span className={picoClasses.label}>Bring your own OpenAI key</span>
                              <input
                                id={OPENAI_KEY_ID}
                                type="password"
                                value={openAIApiKey}
                                onChange={(event) => setOpenAIApiKey(event.target.value)}
                                aria-invalid={Boolean(openAIConnectionError)}
                                aria-describedby={
                                  openAIConnectionError ? OPENAI_CONNECTION_ERROR_ID : undefined
                                }
                                placeholder="sk-proj-..."
                                className="mt-3 w-full rounded-[18px] border border-[color:var(--pico-border)] bg-[color:var(--pico-bg-surface)] px-4 py-3 text-sm text-[color:var(--pico-text-secondary)] outline-none placeholder:text-[color:var(--pico-text-muted)]"
                              />
                            </label>
                            <button
                              type="button"
                              onClick={() => void connectOpenAI()}
                              disabled={openAIConnectionSaving}
                              className={picoClasses.secondaryButton}
                            >
                              {openAIConnectionSaving ? 'Connecting OpenAI...' : 'Connect OpenAI'}
                            </button>
                          </>
                        )}
                        {openAIConnection?.status === 'platform' ? (
                          <p className="text-xs leading-6 text-[color:var(--pico-text-muted)]">
                            Platform access is already available. Connecting your own key simply overrides the Tutor model budget and ownership path for this account.
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
                        {openAIConnectionError}
                      </p>
                    ) : null}
                  </div>
                </div>
              </div>

              <div className={picoInset('mt-4 p-4')}>
                <p className={picoClasses.label}>Support rule</p>
                <p className="mt-3 text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                  If the answer still does not give you one concrete move, stop looping and open support with the lesson context attached.
                </p>
                <Link href={toHref('/support')} className={cn(picoClasses.secondaryButton, 'mt-4')}>
                  Get human help
                </Link>
              </div>
            </div>
          </div>
        </div>

        <aside className="space-y-6 xl:sticky xl:top-6 xl:self-start">
          <section aria-busy={loading} className={picoPanel('p-5')}>
            <p className={picoClasses.label}>Tutor answer</p>
            <p className="sr-only" role="status" aria-live="polite" aria-atomic="true">
              {loading ? 'Tutor is finding the next step.' : reply ? 'Tutor answer ready.' : ''}
            </p>
            {error ? (
              <div
                id={TUTOR_QUESTION_ERROR_ID}
                role="alert"
                className="mt-4 rounded-[24px] border border-rose-400/20 bg-rose-400/10 p-5 text-sm leading-6 text-rose-50"
              >
                {error}
              </div>
            ) : null}

            {reply ? (
              <div className="mt-4 grid gap-4">
                <div className={picoEmber('p-5')}>
                  <div className="flex flex-wrap items-center gap-2">
                    <span className={picoClasses.chip}>{reply.title}</span>
                    <span className={picoClasses.chip}>{reply.confidence} confidence</span>
                    <span className={picoClasses.chip}>{reply.intent}</span>
                    <span className={picoClasses.chip}>{reply.skillLevel}</span>
                    {reply.usedOfficialFallback ? <span className={picoClasses.chip}>official fallback</span> : null}
                    {reply.escalate ? <span className={picoClasses.chip}>human escalation likely</span> : null}
                  </div>
                  <div className={picoInset('mt-4 p-4')}>
                    <p className={picoClasses.label}>Single next move</p>
                    <p className="mt-3 font-[family:var(--font-site-display)] text-2xl leading-8 tracking-[-0.05em] text-[color:var(--pico-text)]">
                      {reply.structured.steps[0] ?? reply.title}
                    </p>
                  </div>
                  <div className="mt-4 grid gap-4">
                    <div>
                      <p className={picoClasses.label}>Situation</p>
                      <p className="mt-2 text-sm leading-7 text-[color:var(--pico-text-secondary)]">{reply.structured.situation}</p>
                    </div>
                    <div>
                      <p className={picoClasses.label}>Diagnosis</p>
                      <p className="mt-2 text-sm leading-7 text-[color:var(--pico-text-secondary)]">{reply.structured.diagnosis}</p>
                    </div>
                  </div>
                </div>

                <div className={picoSoft('p-5')}>
                  <p className="font-medium text-[color:var(--pico-text)]">Steps</p>
                  <div className="mt-3 grid gap-3">
                    {reply.structured.steps.map((item, index) => (
                      <div key={item} className={picoInset('px-4 py-3 text-sm leading-6 text-[color:var(--pico-text-secondary)]')}>
                        <span className="mr-3 text-[color:var(--pico-accent)]">{String(index + 1).padStart(2, '0')}</span>
                        {item}
                      </div>
                    ))}
                  </div>
                </div>

                {reply.structured.commands.length ? (
                  <div className={picoSoft('p-5')}>
                    <p className="font-medium text-[color:var(--pico-text)]">Commands</p>
                    <div className="mt-3 grid gap-3">
                      {reply.structured.commands.map((command) => (
                        <div key={`${command.label}-${command.code}`} className={picoInset('p-4')}>
                          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[color:var(--pico-text-muted)]">
                            {command.label}
                          </p>
                          <pre className="mt-3 overflow-x-auto rounded-[18px] border border-[color:var(--pico-border)] bg-[color:var(--pico-bg-input)] p-4 text-xs leading-6 text-[color:var(--pico-text-secondary)]">
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
                    <p className="font-medium text-[color:var(--pico-text)]">Review check</p>
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
                    <p className="font-medium text-[color:var(--pico-text)]">Fallback path</p>
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
            ) : (
              <div className={picoSoft('mt-4 p-5')}>
                <p className={picoClasses.body}>
                  Ask one blocker, not the whole project. Pico Tutor uses lessons, the builder pack, and official docs when the question depends on current setup details.
                </p>
                <p className="mt-4 text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                  How this works: state the failing step, the expected result, and the exact failure. The answer should give you a concrete move, one verification step, and a clean escalation path if the evidence is still thin.
                </p>
              </div>
            )}
          </section>

          {reply?.lessons.length ? (
            <section className={picoPanel('p-5')}>
              <p className={picoClasses.label}>Lesson matches</p>
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
                    <span className={picoClasses.chip}>{index === 0 ? 'best match' : 'alt'}</span>
                  </Link>
                ))}
              </div>
            </section>
          ) : null}

          {reply?.structured.sources.length ? (
            <section className={picoPanel('p-5')}>
              <p className={picoClasses.label}>Answer sources</p>
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
                        Open source
                      </Link>
                    ) : null}
                  </div>
                ))}
              </div>
            </section>
          ) : null}

          {reply?.structured.officialLinks.length ? (
            <section className={picoPanel('p-5')}>
              <p className={picoClasses.label}>Official links</p>
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
            <p className={picoClasses.label}>Exit path</p>
            <div className="mt-4 grid gap-3">
              <Link
                href={
                  selectedLesson
                    ? toHref(`/academy/${selectedLesson.slug}`)
                    : derived.nextLesson
                      ? toHref(`/academy/${derived.nextLesson.slug}`)
                      : toHref('/academy')
                }
                className={picoClasses.secondaryButton}
              >
                {selectedLesson
                  ? 'Return to blocked lesson'
                  : derived.nextLesson
                    ? `Open ${derived.nextLesson.title}`
                    : 'Return to academy'}
              </Link>
              <Link href={toHref('/autopilot')} className={picoClasses.tertiaryButton}>
                Open Autopilot
              </Link>
              <Link href={toHref('/support')} className={picoClasses.tertiaryButton}>
                Get human help
              </Link>
            </div>
            <div className={picoSoft('mt-4 p-4')}>
              <p className={picoClasses.body}>
                Tutor should end with a next step. Return to the lesson if the path is clear, open Autopilot if runtime state is the blocker, and get human help when setup needs a person.
              </p>
            </div>
          </section>

          {reply?.escalationReason ? (
            <section className={picoPanel('p-5')}>
              <p className={picoClasses.label}>Escalation note</p>
              <div className="mt-4 rounded-[24px] border border-amber-400/20 bg-amber-400/10 p-5 text-sm text-amber-50">
                {reply.escalationReason}
                <div className="mt-4">
                  <Link href={toHref('/support')} className={picoClasses.primaryButton}>
                    Get human help
                  </Link>
                </div>
              </div>
            </section>
          ) : null}

          {reply?.structured.nextQuestion ? (
            <section className={picoPanel('p-5')}>
              <p className={picoClasses.label}>If the answer is still fuzzy</p>
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
