import type { NextRequest } from 'next/server'
import { NextResponse } from 'next/server'

import {
  PICO_AUTH_LOCALE_COOKIE,
  PICO_DEFAULT_LOCALE,
  PICO_LOCALE_COOKIE,
  PICO_LOCALE_QUERY_PARAM,
  normalizePicoLocale,
  resolvePicoLocale,
  type PicoLocale,
} from '@/lib/pico/locale'

type RateLimitPolicy = {
  limit: number
  windowMs: number
}

type RateLimitState = {
  count: number
  resetTime: number
}

const SAFE_HTTP_METHODS = new Set(['GET', 'HEAD', 'OPTIONS', 'TRACE'])
const CSRF_FAILURE_DETAIL = 'CSRF validation failed: origin is not allowed'
const APP_HOST = 'app.mutx.dev'
const PICO_HOST = 'pico.mutx.dev'
const APP_HOSTS = new Set([APP_HOST, 'app.localhost'])
const MARKETING_HOSTS = new Set(['mutx.dev', 'www.mutx.dev'])
const PICO_HOSTS = new Set([PICO_HOST, 'pico.localhost'])
const PICO_AUTH_PAGE_PATHS = new Set([
  '/login',
  '/register',
  '/verify-email',
  '/forgot-password',
  '/reset-password',
])
const PICO_PRODUCT_PATHS = new Set([
  '/onboarding',
  '/academy',
  '/tutor',
  '/support',
  '/autopilot',
  '/pricing',
  '/build-ledger',
  // Compatibility-only alias; the route permanently redirects to /build-ledger.
  '/wip',
])
const PICO_LOCALE_COOKIE_MAX_AGE = 60 * 60 * 24 * 365
const PICO_LOCALE_BY_COUNTRY: Partial<Record<string, PicoLocale>> = {
  JP: 'ja',
  KR: 'ko',
  CN: 'zh',
  HK: 'zh',
  TW: 'zh',
  MO: 'zh',
  IT: 'it',
  PT: 'pt',
  BR: 'pt',
  ES: 'es',
  MX: 'es',
  AR: 'es',
  CO: 'es',
  CL: 'es',
  FR: 'fr',
  BE: 'fr',
  LU: 'fr',
  DE: 'de',
  AT: 'de',
  SA: 'ar',
  AE: 'ar',
  EG: 'ar',
  US: 'en',
  GB: 'en',
  AU: 'en',
  CA: 'en',
}
const UI_CACHE_CONTROL = 'private, no-cache, no-store, max-age=0, must-revalidate'
const API_CACHE_CONTROL = 'no-store'
const APP_PUBLIC_PATHS = new Set([
  '/',
  '/overview',
  '/agents',
  '/deployments',
  '/runs',
  '/environments',
  '/access',
  '/connectors',
  '/audit',
  '/approvals',
  '/usage',
  '/settings',
])

const DEFAULT_POLICY: RateLimitPolicy = {
  limit: 10,
  windowMs: 10 * 60 * 1000,
}

const AUTH_POLICY: RateLimitPolicy = {
  limit: 8,
  windowMs: 5 * 60 * 1000,
}

const LIMIT_STORE = new Map<string, RateLimitState>()

const POLICY_BY_PATH: Array<[string, RateLimitPolicy]> = [
  ['/api/auth/login', AUTH_POLICY],
  ['/api/auth/register', AUTH_POLICY],
  ['/api/auth/forgot-password', AUTH_POLICY],
  ['/api/auth/reset-password', AUTH_POLICY],
  ['/api/contact', DEFAULT_POLICY],
  ['/api/leads', DEFAULT_POLICY],
  ['/api/newsletter', DEFAULT_POLICY],
]

function getGeoLocale(request: NextRequest): PicoLocale | null {
  const cfCountry = request.headers.get('CF-IPCountry') ||
                    request.headers.get('X-Vercel-IP-Country')
  if (cfCountry) {
    const localeFromCountry = PICO_LOCALE_BY_COUNTRY[cfCountry.toUpperCase()]
    if (localeFromCountry) {
      return localeFromCountry
    }
  }

  return null
}

