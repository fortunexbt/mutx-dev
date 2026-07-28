import { NextRequest } from 'next/server'

import { getApiBaseUrl, hasAuthSession } from '@/app/api/_lib/controlPlane'
import { unauthorized, withErrorHandling } from '@/app/api/_lib/errors'
import { proxyJson } from '@/app/api/_lib/proxy'

export const dynamic = 'force-dynamic'

export async function GET(request: NextRequest) {
  return withErrorHandling(async () => {
    if (!hasAuthSession(request)) {
      return unauthorized()
    }

    return proxyJson(request, `${getApiBaseUrl()}/v1/approvals/reviewers`, {
      method: 'GET',
      fallbackMessage: 'Failed to fetch eligible approval reviewers',
    })
  })(request)
}
