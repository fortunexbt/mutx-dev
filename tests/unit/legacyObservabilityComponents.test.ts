import { readFileSync } from 'node:fs'
import { join } from 'node:path'

import {
  fetchDeploymentEvents,
  parseDeploymentEventHistory,
} from '../../components/app/Observability/StateTransitions'
import {
  fetchDeploymentLogs,
  parseDeploymentLogs,
} from '../../components/app/log-viewer'

function jsonResponse(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('legacy observability component contracts', () => {
  it('requests deployment events through the website proxy and parses the history envelope', async () => {
    const event = {
      id: 'event-1',
      deployment_id: 'deployment/one',
      event_type: 'started',
      status: 'success',
      node_id: 'node-1',
      error_message: null,
      created_at: '2026-07-28T10:00:00Z',
    }
    const request = jest.fn() as jest.MockedFunction<typeof fetch>
    request.mockResolvedValue(jsonResponse({
      deployment_id: 'deployment/one',
      deployment_status: 'running',
      items: [event],
      total: 1,
      skip: 0,
      limit: 50,
      has_more: false,
      event_type: null,
      status: null,
    }))

    await expect(fetchDeploymentEvents('deployment/one', request)).resolves.toEqual([event])
    expect(request).toHaveBeenCalledWith(
      '/api/deployments/deployment%2Fone/events?limit=50',
      { cache: 'no-store' },
    )
  })

  it('preserves an explicitly empty deployment event history', () => {
    expect(parseDeploymentEventHistory({ items: [], total: 0 })).toEqual([])
  })

  it('surfaces deployment event proxy errors instead of presenting an empty history', async () => {
    const request = jest.fn() as jest.MockedFunction<typeof fetch>
    request.mockResolvedValue(jsonResponse({ detail: 'Deployment events unavailable' }, 503))

    await expect(fetchDeploymentEvents('deployment-1', request)).rejects.toThrow(
      'Deployment events unavailable',
    )
  })

  it('requests deployment logs through the website proxy and parses backend items', async () => {
    const log = {
      id: 'log-1',
      agent_id: 'agent-1',
      level: 'warning',
      message: 'Replica is restarting',
      extra_data: '{"replica":2}',
      timestamp: '2026-07-28T10:01:00Z',
    }
    const request = jest.fn() as jest.MockedFunction<typeof fetch>
    request.mockResolvedValue(jsonResponse({
      deployment_id: 'deployment/one',
      items: [log],
      total: 1,
      skip: 0,
      limit: 200,
      has_more: false,
      level: 'warning',
    }))

    await expect(fetchDeploymentLogs('deployment/one', 'warning', request)).resolves.toEqual([log])
    expect(request).toHaveBeenCalledWith(
      '/api/deployments/deployment%2Fone/logs?limit=200&level=warning',
      { cache: 'no-store' },
    )
  })

  it('preserves an explicitly empty deployment log history', () => {
    expect(parseDeploymentLogs({ items: [], total: 0 })).toEqual([])
  })

  it('surfaces deployment log proxy errors instead of fabricating records', async () => {
    const request = jest.fn() as jest.MockedFunction<typeof fetch>
    request.mockResolvedValue(jsonResponse({ detail: 'Deployment logs unavailable' }, 502))

    await expect(fetchDeploymentLogs('deployment-1', '', request)).rejects.toThrow(
      'Deployment logs unavailable',
    )
  })

  it('renders explicit log empty/error states without contract-invented fields or demo records', () => {
    const source = readFileSync(
      join(process.cwd(), 'components/app/log-viewer.tsx'),
      'utf8',
    )

    expect(source).toContain('title="Logs unavailable"')
    expect(source).toContain("'No logs available'")
    expect(source).not.toContain('demo-')
    expect(source).not.toContain('dep.name')
    expect(source).not.toContain('entry.source')
  })
})
