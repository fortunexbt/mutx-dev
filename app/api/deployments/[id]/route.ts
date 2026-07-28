import { NextRequest, NextResponse } from 'next/server'

import { getApiBaseUrl } from '@/app/api/_lib/controlPlane'
import { withErrorHandling } from '@/app/api/_lib/errors'
import { checkDeploymentOwnership } from '@/app/api/_lib/ownership'
import { proxyJson } from '@/app/api/_lib/proxy'


export const dynamic = 'force-dynamic'

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
): Promise<NextResponse> {
  return withErrorHandling(async () => {
    const { id } = await params

    // Check ownership before proceeding
    const ownershipError = await checkDeploymentOwnership(request, id)
    if (ownershipError) {
      return ownershipError
    }

    return proxyJson(request, `${getApiBaseUrl()}/v1/deployments/${id}`, {
      fallbackMessage: 'Failed to fetch deployment',
    })
  })(request)
}

export async function DELETE(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
): Promise<NextResponse> {
  return withErrorHandling(async () => {
    const { id } = await params

    // Check ownership before proceeding
    const ownershipError = await checkDeploymentOwnership(request, id)
    if (ownershipError) {
      return ownershipError
    }

    return proxyJson(request, `${getApiBaseUrl()}/v1/deployments/${id}`, {
      method: 'DELETE',
      fallbackMessage: 'Failed to delete deployment',
    })
  })(request)
}
