import { existsSync } from 'node:fs'
import { join } from 'node:path'

import {
  ALL_DASHBOARD_NAV_ITEMS,
  DASHBOARD_NAV_GROUPS,
  DASHBOARD_NAV_ITEMS,
  getDashboardNavHref,
  getDashboardNavPanel,
  isDashboardNavItemActive,
} from '../../components/dashboard/dashboardNav'
import {
  DASHBOARD_ROUTE_PATHS,
  PRIMARY_DESKTOP_ROUTE_ORDER,
} from '../../components/desktop/desktopRouteConfig'

describe('dashboard navigation helpers', () => {
  const homeItem = DASHBOARD_NAV_ITEMS.find((item) => item.key === 'home')!
  const agentsItem = DASHBOARD_NAV_ITEMS.find((item) => item.key === 'agents')!
  const sessionsItem = DASHBOARD_NAV_ITEMS.find((item) => item.key === 'sessions')!

  it('keeps primary dashboard nav items in desktop route order', () => {
    expect(DASHBOARD_NAV_ITEMS.map((item) => item.key)).toEqual(PRIMARY_DESKTOP_ROUTE_ORDER)
    expect(ALL_DASHBOARD_NAV_ITEMS).toEqual(
      expect.arrayContaining(DASHBOARD_NAV_ITEMS),
    )
  })

  it('uses internal hrefs for dashboard and app shells', () => {
    expect(getDashboardNavHref('/dashboard', sessionsItem)).toBe('/dashboard/sessions')
    expect(getDashboardNavHref('/app/runtime', sessionsItem)).toBe('/dashboard/sessions')
  })

  it('uses safe dashboard hrefs outside the dashboard shells', () => {
    expect(getDashboardNavHref('/pricing', agentsItem)).toBe('/dashboard/agents')
  })

  it('limits browser navigation to the explicit real dashboard route contract', () => {
    const dashboardRoutePaths = Object.values(DASHBOARD_ROUTE_PATHS)

    for (const item of ALL_DASHBOARD_NAV_ITEMS) {
      expect(item.href).toBe(DASHBOARD_ROUTE_PATHS[item.key])
      expect(item.publicHref).toBe(item.href)
      expect(dashboardRoutePaths).toContain(item.publicHref)
      expect(item.publicHref).toMatch(/^\/dashboard(?:\/|$)/)
      expect(existsSync(join(process.cwd(), 'app', item.href.slice(1), 'page.tsx'))).toBe(true)
    }
  })

  it('leaves unavailable browser routes unlinked without disabling internal navigation', () => {
    const unavailableAgentsItem = { ...agentsItem, publicHref: null }

    expect(getDashboardNavHref('/pricing', unavailableAgentsItem)).toBeNull()
    expect(getDashboardNavHref('/dashboard', unavailableAgentsItem)).toBe('/dashboard/agents')
  })

  it('maps route metadata keys onto canonical SPA panel identifiers', () => {
    expect(getDashboardNavPanel('home')).toBe('overview')
    expect(getDashboardNavPanel('apiKeys')).toBe('api-keys')
    expect(getDashboardNavPanel('budgets')).toBe('cost-tracker')
    expect(getDashboardNavPanel('analytics')).toBe('tokens')
    expect(getDashboardNavPanel('deployments')).toBe('deployments')
  })

  it('treats overview aliases as active for the home nav item', () => {
    expect(isDashboardNavItemActive('/', homeItem)).toBe(true)
    expect(isDashboardNavItemActive('/dashboard', homeItem)).toBe(true)
    expect(isDashboardNavItemActive('/overview', homeItem)).toBe(true)
    expect(isDashboardNavItemActive('/dashboard/agents', homeItem)).toBe(false)
  })

  it('treats nested route paths as active and ignores trailing slashes', () => {
    expect(isDashboardNavItemActive('/dashboard/agents/', agentsItem)).toBe(true)
    expect(isDashboardNavItemActive('/dashboard/agents/launch', agentsItem)).toBe(true)
    expect(isDashboardNavItemActive('/agents/launch', agentsItem)).toBe(false)
    expect(isDashboardNavItemActive('/dashboard/api-keys', agentsItem)).toBe(false)
  })

  it('uses canonical operator nouns for browser and desktop navigation', () => {
    const titles = Object.fromEntries(
      ALL_DASHBOARD_NAV_ITEMS.map((item) => [item.key, item.title]),
    )

    expect(titles).toMatchObject({
      home: 'Overview',
      agents: 'Agents',
      deployments: 'Deployments',
      runs: 'Runs',
      sessions: 'Sessions',
      observability: 'Observability',
      apiKeys: 'API Keys',
      budgets: 'Usage',
      webhooks: 'Connectors',
      security: 'Access',
      control: 'Settings',
      analytics: 'Analytics',
    })
  })

  it('groups every primary nav item exactly once', () => {
    const groupedKeys = DASHBOARD_NAV_GROUPS.flatMap((group) => group.items.map((item) => item.key))

    expect(groupedKeys).toEqual(DASHBOARD_NAV_ITEMS.map((item) => item.key))
  })
})
