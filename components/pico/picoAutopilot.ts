export type AutopilotRunSummary = {
  id: string
  agent_id?: string
  status: string
  input_text?: string | null
  output_text?: string | null
  error_message?: string | null
  metadata?: Record<string, unknown>
  started_at?: string | null
  completed_at?: string | null
  created_at?: string | null
  trace_count?: number
}

export type AutopilotRunTrace = {
  id: string
  run_id: string
  event_type: string
  message: string
  payload?: Record<string, unknown>
  sequence?: number
  timestamp?: string | null
}

export type AutopilotAlertSummary = {
  id: string
  agent_id: string
  type: string
  message: string
  resolved: boolean
  created_at: string
  resolved_at?: string | null
}

export type AutopilotBudgetSummary = {
  plan: string
  credits_total: number
  credits_used: number
  credits_remaining: number
  usage_percentage: number
  reset_date?: string
}

export type AutopilotUsageByAgent = {
  agent_id: string
  agent_name: string
  credits_used: number
  event_count: number
}

export type AutopilotUsageByType = {
  event_type: string
  credits_used: number
  event_count: number
}

export type AutopilotUsageBreakdown = {
  total_credits_used: number
  credits_remaining: number
  credits_total: number
  period_start: string
  period_end: string
  usage_by_agent: AutopilotUsageByAgent[]
  usage_by_type: AutopilotUsageByType[]
}

export type AutopilotApprovalSummary = {
  id: string
  owner_id: string
  reviewer_id: string | null
  can_resolve: boolean
  agent_id: string
  session_id?: string
  action_type: string
  payload?: Record<string, unknown>
  status: string
  requester: string
  approver?: string | null
  created_at: string
  resolved_at?: string | null
}

export type AutopilotAgentSummary = {
  id: string
  name?: string | null
  status?: string | null
  deployment_status?: string | null
  updated_at?: string | null
}

export type AutopilotTimelineItem = {
  id: string
  kind: 'run' | 'alert' | 'approval' | 'budget'
  occurredAt: string | null
  title: string
  detail: string
  impact: string
  severity: 'neutral' | 'good' | 'warn' | 'critical'
  href: string
  sourceLabel: string
}

export type AutopilotIntegrationStatus = {
  hasLiveAgent: boolean
  hasRuns: boolean
  hasAlerts: boolean
  hasBudget: boolean
  hasUsage: boolean
  hasApprovalRecords: boolean
  approvalGatePreferenceEnabled: boolean
}

export type AutopilotNextStep = {
  label: string
  href: string
}

export type AutopilotEmptyState = {
  title: string
  body: string
  nextStep: AutopilotNextStep
}

function toDate(value?: string | null) {
  if (!value) return null
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? null : date
}

function fallbackTimestamp(...values: Array<string | null | undefined>): string | null {
  return values.find((value) => typeof value === 'string' && value.trim()) ?? null
}

function excerpt(value?: string | null, max = 140) {
  if (!value) return null
  const compact = value.replace(/\s+/g, ' ').trim()
  if (!compact) return null
  if (compact.length <= max) return compact
  if (max <= 3) return '.'.repeat(Math.max(0, max))
  return `${compact.slice(0, max - 3)}...`
}

