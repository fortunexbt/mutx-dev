import { NextRequest } from 'next/server'

const proxyJson = jest.fn()

jest.mock('../../app/api/_lib/controlPlane', () => ({
  getApiBaseUrl: () => 'http://localhost:8000',
}))

jest.mock('../../app/api/_lib/proxy', () => ({
  proxyJson,
}))

function jsonRequest(
  url: string,
  method: string,
  payload: unknown,
  headers: Record<string, string> = {},
) {
  return new NextRequest(url, {
    method,
    headers: { 'Content-Type': 'application/json', ...headers },
    body: JSON.stringify(payload),
  })
}

describe('dashboard template route proxies', () => {
  beforeEach(() => {
    proxyJson.mockReset()
    proxyJson.mockResolvedValue(
      new Response(JSON.stringify({ id: 'proxied' }), {
        status: 201,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
  })

  it('forwards catalog state updates with their JSON body', async () => {
    const payload = {
      pinned_template_ids: ['personal_assistant'],
      recent_template_ids: [],
      deployment_count_by_template: { personal_assistant: 2 },
    }
    const request = jsonRequest(
      'http://localhost:3000/api/dashboard/templates/state',
      'PUT',
      payload,
    )
    const { PUT } = await import('../../app/api/dashboard/templates/state/route')

    await PUT(request)

    expect(proxyJson).toHaveBeenCalledWith(request, 'http://localhost:8000/v1/templates/state', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      fallbackMessage: 'Failed to update template catalog state',
    })
  })

  it('forwards custom template creation with its JSON body', async () => {
    const payload = {
      id: 'custom-contract',
      name: 'Custom Contract',
      system_prompt: 'Act as the contract assistant.',
    }
    const request = jsonRequest(
      'http://localhost:3000/api/dashboard/templates/custom',
      'POST',
      payload,
    )
    const { POST } = await import('../../app/api/dashboard/templates/custom/route')

    await POST(request)

    expect(proxyJson).toHaveBeenCalledWith(request, 'http://localhost:8000/v1/templates/custom', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      fallbackMessage: 'Failed to create custom template',
    })
  })

  it('forwards custom template updates with their JSON body', async () => {
    const payload = { name: 'Updated custom template' }
    const request = jsonRequest(
      'http://localhost:3000/api/dashboard/templates/custom/custom-contract',
      'PUT',
      payload,
    )
    const { PUT } = await import('../../app/api/dashboard/templates/custom/[templateId]/route')

    await PUT(request, { params: Promise.resolve({ templateId: 'custom-contract' }) })

    expect(proxyJson).toHaveBeenCalledWith(
      request,
      'http://localhost:8000/v1/templates/custom/custom-contract',
      {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
        fallbackMessage: 'Failed to update custom template',
      },
    )
  })

  it('forwards clone requests with their JSON body', async () => {
    const payload = { id: 'personal-copy', name: 'Personal Copy', version: '1' }
    const request = jsonRequest(
      'http://localhost:3000/api/dashboard/templates/personal_assistant/clone',
      'POST',
      payload,
    )
    const { POST } = await import('../../app/api/dashboard/templates/[templateId]/clone/route')

    await POST(request, { params: Promise.resolve({ templateId: 'personal_assistant' }) })

    expect(proxyJson).toHaveBeenCalledWith(
      request,
      'http://localhost:8000/v1/templates/personal_assistant/clone',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
        fallbackMessage: 'Failed to clone template',
      },
    )
  })

  it('keeps decoded template identifiers inside one upstream path segment', async () => {
    const payload = { id: 'safe-copy', name: 'Safe Copy', version: '1' }
    const request = jsonRequest(
      'http://localhost:3000/api/dashboard/templates/team%2Ftemplate/clone',
      'POST',
      payload,
    )
    const { POST } = await import('../../app/api/dashboard/templates/[templateId]/clone/route')

    await POST(request, { params: Promise.resolve({ templateId: 'team/template' }) })

    expect(proxyJson).toHaveBeenCalledWith(
      request,
      'http://localhost:8000/v1/templates/team%2Ftemplate/clone',
      expect.objectContaining({ method: 'POST', body: JSON.stringify(payload) }),
    )
  })

  it('forwards deployment bodies and idempotency keys', async () => {
    const payload = { name: 'Deploy once', replicas: 1 }
    const request = jsonRequest(
      'http://localhost:3000/api/dashboard/templates/personal_assistant/deploy',
      'POST',
      payload,
      { 'Idempotency-Key': 'deploy-once-contract' },
    )
    const { POST } = await import('../../app/api/dashboard/templates/[templateId]/deploy/route')

    await POST(request, { params: Promise.resolve({ templateId: 'personal_assistant' }) })

    expect(proxyJson).toHaveBeenCalledWith(
      request,
      'http://localhost:8000/v1/templates/personal_assistant/deploy',
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Idempotency-Key': 'deploy-once-contract',
        },
        body: JSON.stringify(payload),
        fallbackMessage: 'Failed to deploy starter template',
      },
    )
  })

  it('preserves bodyless DELETE semantics', async () => {
    const request = new NextRequest(
      'http://localhost:3000/api/dashboard/templates/custom/custom-contract',
      { method: 'DELETE' },
    )
    const { DELETE } = await import('../../app/api/dashboard/templates/custom/[templateId]/route')

    await DELETE(request, { params: Promise.resolve({ templateId: 'custom-contract' }) })

    expect(proxyJson).toHaveBeenCalledWith(
      request,
      'http://localhost:8000/v1/templates/custom/custom-contract',
      {
        method: 'DELETE',
        fallbackMessage: 'Failed to delete custom template',
      },
    )
  })

  it('returns a detail error and does not proxy malformed JSON', async () => {
    const request = new NextRequest('http://localhost:3000/api/dashboard/templates/custom', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: '{',
    })
    const { POST } = await import('../../app/api/dashboard/templates/custom/route')

    const response = await POST(request)

    expect(response.status).toBe(400)
    await expect(response.json()).resolves.toEqual({ detail: 'Invalid JSON in request body' })
    expect(proxyJson).not.toHaveBeenCalled()
  })
})
