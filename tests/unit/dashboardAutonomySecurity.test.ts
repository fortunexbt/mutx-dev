import { promises as fs } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'

import { NextRequest } from 'next/server'

const applyAuthCookies = jest.fn()
const authenticatedFetch = jest.fn()
const hasAuthSession = jest.fn()

jest.mock('../../app/api/_lib/controlPlane', () => ({
  applyAuthCookies,
  authenticatedFetch,
  getApiBaseUrl: () => 'http://localhost:8000',
  hasAuthSession,
}))

const originalEnvironment = {
  root: process.env.MUTX_AUTONOMY_ROOT,
  capability: process.env.MUTX_LOCAL_AUTONOMY_CAPABILITY,
  desktopMode: process.env.MUTX_DESKTOP_MODE,
  staleAfterSeconds: process.env.MUTX_AUTONOMY_STALE_AFTER_SECONDS,
}

const temporaryRoots: string[] = []

function restoreEnvironment(name: keyof typeof originalEnvironment, environmentName: string) {
  const value = originalEnvironment[name]
  if (value === undefined) delete process.env[environmentName]
  else process.env[environmentName] = value
}

async function makeRoot() {
  const root = await fs.mkdtemp(path.join(tmpdir(), 'mutx-autonomy-test-'))
  temporaryRoots.push(root)
  return root
}

async function writeSource(root: string, relativePath: string, value: unknown, raw = false) {
  const target = path.join(root, relativePath)
  await fs.mkdir(path.dirname(target), { recursive: true })
  await fs.writeFile(target, raw ? String(value) : JSON.stringify(value), 'utf8')
}

function request() {
  return new NextRequest('http://localhost:3000/api/dashboard/autonomy')
}

function authenticatedResult(
  status = 200,
  refresh?: { access_token: string; refresh_token: string; expires_in: number },
) {
  return {
    response: new Response(JSON.stringify({ id: 'operator-1' }), {
      status,
      headers: { 'Content-Type': 'application/json' },
    }),
    tokenRefreshed: Boolean(refresh),
    ...(refresh ? { refreshedTokens: refresh } : {}),
  }
}