function titleCase(value: string) {
  return value
    .toLowerCase()
    .split(/[_\s-]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ')
}

export type AutopilotTranslator = (
  key: string,
  values?: Record<string, string | number>,
) => string

export function formatTimestamp(
  value?: string | null,
  locale = 'en',
  unknownTime = 'Unknown time',
) {
  const date = toDate(value)
  if (!date) return unknownTime

  return new Intl.DateTimeFormat(locale, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
}

export function formatRelativeTime(
  value?: string | null,
  now = new Date(),
  locale = 'en',
  unknownTime = 'unknown time',
) {
  const date = toDate(value)
  if (!date) return unknownTime

  const diffMs = date.getTime() - now.getTime()
  const diffMinutes = Math.round(diffMs / 60000)
  const formatter = new Intl.RelativeTimeFormat(locale, { numeric: 'auto' })

  if (Math.abs(diffMinutes) < 60) {
    return formatter.format(diffMinutes, 'minute')
  }

  const diffHours = Math.round(diffMinutes / 60)
  if (Math.abs(diffHours) < 48) {
    return formatter.format(diffHours, 'hour')
  }

  const diffDays = Math.round(diffHours / 24)
  return formatter.format(diffDays, 'day')
}

export function formatPercent(value: number) {
  if (!Number.isFinite(value)) return '--'
  return `${Math.round(value)}%`
}

export function humanizeRunStatus(status: string, t?: AutopilotTranslator) {
  return t?.(`shared.statusLabels.${status.toUpperCase()}`) ?? titleCase(status)
}

export function getRunSeverity(status: string): AutopilotTimelineItem['severity'] {
  const normalized = status.toUpperCase()
  if (['FAILED', 'ERROR', 'CANCELLED'].includes(normalized)) return 'critical'
  if (['RUNNING', 'QUEUED', 'PENDING', 'AWAITING_OWNER'].includes(normalized)) return 'warn'
  if (['COMPLETED', 'SUCCEEDED', 'SUCCESS'].includes(normalized)) return 'good'
  return 'neutral'
}

export function describeRunDetail(
  run: AutopilotRunSummary,
  traces: AutopilotRunTrace[] = [],
  t?: AutopilotTranslator,
) {
  const status = run.status.toUpperCase()
  const latestTrace = traces
    .filter((trace) => typeof trace.message === 'string' && trace.message.trim())
    .reduce<AutopilotRunTrace | undefined>((latest, trace) => {
      if (!latest) return trace
      return new Date(trace.timestamp ?? 0).getTime() > new Date(latest.timestamp ?? 0).getTime() ? trace : latest
    }, undefined)

  if (['FAILED', 'ERROR', 'CANCELLED'].includes(status)) {
    return excerpt(run.error_message) ?? excerpt(latestTrace?.message) ?? t?.('shared.runDetail.failedNoMessage') ?? 'The run stopped without a stored error message.'
  }

  if (['RUNNING', 'QUEUED', 'PENDING'].includes(status)) {
    return excerpt(latestTrace?.message) ?? t?.('shared.runDetail.inFlight') ?? 'The run is still moving through the pipeline.'
  }

  if (status === 'AWAITING_OWNER') {
    return excerpt(latestTrace?.message) ?? t?.('shared.runDetail.awaitingOwner') ?? 'The run is paused — waiting for owner input before continuing.'
  }

  return excerpt(run.output_text) ?? excerpt(latestTrace?.message) ?? excerpt(run.input_text) ?? t?.('shared.runDetail.completedNoSummary') ?? 'The run completed without a short summary.'
}

export function explainRunImpact(run: AutopilotRunSummary, t?: AutopilotTranslator) {
  const status = run.status.toUpperCase()
  if (['FAILED', 'ERROR', 'CANCELLED'].includes(status)) {
    return t?.('shared.runImpact.failed') ?? 'This workflow did not finish cleanly. Check the error and traces before trusting the next attempt.'
  }

  if (['RUNNING', 'QUEUED', 'PENDING'].includes(status)) {
    return t?.('shared.runImpact.active') ?? 'Work is still in flight. Watch for hangs, retries, or silence that lasts too long.'
  }

  if (status === 'AWAITING_OWNER') {
    return t?.('shared.runImpact.awaitingOwner') ?? 'The run is paused waiting for owner action. Respond to unblock the pipeline.'
  }

  return t?.('shared.runImpact.completed') ?? 'This run completed. Verify the output is useful before you automate more of this work.'
}

export function explainAlertImpact(alert: AutopilotAlertSummary, t?: AutopilotTranslator) {
  if (alert.resolved) {
    return t?.('shared.alertImpact.resolved') ?? 'The alert is cleared, but you still want the root cause to make sense.'
  }

  return t?.('shared.alertImpact.active') ?? 'This active alert needs review before the runtime keeps running unattended.'
}

export function explainApprovalImpact(approval: AutopilotApprovalSummary, t?: AutopilotTranslator) {
  const normalized = approval.status.toUpperCase()
  if (normalized === 'PENDING') {
    return t?.('shared.approvalImpact.pending') ?? 'A risky action is waiting for a human decision. Nothing should proceed past this gate yet.'
  }

  if (normalized === 'APPROVED') {
    return t?.('shared.approvalImpact.approved') ?? 'The gate opened. Make sure the approved action actually matches the request you intended to allow.'
  }

  if (normalized === 'REJECTED') {
    return t?.('shared.approvalImpact.rejected') ?? 'The risky action was blocked. Good. Now decide whether the request was wrong or the guardrail is too strict.'
  }

  return t?.('shared.approvalImpact.changed') ?? 'This approval changed state and should be reviewed if it affects live behavior.'
}

export function analyzeAutopilotIntegration(input: {
  agents?: AutopilotAgentSummary[]
  runs: AutopilotRunSummary[]
  alerts: AutopilotAlertSummary[]
  approvals: AutopilotApprovalSummary[]
  budget: AutopilotBudgetSummary | null
  usage: AutopilotUsageBreakdown | null
  approvalGatePreferenceEnabled: boolean
}): AutopilotIntegrationStatus {
  const agents = input.agents ?? []
  const hasRuns = input.runs.length > 0
  const hasAlerts = input.alerts.length > 0
  const hasApprovalRecords = input.approvals.length > 0
  const hasBudget = Boolean(input.budget)
  const hasUsage = Boolean(
    input.usage &&
      (input.usage.total_credits_used > 0 ||
        input.usage.usage_by_agent.length > 0 ||
        input.usage.usage_by_type.length > 0)
  )
  const hasLiveAgent =
    agents.length > 0 ||
    hasRuns ||
    hasAlerts ||
    hasApprovalRecords ||
    hasBudget ||
    hasUsage

  return {
    hasLiveAgent,
    hasRuns,
    hasAlerts,
    hasBudget,
    hasUsage,
    hasApprovalRecords,
    approvalGatePreferenceEnabled: input.approvalGatePreferenceEnabled,
  }
}

export function getRunsEmptyState(status: AutopilotIntegrationStatus, nextStep: AutopilotNextStep, t?: AutopilotTranslator): AutopilotEmptyState {
  if (!status.hasLiveAgent) {
    return {
      title: t?.('emptyStates.runs.noAgent.title') ?? 'No monitored agent exists yet',
      body: t?.('emptyStates.runs.noAgent.body') ?? 'Pico has no real MUTX agent to attach to. Create or deploy one actual agent first, then come back for run history.',
      nextStep,
    }
  }

  return {
    title: t?.('emptyStates.runs.noHistory.title') ?? 'An agent exists, but nothing has run yet',
    body: t?.('emptyStates.runs.noHistory.body') ?? 'MUTX knows about at least one agent, but there is no run history yet. Trigger one real task or wait for the first schedule tick, then come back here.',
    nextStep,
  }
}

export function getAlertsEmptyState(status: AutopilotIntegrationStatus, nextStep: AutopilotNextStep, t?: AutopilotTranslator): AutopilotEmptyState {
  if (!status.hasRuns) {
    return {
      title: t?.('emptyStates.alerts.noRuns.title') ?? 'No alerts because nothing is running yet',
      body: t?.('emptyStates.alerts.noRuns.body') ?? 'An empty alert feed means nothing until the agent has executed real work. Get one run into MUTX first.',
      nextStep,
    }
  }

  return {
    title: t?.('emptyStates.alerts.none.title') ?? 'No live alerts right now',
    body: t?.('emptyStates.alerts.none.body') ?? 'Good. The monitoring feed is quiet right now. Keep watching the next real run and failure path.',
    nextStep,
  }
}

export function getUsageEmptyState(status: AutopilotIntegrationStatus, nextStep: AutopilotNextStep, t?: AutopilotTranslator): AutopilotEmptyState {
  if (!status.hasBudget) {
    return {
      title: t?.('emptyStates.usage.noBudget.title') ?? 'No live budget snapshot yet',
      body: t?.('emptyStates.usage.noBudget.body') ?? 'There is no MUTX budget snapshot to compare against yet. Until that exists, cost awareness is incomplete.',
      nextStep,
    }
  }

  return {
    title: t?.('emptyStates.usage.empty.title') ?? 'Budget exists, but usage is empty',
    body: t?.('emptyStates.usage.empty.body') ?? 'The budget page is live, but no usage events landed in the current window. Either the agent has not spent anything yet or usage emission is missing.',
    nextStep,
  }
}

export function getApprovalsEmptyState(status: AutopilotIntegrationStatus, nextStep: AutopilotNextStep, t?: AutopilotTranslator): AutopilotEmptyState {
  if (!status.hasLiveAgent) {
    return {
      title: t?.('emptyStates.approvals.noAgent.title') ?? 'No agent exists to gate yet',
      body: t?.('emptyStates.approvals.noAgent.body') ?? 'Approval queues only matter when a real agent is capable of doing something risky. Create or deploy the agent first.',
      nextStep,
    }
  }

  if (status.hasApprovalRecords) {
    return {
      title: t?.('emptyStates.approvals.gateOff.title') ?? 'Approval history exists; enforcement is unverified',
      body: t?.('emptyStates.approvals.gateOff.body') ?? 'Approval records prove the review workflow was used. They do not prove a runtime enforcement gate is active.',
      nextStep,
    }
  }

  return {
    title: t?.('emptyStates.approvals.none.title') ?? 'No approval records yet',
    body: t?.('emptyStates.approvals.none.body') ?? 'No risky action has reached the approval queue yet. Run one gated action before relying on this page for approval review.',
    nextStep,
  }
}

export function buildAutopilotTimeline(input: {
  runs: AutopilotRunSummary[]
  alerts: AutopilotAlertSummary[]
  approvals: AutopilotApprovalSummary[]
  budget: AutopilotBudgetSummary | null
  thresholdPercent: number
  tracesByRunId?: Record<string, AutopilotRunTrace[]>
  t?: AutopilotTranslator
}): AutopilotTimelineItem[] {
  const timeline: AutopilotTimelineItem[] = []
  const tracesByRunId = input.tracesByRunId ?? {}

  input.runs.forEach((run) => {
    timeline.push({
      id: `run-${run.id}`,
      kind: 'run',
      occurredAt: fallbackTimestamp(run.completed_at, run.started_at, run.created_at),
      title: input.t?.('shared.timeline.runTitle', { status: humanizeRunStatus(run.status, input.t), runId: run.id.slice(0, 8) }) ?? `${humanizeRunStatus(run.status)} run ${run.id.slice(0, 8)}`,
      detail: describeRunDetail(run, tracesByRunId[run.id] ?? [], input.t),
      impact: explainRunImpact(run, input.t),
      severity: getRunSeverity(run.status),
      href: '#recent-runs',
      sourceLabel: input.t?.('shared.timelineSources.runs') ?? 'Runs',
    })
  })

  input.alerts.forEach((alert) => {
    timeline.push({
      id: `alert-${alert.id}`,
      kind: 'alert',
      occurredAt: fallbackTimestamp(alert.resolved_at, alert.created_at),
      title: input.t?.('shared.timeline.alertTitle', { type: titleCase(alert.type), state: alert.resolved ? input.t('shared.timeline.alertResolved') : input.t('shared.timeline.alertTriggered') }) ?? `${titleCase(alert.type)} ${alert.resolved ? 'resolved' : 'triggered'}`,
      detail: excerpt(alert.message, 180) ?? input.t?.('shared.timeline.alertNoMessage') ?? 'Alert recorded without a message.',
      impact: explainAlertImpact(alert, input.t),
      severity: alert.resolved ? 'good' : 'critical',
      href: '#alerts-section',
      sourceLabel: input.t?.('shared.timelineSources.alerts') ?? 'Alerts',
    })
  })

  const getApprovalSeverity = (status: string): 'warn' | 'good' | 'critical' | 'neutral' => {
    switch (status) {
      case 'PENDING':
        return 'warn'
      case 'APPROVED':
        return 'good'
      case 'REJECTED':
        return 'critical'
      default:
        return 'neutral'
    }
  }

  input.approvals.forEach((approval) => {
    const normalized = approval.status.toUpperCase()
    const summary =
      typeof approval.payload?.summary === 'string' && approval.payload.summary.trim()
        ? approval.payload.summary
        : input.t?.('shared.timeline.approvalRequestedBy', { requester: approval.requester }) ?? `Requested by ${approval.requester}.`

    timeline.push({
      id: `approval-${approval.id}`,
      kind: 'approval',
      occurredAt: fallbackTimestamp(approval.resolved_at, approval.created_at),
      title: input.t?.('shared.timeline.approvalTitle', { action: titleCase(approval.action_type), status: input.t(`shared.timeline.approvalStatus.${normalized.toLowerCase()}`) }) ?? `${titleCase(approval.action_type)} ${normalized.toLowerCase()}`,
      detail: excerpt(summary, 180) ?? input.t?.('shared.timeline.approvalRequestedBy', { requester: approval.requester }) ?? `Requested by ${approval.requester}.`,
      impact: explainApprovalImpact(approval, input.t),
      severity: getApprovalSeverity(normalized),
      href: '#approvals-section',
      sourceLabel: input.t?.('shared.timelineSources.approvals') ?? 'Approvals',
    })
  })

  return timeline.sort((left, right) => {
    const rightTime = toDate(right.occurredAt)?.getTime() ?? 0
    const leftTime = toDate(left.occurredAt)?.getTime() ?? 0
    return rightTime - leftTime
  })
}
