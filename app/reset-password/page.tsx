import { headers } from 'next/headers'
import { Suspense } from 'react'
import { Loader2 } from 'lucide-react'

import { PicoResetPasswordPageClient } from '@/components/pico/PicoResetPasswordPageClient'
import styles from '@/components/site/marketing/MarketingCore.module.css'
import {
  getDefaultRedirectPathForHost,
  isPicoHost,
} from '@/lib/auth/redirects'

export default async function ResetPasswordPage() {
  const host = (await headers()).get('host')?.split(':')[0] ?? null

  return (
    <Suspense
      fallback={
        <div className={styles.page}>
          <main id="main-content" tabIndex={-1} className="flex min-h-screen items-center justify-center">
            <Loader2 className="h-8 w-8 animate-spin" aria-hidden="true" />
          </main>
        </div>
      }
    >
      <PicoResetPasswordPageClient
        fallbackPath={getDefaultRedirectPathForHost(host)}
        hostVariant={isPicoHost(host) ? 'pico' : 'default'}
      />
    </Suspense>
  )
}
