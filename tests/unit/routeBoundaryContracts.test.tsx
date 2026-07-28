import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { createElement, type AnchorHTMLAttributes, type ComponentType, type ReactNode } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'

import GlobalError from '../../app/global-error'
import ControlError from '../../app/control/error'
import ControlLoading from '../../app/control/loading'
import ControlNotFound from '../../app/control/not-found'
import DashboardError from '../../app/dashboard/error'
import DashboardLoading from '../../app/dashboard/loading'
import DashboardNotFound from '../../app/dashboard/not-found'
import PicoError from '../../app/pico/error'
import PicoLoading from '../../app/pico/loading'
import PicoNotFound from '../../app/pico/not-found'

type MockLinkProps = Omit<AnchorHTMLAttributes<HTMLAnchorElement>, 'href'> & {
  href: string
  children?: ReactNode
}

jest.mock('next/link', () => {
  const React = jest.requireActual<typeof import('react')>('react')

  return {
    __esModule: true,
    default: ({ href, children, ...props }: MockLinkProps) =>
      React.createElement('a', { ...props, href }, children),
  }
})

jest.mock('next-intl/server', () => ({
  getTranslations: async () => (key: string) => key,
}))

type ErrorBoundaryProps = {
  error: Error & { digest?: string }
  reset: () => void
}

type SegmentContract = {
  surface: 'dashboard' | 'control' | 'pico'
  Loading: ComponentType
  Error: ComponentType<ErrorBoundaryProps>
  NotFound: ComponentType
  errorHref: string
  notFoundHrefs: string[]
}

const segmentContracts: SegmentContract[] = [
  {
    surface: 'dashboard',
    Loading: DashboardLoading,
    Error: DashboardError,
    NotFound: DashboardNotFound,
    errorHref: '/dashboard',
    notFoundHrefs: ['/dashboard', '/dashboard/runs'],
  },
  {
    surface: 'control',
    Loading: ControlLoading,
    Error: ControlError,
    NotFound: ControlNotFound,
    errorHref: '/control',
    notFoundHrefs: ['/control', '/control/agents'],
  },
  {
    surface: 'pico',
    Loading: PicoLoading,
    Error: PicoError,
    NotFound: PicoNotFound,
    errorHref: '/pico/support',
    notFoundHrefs: ['/pico', '/pico/academy'],
  },
]

const segmentKinds = ['loading', 'error', 'not-found'] as const
const errorFiles = [
  'app/global-error.tsx',
  ...segmentContracts.map(({ surface }) => `app/${surface}/error.tsx`),
]
const loadingFiles = segmentContracts.map(({ surface }) => `app/${surface}/loading.tsx`)
const actionFiles = [
  ...errorFiles,
  ...segmentContracts.map(({ surface }) => `app/${surface}/not-found.tsx`),
]

function readSource(relativePath: string) {
  return readFileSync(join(process.cwd(), relativePath), 'utf8')
}

