import { NextRequest } from 'next/server'

import { getApiBaseUrl } from '@/app/api/_lib/controlPlane'
import { withErrorHandling } from '@/app/api/_lib/errors'
import { proxyJson } from '@/app/api/_lib/proxy'

export const dynamic = 'force-dynamic'

function buildTargetUrl(path: string[], search = '') {
  const suffix = path.length > 0 ? `/${path.map(encodeURIComponent).join('/')}` : ''
  return `${getApiBaseUrl()}/v1/governance/attestations${suffix}${search}`
}

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> },
) {
  return withErrorHandling(async () => {
    const { path } = await params
    return proxyJson(request, buildTargetUrl(path, request.nextUrl.search), {
      method: 'GET',
      fallbackMessage: 'Failed to fetch governance attestations',
    })
  })(request)
}

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> },
) {
  return withErrorHandling(async () => {
    const { path } = await params
    const body = await request.text()
    return proxyJson(request, buildTargetUrl(path, request.nextUrl.search), {
      method: 'POST',
      headers: body ? { 'Content-Type': 'application/json' } : undefined,
      body: body || undefined,
      fallbackMessage: 'Failed to verify governance attestations',
    })
  })(request)
}
