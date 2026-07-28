import { NextRequest, NextResponse } from 'next/server'

import {
  applyAuthCookies,
  authenticatedFetch,
  getApiBaseUrl,
  hasAuthSession,
} from '@/app/api/_lib/controlPlane'
import { badRequest, unauthorized, withErrorHandling } from '@/app/api/_lib/errors'
import { malformedTutorUpstream, tutorProxyError } from '@/app/api/pico/tutor/contract'
import { normalizeTutorReplyPayload } from '@/lib/pico/tutor'

export const dynamic = 'force-dynamic'

export async function POST(request: NextRequest) {
  return withErrorHandling(async () => {
    if (!hasAuthSession(request)) {
      return unauthorized()
    }

    const body = await request.json().catch(() => ({}))
    const question = typeof body.question === 'string' ? body.question.trim() : ''
    const normalizedLessonSlug = typeof body.lessonSlug === 'string' ? body.lessonSlug.trim() : ''
    const lessonSlug = normalizedLessonSlug || null

    if (!question) {
      return badRequest('Question is required')
    }

    const apiBaseUrl = getApiBaseUrl()
    const { response, tokenRefreshed, refreshedTokens } = await authenticatedFetch(
      request,
      `${apiBaseUrl}/v1/pico/tutor`,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(request.headers.get('traceparent')
            ? { TRACEPARENT: request.headers.get('traceparent') as string }
            : {}),
          ...(request.headers.get('tracestate')
            ? { TRACESTATE: request.headers.get('tracestate') as string }
            : {}),
        },
        body: JSON.stringify({
          question,
          lessonSlug,
          progress: body.progress,
          setupContext: body.setupContext,
        }),
      },
    )

    const payload = await response.json().catch(() => null)
    let nextResponse: NextResponse
    if (!response.ok) {
      nextResponse = tutorProxyError(response.status, payload, 'Tutor request failed')
    } else {
      const normalizedReply = normalizeTutorReplyPayload(payload)
      nextResponse = normalizedReply
        ? NextResponse.json(normalizedReply, { status: response.status })
        : malformedTutorUpstream('Tutor returned an unverified or malformed response.')
    }

    if (tokenRefreshed && refreshedTokens) {
      applyAuthCookies(nextResponse, request, refreshedTokens)
    }

    return nextResponse
  })(request)
}