describe('App Router boundary source contracts', () => {
  it('sends every unmatched Pico segment through the scoped not-found boundary', () => {
    const source = readSource('app/pico/[...unknown]/page.tsx')

    expect(source).toContain("from 'next/navigation'")
    expect(source).toContain('notFound()')
  })

  it.each(segmentContracts.flatMap(({ surface }) =>
    segmentKinds.map((kind) => ({ surface, kind, path: `app/${surface}/${kind}.tsx` })),
  ))('keeps $surface/$kind segment scoped', ({ surface, kind, path }) => {
    const source = readSource(path)

    expect(source).toMatch(/export default (?:async )?function/)
    expect(source).toContain(`data-boundary-surface="${surface}"`)
    expect(source).toContain(`data-boundary-kind="${kind}"`)
  })

  it.each(['control', 'pico'] as const)('keeps the root skip-link target alive on %s boundaries', (surface) => {
    for (const kind of segmentKinds) {
      const source = readSource(`app/${surface}/${kind}.tsx`)

      expect(source).toContain('id="main-content"')
      expect(source).toContain('tabIndex={-1}')
    }
  })

  it('keeps the dashboard access boundary reachable from the root skip link', () => {
    const source = readSource('components/dashboard/DashboardAuthBoundary.tsx')

    expect(source).toContain("id='main-content'")
    expect(source).toContain('tabIndex={-1}')
  })

  it.each(errorFiles)('keeps %s as a client retry boundary without raw exception output', (path) => {
    const source = readSource(path)

    expect(source.trimStart()).toMatch(/^['"]use client['"]/) // Required by Next error files.
    expect(source).toContain('error: Error & { digest?: string }')
    expect(source).toContain('reset: () => void')
    expect(source).toContain('type="button"')
    expect(source).toContain('onClick={reset}')
    expect(source).not.toContain('console.error')
    expect(source).not.toMatch(/(?:_?error)\.(?:message|digest|stack)/)
  })

  it('keeps the global boundary self-contained when the root layout fails', () => {
    const source = readSource('app/global-error.tsx')

    expect(source).toContain('<html lang="en">')
    expect(source).toContain('<body')
    expect(source).toContain('id="main-content"')
  })

  it.each(loadingFiles)('keeps %s honest, announced, and reduced-motion aware', (path) => {
    const source = readSource(path)

    expect(source).toContain('role="status"')
    expect(source).toContain('aria-live="polite"')
    expect(source).toContain('aria-busy="true"')
    expect(source).toContain('motion-safe:animate-pulse')
    expect(source).toContain('motion-reduce:animate-none')
  })

  it.each(actionFiles)('keeps actions in %s keyboard-visible', (path) => {
    expect(readSource(path)).toContain('focus-visible:outline')
  })
})

describe('App Router boundary DOM contracts', () => {
  it.each(segmentContracts)('renders announced, data-free loading UI for $surface', ({
    surface,
    Loading,
  }) => {
    const html = renderToStaticMarkup(createElement(Loading))

    expect(html).toContain(`data-boundary-surface="${surface}"`)
    expect(html).toContain('data-boundary-kind="loading"')
    expect(html).toContain('role="status"')
    expect(html).toContain('aria-busy="true"')
    expect(html).not.toMatch(/data-agent-id|data-run-id|data-deployment-id/)
  })

  it.each(segmentContracts)('renders a safe retry and scoped exit for $surface errors', ({
    surface,
    Error: ErrorBoundary,
    errorHref,
  }) => {
    const secretExceptionText = `private-${surface}-exception-detail`
    const html = renderToStaticMarkup(
      createElement(ErrorBoundary, {
        error: new Error(secretExceptionText),
        reset: jest.fn(),
      }),
    )

    expect(html).toContain(`data-boundary-surface="${surface}"`)
    expect(html).toContain('data-boundary-kind="error"')
    expect(html).toContain('role="alert"')
    expect(html).toContain('<button type="button"')
    expect(html).toContain(`href="${errorHref}"`)
    expect(html).not.toContain(secretExceptionText)
  })

  it.each(segmentContracts)('renders surface-appropriate exits for $surface not-found UI', async ({
    surface,
    NotFound,
    notFoundHrefs,
  }) => {
    const element = surface === 'pico' ? await PicoNotFound() : createElement(NotFound)
    const html = renderToStaticMarkup(element)

    expect(html).toContain(`data-boundary-surface="${surface}"`)
    expect(html).toContain('data-boundary-kind="not-found"')
    expect(html).toContain('aria-label=')
    notFoundHrefs.forEach((href) => expect(html).toContain(`href="${href}"`))
  })

  it('renders the global error as a complete document without exposing the exception', () => {
    const secretExceptionText = 'private-global-exception-detail'
    const html = renderToStaticMarkup(
      createElement(GlobalError, {
        error: new Error(secretExceptionText),
        reset: jest.fn(),
      }),
    )

    expect(html).toMatch(/^<html lang="en">/)
    expect(html).toContain('<body')
    expect(html).toContain('data-boundary-surface="global"')
    expect(html).toContain('<button type="button"')
    expect(html).not.toContain(secretExceptionText)
  })
})
