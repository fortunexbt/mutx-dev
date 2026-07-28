import { NextRequest } from 'next/server'

import { withErrorHandling } from '@/app/api/_lib/errors'
import { getApiBaseUrl } from '@/app/api/_lib/controlPlane'
import { proxyJson } from '@/app/api/_lib/proxy'

export const dynamic = 'force-dynamic'

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ jobId: string }> },
) {
  return withErrorHandling(async () => {
    const { jobId } = await params
    return proxyJson(request, `${getApiBaseUrl()}/v1/reasoning/jobs/${encodeURIComponent(jobId)}`, {
      method: 'GET',
      fallbackMessage: 'Failed to fetch reasoning job',
    })
  })(request)
}
