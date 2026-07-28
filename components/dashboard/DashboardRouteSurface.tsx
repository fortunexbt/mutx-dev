'use client'

import type { ReactNode } from 'react'
import { usePathname } from 'next/navigation'

import { DashboardSpaPanelHost } from '@/components/dashboard/DashboardSpaPanelHost'
import { useDesktopStatus } from '@/components/desktop/useDesktopStatus'
import { shouldUseDashboardSpaPanelHost } from '@/lib/dashboardPanels'

export function DashboardRouteSurface({
  children,
  spaShellEnabled,
}: {
  children: ReactNode
  spaShellEnabled: boolean
}) {
  const { isDesktop } = useDesktopStatus()
  const pathname = usePathname()

  if (!spaShellEnabled || isDesktop || !shouldUseDashboardSpaPanelHost(pathname)) {
    return <>{children}</>
  }

  return <DashboardSpaPanelHost />
}
