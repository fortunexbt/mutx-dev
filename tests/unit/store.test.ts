import {
  type Agent,
  type AnalyticsSummary,
  type Budget,
  type Deployment,
  type MissionControlStore,
  type MonitoringAlert,
  type OverviewData,
  type Run,
  type Session,
  useMissionControl,
} from '@/lib/store'

const agent: Agent = {
  id: 'agent-1',
  name: 'Agent One',
  role: 'operator',
  status: 'idle',
  created_at: '2026-07-28T08:00:00Z',
  updated_at: '2026-07-28T08:00:00Z',
}

const session: Session = {
  id: 'session-1',
  key: 'session-key-1',
  kind: 'codex',
  age: 30,
  flags: [],
  active: true,
}

const run: Run = {
  id: 'run-1',
  status: 'completed',
}

const alert: MonitoringAlert = {
  id: 'alert-1',
  type: 'runtime',
  severity: 'warning',
  message: 'Run requires attention',
  acknowledged: false,
  created_at: '2026-07-28T08:00:00Z',
}

const deployment: Deployment = {
  id: 'deployment-1',
  agent_id: agent.id,
  status: 'success',
  created_at: '2026-07-28T08:00:00Z',
  updated_at: '2026-07-28T08:00:00Z',
}

const budget: Budget = {
  user_id: 'user-1',
  plan: 'pro',
  credits_total: 100,
  credits_used: 25,
  credits_remaining: 75,
  reset_date: '2026-08-01T00:00:00Z',
  usage_percentage: 25,
}

const overview: OverviewData = {
  agents: { total: 1, active: 1, idle: 0, error: 0 },
  sessions: { total: 1, active: 1 },
  runs: { total: 1, pending: 0, running: 0, completed: 1, failed: 0 },
  costs: { today: 1, week: 5, month: 10 },
}

const analyticsSummary: AnalyticsSummary = {
  total_agents: 1,
  active_sessions: 1,
  total_runs: 1,
  total_cost: 1,
  total_tokens: 100,
  period: '30d',
}

const originalFetch = global.fetch

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { 'content-type': 'application/json' },
  })
}

type FetchAction =
  | 'fetchAgents'
  | 'fetchSessions'
  | 'fetchRuns'
  | 'fetchOverview'
  | 'fetchAnalyticsSummary'
  | 'fetchMonitoringAlerts'
  | 'fetchBudgets'
  | 'fetchDeployments'

type FetchCase = {
  name: string
  action: FetchAction
  path: string
  seed: () => void
  snapshot: (state: MissionControlStore) => unknown
}

type CollectionFetchCase = FetchCase & {
  envelopeKey: string
  value: unknown[]
}

const collectionFetchCases: CollectionFetchCase[] = [
  {
    name: 'agents',
    action: 'fetchAgents',
    path: '/api/dashboard/agents',
    envelopeKey: 'items',
    value: [agent],
    seed: () => useMissionControl.setState({ agents: [agent] }),
    snapshot: (state) => state.agents,
  },
  {
    name: 'sessions',
    action: 'fetchSessions',
    path: '/api/dashboard/sessions',
    envelopeKey: 'sessions',
    value: [session],
    seed: () => useMissionControl.setState({ sessions: [session] }),
    snapshot: (state) => state.sessions,
  },
  {
    name: 'runs',
    action: 'fetchRuns',
    path: '/api/dashboard/runs',
    envelopeKey: 'items',
    value: [run],
    seed: () => useMissionControl.setState({ runs: [run] }),
    snapshot: (state) => state.runs,
  },
  {
    name: 'monitoring alerts',
    action: 'fetchMonitoringAlerts',
    path: '/api/dashboard/monitoring/alerts',
    envelopeKey: 'items',
    value: [alert],
    seed: () => useMissionControl.setState({ monitoringAlerts: [alert] }),
    snapshot: (state) => state.monitoringAlerts,
  },
  {
    name: 'deployments',
    action: 'fetchDeployments',
    path: '/api/dashboard/deployments',
    envelopeKey: 'items',
    value: [deployment],
    seed: () => useMissionControl.setState({ deployments: [deployment] }),
    snapshot: (state) => state.deployments,
  },
]

const singletonFetchCases: Array<FetchCase & { envelopeKey: string; value: unknown }> = [
  {
    name: 'overview',
    action: 'fetchOverview',
    path: '/api/dashboard/overview',
    envelopeKey: 'overview',
    value: overview,
    seed: () => useMissionControl.setState({ overview }),
    snapshot: (state) => state.overview,
  },
  {
    name: 'analytics summary',
    action: 'fetchAnalyticsSummary',
    path: '/api/dashboard/analytics/summary',
    envelopeKey: 'summary',
    value: analyticsSummary,
    seed: () => useMissionControl.setState({ analyticsSummary }),
    snapshot: (state) => state.analyticsSummary,
  },
  {
    name: 'budget',
    action: 'fetchBudgets',
    path: '/api/dashboard/budgets',
    envelopeKey: 'budget',
    value: budget,
    seed: () => useMissionControl.setState({ budget, budgets: [budget] }),
    snapshot: (state) => ({ budget: state.budget, budgets: state.budgets }),
  },
]

