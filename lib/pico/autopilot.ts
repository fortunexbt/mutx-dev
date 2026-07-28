export type AutopilotRunSummary = {
  id: string
  status: string
  agent_id?: string | null
  started_at?: string | null
  completed_at?: string | null
  created_at?: string | null
  error_message?: string | null
  trace_count?: number | null
}

export type AutopilotRunTrace = {
  id: string
  run_id: string
  event_type: string
  message: string
  timestamp?: string | null
  sequence?: number | null
}

export type AutopilotBudgetSummary = {
  plan: string
  credits_total: number
  credits_used: number
  credits_remaining: number
  usage_percentage: number
  reset_date?: string | null
}

export type AutopilotUsageBreakdown = {
  usage_by_agent: Array<{
    agent_id: string
    agent_name: string
    credits_used: number
    event_count: number
  }>
  usage_by_type: Array<{
    event_type: string
    credits_used: number
    event_count: number
  }>
}

export type AutopilotAlertSummary = {
  id: string
  agent_id?: string | null
  type: string
  message: string
  resolved: boolean
  created_at: string
  resolved_at?: string | null
}

export type AutopilotApprovalSummary = {
  id: string
  owner_id: string
  reviewer_id: string | null
  can_resolve: boolean
  agent_id: string
  action_type: string
  payload?: { summary?: string; [key: string]: unknown } | null
  status: string
  requester: string
  approver?: string | null
  created_at: string
  resolved_at?: string | null
}

export type EligibleApprovalReviewer = {
  id: string
  email: string
  name: string
  roles: string[]
}

export const AUTOPILOT_APPROVAL_STATUSES = [
  'PENDING',
  'APPROVED',
  'REJECTED',
  'EXPIRED',
] as const

export type AutopilotApprovalStatus = (typeof AUTOPILOT_APPROVAL_STATUSES)[number]

export type AutopilotApprovalPage = {
  items: AutopilotApprovalSummary[]
  total: number
  skip: number
  limit: number
  status: AutopilotApprovalStatus | null
  agent_id: string | null
}

export type AutopilotRuntimeSnapshot = {
  provider: string
  label: string
  status: string
  last_seen_at: string | null
  last_synced_at: string | null
  stale: boolean
  stale_after_seconds: number | null
  binding_count: number | null
  gateway?: Record<string, unknown>
  gateway_url?: string | null
  version?: string | null
}

export type AutopilotRuntimePresentation = {
  state: 'fresh' | 'stale' | 'unavailable'
  label: string
  detail: string
  reportedStatus: string | null
  observedAt: string | null
  syncedAt: string | null
  fetchedAt: string
}

export type ApprovalMutationFailure = {
  kind: 'unauthorized' | 'forbidden' | 'not_found' | 'conflict' | 'server' | 'request'
  message: string
  shouldReload: boolean
  requiresAuth: boolean
}

export type AutopilotTimelineItem = {
  id: string
  occurredAt: string
  title: string
  detail: string
  impact: string
  severity: 'critical' | 'warn' | 'good' | 'neutral'
  sourceLabel: 'Run' | 'Alert' | 'Approval' | 'Budget'
  href: string
}

