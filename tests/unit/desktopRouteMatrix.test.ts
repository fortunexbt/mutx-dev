import {
  DASHBOARD_ROUTE_PATHS,
  DESKTOP_ROUTE_META,
  DESKTOP_ROUTE_ORDER,
  PRIMARY_DESKTOP_ROUTE_ORDER,
  STABLE_DESKTOP_ROUTE_ORDER,
  getDesktopRouteKeyForPath,
  getDesktopRouteSurface,
  getDesktopWindowRoleForPath,
  getDesktopWorkspacePaneForPath,
  isDesktopRoutePathActive,
} from '../../components/desktop/desktopRouteConfig'

describe('desktop route matrix', () => {
  it('derives route order and paths from the canonical registry', () => {
    expect(DESKTOP_ROUTE_ORDER).toEqual(expect.arrayContaining(Object.keys(DESKTOP_ROUTE_META)))
    expect(DESKTOP_ROUTE_ORDER).toHaveLength(Object.keys(DESKTOP_ROUTE_META).length)
    expect(new Set(DESKTOP_ROUTE_ORDER).size).toBe(DESKTOP_ROUTE_ORDER.length)
    expect(new Set(Object.values(DASHBOARD_ROUTE_PATHS)).size).toBe(DESKTOP_ROUTE_ORDER.length)

    for (const key of DESKTOP_ROUTE_ORDER) {
      expect(DESKTOP_ROUTE_META[key].key).toBe(key)
      expect(DASHBOARD_ROUTE_PATHS[key]).toBe(DESKTOP_ROUTE_META[key].path)
    }
  })

  it.each(STABLE_DESKTOP_ROUTE_ORDER)(
    'gives stable route %s an active route and a valid desktop rendering contract',
    (key) => {
      const meta = DESKTOP_ROUTE_META[key]
      const surface = getDesktopRouteSurface(key)
      const hasRenderingOrFallback =
        surface === 'native' || surface === 'settings' || Boolean(meta.publicHref)

      expect(hasRenderingOrFallback).toBe(true)
      expect(getDesktopRouteKeyForPath(meta.path)).toBe(key)
      expect(getDesktopRouteKeyForPath(`${meta.path}/`)).toBe(key)
      expect(isDesktopRoutePathActive(`${meta.path}/?source=desktop`, key)).toBe(true)

      if (key !== 'home') {
        expect(getDesktopRouteKeyForPath(`${meta.path}/detail-id`)).toBe(key)
        expect(isDesktopRoutePathActive(`${meta.path}/detail-id`, key)).toBe(true)
      }
    },
  )

  it('publishes every implemented surface and hides only compatibility redirects', () => {
    const redirects = DESKTOP_ROUTE_ORDER.filter(
      (key) => DESKTOP_ROUTE_META[key].stage === 'redirect',
    )
    const previews = DESKTOP_ROUTE_ORDER.filter(
      (key) => DESKTOP_ROUTE_META[key].stage === 'preview',
    )

    expect(redirects).toEqual(['spawn'])
    expect(previews).toEqual([])
    expect(PRIMARY_DESKTOP_ROUTE_ORDER).toEqual(
      DESKTOP_ROUTE_ORDER.filter((key) => !redirects.includes(key)),
    )
  })

  it('uses shared browser content for stable workflow routes and native telemetry content', () => {
    expect(getDesktopRouteSurface('documents')).toBe('shared')
    expect(getDesktopRouteSurface('reasoning')).toBe('shared')
    expect(getDesktopRouteSurface('approvals')).toBe('shared')
    expect(getDesktopRouteSurface('audit')).toBe('shared')
    expect(getDesktopRouteSurface('observability')).toBe('native')
    expect(DESKTOP_ROUTE_META.documents.publicHref).toBe('/dashboard/documents')
    expect(DESKTOP_ROUTE_META.reasoning.publicHref).toBe('/dashboard/reasoning')
    expect(DESKTOP_ROUTE_META.approvals.publicHref).toBe('/dashboard/approvals')
    expect(DESKTOP_ROUTE_META.audit.publicHref).toBe('/dashboard/audit')
    expect(getDesktopRouteSurface('history')).toBe('shared')
    expect(DESKTOP_ROUTE_META.history.stage).toBe('stable')
  })

  it('keeps nested agent and deployment details in the correct workspace context', () => {
    expect(getDesktopRouteKeyForPath('/dashboard/agents/agent_alpha')).toBe('agents')
    expect(getDesktopWorkspacePaneForPath('/dashboard/agents/agent_alpha')).toBe('fleet')
    expect(getDesktopWindowRoleForPath('/dashboard/agents/agent_alpha')).toBe('workspace')

    expect(getDesktopRouteKeyForPath('/dashboard/deployments/deploy_alpha')).toBe('deployments')
    expect(getDesktopWorkspacePaneForPath('/dashboard/deployments/deploy_alpha')).toBe('rollouts')
    expect(getDesktopWindowRoleForPath('/dashboard/deployments/deploy_alpha')).toBe('workspace')
  })

  it('keeps canonical operator nouns attached to their routes', () => {
    const nounKeys = [
      'home',
      'agents',
      'deployments',
      'documents',
      'reasoning',
      'observability',
    ] as const

    expect(
      Object.fromEntries(
        nounKeys.map((key) => [
          DESKTOP_ROUTE_META[key].path,
          DESKTOP_ROUTE_META[key].title,
        ]),
      ),
    ).toEqual({
      '/dashboard': 'Overview',
      '/dashboard/agents': 'Agents',
      '/dashboard/deployments': 'Deployments',
      '/dashboard/documents': 'Documents',
      '/dashboard/reasoning': 'Reasoning',
      '/dashboard/observability': 'Observability',
    })
  })
})
