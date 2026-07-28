import { NextRequest } from 'next/server'

import { getApiBaseUrl, hasAuthSession } from '@/app/api/_lib/controlPlane'
import { badRequest, unauthorized, withErrorHandling } from '@/app/api/_lib/errors'
import { proxyJson } from '@/app/api/_lib/proxy'

export const dynamic = 'force-dynamic'

type RuntimeProviderRouteProps = {
  params: Promise<{ provider: string }>
}

function validateProvider(provider: string) {
  const normalized = provider.trim().toLowerCase()
  return /^[a-z0-9][a-z0-9_-]{0,63}$/.test(normalized) ? normalized : null
}

export async function GET(request: NextRequest, { params }: RuntimeProviderRouteProps) {
  return withErrorHandling(async () => {
    if (!hasAuthSession(request)) {
      return unauthorized()
    }

    const { provider } = await params
    const validatedProvider = validateProvider(provider)
    if (!validatedProvider) {
      return badRequest('Invalid runtime provider')
    }

    return proxyJson(request, `${getApiBaseUrl()}/v1/runtime/providers/${encodeURIComponent(validatedProvider)}`, {
      fallbackMessage: 'Failed to fetch Pico runtime provider state',
    })
  })(request)
}

export async function PUT(request: NextRequest, { params }: RuntimeProviderRouteProps) {
  return withErrorHandling(async () => {
    if (!hasAuthSession(request)) {
      return unauthorized()
    }

    const { provider } = await params
    const validatedProvider = validateProvider(provider)
    if (!validatedProvider) {
      return badRequest('Invalid runtime provider')
    }

    let payload: unknown
    try {
      payload = await request.json()
    } catch {
      return badRequest('Invalid JSON in request body')
    }

    if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
      return badRequest('Runtime snapshot must be a JSON object')
    }

    return proxyJson(request, `${getApiBaseUrl()}/v1/runtime/providers/${encodeURIComponent(validatedProvider)}`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
      fallbackMessage: 'Failed to update Pico runtime provider state',
    })
  })(request)
}
