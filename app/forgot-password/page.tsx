import { headers } from 'next/headers'

import { PicoForgotPasswordPageClient } from '@/components/pico/PicoForgotPasswordPageClient'
import {
  getDefaultRedirectPathForHost,
  isPicoHost,
  resolveRedirectPath,
} from '@/lib/auth/redirects'

type ForgotPasswordPageProps = {
  searchParams: Promise<{ next?: string | string[] }>
}

export default async function ForgotPasswordPage({ searchParams }: ForgotPasswordPageProps) {
  const host = (await headers()).get('host')?.split(':')[0] ?? null
  const params = await searchParams
  const requestedPath = typeof params.next === 'string' ? params.next : null
  const returnPath = resolveRedirectPath(requestedPath, getDefaultRedirectPathForHost(host))

  return (
    <PicoForgotPasswordPageClient
      returnPath={returnPath}
      hostVariant={isPicoHost(host) ? 'pico' : 'default'}
    />
  )
}
