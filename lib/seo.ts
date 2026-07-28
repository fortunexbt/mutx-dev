import type { Metadata } from 'next'

export const DEFAULT_SITE_URL = 'https://mutx.dev'
export const DEFAULT_APP_URL = 'https://app.mutx.dev'
export const DEFAULT_PICO_URL = 'https://pico.mutx.dev'
export const DEFAULT_DOCS_URL = `${DEFAULT_SITE_URL}/docs`
export const DEFAULT_GITHUB_URL = 'https://github.com/mutx-dev/mutx-dev'
export const DEFAULT_X_HANDLE = '@mutxdev'
export const DEFAULT_OG_IMAGE = '/opengraph-image'
export const DEFAULT_OG_IMAGE_ALT = 'MUTX branded social preview card'
export const SOCIAL_IMAGE_WIDTH = 1200
export const SOCIAL_IMAGE_HEIGHT = 630
export const SOCIAL_IMAGE_TYPE = 'image/png'

export const PUBLIC_MARKETING_ROUTES = [
  '/',
  '/download',
  '/download/macos',
  '/releases',
  '/contact',
  '/docs',
  '/manifesto',
  '/infrastructure',
  '/sdk',
  '/whitepaper',
  '/security',
  '/support',
  '/roadmap',
  '/privacy-policy',
  '/ai-agent-governance',
  '/ai-agent-approvals',
  '/ai-agent-audit-logs',
  '/ai-agent-control-plane',
  '/ai-agent-cost',
  '/ai-agent-deployment',
  '/ai-agent-guardrails',
  '/ai-agent-infrastructure',
  '/ai-agent-monitoring',
  '/ai-agent-reliability',
] as const

export const BLOCKED_CRAWL_PREFIXES = [
  '/api/',
  '/dashboard',
  '/control',
  '/login',
  '/register',
  '/forgot-password',
  '/reset-password',
  '/onboarding',
] as const

export type SeoSurface = 'marketing' | 'app' | 'pico'

export type SocialSection =
  | 'home'
  | 'docs'
  | 'download'
  | 'releases'
  | 'contact'
  | 'legal'
  | 'security'
  | 'support'
  | 'governance'
  | 'approvals'
  | 'audit'
  | 'control'
  | 'cost'
  | 'deployment'
  | 'guardrails'
  | 'infrastructure'
  | 'monitoring'
  | 'reliability'
  | 'academy'
  | 'tutor'
  | 'autopilot'
  | 'pricing'
  | 'onboarding'
  | 'manifesto'
  | 'roadmap'
  | 'whitepaper'
  | 'sdk'
  | 'generic'

type ArrayElement<T> = T extends readonly (infer Item)[] ? Item : T
type OpenGraphImages = NonNullable<NonNullable<Metadata['openGraph']>['images']>
type SocialImageDescriptor = ArrayElement<OpenGraphImages>

const APP_HOSTNAMES = new Set(['app.mutx.dev', 'app.localhost'])
const PICO_HOSTNAMES = new Set(['pico.mutx.dev', 'pico.localhost'])

function normalizeUrl(value: string | undefined, fallback: string) {
  if (!value) {
    return fallback
  }

  return value.replace(/\/$/, '')
}

function normalizePath(path = '/') {
  if (!path || path === '/') {
    return '/'
  }

  return path.startsWith('/') ? path : `/${path}`
}

function normalizeHostname(value?: string | null) {
  if (!value) {
    return null
  }

  const firstValue = value.split(',')[0]?.trim()
  if (!firstValue) {
    return null
  }

  try {
    return new URL(firstValue).hostname.toLowerCase()
  } catch {
    return firstValue.split(':')[0].toLowerCase()
  }
}

function getSiteNameForSurface(surface: SeoSurface) {
  switch (surface) {
    case 'app':
      return 'MUTX App'
    case 'pico':
      return 'PicoMUTX'
    default:
      return 'MUTX'
  }
}

