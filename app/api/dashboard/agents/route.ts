import { NextRequest, NextResponse } from 'next/server'

import {
  applyAuthCookies,
  authenticatedFetch,
  getApiBaseUrl,
  hasAuthSession,
} from '@/app/api/_lib/controlPlane'
import { validateRequest, schemas } from '@/app/api/_lib/validation'
import { withErrorHandling, unauthorized } from '@/app/api/_lib/errors'


export const dynamic = 'force-dynamic'

/**
 * Dashboard agents endpoint.
 * Ownership is enforced by the backend - it derives ownership from the auth token.
 * No need to pass user_id or call /auth/me first.
 */
export async function GET(request: NextRequest): Promise<NextResponse> {
  return withErrorHandling(async (_req: Request) => {
    if (!hasAuthSession(request)) {
      return unauthorized()
    }

    const skip = request.nextUrl.searchParams.get('skip') ?? '0'
    const limit = request.nextUrl.searchParams.get('limit') ?? '20'
    const query = new URLSearchParams({ skip, limit })

    const { response, tokenRefreshed, refreshedTokens } = await authenticatedFetch(
      request,
      `${getApiBaseUrl()}/v1/agents?${query.toString()}`,
      { cache: 'no-store' }
    )

    const payload = await response.json().catch(() => ({ detail: 'Failed to fetch agents' }))
    const nextResponse = NextResponse.json(payload, { status: response.status })

    if (tokenRefreshed && refreshedTokens) {
      applyAuthCookies(nextResponse, request, refreshedTokens)
    }

    return nextResponse
  })(request)
}

export async function POST(request: NextRequest): Promise<NextResponse> {
  return withErrorHandling(async (req: Request) => {
    if (!hasAuthSession(request)) {
      return unauthorized()
    }

    const validation = await validateRequest(schemas.agentCreate, req)
    if (!validation.success) {
      return validation.response
    }

    const { response, tokenRefreshed, refreshedTokens } = await authenticatedFetch(
      request,
      `${getApiBaseUrl()}/v1/agents`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(validation.data),
        cache: 'no-store',
      }
    )

    const payload = await response.json().catch(() => ({ detail: 'Failed to create agent' }))
    const nextResponse = NextResponse.json(payload, { status: response.status })

    if (tokenRefreshed && refreshedTokens) {
      applyAuthCookies(nextResponse, request, refreshedTokens)
    }

    return nextResponse
  })(request)
}
