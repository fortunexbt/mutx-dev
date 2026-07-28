import type { NextRequest } from 'next/server'

const applyAuthCookies = jest.fn()
const authenticatedFetch = jest.fn()
const hasAuthSession = jest.fn()

jest.mock('../../app/api/_lib/controlPlane', () => ({
  getApiBaseUrl: () => 'http://localhost:8000',
  applyAuthCookies,
  authenticatedFetch,
  hasAuthSession,
}))

function mockJsonRequest(body: unknown) {
  return {
    json: async () => body,
    headers: {
      get: () => null,
    },
    cookies: {
      get: () => undefined,
    },
  } as unknown as NextRequest
}

const entitlement = {
  authenticated: true,
  plan: 'starter',
  tutorAccess: true,
  minimumPlan: 'starter',
  byokAccess: false,
  byokMinimumPlan: 'pro',
}

const tutorReply = {
  title: 'Create a scheduled workflow',
  summary: 'Open the scheduling lesson and create one cron workflow.',
  answer: 'Open the scheduling lesson and create one cron workflow.',
  confidence: 'high',
  nextActions: ['Open the scheduling lesson', 'Create one cron workflow'],
  lessons: [
    {
      id: 'create-a-scheduled-workflow',
      title: 'Create a scheduled workflow',
      href: '/pico/academy/create-a-scheduled-workflow',
    },
  ],
  docs: [
    {
      label: 'github.com',
      href: 'https://github.com/nousresearch/hermes-agent',
      sourcePath: 'github.com',
    },
  ],
  recommendedLessonIds: ['create-a-scheduled-workflow'],
  escalate: false,
  structured: {
    situation: 'The workflow is blocked at scheduling.',
    diagnosis: 'Use the scheduling lesson as the primary recovery path.',
    steps: ['Open the lesson', 'Create one cron job'],
    commands: [],
    verify: ['The cron entry exists and is visible after reload.'],
    ifThisFails: ['Paste the failing schedule output.'],
    officialLinks: [],
    sources: [],
  },
  intent: 'integrate',
  skillLevel: 'intermediate',
  usedOfficialFallback: false,
  entitlement,
  generation: {
    provider: 'openai',
    source: 'platform',
    model: 'gpt-5-mini',
    responseId: 'chatcmpl-route-proof',
    completedAt: '2026-07-28T12:00:00Z',
  },
}

describe('pico tutor route', () => {
  beforeEach(() => {
    jest.resetModules()
    applyAuthCookies.mockReset()
    authenticatedFetch.mockReset()
    hasAuthSession.mockReset()
    hasAuthSession.mockReturnValue(true)
  })

  it('returns 401 when no auth session exists', async () => {
    hasAuthSession.mockReturnValue(false)

    const { POST } = await import('../../app/api/pico/tutor/route')
    const response = await POST(
      mockJsonRequest({ question: 'How do I debug my run?' }) as never,
    )

    expect(response.status).toBe(401)
    await expect(response.json()).resolves.toEqual({
      status: 'error',
      error: { code: 'UNAUTHORIZED', message: 'Unauthorized' },
    })
    expect(authenticatedFetch).not.toHaveBeenCalled()
  })

  it('returns a grounded tutor reply for a valid question', async () => {
    const { POST } = await import('../../app/api/pico/tutor/route')
    authenticatedFetch.mockResolvedValue({
      response: {
        status: 200,
        ok: true,
        json: async () => tutorReply,
      },
      tokenRefreshed: false,
    })

    const response = await POST(
      mockJsonRequest({
        question: 'How do I schedule a cron workflow for my agent?',
        lessonSlug: 'create-a-scheduled-workflow',
      }) as never,
    )

    expect(response.status).toBe(200)
    await expect(response.json()).resolves.toMatchObject({
      title: 'Create a scheduled workflow',
      recommendedLessonIds: expect.arrayContaining(['create-a-scheduled-workflow']),
      lessons: expect.arrayContaining([
        expect.objectContaining({ href: '/pico/academy/create-a-scheduled-workflow' }),
      ]),
      nextActions: expect.any(Array),
      structured: expect.objectContaining({
        diagnosis: expect.any(String),
      }),
    })
  })

  it('trims the forwarded question and normalizes a blank lesson slug before proxying upstream', async () => {
    const { POST } = await import('../../app/api/pico/tutor/route')
    const request = mockJsonRequest({
      question: '  How do I deploy my starter agent?  ',
      lessonSlug: '   ',
      progress: { completedLessons: ['run-your-first-agent'] },
    })

    authenticatedFetch.mockResolvedValue({
      response: {
        status: 200,
        ok: true,
        json: async () => tutorReply,
      },
      tokenRefreshed: false,
    })

    const response = await POST(request as never)

    expect(response.status).toBe(200)
    expect(authenticatedFetch).toHaveBeenCalledWith(
      request,
      'http://localhost:8000/v1/pico/tutor',
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          question: 'How do I deploy my starter agent?',
          lessonSlug: null,
          progress: { completedLessons: ['run-your-first-agent'] },
          setupContext: undefined,
        }),
      },
    )
  })

  it('rejects empty questions', async () => {
    const { POST } = await import('../../app/api/pico/tutor/route')

    const response = await POST(
      mockJsonRequest({ question: '   ' }) as never,
    )

    expect(response.status).toBe(400)
    await expect(response.json()).resolves.toMatchObject({
      status: 'error',
      error: {
        code: 'BAD_REQUEST',
        message: 'Question is required',
      },
    })
  })

  it.each([
    [403, 'TUTOR_PLAN_REQUIRED'],
    [429, 'TUTOR_RATE_LIMITED'],
    [503, 'TUTOR_MODEL_UNAVAILABLE'],
  ])('preserves upstream HTTP %i with a distinct error contract', async (status, code) => {
    authenticatedFetch.mockResolvedValue({
      response: {
        status,
        ok: false,
        json: async () => ({ detail: { code, message: `failure ${status}` } }),
      },
      tokenRefreshed: false,
    })

    const { POST } = await import('../../app/api/pico/tutor/route')
    const response = await POST(mockJsonRequest({ question: 'Why is this blocked?' }) as never)

    expect(response.status).toBe(status)
    await expect(response.json()).resolves.toMatchObject({
      status: 'error',
      error: { code, message: `failure ${status}` },
    })
  })

  it('returns 502 instead of forwarding an unproven answer', async () => {
    authenticatedFetch.mockResolvedValue({
      response: {
        status: 200,
        ok: true,
        json: async () => ({ answer: 'plausible but unproven' }),
      },
      tokenRefreshed: false,
    })

    const { POST } = await import('../../app/api/pico/tutor/route')
    const response = await POST(mockJsonRequest({ question: 'What should I do?' }) as never)

    expect(response.status).toBe(502)
    await expect(response.json()).resolves.toMatchObject({
      error: { code: 'TUTOR_MALFORMED_RESPONSE' },
    })
  })
})
