import { NextRequest, NextResponse } from 'next/server'

import {
  applyAuthCookies,
  authenticatedFetch,
  getApiBaseUrl,
  hasAuthSession,
} from '@/app/api/_lib/controlPlane'
import { serviceUnavailable, unauthorized, withErrorHandling } from '@/app/api/_lib/errors'

export const dynamic = 'force-dynamic'

export async function POST(request: NextRequest) {
  return withErrorHandling(async () => {
    if (!hasAuthSession(request)) {
      return unauthorized()
    }

    const idempotencyKey = request.headers.get('idempotency-key')
    if (!idempotencyKey) {
      return NextResponse.json({ detail: 'Idempotency-Key is required' }, { status: 400 })
    }

    const formData = await request.formData()
    let upstream
    try {
      upstream = await authenticatedFetch(
        request,
        `${getApiBaseUrl()}/v1/documents/jobs/submit`,
        {
          method: 'POST',
          headers: { 'Idempotency-Key': idempotencyKey },
          body: formData,
        },
      )
    } catch {
      return serviceUnavailable('Document service is unreachable; no execution was confirmed')
    }

    const { response, tokenRefreshed, refreshedTokens } = upstream
    const payload = await response.json().catch(() => ({
      detail: 'Document service returned an invalid response',
    }))
    const nextResponse = NextResponse.json(payload, { status: response.status })
    if (tokenRefreshed && refreshedTokens) {
      applyAuthCookies(nextResponse, request, refreshedTokens)
    }
    return nextResponse
  })(request)
}
