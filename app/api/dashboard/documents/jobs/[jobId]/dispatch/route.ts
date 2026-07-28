import { NextRequest } from 'next/server'

import { withErrorHandling } from '@/app/api/_lib/errors'
import { getApiBaseUrl } from '@/app/api/_lib/controlPlane'
import { proxyJson } from '@/app/api/_lib/proxy'

export const dynamic = 'force-dynamic'

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ jobId: string }> },
) {
  return withErrorHandling(async () => {
    const { jobId } = await params
    const encodedJobId = encodeURIComponent(jobId)
    const body = await request.json()
    return proxyJson(request, `${getApiBaseUrl()}/v1/documents/jobs/${encodedJobId}/dispatch`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      fallbackMessage: 'Failed to dispatch document job',
    })
  })(request)
}
