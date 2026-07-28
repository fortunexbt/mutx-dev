import { readFileSync } from 'node:fs'
import { join } from 'node:path'

import {
  DASHBOARD_HEALTH_ROUTE,
  DASHBOARD_MEMORY_ROUTE,
  createInitialBootSteps,
  loadMemoryWarmup,
  probeControlPlane,
  summarizeBoot,
} from '../../components/dashboard/dashboardSpaBoot'

function jsonResponse(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('dashboard workspace startup evidence', () => {
  it('reports a connection only after the real health contract is healthy and ready', async () => {
    const fetcher = jest.fn(async () =>
      jsonResponse({ status: 'healthy', database: 'ready', version: '1.4.0' }),
    )
    const now = jest.fn().mockReturnValueOnce(100).mockReturnValueOnce(137)

    await expect(probeControlPlane(fetcher, now)).resolves.toEqual({
      status: 'healthy',
      database: 'ready',
      version: '1.4.0',
      latency: 37,
    })
    expect(fetcher).toHaveBeenCalledWith(DASHBOARD_HEALTH_ROUTE, { cache: 'no-store' })
  })

  it.each([
    [{ status: 'degraded', database: 'ready' }, 'Control plane reported a degraded state.'],
    [{ status: 'healthy', database: 'initializing' }, 'Control plane reported a degraded state.'],
  ])('rejects a 200 response without complete health evidence', async (payload, message) => {
    const fetcher = jest.fn(async () => jsonResponse(payload))

    await expect(probeControlPlane(fetcher)).rejects.toThrow(message)
  })

  it('surfaces the control-plane error returned by a failed health request', async () => {
    const fetcher = jest.fn(async () =>
      jsonResponse({ status: 'degraded', error: 'Connection failed' }, 503),
    )

    await expect(probeControlPlane(fetcher)).rejects.toThrow('Connection failed')
  })

  it('warms memory through the live route and preserves partial-source evidence', async () => {
    const fetcher = jest.fn(async () =>
      jsonResponse({
        generatedAt: '2026-07-28T10:00:00.000Z',
        summary: {
          sessions: 2,
          documentArtifacts: 1,
          reasoningArtifacts: 2,
        },
        partials: [
          'Memory inventory is read-only and derived from live sessions plus artifact-producing jobs.',
          'Document jobs are unavailable.',
        ],
      }),
    )

    await expect(loadMemoryWarmup(fetcher)).resolves.toEqual({
      status: 'warning',
      detail: '2 sessions and 3 artifacts indexed; 1 source unavailable.',
      issues: ['Document jobs are unavailable.'],
    })
    expect(fetcher).toHaveBeenCalledWith(DASHBOARD_MEMORY_ROUTE, { cache: 'no-store' })
  })

  it('does not call a partially failed boot fully ready', () => {
    const steps = createInitialBootSteps().map((step) => ({
      ...step,
      status: step.key === 'memory' ? ('warning' as const) : ('complete' as const),
    }))

    expect(summarizeBoot(steps)).toEqual({
      phase: 'degraded',
      settled: steps.length,
      complete: steps.length - 1,
      warnings: 1,
      errors: 0,
      fullyReady: false,
    })
  })

  it('uses the shared accessible dialog and reduced-motion-safe startup UI', () => {
    const source = readFileSync(
      join(process.cwd(), 'components/dashboard/DashboardSpaPanelHost.tsx'),
      'utf8',
    )
    const dialogSource = readFileSync(
      join(process.cwd(), 'components/dashboard/DashboardDialog.tsx'),
      'utf8',
    )

    expect(source.match(/<DashboardDialog/g)).toHaveLength(2)
    expect(source).toContain("aria-live={announce ? 'polite' : undefined}")
    expect(source).toContain("role='progressbar'")
    expect(source).toContain('motion-reduce:animate-none')
    expect(source).toContain('motion-reduce:transition-none')
    expect(source).toContain('data-autofocus')
    expect(source).toContain('setBootComplete(outcome.fullyReady)')
    expect(source).not.toContain("'/api/auth/me'")
    expect(source).toContain("updateStep('auth', 'complete', `Verified ${currentUser.display_name}.`)")
    expect(source).toContain("'Skipped because operator access was not verified.'")
    expect(source).not.toContain('ContentRouter active')
    expect(source).not.toContain('runtime connection stub')
    expect(source).not.toContain('until backend contracts ship')
    expect(dialogSource).toContain('role="dialog"')
    expect(dialogSource).toContain('aria-modal="true"')
    expect(dialogSource).toContain('if (event.key === "Escape")')
    expect(dialogSource).toContain('element.inert = true')
    expect(dialogSource).toContain('returnFocus.focus({ preventScroll: true })')
  })

  it('keeps the SPA history panel aligned with the canonical history route', () => {
    const source = readFileSync(
      join(process.cwd(), 'components/dashboard/DashboardContentRouter.tsx'),
      'utf8',
    )
    const activityCase = source.slice(
      source.indexOf("case 'activity':"),
      source.indexOf("case 'traces':"),
    )

    expect(activityCase).toContain("title='History'")
    expect(activityCase).toContain("<LogsPageClient mode='history' />")
    expect(activityCase).not.toContain('<MonitoringPageClient />')
  })
})
