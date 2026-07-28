'use client'

import { BrowserDashboardRedirect } from '@/components/desktop/BrowserDashboardRedirect'
import { DesktopOperatorCockpit } from '@/components/desktop/DesktopOperatorCockpit'
import {
  DesktopStatusProvider,
  useDesktopStatus,
} from '@/components/desktop/useDesktopStatus'
import { toAbsoluteAppUrl } from '@/lib/seo'

const browserOnboardingUrl = toAbsoluteAppUrl('/dashboard/control')

function OnboardingRouteSurface() {
  const { isDesktop, platformReady } = useDesktopStatus()

  if (!platformReady) {
    return (
      <main
        id="main-content"
        className="flex min-h-screen items-center justify-center bg-[linear-gradient(180deg,#04070d_0%,#09111d_55%,#050910_100%)] px-6 py-10"
      >
        <p role="status" aria-live="polite" className="text-sm text-slate-300">
          Opening the right MUTX setup surface…
        </p>
      </main>
    )
  }

  if (!isDesktop) {
    return (
      <main
        id="main-content"
        className="flex min-h-screen items-center justify-center bg-[linear-gradient(180deg,#04070d_0%,#09111d_55%,#050910_100%)] px-6 py-10"
      >
        <div className="w-full max-w-xl">
          <BrowserDashboardRedirect href={browserOnboardingUrl} />
        </div>
      </main>
    )
  }

  return <DesktopOperatorCockpit variant="standalone" />
}

export default function OnboardingPage() {
  return (
    <DesktopStatusProvider>
      <OnboardingRouteSurface />
    </DesktopStatusProvider>
  )
}
