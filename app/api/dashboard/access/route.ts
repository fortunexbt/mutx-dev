import { NextRequest, NextResponse } from 'next/server'

import {
  applyAuthCookies,
  authenticatedFetch,
  clearAuthCookies,
  getApiBaseUrl,
  hasAuthSession,
} from '@/app/api/_lib/controlPlane'

export const dynamic = 'force-dynamic'

function unauthenticated(reason: 'missing_session' | 'expired_session' | 'access_denied') {
  return NextResponse.json({ authenticated: false, reason })
}

function applyRotatedCookies(
  response: NextResponse,
  request: NextRequest,
  result: Awaited<ReturnType<typeof authenticatedFetch>>,
) {
  if (result.tokenRefreshed && result.refreshedTokens) {
    applyAuthCookies(response, request, result.refreshedTokens)
  }
  return response
}

export async function GET(request: NextRequest): Promise<NextResponse> {
  if (!hasAuthSession(request)) {
    return unauthenticated('missing_session')
  }

  try {
    const result = await authenticatedFetch(request, `${getApiBaseUrl()}/v1/auth/me`, {
      cache: 'no-store',
    })
    const payload = await result.response
      .json()
      .catch(() => ({ detail: 'Dashboard access returned an invalid response' }))

    if (result.response.status === 401) {
      const response = unauthenticated('expired_session')
      clearAuthCookies(response, request)
      return response
    }

    if (result.response.status === 403) {
      return applyRotatedCookies(unauthenticated('access_denied'), request, result)
    }

    if (!result.response.ok) {
      return applyRotatedCookies(
        NextResponse.json(payload, { status: result.response.status }),
        request,
        result,
      )
    }

    return applyRotatedCookies(
      NextResponse.json({ authenticated: true, user: payload }),
      request,
      result,
    )
  } catch {
    return NextResponse.json(
      { detail: 'Dashboard access could not be verified' },
      { status: 503 },
    )
  }
}