function safeDate(value?: string | null) {
  if (!value) return 0
  const timestamp = new Date(value).getTime()
  return Number.isFinite(timestamp) ? timestamp : 0
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

function isNonNegativeInteger(value: unknown): value is number {
  return typeof value === 'number' && Number.isInteger(value) && value >= 0
}

function isApprovalStatus(value: unknown): value is AutopilotApprovalStatus {
  return AUTOPILOT_APPROVAL_STATUSES.includes(value as AutopilotApprovalStatus)
}

function isApprovalSummary(value: unknown): value is AutopilotApprovalSummary {
  if (!isRecord(value)) return false

  return (
    typeof value.id === 'string' &&
    typeof value.owner_id === 'string' &&
    (value.reviewer_id === null || typeof value.reviewer_id === 'string') &&
    typeof value.can_resolve === 'boolean' &&
    typeof value.agent_id === 'string' &&
    typeof value.action_type === 'string' &&
    isApprovalStatus(value.status) &&
    typeof value.requester === 'string' &&
    typeof value.created_at === 'string'
  )
}

export function parseEligibleApprovalReviewers(
  payload: unknown,
): EligibleApprovalReviewer[] | null {
  if (!Array.isArray(payload)) return null
  if (!payload.every(isRecord)) return null
  const reviewers = payload.flatMap((reviewer) => {
    if (
      typeof reviewer.id !== 'string' ||
      typeof reviewer.email !== 'string' ||
      typeof reviewer.name !== 'string' ||
      !Array.isArray(reviewer.roles) ||
      !reviewer.roles.every((role) => typeof role === 'string')
    ) return []
    return [{
      id: reviewer.id,
      email: reviewer.email,
      name: reviewer.name,
      roles: reviewer.roles,
    }]
  })
  return reviewers.length === payload.length ? reviewers : null
}

function readErrorMessage(payload: unknown): string | null {
  if (!isRecord(payload)) return null
  if (typeof payload.detail === 'string' && payload.detail.trim()) return payload.detail.trim()
  if (typeof payload.message === 'string' && payload.message.trim()) return payload.message.trim()
  if (typeof payload.error === 'string' && payload.error.trim()) return payload.error.trim()

  if (isRecord(payload.error) && typeof payload.error.message === 'string' && payload.error.message.trim()) {
    return payload.error.message.trim()
  }

  return null
}

function parseIsoTimestamp(value: unknown): string | null {
  if (typeof value !== 'string' || !value.trim()) return null
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? null : date.toISOString()
}

export function parseApprovalPage(
  payload: unknown,
  expectedStatus?: AutopilotApprovalStatus,
): AutopilotApprovalPage | null {
  if (!isRecord(payload) || !Array.isArray(payload.items)) return null
  if (!isNonNegativeInteger(payload.total) || !isNonNegativeInteger(payload.skip)) return null
  if (!Number.isInteger(payload.limit) || (payload.limit as number) < 1) return null
  if (!payload.items.every(isApprovalSummary)) return null

  const status = payload.status === null ? null : isApprovalStatus(payload.status) ? payload.status : null
  if (payload.status !== null && status === null) return null
  if (expectedStatus && status !== expectedStatus) return null
  if (payload.total < payload.items.length) return null

  const agentId = payload.agent_id
  if (agentId !== null && typeof agentId !== 'string') return null

  return {
    items: payload.items,
    total: payload.total,
    skip: payload.skip,
    limit: payload.limit as number,
    status,
    agent_id: agentId,
  }
}

export function hasNextApprovalPage(page: AutopilotApprovalPage) {
  return page.skip + page.items.length < page.total
}

export function appendApprovalPage(
  current: AutopilotApprovalPage,
  next: AutopilotApprovalPage,
): AutopilotApprovalPage | null {
  if (current.status !== next.status || current.agent_id !== next.agent_id) return null
  if (next.skip !== current.skip + current.items.length) return null

  const itemsById = new Map(current.items.map((item) => [item.id, item]))
  next.items.forEach((item) => itemsById.set(item.id, item))
  if (itemsById.size > next.total) return null

  return {
    ...next,
    items: Array.from(itemsById.values()),
    skip: current.skip,
    total: next.total,
  }
}

export function parseRuntimeSnapshot(payload: unknown): AutopilotRuntimeSnapshot | null {
  if (!isRecord(payload)) return null
  if (
    typeof payload.provider !== 'string' ||
    typeof payload.label !== 'string' ||
    typeof payload.status !== 'string' ||
    typeof payload.stale !== 'boolean'
  ) {
    return null
  }

  const staleAfterSeconds = payload.stale_after_seconds
  if (
    staleAfterSeconds !== undefined &&
    staleAfterSeconds !== null &&
    (!Number.isInteger(staleAfterSeconds) || (staleAfterSeconds as number) < 1)
  ) {
    return null
  }

  const bindingCount = payload.binding_count
  if (bindingCount !== undefined && bindingCount !== null && !isNonNegativeInteger(bindingCount)) {
    return null
  }

  return {
    provider: payload.provider,
    label: payload.label,
    status: payload.status,
    last_seen_at: parseIsoTimestamp(payload.last_seen_at),
    last_synced_at: parseIsoTimestamp(payload.last_synced_at),
    stale: payload.stale,
    stale_after_seconds:
      typeof staleAfterSeconds === 'number' ? staleAfterSeconds : null,
    binding_count: typeof bindingCount === 'number' ? bindingCount : null,
    gateway: isRecord(payload.gateway) ? payload.gateway : undefined,
    gateway_url: typeof payload.gateway_url === 'string' ? payload.gateway_url : null,
    version: typeof payload.version === 'string' ? payload.version : null,
  }
}

export function presentRuntimeSnapshot(
  snapshot: AutopilotRuntimeSnapshot | null,
  fetchedAt: string,
  now = new Date(),
): AutopilotRuntimePresentation {
  const normalizedFetchedAt = parseIsoTimestamp(fetchedAt) ?? now.toISOString()
  if (!snapshot) {
    return {
      state: 'unavailable',
      label: 'Runtime unavailable',
      detail: 'No provider snapshot was returned. No runtime status or safety state is assumed.',
      reportedStatus: null,
      observedAt: null,
      syncedAt: null,
      fetchedAt: normalizedFetchedAt,
    }
  }

  const observedAt = parseIsoTimestamp(snapshot.last_seen_at)
  const syncedAt = parseIsoTimestamp(snapshot.last_synced_at)
  const staleAfterSeconds = snapshot.stale_after_seconds
  const observedTime = observedAt ? new Date(observedAt).getTime() : Number.NaN
  const nowTime = now.getTime()

  if (
    !observedAt ||
    !staleAfterSeconds ||
    !Number.isFinite(observedTime) ||
    observedTime > nowTime + 5 * 60 * 1000
  ) {
    return {
      state: 'unavailable',
      label: 'Runtime freshness unavailable',
      detail: `The fetched snapshot reported ${snapshot.status}, but it has no trustworthy observation time. Treat the runtime as unavailable.`,
      reportedStatus: snapshot.status,
      observedAt,
      syncedAt,
      fetchedAt: normalizedFetchedAt,
    }
  }

  const clientDetectedStale = nowTime - observedTime > staleAfterSeconds * 1000
  if (snapshot.stale || clientDetectedStale) {
    return {
      state: 'stale',
      label: 'Stale runtime snapshot',
      detail: `Last reported ${snapshot.status}. This is historical state, not a current health or safety signal.`,
      reportedStatus: snapshot.status,
      observedAt,
      syncedAt,
      fetchedAt: normalizedFetchedAt,
    }
  }

  return {
    state: 'fresh',
    label: 'Fresh runtime snapshot',
    detail: `Provider reported ${snapshot.status}. Freshness does not prove that an action is safe.`,
    reportedStatus: snapshot.status,
    observedAt,
    syncedAt,
    fetchedAt: normalizedFetchedAt,
  }
}

export function describeApprovalMutationFailure(
  status: number,
  payload: unknown,
  action: 'approve' | 'reject' | 'create',
): ApprovalMutationFailure {
  const operation = action === 'create' ? 'create this request' : `${action} this request`
  const upstreamMessage = readErrorMessage(payload)

  if (status === 401) {
    return {
      kind: 'unauthorized',
      message: `Sign in again before you ${operation}. No approval state was changed.`,
      shouldReload: false,
      requiresAuth: true,
    }
  }

  if (status === 403) {
    return {
      kind: 'forbidden',
      message: `You do not have permission to ${operation}. Ask the approval owner or an approver.`,
      shouldReload: false,
      requiresAuth: false,
    }
  }

  if (status === 404) {
    return {
      kind: 'not_found',
      message: 'This approval no longer exists or is no longer visible. The canonical queue was reloaded.',
      shouldReload: true,
      requiresAuth: false,
    }
  }

  if (status === 409) {
    return {
      kind: 'conflict',
      message: 'This approval was already decided elsewhere. The canonical queue was reloaded.',
      shouldReload: true,
      requiresAuth: false,
    }
  }

  if (status >= 500) {
    return {
      kind: 'server',
      message: `MUTX could not ${operation} right now. No approval state was assumed.${upstreamMessage ? ` ${upstreamMessage}` : ''}`,
      shouldReload: false,
      requiresAuth: false,
    }
  }

  return {
    kind: 'request',
    message: upstreamMessage ?? `Failed to ${operation}. No approval state was assumed.`,
    shouldReload: false,
    requiresAuth: false,
  }
}

function chooseRunTime(run: AutopilotRunSummary) {
  return run.completed_at ?? run.started_at ?? run.created_at ?? new Date(0).toISOString()
}

export function formatPercent(value: number) {
  return `${Math.round(value)}%`
}

export function formatTimestamp(value?: string | null) {
  if (!value) return 'Unknown time'
  const timestamp = new Date(value)
  if (Number.isNaN(timestamp.getTime())) return 'Unknown time'
  return timestamp.toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  })
}

