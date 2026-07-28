import { NextRequest } from 'next/server'

const proxyJson = jest.fn()

jest.mock('../../app/api/_lib/controlPlane', () => ({
  getApiBaseUrl: () => 'http://localhost:8000',
}))

jest.mock('../../app/api/_lib/proxy', () => ({
  proxyJson,
}))

function mockRequest(url = 'http://localhost:3000/api/test') {
  return {
    url,
    nextUrl: new URL(url),
    text: async () => '',
  } as unknown as NextRequest
}

describe('dashboard governance route proxies', () => {
  beforeEach(() => {
    proxyJson.mockReset()
    proxyJson.mockResolvedValue(new Response(JSON.stringify({ ok: true }), { status: 200 }))
  })

  it('proxies governance security GET routes to /v1/security', async () => {
    const { GET } = await import('../../app/api/dashboard/governance/security/[...path]/route')

    await GET(mockRequest(), { params: Promise.resolve({ path: ['approvals'] }) })

    expect(proxyJson).toHaveBeenCalledWith(
      expect.anything(),
      'http://localhost:8000/v1/security/approvals',
      expect.objectContaining({ method: 'GET' }),
    )
  })

  it('proxies governance credentials GET routes', async () => {
    const { GET } = await import('../../app/api/dashboard/governance/credentials/[...path]/route')

    await GET(mockRequest(), { params: Promise.resolve({ path: ['backends'] }) })

    expect(proxyJson).toHaveBeenCalledWith(
      expect.anything(),
      'http://localhost:8000/v1/governance/credentials/backends',
      expect.objectContaining({ method: 'GET' }),
    )
  })

  it('encodes decoded catch-all segments before building an upstream URL', async () => {
    const { GET } = await import('../../app/api/dashboard/governance/credentials/[...path]/route')

    await GET(mockRequest(), { params: Promise.resolve({ path: ['get', 'team/secret'] }) })

    expect(proxyJson).toHaveBeenCalledWith(
      expect.anything(),
      'http://localhost:8000/v1/governance/credentials/get/team%2Fsecret',
      expect.objectContaining({ method: 'GET' }),
    )
  })

  it('proxies governance trust POST routes', async () => {
    const { POST } = await import('../../app/api/dashboard/governance/trust/[...path]/route')
    const request = {
      ...mockRequest(),
      text: async () => JSON.stringify({ delta: 10 }),
    } as unknown as NextRequest

    await POST(request, { params: Promise.resolve({ path: ['agent-1'] }) })

    expect(proxyJson).toHaveBeenCalledWith(
      expect.anything(),
      'http://localhost:8000/v1/governance/trust/agent-1',
      expect.objectContaining({ method: 'POST', body: JSON.stringify({ delta: 10 }) }),
    )
  })

  it('proxies governance trust collection route', async () => {
    const { GET } = await import('../../app/api/dashboard/governance/trust/route')

    await GET(mockRequest())

    expect(proxyJson).toHaveBeenCalledWith(
      expect.anything(),
      'http://localhost:8000/v1/governance/trust',
      expect.objectContaining({ method: 'GET' }),
    )
  })

  it('proxies governance lifecycle POST routes', async () => {
    const { POST } = await import('../../app/api/dashboard/governance/lifecycle/[...path]/route')
    const request = {
      ...mockRequest(),
      text: async () => JSON.stringify({ state: 'suspended' }),
    } as unknown as NextRequest

    await POST(request, { params: Promise.resolve({ path: ['agent-1'] }) })

    expect(proxyJson).toHaveBeenCalledWith(
      expect.anything(),
      'http://localhost:8000/v1/governance/lifecycle/agent-1',
      expect.objectContaining({ method: 'POST' }),
    )
  })

  it('proxies governance discovery scan routes', async () => {
    const { POST } = await import('../../app/api/dashboard/governance/discovery/[...path]/route')

    await POST(mockRequest(), { params: Promise.resolve({ path: ['scan'] }) })

    expect(proxyJson).toHaveBeenCalledWith(
      expect.anything(),
      'http://localhost:8000/v1/governance/discovery/scan',
      expect.objectContaining({ method: 'POST' }),
    )
  })

  it('proxies governance discovery collection route', async () => {
    const { GET } = await import('../../app/api/dashboard/governance/discovery/route')

    await GET(mockRequest())

    expect(proxyJson).toHaveBeenCalledWith(
      expect.anything(),
      'http://localhost:8000/v1/governance/discovery',
      expect.objectContaining({ method: 'GET' }),
    )
  })

  it('proxies governance attestation verify routes', async () => {
    const { POST } = await import('../../app/api/dashboard/governance/attestations/[...path]/route')

    await POST(mockRequest(), { params: Promise.resolve({ path: ['verify'] }) })

    expect(proxyJson).toHaveBeenCalledWith(
      expect.anything(),
      'http://localhost:8000/v1/governance/attestations/verify',
      expect.objectContaining({ method: 'POST' }),
    )
  })

  it('proxies governance attestation collection route', async () => {
    const { GET } = await import('../../app/api/dashboard/governance/attestations/route')

    await GET(mockRequest())

    expect(proxyJson).toHaveBeenCalledWith(
      expect.anything(),
      'http://localhost:8000/v1/governance/attestations',
      expect.objectContaining({ method: 'GET' }),
    )
  })

  it('proxies supervised runtime restart routes', async () => {
    const { POST } = await import('../../app/api/dashboard/runtime/governance/supervised/[[...path]]/route')
    const request = {
      ...mockRequest(),
      text: async () => '',
    } as unknown as NextRequest

    await POST(request, { params: Promise.resolve({ path: ['agent-1', 'restart'] }) })

    expect(proxyJson).toHaveBeenCalledWith(
      expect.anything(),
      'http://localhost:8000/v1/runtime/governance/supervised/agent-1/restart',
      expect.objectContaining({ method: 'POST' }),
    )
  })

  it('proxies governed runtime status route', async () => {
    const { GET } = await import('../../app/api/dashboard/runtime/governance/status/route')

    await GET(mockRequest())

    expect(proxyJson).toHaveBeenCalledWith(
      expect.anything(),
      'http://localhost:8000/v1/runtime/governance/status',
      expect.objectContaining({ method: 'GET' }),
    )
  })
})
