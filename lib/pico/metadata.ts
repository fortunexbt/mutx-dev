import type { Metadata } from 'next'
import { getLocale, getTranslations } from 'next-intl/server'

import { routing } from '@/i18n/routing'
import { resolvePicoLocale } from '@/lib/pico/locale'
import {
  buildPageMetadata,
  getPicoUrl,
} from '@/lib/seo'

export async function buildPicoPageMetadata(
  namespace: string,
  pathname: string,
  values?: Record<string, string | number>,
): Promise<Metadata> {
  const locale = resolvePicoLocale(await getLocale())
  const t = await getTranslations({ locale, namespace })
  const title = t('title', values)
  const description = t('description', values)
  const picoHost = getPicoUrl()
  const pageMetadata = buildPageMetadata({
    title,
    description,
    path: pathname,
    host: picoHost,
    siteName: 'PicoMUTX',
  })
  const url = pathname === '/' ? picoHost : `${picoHost}${pathname}`

  return {
    title,
    description,
    robots:
      pathname === '/build-ledger' || pathname === '/wip'
        ? {
            index: false,
            follow: false,
            nocache: true,
          }
        : undefined,
    alternates: {
      canonical: pageMetadata.alternates?.canonical ?? url,
      languages: Object.fromEntries(
        routing.locales.map((supportedLocale) => [supportedLocale, url]),
      ),
    },
    openGraph: {
      ...pageMetadata.openGraph,
      locale,
      url,
    },
    twitter: pageMetadata.twitter,
  }
}
