import { NextRequest, NextResponse } from 'next/server'

const proxyJson = jest.fn()
const checkAgentOwnership = jest.fn()
const checkDeploymentOwnership = jest.fn()

jest.mock('../../app/api/_lib/controlPlane', () => ({
  getApiBaseUrl: () => 'http://localhost:8000',
  hasAuthSession: () => true,
}))

jest.mock('../../app/api/_lib/proxy', () => ({ proxyJson }))

jest.mock('../../app/api/_lib/ownership', () => ({
  checkAgentOwnership,
  checkDeploymentOwnership,
}))

type LegacyHandler = (
  request: NextRequest,
  context: { params: Promise<Record<string, string>> },
) => Promise<NextResponse>

type RouteCase = {
  name: string
  method: 'GET' | 'POST' | 'DELETE'
  url: string
  params?: Record<string, string>
  body?: unknown
  load: () => Promise<LegacyHandler>
  expectedUrl: string
  expectedOptions: Record<string, unknown>
  ownership?: 'agent' | 'deployment'
}

const agentId = 'agent-123'
const deploymentId = 'deployment-123'
const runId = 'run-123'
const deploymentAgentId = '123e4567-e89b-42d3-a456-426614174000'

const cases: RouteCase[] = [
  {
    name: 'agents list forwards its full query',
    method: 'GET',
    url: 'http://localhost:3000/api/agents?skip=10&limit=25',
    load: async () => (await import('../../app/api/agents/route')).GET as unknown as LegacyHandler,
    expectedUrl: 'http://localhost:8000/v1/agents?skip=10&limit=25',
    expectedOptions: {
      headers: { 'Content-Type': 'application/json' },
      fallbackMessage: 'Failed to fetch agents',
    },
  },
  {
    name: 'agent create forwards the validated openclaw body',
    method: 'POST',
    url: 'http://localhost:3000/api/agents',
    body: {
      name: 'OpenClaw operator',
      type: 'openclaw',
      config: { runtime: 'personal_assistant' },
    },
    load: async () => (await import('../../app/api/agents/route')).POST as unknown as LegacyHandler,
    expectedUrl: 'http://localhost:8000/v1/agents',
    expectedOptions: {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: 'OpenClaw operator',
        type: 'openclaw',
        config: { runtime: 'personal_assistant' },
      }),
      fallbackMessage: 'Failed to create agent',
    },
  },
  {
    name: 'agent detail uses the shared proxy',
    method: 'GET',
    url: `http://localhost:3000/api/agents/${agentId}`,
    params: { id: agentId },
    load: async () =>
      (await import('../../app/api/agents/[id]/route')).GET as unknown as LegacyHandler,
    expectedUrl: `http://localhost:8000/v1/agents/${agentId}`,
    expectedOptions: { fallbackMessage: 'Failed to fetch agent' },
    ownership: 'agent',
  },
  {
    name: 'agent delete uses the shared proxy',
    method: 'DELETE',
    url: `http://localhost:3000/api/agents/${agentId}`,
    params: { id: agentId },
    load: async () =>
      (await import('../../app/api/agents/[id]/route')).DELETE as unknown as LegacyHandler,
    expectedUrl: `http://localhost:8000/v1/agents/${agentId}`,
    expectedOptions: { method: 'DELETE', fallbackMessage: 'Failed to delete agent' },
    ownership: 'agent',
  },
  {
    name: 'agent deploy uses the shared proxy',
    method: 'POST',
    url: `http://localhost:3000/api/agents/${agentId}/deploy`,
    params: { id: agentId },
    load: async () =>
      (await import('../../app/api/agents/[id]/deploy/route')).POST as unknown as LegacyHandler,
    expectedUrl: `http://localhost:8000/v1/agents/${agentId}/deploy`,
    expectedOptions: { method: 'POST', fallbackMessage: 'Failed to deploy agent' },
    ownership: 'agent',
  },
  {
    name: 'agent logs forward their full query',
    method: 'GET',
    url: `http://localhost:3000/api/agents/${agentId}/logs?level=error&limit=25`,
    params: { id: agentId },
    load: async () =>
      (await import('../../app/api/agents/[id]/logs/route')).GET as unknown as LegacyHandler,
    expectedUrl: `http://localhost:8000/v1/agents/${agentId}/logs?level=error&limit=25`,
    expectedOptions: { fallbackMessage: 'Failed to fetch logs' },
    ownership: 'agent',
  },
  {
    name: 'agent stop uses the shared proxy',
    method: 'POST',
    url: `http://localhost:3000/api/agents/${agentId}/stop`,
    params: { id: agentId },
    load: async () =>
      (await import('../../app/api/agents/[id]/stop/route')).POST as unknown as LegacyHandler,
    expectedUrl: `http://localhost:8000/v1/agents/${agentId}/stop`,
    expectedOptions: { method: 'POST', fallbackMessage: 'Failed to stop agent' },
    ownership: 'agent',
  },
  {
    name: 'deployments list forwards its full query',
    method: 'GET',
    url: 'http://localhost:3000/api/deployments?skip=5&limit=10',
    load: async () =>
      (await import('../../app/api/deployments/route')).GET as unknown as LegacyHandler,
    expectedUrl: 'http://localhost:8000/v1/deployments?skip=5&limit=10',
    expectedOptions: {
      headers: { 'Content-Type': 'application/json' },
      fallbackMessage: 'Failed to fetch deployments',
    },
  },
  {
    name: 'deployment create forwards only backend-supported fields',
    method: 'POST',
    url: 'http://localhost:3000/api/deployments',
    body: { agent_id: deploymentAgentId, replicas: 3 },
    load: async () =>
      (await import('../../app/api/deployments/route')).POST as unknown as LegacyHandler,
    expectedUrl: 'http://localhost:8000/v1/deployments',
    expectedOptions: {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ agent_id: deploymentAgentId, replicas: 3 }),
      fallbackMessage: 'Failed to create deployment',
    },
  },
  {
    name: 'deployment detail uses the shared proxy',
    method: 'GET',
    url: `http://localhost:3000/api/deployments/${deploymentId}`,
    params: { id: deploymentId },
    load: async () =>
      (await import('../../app/api/deployments/[id]/route')).GET as unknown as LegacyHandler,
    expectedUrl: `http://localhost:8000/v1/deployments/${deploymentId}`,
    expectedOptions: { fallbackMessage: 'Failed to fetch deployment' },
    ownership: 'deployment',
  },
  {
    name: 'deployment delete uses the shared proxy',
    method: 'DELETE',
    url: `http://localhost:3000/api/deployments/${deploymentId}`,
    params: { id: deploymentId },
    load: async () =>
      (await import('../../app/api/deployments/[id]/route')).DELETE as unknown as LegacyHandler,
    expectedUrl: `http://localhost:8000/v1/deployments/${deploymentId}`,
    expectedOptions: { method: 'DELETE', fallbackMessage: 'Failed to delete deployment' },
    ownership: 'deployment',
  },
  {
    name: 'deployment events forward their full query',
    method: 'GET',
    url: `http://localhost:3000/api/deployments/${deploymentId}/events?status=failed&limit=20`,
    params: { id: deploymentId },
    load: async () =>
      (await import('../../app/api/deployments/[id]/events/route')).GET as unknown as LegacyHandler,
    expectedUrl: `http://localhost:8000/v1/deployments/${deploymentId}/events?status=failed&limit=20`,
    expectedOptions: { fallbackMessage: 'Failed to fetch events' },
    ownership: 'deployment',
  },
  {
    name: 'deployment logs forward their full query',
    method: 'GET',
    url: `http://localhost:3000/api/deployments/${deploymentId}/logs?level=warning&limit=50`,
    params: { id: deploymentId },
    load: async () =>
      (await import('../../app/api/deployments/[id]/logs/route')).GET as unknown as LegacyHandler,
    expectedUrl: `http://localhost:8000/v1/deployments/${deploymentId}/logs?level=warning&limit=50`,
    expectedOptions: { fallbackMessage: 'Failed to fetch logs' },
    ownership: 'deployment',
  },
  {
    name: 'deployment metrics forward their full query',
    method: 'GET',
    url: `http://localhost:3000/api/deployments/${deploymentId}/metrics?window=1h&limit=60`,
    params: { id: deploymentId },
    load: async () =>
      (await import('../../app/api/deployments/[id]/metrics/route')).GET as unknown as LegacyHandler,
    expectedUrl: `http://localhost:8000/v1/deployments/${deploymentId}/metrics?window=1h&limit=60`,
    expectedOptions: { fallbackMessage: 'Failed to fetch metrics' },
    ownership: 'deployment',
  },
  {
    name: 'deployment restart uses the shared proxy',
    method: 'POST',
    url: `http://localhost:3000/api/deployments/${deploymentId}/restart`,
    params: { id: deploymentId },
    load: async () =>
      (await import('../../app/api/deployments/[id]/restart/route')).POST as unknown as LegacyHandler,
    expectedUrl: `http://localhost:8000/v1/deployments/${deploymentId}/restart`,
    expectedOptions: { method: 'POST', fallbackMessage: 'Failed to restart deployment' },
    ownership: 'deployment',
  },
  {
    name: 'deployment scale forwards its JSON body',
    method: 'POST',
    url: `http://localhost:3000/api/deployments/${deploymentId}/scale`,
    params: { id: deploymentId },
    body: { replicas: 0 },
    load: async () =>
      (await import('../../app/api/deployments/[id]/scale/route')).POST as unknown as LegacyHandler,
    expectedUrl: `http://localhost:8000/v1/deployments/${deploymentId}/scale`,
    expectedOptions: {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ replicas: 0 }),
      fallbackMessage: 'Failed to scale deployment',
    },
    ownership: 'deployment',
  },
  {
    name: 'run traces list forwards its full query',
    method: 'GET',
    url: `http://localhost:3000/api/runs/${runId}/traces?skip=25&limit=25`,
    params: { runId },
    load: async () =>
      (await import('../../app/api/runs/[runId]/traces/route')).GET as unknown as LegacyHandler,
    expectedUrl: `http://localhost:8000/v1/runs/${runId}/traces?skip=25&limit=25`,
    expectedOptions: {
      headers: { 'Content-Type': 'application/json' },
      fallbackMessage: 'Failed to fetch traces',
    },
  },
  {
    name: 'run trace create forwards its JSON body',
    method: 'POST',
    url: `http://localhost:3000/api/runs/${runId}/traces`,
    params: { runId },
    body: { name: 'mutx.tool.execution', attributes: { 'agent.id': agentId } },
    load: async () =>
      (await import('../../app/api/runs/[runId]/traces/route')).POST as unknown as LegacyHandler,
    expectedUrl: `http://localhost:8000/v1/runs/${runId}/traces`,
    expectedOptions: {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: 'mutx.tool.execution',
        attributes: { 'agent.id': agentId },
      }),
      fallbackMessage: 'Failed to add traces',
    },
  },
]

