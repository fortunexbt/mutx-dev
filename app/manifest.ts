import type { MetadataRoute } from 'next'

import { getSiteUrl } from '@/lib/seo'

export default function manifest(): MetadataRoute.Manifest {
  const siteUrl = getSiteUrl()

  return {
    name: 'MUTX',
    short_name: 'MUTX',
    description:
      'The open control plane for deployed AI agents across runtime operations, governance, releases, and operator workflows.',
    start_url: '/',
    scope: '/',
    display: 'standalone',
    background_color: '#060810',
    theme_color: '#060810',
    categories: ['developer tools', 'productivity', 'utilities'],
    icons: [
      {
        src: '/favicon-32x32.png',
        sizes: '32x32',
        type: 'image/png',
      },
      {
        src: '/favicon-16x16.png',
        sizes: '16x16',
        type: 'image/png',
      },
      {
        src: '/apple-touch-icon.png',
        sizes: '180x180',
        type: 'image/png',
      },
      {
        src: '/android-chrome-192x192.png',
        sizes: '192x192',
        type: 'image/png',
      },
      {
        src: '/android-chrome-512x512.png',
        sizes: '512x512',
        type: 'image/png',
      },
    ],
    screenshots: [
      {
        src: `${siteUrl}/landing/webp/docs-surface.webp`,
        sizes: '1536x1024',
        type: 'image/webp',
        label: 'MUTX operator workspace',
      },
    ],
  }
}
