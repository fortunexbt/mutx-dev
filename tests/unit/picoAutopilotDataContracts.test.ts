import { readFileSync } from 'node:fs'
import { join } from 'node:path'

import { fetchSignal } from '../../components/pico/PicoAutopilotPageClient'
import {
  appendApprovalPage,
  describeApprovalMutationFailure,
  hasNextApprovalPage,
  parseApprovalPage,
  parseEligibleApprovalReviewers,
  parseRuntimeSnapshot,
  presentRuntimeSnapshot,
} from '../../lib/pico/autopilot'

const pendingItem = {
  id: 'approval-1',
  owner_id: 'owner-1',
  reviewer_id: 'reviewer-1',
  can_resolve: true,
  agent_id: 'agent-1',
  session_id: 'session-1',
  action_type: 'OUTBOUND_SEND',
  payload: { summary: 'Send a message only after review.' },
  status: 'PENDING',
  requester: 'operator@mutx.dev',
  created_at: '2026-07-28T09:00:00.000Z',
}

describe('pico autopilot approval and runtime data contracts', () => {
  it('accepts only discoverable reviewer records with explicit roles', () => {
    expect(
      parseEligibleApprovalReviewers([
        {
          id: 'reviewer-1',
          email: 'reviewer@mutx.dev',
          name: 'Reviewer',
          roles: ['DEVELOPER'],
        },
      ]),
    ).toEqual([
      expect.objectContaining({ id: 'reviewer-1', roles: ['DEVELOPER'] }),
    ])
    expect(
      parseEligibleApprovalReviewers([
        { id: 'reviewer-2', email: 'reviewer@mutx.dev', name: 'Reviewer' },
      ]),
    ).toBeNull()
  })

  it('parses the real paginated approval envelope without discarding totals or status', () => {
    const page = parseApprovalPage(
      {
        items: [pendingItem],
        total: 31,
        skip: 20,
        limit: 20,
        status: 'PENDING',
        agent_id: null,
      },
      'PENDING',
    )

    expect(page).toMatchObject({
      total: 31,
      skip: 20,
      limit: 20,
      status: 'PENDING',
      agent_id: null,
    })
    expect(page?.items[0]).toMatchObject({
      id: 'approval-1',
      owner_id: 'owner-1',
      reviewer_id: 'reviewer-1',
      can_resolve: true,
      status: 'PENDING',
      payload: { summary: 'Send a message only after review.' },
    })
    expect(hasNextApprovalPage(page!)).toBe(true)
  })

  it('rejects legacy arrays and mismatched status pages instead of fabricating an empty queue', () => {
    expect(parseApprovalPage([pendingItem], 'PENDING')).toBeNull()
    expect(
      parseApprovalPage(
        {
          items: [{ ...pendingItem, status: 'APPROVED' }],
          total: 1,
          skip: 0,
          limit: 50,
          status: 'APPROVED',
          agent_id: null,
        },
        'PENDING',
      ),
    ).toBeNull()
    const missingReviewer = Object.fromEntries(
      Object.entries(pendingItem).filter(([key]) => key !== 'reviewer_id'),
    )
    expect(
      parseApprovalPage(
        {
          items: [missingReviewer],
          total: 1,
          skip: 0,
          limit: 50,
          status: 'PENDING',
          agent_id: null,
        },
        'PENDING',
      ),
    ).toBeNull()
  })

  it('appends sequential approval pages while retaining canonical pagination metadata', () => {
    const first = parseApprovalPage(
      {
        items: [pendingItem],
        total: 2,
        skip: 0,
        limit: 1,
        status: 'PENDING',
        agent_id: null,
      },
      'PENDING',
    )!
    const second = parseApprovalPage(
      {
        items: [{ ...pendingItem, id: 'approval-2' }],
        total: 2,
        skip: 1,
        limit: 1,
        status: 'PENDING',
        agent_id: null,
      },
      'PENDING',
    )!

    const merged = appendApprovalPage(first, second)

    expect(merged?.items.map((item) => item.id)).toEqual(['approval-1', 'approval-2'])
    expect(merged).toMatchObject({ total: 2, skip: 0, limit: 1, status: 'PENDING' })
    expect(hasNextApprovalPage(merged!)).toBe(false)
  })

  it('marks a server-reported healthy snapshot stale when its observation timestamp expired', () => {
    const snapshot = parseRuntimeSnapshot({
      provider: 'openclaw',
      label: 'OpenClaw',
      status: 'healthy',
      last_seen_at: '2026-07-28T08:00:00.000Z',
      last_synced_at: '2026-07-28T08:01:00.000Z',
      stale: false,
      stale_after_seconds: 900,
      binding_count: 1,
    })
    const presentation = presentRuntimeSnapshot(
      snapshot,
      '2026-07-28T09:00:00.000Z',
      new Date('2026-07-28T09:00:00.000Z'),
    )

    expect(presentation.state).toBe('stale')
    expect(presentation.label).toMatch(/stale runtime snapshot/i)
    expect(presentation.detail).toMatch(/historical state, not a current health or safety signal/i)
    expect(presentation.observedAt).toBe('2026-07-28T08:00:00.000Z')
    expect(presentation.fetchedAt).toBe('2026-07-28T09:00:00.000Z')
  })

  it('keeps missing timestamps and partial runtime failures explicitly unavailable', () => {
    const missingTimestamp = parseRuntimeSnapshot({
      provider: 'openclaw',
      label: 'OpenClaw',
      status: 'healthy',
      last_seen_at: null,
      last_synced_at: null,
      stale: false,
      stale_after_seconds: 900,
    })

    expect(missingTimestamp?.binding_count).toBeNull()
    expect(
      presentRuntimeSnapshot(
        missingTimestamp,
        '2026-07-28T09:00:00.000Z',
        new Date('2026-07-28T09:00:00.000Z'),
      ),
    ).toMatchObject({
      state: 'unavailable',
      label: 'Runtime freshness unavailable',
      reportedStatus: 'healthy',
    })

    const unavailable = presentRuntimeSnapshot(
      null,
      '2026-07-28T09:00:00.000Z',
      new Date('2026-07-28T09:00:00.000Z'),
    )
    expect(unavailable.state).toBe('unavailable')
    expect(unavailable.reportedStatus).toBeNull()
    expect(unavailable.detail).toMatch(/no runtime status or safety state is assumed/i)
    expect(unavailable.detail).not.toMatch(/0|healthy/i)
  })

  it.each([
    [401, 'unauthorized', true, false],
    [403, 'forbidden', false, false],
    [404, 'not_found', false, true],
    [409, 'conflict', false, true],
    [503, 'server', false, false],
  ] as const)(
    'distinguishes mutation response %s as %s',
    (status, kind, requiresAuth, shouldReload) => {
      const failure = describeApprovalMutationFailure(
        status,
        { detail: 'upstream detail' },
        'approve',
      )

      expect(failure).toMatchObject({ kind, requiresAuth, shouldReload })
      expect(failure.message).toMatch(/no approval state|canonical queue|permission|already decided/i)
    },
  )

  it('aborts an obsolete signal refresh instead of allowing stale data to win', async () => {
    const fetchMock = jest.spyOn(global, 'fetch').mockImplementation((_input, init) =>
      new Promise((_resolve, reject) => {
        init?.signal?.addEventListener('abort', () => {
          reject(new DOMException('The operation was aborted', 'AbortError'))
        })
      }),
    )
    const controller = new AbortController()

    const pendingRefresh = fetchSignal(
      'runtime',
      'runtime snapshot',
      '/api/pico/runtime/openclaw',
      controller.signal,
    )
    controller.abort()

    await expect(pendingRefresh).rejects.toMatchObject({ name: 'AbortError' })
    fetchMock.mockRestore()
  })

  it('keeps pending actions, confirmations, and compact controls keyboard-accessible', () => {
    const source = readFileSync(
      join(process.cwd(), 'components/pico/PicoAutopilotPageClient.tsx'),
      'utf8',
    )

    expect(source).toContain('aria-busy={resolvingApprovalId === approval.id}')
    expect(source).toContain('{approval.can_resolve ? (')
    expect(source).toContain('approvalActionErrors[approval.id]')
    expect(source).toContain("'/api/pico/approvals/reviewers'")
    expect(source).toContain('reviewer_id: approvalDraft.reviewerId')
    expect(source).toContain('disabled={creatingApproval || eligibleReviewers.length === 0}')
    expect(source).toContain('role="status"')
    expect(source).toContain('tabIndex={-1}')
    expect(source).toContain('type="submit"')
    expect(source).toContain("'mt-4 min-h-11 w-full sm:w-auto'")
  })
})
