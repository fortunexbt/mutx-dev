import { headers } from 'next/headers'
import { permanentRedirect } from 'next/navigation'

import { isPicoHost } from '@/lib/auth/redirects'

export default async function LegacyPicoBuildLedgerRedirect() {
  const host = (await headers()).get('host')?.split(':')[0] ?? null

  permanentRedirect(isPicoHost(host) ? '/build-ledger' : '/pico/build-ledger')
}
