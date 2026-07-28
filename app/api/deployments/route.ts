import { NextRequest, NextResponse } from 'next/server'

import { getApiBaseUrl, hasAuthSession } from '@/app/api/_lib/controlPlane'
import { unauthorized, withErrorHandling } from '@/app/api/_lib/errors'
import { proxyJson } from '@/app/api/_lib/proxy'
import { schemas, validateRequest } from '@/app/api/_lib/validation'


export const dynamic = 'force-dynamic'

/**
 * CLI-compatible deployments endpoint.
 * Proxies directly to control plane without user filtering.
 */
export async function GET(request: NextRequest): Promise<NextResponse> {
  return withErrorHandling(async () => {
    const query = new URL(request.url).search
    return proxyJson(request, `${getApiBaseUrl()}/v1/deployments${query}`, {
      headers: { 'Content-Type': 'application/json' },
      fallbackMessage: 'Failed to fetch deployments',
    })
  })(request)
}

export async function POST(request: NextRequest): Promise<NextResponse> {
  return withErrorHandling(async () => {
    if (!hasAuthSession(request)) {
      return unauthorized()
    }

    const validation = await validateRequest(schemas.deploymentCreate, request)
    if (!validation.success) {
      return validation.response
    }

    return proxyJson(request, `${getApiBaseUrl()}/v1/deployments`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(validation.data),
      fallbackMessage: 'Failed to create deployment',
    })
  })(request)
}
