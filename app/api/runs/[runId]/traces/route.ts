import { NextRequest, NextResponse } from 'next/server'

import { getApiBaseUrl } from '@/app/api/_lib/controlPlane'
import { withErrorHandling } from '@/app/api/_lib/errors'
import { proxyJson } from '@/app/api/_lib/proxy'


export const dynamic = 'force-dynamic'

/**
 * Proxy for run traces API.
 * GET: List traces for a run
 * POST: Add traces to a run
 */
export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ runId: string }> }
): Promise<NextResponse> {
  return withErrorHandling(async () => {
    const { runId } = await params
    const query = new URL(request.url).search
    return proxyJson(request, `${getApiBaseUrl()}/v1/runs/${runId}/traces${query}`, {
      headers: { 'Content-Type': 'application/json' },
      fallbackMessage: 'Failed to fetch traces',
    })
  })(request)
}

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ runId: string }> }
): Promise<NextResponse> {
  return withErrorHandling(async (req: Request) => {
    const { runId } = await params
    const body = await req.json()

    return proxyJson(request, `${getApiBaseUrl()}/v1/runs/${runId}/traces`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      fallbackMessage: 'Failed to add traces',
    })
  })(request)
}
