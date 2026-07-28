import { existsSync, readFileSync, readdirSync } from 'node:fs'
import { join } from 'node:path'
import {
  Children,
  isValidElement,
  type ReactElement,
  type ReactNode,
} from 'react'
import { renderToStaticMarkup } from 'react-dom/server'

import { ApiRequestError } from '../../components/app/http'
import { getDashboardRequestAccessFailure } from '../../components/dashboard/dashboardRequestAccess'
import { LiveAuthRequired, LiveForbidden } from '../../components/dashboard/livePrimitives'

const mockSetInterfaceMode = jest.fn()

jest.mock('next/dynamic', () => ({
  __esModule: true,
  default: () => () => null,
}))

jest.mock('@/lib/store', () => ({
  useMissionControl: (selector: (state: { setInterfaceMode: typeof mockSetInterfaceMode }) => unknown) =>
    selector({ setInterfaceMode: mockSetInterfaceMode }),
}))

import {
  UpgradeNudge,
  hasFullModeAccess,
} from '../../components/dashboard/DashboardContentRouter'

type InteractiveProps = {
  'aria-label'?: string
  children?: ReactNode
  href?: string
  onClick?: () => void
}

function findInteractiveElement(node: ReactNode, accessibleLabel: string): ReactElement | null {
  let match: ReactElement | null = null

  Children.forEach(node, (child) => {
    if (match || !isValidElement(child)) return

    const props = child.props as InteractiveProps
    if (
      (child.type === 'a' || child.type === 'button') &&
      props['aria-label'] === accessibleLabel
    ) {
      match = child
      return
    }

    match = findInteractiveElement(props.children, accessibleLabel)
  })

  return match
}

function readSource(relativePath: string) {
  return readFileSync(join(process.cwd(), relativePath), 'utf8')
}

function sourceFiles(relativeDirectory: string): string[] {
  const directory = join(process.cwd(), relativeDirectory)

  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const relativePath = join(relativeDirectory, entry.name)
    if (entry.isDirectory()) return sourceFiles(relativePath)
    return /\.(?:ts|tsx)$/.test(entry.name) ? [relativePath] : []
  })
}

const aggregateClients = [
  'components/dashboard/NotificationsPageClient.tsx',
  'components/dashboard/StandupPageClient.tsx',
  'components/dashboard/DashboardOverviewPageClient.tsx',
]

