import { readFileSync } from 'node:fs'
import { join } from 'node:path'

import { ApiRequestError } from '../../components/app/http'
import {
  dashboardRequestErrorMessage,
  getDashboardRequestAccessFailure,
} from '../../components/dashboard/dashboardRequestAccess'
import {
  HIDDEN_ACTIVITY_POLL_MS,
  VISIBLE_ACTIVITY_POLL_MS,
  getActivityPollDelay,
  hasNonterminalRunActivity,
} from '../../components/dashboard/useAdaptiveActivityPolling'

function readSource(relativePath: string) {
  return readFileSync(join(process.cwd(), relativePath), 'utf8')
}

describe('dashboard auth and continuity contracts', () => {
  it('reserves authentication recovery for 401 and classifies 403 as permission denial', () => {
    const unauthorized = new ApiRequestError('Session expired', 401)
    const forbidden = new ApiRequestError('ADMIN role required', 403)

    expect(getDashboardRequestAccessFailure(unauthorized)).toBe('authentication')
    expect(getDashboardRequestAccessFailure(forbidden)).toBe('permission')
    expect(dashboardRequestErrorMessage(forbidden, 'Request failed')).toBe(
      'Permission denied: ADMIN role required',
    )
  })

  it('renders permission-specific states across the owned live-data surfaces', () => {
    const permissionAwareSurfaces = [
      'app/dashboard/agents/[agentId]/page.tsx',
      'app/dashboard/deployments/[id]/page.tsx',
      'components/dashboard/AgentsListClient.tsx',
      'components/dashboard/AnalyticsPageClient.tsx',
      'components/dashboard/ApiKeysPageClient.tsx',
      'components/dashboard/AutonomyPageClient.tsx',
      'components/dashboard/BudgetsPageClient.tsx',
      'components/dashboard/ChannelsPageClient.tsx',
      'components/dashboard/DashboardAuthBoundary.tsx',
      'components/dashboard/DocumentsPageClient.tsx',
      'components/dashboard/LogsPageClient.tsx',
      'components/dashboard/MemoryPageClient.tsx',
      'components/dashboard/MonitoringPageClient.tsx',
      'components/dashboard/ObservabilityPageClient.tsx',
      'components/dashboard/OrchestrationPageClient.tsx',
      'components/dashboard/ReasoningPageClient.tsx',
      'components/dashboard/RunsPageClient.tsx',
      'components/dashboard/SecurityPageClient.tsx',
      'components/dashboard/SessionsPageClient.tsx',
      'components/dashboard/SkillsPageClient.tsx',
      'components/dashboard/SwarmsPageClient.tsx',
      'components/dashboard/TemplateCatalogPageClient.tsx',
      'components/dashboard/TracesPageClient.tsx',
      'components/dashboard/control/OpenclawSetupSurface.tsx',
    ]

    for (const relativePath of permissionAwareSurfaces) {
      const source = readSource(relativePath)
      expect(source).toContain('LiveForbidden')
      expect(source).not.toMatch(/status\s*===\s*401\s*\|\|[^\n]*status\s*===\s*403/)
    }

    for (const relativePath of [
      'components/dashboard/ApprovalsPageClient.tsx',
      'components/dashboard/AuditPageClient.tsx',
    ]) {
      const source = readSource(relativePath)
      expect(source).toContain('viewState === "forbidden"')
      expect(source).toContain('role="alert"')
    }
  })

  it('polls nonterminal activity adaptively and pauses without activity or connectivity', () => {
    expect(
      getActivityPollDelay({ active: true, online: true, visibilityState: 'visible' }),
    ).toBe(VISIBLE_ACTIVITY_POLL_MS)
    expect(
      getActivityPollDelay({ active: true, online: true, visibilityState: 'hidden' }),
    ).toBe(HIDDEN_ACTIVITY_POLL_MS)
    expect(
      getActivityPollDelay({ active: true, online: false, visibilityState: 'visible' }),
    ).toBeNull()
    expect(
      getActivityPollDelay({ active: false, online: true, visibilityState: 'visible' }),
    ).toBeNull()

    expect(hasNonterminalRunActivity([{ status: 'running', completed_at: null }])).toBe(true)
    expect(hasNonterminalRunActivity([{ status: 'queued', completed_at: null }])).toBe(true)
    expect(hasNonterminalRunActivity([{ status: 'completed', completed_at: null }])).toBe(false)
    expect(
      hasNonterminalRunActivity([
        { status: 'running', completed_at: '2026-07-28T10:00:00.000Z' },
        { status: 'failed', completed_at: null },
      ]),
    ).toBe(false)
  })

  it('keeps run snapshots honest and cleans up polling and requests', () => {
    const runs = readSource('components/dashboard/RunsPageClient.tsx')
    const logs = readSource('components/dashboard/LogsPageClient.tsx')
    const polling = readSource('components/dashboard/useAdaptiveActivityPolling.ts')

    for (const source of [runs, logs]) {
      expect(source).toContain('useAdaptiveActivityPolling')
      expect(source).toContain('Last updated')
      expect(source).toContain('Refresh now')
      expect(source).toContain('.abort()')
      expect(source).toContain('LiveForbidden')
      expect(source).not.toMatch(/401\s*\|\|[^\n]*403/)
    }
    expect(logs).toContain('Run log snapshot')
    expect(logs).not.toContain('Run log stream')
    expect(polling).toContain("window.addEventListener('online'")
    expect(polling).toContain("window.addEventListener('offline'")
    expect(polling).toContain("document.addEventListener('visibilitychange'")
    expect(polling).toContain("window.removeEventListener('online'")
    expect(polling).toContain("document.removeEventListener('visibilitychange'")
    expect(polling).toContain('window.clearTimeout(timeoutId)')
  })

  it('uses web mission-control identity and preserves native desktop identity', () => {
    const shell = readSource('components/dashboard/DashboardShell.tsx')

    expect(shell).toContain('const webCurrentUser = useMissionControl((state) => state.currentUser)')
    expect(shell).toContain('isDesktop ? status.user?.email : webCurrentUser?.email')
    expect(shell).not.toContain('status.user?.email || "Sign in to load workspace data"')
  })

  it('announces async failures and exposes the control demo as searchbox plus results region', () => {
    const primitives = readSource('components/dashboard/livePrimitives.tsx')
    const analytics = readSource('components/dashboard/AnalyticsPageClient.tsx')
    const observability = readSource('components/dashboard/ObservabilityPageClient.tsx')
    const search = readSource('components/dashboard/demo/demoPrimitives.tsx')

    expect(primitives).toContain('export function LiveForbidden')
    expect(primitives).toContain('aria-live="assertive"')
    expect(analytics).toContain('aria-live={error ? "assertive" : undefined}')
    expect(observability.match(/aria-live="assertive"/g)).toHaveLength(2)
    expect(search).toContain('role="searchbox"')
    expect(search).toContain('role="region"')
    expect(search).toContain('aria-labelledby={resultsLabelId}')
    expect(search).not.toContain('role="combobox"')
  })
})