function getAcceptLanguageLocale(request: NextRequest): PicoLocale | null {
  const acceptLang = request.headers.get('accept-language')
  if (acceptLang) {
    const langs = acceptLang.split(',').map(l => l.split(';')[0].trim().toLowerCase())
    for (const lang of langs) {
      const locale = normalizePicoLocale(lang)
      if (locale) {
        return locale
      }
    }
  }

  return null
}

function getLocaleFromRequest(request: NextRequest): PicoLocale {
  return resolvePicoLocale(
    request.nextUrl.searchParams.get(PICO_LOCALE_QUERY_PARAM),
    request.cookies.get(PICO_AUTH_LOCALE_COOKIE)?.value,
    request.cookies.get(PICO_LOCALE_COOKIE)?.value,
    getGeoLocale(request),
    getAcceptLanguageLocale(request),
    PICO_DEFAULT_LOCALE,
  )
}

function getClientIp(request: NextRequest): string {
  return request.headers.get('x-forwarded-for')?.split(',')[0]?.trim() ||
         request.headers.get('x-real-ip') ||
         'unknown'
}

function getRequestHost(request: NextRequest): string {
  const host = request.headers.get('host')?.split(',')[0]?.trim()
  const forwardedHost = request.headers.get('x-forwarded-host')?.split(',')[0]?.trim()
  return (host || forwardedHost || request.nextUrl.hostname).split(':')[0].toLowerCase()
}

function getRequestScheme(request: NextRequest): string {
  const forwardedProto = request.headers.get('x-forwarded-proto')?.split(',')[0]?.trim()
  if (forwardedProto) {
    return forwardedProto.toLowerCase()
  }

  return request.nextUrl.protocol.replace(':', '').toLowerCase()
}

function normalizeOrigin(origin: string | null): string | null {
  if (!origin) {
    return null
  }

  try {
    return new URL(origin).origin.toLowerCase()
  } catch {
    return null
  }
}

function normalizePathname(pathname: string): string {
  if (pathname !== '/' && pathname.endsWith('/')) {
    return pathname.slice(0, -1)
  }

  return pathname
}

function isOAuthCallbackPath(pathname: string): boolean {
  return /^\/api\/auth\/oauth\/[^/]+\/callback$/.test(pathname)
}

function mapLegacyAppPathToDashboard(pathname: string): string {
  const normalized = normalizePathname(pathname)

  const directMap: Record<string, string> = {
    '/app': '/dashboard',
    '/app/agents': '/dashboard/agents',
    '/app/deployments': '/dashboard/deployments',
    '/app/api-keys': '/dashboard/api-keys',
    '/app/webhooks': '/dashboard/webhooks',
    '/app/logs': '/dashboard/logs',
    '/app/history': '/dashboard/history',
    '/app/activity': '/dashboard/history',
    '/app/budgets': '/dashboard/budgets',
    '/app/traces': '/dashboard/traces',
    '/app/runs': '/dashboard/runs',
    '/app/memory': '/dashboard/memory',
    '/app/spawn': '/dashboard/spawn',
    '/app/control': '/dashboard/control',
    '/app/settings': '/dashboard/control',
    '/app/orchestration': '/dashboard/orchestration',
    '/app/cron': '/dashboard/autonomy',
    '/app/health': '/dashboard/monitoring',
    '/app/observability': '/dashboard/observability',
  }

  if (directMap[normalized]) {
    return directMap[normalized]
  }

  if (normalized.startsWith('/app/')) {
    return `/dashboard${normalized.slice('/app'.length)}`
  }

  return normalized
}

function mapAppHostPicoPathToCanonicalPicoPath(pathname: string): string | null {
  const normalized = normalizePathname(pathname)

  if (normalized === '/pico') {
    return '/'
  }

  if (normalized.startsWith('/pico/')) {
    return normalized.slice('/pico'.length)
  }

  return null
}