describe('dashboard aggregate access states', () => {
  it('reserves authentication for 401 and classifies 403 as permission denied', () => {
    expect(getDashboardRequestAccessFailure(new ApiRequestError('Sign in', 401))).toBe(
      'authentication',
    )
    expect(getDashboardRequestAccessFailure(new ApiRequestError('Forbidden', 403))).toBe(
      'permission',
    )
  })

  it.each(aggregateClients)('keeps authentication and permission branches separate in %s', (path) => {
    const source = readSource(path)

    expect(source).toContain('getDashboardRequestAccessFailure(loadError)')
    expect(source).toMatch(/accessFailure === ["']authentication["']/)
    expect(source).toMatch(/accessFailure === ["']permission["']/)
    expect(source).toContain('<LiveAuthRequired')
    expect(source).toContain('<LiveForbidden')
    expect(source).not.toMatch(/status === 401\s*\|\|\s*[^\n]*status === 403/)
  })

  it('announces permission denial without offering an authentication or workspace action', () => {
    const markup = renderToStaticMarkup(
      <LiveForbidden
        title='Overview permission required'
        message='Workspace actions are unavailable.'
      />,
    )

    expect(markup).toContain('role="alert"')
    expect(markup).toContain('aria-live="assertive"')
    expect(markup).toContain('data-dashboard-access="forbidden"')
    expect(markup).not.toContain('<button')
    expect(markup).not.toContain('<a ')
    expect(markup).not.toMatch(/sign in|create account|recover access/i)
  })

  it('offers authentication recovery with the exact nested dashboard return path', () => {
    const markup = renderToStaticMarkup(
      <LiveAuthRequired
        title='Operator session required'
        message='Sign in to continue.'
        nextPath='/dashboard/notifications?scope=open'
      />,
    )

    expect(markup).toContain('href="/login?next=%2Fdashboard%2Fnotifications%3Fscope%3Dopen"')
    expect(markup).toContain('href="/register?next=%2Fdashboard%2Fnotifications%3Fscope%3Dopen"')
    expect(markup).toContain('href="/forgot-password?next=%2Fdashboard%2Fnotifications%3Fscope%3Dopen"')
  })
})

describe('actionable full-mode boundary', () => {
  beforeEach(() => {
    mockSetInterfaceMode.mockReset()
  })

  it.each([
    ['free', false],
    ['pro', true],
    ['enterprise', true],
    [null, false],
  ] as const)('resolves %s full-mode entitlement without coercion', (plan, expected) => {
    expect(hasFullModeAccess(plan)).toBe(expected)
  })

  it.each(['pro', 'enterprise'] as const)('switches a %s workspace into full mode', (plan) => {
    const boundary = UpgradeNudge({ panel: 'security', subscription: plan })
    const action = findInteractiveElement(
      boundary,
      'Switch security panel to full mode',
    )

    expect(action?.type).toBe('button')
    ;(action?.props as InteractiveProps).onClick?.()
    expect(mockSetInterfaceMode).toHaveBeenCalledWith('full')
  })

  it('links a Free workspace to the Pro plan comparison', () => {
    const boundary = UpgradeNudge({ panel: 'security', subscription: 'free' })
    const action = findInteractiveElement(boundary, 'Compare plans for security panel')

    expect(action?.type).toBe('a')
    expect((action?.props as InteractiveProps).href).toBe('/pico/pricing?plan=pro')
    expect(mockSetInterfaceMode).not.toHaveBeenCalled()
  })

  it('retries the live entitlement check when the plan is unknown', () => {
    const reload = jest.fn()
    const originalWindow = Object.getOwnPropertyDescriptor(globalThis, 'window')
    Object.defineProperty(globalThis, 'window', {
      configurable: true,
      value: { location: { reload } },
    })

    try {
      const boundary = UpgradeNudge({ panel: 'security', subscription: null })
      const action = findInteractiveElement(
        boundary,
        'Retry plan check for security panel',
      )

      expect(action?.type).toBe('button')
      ;(action?.props as InteractiveProps).onClick?.()
      expect(reload).toHaveBeenCalledTimes(1)
    } finally {
      if (originalWindow) {
        Object.defineProperty(globalThis, 'window', originalWindow)
      } else {
        Reflect.deleteProperty(globalThis, 'window')
      }
    }
  })

  it.each([
    ['pro', 'Switch security panel to full mode'],
    ['free', 'Compare plans for security panel'],
    [null, 'Retry plan check for security panel'],
  ] as const)('labels the %s primary action and overview exit', (plan, primaryLabel) => {
    const boundary = UpgradeNudge({ panel: 'security', subscription: plan })

    expect(findInteractiveElement(boundary, primaryLabel)).not.toBeNull()
    expect(findInteractiveElement(boundary, 'Return to dashboard overview')).not.toBeNull()
  })

  it('keeps the workspace in essential mode until a paid entitlement is verified', () => {
    const host = readSource('components/dashboard/DashboardSpaPanelHost.tsx')

    expect(host).toContain("setInterfaceMode('essential')")
    expect(host).toContain('setSubscription(null)')
    expect(host).toContain('disabled={!hasFullModeAccess(subscription)}')
    expect(host).toContain("if (hasFullModeAccess(subscription)) setInterfaceMode('full')")
    expect(host).not.toContain("setSubscription('free')")
  })
})

describe('reachable dashboard source truth', () => {
  const reachableSources = [
    ...sourceFiles('app/dashboard'),
    ...sourceFiles('components/dashboard').filter(
      (path) => !path.startsWith('components/dashboard/demo/'),
    ),
  ]
  const prohibitedCopy = [
    /still being wired/i,
    /shell ready/i,
    /not shipped/i,
    /coming[- ]soon/i,
    /\bsprint\b/i,
    /\bbeta\b/i,
    /\bpreview\b/i,
    /\bfake[- ]live\b/i,
    /\bdemo[- ]data\b/i,
    /\b(?:placeholder|sample|mock|simulated) (?:content|data|metrics|records|surface|values)\b/i,
  ]

  it.each(reachableSources)('keeps %s free of placeholder release framing', (path) => {
    const source = readSource(path)

    for (const pattern of prohibitedCopy) {
      expect(source).not.toMatch(pattern)
    }
  })

  it.each(['DashboardSectionPage.tsx', 'DemoRoutePage.tsx'])(
    'removes the unreferenced generic placeholder %s',
    (fileName) => {
      expect(existsSync(join(process.cwd(), 'components/dashboard', fileName))).toBe(false)
    },
  )

  it('keeps the explicit simulated control demo outside the real dashboard source set', () => {
    expect(reachableSources.some((path) => path.startsWith('components/dashboard/demo/'))).toBe(
      false,
    )
  })

  it('documents host-dependent surfaces as current boundaries', () => {
    expect(readSource('app/dashboard/autonomy/page.tsx')).toMatch(/machine-host scoped/i)

    const openclaw = readSource('components/dashboard/control/OpenclawSetupSurface.tsx')
    expect(openclaw).toMatch(/machine-host security boundary/i)
    expect(openclaw).toMatch(/intentionally read-only/i)
    expect(openclaw).toContain(': "unavailable"')
  })
})
