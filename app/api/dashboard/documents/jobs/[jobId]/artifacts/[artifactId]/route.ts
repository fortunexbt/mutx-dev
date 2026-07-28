import { NextRequest, NextResponse } from 'next/server'

import {
  applyAuthCookies,
  authenticatedFetch,
  getApiBaseUrl,
  hasAuthSession,
} from '@/app/api/_lib/controlPlane'
import { unauthorized, withErrorHandling } from '@/app/api/_lib/errors'

export const dynamic = 'force-dynamic'

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ jobId: string; artifactId: string }> },
) {
  return withErrorHandling(async () => {
    if (!hasAuthSession(request)) {
      return unauthorized()
    }

    const { jobId, artifactId } = await params
    const encodedJobId = encodeURIComponent(jobId)
    const encodedArtifactId = encodeURIComponent(artifactId)
    const { response, tokenRefreshed, refreshedTokens } = await authenticatedFetch(
      request,
      `${getApiBaseUrl()}/v1/documents/jobs/${encodedJobId}/artifacts/${encodedArtifactId}`,
      {
        method: 'GET',
      },
    )

    const blob = await response.arrayBuffer()
    const nextResponse = new NextResponse(blob, {
      status: response.status,
      headers: {
        'content-type': response.headers.get('content-type') || 'application/octet-stream',
        'content-disposition': response.headers.get('content-disposition') || '',
      },
    })
    if (tokenRefreshed && refreshedTokens) {
      applyAuthCookies(nextResponse, request, refreshedTokens)
    }
    return nextResponse
  })(request)
}