export function formatRelativeTime(value?: string | null) {
  if (!value) return 'unknown'
  const timestamp = new Date(value).getTime()
  if (!Number.isFinite(timestamp)) return 'unknown'

  const deltaMs = Date.now() - timestamp
  const deltaMinutes = Math.round(deltaMs / 60000)
  const absoluteMinutes = Math.abs(deltaMinutes)

  if (absoluteMinutes < 1) return 'just now'
  if (absoluteMinutes < 60) return `${absoluteMinutes}m ${deltaMinutes >= 0 ? 'ago' : 'from now'}`

  const absoluteHours = Math.round(absoluteMinutes / 60)
  if (absoluteHours < 48) return `${absoluteHours}h ${deltaMinutes >= 0 ? 'ago' : 'from now'}`

  const absoluteDays = Math.round(absoluteHours / 24)
  return `${absoluteDays}d ${deltaMinutes >= 0 ? 'ago' : 'from now'}`
}

export function humanizeRunStatus(status: string) {
  return status.replace(/[_-]+/g, ' ').toLowerCase().replace(/\b\w/g, (char) => char.toUpperCase())
}

export function getRunSeverity(status: string): AutopilotTimelineItem['severity'] {
  const normalized = status.toUpperCase()
  if (['FAILED', 'ERROR', 'CANCELLED'].includes(normalized)) return 'critical'
  if (['RUNNING', 'QUEUED', 'PENDING'].includes(normalized)) return 'warn'
  if (['COMPLETED', 'SUCCEEDED', 'SUCCESS'].includes(normalized)) return 'good'
  return 'neutral'
}

