import { NextRequest } from 'next/server'

import { getApiBaseUrl, hasAuthSession } from '@/app/api/_lib/controlPlane'
import { badRequest, unauthorized, withErrorHandling } from '@/app/api/_lib/errors'
import { proxyJson } from '@/app/api/_lib/proxy'

export const dynamic = 'force-dynamic'

const COACH_SESSION_ID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/

export async function GET(request: NextRequest) {
  return withErrorHandling(async () => {
    if (request.nextUrl.searchParams.get('view') === 'coach_session') {
      const targetUrl = new URL(`${getApiBaseUrl()}/v1/pico/session`)
      const sessionId = request.nextUrl.searchParams.get('session_id')?.trim()
      if (sessionId) {
        targetUrl.searchParams.set('session_id', sessionId)
      }
      return proxyJson(request, targetUrl.toString(), {
        fallbackMessage: 'Failed to resume Pico onboarding session',
      })
    }

    const query = request.nextUrl.search
    return proxyJson(
      request,
      `${getApiBaseUrl()}/v1/onboarding${query}`,
      { fallbackMessage: 'Failed to fetch Pico onboarding state' },
    )
  })(request)
}

export async function POST(request: NextRequest) {
  return withErrorHandling(async () => {
    if (!hasAuthSession(request)) {
      return unauthorized()
    }

    let payload: unknown
    try {
      payload = await request.json()
    } catch {
      return badRequest('Invalid JSON in request body')
    }

    if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
      return badRequest('A JSON object is required')
    }

    const body = payload as Record<string, unknown>
    if (body.action === 'coach_message') {
      const message = typeof body.message === 'string' ? body.message.trim() : ''
      const sessionId = typeof body.session_id === 'string' ? body.session_id.trim() : null
      const requestId = typeof body.request_id === 'string' ? body.request_id.trim() : null

      if (!message) {
        return badRequest('Message is required')
      }
      if (message.length > 6000) {
        return badRequest('Message is too long')
      }
      if (sessionId && sessionId.length > 36) {
        return badRequest('Invalid onboarding session ID')
      }
      if (requestId && requestId.length > 64) {
        return badRequest('Invalid onboarding request ID')
      }

      return proxyJson(request, `${getApiBaseUrl()}/v1/pico/chat`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          message,
          ...(sessionId ? { session_id: sessionId } : {}),
          ...(requestId ? { request_id: requestId } : {}),
        }),
        fallbackMessage: 'Pico onboarding coach request failed',
      })
    }

    return proxyJson(request, `${getApiBaseUrl()}/v1/onboarding`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(body),
      fallbackMessage: 'Failed to update Pico onboarding state',
    })
  })(request)
}

export async function DELETE(request: NextRequest) {
  return withErrorHandling(async () => {
    if (!hasAuthSession(request)) {
      return unauthorized()
    }

    const targetUrl = new URL(`${getApiBaseUrl()}/v1/pico/session`)
    const sessionId = request.nextUrl.searchParams.get('session_id')?.trim()
    if (sessionId && !COACH_SESSION_ID_PATTERN.test(sessionId)) {
      return badRequest('Invalid onboarding session ID')
    }
    if (sessionId) {
      targetUrl.searchParams.set('session_id', sessionId)
    }

    return proxyJson(request, targetUrl.toString(), {
      method: 'DELETE',
      fallbackMessage: 'Failed to reset Pico onboarding session',
    })
  })(request)
}
