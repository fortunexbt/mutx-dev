import { NextRequest } from 'next/server'

import { getApiBaseUrl, hasAuthSession } from '@/app/api/_lib/controlPlane'
import { badRequest, unauthorized, withErrorHandling } from '@/app/api/_lib/errors'
import { proxyJson } from '@/app/api/_lib/proxy'
import { isPicoHost } from '@/lib/auth/redirects'
import { isPicoPaidPlanId } from '@/lib/pico/payments'

export const dynamic = 'force-dynamic'

export async function GET(request: NextRequest) {
  return withErrorHandling(async () => {
    if (!hasAuthSession(request)) {
      return unauthorized()
    }

    return proxyJson(request, `${getApiBaseUrl()}/v1/payments/subscription`, {
      cache: 'no-store',
      fallbackMessage: 'Failed to refresh subscription status',
    })
  })(request)
}

export async function POST(request: NextRequest) {
  return withErrorHandling(async () => {
    if (!hasAuthSession(request)) {
      return unauthorized()
    }

    let body: unknown
    try {
      body = await request.json()
    } catch {
      return badRequest('Invalid JSON in request body')
    }

    const planId = body && typeof body === 'object' && 'planId' in body
      ? (body as { planId?: unknown }).planId
      : null

    if (!isPicoPaidPlanId(planId)) {
      return badRequest('A supported planId is required')
    }

    const origin = new URL(request.url).origin
    const returnBasePath = isPicoHost(request.nextUrl.hostname) ? '' : '/pico'

    return proxyJson(request, `${getApiBaseUrl()}/v1/payments/checkout`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        plan_id: planId,
        success_url: `${origin}${returnBasePath}/pricing?checkout=success&plan=${planId}&session_id={CHECKOUT_SESSION_ID}`,
        cancel_url: `${origin}${returnBasePath}/pricing?checkout=canceled&plan=${planId}`,
      }),
      fallbackMessage: 'Failed to create checkout session',
    })
  })(request)
}