function mapCanonicalPicoPathToInternalPath(pathname: string): string | null {
  const normalized = normalizePathname(pathname)

  if (normalized === '/') {
    return '/pico'
  }

  if (PICO_PRODUCT_PATHS.has(normalized) || normalized.startsWith('/academy/')) {
    return `/pico${normalized}`
  }

  return null
}

function appHostPathToInternalDashboardPath(pathname: string): string {
  const normalized = normalizePathname(pathname)

  const directMap: Record<string, string> = {
    '/': '/dashboard',
    '/overview': '/dashboard',
    '/agents': '/dashboard/agents',
    '/deployments': '/dashboard/deployments',
    '/runs': '/dashboard/runs',
    '/environments': '/dashboard/monitoring',
    '/access': '/dashboard/security',
    '/connectors': '/dashboard/webhooks',
    '/audit': '/dashboard/audit',
    '/approvals': '/dashboard/approvals',
    '/usage': '/dashboard/budgets',
    '/settings': '/dashboard/control',
  }

  if (directMap[normalized]) {
    return directMap[normalized]
  }

  return normalized
}

function redirectToHost(request: NextRequest, host: string, pathname: string) {
  const url = new URL(request.url)
  url.hostname = host
  url.port = ''
  url.pathname = pathname
  url.search = request.nextUrl.search
  return NextResponse.redirect(url)
}

function redirectWithinHost(request: NextRequest, pathname: string) {
  const url = new URL(request.url)
  url.pathname = pathname
  url.search = request.nextUrl.search
  return NextResponse.redirect(url)
}

function rewriteWithinHost(request: NextRequest, pathname: string, requestHeaders?: Headers) {
  const url = new URL(request.url)
  url.pathname = pathname
  url.search = request.nextUrl.search
  if (!requestHeaders) {
    return NextResponse.rewrite(url)
  }

  return NextResponse.rewrite(url, {
    request: {
      headers: requestHeaders,
    },
  })
}

function applyPicoLocale(response: NextResponse, locale: PicoLocale) {
  response.cookies.set(PICO_LOCALE_COOKIE, locale, {
    path: '/',
    sameSite: 'lax',
    maxAge: PICO_LOCALE_COOKIE_MAX_AGE,
  })

  return response
}

function buildPicoRequestHeaders(request: NextRequest, locale: PicoLocale) {
  const requestHeaders = new Headers()
  const rawHeaders = request.headers as unknown as {
    entries?: () => IterableIterator<[string, string]>
    get?: (name: string) => string | null
  }

  if (typeof rawHeaders.entries === 'function') {
    for (const [key, value] of rawHeaders.entries()) {
      requestHeaders.set(key, value)
    }
  } else if (typeof rawHeaders.get === 'function') {
    for (const name of ['cookie', 'accept-language', 'host', 'x-forwarded-host', 'x-forwarded-proto']) {
      const value = rawHeaders.get(name)
      if (value) {
        requestHeaders.set(name, value)
      }
    }
  }

  requestHeaders.set('x-mutx-locale', locale)
  return requestHeaders
}

function shouldDisableUiCaching(host: string, pathname: string): boolean {
  if (pathname.startsWith('/api')) {
    return false
  }

  return MARKETING_HOSTS.has(host) || APP_HOSTS.has(host) || PICO_HOSTS.has(host)
}

function applyUiCacheHeaders(response: NextResponse, host: string, pathname: string) {
  if (shouldDisableUiCaching(host, pathname)) {
    response.headers.set('Cache-Control', UI_CACHE_CONTROL)
  }

  return response
}

function applySecurityHeaders(response: NextResponse, pathname: string) {
  response.headers.set('X-Frame-Options', 'DENY')
  response.headers.set('X-Content-Type-Options', 'nosniff')
  response.headers.set('Referrer-Policy', 'strict-origin-when-cross-origin')
  response.headers.set('Permissions-Policy', 'geolocation=(), microphone=(), camera=()')

  if (pathname.startsWith('/api')) {
    response.headers.set('Cache-Control', API_CACHE_CONTROL)
  }

  return response
}

function finalizeResponse(response: NextResponse, host: string, pathname: string) {
  applyUiCacheHeaders(response, host, pathname)
  applySecurityHeaders(response, pathname)
  return response
}