const allFetchCases: FetchCase[] = [...collectionFetchCases, ...singletonFetchCases]

describe('mission control store fetch actions', () => {
  beforeEach(() => {
    global.fetch = jest.fn()
    useMissionControl.setState({
      agents: [],
      sessions: [],
      runs: [],
      overview: null,
      analyticsSummary: null,
      monitoringAlerts: [],
      budget: null,
      budgets: [],
      deployments: [],
      bootComplete: false,
    })
  })

  afterAll(() => {
    global.fetch = originalFetch
  })

  describe.each(collectionFetchCases)('$name collection', (fetchCase) => {
    it.each([
      ['bare', (value: unknown[]) => value],
      ['enveloped', (value: unknown[]) => ({ [fetchCase.envelopeKey]: value })],
    ])('normalizes a 200 %s contract', async (_contract, makePayload) => {
      const fetchMock = global.fetch as jest.MockedFunction<typeof fetch>
      fetchMock.mockResolvedValue(jsonResponse(makePayload(fetchCase.value)))

      await useMissionControl.getState()[fetchCase.action]()

      expect(fetchCase.snapshot(useMissionControl.getState())).toEqual(fetchCase.value)
      expect(fetchMock).toHaveBeenCalledWith(fetchCase.path)
    })

    it('accepts 204 as a valid empty collection', async () => {
      const fetchMock = global.fetch as jest.MockedFunction<typeof fetch>
      fetchCase.seed()
      fetchMock.mockResolvedValue(new Response(null, { status: 204 }))

      await useMissionControl.getState()[fetchCase.action]()

      expect(fetchCase.snapshot(useMissionControl.getState())).toEqual([])
    })
  })

  describe.each(singletonFetchCases)('$name singleton', (fetchCase) => {
    it.each([
      ['bare', (value: unknown) => value],
      ['enveloped', (value: unknown) => ({ [fetchCase.envelopeKey]: value })],
    ])('normalizes a 200 %s contract', async (_contract, makePayload) => {
      const fetchMock = global.fetch as jest.MockedFunction<typeof fetch>
      fetchMock.mockResolvedValue(jsonResponse(makePayload(fetchCase.value)))

      await useMissionControl.getState()[fetchCase.action]()

      const expected =
        fetchCase.action === 'fetchBudgets'
          ? { budget: fetchCase.value, budgets: [fetchCase.value] }
          : fetchCase.value
      expect(fetchCase.snapshot(useMissionControl.getState())).toEqual(expected)
      expect(fetchMock).toHaveBeenCalledWith(fetchCase.path)
    })

    it('rejects 204 and preserves the prior singleton', async () => {
      const fetchMock = global.fetch as jest.MockedFunction<typeof fetch>
      fetchCase.seed()
      const before = fetchCase.snapshot(useMissionControl.getState())
      fetchMock.mockResolvedValue(new Response(null, { status: 204 }))

      await expect(useMissionControl.getState()[fetchCase.action]()).rejects.toThrow('204')

      expect(fetchCase.snapshot(useMissionControl.getState())).toEqual(before)
    })
  })

  describe.each(allFetchCases)('$name failures', (fetchCase) => {
    it.each([
      ['401', () => jsonResponse({ detail: 'Unauthorized' }, 401), '401'],
      ['403', () => jsonResponse({ detail: 'Forbidden' }, 403), '403'],
      ['500', () => jsonResponse({ detail: 'Server error' }, 500), '500'],
      ['malformed JSON', () => new Response('{', { status: 200 }), 'invalid JSON'],
    ])('rejects %s without replacing prior state', async (_failure, makeResponse, message) => {
      const fetchMock = global.fetch as jest.MockedFunction<typeof fetch>
      fetchCase.seed()
      const before = fetchCase.snapshot(useMissionControl.getState())
      fetchMock.mockResolvedValue(makeResponse())

      await expect(useMissionControl.getState()[fetchCase.action]()).rejects.toThrow(message)

      expect(fetchCase.snapshot(useMissionControl.getState())).toEqual(before)
    })

    it('rejects a network failure without replacing prior state', async () => {
      const fetchMock = global.fetch as jest.MockedFunction<typeof fetch>
      fetchCase.seed()
      const before = fetchCase.snapshot(useMissionControl.getState())
      fetchMock.mockRejectedValue(new Error('network offline'))

      await expect(useMissionControl.getState()[fetchCase.action]()).rejects.toThrow(
        'network offline'
      )

      expect(fetchCase.snapshot(useMissionControl.getState())).toEqual(before)
    })
  })

  it('keeps the singleton and compatibility budget state synchronized through setters', () => {
    useMissionControl.getState().setBudget(budget)
    expect(useMissionControl.getState().budget).toEqual(budget)
    expect(useMissionControl.getState().budgets).toEqual([budget])

    useMissionControl.getState().setBudgets([])
    expect(useMissionControl.getState().budget).toBeNull()
    expect(useMissionControl.getState().budgets).toEqual([])
  })
})
