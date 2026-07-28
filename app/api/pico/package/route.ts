import { NextRequest, NextResponse } from 'next/server'

import {
  applyAuthCookies,
  authenticatedFetch,
  getApiBaseUrl,
  hasAuthSession,
} from '@/app/api/_lib/controlPlane'
import { badRequest, unauthorized, withErrorHandling } from '@/app/api/_lib/errors'

export const dynamic = 'force-dynamic'

const fallbackFilename = 'pico-agent-package.zip'

function sanitizePackageFilename(value: string | null | undefined) {
  if (!value) return fallbackFilename

  const basename = value.replaceAll('\\', '/').split('/').pop() ?? ''
  const safe = basename
    .replace(/[^A-Za-z0-9._-]+/g, '-')
    .replace(/^[.-]+|[.-]+$/g, '')
    .slice(0, 120)

  if (!safe) return fallbackFilename
  return safe.toLowerCase().endsWith('.zip') ? safe : `${safe}.zip`
}

function packageFilenameFromHeader(contentDisposition: string | null) {
  if (!contentDisposition) return fallbackFilename

  const encoded = contentDisposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1]
  const plain = contentDisposition.match(/filename="?([^";]+)"?/i)?.[1]
  let candidate = encoded ?? plain ?? ''
  if (encoded) {
    try {
      candidate = decodeURIComponent(encoded)
    } catch {
      candidate = ''
    }
  }
  return sanitizePackageFilename(candidate.trim())
}

export async function POST(request: NextRequest) {
  return withErrorHandling(async () => {
    if (!hasAuthSession(request)) {
      return unauthorized()
    }

    let payload: unknown
    try {
      payload = await request.json()
    } catch {
      return badRequest('Invalid JSON in request body')
    }

    const sessionId =
      payload && typeof payload === 'object' && !Array.isArray(payload) &&
      typeof (payload as Record<string, unknown>).session_id === 'string'
        ? (payload as Record<string, string>).session_id.trim()
        : ''

    if (!sessionId) {
      return badRequest('session_id is required')
    }
    if (sessionId.length > 36) {
      return badRequest('Invalid onboarding session ID')
    }

    const { response, tokenRefreshed, refreshedTokens } = await authenticatedFetch(
      request,
      `${getApiBaseUrl()}/v1/pico/generate-package`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId }),
        cache: 'no-store',
      },
    )

    if (!response.ok) {
      const errorPayload = await response.json().catch(() => ({
        detail: 'Failed to generate Pico package',
      }))
      const errorResponse = NextResponse.json(errorPayload, { status: response.status })
      if (tokenRefreshed && refreshedTokens) {
        applyAuthCookies(errorResponse, request, refreshedTokens)
      }
      return errorResponse
    }

    const contentType = response.headers.get('content-type')?.toLowerCase() ?? ''
    if (!contentType.includes('zip') && !contentType.includes('octet-stream')) {
      const invalidResponse = NextResponse.json(
        { detail: 'Package service returned an invalid download' },
        { status: 502 },
      )
      if (tokenRefreshed && refreshedTokens) {
        applyAuthCookies(invalidResponse, request, refreshedTokens)
      }
      return invalidResponse
    }

    const arrayBuffer = await response.arrayBuffer()
    const signature = new Uint8Array(arrayBuffer, 0, Math.min(arrayBuffer.byteLength, 2))
    if (signature.length < 2 || signature[0] !== 0x50 || signature[1] !== 0x4b) {
      const invalidResponse = NextResponse.json(
        { detail: 'Package service returned an invalid ZIP archive' },
        { status: 502 },
      )
      if (tokenRefreshed && refreshedTokens) {
        applyAuthCookies(invalidResponse, request, refreshedTokens)
      }
      return invalidResponse
    }

    const filename = packageFilenameFromHeader(response.headers.get('content-disposition'))
    const headers: Record<string, string> = {
      'Content-Type': contentType || 'application/zip',
      'Content-Disposition': `attachment; filename="${filename}"`,
      'Cache-Control': 'no-store',
      'X-Content-Type-Options': 'nosniff',
    }
    const sessionHeader = response.headers.get('x-pico-onboarding-session')
    const stateHashHeader = response.headers.get('x-pico-onboarding-state-sha256')
    if (sessionHeader) headers['X-Pico-Onboarding-Session'] = sessionHeader
    if (stateHashHeader) headers['X-Pico-Onboarding-State-SHA256'] = stateHashHeader

    const nextResponse = new NextResponse(arrayBuffer, {
      status: response.status,
      headers,
    })

    if (tokenRefreshed && refreshedTokens) {
      applyAuthCookies(nextResponse, request, refreshedTokens)
    }

    return nextResponse
  })(request)
}
