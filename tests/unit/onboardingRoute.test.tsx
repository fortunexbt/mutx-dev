import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'

const mockUseDesktopStatus = jest.fn()

jest.mock('../../components/desktop/useDesktopStatus', () => ({
  DesktopStatusProvider: ({ children }: { children: React.ReactNode }) => children,
  useDesktopStatus: () => mockUseDesktopStatus(),
}))

jest.mock('../../components/desktop/DesktopOperatorCockpit', () => ({
  DesktopOperatorCockpit: ({ variant }: { variant: string }) => (
    <div data-desktop-cockpit={variant}>Desktop cockpit</div>
  ),
}))

jest.mock('../../components/desktop/BrowserDashboardRedirect', () => ({
  BrowserDashboardRedirect: ({ href }: { href: string }) => (
    <a href={href}>Continue in the browser dashboard</a>
  ),
}))

import OnboardingPage from '../../app/onboarding/page'

const browserOnboardingUrl = 'https://app.mutx.dev/dashboard/control'

describe('main-host onboarding route', () => {
  it('sends browser sessions to the canonical dashboard setup surface', () => {
    mockUseDesktopStatus.mockReturnValue({
      isDesktop: false,
      platformReady: true,
    })

    const html = renderToStaticMarkup(createElement(OnboardingPage))

    expect(html).toContain(`href="${browserOnboardingUrl}"`)
    expect(html).toContain('Continue in the browser dashboard')
    expect(html).not.toContain('Desktop cockpit')
  })

  it('preserves the standalone native cockpit for desktop sessions', () => {
    mockUseDesktopStatus.mockReturnValue({
      isDesktop: true,
      platformReady: true,
    })

    const html = renderToStaticMarkup(createElement(OnboardingPage))

    expect(html).toContain('data-desktop-cockpit="standalone"')
    expect(html).not.toContain('Continue in the browser dashboard')
  })

  it('announces route selection while the desktop bridge is detected', () => {
    mockUseDesktopStatus.mockReturnValue({
      isDesktop: false,
      platformReady: false,
    })

    const html = renderToStaticMarkup(createElement(OnboardingPage))

    expect(html).toContain('role="status"')
    expect(html).toContain('Opening the right MUTX setup surface')
  })
})
