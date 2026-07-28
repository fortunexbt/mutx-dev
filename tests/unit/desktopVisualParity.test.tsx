import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'

import { dashboardTokens } from '../../components/dashboard/tokens'
import { DesktopJobNotice } from '../../components/desktop/DesktopJobNotice'
import {
  DESKTOP_VISUAL_CONTRACT,
  getDesktopFreshnessPresentation,
  getDesktopStateTone,
} from '../../components/desktop/desktopVisualContract'

const presentationFiles = [
  'components/desktop/BrowserDashboardRedirect.tsx',
  'components/desktop/DesktopJobNotice.tsx',
  'components/desktop/DesktopNativeRoutePage.tsx',
  'components/desktop/DesktopOperatorCockpit.tsx',
  'components/desktop/DesktopRouteBoundary.tsx',
  'components/desktop/DesktopSettingsWindow.tsx',
  'components/desktop/DesktopStatusRow.tsx',
  'components/desktop/DesktopWindowShell.tsx',
] as const

function readSource(relativePath: string) {
  return readFileSync(join(process.cwd(), relativePath), 'utf8')
}

describe('desktop visual parity contract', () => {
  it('aliases the canonical dashboard palette and MUTX typography', () => {
    expect(DESKTOP_VISUAL_CONTRACT.palette).toMatchObject({
      canvas: dashboardTokens.bgCanvas,
      surface: dashboardTokens.bgSurface,
      inset: dashboardTokens.bgInset,
      bone: dashboardTokens.textPrimary,
      signal: dashboardTokens.brand,
      signalStrong: dashboardTokens.brandStrong,
      trace: dashboardTokens.trace,
      success: dashboardTokens.success,
      warning: dashboardTokens.warn,
      danger: dashboardTokens.danger,
    })
    expect(DESKTOP_VISUAL_CONTRACT.typography).toEqual({
      body: dashboardTokens.fontSans,
      display: 'var(--font-site-display, var(--font-display))',
      data: dashboardTokens.fontMono,
    })
  })

  it('keeps panel geometry on the 0/4/6/8px system', () => {
    expect(DESKTOP_VISUAL_CONTRACT.geometry).toEqual({
      square: 0,
      control: 4,
      panel: 6,
      dialog: 8,
      compactStatus: 9999,
    })

    for (const path of presentationFiles) {
      const radii = [...readSource(path).matchAll(/rounded-\[(\d+)px\]/g)].map((match) =>
        Number(match[1]),
      )
      expect(radii.every((radius) => [4, 6, 8].includes(radius))).toBe(true)
    }
  })

  it('keeps source freshness and lifecycle state truthful', () => {
    expect(getDesktopFreshnessPresentation('fresh')).toEqual({ label: 'Live', tone: 'success' })
    expect(getDesktopFreshnessPresentation('checking')).toEqual({
      label: 'Checking',
      tone: 'running',
    })
    expect(getDesktopFreshnessPresentation('stale')).toEqual({
      label: 'Stale',
      tone: 'warning',
    })
    expect(getDesktopFreshnessPresentation('unavailable')).toEqual({
      label: 'Unavailable',
      tone: 'danger',
    })
    expect(getDesktopStateTone('ready')).toBe('success')
    expect(getDesktopStateTone('restarting')).toBe('running')
    expect(getDesktopStateTone('degraded')).toBe('warning')
    expect(getDesktopStateTone('unavailable')).toBe('danger')
  })

  it.each(presentationFiles)('keeps %s free of superseded desktop styling', (path) => {
    const source = readSource(path)

    expect(source).not.toMatch(/rounded-(?:xl|2xl|3xl)/)
    expect(source).not.toMatch(/(?:cyan|sky)-/)
    expect(source).not.toMatch(/bg-white(?:\b|\/)/)
    expect(source).not.toMatch(/-apple-system|SF Pro (?:Text|Display)/)
  })
})

describe('desktop route-shell presentation contracts', () => {
  it('retains native chrome while exposing named keyboard landmarks', () => {
    const shell = readSource('components/desktop/DesktopWindowShell.tsx')

    expect(shell).toContain('data-desktop-region="native-titlebar"')
    expect(shell).toContain('style={dragRegionStyle}')
    expect(shell).toContain('aria-label="Desktop windows"')
    expect(shell).toContain('aria-label="Workspace routes"')
    expect(shell).toContain('aria-label="Settings panes"')
    expect(shell).toContain('href="#main-content"')
    expect(shell).toContain('id="main-content" tabIndex={-1}')
    expect(shell).toContain('role="tablist"')
    expect(shell).toContain('aria-selected={tracesTab === item.tab}')
    expect(shell).toContain('onKeyDown={handleTraceTabKeyDown}')
    expect(shell).not.toMatch(/window\.addEventListener[\s\S]*?Arrow(?:Up|Down|Left|Right)/)
  })

  it('keeps dialogs, route loading, forms, and motion preferences explicit', () => {
    const nativeRoute = readSource('components/desktop/DesktopNativeRoutePage.tsx')
    const boundary = readSource('components/desktop/DesktopRouteBoundary.tsx')
    const cockpit = readSource('components/desktop/DesktopOperatorCockpit.tsx')

    expect(nativeRoute).toContain('role="dialog"')
    expect(nativeRoute).toContain('aria-modal="true"')
    expect(nativeRoute).toContain('aria-label="Agent name"')
    expect(nativeRoute).toContain('aria-label="Deployment replicas"')
    expect(nativeRoute).toContain('aria-label="Webhook endpoint URL"')
    expect(nativeRoute).toContain('aria-label="Operator password"')
    expect(nativeRoute).toContain('motion-reduce:animate-none')
    expect(boundary).toContain('role="status"')
    expect(boundary).toContain('motion-reduce:animate-none')
    expect(cockpit).toContain('aria-label="Assistant name"')
    expect(cockpit).toContain('motion-reduce:transition-none')
  })

  it('renders deterministic, announced job states without pill progress bars', () => {
    const running = renderToStaticMarkup(
      createElement(DesktopJobNotice, {
        job: {
          id: 'runtimeResync',
          status: 'running',
          progress: 42,
          message: 'Refreshing local runtime state',
        },
        onDismiss: () => undefined,
      }),
    )
    const failed = renderToStaticMarkup(
      createElement(DesktopJobNotice, {
        job: {
          id: 'doctor',
          status: 'failed',
          progress: 67,
          message: '',
          error: 'Desktop Doctor could not complete.',
        },
      }),
    )

    expect(running).toContain('role="status"')
    expect(running).toContain('role="progressbar"')
    expect(running).toContain('aria-valuenow="42"')
    expect(running).toContain('aria-label="Dismiss Runtime Resync status"')
    expect(running).not.toContain('rounded-full')
    expect(failed).toContain('role="alert"')
    expect(failed).toContain('Desktop Doctor could not complete.')
  })
})
