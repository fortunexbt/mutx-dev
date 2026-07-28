import type { ReactNode } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'

let desktopStatus = { isDesktop: false, platformReady: false }

jest.mock('next/navigation', () => ({
  usePathname: () => '/dashboard/agents',
}))

jest.mock('../../components/desktop/useDesktopStatus', () => ({
  useDesktopStatus: () => desktopStatus,
}))

jest.mock('../../components/dashboard/livePrimitives', () => ({
  LivePanel: ({ children, title }: { children: ReactNode; title: string }) => (
    <section aria-label={title}>{children}</section>
  ),
  LiveAuthRequired: () => <section>Sign in to open the dashboard</section>,
}))

import { DashboardAuthBoundary } from '../../components/dashboard/DashboardAuthBoundary'

describe('dashboard auth boundary', () => {
  beforeEach(() => {
    desktopStatus = { isDesktop: false, platformReady: false }
  })

  it('does not render protected browser content while access is unresolved', () => {
    const markup = renderToStaticMarkup(
      <DashboardAuthBoundary>
        <div>private agent record</div>
      </DashboardAuthBoundary>,
    )

    expect(markup).toContain('Resolving dashboard runtime')
    expect(markup).toContain('Workspace records stay hidden')
    expect(markup).not.toContain('private agent record')
  })

  it('preserves the existing desktop surface without a browser auth probe', () => {
    desktopStatus = { isDesktop: true, platformReady: true }

    const markup = renderToStaticMarkup(
      <DashboardAuthBoundary>
        <div>desktop operator surface</div>
      </DashboardAuthBoundary>,
    )

    expect(markup).toContain('desktop operator surface')
    expect(markup).not.toContain('Dashboard access')
  })
})
