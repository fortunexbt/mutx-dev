import { NextRequest, NextResponse } from 'next/server'

import { getApiBaseUrl } from '@/app/api/_lib/controlPlane'
import { proxyJson } from '@/app/api/_lib/proxy'
import { withErrorHandling, badRequest } from '@/app/api/_lib/errors'
import { checkAgentOwnership } from '@/app/api/_lib/ownership'
import { z } from 'zod'


export const dynamic = 'force-dynamic'

export async function GET(request: NextRequest, { params }: { params: Promise<{ agentId: string }> }): Promise<NextResponse> {
  return withErrorHandling(async () => {
    const { agentId } = await params

    const idValidation = z.string().uuid('Invalid agent ID').safeParse(agentId)
    if (!idValidation.success) {
      return badRequest('Invalid agent ID format')
    }

    const ownershipError = await checkAgentOwnership(request, agentId)
    if (ownershipError) {
      return ownershipError
    }

    const encodedAgentId = encodeURIComponent(agentId)

    const { searchParams } = new URL(request.url)
    const path = searchParams.get('path') || ''
    const targetUrl =
      path === 'logs'
        ? `${getApiBaseUrl()}/v1/agents/${encodedAgentId}/logs`
        : path === 'metrics'
          ? `${getApiBaseUrl()}/v1/agents/${encodedAgentId}/metrics`
          : `${getApiBaseUrl()}/v1/agents/${encodedAgentId}`

    return proxyJson(request, targetUrl, {
      method: 'GET',
      fallbackMessage:
        path === 'logs'
          ? 'Failed to fetch agent logs'
          : path === 'metrics'
            ? 'Failed to fetch agent metrics'
            : 'Failed to fetch agent',
    })
  })(request)
}

export async function DELETE(request: NextRequest, { params }: { params: Promise<{ agentId: string }> }): Promise<NextResponse> {
  return withErrorHandling(async () => {
    const { agentId } = await params

    const idValidation = z.string().uuid('Invalid agent ID').safeParse(agentId)
    if (!idValidation.success) {
      return badRequest('Invalid agent ID format')
    }

    const ownershipError = await checkAgentOwnership(request, agentId)
    if (ownershipError) {
      return ownershipError
    }

    return proxyJson(request, `${getApiBaseUrl()}/v1/agents/${encodeURIComponent(agentId)}`, {
      method: 'DELETE',
      fallbackMessage: 'Failed to delete agent',
    })
  })(request)
}

export async function POST(request: NextRequest, { params }: { params: Promise<{ agentId: string }> }): Promise<NextResponse> {
  return withErrorHandling(async () => {
    const { agentId } = await params

    const idValidation = z.string().uuid('Invalid agent ID').safeParse(agentId)
    if (!idValidation.success) {
      return badRequest('Invalid agent ID format')
    }

    const ownershipError = await checkAgentOwnership(request, agentId)
    if (ownershipError) {
      return ownershipError
    }

    const encodedAgentId = encodeURIComponent(agentId)

    const { searchParams } = new URL(request.url)
    const action = searchParams.get('action')

    if (action === 'stop') {
      return proxyJson(request, `${getApiBaseUrl()}/v1/agents/${encodedAgentId}/stop`, {
        method: 'POST',
        fallbackMessage: 'Failed to stop agent',
      })
    }

    if (action === 'deploy') {
      return proxyJson(request, `${getApiBaseUrl()}/v1/agents/${encodedAgentId}/deploy`, {
        method: 'POST',
        fallbackMessage: 'Failed to deploy agent',
      })
    }

    return badRequest('Invalid action')
  })(request)
}