export function resolveSocialSection(path = '/', host?: string | null): SocialSection {
  const normalizedPath = normalizePath(path)
  const surface = resolveSeoSurfaceForPath(normalizedPath, host)

  if (surface === 'app') {
    if (normalizedPath === '/control') {
      return 'control'
    }

    if (normalizedPath === '/' || normalizedPath.startsWith('/dashboard')) {
      return 'monitoring'
    }
  }

  if (surface === 'pico') {
    if (normalizedPath === '/academy' || normalizedPath.startsWith('/academy/')) {
      return 'academy'
    }

    if (normalizedPath === '/tutor') {
      return 'tutor'
    }

    if (normalizedPath === '/autopilot') {
      return 'autopilot'
    }

    if (normalizedPath === '/pricing') {
      return 'pricing'
    }

    if (normalizedPath === '/onboarding') {
      return 'onboarding'
    }

    return 'generic'
  }

  if (normalizedPath === '/') return 'home'
  if (normalizedPath === '/download' || normalizedPath.startsWith('/download/')) return 'download'
  if (normalizedPath === '/releases') return 'releases'
  if (normalizedPath === '/contact') return 'contact'
  if (normalizedPath === '/privacy-policy') return 'legal'
  if (normalizedPath === '/security') return 'security'
  if (normalizedPath === '/support') return 'support'
  if (normalizedPath === '/manifesto') return 'manifesto'
  if (normalizedPath === '/roadmap') return 'roadmap'
  if (normalizedPath === '/whitepaper') return 'whitepaper'
  if (normalizedPath === '/sdk') return 'sdk'
  if (normalizedPath === '/docs' || normalizedPath.startsWith('/docs/')) return 'docs'
  if (normalizedPath === '/ai-agent-governance') return 'governance'
  if (normalizedPath === '/ai-agent-approvals') return 'approvals'
  if (normalizedPath === '/ai-agent-audit-logs') return 'audit'
  if (normalizedPath === '/ai-agent-control-plane') return 'control'
  if (normalizedPath === '/ai-agent-cost') return 'cost'
  if (normalizedPath === '/ai-agent-deployment') return 'deployment'
  if (normalizedPath === '/ai-agent-guardrails') return 'guardrails'
  if (normalizedPath === '/ai-agent-infrastructure' || normalizedPath === '/infrastructure') {
    return 'infrastructure'
  }
  if (normalizedPath === '/ai-agent-monitoring') return 'monitoring'
  if (normalizedPath === '/ai-agent-reliability') return 'reliability'

  return 'generic'
}

export function getSiteUrl() {
  return normalizeUrl(process.env.NEXT_PUBLIC_SITE_URL, DEFAULT_SITE_URL)
}

export function getAppUrl() {
  return normalizeUrl(process.env.NEXT_PUBLIC_APP_URL, DEFAULT_APP_URL)
}

export function getPicoUrl() {
  return normalizeUrl(process.env.NEXT_PUBLIC_PICO_URL, DEFAULT_PICO_URL)
}

export function toAbsoluteUrl(origin: string, path = '/') {
  const normalizedPath = normalizePath(path)
  const normalizedOrigin = normalizeUrl(origin, origin)

  return normalizedPath === '/' ? normalizedOrigin : `${normalizedOrigin}${normalizedPath}`
}

export function toAbsoluteSiteUrl(path = '/') {
  return toAbsoluteUrl(getSiteUrl(), path)
}

export function toAbsoluteAppUrl(path = '/') {
  return toAbsoluteUrl(getAppUrl(), path)
}

export function toAbsolutePicoUrl(path = '/') {
  return toAbsoluteUrl(getPicoUrl(), path)
}

export function resolveSeoSurface(hostname?: string | null): SeoSurface {
  const normalizedHost = normalizeHostname(hostname)

  if (normalizedHost && APP_HOSTNAMES.has(normalizedHost)) {
    return 'app'
  }

  if (normalizedHost && PICO_HOSTNAMES.has(normalizedHost)) {
    return 'pico'
  }

  return 'marketing'
}

export function resolveSeoSurfaceForPath(path = '/', host?: string | null): SeoSurface {
  const surfaceFromHost = resolveSeoSurface(host)
  if (surfaceFromHost !== 'marketing') {
    return surfaceFromHost
  }

  const normalizedPath = normalizePath(path)

  if (normalizedPath === '/control' || normalizedPath.startsWith('/dashboard')) {
    return 'app'
  }

  if (
    normalizedPath === '/pico' ||
    normalizedPath.startsWith('/pico/') ||
    normalizedPath === '/academy' ||
    normalizedPath.startsWith('/academy/') ||
    normalizedPath === '/tutor' ||
    normalizedPath === '/autopilot' ||
    normalizedPath === '/pricing' ||
    normalizedPath === '/onboarding'
  ) {
    return 'pico'
  }

  return 'marketing'
}

