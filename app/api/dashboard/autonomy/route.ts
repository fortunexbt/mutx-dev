import { NextRequest, NextResponse } from 'next/server'

import {
  applyAuthCookies,
  authenticatedFetch,
  getApiBaseUrl,
  hasAuthSession,
} from '@/app/api/_lib/controlPlane'
import {
  AutonomyDataError,
  loadAutonomySnapshot,
} from '@/app/api/dashboard/autonomy/autonomyData'

export const dynamic = 'force-dynamic'

type ErrorCode =
  | 'UNAUTHORIZED'
  | 'FORBIDDEN'
  | 'NOT_FOUND'
  | 'SERVICE_UNAVAILABLE'

function jsonResponse(payload: unknown, status: number) {
  return NextResponse.json(payload, {
    status,
    headers: {
      'Cache-Control': 'private, no-store, max-age=0',
      'X-Content-Type-Options': 'nosniff',
    },
  })
}

function errorResponse(code: ErrorCode, message: string, status: number) {
  return jsonResponse({ status: 'error', error: { code, message } }, status)
}

function localCapabilityEnabled() {
  return (
    process.env.MUTX_DESKTOP_MODE === 'true' ||
    process.env.MUTX_LOCAL_AUTONOMY_CAPABILITY === 'enabled'
  )
}

export async function GET(request: NextRequest): Promise<NextResponse> {
  if (!hasAuthSession(request)) {
    return errorResponse('UNAUTHORIZED', 'Unauthorized', 401)
  }

  let authResult: Awaited<ReturnType<typeof authenticatedFetch>>
  try {
    authResult = await authenticatedFetch(request, `${getApiBaseUrl()}/v1/auth/me`, {
      cache: 'no-store',
    })
  } catch {
    return errorResponse(
      'SERVICE_UNAVAILABLE',
      'Unable to verify the operator session',
      503,
    )
  }

  const finish = (response: NextResponse) => {
    if (authResult.tokenRefreshed && authResult.refreshedTokens) {
      applyAuthCookies(response, request, authResult.refreshedTokens)
    }
    return response
  }

  if (!authResult.response.ok) {
    if (authResult.response.status === 401) {
      return finish(errorResponse('UNAUTHORIZED', 'Unauthorized', 401))
    }
    if (authResult.response.status === 403) {
      return finish(errorResponse('FORBIDDEN', 'Forbidden', 403))
    }
    return finish(
      errorResponse(
        'SERVICE_UNAVAILABLE',
        'Unable to verify the operator session',
        503,
      ),
    )
  }

  if (!localCapabilityEnabled()) {
    return finish(
      errorResponse(
        'FORBIDDEN',
        'Local autonomy is available only in an approved local capability context',
        403,
      ),
    )
  }

  const configuredRoot = process.env.MUTX_AUTONOMY_ROOT?.trim()
  if (!configuredRoot) {
    return finish(
      errorResponse(
        'SERVICE_UNAVAILABLE',
        'The local autonomy capability is not configured',
        503,
      ),
    )
  }

  try {
    const payload = await loadAutonomySnapshot(configuredRoot, {
      staleAfterSeconds: process.env.MUTX_AUTONOMY_STALE_AFTER_SECONDS,
    })
    return finish(jsonResponse(payload, 200))
  } catch (error) {
    if (
      error instanceof AutonomyDataError &&
      (error.code === 'root_not_found' || error.code === 'data_not_found')
    ) {
      return finish(
        errorResponse('NOT_FOUND', 'No local autonomy data was found', 404),
      )
    }

    return finish(
      errorResponse(
        'SERVICE_UNAVAILABLE',
        'Local autonomy data could not be read safely',
        503,
      ),
    )
  }
}
