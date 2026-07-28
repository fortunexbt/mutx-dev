import { NextRequest, NextResponse } from 'next/server'

import {
  applyAuthCookies,
  authenticatedFetch,
  getApiBaseUrl,
  hasAuthSession,
} from '@/app/api/_lib/controlPlane'
import { unauthorized, withErrorHandling } from '@/app/api/_lib/errors'

export const dynamic = 'force-dynamic'

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ jobId: string }> },
) {
  return withErrorHandling(async () => {
    if (!hasAuthSession(request)) {
      return unauthorized()
    }

    const { jobId } = await params
    const formData = await request.formData()
    const { response, tokenRefreshed, refreshedTokens } = await authenticatedFetch(
      request,
      `${getApiBaseUrl()}/v1/reasoning/jobs/${encodeURIComponent(jobId)}/artifacts`,
      {
        method: 'POST',
        body: formData,
      },
    )

    const payload = await response.json().catch(() => ({ detail: 'Failed to upload reasoning artifact' }))
    const nextResponse = NextResponse.json(payload, { status: response.status })
    if (tokenRefreshed && refreshedTokens) {
      applyAuthCookies(nextResponse, request, refreshedTokens)
    }
    return nextResponse
  })(request)
}
