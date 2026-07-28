import type { AutonomyDashboardPayload } from '../../app/api/dashboard/autonomy/autonomyData'

import {
  getAutonomyErrorPresentation,
  getAutonomySnapshotPresentation,
} from '../../components/dashboard/AutonomyPageClient'

function payload(
  overrides: Partial<AutonomyDashboardPayload> = {},
): AutonomyDashboardPayload {
  return {
    status: 'ok',
    scope: 'local-only',
    availability: 'complete',
    generatedAt: '2026-07-28T12:00:00.000Z',
    freshness: {
      state: 'fresh',
      heartbeatAt: '2026-07-28T11:59:45.000Z',
      ageSeconds: 15,
      staleAfterSeconds: 1200,
    },
    sources: { available: 6, missing: 0 },
    daemon: {
      reportedStatus: 'running',
      live: true,
      cycleCount: 12,
      lastCycleCompletedAt: '2026-07-28T11:59:45.000Z',
      lastResultStatus: 'idle',
    },
    lanes: [],
    fleet: { roles: [] },
    generatedTasks: [],
    queue: {
      counts: { queued: 0, running: 0, parked: 0, completed: 0, other: 0 },
      queued: [],
      running: [],
      parked: [],
      completed: [],
    },
    activeRunners: [],
    reports: [],
    ...overrides,
  }
}

describe('autonomy dashboard client truth states', () => {
  it.each([
    [401, 'auth', 'Operator session required'],
    [403, 'forbidden', 'Local autonomy access denied'],
    [404, 'error', 'Local autonomy data not found'],
    [503, 'error', 'Local autonomy unavailable'],
    [500, 'error', 'Autonomy service error'],
    [null, 'error', 'Autonomy connection unavailable'],
  ] as const)('maps %s to a distinct UI state', (status, kind, title) => {
    expect(getAutonomyErrorPresentation(status)).toEqual(
      expect.objectContaining({ kind, title }),
    )
  })

  it('never presents a stale running file as current daemon or runner activity', () => {
    const presentation = getAutonomySnapshotPresentation(
      payload({
        freshness: {
          state: 'stale',
          heartbeatAt: '2026-04-01T00:00:00.000Z',
          ageSeconds: 10_238_400,
          staleAfterSeconds: 1200,
        },
        daemon: {
          reportedStatus: 'running',
          live: true,
          cycleCount: 12,
          lastCycleCompletedAt: '2026-04-01T00:00:00.000Z',
          lastResultStatus: 'running',
        },
      }),
    )

    expect(presentation).toEqual(
      expect.objectContaining({
        snapshotLabel: 'stale local snapshot',
        daemonValue: 'stale snapshot',
        operationalStateVerified: false,
      }),
    )
    expect(presentation.heartbeatDetail).toContain('current execution is not verified')
    expect(presentation.daemonValue).not.toBe('running')
  })

  it('does not claim activity from a fresh heartbeat when the daemon reports stopped', () => {
    const presentation = getAutonomySnapshotPresentation(
      payload({
        daemon: {
          reportedStatus: 'stopped',
          live: false,
          cycleCount: 13,
          lastCycleCompletedAt: '2026-07-28T11:59:45.000Z',
          lastResultStatus: 'stopped',
        },
      }),
    )

    expect(presentation.snapshotLabel).toBe('fresh file · daemon not active')
    expect(presentation.operationalStateVerified).toBe(false)
  })
})