function isLoopbackHost(hostname: string) {
  return hostname === 'localhost' || hostname === '127.0.0.1' || hostname === '::1'
}

function isAllowedApiOrigin(request: NextRequest, host: string): boolean {
  const requestOrigin = normalizeOrigin(request.headers.get('origin'))
  if (!requestOrigin) {
    return false
  }

  try {
    const originUrl = new URL(requestOrigin)
    const requestUrl = request.nextUrl
    const requestScheme = getRequestScheme(request)
    const exactMatch = requestOrigin === normalizeOrigin(requestUrl.origin)
    const sameHost = originUrl.protocol === `${requestScheme}:` && originUrl.hostname === requestUrl.hostname
    const sameHostHeader = originUrl.protocol === `${requestScheme}:` && originUrl.hostname === host
    const loopbackMatch =
      originUrl.protocol === `${requestScheme}:` &&
      isLoopbackHost(originUrl.hostname) &&
      (isLoopbackHost(requestUrl.hostname) || isLoopbackHost(host))
    return exactMatch || sameHost || sameHostHeader || loopbackMatch
  } catch {
    return false
  }
}

function getPolicy(pathname: string): RateLimitPolicy | null {
  for (const [prefix, policy] of POLICY_BY_PATH) {
    if (pathname.startsWith(prefix)) {
      return policy
    }
  }

  return null
}

function checkRateLimit(
  request: NextRequest,
  policy: RateLimitPolicy
): { allowed: boolean; remaining: number; resetTime: number } {
  const now = Date.now()
  const key = `${request.nextUrl.pathname}:${getClientIp(request)}`
  const current = LIMIT_STORE.get(key)

  if (!current || current.resetTime <= now) {
    LIMIT_STORE.set(key, { count: 1, resetTime: now + policy.windowMs })
    return { allowed: true, remaining: policy.limit - 1, resetTime: now + policy.windowMs }
  }

  if (current.count >= policy.limit) {
    return { allowed: false, remaining: 0, resetTime: current.resetTime }
  }

  current.count += 1
  LIMIT_STORE.set(key, current)
  return { allowed: true, remaining: Math.max(0, policy.limit - current.count), resetTime: current.resetTime }
}

