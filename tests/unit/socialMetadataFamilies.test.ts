jest.mock('../../app/fonts/app', () => ({ appFontVariables: 'font-vars' }))
jest.mock('next-intl', () => ({
  NextIntlClientProvider: ({ children }: { children: unknown }) => children,
}))
jest.mock('next-intl/server', () => ({
  getLocale: jest.fn(async () => 'en'),
  getMessages: jest.fn(async () => ({})),
  getTranslations: jest.fn(async ({ namespace }: { namespace: string }) => {
    return (key: string, values?: Record<string, string | number>) => {
      if (key === 'title') {
        return values?.title ? String(values.title) : `${namespace} title`
      }

      if (key === 'description') {
        return values?.summary ? String(values.summary) : `${namespace} description`
      }

      return `${namespace}.${key}`
    }
  }),
}))
jest.mock('../../i18n/routing', () => ({
  routing: {
    locales: ['en', 'fr'],
  },
}))

import { metadata as controlMetadata } from '../../app/control/layout'
import { metadata as dashboardMetadata } from '../../app/dashboard/layout'
import { buildPicoPageMetadata } from '../../lib/pico/metadata'

describe('surface-specific metadata families', () => {
  it('keeps dashboard metadata on the app host with explicit image objects', () => {
    expect(dashboardMetadata.alternates?.canonical).toBe('https://app.mutx.dev/dashboard')
    expect(dashboardMetadata.openGraph?.siteName).toBe('MUTX App')
    expect(dashboardMetadata.openGraph?.images).toEqual([
      expect.objectContaining({
        url: expect.stringContaining('https://app.mutx.dev/opengraph-image?'),
        width: 1200,
        height: 630,
        alt: 'Dashboard - MUTX social preview for MUTX App',
      }),
    ])
    expect(dashboardMetadata.twitter?.images).toEqual([
      expect.objectContaining({
        url: expect.stringContaining('https://app.mutx.dev/twitter-image?'),
      }),
    ])
  })

  it('keeps control-plane metadata on the app host with the control badge', () => {
    expect(controlMetadata.alternates?.canonical).toBe('https://app.mutx.dev/control')
    expect(controlMetadata.openGraph?.images).toEqual([
      expect.objectContaining({
        url: expect.stringContaining('https://app.mutx.dev/opengraph-image?'),
      }),
    ])
    expect(controlMetadata.twitter?.images).toEqual([
      expect.objectContaining({
        url: expect.stringContaining('badge=CONTROL+PLANE'),
      }),
    ])
  })

  it('builds pico metadata on the pico host with explicit image objects', async () => {
    const metadata = await buildPicoPageMetadata('pico.pages.academy.meta', '/academy')

    expect(metadata.alternates?.canonical).toBe('https://pico.mutx.dev/academy')
    expect(metadata.alternates?.languages).toEqual(
      expect.objectContaining({
        en: 'https://pico.mutx.dev/academy',
      }),
    )
    expect(metadata.openGraph?.siteName).toBe('PicoMUTX')
    expect(metadata.openGraph?.images).toEqual([
      expect.objectContaining({
        url: expect.stringContaining('https://pico.mutx.dev/opengraph-image?'),
        width: 1200,
        height: 630,
        alt: 'pico.pages.academy.meta title social preview for PicoMUTX',
      }),
    ])
    expect(metadata.twitter?.images).toEqual([
      expect.objectContaining({
        url: expect.stringContaining('https://pico.mutx.dev/twitter-image?'),
      }),
    ])
  })
})