export function describeRunDetail(run: AutopilotRunSummary, traces: AutopilotRunTrace[]) {
  if (run.error_message?.trim()) return run.error_message

  const latestTrace = [...traces]
    .sort((left, right) => safeDate(right.timestamp) - safeDate(left.timestamp))
    .find((trace) => trace.message?.trim())

  if (latestTrace?.message) return latestTrace.message

  if (['RUNNING', 'QUEUED', 'PENDING'].includes(run.status.toUpperCase())) {
    return 'The run is still active. If it stays quiet too long, assume something is stuck.'
  }

  return `Run ${humanizeRunStatus(run.status)}.`
}

export function explainAlertImpact(alert: AutopilotAlertSummary) {
  if (alert.resolved) {
    return 'The issue was resolved, which means the system recovered or someone intervened.'
  }

  if (/runtime|error|fail/i.test(alert.type) || /retry|failed|error/i.test(alert.message)) {
    return 'A live workflow is hurting. Hidden runtime failures are how trust dies.'
  }

  return 'Something triggered monitoring. Verify the runtime before letting it continue unattended.'
}

export function explainApprovalImpact(approval: AutopilotApprovalSummary) {
  if (approval.status === 'PENDING') {
    return 'This action needs a human decision before the agent crosses a risky line.'
  }

  if (approval.status === 'APPROVED') {
    return 'A human allowed this risky action, so the audit trail should justify that call.'
  }

  if (approval.status === 'REJECTED') {
    return 'A human blocked this action, which means the guardrail did its job.'
  }

  return 'This approval event changed what the agent was allowed to do.'
}

