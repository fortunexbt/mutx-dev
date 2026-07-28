import { readFileSync } from 'node:fs'
import { join } from 'node:path'

import {
  buildDesktopRouteHref,
  navigateCurrentDesktopRoute,
} from '@/components/desktop/desktopRouteNavigation'
import {
  DESKTOP_ROUTE_META,
  getDesktopRouteSurface,
  type DesktopRouteKey,
} from '@/components/desktop/desktopRouteConfig'
import { getNextDesktopTabIndex } from '@/components/desktop/desktopTabNavigation'
import type { DesktopWindowPayload } from '@/components/desktop/types'

function readSource(relativePath: string) {
  return readFileSync(join(process.cwd(), relativePath), 'utf8')
}

describe('desktop canonical route navigation', () => {
  it.each([
    { key: 'agents', page: 'app/dashboard/agents/page.tsx', payload: { agentId: 'agent_alpha' } },
    { key: 'documents', page: 'app/dashboard/documents/page.tsx', payload: { runId: 'run_alpha' } },
  ] satisfies Array<{
    key: DesktopRouteKey
    page: string
    payload: DesktopWindowPayload
  }>)('pushes the $key destination through Next so its route boundary renders', ({ key, page, payload }) => {
    const push = jest.fn()
    const route = DESKTOP_ROUTE_META[key].path

    const href = navigateCurrentDesktopRoute(push, route, payload)

    expect(push).toHaveBeenCalledTimes(1)
    expect(push).toHaveBeenCalledWith(href)
    expect(href).toBe(buildDesktopRouteHref(route, payload))
    expect(href).toMatch(new RegExp(`^${route}\\?`))
    expect(readSource(page)).toMatch(new RegExp(`routeKey=["']${key}["']`))
  })

  it('covers both native and shared rendered destination contracts', () => {
    expect(getDesktopRouteSurface('agents')).toBe('native')
    expect(getDesktopRouteSurface('documents')).toBe('shared')

    const boundary = readSource('components/desktop/DesktopRouteBoundary.tsx')
    expect(boundary).toContain('<DesktopNativeRoutePage routeKey={routeKey} />')
    expect(boundary).toContain('browserView ?? <AccessibleBrowserFallback')
    expect(boundary).not.toContain('effectiveRouteKey')
  })

  it('routes every renderer-owned current-window destination through the shared Next helper', () => {
    const shell = readSource('components/desktop/DesktopWindowShell.tsx')
    const nativeRoute = readSource('components/desktop/DesktopNativeRoutePage.tsx')
    const cockpit = readSource('components/desktop/DesktopOperatorCockpit.tsx')
    const windowManager = readSource('desktop/main/windowManager.cjs')

    expect(shell).toContain('navigateCurrentRoute(item.href')
    expect(shell).toContain('navigateCurrentRoute(nextRoute')
    expect(shell).not.toContain('updateCurrentWindow')
    expect(nativeRoute).toMatch(
      /if \(currentWindow\.currentRole === "workspace"\) \{\s+navigateCurrentRoute\(href, nextPayload\)/,
    )
    expect(cockpit).toContain('navigateCurrentRoute(route, nextPayload)')
    expect(cockpit).not.toContain('updateCurrentWindow')
    expect(windowManager).toMatch(
      /action\.type === "navigate\.current"[\s\S]{0,320}updateCurrentWindowState\([\s\S]{0,320}webContents\.send\([\s\S]{0,180}buildRendererRoute/,
    )
    expect(windowManager).toMatch(
      /if \(existing\) \{[\s\S]{0,220}route: nextRoute,[\s\S]{0,120}payload: nextPayload,[\s\S]{0,500}webContents\.send\([\s\S]{0,120}buildRendererRoute/,
    )
  })
})

describe('desktop scoped tab keyboard navigation', () => {
  it('moves trace tabs in visual order for LTR and RTL without losing Home/End behavior', () => {
    expect(getNextDesktopTabIndex('ArrowRight', 0, 3, false)).toBe(1)
    expect(getNextDesktopTabIndex('ArrowLeft', 0, 3, false)).toBe(2)
    expect(getNextDesktopTabIndex('ArrowRight', 0, 3, true)).toBe(2)
    expect(getNextDesktopTabIndex('ArrowLeft', 0, 3, true)).toBe(1)
    expect(getNextDesktopTabIndex('Home', 2, 3, true)).toBe(0)
    expect(getNextDesktopTabIndex('End', 0, 3, false)).toBe(2)
  })

  it('keeps arrow handling on the trace tablist instead of the global shortcut listener', () => {
    const shell = readSource('components/desktop/DesktopWindowShell.tsx')
    const globalShortcutHandler = shell.match(
      /useEffect\(\(\) => \{\s+const handleKeyDown[\s\S]*?\}, \[paletteOpen\]\);/,
    )?.[0]

    expect(globalShortcutHandler).toBeDefined()
    expect(globalShortcutHandler).not.toMatch(/ArrowLeft|ArrowRight/)
    expect(shell).toContain('onKeyDown={handleTraceTabKeyDown}')
    expect(shell).not.toContain('window.addEventListener("keydown", handleTraceTabKeyDown)')
  })
})
