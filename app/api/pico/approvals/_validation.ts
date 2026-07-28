import { NextResponse } from 'next/server'
import { z } from 'zod'

import { badRequest } from '@/app/api/_lib/errors'

export const approvalCreateSchema = z
  .object({
    agent_id: z.string().trim().min(1, 'agent_id is required').max(255, 'agent_id is too long'),
    session_id: z.string().trim().min(1, 'session_id is required').max(255, 'session_id is too long'),
    action_type: z.string().trim().min(1, 'action_type is required').max(255, 'action_type is too long'),
    reviewer_id: z.string().uuid('reviewer_id must be a UUID'),
    payload: z.record(z.string(), z.unknown()).default({}),
  })
  .strict()

export const approvalResolveSchema = z
  .object({
    comment: z.string().trim().max(1000, 'comment is too long').nullable().optional(),
  })
  .strict()

export function validateApprovalRequestId(requestId: string) {
  const result = z.string().trim().min(1, 'requestId is required').max(255, 'requestId is too long').safeParse(requestId)

  if (!result.success) {
    return {
      success: false as const,
      response: badRequest(result.error.issues[0]?.message ?? 'Invalid requestId'),
    }
  }

  return {
    success: true as const,
    requestId: result.data,
  }
}

export async function normalizeApprovalMutationConflict(response: NextResponse) {
  if (response.status !== 400) {
    return response
  }

  const payload = (await response.clone().json().catch(() => null)) as { detail?: unknown } | null
  if (typeof payload?.detail !== 'string' || !/^Cannot (approve|reject) request in /i.test(payload.detail)) {
    return response
  }

  return new NextResponse(response.body, {
    status: 409,
    headers: response.headers,
  })
}
