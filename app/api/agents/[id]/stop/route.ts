import { NextRequest, NextResponse } from 'next/server'

import { getApiBaseUrl } from '@/app/api/_lib/controlPlane'
import { withErrorHandling } from '@/app/api/_lib/errors'
import { checkAgentOwnership } from '@/app/api/_lib/ownership'
import { proxyJson } from '@/app/api/_lib/proxy'


export const dynamic = 'force-dynamic'

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
): Promise<NextResponse> {
  return withErrorHandling(async () => {
    const { id } = await params

    // Check ownership before proceeding
    const ownershipError = await checkAgentOwnership(request, id)
    if (ownershipError) {
      return ownershipError
    }

    return proxyJson(request, `${getApiBaseUrl()}/v1/agents/${id}/stop`, {
      method: 'POST',
      fallbackMessage: 'Failed to stop agent',
    })
  })(request)
}
