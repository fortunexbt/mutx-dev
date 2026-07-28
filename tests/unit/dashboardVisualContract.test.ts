import { readFileSync } from 'node:fs'
import { join } from 'node:path'

function source(relativePath: string) {
  return readFileSync(join(process.cwd(), relativePath), 'utf8')
}

const LIVE_ROUTE_WRAPPERS = [
  'app/dashboard/page.tsx',
  'app/dashboard/agents/page.tsx',
  'app/dashboard/agents/[agentId]/page.tsx',
  'app/dashboard/analytics/page.tsx',
  'app/dashboard/api-keys/page.tsx',
  'app/dashboard/approvals/page.tsx',
  'app/dashboard/audit/page.tsx',
  'app/dashboard/autonomy/page.tsx',
  'app/dashboard/budgets/page.tsx',
  'app/dashboard/channels/page.tsx',
  'app/dashboard/deployments/page.tsx',
  'app/dashboard/deployments/[id]/page.tsx',
  'app/dashboard/documents/page.tsx',
  'app/dashboard/history/page.tsx',
  'app/dashboard/logs/page.tsx',
  'app/dashboard/memory/page.tsx',
  'app/dashboard/monitoring/page.tsx',
  'app/dashboard/notifications/page.tsx',
  'app/dashboard/observability/page.tsx',
  'app/dashboard/orchestration/page.tsx',
  'app/dashboard/reasoning/page.tsx',
  'app/dashboard/runs/page.tsx',
  'app/dashboard/security/page.tsx',
  'app/dashboard/sessions/page.tsx',
  'app/dashboard/skills/page.tsx',
  'app/dashboard/standup/page.tsx',
  'app/dashboard/swarm/page.tsx',
  'app/dashboard/templates/page.tsx',
  'app/dashboard/traces/page.tsx',
  'app/dashboard/webhooks/page.tsx',
]

describe('dashboard flight-recorder visual contract', () => {
  it('installs one scoped contract at the live browser shell', () => {
    const shell = source('components/dashboard/DashboardShell.tsx')

    expect(shell).toContain('dashboardVisualContract.module.css')
    expect(shell).toContain('visualContract.visualContract')
    expect(shell).toContain('data-dashboard-theme="flight-recorder"')
    expect(shell).toContain('SYS {String(activeRecord)')
  })

  it('exposes the canonical live-route primitive grammar', () => {
    const primitives = source('components/dashboard/livePrimitives.tsx')

    for (const primitive of [
      'Surface',
      'Panel',
      'RecordRow',
      'Action',
      'Field',
      'Badge',
      'Notice',
    ]) {
      expect(primitives).toContain(`export function ${primitive}`)
    }

    expect(primitives).toContain('DashboardDialog as Dialog')
    expect(primitives).toContain('LiveEmptyState as Empty')
    expect(primitives).toContain('LiveErrorState as Error')
    expect(primitives).toContain('LiveLoading as Loading')
    expect(primitives).not.toMatch(/>\s*REC\s*</)
  })

  it('keeps every browser operator route on the shared RouteHeader hierarchy', () => {
    for (const route of LIVE_ROUTE_WRAPPERS) {
      expect(source(route)).toContain('RouteHeader')
    }

    const routeHeader = source('components/dashboard/RouteHeader.tsx')
    expect(routeHeader).toContain('data-dashboard-ui="route-header"')
    expect(routeHeader).toContain('text-[11px]')
    expect(routeHeader).toContain('REC /')
  })

  it('locks responsive geometry, touch, focus, overflow, and reduced motion rules', () => {
    const contract = source('components/dashboard/dashboardVisualContract.module.css')

    expect(contract).toContain('--dashboard-contract-radius-action: 4px')
    expect(contract).toContain('--dashboard-contract-radius-panel: 6px')
    expect(contract).toContain('--dashboard-contract-radius-dialog: 8px')
    expect(contract).toContain('min-height: 44px')
    expect(contract).toContain('var(--mutx-dashboard-trace)')
    expect(contract).toContain('overflow-x: auto')
    expect(contract).toContain('@container (max-width: 360px)')
    expect(contract).toContain('@media (prefers-reduced-motion: reduce)')
    expect(contract).toContain('transform: none !important')
    expect(contract).toContain('background-image: none !important')
    expect(contract).toContain(':where([role="alert"], [role="status"])')
  })

  it('removes the legacy Card generation from live webhook and deployment history routes', () => {
    const webhooks = source('components/webhooks/WebhooksPageClient.tsx')
    const deploymentHistory = source('components/app/DeploymentHistory.tsx')

    expect(webhooks).toContain('Surface as Card')
    expect(deploymentHistory).toContain('Surface as Card')
    expect(webhooks).not.toContain('@/components/ui/Card')
    expect(deploymentHistory).not.toContain('@/components/ui/Card')
  })

  it('retains truthful source and freshness vocabulary in the converged clients', () => {
    const clients = [
      'components/dashboard/AnalyticsPageClient.tsx',
      'components/dashboard/AutonomyPageClient.tsx',
      'components/dashboard/DocumentsPageClient.tsx',
      'components/dashboard/NotificationsPageClient.tsx',
      'components/dashboard/OrchestrationPageClient.tsx',
      'components/dashboard/TemplateCatalogPageClient.tsx',
    ].map(source).join('\n')

    expect(clients).toMatch(/stale/i)
    expect(clients).toMatch(/unavailable/i)
    expect(clients).toMatch(/local-only|local catalog/i)
    expect(source('components/dashboard/DashboardContentRouter.tsx')).toContain("value: 'Live API'")
  })

  it('keeps dashboard menus and hints keyboard and small-viewport safe', () => {
    const topBar = source('components/dashboard/TopBar.tsx')
    const kebab = source('components/dashboard/KebabMenu.tsx')
    const palette = source('components/dashboard/DashboardCommandPalette.tsx')
    const hint = source('components/dashboard/FeatureHint.tsx')

    for (const menu of [topBar, kebab]) {
      expect(menu).toContain('aria-haspopup="menu"')
      expect(menu).toContain('event.key === "ArrowDown"')
      expect(menu).toContain('event.key === "ArrowUp"')
      expect(menu).toContain('event.key === "Home"')
      expect(menu).toContain('event.key === "End"')
      expect(menu).toContain('event.key !== "Escape"')
    }

    expect(palette).toContain('event.key === "Home"')
    expect(palette).toContain('event.key === "End"')
    expect(palette).toContain('scrollIntoView({ block: "nearest" })')
    expect(hint).toContain('max-sm:w-full')
    expect(hint).toContain('sm:absolute')
    expect(hint).toContain('sm:w-[min(20rem,calc(100vw-2rem))]')
  })
})
