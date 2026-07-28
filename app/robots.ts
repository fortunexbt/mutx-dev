import type { MetadataRoute } from 'next'
import { headers } from 'next/headers'

import {
  BLOCKED_CRAWL_PREFIXES,
  getAppUrl,
  getPicoUrl,
  getSiteUrl,
  resolveSeoSurface,
} from '@/lib/seo'

const PICO_BLOCKED_CRAWL_PREFIXES: string[] = [...BLOCKED_CRAWL_PREFIXES, 
  '/academy',
  '/autopilot',
  '/build-ledger',
  '/pricing',
  '/support',
  '/tutor',
  '/start',
  '/wip',
  '/pico',
]

export default async function robots(): Promise<MetadataRoute.Robots> {
  const requestHeaders = await headers()
  const requestHost = requestHeaders.get('x-forwarded-host') ?? requestHeaders.get('host')
  const surface = resolveSeoSurface(requestHost)
  const siteUrl = getSiteUrl()

  if (surface === 'app') {
    const appUrl = getAppUrl()

    return {
      rules: [
        {
          userAgent: '*',
          allow: ['/control', '/opengraph-image', '/twitter-image'],
          disallow: ['/'],
        },
      ],
      sitemap: `${appUrl}/sitemap.xml`,
      host: appUrl,
    }
  }

  if (surface === 'pico') {
    const picoUrl = getPicoUrl()

    return {
      rules: [
        {
          userAgent: '*',
          allow: ['/', '/opengraph-image', '/twitter-image'],
          disallow: PICO_BLOCKED_CRAWL_PREFIXES,
        },
      ],
      sitemap: `${picoUrl}/sitemap.xml`,
      host: picoUrl,
    }
  }

  return {
    rules: [
      {
        userAgent: '*',
        allow: '/',
        disallow: [...BLOCKED_CRAWL_PREFIXES],
      },
    ],
    sitemap: `${siteUrl}/sitemap.xml`,
    host: siteUrl,
  }
}
