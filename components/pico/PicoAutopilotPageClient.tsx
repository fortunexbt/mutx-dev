'use client'

import Link from 'next/link'
import { useLocale, useTranslations } from 'next-intl'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { usePathname } from 'next/navigation'

import { PicoSessionBanner } from '@/components/pico/PicoSessionBanner'
import { PicoShell } from '@/components/pico/PicoShell'
import { PicoSignalDiagram } from '@/components/pico/PicoSignalDiagram'
import { PicoSurfaceCompass } from '@/components/pico/PicoSurfaceCompass'
import { picoClasses, picoEmber, picoInset, picoPanel, picoSoft } from '@/components/pico/picoTheme'
import { usePicoLessonWorkspace } from '@/components/pico/usePicoLessonWorkspace'
import { usePicoProgress } from '@/components/pico/usePicoProgress'
import { usePicoSession } from '@/components/pico/usePicoSession'
import { localizePicoLesson } from '@/lib/pico/content'
import { usePicoHref } from '@/lib/pico/navigation'
import {
  AUTOPILOT_APPROVAL_STATUSES,
  appendApprovalPage,
  describeApprovalMutationFailure,
  hasNextApprovalPage,
  parseApprovalPage,
  parseEligibleApprovalReviewers,
  parseRuntimeSnapshot,
  presentRuntimeSnapshot,
  type AutopilotApprovalPage,
  type AutopilotApprovalStatus,
  type AutopilotRuntimeSnapshot,
  type EligibleApprovalReviewer,
} from '@/lib/pico/autopilot'
import { cn } from '@/lib/utils'
import {
  analyzeAutopilotIntegration,
  buildAutopilotTimeline,
  describeRunDetail,
  explainAlertImpact,
  explainApprovalImpact,
  formatPercent,
  formatRelativeTime,
  formatTimestamp,
  getAlertsEmptyState,
  getApprovalsEmptyState,
  getRunsEmptyState,
  getRunSeverity,
  getUsageEmptyState,
  humanizeRunStatus,
  type AutopilotTranslator,
  type AutopilotAlertSummary,
  type AutopilotApprovalSummary,
  type AutopilotBudgetSummary,
  type AutopilotEmptyState,
  type AutopilotRunSummary,
  type AutopilotRunTrace,
  type AutopilotTimelineItem,
  type AutopilotUsageBreakdown,
} from '@/components/pico/picoAutopilot'

type LoadState = 'loading' | 'ready' | 'partial' | 'offline'

type ApprovalPages = Record<AutopilotApprovalStatus, AutopilotApprovalPage | null>

type SignalResult = {
  key: string
  label: string
  response: Response | null
  payload: unknown
  fetchedAt: string
  networkError: string | null
}

const APPROVAL_PAGE_LIMIT = 50

function createEmptyApprovalPages(): ApprovalPages {
  return {
    PENDING: null,
    APPROVED: null,
    REJECTED: null,
    EXPIRED: null,
  }
}

function isAbortError(error: unknown) {
  return Boolean(error && typeof error === 'object' && 'name' in error && error.name === 'AbortError')
}

export async function fetchSignal(
  key: string,
  label: string,
  url: string,
  signal: AbortSignal,
): Promise<SignalResult> {
  try {
    const response = await fetch(url, {
      credentials: 'include',
      cache: 'no-store',
      signal,
    })

    return {
      key,
      label,
      response,
      payload: await readJsonSafely(response),
      fetchedAt: new Date().toISOString(),
      networkError: null,
    }
  } catch (error) {
    if (isAbortError(error)) throw error

    return {
      key,
      label,
      response: null,
      payload: null,
      fetchedAt: new Date().toISOString(),
      networkError: error instanceof Error ? error.message : 'Network request failed',
    }
  }
}

function describeSignalFailure(result: SignalResult, t: AutopilotTranslator) {
  const status = result.response?.status
  if (status === 401) return t('signalFailure.authRequired', { label: result.label, status })
  if (status === 403) return t('signalFailure.permissionDenied', { label: result.label, status })
  if (status === 404) return t('signalFailure.notFound', { label: result.label, status })
  if (status === 409) return t('signalFailure.conflict', { label: result.label, status })
  if (status && status >= 500) return t('signalFailure.controlPlaneUnavailable', { label: result.label, status })
  if (status) return t('signalFailure.requestFailed', { label: result.label, status })
  return t('signalFailure.network', {
    label: result.label,
    detail: result.networkError ?? t('signalFailure.requestUnavailable'),
  })
}

async function readJsonSafely(response: Response) {
  return response.json().catch(() => null)
}

export function isUnauthorizedPayload(payload: unknown) {
  if (!payload || typeof payload !== 'object') {
    return false
  }

  const candidate = payload as {
    status?: unknown
    error?: unknown
  }

  if (candidate.status === 'error' && candidate.error && typeof candidate.error === 'object') {
    const error = candidate.error as { code?: unknown }
    return error.code === 'UNAUTHORIZED'
  }

  return false
}

function severityClasses(severity: AutopilotTimelineItem['severity']) {
  switch (severity) {
    case 'critical':
      return 'border-rose-400/20 bg-rose-400/10 text-rose-50'
    case 'warn':
      return 'border-amber-400/20 bg-amber-400/10 text-amber-50'
    case 'good':
      return 'border-[color:var(--pico-border-hover)] bg-[linear-gradient(180deg,rgba(var(--pico-accent-rgb),0.16),rgba(8,15,9,0.2))] text-[color:var(--pico-text)]'
    default:
      return 'border-[color:var(--pico-border)] bg-[color:var(--pico-bg-surface)] text-[color:var(--pico-text-secondary)]'
  }
}

function sectionClasses() {
  return picoPanel('p-6')
}

function StatCard({ label, value, hint }: { label: string; value: string; hint: string }) {
  return (
    <div className={picoClasses.metric}>
      <p className={picoClasses.label}>{label}</p>
      <p className={picoClasses.metricValue}>{value}</p>
      <p className="mt-3 text-sm leading-6 text-[color:var(--pico-text-secondary)]">{hint}</p>
    </div>
  )
}

function TimelineItemCard({
  item,
  locale,
  t,
}: {
  item: AutopilotTimelineItem
  locale: string
  t: AutopilotTranslator
}) {
  return (
    <div className={`rounded-[24px] border p-5 ${severityClasses(item.severity)}`}>
      <div className="flex flex-wrap items-center justify-between gap-3 text-xs uppercase tracking-[0.18em]">
        <span>{item.sourceLabel}</span>
        <span>{formatTimestamp(item.occurredAt, locale, t('shared.time.unknown'))} • {formatRelativeTime(item.occurredAt, new Date(), locale, t('shared.time.unknownRelative'))}</span>
      </div>
      <h3 className="mt-3 font-[family:var(--font-site-display)] text-2xl tracking-[-0.05em] text-[color:var(--pico-text)]">{item.title}</h3>
      <p className="mt-2 text-sm leading-6">{item.detail}</p>
      <p className="mt-3 text-sm leading-6 text-[color:var(--pico-text-secondary)]">{t('shared.label.whyItMatters', { impact: item.impact })}</p>
      <Link href={item.href} className={cn(picoClasses.link, 'mt-4 inline-flex')}>
        {t('shared.action.jumpToDetail')}
      </Link>
    </div>
  )
}

function EmptyStatePanel({ state }: { state: AutopilotEmptyState }) {
  return (
    <div className={picoSoft('p-5')}>
      <p className="font-medium text-[color:var(--pico-text)]">{state.title}</p>
      <p className="mt-2">{state.body}</p>
      <Link
        href={state.nextStep.href}
        className={cn(picoClasses.secondaryButton, 'mt-4')}
      >
        {state.nextStep.label}
      </Link>
    </div>
  )
}