export function proxy(request: NextRequest) {
  const pathname = request.nextUrl.pathname

  if (
    pathname.startsWith('/_next') ||
    pathname.startsWith('/static') ||
    pathname.includes('.')
  ) {
    return NextResponse.next()
  }

  const normalizedPath = normalizePathname(pathname)
  const host = getRequestHost(request)

  if (
    normalizedPath.startsWith('/api') &&
    !isOAuthCallbackPath(normalizedPath) &&
    !SAFE_HTTP_METHODS.has(request.method.toUpperCase()) &&
    request.headers.get('origin') &&
    !isAllowedApiOrigin(request, host)
  ) {
    return finalizeResponse(
      NextResponse.json({ detail: CSRF_FAILURE_DETAIL }, { status: 403 }),
      host,
      normalizedPath,
    )
  }

  if (PICO_HOSTS.has(host) && !normalizedPath.startsWith('/api')) {
    const locale = getLocaleFromRequest(request)
    const picoRequestHeaders = buildPicoRequestHeaders(request, locale)

    if (normalizedPath === '/pico' || normalizedPath.startsWith('/pico/')) {
      const canonicalPath = normalizedPath === '/pico' ? '/' : normalizedPath.slice('/pico'.length)
      return finalizeResponse(
        applyPicoLocale(redirectWithinHost(request, canonicalPath), locale),
        host,
        normalizedPath,
      )
    }

    if (normalizedPath === '/start') {
      return finalizeResponse(
        applyPicoLocale(redirectWithinHost(request, '/onboarding'), locale),
        host,
        normalizedPath,
      )
    }

    const internalPicoPath = mapCanonicalPicoPathToInternalPath(normalizedPath)
    if (internalPicoPath) {
      return finalizeResponse(
        applyPicoLocale(rewriteWithinHost(request, internalPicoPath, picoRequestHeaders), locale),
        host,
        normalizedPath,
      )
    }

    if (PICO_AUTH_PAGE_PATHS.has(normalizedPath)) {
      return finalizeResponse(
        applyPicoLocale(
          NextResponse.next({ request: { headers: picoRequestHeaders } }),
          locale,
        ),
        host,
        normalizedPath,
      )
    }

    return finalizeResponse(
      applyPicoLocale(
        rewriteWithinHost(request, '/pico/__not-found', picoRequestHeaders),
        locale,
      ),
      host,
      normalizedPath,
    )
  }

  if (MARKETING_HOSTS.has(host)) {
    // Block direct /pico access on the main domain
    if (normalizedPath.startsWith('/pico')) {
      return finalizeResponse(
        redirectWithinHost(request, '/'),
        host,
        normalizedPath,
      )
    }

    if (normalizedPath === '/login' || normalizedPath === '/register') {
      return finalizeResponse(
        redirectToHost(request, APP_HOST, normalizedPath),
        host,
        normalizedPath,
      )
    }

    if (normalizedPath !== '/' && APP_PUBLIC_PATHS.has(normalizedPath)) {
      return finalizeResponse(
        redirectToHost(request, APP_HOST, normalizedPath === '/overview' ? '/' : normalizedPath),
        host,
        normalizedPath,
      )
    }

    if (
      normalizedPath === '/dashboard' ||
      normalizedPath.startsWith('/dashboard/') ||
      normalizedPath === '/app' ||
      normalizedPath.startsWith('/app/')
    ) {
      const canonicalDashboardPath = normalizedPath.startsWith('/app')
        ? mapLegacyAppPathToDashboard(normalizedPath)
        : normalizedPath
      return finalizeResponse(
        redirectToHost(request, APP_HOST, canonicalDashboardPath),
        host,
        normalizedPath,
      )
    }
  }

  if (APP_HOSTS.has(host)) {
    const canonicalPicoPath = mapAppHostPicoPathToCanonicalPicoPath(normalizedPath)
    if (canonicalPicoPath) {
      const picoHost = host === 'app.localhost' ? 'pico.localhost' : PICO_HOST
      return finalizeResponse(
        redirectToHost(request, picoHost, canonicalPicoPath),
        host,
        normalizedPath,
      )
    }

    if (normalizedPath === '/dashboard' || normalizedPath.startsWith('/dashboard/')) {
      return finalizeResponse(NextResponse.next(), host, normalizedPath)
    }

    if (normalizedPath === '/control' || normalizedPath.startsWith('/control/')) {
      return finalizeResponse(NextResponse.next(), host, normalizedPath)
    }

    if (normalizedPath === '/app' || normalizedPath.startsWith('/app/')) {
      return finalizeResponse(
        redirectWithinHost(request, mapLegacyAppPathToDashboard(normalizedPath)),
        host,
        normalizedPath,
      )
    }

    const internalPath = appHostPathToInternalDashboardPath(normalizedPath)
    if (internalPath !== normalizedPath) {
      return finalizeResponse(
        rewriteWithinHost(request, internalPath),
        host,
        normalizedPath,
      )
    }
  }

  const policy = getPolicy(pathname)
  if (!policy) {
    return finalizeResponse(NextResponse.next(), host, normalizedPath)
  }

  const { allowed, remaining, resetTime } = checkRateLimit(request, policy)
  const response = NextResponse.next()
  response.headers.set('X-RateLimit-Limit', String(policy.limit))
  response.headers.set('X-RateLimit-Remaining', String(remaining))
  response.headers.set('X-RateLimit-Reset', String(resetTime))

  if (!allowed) {
    const headers = new Headers(response.headers)
    headers.set('Retry-After', String(Math.ceil((resetTime - Date.now()) / 1000)))
    return finalizeResponse(new NextResponse('Too Many Requests', { status: 429, headers }), host, normalizedPath)
  }

  return finalizeResponse(response, host, normalizedPath)
}

export const middleware = proxy

export const config = {
  matcher: ['/:path*'],
}
