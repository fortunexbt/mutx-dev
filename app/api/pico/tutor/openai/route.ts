import { NextRequest, NextResponse } from 'next/server'

import {
  applyAuthCookies,
  authenticatedFetch,
  getApiBaseUrl,
  hasAuthSession,
} from '@/app/api/_lib/controlPlane'
import { badRequest, unauthorized, withErrorHandling } from '@/app/api/_lib/errors'
import { malformedTutorUpstream, tutorProxyError } from '@/app/api/pico/tutor/contract'
import { normalizeTutorConnectionPayload } from '@/lib/pico/tutor'

export const dynamic = 'force-dynamic'

async function proxyConnectionRequest(
  request: NextRequest,
  init: RequestInit & { fallbackMessage: string },
) {
  if (!hasAuthSession(request)) {
    return unauthorized()
  }

  const { fallbackMessage, ...fetchInit } = init
  const { response, tokenRefreshed, refreshedTokens } = await authenticatedFetch(
    request,
    `${getApiBaseUrl()}/v1/pico/tutor/openai`,
    {
      ...fetchInit,
      cache: 'no-store',
    },
  )

  const payload = await response.json().catch(() => null)
  let nextResponse: NextResponse
  if (!response.ok) {
    nextResponse = tutorProxyError(response.status, payload, fallbackMessage)
  } else {
    const connection = normalizeTutorConnectionPayload(payload)
    nextResponse = connection
      ? NextResponse.json(connection, { status: response.status })
      : malformedTutorUpstream('Tutor provider status could not be verified.')
  }
  if (tokenRefreshed && refreshedTokens) {
    applyAuthCookies(nextResponse, request, refreshedTokens)
  }

  return nextResponse
}

export async function GET(request: NextRequest) {
  return withErrorHandling(async () =>
    proxyConnectionRequest(request, {
      method: 'GET',
      fallbackMessage: 'Failed to load the Pico Tutor OpenAI connection',
    }),
  )(request)
}

export async function PUT(request: NextRequest) {
  return withErrorHandling(async () => {
    if (!hasAuthSession(request)) {
      return unauthorized()
    }

    const body = await request.json().catch(() => ({}))
    const apiKey = typeof body.apiKey === 'string' ? body.apiKey.trim() : ''
    if (!apiKey) {
      return badRequest('OpenAI API key is required')
    }

    return proxyConnectionRequest(request, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ apiKey }),
      fallbackMessage: 'Failed to connect the OpenAI key for Pico Tutor',
    })
  })(request)
}

export async function DELETE(request: NextRequest) {
  return withErrorHandling(async () =>
    proxyConnectionRequest(request, {
      method: 'DELETE',
      fallbackMessage: 'Failed to disconnect the OpenAI key for Pico Tutor',
    }),
  )(request)
}