describe('legacy control-plane proxy routes', () => {
  beforeEach(() => {
    proxyJson.mockReset()
    proxyJson.mockResolvedValue(NextResponse.json({ proxied: true }, { status: 202 }))
    checkAgentOwnership.mockReset()
    checkAgentOwnership.mockResolvedValue(null)
    checkDeploymentOwnership.mockReset()
    checkDeploymentOwnership.mockResolvedValue(null)
  })

  it.each(cases)('$name', async (routeCase) => {
    const request = new NextRequest(routeCase.url, {
      method: routeCase.method,
      headers: {
        authorization: 'Bearer route-token',
        ...(routeCase.body === undefined ? {} : { 'Content-Type': 'application/json' }),
      },
      body: routeCase.body === undefined ? undefined : JSON.stringify(routeCase.body),
    })
    const handler = await routeCase.load()
    const response = await handler(request, {
      params: Promise.resolve(routeCase.params ?? {}),
    })

    expect(proxyJson).toHaveBeenCalledWith(
      request,
      routeCase.expectedUrl,
      routeCase.expectedOptions,
    )
    expect(response.status).toBe(202)

    if (routeCase.ownership === 'agent') {
      expect(checkAgentOwnership).toHaveBeenCalledWith(request, agentId)
    } else if (routeCase.ownership === 'deployment') {
      expect(checkDeploymentOwnership).toHaveBeenCalledWith(request, deploymentId)
    }
  })

  it('rejects unsupported deployment create fields before proxying', async () => {
    const request = new NextRequest('http://localhost:3000/api/deployments', {
      method: 'POST',
      headers: { authorization: 'Bearer route-token', 'Content-Type': 'application/json' },
      body: JSON.stringify({
        agent_id: deploymentAgentId,
        replicas: 2,
        environment: 'production',
      }),
    })
    const { POST } = await import('../../app/api/deployments/route')

    const response = await POST(request)

    expect(response.status).toBe(400)
    expect(proxyJson).not.toHaveBeenCalled()
  })
})