export function PicoAutopilotPageClient() {
  const pathname = usePathname()
  const locale = useLocale()
  const t = useTranslations('pico.autopilotPage')
  const contentT = useTranslations('pico.content')
  const session = usePicoSession()
  const { progress, derived, actions, syncState } = usePicoProgress(
    session.status === 'authenticated',
  )
  const toHref = usePicoHref()
  const [runs, setRuns] = useState<AutopilotRunSummary[]>([])
  const [tracesByRunId, setTracesByRunId] = useState<Record<string, AutopilotRunTrace[]>>({})
  const [budget, setBudget] = useState<AutopilotBudgetSummary | null>(null)
  const [usage, setUsage] = useState<AutopilotUsageBreakdown | null>(null)
  const [alerts, setAlerts] = useState<AutopilotAlertSummary[]>([])
  const [approvalPages, setApprovalPages] = useState<ApprovalPages>(createEmptyApprovalPages)
  const [eligibleReviewers, setEligibleReviewers] = useState<EligibleApprovalReviewer[]>([])
  const [runtimeSnapshot, setRuntimeSnapshot] = useState<AutopilotRuntimeSnapshot | null>(null)
  const [runtimeFetchedAt, setRuntimeFetchedAt] = useState<string | null>(null)
  const [lastRefreshAt, setLastRefreshAt] = useState<string | null>(null)
  const [loadState, setLoadState] = useState<LoadState>('loading')
  const [authRequired, setAuthRequired] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [approvalNotice, setApprovalNotice] = useState<string | null>(null)
  const [unavailableSignals, setUnavailableSignals] = useState<string[]>([])
  const [unavailableTraceRunIds, setUnavailableTraceRunIds] = useState<string[]>([])
  const [thresholdDraft, setThresholdDraft] = useState(progress.autopilot.costThresholdPercent)
  const [resolvingApprovalId, setResolvingApprovalId] = useState<string | null>(null)
  const [approvalActionErrors, setApprovalActionErrors] = useState<Record<string, string>>({})
  const [creatingApproval, setCreatingApproval] = useState(false)
  const [visiblePendingCount, setVisiblePendingCount] = useState(3)
  const [visibleDecisionCount, setVisibleDecisionCount] = useState(3)
  const [loadingApprovalPage, setLoadingApprovalPage] = useState<'pending' | 'decisions' | null>(null)
  const loadAbortRef = useRef<AbortController | null>(null)
  const approvalPageAbortRef = useRef<AbortController | null>(null)
  const approvalNoticeRef = useRef<HTMLDivElement | null>(null)
  const [approvalDraft, setApprovalDraft] = useState({
    agentId: '',
    sessionId: '',
    actionType: 'OUTBOUND_SEND',
    summary: t('composer.summaryDefault'),
    reviewerId: '',
  })
  const nextLesson = useMemo(
    () => derived.nextLesson ? localizePicoLesson(derived.nextLesson, contentT) : null,
    [contentT, derived.nextLesson],
  )
  const controlProtocol = ([0, 1, 2] as const).map((index) => ({
    id: t(`controlProtocol.steps.${index}.id`),
    title: t(`controlProtocol.steps.${index}.title`),
    body: t(`controlProtocol.steps.${index}.body`),
    href: index === 0 ? '#recent-runs' : index === 1 ? '#budget-section' : '#approvals-section',
    action: t(`controlProtocol.steps.${index}.action`),
  }))
  const autopilotVisuals = ([0, 1, 2] as const).map((index) => ({
    index: t(`visuals.${index}.index`),
    label: t(`visuals.${index}.label`),
    title: t(`visuals.${index}.title`),
    caption: t(`visuals.${index}.caption`),
  }))
  const storyRailClass =
    'mt-6 grid grid-flow-col auto-cols-[minmax(16rem,82vw)] gap-4 overflow-x-auto pb-2 snap-x snap-mandatory md:grid-flow-row md:auto-cols-auto md:overflow-visible xl:grid-cols-3'

  const approvals = useMemo(
    () =>
      AUTOPILOT_APPROVAL_STATUSES.flatMap((status) => approvalPages[status]?.items ?? [])
        .sort((left, right) => {
          const leftTime = new Date(left.resolved_at ?? left.created_at).getTime()
          const rightTime = new Date(right.resolved_at ?? right.created_at).getTime()
          return rightTime - leftTime
        }) as AutopilotApprovalSummary[],
    [approvalPages],
  )

  const pendingApprovals = useMemo(
    () => (approvalPages.PENDING?.items ?? []) as AutopilotApprovalSummary[],
    [approvalPages.PENDING],
  )

  const resolvedApprovals = useMemo(
    () => approvals.filter((approval) => approval.status !== 'PENDING'),
    [approvals],
  )

  const pendingApprovalTotal = approvalPages.PENDING?.total ?? null
  const decisionTotal = useMemo(() => {
    const decisionPages = [approvalPages.APPROVED, approvalPages.REJECTED, approvalPages.EXPIRED]
    if (decisionPages.some((page) => page === null)) return null
    return decisionPages.reduce((total, page) => total + (page?.total ?? 0), 0)
  }, [approvalPages.APPROVED, approvalPages.EXPIRED, approvalPages.REJECTED])

  const latestRun = runs[0] ?? null

  useEffect(() => {
    setApprovalDraft((current) => ({
      ...current,
      agentId: current.agentId || latestRun?.agent_id || '',
      sessionId: current.sessionId || latestRun?.id || '',
    }))
  }, [latestRun?.agent_id, latestRun?.id])

  const load = useCallback(async () => {
    approvalPageAbortRef.current?.abort()
    loadAbortRef.current?.abort()
    const controller = new AbortController()
    loadAbortRef.current = controller
    setLoadState('loading')
    setError(null)

    try {
      const results = await Promise.all([
        fetchSignal('runs', t('signals.runs'), '/api/dashboard/runs?limit=6', controller.signal),
        fetchSignal('budget', t('signals.budget'), '/api/dashboard/budgets', controller.signal),
        fetchSignal('usage', t('signals.usage'), '/api/dashboard/budgets/usage?period_start=30d', controller.signal),
        fetchSignal('alerts', t('signals.alerts'), '/api/dashboard/monitoring/alerts?limit=8', controller.signal),
        fetchSignal('runtime', t('signals.runtime'), '/api/pico/runtime/openclaw', controller.signal),
        fetchSignal('reviewers', t('composer.sectionLabel'), '/api/pico/approvals/reviewers', controller.signal),
        ...AUTOPILOT_APPROVAL_STATUSES.map((status) =>
          fetchSignal(
            `approval:${status}`,
            t('signals.approvals', { status: t(`shared.statusLabels.${status}`) }),
            `/api/pico/approvals?status=${status}&skip=0&limit=${APPROVAL_PAGE_LIMIT}`,
            controller.signal,
          ),
        ),
      ])

      if (loadAbortRef.current !== controller) return

      const resultByKey = new Map(results.map((result) => [result.key, result]))
      const failures: string[] = []
      const failedSignalKeys = new Set<string>()
      let successfulSignals = 0
      const recordFailure = (result: SignalResult, reason?: string) => {
        failedSignalKeys.add(result.key)
        failures.push(reason ? t('signalFailure.detail', { label: result.label, detail: reason }) : describeSignalFailure(result, t))
      }

      const runsResult = resultByKey.get('runs')!
      let nextRuns: AutopilotRunSummary[] | null = null
      if (runsResult.response?.ok) {
        const items = (runsResult.payload as { items?: unknown } | null)?.items
        if (Array.isArray(items)) {
          nextRuns = items as AutopilotRunSummary[]
          setRuns(nextRuns)
          successfulSignals += 1
        } else {
          recordFailure(runsResult, t('signalFailure.invalidResponse'))
        }
      } else {
        recordFailure(runsResult)
      }

      const budgetResult = resultByKey.get('budget')!
      if (budgetResult.response?.ok && budgetResult.payload && typeof budgetResult.payload === 'object') {
        setBudget(budgetResult.payload as AutopilotBudgetSummary)
        successfulSignals += 1
      } else if (budgetResult.response?.ok) {
        recordFailure(budgetResult, t('signalFailure.invalidResponse'))
      } else {
        recordFailure(budgetResult)
      }

      const usageResult = resultByKey.get('usage')!
      if (usageResult.response?.ok && usageResult.payload && typeof usageResult.payload === 'object') {
        setUsage(usageResult.payload as AutopilotUsageBreakdown)
        successfulSignals += 1
      } else if (usageResult.response?.ok) {
        recordFailure(usageResult, t('signalFailure.invalidResponse'))
      } else {
        recordFailure(usageResult)
      }

      const alertsResult = resultByKey.get('alerts')!
      if (alertsResult.response?.ok) {
        const items = (alertsResult.payload as { items?: unknown } | null)?.items
        if (Array.isArray(items)) {
          setAlerts(items as AutopilotAlertSummary[])
          successfulSignals += 1
        } else {
          recordFailure(alertsResult, t('signalFailure.invalidResponse'))
        }
      } else {
        recordFailure(alertsResult)
      }

      const runtimeResult = resultByKey.get('runtime')!
      if (runtimeResult.response?.ok) {
        const parsedRuntime = parseRuntimeSnapshot(runtimeResult.payload)
        if (parsedRuntime) {
          setRuntimeSnapshot(parsedRuntime)
          setRuntimeFetchedAt(runtimeResult.fetchedAt)
          successfulSignals += 1
        } else {
          setRuntimeSnapshot(null)
          setRuntimeFetchedAt(runtimeResult.fetchedAt)
          recordFailure(runtimeResult, t('signalFailure.invalidResponse'))
        }
      } else {
        setRuntimeSnapshot(null)
        setRuntimeFetchedAt(runtimeResult.fetchedAt)
        recordFailure(runtimeResult)
      }

      const reviewersResult = resultByKey.get('reviewers')!
      if (reviewersResult.response?.ok) {
        const reviewers = parseEligibleApprovalReviewers(reviewersResult.payload)
        if (reviewers) {
          setEligibleReviewers(reviewers)
          setApprovalDraft((current) => ({
            ...current,
            reviewerId: reviewers.some((reviewer) => reviewer.id === current.reviewerId)
              ? current.reviewerId
              : reviewers[0]?.id ?? '',
          }))
          successfulSignals += 1
        } else {
          setEligibleReviewers([])
          recordFailure(reviewersResult, t('signalFailure.invalidResponse'))
        }
      } else {
        setEligibleReviewers([])
        recordFailure(reviewersResult)
      }

      const nextApprovalPages: Partial<ApprovalPages> = {}
      for (const status of AUTOPILOT_APPROVAL_STATUSES) {
        const result = resultByKey.get(`approval:${status}`)!
        if (result.response?.ok) {
          const page = parseApprovalPage(result.payload, status)
          if (page) {
            nextApprovalPages[status] = page
            successfulSignals += 1
          } else {
            recordFailure(result, t('signalFailure.invalidPaginatedResponse'))
          }
        } else {
          recordFailure(result)
        }
      }

      if (Object.keys(nextApprovalPages).length > 0) {
        setApprovalPages((current) => ({ ...current, ...nextApprovalPages }))
        setVisiblePendingCount(3)
        setVisibleDecisionCount(3)
      }

      const authFailures = results.filter((result) => result.response?.status === 401).length
      setAuthRequired(authFailures > 0 && successfulSignals === 0)

      if ((nextRuns?.length ?? 0) > 0 || ((alertsResult.payload as { items?: unknown[] } | null)?.items?.length ?? 0) > 0) {
        actions.unlockMilestone('first_monitoring_event_seen')
      }

      if (nextRuns) {
        const traceResults = await Promise.all(
          nextRuns.slice(0, 4).map(async (run) => {
            try {
              const response = await fetch(`/api/dashboard/runs/${encodeURIComponent(run.id)}/traces?limit=6`, {
                credentials: 'include',
                cache: 'no-store',
                signal: controller.signal,
              })

              if (!response.ok) {
                return { runId: run.id, traces: null, status: response.status }
              }

              const payload = (await readJsonSafely(response)) as { items?: AutopilotRunTrace[] } | null
              return {
                runId: run.id,
                traces: Array.isArray(payload?.items) ? payload.items : null,
                status: response.status,
              }
            } catch (traceError) {
              if (isAbortError(traceError)) throw traceError
              return { runId: run.id, traces: null, status: null }
            }
          }),
        )

        if (loadAbortRef.current !== controller) return

        const successfulTracePairs = traceResults
          .filter((result): result is { runId: string; traces: AutopilotRunTrace[]; status: number } => result.traces !== null)
          .map((result) => [result.runId, result.traces] as const)
        setTracesByRunId(Object.fromEntries(successfulTracePairs))

        const failedTraceRunIds = traceResults
          .filter((result) => result.traces === null)
          .map((result) => result.runId)
        setUnavailableTraceRunIds(failedTraceRunIds)
        const failedTraceCount = failedTraceRunIds.length
        if (failedTraceCount > 0) {
          failures.push(t('signalFailure.traceRequestsUnavailable', { count: failedTraceCount }))
        }
      }

      const refreshTimestamp = new Date().toISOString()
      setLastRefreshAt(refreshTimestamp)
      setUnavailableSignals(Array.from(failedSignalKeys))
      if (failures.length > 0) {
        setError(t('shared.error.partialSignals', { detail: failures.join('; ') }))
      }
      setLoadState(
        failures.length === 0
          ? 'ready'
          : successfulSignals > 0
            ? 'partial'
            : authFailures > 0
              ? 'offline'
              : 'partial',
      )
    } catch (loadError) {
      if (isAbortError(loadError)) return
      if (loadAbortRef.current !== controller) return
      setLoadState('partial')
      setRuntimeSnapshot(null)
      setRuntimeFetchedAt(new Date().toISOString())
      setUnavailableSignals([
        'runs',
        'budget',
        'usage',
        'alerts',
        'runtime',
        'reviewers',
        ...AUTOPILOT_APPROVAL_STATUSES.map((status) => `approval:${status}`),
      ])
      setError(
        t('shared.error.loadLiveData', {
          detail: loadError instanceof Error ? loadError.message : t('shared.error.loadLiveDataFallback'),
        }),
      )
    }
  }, [actions, t])

  useEffect(() => {
    loadAbortRef.current?.abort()
    approvalPageAbortRef.current?.abort()

    if (session.status === 'loading') {
      setLoadState('loading')
      setAuthRequired(false)
      setError(null)
      return
    }

    if (session.status !== 'authenticated') {
      setRuns([])
      setTracesByRunId({})
      setBudget(null)
      setUsage(null)
      setAlerts([])
      setApprovalPages(createEmptyApprovalPages())
      setEligibleReviewers([])
      setApprovalActionErrors({})
      setRuntimeSnapshot(null)
      setRuntimeFetchedAt(null)
      setLastRefreshAt(null)
      setUnavailableSignals([])
      setUnavailableTraceRunIds([])
      setLoadState('offline')
      setAuthRequired(session.status === 'unauthenticated')
      setError(session.status === 'error' ? session.error : null)
      return
    }

    setAuthRequired(false)
    void load()
    return () => {
      loadAbortRef.current?.abort()
      approvalPageAbortRef.current?.abort()
    }
  }, [load, session.error, session.status])

  useEffect(() => {
    if (progress.platform.activeSurface !== 'autopilot') {
      actions.setPlatform({ activeSurface: 'autopilot' })
    }
  }, [actions, progress.platform.activeSurface])

  useEffect(() => {
    setThresholdDraft(progress.autopilot.costThresholdPercent)
  }, [progress.autopilot.costThresholdPercent])

  const thresholdBreached = useMemo(() => {
    if (!budget || unavailableSignals.includes('budget')) return false
    return budget.usage_percentage >= progress.autopilot.costThresholdPercent
  }, [budget, progress.autopilot.costThresholdPercent, unavailableSignals])

  const thresholdValidationError = useMemo(() => {
    if (!Number.isFinite(thresholdDraft)) {
      return t('shared.validation.thresholdRange')
    }

    if (thresholdDraft < 1 || thresholdDraft > 100) {
      return t('shared.validation.thresholdRange')
    }

    return null
  }, [t, thresholdDraft])

  useEffect(() => {
    if (thresholdBreached && !progress.autopilot.lastThresholdBreachAt) {
      actions.setAutopilot({ lastThresholdBreachAt: new Date().toISOString() })
    }
  }, [actions, progress.autopilot.lastThresholdBreachAt, thresholdBreached])

  const failedRuns = useMemo(
    () => runs.filter((run) => ['FAILED', 'ERROR', 'CANCELLED'].includes(run.status.toUpperCase())),
    [runs],
  )

  const timeline = useMemo(
    () =>
      buildAutopilotTimeline({
        runs,
        alerts,
        approvals: approvals.slice(0, 8),
        budget,
        thresholdPercent: progress.autopilot.costThresholdPercent,
        tracesByRunId,
        t,
      }).slice(0, 10),
    [alerts, approvals, budget, progress.autopilot.costThresholdPercent, runs, t, tracesByRunId],
  )
  const visibleTimeline = timeline.slice(0, 4)
  const visibleRuns = runs.slice(0, 3)
  const visibleAlerts = alerts.slice(0, 4)
  const visiblePendingApprovals = pendingApprovals.slice(0, visiblePendingCount)
  const visibleResolvedApprovals = resolvedApprovals.slice(0, visibleDecisionCount)

  const integrationStatus = useMemo(
    () =>
      analyzeAutopilotIntegration({
        runs,
        alerts,
        approvals,
        budget,
        usage,
        approvalGatePreferenceEnabled: progress.autopilot.approvalGateEnabled,
      }),
    [alerts, approvals, budget, progress.autopilot.approvalGateEnabled, runs, usage],
  )

  const runEmptyState = useMemo(
    () =>
      getRunsEmptyState(integrationStatus, {
        label: nextLesson ? t('shared.action.openLesson', { lessonTitle: nextLesson.title }) : t('emptyStates.runs.openAcademy'),
        href: nextLesson ? toHref(`/academy/${nextLesson.slug}`) : toHref('/academy'),
      }, t),
    [integrationStatus, nextLesson, t, toHref],
  )

  const alertsEmptyState = useMemo(
    () =>
      getAlertsEmptyState(integrationStatus, {
        label: integrationStatus.hasRuns ? t('emptyStates.alerts.inspectRecentRuns') : t('emptyStates.alerts.getFirstRunLive'),
        href: integrationStatus.hasRuns
          ? '#recent-runs'
          : nextLesson
            ? toHref(`/academy/${nextLesson.slug}`)
            : toHref('/academy'),
      }, t),
    [integrationStatus, nextLesson, t, toHref],
  )

  const usageEmptyState = useMemo(
    () =>
      getUsageEmptyState(integrationStatus, {
        label: integrationStatus.hasBudget ? t('emptyStates.usage.triggerRealUsage') : t('emptyStates.usage.setupBudgetVisibility'),
        href: integrationStatus.hasBudget
          ? '#recent-runs'
          : nextLesson
            ? toHref(`/academy/${nextLesson.slug}`)
            : toHref('/academy'),
      }, t),
    [integrationStatus, nextLesson, t, toHref],
  )

  const approvalsEmptyState = useMemo(
    () =>
      getApprovalsEmptyState(integrationStatus, {
        label: t('emptyStates.approvals.runGatedAction'),
        href: toHref('/academy/add-an-approval-gate'),
      }, t),
    [integrationStatus, t, toHref],
  )

  const loadStateLabel = useMemo(() => {
    if (authRequired) {
      return t('shared.loadState.authRequired')
    }

    switch (loadState) {
      case 'loading':
        return t('shared.loadState.loading')
      case 'partial':
        return t('shared.loadState.partial')
      case 'offline':
        return t('shared.loadState.offline')
      default:
        return t('shared.loadState.ready')
    }
  }, [authRequired, lastRefreshAt, loadState, t])

  async function fetchNextApprovalPage(status: AutopilotApprovalStatus) {
    const currentPage = approvalPages[status]
    if (!currentPage || !hasNextApprovalPage(currentPage)) return false

    approvalPageAbortRef.current?.abort()
    const controller = new AbortController()
    approvalPageAbortRef.current = controller
    const nextSkip = currentPage.skip + currentPage.items.length

    try {
      const result = await fetchSignal(
        `approval:${status}`,
        `${status.toLowerCase()} approvals`,
        `/api/pico/approvals?status=${status}&skip=${nextSkip}&limit=${currentPage.limit}`,
        controller.signal,
      )

      if (approvalPageAbortRef.current !== controller) return false
      if (!result.response?.ok) {
        if (result.response?.status === 401) setAuthRequired(true)
        setUnavailableSignals((current) => Array.from(new Set([...current, result.key])))
        setError(t('pagination.signalUnavailable', { detail: describeSignalFailure(result, t) }))
        return false
      }

      const nextPage = parseApprovalPage(result.payload, status)
      const mergedPage = nextPage ? appendApprovalPage(currentPage, nextPage) : null
      if (!mergedPage) {
        setError(t('pagination.queueChanged'))
        await load()
        return false
      }

      setApprovalPages((current) => ({ ...current, [status]: mergedPage }))
      setUnavailableSignals((current) => current.filter((key) => key !== result.key))
      setError(null)
      return true
    } catch (paginationError) {
      if (isAbortError(paginationError)) return false
      setError(t('pagination.loadFailed'))
      return false
    }
  }

  async function showMorePendingApprovals() {
    if (pendingApprovals.length > visiblePendingCount) {
      setVisiblePendingCount((current) => current + 3)
      return
    }

    setLoadingApprovalPage('pending')
    const loaded = await fetchNextApprovalPage('PENDING')
    if (loaded) setVisiblePendingCount((current) => current + 3)
    setLoadingApprovalPage(null)
  }

  async function showMoreDecisions() {
    if (resolvedApprovals.length > visibleDecisionCount) {
      setVisibleDecisionCount((current) => current + 3)
      return
    }

    const nextStatus = (['APPROVED', 'REJECTED', 'EXPIRED'] as const).find((status) => {
      const page = approvalPages[status]
      return page ? hasNextApprovalPage(page) : false
    })
    if (!nextStatus) return

    setLoadingApprovalPage('decisions')
    const loaded = await fetchNextApprovalPage(nextStatus)
    if (loaded) setVisibleDecisionCount((current) => current + 3)
    setLoadingApprovalPage(null)
  }

  function saveThreshold() {
    if (thresholdValidationError) {
      return
    }

    const nextThreshold = Math.round(thresholdDraft)
    setThresholdDraft(nextThreshold)
    actions.setAutopilot({
      costThresholdPercent: nextThreshold,
      alertChannel: progress.autopilot.alertChannel,
    })
    actions.unlockMilestone('first_alert_configured')
  }

  async function resolveApproval(id: string, action: 'approve' | 'reject') {
    setResolvingApprovalId(id)
    setApprovalActionErrors((current) => {
      const next = { ...current }
      delete next[id]
      return next
    })
    setApprovalNotice(null)

    try {
      const response = await fetch(`/api/pico/approvals/${encodeURIComponent(id)}/${action}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        credentials: 'include',
        body: JSON.stringify({ comment: `Resolved from Pico ${action} flow` }),
      })

      const payload = await readJsonSafely(response)
      if (!response.ok) {
        const failure = describeApprovalMutationFailure(response.status, payload, action)
        if (failure.requiresAuth) {
          setAuthRequired(true)
          setLoadState('offline')
        }

        setApprovalActionErrors((current) => ({
          ...current,
          [id]: t('shared.error.resolveRequest', {
            action: t(`approvals.card.${action}`),
            detail: failure.message,
          }),
        }))
        return
      }

      await load()
      const resolvedStatus = action === 'approve' ? 'approved' : 'rejected'
      setApprovalNotice(
        t('approvals.resolvedNotice', {
          approvalId: id.slice(0, 8),
          status: t(`shared.timeline.approvalStatus.${resolvedStatus}`),
        }),
      )
      setApprovalActionErrors((current) => {
        const next = { ...current }
        delete next[id]
        return next
      })
      requestAnimationFrame(() => approvalNoticeRef.current?.focus())
    } catch (requestError) {
      if (isAbortError(requestError)) return
      setApprovalActionErrors((current) => ({
        ...current,
        [id]: t('shared.error.resolveRequest', {
          action: t(`approvals.card.${action}`),
          detail: requestError instanceof Error ? requestError.message : t('approvals.requestFailed'),
        }),
      }))
    } finally {
      setResolvingApprovalId(null)
    }
  }

  async function createApprovalRequest() {
    if (
      !approvalDraft.agentId.trim() ||
      !approvalDraft.sessionId.trim() ||
      !approvalDraft.actionType.trim() ||
      !approvalDraft.reviewerId
    ) {
      setError(t('shared.error.createApprovalRequiredFields'))
      return
    }

    setCreatingApproval(true)
    setError(null)
    setApprovalNotice(null)

    try {
      const response = await fetch('/api/pico/approvals', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        credentials: 'include',
        body: JSON.stringify({
          agent_id: approvalDraft.agentId.trim(),
          session_id: approvalDraft.sessionId.trim(),
          action_type: approvalDraft.actionType.trim(),
          reviewer_id: approvalDraft.reviewerId,
          payload: {
            summary: approvalDraft.summary.trim(),
            source: 'pico-autopilot',
          },
        }),
      })

      const payload = await readJsonSafely(response)
      if (!response.ok) {
        const failure = describeApprovalMutationFailure(response.status, payload, 'create')
        if (failure.requiresAuth) {
          setAuthRequired(true)
          setLoadState('offline')
        }

        setError(t('shared.error.createApproval', { detail: failure.message }))
        return
      }

      await load()
      setApprovalNotice(t('approvals.createdNotice'))
      requestAnimationFrame(() => approvalNoticeRef.current?.focus())
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? t('shared.error.createApproval', { detail: requestError.message })
          : t('shared.error.createApproval', { detail: t('approvals.requestFailed') }),
      )
    } finally {
      setCreatingApproval(false)
    }
  }

  const signalValue = (key: string, value: string) =>
    authRequired || unavailableSignals.includes(key) || (!lastRefreshAt && loadState === 'loading')
      ? '--'
      : value
  const initialLoadPending = loadState === 'loading' && !lastRefreshAt
  const liveHint = (readyHint: string, offlineHint: string) => (authRequired ? offlineHint : readyHint)
  const runtimePresentation = useMemo(
    () =>
      presentRuntimeSnapshot(
        runtimeSnapshot,
        runtimeFetchedAt ?? lastRefreshAt ?? new Date().toISOString(),
      ),
    [lastRefreshAt, runtimeFetchedAt, runtimeSnapshot],
  )
  const runtimeDisplayLabel = initialLoadPending
    ? t('runtimePresentation.loadingLabel')
    : t(`runtimePresentation.${runtimePresentation.state}.label`)
  const runtimeDisplayDetail = initialLoadPending
    ? t('runtimePresentation.loadingDetail')
    : t(`runtimePresentation.${runtimePresentation.state}.detail`, {
        status: runtimePresentation.reportedStatus ?? t('shared.time.unknown'),
      })
  const approvalUnavailableStatuses = AUTOPILOT_APPROVAL_STATUSES.filter(
    (status) => unavailableSignals.includes(`approval:${status}`) || approvalPages[status] === null,
  )
  const approvalMutationsAvailable =
    !authRequired &&
    loadState !== 'loading' &&
    !unavailableSignals.includes('approval:PENDING') &&
    approvalPages.PENDING !== null
  const primaryAutopilotHref = authRequired || !latestRun
    ? nextLesson
      ? toHref(`/academy/${nextLesson.slug}`)
      : toHref('/academy')
    : '#recent-runs'
  const primaryAutopilotLabel = authRequired || !latestRun
    ? nextLesson
      ? t('hero.primaryAction.finishLesson', { lessonTitle: nextLesson.title })
      : t('hero.primaryAction.goBackToAcademy')
    : t('hero.primaryAction.inspectRun', { runId: latestRun.id.slice(0, 8) })
  const latestRunTimestamp = latestRun?.completed_at ?? latestRun?.started_at ?? latestRun?.created_at ?? null
  const latestRunTraces = latestRun ? tracesByRunId[latestRun.id] ?? [] : []
  const reviewFlow = [
    {
      label: t('operatorDoctrine.step.read.label'),
      title: t('operatorDoctrine.step.read.title'),
      body: authRequired
        ? t('operatorDoctrine.step.read.authRequired')
        : initialLoadPending
          ? t('operatorDoctrine.step.read.loading')
          : unavailableSignals.includes('runs')
            ? t('operatorDoctrine.step.read.unavailable')
        : latestRun
          ? t('operatorDoctrine.step.read.withRun', { runId: latestRun.id.slice(0, 8), detail: describeRunDetail(latestRun, latestRunTraces, t) })
          : t('operatorDoctrine.step.read.noRun'),
    },
    {
      label: t('operatorDoctrine.step.judge.label'),
      title: t('operatorDoctrine.step.judge.title'),
      body: authRequired
        ? t('operatorDoctrine.step.judge.authRequired')
        : initialLoadPending
          ? t('operatorDoctrine.step.judge.loading')
          : unavailableSignals.includes('budget')
            ? t('operatorDoctrine.step.judge.unavailable')
        : budget
          ? t('operatorDoctrine.step.judge.withBudget', { usage: formatPercent(budget.usage_percentage), threshold: formatPercent(progress.autopilot.costThresholdPercent) })
          : t('operatorDoctrine.step.judge.noBudget'),
    },
    {
      label: t('operatorDoctrine.step.intervene.label'),
      title: t('operatorDoctrine.step.intervene.title'),
      body:
        pendingApprovalTotal === null || unavailableSignals.includes('approval:PENDING')
          ? t('operatorDoctrine.step.intervene.unavailable')
          : pendingApprovalTotal > 0
            ? t('operatorDoctrine.step.intervene.pending', {
                count: pendingApprovalTotal,
                pluralSuffix: pendingApprovalTotal === 1 ? '' : 's',
              })
          : `${t('gateStatus.configuredLocally')}: ${
              progress.autopilot.approvalGateEnabled
                ? t('gateStatus.yes')
                : t('gateStatus.no')
            }`,
    },
  ]
  const recoveryWorkspace = usePicoLessonWorkspace(nextLesson?.slug ?? 'autopilot', nextLesson?.steps.length ?? 0, {
    progress,
    persistRemote: nextLesson
      ? (lessonSlug, workspace) => actions.setLessonWorkspace(lessonSlug, workspace)
      : undefined,
  })
  const recoveryFocusedStep =
    nextLesson && recoveryWorkspace.workspace.activeStepIndex >= 0
      ? nextLesson.steps[recoveryWorkspace.workspace.activeStepIndex]?.title ?? t('hero.packet.recoveryNotSet')
      : t('hero.packet.recoveryNotSet')
  const heroRunSignal = authRequired
    ? t('hero.runState.authRequired')
    : unavailableSignals.includes('runs') || initialLoadPending
      ? t('hero.runState.unavailable')
    : latestRun
      ? humanizeRunStatus(latestRun.status, t)
      : t('hero.runState.noLiveRun')
  const heroBudgetSignal = authRequired
    ? t('hero.runState.authRequired')
    : unavailableSignals.includes('budget') || initialLoadPending
      ? t('hero.budgetLine.offline')
    : budget
      ? formatPercent(budget.usage_percentage)
      : t('hero.budgetLine.pending')
  const heroGateSignal =
    pendingApprovalTotal === null || unavailableSignals.includes('approval:PENDING')
      ? t('hero.gateState.unavailable')
      : pendingApprovalTotal > 0
        ? t('hero.gateState.waiting', { count: pendingApprovalTotal })
      : t('hero.gateState.unavailable')
  const autopilotPacketPreview = [
    t('hero.packet.run', { value: latestRun ? latestRun.id.slice(0, 8) : t('hero.packet.runNone') }),
    t('hero.packet.runtime', { value: runtimeDisplayLabel }),
    t('hero.packet.budget', { value: heroBudgetSignal }),
    t('hero.packet.gate', { value: heroGateSignal }),
    t('hero.packet.recovery', { value: recoveryFocusedStep }),
  ].join('\n')

  return (
    <PicoShell
      eyebrow={t('shell.eyebrow')}
      title={t('shell.title')}
      description={t('shell.description')}
      heroContent={
        <div
          className="relative overflow-hidden rounded-[28px] border border-[color:var(--pico-border-hover)] bg-[linear-gradient(135deg,rgba(var(--pico-accent-rgb),0.14),rgba(8,14,9,0.92)_36%,rgba(255,255,255,0.02)_100%)] p-5 shadow-[0_24px_70px_rgba(0,0,0,0.28)] sm:p-6"
          data-testid="pico-autopilot-hero-signal"
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
                <span className={picoClasses.chip}>{t('hero.runtimePulse')}</span>
                <span className="inline-flex rounded-full border border-[color:var(--pico-border)] bg-[rgba(255,255,255,0.03)] px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-[color:var(--pico-text-secondary)]">
                  {loadStateLabel}
                </span>
              </div>
              <h2 className="font-[family:var(--font-site-display)] text-[clamp(1.9rem,4vw,2.9rem)] leading-[0.94] tracking-[-0.06em] text-[color:var(--pico-text)]">
                {t('hero.headline')}
              </h2>
              <p className="max-w-2xl text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                {t('hero.body')}
              </p>

              <div className="grid min-w-0 gap-3 sm:grid-cols-2 2xl:grid-cols-4">
                <div className={picoSoft('p-4')}>
                  <p className={picoClasses.label}>{t('hero.runState.label')}</p>
                  <p className="mt-2 font-[family:var(--font-site-display)] text-3xl tracking-[-0.05em] text-[color:var(--pico-text)]">
                    {heroRunSignal}
                  </p>
                  <p className="mt-2 text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                    {latestRunTimestamp ? formatTimestamp(latestRunTimestamp, locale, t('shared.time.unknown')) : t('hero.runState.triggerTaskFirst')}
                  </p>
                </div>

                <div className={picoSoft('min-w-0 p-4')} data-testid="pico-runtime-freshness">
                  <p className={picoClasses.label}>{t('hero.providerSnapshot')}</p>
                  <p className="mt-2 break-words font-[family:var(--font-site-display)] text-xl tracking-[-0.04em] text-[color:var(--pico-text)]">
                    {runtimeDisplayLabel}
                  </p>
                  <p className="mt-2 text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                    {initialLoadPending
                      ? t('runtimePresentation.waitingForObservation')
                      : runtimePresentation.observedAt
                      ? t('runtimePresentation.observedAt', { time: formatTimestamp(runtimePresentation.observedAt, locale, t('shared.time.unknown')) })
                      : t('runtimePresentation.fetchedWithoutObservation', { time: formatTimestamp(runtimePresentation.fetchedAt, locale, t('shared.time.unknown')) })}
                  </p>
                </div>

                <div className={picoSoft('p-4')}>
                  <p className={picoClasses.label}>{t('hero.budgetLine.label')}</p>
                  <p className="mt-2 font-[family:var(--font-site-display)] text-3xl tracking-[-0.05em] text-[color:var(--pico-text)]">
                    {heroBudgetSignal}
                  </p>
                  <p className="mt-2 text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                    {budget
                      ? t('hero.budgetLine.threshold', { percent: formatPercent(progress.autopilot.costThresholdPercent) })
                      : t('hero.budgetLine.waitingForSpend')}
                  </p>
                </div>

                <div className={picoSoft('p-4')}>
                  <p className={picoClasses.label}>{t('hero.gateState.label')}</p>
                  <p className="mt-2 break-words font-[family:var(--font-site-display)] text-2xl tracking-[-0.05em] text-[color:var(--pico-text)]">
                    {heroGateSignal}
                  </p>
                  <p className="mt-2 text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                    {t('gateStatus.configuredLocally')}: {progress.autopilot.approvalGateEnabled ? t('gateStatus.yes') : t('gateStatus.no')}
                  </p>
                </div>
              </div>

              <div className={picoInset('grid gap-3 p-4 sm:grid-cols-[auto,minmax(0,1fr)] sm:items-center')}>
                <div className="flex h-14 w-14 items-center justify-center rounded-[20px] border border-[rgba(var(--pico-accent-rgb),0.24)] bg-[linear-gradient(180deg,rgba(var(--pico-accent-rgb),0.18),rgba(7,13,8,0.5))] shadow-[0_18px_40px_rgba(var(--pico-accent-rgb),0.12)]">
                  <span className="h-3 w-3 rounded-full bg-[color:var(--pico-accent-bright)] shadow-[0_0_18px_rgba(var(--pico-accent-rgb),0.5)]" />
                </div>
                <div className="min-w-0">
                  <p className={picoClasses.label}>{t('hero.nextCheck.label')}</p>
                  <p className="mt-2 font-[family:var(--font-site-display)] text-2xl tracking-[-0.05em] text-[color:var(--pico-text)]">
                    {latestRun ? t('hero.nextCheck.inspectRun', { runId: latestRun.id.slice(0, 8) }) : t('hero.nextCheck.createFirstRun')}
                  </p>
                  <p className="mt-2 text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                    {latestRun
                      ? describeRunDetail(latestRun, latestRunTraces, t)
                      : t('hero.nextCheck.noRunBody')}
                  </p>
                </div>
              </div>
            </div>

            <div className={picoInset('grid gap-4 overflow-hidden border-[color:rgba(var(--pico-accent-rgb),0.24)] bg-[radial-gradient(circle_at_50%_20%,rgba(var(--pico-accent-rgb),0.16),rgba(6,11,7,0.94)_54%,rgba(3,5,3,0.98)_100%)] p-4')}>
              <div className={picoSoft('p-4')}>
                <p className={picoClasses.label}>{t('hero.packet.label')}</p>
                <pre className="mt-3 whitespace-pre-wrap text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                  <code>{autopilotPacketPreview}</code>
                </pre>
              </div>
              <div className={picoSoft('p-4')}>
                <p className={picoClasses.label}>{t('hero.decisionLine.label')}</p>
                <p className="mt-3 text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                  {thresholdBreached
                    ? t('hero.decisionLine.thresholdBreached')
                    : (pendingApprovalTotal ?? 0) > 0
                      ? t('hero.decisionLine.pendingQueue')
                      : t('hero.decisionLine.clear')}
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
        <Link
          href={primaryAutopilotHref}
          className={picoClasses.primaryButton}
        >
          {primaryAutopilotLabel}
        </Link>
      }
    >
      <PicoSessionBanner
        session={session}
        nextPath={pathname}
        progressSyncState={syncState}
        runtimeSignal={{
          label: runtimeDisplayLabel,
          state: initialLoadPending
            ? 'loading'
            : runtimePresentation.state === 'fresh'
              ? runtimePresentation.reportedStatus?.toLowerCase() === 'healthy'
                ? 'available'
                : 'degraded'
              : runtimePresentation.state,
        }}
      />
      <PicoSurfaceCompass
        title={t('surfaceCompass.title')}
        body={t('surfaceCompass.body')}
        status={
          authRequired
            ? t('surfaceCompass.status.hostedSessionRequired')
            : latestRun
              ? t('surfaceCompass.status.runtimeVisible')
              : t('surfaceCompass.status.waitingForFirstRun')
        }
        aside={t('surfaceCompass.aside')}
        items={[
          {
            href: nextLesson ? toHref(`/academy/${nextLesson.slug}`) : toHref('/academy'),
            label: nextLesson ? t('surfaceCompass.items.finishLesson', { lessonTitle: nextLesson.title }) : t('surfaceCompass.items.goBackToAcademy'),
            caption: t('surfaceCompass.items.lessonCaption'),
            note: t('surfaceCompass.items.backToLaneNote'),
          },
          {
            href: toHref(`/tutor${nextLesson ? `?lesson=${nextLesson.slug}` : ''}`),
            label: t('surfaceCompass.items.askTutor'),
            caption: t('surfaceCompass.items.askTutorCaption'),
            note: t('surfaceCompass.items.askTutorNote'),
          },
          {
            href: '#recent-runs',
            label: t('surfaceCompass.items.stayOnRecentRuns'),
            caption: t('surfaceCompass.items.stayOnRecentRunsCaption'),
            note: t('surfaceCompass.items.stayHereNote'),
            tone: 'primary',
          },
          {
            href: toHref('/support'),
            label: t('surfaceCompass.items.escalateWithEvidence'),
            caption: t('surfaceCompass.items.escalateCaption'),
            note: t('surfaceCompass.items.messyEdgeNote'),
            tone: 'soft',
          },
        ]}
      />

      {authRequired ? (
        <div className="mb-6 rounded-[28px] border border-amber-400/20 bg-amber-400/10 p-6 text-sm leading-6 text-amber-50">
          {t('banner.authRequired')}
        </div>
      ) : null}

      {error ? (
        <div role="alert" className="mb-6 break-words rounded-[28px] border border-rose-400/20 bg-rose-400/10 p-5 text-sm leading-6 text-rose-50 sm:p-6">
          {error}
        </div>
      ) : null}

      {approvalNotice ? (
        <div
          ref={approvalNoticeRef}
          role="status"
          aria-live="polite"
          tabIndex={-1}
          className="mb-6 rounded-[28px] border border-[color:var(--pico-border-hover)] bg-[rgba(var(--pico-accent-rgb),0.12)] p-5 text-sm leading-6 text-[color:var(--pico-text)] outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--pico-accent)] sm:p-6"
        >
          {approvalNotice}
        </div>
      ) : null}

      <section className={picoPanel('mb-6 p-6 sm:p-7')} data-testid="pico-autopilot-operator-doctrine">
        <div className="grid gap-6 lg:grid-cols-[minmax(0,1.08fr),20rem]">
          <div>
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div>
                <p className={picoClasses.label}>{t('operatorDoctrine.sectionLabel')}</p>
                <h2 className="mt-3 font-[family:var(--font-site-display)] text-4xl tracking-[-0.06em] text-[color:var(--pico-text)]">
                  {t('operatorDoctrine.title')}
                </h2>
              </div>
              <span className={picoClasses.chip}>{t('operatorDoctrine.chip')}</span>
            </div>

            <div className={storyRailClass}>
              {reviewFlow.map((item) => (
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
              <p className={picoClasses.label}>{t('operatorDoctrine.postureLabel')}</p>
              <p className="mt-3 text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                {t('operatorDoctrine.postureBody')}
              </p>
            </div>

            <div className={picoInset('p-5')}>
              <p className={picoClasses.label}>{t('operatorDoctrine.decisionLineLabel')}</p>
              <p className="mt-3 text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                {t('operatorDoctrine.decisionLineBody')}
              </p>
            </div>

            <div className={picoInset('p-4')}>
                <p className={picoClasses.label}>{t('operatorDoctrine.operatorCuesLabel')}</p>
              <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-1">
                {autopilotVisuals.map((item) => (
                  <PicoSignalDiagram key={item.index} {...item} compact />
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
              <p className={picoClasses.label}>{t('controlBrief.sectionLabel')}</p>
              <h2 className="mt-3 font-[family:var(--font-site-display)] text-4xl tracking-[-0.06em] text-[color:var(--pico-text)] sm:text-5xl">
                {t('controlBrief.title')}
              </h2>
              <p className="mt-4 max-w-3xl text-sm leading-7 text-[color:var(--pico-text-secondary)] sm:text-base">
                {t('controlBrief.body')}
              </p>

              <div className={picoEmber('mt-6 p-5')}>
                <div className="flex flex-wrap items-center gap-2">
                  <span className={picoClasses.chip}>{loadStateLabel}</span>
                  <span className={picoClasses.chip}>
                    {authRequired ? t('controlBrief.chip.hostedSessionRequired') : runtimeDisplayLabel}
                  </span>
                  <span className={picoClasses.chip}>
                    {t('gateStatus.configuredLocally')}: {progress.autopilot.approvalGateEnabled ? t('gateStatus.yes') : t('gateStatus.no')}
                  </span>
                </div>
                <p className="mt-4 text-sm leading-7 text-[color:var(--pico-text-secondary)]">
                  {authRequired
                    ? t('controlBrief.summary.authRequired')
                    : `${runtimeDisplayDetail} ${latestRun
                      ? t('controlBrief.summary.withRun', {
                          runId: latestRun.id.slice(0, 8),
                          status: humanizeRunStatus(latestRun.status, t),
                          asOfClause: latestRunTimestamp
                            ? t('controlBrief.summary.withRunAsOf', {
                                timestamp: formatTimestamp(latestRunTimestamp, locale, t('shared.time.unknown')),
                              })
                            : '',
                          detail: describeRunDetail(latestRun, latestRunTraces, t),
                        })
                      : t('controlBrief.summary.noRun')}`}
                </p>
              </div>

            </div>

            <div className="border-t border-[color:var(--pico-border)] bg-[color:var(--pico-bg-surface)] p-6 lg:border-s lg:border-t-0">
              <p className={picoClasses.label}>{t('operatorRail.sectionLabel')}</p>
              <div className="mt-4 grid gap-3">
                <div className={picoSoft('p-4')}>
                  <p className="text-sm text-[color:var(--pico-text-muted)]">{t('operatorRail.sessionStatusLabel')}</p>
                  <p className="mt-1 text-lg font-medium text-[color:var(--pico-text)]">
                    {authRequired ? t('operatorRail.sessionStatus.authRequired') : t('operatorRail.sessionStatus.attached')}
                  </p>
                </div>
                <div className={picoSoft('min-w-0 p-4')}>
                  <p className="text-sm text-[color:var(--pico-text-muted)]">{t('hero.providerSnapshot')}</p>
                  <p className="mt-1 break-words text-lg font-medium text-[color:var(--pico-text)]">
                    {runtimeDisplayLabel}
                  </p>
                  <p className="mt-2 text-xs leading-5 text-[color:var(--pico-text-secondary)]">
                    {initialLoadPending
                      ? t('runtimePresentation.waitingForFirstFetch')
                      : t('runtimePresentation.fetchedAt', { time: formatTimestamp(runtimePresentation.fetchedAt, locale, t('shared.time.unknown')) })}
                  </p>
                </div>
                <div className={picoSoft('p-4')}>
                  <p className="text-sm text-[color:var(--pico-text-muted)]">{t('operatorRail.progressSyncLabel')}</p>
                  <p className="mt-1 text-lg font-medium text-[color:var(--pico-text)]">{t(`shared.syncStateLabels.${syncState}`)}</p>
                </div>
                <div className={picoSoft('p-4')}>
                  <p className="text-sm text-[color:var(--pico-text-muted)]">{t('operatorRail.budgetLineLabel')}</p>
                  <p className="mt-1 text-lg font-medium text-[color:var(--pico-text)]">
                    {formatPercent(progress.autopilot.costThresholdPercent)}
                  </p>
                </div>
                <div className={picoSoft('p-4')}>
                  <p className="text-sm text-[color:var(--pico-text-muted)]">{t('gateStatus.configuredLocally')}</p>
                  <p className="mt-1 text-lg font-medium text-[color:var(--pico-text)]">
                    {progress.autopilot.approvalGateEnabled ? t('gateStatus.yes') : t('gateStatus.no')}
                  </p>
                </div>
                <div className={picoSoft('p-4')}>
                  <p className="text-sm text-[color:var(--pico-text-muted)]">{t('operatorRail.activeSurfaceLabel')}</p>
                  <p className="mt-1 text-lg font-medium text-[color:var(--pico-text)]">
                    {progress.platform.activeSurface ? t('shell.eyebrow') : t('operatorRail.activeSurfaceNone')}
                  </p>
                </div>
                <div className={picoSoft('p-4')}>
                  <p className="text-sm text-[color:var(--pico-text-muted)]">{t('operatorRail.helpLaneLabel')}</p>
                  <p className="mt-1 text-lg font-medium text-[color:var(--pico-text)]">
                    {progress.platform.helpLaneOpen ? t('operatorRail.helpLane.open') : t('operatorRail.helpLane.closed')}
                  </p>
                </div>
              </div>

              <div className={picoInset('mt-4 p-4')}>
                <p className={picoClasses.label}>{t('operatorRail.jumpToSubsystem')}</p>
                <div className="mt-3 grid gap-2">
                  <Link href="#timeline-section" className={picoClasses.secondaryButton}>
                    {t('operatorRail.jump.timeline')}
                  </Link>
                  <Link href="#recent-runs" className={picoClasses.tertiaryButton}>
                    {t('operatorRail.jump.recentRuns')}
                  </Link>
                  <Link href="#alerts-section" className={picoClasses.tertiaryButton}>
                    {t('operatorRail.jump.alerts')}
                  </Link>
                  <Link href="#approvals-section" className={picoClasses.tertiaryButton}>
                    {t('operatorRail.jump.approvalQueue')}
                  </Link>
                </div>
              </div>

              <div className={picoInset('mt-4 p-4')}>
                <p className={picoClasses.label}>{t('operatorRail.emptyFeedLabel')}</p>
                <p className="mt-3 text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                  {t('operatorRail.emptyFeedBody')}
                </p>
                <Link
                  href={nextLesson ? toHref(`/academy/${nextLesson.slug}`) : toHref('/academy')}
                  className={cn(picoClasses.secondaryButton, 'mt-4')}
                >
                  {nextLesson ? t('shared.action.openLesson', { lessonTitle: nextLesson.title }) : t('shared.action.returnToAcademy')}
                </Link>
              </div>
            </div>
          </div>

          <div className="grid gap-4 border-t border-[color:var(--pico-border)] p-6 md:grid-cols-2 xl:grid-cols-5">
            <StatCard
              label={t('stats.runs.label')}
              value={signalValue('runs', String(runs.length))}
              hint={liveHint(
                unavailableSignals.includes('runs')
                  ? t('stats.runs.offline')
                  : !integrationStatus.hasLiveAgent
                  ? t('stats.runs.noAgent')
                  : runs.length > 0
                    ? t('stats.runs.hasRuns')
                    : t('stats.runs.noRunsYet'),
                t('stats.runs.offline'),
              )}
            />
            <StatCard
              label={t('stats.failures.label')}
              value={signalValue('runs', String(failedRuns.length))}
              hint={liveHint(
                unavailableSignals.includes('runs')
                  ? t('stats.failures.offline')
                  : failedRuns.length > 0
                  ? t('stats.failures.hasFailures')
                  : t('stats.failures.none'),
                t('stats.failures.offline'),
              )}
            />
            <StatCard
              label={t('stats.alerts.label')}
              value={signalValue('alerts', String(alerts.filter((alert) => !alert.resolved).length))}
              hint={liveHint(
                unavailableSignals.includes('alerts')
                  ? t('stats.alerts.offline')
                  : alerts.some((alert) => !alert.resolved)
                  ? t('stats.alerts.hasAlerts')
                  : integrationStatus.hasRuns
                    ? t('stats.alerts.noneWithRuns')
                    : t('stats.alerts.noneNoRuns'),
                t('stats.alerts.offline'),
              )}
            />
            <StatCard
              label={t('stats.budget.label')}
              value={signalValue('budget', budget ? formatPercent(budget.usage_percentage) : '--')}
              hint={liveHint(
                unavailableSignals.includes('budget')
                  ? t('stats.budget.offline')
                  : !integrationStatus.hasBudget
                  ? t('stats.budget.noSnapshot')
                  : integrationStatus.hasUsage
                    ? t('stats.budget.hasUsage', { threshold: formatPercent(progress.autopilot.costThresholdPercent) })
                    : t('stats.budget.noUsage'),
                t('stats.budget.offline'),
              )}
            />
            <StatCard
              label={t('stats.approvals.label')}
              value={signalValue('approval:PENDING', pendingApprovalTotal === null ? '--' : String(pendingApprovalTotal))}
              hint={liveHint(
                unavailableSignals.includes('approval:PENDING') || pendingApprovalTotal === null
                  ? t('stats.approvals.offline')
                  : pendingApprovalTotal > 0
                  ? t('stats.approvals.pending')
                  : t('stats.approvals.none'),
                t('stats.approvals.offline'),
              )}
            />
          </div>
        </div>

        <aside className="space-y-6 xl:sticky xl:top-6 xl:self-start">
          <section className={picoPanel('p-5')}>
            <p className={picoClasses.label}>{t('sidebar.latestRunLabel')}</p>
            <div className="mt-4 grid gap-3">
              <div className={picoSoft('p-4')}>
                <p className="text-sm text-[color:var(--pico-text-muted)]">{t('sidebar.latestRunLabel')}</p>
                <p className="mt-1 text-lg font-medium text-[color:var(--pico-text)]">
                  {authRequired
                    ? t('sidebar.latestRun.unavailable')
                    : latestRun
                      ? humanizeRunStatus(latestRun.status, t)
                      : t('sidebar.latestRun.noneYet')}
                </p>
              </div>
              <div className={picoSoft('p-4')}>
                <p className="text-sm text-[color:var(--pico-text-muted)]">{t('sidebar.thresholdLineLabel')}</p>
                <p className="mt-1 text-lg font-medium text-[color:var(--pico-text)]">
                  {thresholdBreached ? t('sidebar.thresholdLine.breached') : t('sidebar.thresholdLine.clear')}
                </p>
              </div>
              {nextLesson ? (
                <>
                  <div className={picoInset('p-4')} data-testid="pico-autopilot-academy-context">
                    <p className="text-sm text-[color:var(--pico-text-muted)]">{t('sidebar.recoveryLessonLabel')}</p>
                    <p className="mt-1 text-lg font-medium text-[color:var(--pico-text)]">{nextLesson.title}</p>
                    <p className="mt-2 text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                      {t('sidebar.stepsProgress', { completed: recoveryWorkspace.completedStepCount, total: nextLesson.steps.length })}
                    </p>
                    <p className="mt-2 text-sm font-medium text-[color:var(--pico-text)]">
                      {recoveryWorkspace.workspace.evidence.trim() ? t('sidebar.evidence.captured') : t('sidebar.evidence.missing')}
                    </p>
                  </div>
                  <div className={picoInset('p-4')}>
                    <p className="text-sm text-[color:var(--pico-text-muted)]">{t('sidebar.workspaceProofLabel')}</p>
                    <p className="mt-1 text-lg font-medium text-[color:var(--pico-text)]">
                      {recoveryWorkspace.workspace.evidence.trim() ? t('sidebar.evidence.captured') : t('sidebar.evidence.missing')}
                    </p>
                    <p className="mt-2 text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                      {t('sidebar.stepsWithFocus', { completed: recoveryWorkspace.completedStepCount, total: nextLesson.steps.length, stepTitle: recoveryFocusedStep })}
                    </p>
                  </div>
                </>
              ) : null}
            </div>
            <div className="mt-4 grid gap-3">
              <Link
                href={nextLesson ? toHref(`/academy/${nextLesson.slug}`) : toHref('/academy')}
                className={picoClasses.secondaryButton}
              >
                {nextLesson ? t('shared.action.openLesson', { lessonTitle: nextLesson.title }) : t('shared.action.returnToAcademy')}
              </Link>
              <Link
                href={toHref(`/tutor${nextLesson ? `?lesson=${nextLesson.slug}` : ''}`)}
                className={picoClasses.tertiaryButton}
              >
                {t('sidebar.askTutor')}
              </Link>
              <Link href={toHref('/support')} className={picoClasses.tertiaryButton}>
                {t('sidebar.escalateHumanHelp')}
              </Link>
            </div>
            <div className={picoSoft('mt-4 p-4')}>
              <p className={picoClasses.body}>
                {t('sidebar.body')}
              </p>
            </div>
          </section>
        </aside>
      </section>

      <section className={picoPanel('mt-6 p-6 sm:p-7')} data-testid="pico-autopilot-control-protocol">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <p className={picoClasses.label}>{t('controlProtocol.sectionLabel')}</p>
            <h2 className="mt-3 font-[family:var(--font-site-display)] text-3xl tracking-[-0.05em] text-[color:var(--pico-text)] sm:text-4xl">
              {t('controlProtocol.title')}
            </h2>
            <p className="mt-3 max-w-3xl text-sm leading-6 text-[color:var(--pico-text-secondary)]">
              {t('controlProtocol.body')}
            </p>
          </div>
          <span className={picoClasses.chip}>{t('controlProtocol.chip')}</span>
        </div>

        <div className={storyRailClass}>
          {controlProtocol.map((item) => (
            <article key={item.id} className={picoInset('snap-start flex h-full flex-col p-5 sm:p-6')}>
              <div className="flex items-center justify-between gap-3">
                <span className="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-full border border-[color:var(--pico-border)] bg-[rgba(var(--pico-accent-rgb),0.12)] text-[11px] font-semibold uppercase tracking-[0.18em] text-[color:var(--pico-accent)]">
                  {item.id}
                </span>
                <span className={picoClasses.label}>{t('controlProtocol.cardLabel')}</span>
              </div>
              <h3 className="mt-6 font-[family:var(--font-site-display)] text-3xl tracking-[-0.05em] text-[color:var(--pico-text)]">
                {item.title}
              </h3>
              <p className="mt-4 flex-1 text-sm leading-7 text-[color:var(--pico-text-secondary)]">{item.body}</p>
              <Link href={item.href} className={cn(picoClasses.link, 'mt-6 inline-flex')}>
                {item.action}
              </Link>
            </article>
          ))}
        </div>
      </section>

      <section className="mt-6 grid gap-6 xl:grid-cols-[minmax(0,1.08fr),22rem]">
        <div className="space-y-6">
          <div id="timeline-section" className={sectionClasses()}>
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div className="min-w-0">
                <p className={picoClasses.label}>{t('timeline.sectionLabel')}</p>
                <h2 className="mt-3 font-[family:var(--font-site-display)] text-4xl tracking-[-0.05em] text-[color:var(--pico-text)]">
                  {t('timeline.title')}
                </h2>
                <p className="mt-3 text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                  {t('timeline.body')}
                </p>
              </div>
              <span className={picoClasses.chip}>{loadStateLabel}</span>
            </div>
            <div className="mt-5 space-y-4">
              {authRequired ? (
                <div className="rounded-[24px] border border-[color:var(--pico-border)] bg-[color:var(--pico-bg-surface)] p-5 text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                  {t('timeline.authRequired')}
                </div>
              ) : initialLoadPending ? (
                <div className="rounded-[24px] border border-[color:var(--pico-border)] bg-[color:var(--pico-bg-surface)] p-5 text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                  {t('timeline.loading')}
                </div>
              ) : timeline.length === 0 ? (
                <EmptyStatePanel state={runEmptyState} />
              ) : (
                <>
                  {visibleTimeline.map((item) => <TimelineItemCard key={item.id} item={item} locale={locale} t={t} />)}
                  {timeline.length > visibleTimeline.length ? (
                    <div className={picoSoft('p-4')}>
                      <p className="text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                        {t('timeline.olderSignalsHidden', {
                          count: timeline.length - visibleTimeline.length,
                          pluralSuffix: timeline.length - visibleTimeline.length === 1 ? '' : 's',
                        })}
                      </p>
                    </div>
                  ) : null}
                </>
              )}
            </div>
          </div>

          <div id="recent-runs" className={sectionClasses()}>
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div className="min-w-0">
                <p className={picoClasses.label}>{t('runs.sectionLabel')}</p>
                <h2 className="mt-3 font-[family:var(--font-site-display)] text-4xl tracking-[-0.05em] text-[color:var(--pico-text)]">
                  {t('runs.title')}
                </h2>
                <p className="mt-3 text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                  {t('runs.body')}
                </p>
              </div>
              <button
                type="button"
                onClick={() => void load()}
                aria-busy={loadState === 'loading'}
                className={cn(picoClasses.secondaryButton, 'min-h-11 w-full sm:w-auto')}
              >
                {loadState === 'loading' ? t('runs.refreshing') : t('runs.refresh')}
              </button>
            </div>
            <div className="mt-5 space-y-4">
              {authRequired ? (
                <div className="rounded-[24px] border border-[color:var(--pico-border)] bg-[color:var(--pico-bg-surface)] p-5 text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                  {t('runs.authRequired')}
                </div>
              ) : initialLoadPending ? (
                <div className="rounded-[24px] border border-[color:var(--pico-border)] bg-[color:var(--pico-bg-surface)] p-5 text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                  {t('runs.loading')}
                </div>
              ) : unavailableSignals.includes('runs') ? (
                <div className="rounded-[24px] border border-amber-400/20 bg-amber-400/10 p-5 text-sm leading-6 text-amber-50">
                  {t('runs.unavailable')}
                </div>
              ) : runs.length === 0 ? (
                <EmptyStatePanel state={runEmptyState} />
              ) : (
                <>
                  {visibleRuns.map((run) => {
                  const severity = getRunSeverity(run.status)
                  const traces = tracesByRunId[run.id] ?? []
                  const runTimestamp = run.completed_at ?? run.started_at ?? run.created_at

                  return (
                    <article key={run.id} className={`rounded-[24px] border p-5 ${severityClasses(severity)}`}>
                      <div className="flex flex-wrap items-start justify-between gap-4">
                        <div>
                          <p className="text-xs uppercase tracking-[0.18em]">{humanizeRunStatus(run.status, t)}</p>
                          <h3 className="mt-2 font-[family:var(--font-site-display)] text-3xl tracking-[-0.05em] text-[color:var(--pico-text)]">
                            {t('runs.card.title', { runId: run.id.slice(0, 8) })}
                          </h3>
                        </div>
                        <div className="text-end text-xs uppercase tracking-[0.18em] text-[color:var(--pico-text-secondary)]">
                          <p>{formatTimestamp(runTimestamp, locale, t('shared.time.unknown'))}</p>
                          <p className="mt-1">{formatRelativeTime(runTimestamp, new Date(), locale, t('shared.time.unknownRelative'))}</p>
                        </div>
                      </div>

                      <p className="mt-4 text-sm leading-7">{describeRunDetail(run, traces, t)}</p>

                      <div className="mt-5 grid gap-3 lg:grid-cols-[minmax(0,1fr),18rem]">
                        <div className={picoInset('p-4')}>
                          <p className={picoClasses.label}>{t('runs.card.operatorReadLabel')}</p>
                          <p className="mt-3 text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                            {['FAILED', 'ERROR', 'CANCELLED'].includes(run.status.toUpperCase())
                              ? t('runs.card.operatorRead.failed')
                              : ['RUNNING', 'QUEUED', 'PENDING'].includes(run.status.toUpperCase())
                                ? t('runs.card.operatorRead.active')
                                : t('runs.card.operatorRead.finished')}
                          </p>
                        </div>

                        <div className={picoInset('p-4')}>
                          <p className={picoClasses.label}>{t('runs.card.factsLabel')}</p>
                          <div className="mt-3 grid gap-2 text-sm text-[color:var(--pico-text-secondary)]">
                            <p>{t('runs.card.agent', { agentId: run.agent_id ?? t('runs.card.agentUnknown') })}</p>
                            <p>
                              {t('runs.card.traceCount', { count: unavailableTraceRunIds.includes(run.id) ? t('hero.runState.unavailable') : run.trace_count ?? traces.length })}
                            </p>
                            <p>
                              {run.started_at
                                ? t('runs.card.started', { timestamp: formatTimestamp(run.started_at, locale, t('shared.time.unknown')) })
                                : t('runs.card.startUnavailable')}
                            </p>
                          </div>
                        </div>
                      </div>

                      <div className={picoInset('mt-4 p-4')}>
                        <p className={picoClasses.label}>{t('runs.card.traceSignalsLabel')}</p>
                        {unavailableTraceRunIds.includes(run.id) ? (
                          <p className="mt-3 text-sm leading-6 text-amber-100">
                            {t('runs.card.tracesUnavailable')}
                          </p>
                        ) : traces.length === 0 ? (
                          <p className="mt-3 text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                            {t('runs.card.noTraces')}
                          </p>
                        ) : (
                          <div className="mt-3 grid gap-2">
                            {[...traces].slice(-3).reverse().map((trace) => (
                              <div
                                key={`${trace.run_id}-${trace.sequence ?? trace.timestamp ?? trace.event_type}`}
                                className={picoSoft('px-4 py-3')}
                              >
                                <p className="text-xs uppercase tracking-[0.16em] text-[#b09376]">
                                  {trace.event_type}
                                </p>
                                <p className="mt-1 text-sm leading-6 text-[color:var(--pico-text-secondary)]">{trace.message}</p>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    </article>
                  )
                  })}
                  {runs.length > visibleRuns.length ? (
                    <div className={picoSoft('p-4')}>
                      <p className="text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                        {t('runs.olderRunsHidden', {
                          count: runs.length - visibleRuns.length,
                          pluralSuffix: runs.length - visibleRuns.length === 1 ? '' : 's',
                        })}
                      </p>
                    </div>
                  ) : null}
                </>
              )}
            </div>
          </div>
        </div>

        <aside className="space-y-6 xl:sticky xl:top-6 xl:self-start">
          <div id="budget-section" className={sectionClasses()}>
            <p className={picoClasses.label}>{t('spend.sectionLabel')}</p>
            <h2 className="mt-3 font-[family:var(--font-site-display)] text-4xl tracking-[-0.05em] text-[color:var(--pico-text)]">
              {t('spend.title')}
            </h2>

            <div className="mt-5 grid gap-4">
              <div className={picoInset('p-5')}>
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div className="min-w-0">
                    <p className={picoClasses.label}>{t('spend.usageLabel')}</p>
                    <p className="mt-3 font-[family:var(--font-site-display)] text-5xl tracking-[-0.06em] text-[color:var(--pico-text)]">
                      {signalValue('budget', budget ? formatPercent(budget.usage_percentage) : '--')}
                    </p>
                  </div>
                  <span className={picoClasses.chip}>
                    {unavailableSignals.includes('budget')
                      ? t('spend.thresholdStatus.unavailable')
                      : budget
                        ? thresholdBreached ? t('spend.thresholdStatus.above') : t('spend.thresholdStatus.within')
                        : t('spend.thresholdStatus.noSnapshot')}
                  </span>
                </div>
                <p className="mt-3 text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                  {authRequired
                    ? t('spend.summary.authRequired')
                    : initialLoadPending
                      ? t('spend.summary.loading')
                    : unavailableSignals.includes('budget')
                      ? t('spend.summary.unavailable')
                      : budget
                      ? t('spend.summary.withBudget', { used: budget.credits_used, total: budget.credits_total, reset: budget.reset_date ? formatTimestamp(budget.reset_date, locale, t('shared.time.unknown')) : t('spend.summary.resetUnknown') })
                      : t('spend.summary.noSnapshot')}
                </p>
              </div>

              <div className={picoSoft('p-5')}>
                <p className={picoClasses.label}>{t('spend.thresholdLabel')}</p>
                <p className="mt-3 text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                  {t('spend.thresholdBody')}
                </p>

                <label className="mt-4 block text-sm text-[color:var(--pico-text-secondary)]">
                  <span className="block text-xs uppercase tracking-[0.24em] text-[color:var(--pico-text-muted)]">
                    {t('spend.thresholdInputLabel')}
                  </span>
                  <input
                    type="number"
                    min={1}
                    max={100}
                    value={thresholdDraft}
                    onChange={(event) => {
                      setError(null)
                      setThresholdDraft(Number(event.target.value))
                    }}
                    className="mt-3 w-full rounded-2xl border border-[color:var(--pico-border)] bg-[color:var(--pico-bg-surface)] px-4 py-3 text-sm text-[color:var(--pico-text)] outline-none"
                  />
                </label>

                <div className="mt-4 flex flex-wrap gap-3">
                  <button
                    type="button"
                    onClick={saveThreshold}
                    disabled={Boolean(thresholdValidationError)}
                    className="inline-flex min-h-11 items-center justify-center gap-2 rounded-full bg-[color:var(--pico-accent)] px-4 py-2 text-sm font-semibold text-[color:var(--pico-accent-contrast)] disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    {t('spend.saveThreshold')}
                  </button>
                  <span className={picoClasses.chip}>{t('spend.sync', { state: t(`shared.syncStateLabels.${syncState}`) })}</span>
                </div>

                {thresholdValidationError ? (
                  <div className="mt-4 rounded-2xl border border-rose-400/20 bg-rose-400/10 px-4 py-3 text-sm text-rose-50">
                    {thresholdValidationError}
                  </div>
                ) : null}
                {thresholdBreached ? (
                  <div className="mt-4 rounded-2xl border border-amber-400/20 bg-amber-400/10 px-4 py-3 text-sm text-amber-50">
                    {t('spend.breachedWarning')}
                  </div>
                ) : null}
              </div>

              <div className="grid gap-4">
                <div className={picoInset('p-4')}>
                  <p className={picoClasses.label}>{t('spend.topSpendersLabel')}</p>
                  <div className="mt-3 grid gap-2">
                    {authRequired ? (
                      <p className="text-sm leading-6 text-[color:var(--pico-text-secondary)]">{t('spend.breakdownAuthRequired')}</p>
                    ) : initialLoadPending ? (
                      <p className="text-sm leading-6 text-[color:var(--pico-text-secondary)]">{t('spend.breakdownLoading')}</p>
                    ) : unavailableSignals.includes('usage') ? (
                      <p className="text-sm leading-6 text-amber-100">{t('spend.breakdownUnavailable')}</p>
                    ) : usage?.usage_by_agent.length ? (
                      usage.usage_by_agent.slice(0, 3).map((item) => (
                        <div key={`${item.agent_id}-${item.agent_name}`} className={picoSoft('px-4 py-3')}>
                          <p className="font-medium text-[color:var(--pico-text)]">{item.agent_name}</p>
                          <p className="mt-1 text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                            {t('spend.breakdownRow', { credits: item.credits_used, events: item.event_count })}
                          </p>
                        </div>
                      ))
                    ) : (
                      <EmptyStatePanel state={usageEmptyState} />
                    )}
                  </div>
                </div>

                <div className={picoInset('p-4')}>
                  <p className={picoClasses.label}>{t('spend.usageDriversLabel')}</p>
                  <div className="mt-3 grid gap-2">
                    {authRequired ? (
                      <p className="text-sm leading-6 text-[color:var(--pico-text-secondary)]">{t('spend.breakdownAuthRequired')}</p>
                    ) : initialLoadPending ? (
                      <p className="text-sm leading-6 text-[color:var(--pico-text-secondary)]">{t('spend.driversLoading')}</p>
                    ) : unavailableSignals.includes('usage') ? (
                      <p className="text-sm leading-6 text-amber-100">{t('spend.driversUnavailable')}</p>
                    ) : usage?.usage_by_type.length ? (
                      usage.usage_by_type.slice(0, 3).map((item) => (
                        <div key={item.event_type} className={picoSoft('px-4 py-3')}>
                          <p className="font-medium text-[color:var(--pico-text)]">{item.event_type}</p>
                          <p className="mt-1 text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                            {t('spend.breakdownRow', { credits: item.credits_used, events: item.event_count })}
                          </p>
                        </div>
                      ))
                    ) : (
                      <EmptyStatePanel state={usageEmptyState} />
                    )}
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div id="alerts-section" className={sectionClasses()}>
            <p className={picoClasses.label}>{t('alerts.sectionLabel')}</p>
            <h2 className="mt-3 font-[family:var(--font-site-display)] text-4xl tracking-[-0.05em] text-[color:var(--pico-text)]">
              {t('alerts.title')}
            </h2>
            <p className="mt-3 text-sm leading-6 text-[color:var(--pico-text-secondary)]">
              {t('alerts.body')}
            </p>

            <div className="mt-5 space-y-4">
              {authRequired ? (
                <div className="rounded-[24px] border border-[color:var(--pico-border)] bg-[color:var(--pico-bg-surface)] p-5 text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                  {t('alerts.authRequired')}
                </div>
              ) : initialLoadPending ? (
                <div className="rounded-[24px] border border-[color:var(--pico-border)] bg-[color:var(--pico-bg-surface)] p-5 text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                  {t('alerts.loading')}
                </div>
              ) : unavailableSignals.includes('alerts') ? (
                <div className="rounded-[24px] border border-amber-400/20 bg-amber-400/10 p-5 text-sm leading-6 text-amber-50">
                  {t('alerts.unavailable')}
                </div>
              ) : alerts.length === 0 ? (
                <EmptyStatePanel state={alertsEmptyState} />
              ) : (
                <>
                  {visibleAlerts.map((alert) => (
                    <article
                      key={alert.id}
                      className={`rounded-[24px] border p-5 ${severityClasses(alert.resolved ? 'good' : 'critical')}`}
                    >
                      <div className="flex flex-wrap items-center justify-between gap-3">
                        <div>
                          <p className="text-xs uppercase tracking-[0.18em]">{alert.type}</p>
                          <h3 className="mt-2 text-lg font-semibold text-[color:var(--pico-text)]">
                            {alert.resolved ? t('alerts.card.resolvedTitle') : t('alerts.card.activeTitle')}
                          </h3>
                        </div>
                        <div className="text-end text-xs uppercase tracking-[0.18em] text-[color:var(--pico-text-secondary)]">
                          <p>{formatTimestamp(alert.resolved_at ?? alert.created_at, locale, t('shared.time.unknown'))}</p>
                          <p className="mt-1">{formatRelativeTime(alert.resolved_at ?? alert.created_at, new Date(), locale, t('shared.time.unknownRelative'))}</p>
                        </div>
                      </div>
                      <p className="mt-4 text-sm leading-6">{alert.message}</p>
                      <div className="mt-3 flex flex-wrap gap-4 text-sm text-[color:var(--pico-text-secondary)]">
                        <span>{t('alerts.card.agent', { agentId: alert.agent_id ?? t('runs.card.agentUnknown') })}</span>
                        <span>{alert.resolved ? t('alerts.card.resolvedStatus') : t('alerts.card.activeStatus')}</span>
                      </div>
                      <p className="mt-3 text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                        {t('shared.label.whyItMatters', { impact: explainAlertImpact(alert, t) })}
                      </p>
                    </article>
                  ))}
                  {alerts.length > visibleAlerts.length ? (
                    <div className={picoSoft('p-4')}>
                      <p className="text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                        {t('alerts.hiddenCount', {
                          count: alerts.length - visibleAlerts.length,
                          pluralSuffix: alerts.length - visibleAlerts.length === 1 ? '' : 's',
                        })}
                      </p>
                    </div>
                  ) : null}
                </>
              )}
            </div>
          </div>
        </aside>
      </section>

      <section id="approvals-section" className="mt-6 grid gap-6 xl:grid-cols-[minmax(0,1.08fr),22rem]">
        <div className={sectionClasses()}>
          <p className={picoClasses.label}>{t('approvals.sectionLabel')}</p>
          <h2 className="mt-3 font-[family:var(--font-site-display)] text-4xl tracking-[-0.05em] text-[color:var(--pico-text)]">
            {t('approvals.title')}
          </h2>
          <p className="mt-3 text-sm leading-6 text-[color:var(--pico-text-secondary)]">
            {t('approvals.body')}
          </p>

          <div className="mt-5 space-y-4">
            {authRequired ? (
              <div className="rounded-[24px] border border-[color:var(--pico-border)] bg-[color:var(--pico-bg-surface)] p-5 text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                {t('approvals.authRequired')}
              </div>
            ) : (
              <>
                {approvalUnavailableStatuses.length > 0 ? (
                  <div className="rounded-[24px] border border-amber-400/20 bg-amber-400/10 p-5 text-sm leading-6 text-amber-50">
                    {initialLoadPending
                      ? t('approvals.loading')
                      : t('approvals.partial', { statuses: approvalUnavailableStatuses.map((status) => t(`shared.statusLabels.${status}`)).join(', ') })}
                  </div>
                ) : null}

                {approvalUnavailableStatuses.length === 0 && pendingApprovalTotal === 0 && decisionTotal === 0 ? (
                  <EmptyStatePanel state={approvalsEmptyState} />
                ) : null}

                {visiblePendingApprovals.map((approval) => (
                  <article
                    key={approval.id}
                    aria-busy={resolvingApprovalId === approval.id}
                    className={`min-w-0 overflow-hidden rounded-[24px] border p-4 sm:p-5 ${severityClasses('warn')}`}
                  >
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <div className="min-w-0">
                        <p className="text-xs uppercase tracking-[0.18em]">{approval.status}</p>
                        <h3 className="mt-2 break-words text-lg font-semibold text-[color:var(--pico-text)]">{approval.action_type}</h3>
                      </div>
                      <div className="text-start text-xs uppercase tracking-[0.18em] text-[color:var(--pico-text-secondary)] sm:text-end">
                        <p>{formatTimestamp(approval.created_at, locale, t('shared.time.unknown'))}</p>
                        <p className="mt-1">{formatRelativeTime(approval.created_at, new Date(), locale, t('shared.time.unknownRelative'))}</p>
                      </div>
                    </div>
                    <p className="mt-4 break-words text-sm leading-6">
                      {typeof approval.payload?.summary === 'string'
                        ? approval.payload.summary
                        : t('approvals.card.fallbackSummary', { requester: approval.requester, agentId: approval.agent_id })}
                    </p>
                    <p className="mt-3 text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                      {t('shared.label.whyItMatters', { impact: explainApprovalImpact(approval, t) })}
                    </p>
                    {approvalActionErrors[approval.id] ? (
                      <p className="mt-4 rounded-[18px] border border-rose-400/25 bg-rose-400/10 p-3 text-sm text-rose-50" role="alert">
                        {approvalActionErrors[approval.id]}
                      </p>
                    ) : null}
                    {approval.can_resolve ? (
                      <div className="mt-4 grid gap-3 sm:flex sm:flex-wrap">
                        <button
                          type="button"
                          onClick={() => void resolveApproval(approval.id, 'approve')}
                          disabled={Boolean(resolvingApprovalId) || !approvalMutationsAvailable}
                          aria-label={t('approvals.card.approveLabel', { action: approval.action_type })}
                          className="inline-flex min-h-11 w-full items-center justify-center gap-2 rounded-full bg-[color:var(--pico-accent)] px-4 py-2 text-sm font-semibold text-[color:var(--pico-accent-contrast)] outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--pico-accent-bright)] disabled:cursor-not-allowed disabled:opacity-60 sm:w-auto"
                        >
                          {resolvingApprovalId === approval.id ? t('approvals.card.working') : t('approvals.card.approve')}
                        </button>
                        <button
                          type="button"
                          onClick={() => void resolveApproval(approval.id, 'reject')}
                          disabled={Boolean(resolvingApprovalId) || !approvalMutationsAvailable}
                          aria-label={t('approvals.card.rejectLabel', { action: approval.action_type })}
                          className="min-h-11 w-full rounded-full border border-[color:var(--pico-border)] px-4 py-2 text-sm font-medium text-[color:var(--pico-text-secondary)] outline-none focus-visible:border-[color:var(--pico-accent)] focus-visible:ring-2 focus-visible:ring-[rgba(var(--pico-accent-rgb),0.28)] disabled:cursor-not-allowed disabled:opacity-60 sm:w-auto"
                        >
                          {resolvingApprovalId === approval.id ? t('approvals.card.working') : t('approvals.card.reject')}
                        </button>
                      </div>
                    ) : null}
                  </article>
                ))}
                {pendingApprovalTotal !== null && pendingApprovalTotal > visiblePendingApprovals.length ? (
                  <div className={picoSoft('p-4')}>
                    <p className="text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                      {t('approvals.pendingPageCount', { visible: visiblePendingApprovals.length, total: pendingApprovalTotal })}
                    </p>
                    <button
                      type="button"
                      onClick={() => void showMorePendingApprovals()}
                      disabled={loadingApprovalPage !== null || Boolean(resolvingApprovalId)}
                      aria-busy={loadingApprovalPage === 'pending'}
                      className={cn(picoClasses.secondaryButton, 'mt-4 min-h-11 w-full sm:w-auto')}
                    >
                      {loadingApprovalPage === 'pending' ? t('approvals.loadingPending') : t('approvals.showMorePending')}
                    </button>
                  </div>
                ) : null}
              </>
            )}
          </div>
        </div>

        <aside className="space-y-6 xl:sticky xl:top-6 xl:self-start">
          <section className={picoPanel('p-5')}>
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div className="min-w-0">
                <p className={picoClasses.label}>{t('composer.sectionLabel')}</p>
                <p className="mt-2 text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                  {t('composer.body')}
                </p>
              </div>
              <span className={picoClasses.chip}>{t('composer.chip')}</span>
            </div>

            <form
              className="mt-4 grid min-w-0 gap-4"
              onSubmit={(event) => {
                event.preventDefault()
                void createApprovalRequest()
              }}
            >
              <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-1">
                <label className="grid gap-2 text-sm text-[color:var(--pico-text-secondary)]">
                  <span className={picoClasses.label}>{t('composer.agentIdLabel')}</span>
                  <input
                    required
                    maxLength={255}
                    value={approvalDraft.agentId}
                    onChange={(event) =>
                      setApprovalDraft((current) => ({ ...current, agentId: event.target.value }))
                    }
                    className="min-w-0 w-full rounded-[20px] border border-[color:var(--pico-border)] bg-[color:var(--pico-bg-surface)] px-4 py-3 text-[color:var(--pico-text)] outline-none placeholder:text-[color:var(--pico-text-muted)] focus-visible:border-[color:var(--pico-accent)] focus-visible:ring-2 focus-visible:ring-[rgba(var(--pico-accent-rgb),0.28)]"
                    placeholder={t('composer.agentIdPlaceholder')}
                  />
                </label>

                <label className="grid gap-2 text-sm text-[color:var(--pico-text-secondary)]">
                  <span className={picoClasses.label}>{t('composer.sessionOrRunIdLabel')}</span>
                  <input
                    required
                    maxLength={255}
                    value={approvalDraft.sessionId}
                    onChange={(event) =>
                      setApprovalDraft((current) => ({ ...current, sessionId: event.target.value }))
                    }
                    className="min-w-0 w-full rounded-[20px] border border-[color:var(--pico-border)] bg-[color:var(--pico-bg-surface)] px-4 py-3 text-[color:var(--pico-text)] outline-none placeholder:text-[color:var(--pico-text-muted)] focus-visible:border-[color:var(--pico-accent)] focus-visible:ring-2 focus-visible:ring-[rgba(var(--pico-accent-rgb),0.28)]"
                    placeholder={t('composer.sessionOrRunIdPlaceholder')}
                  />
                </label>
              </div>

              <label className="grid gap-2 text-sm text-[color:var(--pico-text-secondary)]">
                <span className={picoClasses.label}>{t('composer.actionTypeLabel')}</span>
                <input
                  required
                  maxLength={255}
                  value={approvalDraft.actionType}
                  onChange={(event) =>
                    setApprovalDraft((current) => ({ ...current, actionType: event.target.value }))
                  }
                  className="min-w-0 w-full rounded-[20px] border border-[color:var(--pico-border)] bg-[color:var(--pico-bg-surface)] px-4 py-3 text-[color:var(--pico-text)] outline-none placeholder:text-[color:var(--pico-text-muted)] focus-visible:border-[color:var(--pico-accent)] focus-visible:ring-2 focus-visible:ring-[rgba(var(--pico-accent-rgb),0.28)]"
                  placeholder={t('composer.actionTypePlaceholder')}
                />
              </label>

              <label className="grid gap-2 text-sm text-[color:var(--pico-text-secondary)]">
                <span className={picoClasses.label}>Assigned reviewer</span>
                <select
                  required
                  value={approvalDraft.reviewerId}
                  onChange={(event) =>
                    setApprovalDraft((current) => ({ ...current, reviewerId: event.target.value }))
                  }
                  disabled={eligibleReviewers.length === 0}
                  className="min-h-11 min-w-0 w-full rounded-[20px] border border-[color:var(--pico-border)] bg-[color:var(--pico-bg-surface)] px-4 py-3 text-[color:var(--pico-text)] outline-none focus-visible:border-[color:var(--pico-accent)] focus-visible:ring-2 focus-visible:ring-[rgba(var(--pico-accent-rgb),0.28)] disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {eligibleReviewers.length === 0 ? (
                    <option value="">No eligible reviewers are available</option>
                  ) : null}
                  {eligibleReviewers.map((reviewer) => (
                    <option key={reviewer.id} value={reviewer.id}>
                      {reviewer.name} · {reviewer.email}
                    </option>
                  ))}
                </select>
              </label>

              <label className="grid gap-2 text-sm text-[color:var(--pico-text-secondary)]">
                <span className={picoClasses.label}>{t('composer.summaryLabel')}</span>
                <textarea
                  maxLength={4000}
                  value={approvalDraft.summary}
                  onChange={(event) =>
                    setApprovalDraft((current) => ({ ...current, summary: event.target.value }))
                  }
                  rows={4}
                  className="min-w-0 w-full resize-y rounded-[20px] border border-[color:var(--pico-border)] bg-[color:var(--pico-bg-surface)] px-4 py-3 text-[color:var(--pico-text)] outline-none placeholder:text-[color:var(--pico-text-muted)] focus-visible:border-[color:var(--pico-accent)] focus-visible:ring-2 focus-visible:ring-[rgba(var(--pico-accent-rgb),0.28)]"
                  placeholder={t('composer.summaryPlaceholder')}
                />
              </label>

              <div className="grid gap-3">
                <button
                  type="submit"
                  disabled={creatingApproval || eligibleReviewers.length === 0}
                  aria-busy={creatingApproval}
                  className={picoClasses.primaryButton}
                >
                  {creatingApproval ? t('composer.creating') : t('composer.create')}
                </button>
                <button
                  type="button"
                  onClick={() =>
                    setApprovalDraft({
                      agentId: latestRun?.agent_id || '',
                      sessionId: latestRun?.id || '',
                      actionType: 'OUTBOUND_SEND',
                      summary: t('composer.summaryDefault'),
                      reviewerId: eligibleReviewers[0]?.id ?? '',
                    })
                  }
                  disabled={creatingApproval}
                  className={picoClasses.secondaryButton}
                >
                  {t('composer.reset')}
                </button>
              </div>
            </form>
          </section>

          <section className={picoPanel('p-5')}>
            <p className={picoClasses.label}>{t('gateStatus.sectionLabel')}</p>
            <div className="mt-4 grid gap-3">
              <div className={picoSoft('p-4')}>
                <p className="text-sm text-[color:var(--pico-text-muted)]">{t('gateStatus.pendingActions')}</p>
                <p className="mt-1 text-2xl font-semibold text-[color:var(--pico-text)]">{signalValue('approval:PENDING', pendingApprovalTotal === null ? '--' : String(pendingApprovalTotal))}</p>
              </div>
              <div className={picoSoft('p-4')}>
                <p className="text-sm text-[color:var(--pico-text-muted)]">{t('gateStatus.decisionHistory')}</p>
                <p className="mt-1 text-2xl font-semibold text-[color:var(--pico-text)]">
                  {decisionTotal === null || approvalUnavailableStatuses.some((status) => status !== 'PENDING')
                    ? '--'
                    : decisionTotal}
                </p>
              </div>
              <div className={picoSoft('p-4')}>
                <p className="text-sm text-[color:var(--pico-text-muted)]">{t('gateStatus.configuredLocally')}</p>
                <p className="mt-1 text-lg font-medium text-[color:var(--pico-text)]">
                  {progress.autopilot.approvalGateEnabled ? t('gateStatus.yes') : t('gateStatus.no')}
                </p>
              </div>
            </div>
          </section>

          {resolvedApprovals.length > 0 ? (
            <section className={picoPanel('p-5')}>
              <p className={picoClasses.label}>{t('recentDecisions.sectionLabel')}</p>
              <div className="mt-4 grid gap-3">
                {visibleResolvedApprovals.map((approval) => (
                  <article
                    key={approval.id}
                    className={`min-w-0 overflow-hidden rounded-[24px] border p-4 ${severityClasses(approval.status === 'APPROVED' ? 'good' : approval.status === 'REJECTED' ? 'critical' : 'neutral')}`}
                  >
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="text-xs uppercase tracking-[0.18em]">{approval.status}</p>
                        <h3 className="mt-2 text-base font-semibold text-[color:var(--pico-text)]">{approval.action_type}</h3>
                      </div>
                      <span className={picoClasses.chip}>
                        {formatRelativeTime(approval.resolved_at ?? approval.created_at, new Date(), locale, t('shared.time.unknownRelative'))}
                      </span>
                    </div>
                    <p className="mt-3 text-sm leading-6">
                      {typeof approval.payload?.summary === 'string'
                        ? approval.payload.summary
                        : t('approvals.card.fallbackSummary', { requester: approval.requester, agentId: approval.agent_id })}
                    </p>
                    <p className="mt-3 text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                      {t('shared.label.whyItMatters', { impact: explainApprovalImpact(approval, t) })}
                    </p>
                  </article>
                ))}
                {decisionTotal !== null && decisionTotal > visibleResolvedApprovals.length ? (
                  <div className={picoSoft('p-4')}>
                    <p className="text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                      {t('recentDecisions.pageCount', { visible: visibleResolvedApprovals.length, total: decisionTotal })}
                    </p>
                    <button
                      type="button"
                      onClick={() => void showMoreDecisions()}
                      disabled={loadingApprovalPage !== null || Boolean(resolvingApprovalId)}
                      aria-busy={loadingApprovalPage === 'decisions'}
                      className={cn(picoClasses.secondaryButton, 'mt-4 min-h-11 w-full sm:w-auto')}
                    >
                      {loadingApprovalPage === 'decisions' ? t('recentDecisions.loading') : t('recentDecisions.showMore')}
                    </button>
                  </div>
                ) : null}
              </div>
            </section>
          ) : null}
        </aside>
      </section>
    </PicoShell>
  )
}
