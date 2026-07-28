import { NextRequest, NextResponse } from 'next/server'
import { readFileSync } from 'node:fs'

export type AuthTokens = {
  access_token: string
  refresh_token?: string
  expires_in: number
}

type AuthRequestContext = {
  accessToken: string | null
  refreshToken: string | null
  refreshAttempted: boolean
  refreshPromise: Promise<AuthTokens | null> | null
  refreshedTokens?: AuthTokens
}

// A late 401 from an overlapping dashboard request must reuse the rotation result,
// not submit the now-spent refresh token and trigger family-reuse revocation.
const REFRESH_FLIGHT_GRACE_MS = 5000
const authRequestContexts = new WeakMap<NextRequest, AuthRequestContext>()
const refreshFlights = new Map<string, Promise<AuthTokens | null>>()

function normalizeBaseUrl(value?: string | null) {
  if (!value) return null
  if (value.startsWith('http://') || value.startsWith('https://')) return value
  return `https://${value}`
}

export function getApiBaseUrl() {
  const runtimeContextPath = process.env.MUTX_DESKTOP_RUNTIME_CONTEXT_PATH
  if (runtimeContextPath) {
    try {
      const raw = readFileSync(runtimeContextPath, 'utf8')
      const parsed = JSON.parse(raw) as { apiUrl?: string }
      const runtimeUrl = normalizeBaseUrl(parsed.apiUrl)
      if (runtimeUrl) {
        return runtimeUrl
      }
    } catch {
      // fall through to env-based resolution
    }
  }

  return (
    normalizeBaseUrl(process.env.INTERNAL_API_URL) ||
    normalizeBaseUrl(process.env.NEXT_PUBLIC_API_URL) ||
    normalizeBaseUrl(process.env.RAILWAY_SERVICE_ZOOMING_YOUTH_URL) ||
    normalizeBaseUrl(process.env.API_BASE_URL) ||
    'http://localhost:8000'
  )
}

export function shouldUseSecureCookies(request: NextRequest) {
  // Auth cookies stay secure-only even when desktop/browser flows are mediated
  // through localhost or forwarded HTTPS headers. The release contract and unit
  // tests both assume the stricter posture.
  void request
  return true
}

export function getCookieDomain(request: NextRequest) {
  // Keep auth cookies host-only to avoid exposing tokens across subdomains.
  void request
  return undefined
}

function readAuthToken(request: NextRequest): string | null {
  const token = request.cookies.get('access_token')?.value
  if (token) return token

  const authHeader = request.headers.get('authorization')
  if (authHeader?.startsWith('Bearer ')) {
    return authHeader.substring(7)
  }

  return null
}

export async function getAuthToken(request: NextRequest): Promise<string | null> {
  return readAuthToken(request)
}

export function getRefreshToken(request: NextRequest): string | null {
  return request.cookies.get('refresh_token')?.value ?? null
}

export function hasAuthSession(request: NextRequest): boolean {
  return Boolean(request.cookies.get('access_token')?.value || getRefreshToken(request) || request.headers.get('authorization'))
}

function getAuthRequestContext(request: NextRequest): AuthRequestContext {
  const existingContext = authRequestContexts.get(request)
  if (existingContext) {
    return existingContext
  }

  const context: AuthRequestContext = {
    accessToken: readAuthToken(request),
    refreshToken: getRefreshToken(request),
    refreshAttempted: false,
    refreshPromise: null,
  }
  authRequestContexts.set(request, context)
  return context
}

export function applyAuthCookies(
  response: NextResponse,
  request: NextRequest,
  tokens: AuthTokens
) {
  const secureCookies = shouldUseSecureCookies(request)
  const cookieDomain = getCookieDomain(request)

  response.cookies.set('access_token', tokens.access_token, {
    httpOnly: true,
    sameSite: 'lax',
    secure: secureCookies,
    domain: cookieDomain,
    path: '/',
    maxAge: tokens.expires_in || 1800,
  })

  if (tokens.refresh_token) {
    response.cookies.set('refresh_token', tokens.refresh_token, {
      httpOnly: true,
      sameSite: 'lax',
      secure: secureCookies,
      domain: cookieDomain,
      path: '/',
      maxAge: 60 * 60 * 24 * 7,
    })
  }
}

