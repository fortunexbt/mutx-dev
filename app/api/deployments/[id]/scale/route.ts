import { NextRequest, NextResponse } from 'next/server'

import { getApiBaseUrl } from '@/app/api/_lib/controlPlane'
import { withErrorHandling } from '@/app/api/_lib/errors'
import { checkDeploymentOwnership } from '@/app/api/_lib/ownership'
import { proxyJson } from '@/app/api/_lib/proxy'


export const dynamic = 'force-dynamic'

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
): Promise<NextResponse> {
  return withErrorHandling(async (req: Request) => {
    const { id } = await params

    // Check ownership before proceeding
    const ownershipError = await checkDeploymentOwnership(request, id)
    if (ownershipError) {
      return ownershipError
    }

    const body = await req.json()

    return proxyJson(request, `${getApiBaseUrl()}/v1/deployments/${id}/scale`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      fallbackMessage: 'Failed to scale deployment',
    })
  })(request)
}