export function buildAutopilotTimeline({
  runs,
  alerts,
  approvals,
  budget,
  thresholdPercent,
  tracesByRunId,
}: {
  runs: AutopilotRunSummary[]
  alerts: AutopilotAlertSummary[]
  approvals: AutopilotApprovalSummary[]
  budget: AutopilotBudgetSummary | null
  thresholdPercent: number
  tracesByRunId: Record<string, AutopilotRunTrace[]>
}): AutopilotTimelineItem[] {
  const items: AutopilotTimelineItem[] = []

  if (budget && budget.usage_percentage >= thresholdPercent) {
    items.push({
      id: `budget-${thresholdPercent}`,
      occurredAt: new Date().toISOString(),
      title: 'Budget threshold breached',
      detail: `${formatPercent(budget.usage_percentage)} used against a ${formatPercent(thresholdPercent)} limit on the ${budget.plan} plan.`,
      impact: 'This is the line in the sand for spend. If you ignore it, cost surprises stop being surprises.',
      severity: budget.usage_percentage >= 100 ? 'critical' : 'warn',
      sourceLabel: 'Budget',
      href: '/dashboard/budgets',
    })
  }

  for (const approval of approvals) {
    items.push({
      id: `approval-${approval.id}`,
      occurredAt: approval.resolved_at ?? approval.created_at,
      title: `${approval.action_type.replace(/[_-]+/g, ' ').replace(/\b\w/g, (char) => char.toUpperCase())} ${approval.status.toLowerCase()}`,
      detail:
        typeof approval.payload?.summary === 'string' && approval.payload.summary.trim()
          ? approval.payload.summary
          : `${approval.requester} requested a risky action for ${approval.agent_id}.`,
      impact: explainApprovalImpact(approval),
      severity: approval.status === 'REJECTED' ? 'good' : approval.status === 'PENDING' ? 'warn' : 'neutral',
      sourceLabel: 'Approval',
      href: '/dashboard/approvals',
    })
  }

  for (const alert of alerts) {
    items.push({
      id: `alert-${alert.id}`,
      occurredAt: alert.resolved_at ?? alert.created_at,
      title: `${alert.type.replace(/[_-]+/g, ' ').replace(/\b\w/g, (char) => char.toUpperCase())} ${alert.resolved ? 'resolved' : 'triggered'}`,
      detail: alert.message,
      impact: explainAlertImpact(alert),
      severity: alert.resolved ? 'good' : 'critical',
      sourceLabel: 'Alert',
      href: '/dashboard/monitoring',
    })
  }

  for (const run of runs) {
    items.push({
      id: `run-${run.id}`,
      occurredAt: chooseRunTime(run),
      title: `${['FAILED', 'ERROR', 'CANCELLED'].includes(run.status.toUpperCase()) ? 'Failed run' : humanizeRunStatus(run.status)} ${run.id.slice(0, 8)}`,
      detail: describeRunDetail(run, tracesByRunId[run.id] ?? []),
      impact:
        getRunSeverity(run.status) === 'critical'
          ? 'A surprising failure landed in the execution path. Either explain it or stop pretending the runtime is trustworthy.'
          : getRunSeverity(run.status) === 'warn'
            ? 'The work is still in motion. Long silence here can mean a stuck runtime.'
            : 'The run completed. Now verify the output was actually useful.',
      severity: getRunSeverity(run.status),
      sourceLabel: 'Run',
      href: '/dashboard/runs',
    })
  }

  return items.sort((left, right) => safeDate(right.occurredAt) - safeDate(left.occurredAt))
}