export function getSurfaceUrl(surface: SeoSurface) {
  switch (surface) {
    case 'app':
      return getAppUrl()
    case 'pico':
      return getPicoUrl()
    default:
      return getSiteUrl()
  }
}

export function getCanonicalUrl(path = '/', host?: string) {
  return toAbsoluteUrl(host ? normalizeUrl(host, getSiteUrl()) : getSiteUrl(), path)
}

/**
 * Legacy: static default OG image (the robot).
 * Use getPageOgImageUrl() for per-page unique images.
 */
export function getOgImageUrl() {
  return toAbsoluteSiteUrl(DEFAULT_OG_IMAGE)
}

export function getTwitterImageUrl() {
  return toAbsoluteSiteUrl('/twitter-image')
}

export function getPageOgImageUrl(
  title: string,
  description?: string,
  options?: { path?: string; badge?: string; host?: string },
): string {
  const params = new URLSearchParams({ title })
  if (description) params.set('description', description)
  if (options?.path) params.set('path', options.path)
  if (options?.badge) params.set('badge', options.badge)
  const baseUrl = normalizeUrl(options?.host, getSiteUrl())
  return `${baseUrl}/opengraph-image?${params.toString()}`
}

export function getPageTwitterImageUrl(
  title: string,
  description?: string,
  options?: { path?: string; badge?: string; host?: string },
): string {
  const params = new URLSearchParams({ title })
  if (description) params.set('description', description)
  if (options?.path) params.set('path', options.path)
  if (options?.badge) params.set('badge', options.badge)
  const baseUrl = normalizeUrl(options?.host, getSiteUrl())
  return `${baseUrl}/twitter-image?${params.toString()}`
}

export function getDefaultSocialBadge(path = '/', host?: string | null) {
  const section = resolveSocialSection(path, host)

  switch (section) {
    case 'docs':
      return 'DOCS'
    case 'download':
      return 'DOWNLOAD'
    case 'releases':
      return 'RELEASES'
    case 'contact':
      return 'CONTACT'
    case 'legal':
      return 'LEGAL'
    case 'security':
      return 'SECURITY'
    case 'support':
      return 'SUPPORT'
    case 'manifesto':
      return 'MANIFESTO'
    case 'roadmap':
      return 'ROADMAP'
    case 'whitepaper':
      return 'WHITEPAPER'
    case 'sdk':
      return 'SDK'
    case 'governance':
      return 'GOVERNANCE'
    case 'approvals':
      return 'APPROVALS'
    case 'audit':
      return 'AUDIT'
    case 'control':
      return 'CONTROL PLANE'
    case 'cost':
      return 'COST'
    case 'deployment':
      return 'DEPLOYMENT'
    case 'guardrails':
      return 'GUARDRAILS'
    case 'infrastructure':
      return 'INFRASTRUCTURE'
    case 'monitoring':
      return 'OBSERVABILITY'
    case 'reliability':
      return 'RELIABILITY'
    case 'academy':
      return 'ACADEMY'
    case 'tutor':
      return 'TUTOR'
    case 'autopilot':
      return 'AUTOPILOT'
    case 'pricing':
      return 'PRICING'
    case 'onboarding':
      return 'ONBOARDING'
    default: {
      const surface = resolveSeoSurfaceForPath(path, host)
      if (surface === 'app') return 'APP'
      if (surface === 'pico') return 'PICOMUTX'
      return 'MUTX'
    }
  }
}

export function getSocialImageAlt(title: string, path = '/', host?: string | null) {
  return `${title} social preview for ${getSiteNameForSurface(resolveSeoSurfaceForPath(path, host))}`
}

