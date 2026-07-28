import { NextRequest, NextResponse } from 'next/server'

import {
  applyAuthCookies,
  authenticatedFetch,
  getApiBaseUrl,
  hasAuthSession,
} from '@/app/api/_lib/controlPlane'
import { unauthorized, withErrorHandling } from '@/app/api/_lib/errors'

export const dynamic = 'force-dynamic'

type SubscriptionPlan = 'free' | 'pro' | 'enterprise' | null

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

function extractString(value: unknown): string | null {
  return typeof value === 'string' && value.trim().length > 0 ? value.trim() : null
}

function normalizePlan(value: string | null): SubscriptionPlan {
  if (!value) {
    return null
  }

  const normalized = value.toLowerCase()
  if (normalized === 'enterprise') {
    return 'enterprise'
  }
  if (normalized === 'pro' || normalized === 'plus') {
    return 'pro'
  }
  if (normalized === 'free' || normalized === 'starter' || normalized === 'hobby') {
    return 'free'
  }

  return null
}

function extractPlan(payload: unknown): SubscriptionPlan {
  if (!isRecord(payload)) {
    return null
  }

  const directPlan = normalizePlan(extractString(payload.plan))
  if (directPlan) {
    return directPlan
  }

  const subscription = payload.subscription
  if (isRecord(subscription)) {
    return normalizePlan(extractString(subscription.plan))
  }

  return null
}

function extractOrgName(payload: unknown): string {
  if (!isRecord(payload)) {
    return 'MUTX'
  }

  const preferred = extractString(payload.display_name) || extractString(payload.name)
  if (preferred) {
    return preferred
  }

  const email = extractString(payload.email)
  if (email && email.includes('@')) {
    return email.split('@')[0]
  }

  return 'MUTX'
}

export async function GET(request: NextRequest): Promise<NextResponse> {
  return withErrorHandling(async () => {
    if (!hasAuthSession(request)) {
      return unauthorized()
    }

    const apiBaseUrl = getApiBaseUrl()
    const meResult = await authenticatedFetch(request, `${apiBaseUrl}/v1/auth/me`, {
      cache: 'no-store',
    })
    const mePayload = await meResult.response
      .json()
      .catch(() => ({ detail: 'Failed to fetch dashboard settings' }))

    if (!meResult.response.ok) {
      const nextResponse = NextResponse.json(mePayload, {
        status: meResult.response.status,
      })

      if (meResult.tokenRefreshed && meResult.refreshedTokens) {
        applyAuthCookies(nextResponse, request, meResult.refreshedTokens)
      }

      return nextResponse
    }

    let refreshedTokens = meResult.refreshedTokens
    const subscriptionPayload = await (async () => {
      try {
        const subscriptionResult = await authenticatedFetch(
          request,
          `${apiBaseUrl}/v1/payments/subscription`,
          { cache: 'no-store' },
        )
        const payload = await subscriptionResult.response.json().catch(() => null)

        if (!refreshedTokens && subscriptionResult.tokenRefreshed) {
          refreshedTokens = subscriptionResult.refreshedTokens
        }

        return subscriptionResult.response.ok ? payload : null
      } catch {
        return null
      }
    })()

    const subscription = extractPlan(subscriptionPayload) || extractPlan(mePayload)
    const interfaceMode = subscription === 'pro' || subscription === 'enterprise' ? 'full' : 'essential'
    const nextResponse = NextResponse.json({
      interfaceMode,
      orgName: extractOrgName(mePayload),
      subscription,
      user: mePayload,
    })

    if (refreshedTokens) {
      applyAuthCookies(nextResponse, request, refreshedTokens)
    }

    return nextResponse
  })(request)
}
