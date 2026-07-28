import { notFound, redirect } from 'next/navigation'

import { matchDashboardPanelPath, panelHref } from '@/lib/dashboardPanels'

export default async function DashboardPanelRouterPage({
  params,
}: {
  params: Promise<{ panel: string[] }>
}) {
  const { panel: segments } = await params

  if (segments.length !== 1) {
    notFound()
  }

  const pathname = `/dashboard/${segments[0]}`
  const panel = matchDashboardPanelPath(pathname)

  if (!panel) {
    notFound()
  }

  redirect(panelHref(panel))
}