function buildSocialImageDescriptor(options: {
  title: string
  description: string
  path: string
  host: string
  badge?: string
  type: 'openGraph' | 'twitter'
}): SocialImageDescriptor {
  const url =
    options.type === 'openGraph'
      ? getPageOgImageUrl(options.title, options.description, {
          path: options.path,
          host: options.host,
          badge: options.badge,
        })
      : getPageTwitterImageUrl(options.title, options.description, {
          path: options.path,
          host: options.host,
          badge: options.badge,
        })

  return {
    url,
    width: SOCIAL_IMAGE_WIDTH,
    height: SOCIAL_IMAGE_HEIGHT,
    alt: getSocialImageAlt(options.title, options.path, options.host),
    type: SOCIAL_IMAGE_TYPE,
  }
}

export function buildPageMetadata(options: {
  title: string
  description: string
  path?: string
  host?: string
  siteName?: string
  badge?: string
  locale?: string
  type?: 'website' | 'article'
  socialTitle?: string
  socialDescription?: string
  twitterTitle?: string
  twitterDescription?: string
}): Pick<Metadata, 'alternates' | 'openGraph' | 'twitter'> {
  const path = normalizePath(options.path)
  const surface = resolveSeoSurfaceForPath(path, options.host)
  const host = normalizeUrl(options.host, getSurfaceUrl(surface))
  const siteName = options.siteName ?? getSiteNameForSurface(surface)
  const badge = options.badge ?? getDefaultSocialBadge(path, host)
  const canonical = getCanonicalUrl(path, host)
  const socialTitle = options.socialTitle ?? options.title
  const socialDescription = options.socialDescription ?? options.description
  const twitterTitle = options.twitterTitle ?? socialTitle
  const twitterDescription = options.twitterDescription ?? socialDescription

  return {
    alternates: {
      canonical,
    },
    openGraph: {
      title: socialTitle,
      description: socialDescription,
      url: canonical,
      siteName,
      locale: options.locale ?? 'en_US',
      type: options.type ?? 'website',
      images: [
        buildSocialImageDescriptor({
          title: socialTitle,
          description: socialDescription,
          path,
          host,
          badge,
          type: 'openGraph',
        }),
      ],
    },
    twitter: {
      card: 'summary_large_image',
      creator: DEFAULT_X_HANDLE,
      site: DEFAULT_X_HANDLE,
      title: twitterTitle,
      description: twitterDescription,
      images: [
        buildSocialImageDescriptor({
          title: twitterTitle,
          description: twitterDescription,
          path,
          host,
          badge,
          type: 'twitter',
        }),
      ],
    },
  }
}

/**
 * Build a JSON-LD WebPage schema object for a given route.
 * Includes Organization and WebSite references.
 */
export function buildWebPageStructuredData(options: {
  name: string
  path: string
  description: string
}) {
  const siteUrl = getSiteUrl()
  const canonicalUrl = getCanonicalUrl(options.path)

  return {
    '@context': 'https://schema.org',
    '@graph': [
      {
        '@type': 'Organization',
        '@id': `${siteUrl}/#organization`,
        name: 'MUTX',
        url: siteUrl,
        logo: `${siteUrl}/logo.png`,
        sameAs: [DEFAULT_GITHUB_URL, `https://x.com/${DEFAULT_X_HANDLE.replace('@', '')}`],
      },
      {
        '@type': 'WebSite',
        '@id': `${siteUrl}/#website`,
        name: 'MUTX',
        url: siteUrl,
        publisher: { '@id': `${siteUrl}/#organization` },
      },
      {
        '@type': 'SoftwareApplication',
        '@id': `${siteUrl}/#software`,
        name: 'MUTX',
        applicationCategory: 'DeveloperApplication',
        description:
          'Source-available control plane for AI agent governance, deployment, and observability.',
        operatingSystem: 'macOS',
        url: siteUrl,
        downloadUrl: `${siteUrl}/download`,
        publisher: { '@id': `${siteUrl}/#organization` },
        offers: { '@type': 'Offer', price: '0', priceCurrency: 'USD' },
      },
      {
        '@type': 'WebPage',
        '@id': `${canonicalUrl}#webpage`,
        name: options.name,
        url: canonicalUrl,
        description: options.description,
        isPartOf: { '@id': `${siteUrl}/#website` },
        about: { '@id': `${siteUrl}/#software` },
      },
    ],
  }
}