describe('dashboard autonomy security contract', () => {
  beforeEach(() => {
    jest.resetModules()
    applyAuthCookies.mockReset()
    authenticatedFetch.mockReset()
    hasAuthSession.mockReset()
    hasAuthSession.mockReturnValue(true)
    authenticatedFetch.mockResolvedValue(authenticatedResult())
    process.env.MUTX_LOCAL_AUTONOMY_CAPABILITY = 'enabled'
    delete process.env.MUTX_DESKTOP_MODE
    delete process.env.MUTX_AUTONOMY_STALE_AFTER_SECONDS
  })

  afterEach(async () => {
    restoreEnvironment('root', 'MUTX_AUTONOMY_ROOT')
    restoreEnvironment('capability', 'MUTX_LOCAL_AUTONOMY_CAPABILITY')
    restoreEnvironment('desktopMode', 'MUTX_DESKTOP_MODE')
    restoreEnvironment('staleAfterSeconds', 'MUTX_AUTONOMY_STALE_AFTER_SECONDS')

    await Promise.all(
      temporaryRoots.splice(0).map((root) => fs.rm(root, { recursive: true, force: true })),
    )
  })

  it('rejects missing sessions before verifying auth or resolving local files', async () => {
    hasAuthSession.mockReturnValue(false)
    process.env.MUTX_AUTONOMY_ROOT = '/path/that/must/not/be/read'

    const { GET } = await import('../../app/api/dashboard/autonomy/route')
    const response = await GET(request())

    expect(response.status).toBe(401)
    await expect(response.json()).resolves.toEqual({
      status: 'error',
      error: { code: 'UNAUTHORIZED', message: 'Unauthorized' },
    })
    expect(authenticatedFetch).not.toHaveBeenCalled()
  })

  it('uses the dashboard auth verification and refresh-cookie contract', async () => {
    const root = await makeRoot()
    await writeSource(root, '.autonomy/daemon-status.json', {
      status: 'idle',
      heartbeat_at: new Date().toISOString(),
      active_runners: [],
    })
    process.env.MUTX_AUTONOMY_ROOT = root
    const refreshedTokens = {
      access_token: 'refreshed-access',
      refresh_token: 'refreshed-refresh',
      expires_in: 1800,
    }
    authenticatedFetch.mockResolvedValue(authenticatedResult(200, refreshedTokens))

    const nextRequest = request()
    const { GET } = await import('../../app/api/dashboard/autonomy/route')
    const response = await GET(nextRequest)

    expect(response.status).toBe(200)
    expect(authenticatedFetch).toHaveBeenCalledWith(
      nextRequest,
      'http://localhost:8000/v1/auth/me',
      { cache: 'no-store' },
    )
    expect(applyAuthCookies).toHaveBeenCalledWith(response, nextRequest, refreshedTokens)
    expect(response.headers.get('cache-control')).toBe('private, no-store, max-age=0')
  })

  it('fails closed outside desktop when the explicit local capability is disabled', async () => {
    const root = await makeRoot()
    await writeSource(root, '.autonomy/daemon-status.json', '{ malformed', true)
    process.env.MUTX_AUTONOMY_ROOT = root
    delete process.env.MUTX_LOCAL_AUTONOMY_CAPABILITY

    const { GET } = await import('../../app/api/dashboard/autonomy/route')
    const response = await GET(request())

    expect(response.status).toBe(403)
    await expect(response.json()).resolves.toEqual({
      status: 'error',
      error: {
        code: 'FORBIDDEN',
        message: 'Local autonomy is available only in an approved local capability context',
      },
    })
  })

  it('rejects traversal and symlinks that resolve outside the allowlisted root', async () => {
    const root = await makeRoot()
    const outside = await makeRoot()
    await writeSource(outside, 'daemon-status.json', {
      status: 'running',
      heartbeat_at: new Date().toISOString(),
      active_runners: [],
    })
    await fs.mkdir(path.join(root, '.autonomy'), { recursive: true })
    await fs.symlink(
      path.join(outside, 'daemon-status.json'),
      path.join(root, '.autonomy', 'daemon-status.json'),
    )
    process.env.MUTX_AUTONOMY_ROOT = root

    const { resolveAutonomyReadPath, resolveAutonomyRoot } = await import(
      '../../app/api/dashboard/autonomy/autonomyData'
    )
    const resolvedRoot = await resolveAutonomyRoot(root)
    await expect(resolveAutonomyReadPath(resolvedRoot, '../daemon-status.json')).rejects.toEqual(
      expect.objectContaining({ code: 'unsafe_path' }),
    )

    const { GET } = await import('../../app/api/dashboard/autonomy/route')
    const response = await GET(request())
    const payload = await response.json()

    expect(response.status).toBe(503)
    expect(payload).toEqual({
      status: 'error',
      error: {
        code: 'SERVICE_UNAVAILABLE',
        message: 'Local autonomy data could not be read safely',
      },
    })
    expect(JSON.stringify(payload)).not.toContain(outside)
  })

  it('returns a redacted stale snapshot without treating old runner files as live', async () => {
    const root = await makeRoot()
    await writeSource(root, '.autonomy/daemon-status.json', {
      status: 'running',
      heartbeat_at: '2000-01-01T00:00:00.000Z',
      repo_root: root,
      pid: 4242,
      last_error: `Failure in ${root}/private/daemon.py`,
      active_runners: [
        {
          task_id: `task-from-${root}/queue.json`,
          lane: 'codex',
          runner: 'worker-1',
          pid: 5252,
          started_at: '2000-01-01T00:00:00.000Z',
        },
      ],
    })
    await writeSource(root, 'mutx-engineering-agents/dispatch/action-queue.json', {
      items: [
        {
          id: 'task-1',
          title: `Repair ${root}/src/private.ts`,
          status: 'running',
        },
      ],
    })
    await writeSource(
      root,
      'reports/autonomy-status.jsonl',
      `${JSON.stringify({
        task_id: 'task-1',
        status: 'running',
        summary: 'Trace written to /Users/operator/private/report.log',
        updated_at: '2000-01-01T00:00:00.000Z',
      })}\n`,
      true,
    )
    process.env.MUTX_AUTONOMY_ROOT = root

    const { GET } = await import('../../app/api/dashboard/autonomy/route')
    const response = await GET(request())
    const payload = await response.json()
    const serialized = JSON.stringify(payload)

    expect(response.status).toBe(200)
    expect(payload).toEqual(
      expect.objectContaining({
        scope: 'local-only',
        availability: 'partial',
        freshness: expect.objectContaining({ state: 'stale' }),
        daemon: expect.objectContaining({ reportedStatus: 'running', live: false }),
      }),
    )
    expect(payload.queue.running[0].title).toContain('[redacted]')
    expect(payload.reports[0].summary).toContain('[redacted]')
    expect(serialized).not.toContain(root)
    expect(serialized).not.toContain('/Users/operator')
    expect(serialized).not.toContain('repo_root')
    expect(serialized).not.toContain('last_error')
    expect(serialized).not.toContain('pid')
  })

  it('returns generic 503 errors for malformed sources without leaking file details', async () => {
    const root = await makeRoot()
    await writeSource(root, '.autonomy/daemon-status.json', '{ "status": ', true)
    process.env.MUTX_AUTONOMY_ROOT = root

    const { GET } = await import('../../app/api/dashboard/autonomy/route')
    const response = await GET(request())
    const payload = await response.json()

    expect(response.status).toBe(503)
    expect(payload).toEqual({
      status: 'error',
      error: {
        code: 'SERVICE_UNAVAILABLE',
        message: 'Local autonomy data could not be read safely',
      },
    })
    expect(JSON.stringify(payload)).not.toContain(root)
    expect(JSON.stringify(payload)).not.toContain('daemon-status.json')
  })

  it('returns 404 when the configured allowlisted root does not exist', async () => {
    const parent = await makeRoot()
    process.env.MUTX_AUTONOMY_ROOT = path.join(parent, 'missing-workspace')

    const { GET } = await import('../../app/api/dashboard/autonomy/route')
    const response = await GET(request())

    expect(response.status).toBe(404)
    await expect(response.json()).resolves.toEqual({
      status: 'error',
      error: { code: 'NOT_FOUND', message: 'No local autonomy data was found' },
    })
  })
})
