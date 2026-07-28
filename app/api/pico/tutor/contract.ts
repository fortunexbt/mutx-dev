import { NextResponse } from 'next/server'

import { classifyTutorFailure } from '@/lib/pico/tutor'

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

function readErrorCode(payload: unknown): string | null {
  if (!isRecord(payload)) return null
  if (isRecord(payload.error) && typeof payload.error.code === 'string') {
    return payload.error.code
  }
  if (isRecord(payload.detail) && typeof payload.detail.code === 'string') {
    return payload.detail.code
  }
  return null
}

const failureCodes = {
  unauthenticated: 'UNAUTHORIZED',
  plan_denied: 'TUTOR_PLAN_REQUIRED',
  provider_required: 'TUTOR_PROVIDER_REQUIRED',
  rate_limited: 'TUTOR_RATE_LIMITED',
  model_unavailable: 'TUTOR_MODEL_UNAVAILABLE',
  malformed_response: 'TUTOR_MALFORMED_RESPONSE',
  unknown: 'TUTOR_REQUEST_FAILED',
} as const

export function tutorProxyError(
  statusCode: number,
  payload: unknown,
  fallbackMessage: string,
) {
  const failure = classifyTutorFailure(statusCode, payload)
  return NextResponse.json(
    {
      status: 'error',
      error: {
        code: readErrorCode(payload) ?? failureCodes[failure.kind],
        message: failure.message || fallbackMessage,
        retryable: failure.retryable,
      },
    },
    { status: statusCode },
  )
}

export function malformedTutorUpstream(message: string) {
  return NextResponse.json(
    {
      status: 'error',
      error: {
        code: failureCodes.malformed_response,
        message,
        retryable: true,
      },
    },
    { status: 502 },
  )
}