export function clearAuthCookies(response: NextResponse, request: NextRequest) {
  const secureCookies = shouldUseSecureCookies(request)
  const cookieDomain = getCookieDomain(request)

  response.cookies.set('access_token', '', {
    httpOnly: true,
    sameSite: 'lax',
    secure: secureCookies,
    domain: cookieDomain,
    path: '/',
    maxAge: 0,
  })
  response.cookies.set('refresh_token', '', {
    httpOnly: true,
    sameSite: 'lax',
    secure: secureCookies,
    domain: cookieDomain,
    path: '/',
    maxAge: 0,
  })
}

export async function refreshAuthToken(
  request: NextRequest,
  refreshToken: string
): Promise<AuthTokens | null> {
  const apiBaseUrl = getApiBaseUrl()
  void request

  try {
    const response = await fetch(`${apiBaseUrl}/v1/auth/refresh`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: refreshToken }),
      cache: 'no-store',
    })

    if (!response.ok) {
      return null
    }

    const payload: unknown = await response.json()
    if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
      return null
    }

    const tokens = payload as Partial<AuthTokens>
    if (
      typeof tokens.access_token !== 'string' ||
      tokens.access_token.length === 0 ||
      typeof tokens.refresh_token !== 'string' ||
      tokens.refresh_token.length === 0 ||
      typeof tokens.expires_in !== 'number' ||
      !Number.isFinite(tokens.expires_in) ||
      tokens.expires_in <= 0
    ) {
      return null
    }

    return {
      access_token: tokens.access_token,
      refresh_token: tokens.refresh_token,
      expires_in: tokens.expires_in,
    }
  } catch {
    return null
  }
}

function refreshOnce(request: NextRequest, refreshToken: string): Promise<AuthTokens | null> {
  const existingFlight = refreshFlights.get(refreshToken)
  if (existingFlight) {
    return existingFlight
  }

  const refreshPromise = refreshAuthToken(request, refreshToken)
  refreshFlights.set(refreshToken, refreshPromise)
  const scheduleCleanup = () => {
    const cleanupTimer = setTimeout(() => {
      if (refreshFlights.get(refreshToken) === refreshPromise) {
        refreshFlights.delete(refreshToken)
      }
    }, REFRESH_FLIGHT_GRACE_MS)
    cleanupTimer.unref()
  }
  void refreshPromise.then(scheduleCleanup, scheduleCleanup)

  return refreshPromise
}

function useRefreshedTokens(
  context: AuthRequestContext,
  tokens: AuthTokens | null
): string | null {
  if (!tokens) {
    return null
  }

  context.accessToken = tokens.access_token
  context.refreshToken = tokens.refresh_token ?? null
  context.refreshedTokens = tokens
  return tokens.access_token
}

async function getRetryToken(
  request: NextRequest,
  context: AuthRequestContext,
  rejectedToken: string | null
): Promise<string | null> {
  if (context.accessToken && context.accessToken !== rejectedToken) {
    return context.accessToken
  }

  if (context.refreshPromise) {
    const tokens = await context.refreshPromise
    context.refreshPromise = null
    return useRefreshedTokens(context, tokens)
  }

  if (context.refreshAttempted || !context.refreshToken) {
    return null
  }

  const refreshToken = context.refreshToken
  context.refreshAttempted = true
  context.refreshToken = null
  context.refreshPromise = refreshOnce(request, refreshToken)

  const tokens = await context.refreshPromise
  context.refreshPromise = null

  if (!tokens) {
    return null
  }

  return useRefreshedTokens(context, tokens)
}

function fetchWithAccessToken(url: string, options: RequestInit, token: string | null) {
  const headers = new Headers(options.headers)
  if (token) {
    headers.set('Authorization', `Bearer ${token}`)
  }

  return fetch(url, {
    ...options,
    headers,
    credentials: 'include',
  })
}

/**
 * Authenticated fetch with automatic token refresh on 401.
 * Returns the upstream response and any rotated tokens that the caller must set as cookies.
 */
export async function authenticatedFetch(
  request: NextRequest,
  url: string,
  options: RequestInit = {}
): Promise<{ response: Response; tokenRefreshed: boolean; refreshedTokens?: AuthTokens }> {
  const context = getAuthRequestContext(request)
  let token = context.accessToken

  // Initial fetch with current token
  let response = await fetchWithAccessToken(url, options, token)

  // If unauthorized, try to refresh the token
  if (response.status === 401) {
    const retryToken = await getRetryToken(request, context, token)
    if (retryToken) {
      token = retryToken
      response = await fetchWithAccessToken(url, options, token)
    }
  }

  return {
    response,
    tokenRefreshed: Boolean(context.refreshedTokens),
    refreshedTokens: context.refreshedTokens,
  }
}
