import {
  ESSENTIAL_PANELS,
  canonicalizeDashboardNextPath,
  isPanelAccessibleInMode,
  matchDashboardPanelPath,
  panelHref,
  resolveDashboardPanel,
  shouldUseDashboardSpaPanelHost,
} from '../../lib/dashboardPanels'

describe('dashboard panel routing helpers', () => {
  it('resolves mission control panel ids from dashboard paths and aliases', () => {
    expect(resolveDashboardPanel('/dashboard')).toBe('overview')
    expect(resolveDashboardPanel('/dashboard/sessions')).toBe('chat')
    expect(resolveDashboardPanel('/dashboard/chat')).toBe('chat')
    expect(resolveDashboardPanel('/dashboard/orchestration')).toBe('tasks')
    expect(resolveDashboardPanel('/dashboard/tasks')).toBe('tasks')
    expect(resolveDashboardPanel('/dashboard/analytics')).toBe('tokens')
    expect(resolveDashboardPanel('/dashboard/control')).toBe('settings')
    expect(resolveDashboardPanel('/dashboard/history')).toBe('activity')
    expect(resolveDashboardPanel('/dashboard/autonomy')).toBe('cron')
    expect(resolveDashboardPanel('/dashboard/notifications')).toBe('notifications')
    expect(resolveDashboardPanel('/dashboard/standup')).toBe('standup')
    expect(resolveDashboardPanel('/dashboard/approvals')).toBe('approvals')
    expect(resolveDashboardPanel('/dashboard/audit')).toBe('audit')
  })

  it('distinguishes real panel routes from typos and nested unknown paths', () => {
    expect(matchDashboardPanelPath('/dashboard/chat')).toBe('chat')
    expect(matchDashboardPanelPath('/dashboard/does-not-exist')).toBeNull()
    expect(matchDashboardPanelPath('/dashboard/agents/does-not-exist')).toBeNull()
    expect(matchDashboardPanelPath('/control/agents')).toBeNull()
  })

  it('only lets the SPA host replace canonical panel routes, preserving nested detail children', () => {
    expect(shouldUseDashboardSpaPanelHost('/dashboard/agents')).toBe(true)
    expect(shouldUseDashboardSpaPanelHost('/dashboard/deployments')).toBe(true)
    expect(shouldUseDashboardSpaPanelHost('/dashboard/agents/agent_42')).toBe(false)
    expect(shouldUseDashboardSpaPanelHost('/dashboard/deployments/deploy_42')).toBe(false)
    expect(shouldUseDashboardSpaPanelHost('/dashboard/does-not-exist')).toBe(false)
  })

  it('canonicalizes safe dashboard aliases with search state without allowing redirects', () => {
    expect(canonicalizeDashboardNextPath('/agents?status=running&owner=me')).toBe(
      '/dashboard/agents?status=running&owner=me',
    )
    expect(canonicalizeDashboardNextPath('/app/deployments?region=eu')).toBe(
      '/dashboard/deployments?region=eu',
    )
    expect(canonicalizeDashboardNextPath('/dashboard/agents/agent_42?tab=logs')).toBe(
      '/dashboard/agents/agent_42?tab=logs',
    )
    expect(canonicalizeDashboardNextPath('https://evil.example/dashboard')).toBe('/dashboard')
    expect(canonicalizeDashboardNextPath('//evil.example/dashboard')).toBe('/dashboard')
    expect(canonicalizeDashboardNextPath('/\\evil.example/dashboard')).toBe('/dashboard')
    expect(canonicalizeDashboardNextPath('/login?next=https://evil.example')).toBe('/dashboard')
  })

  it('maps panel ids to the existing MUTX routes instead of inventing new namespaces', () => {
    expect(panelHref('chat')).toBe('/dashboard/sessions')
    expect(panelHref('tasks')).toBe('/dashboard/orchestration')
    expect(panelHref('tokens')).toBe('/dashboard/analytics')
    expect(panelHref('settings')).toBe('/dashboard/control')
    expect(panelHref('cron')).toBe('/dashboard/autonomy')
    expect(panelHref('notifications')).toBe('/dashboard/notifications')
    expect(panelHref('approvals')).toBe('/dashboard/approvals')
    expect(panelHref('audit')).toBe('/dashboard/audit')
  })

  it('gates non-essential panels when the shell is reduced to essential mode', () => {
    expect(ESSENTIAL_PANELS.has('overview')).toBe(true)
    expect(ESSENTIAL_PANELS.has('chat')).toBe(true)
    expect(ESSENTIAL_PANELS.has('approvals')).toBe(true)
    expect(ESSENTIAL_PANELS.has('security')).toBe(false)
    expect(isPanelAccessibleInMode('chat', 'essential')).toBe(true)
    expect(isPanelAccessibleInMode('security', 'essential')).toBe(false)
    expect(isPanelAccessibleInMode('security', 'full')).toBe(true)
  })
})
