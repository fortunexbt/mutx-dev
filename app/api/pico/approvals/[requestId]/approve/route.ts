import { NextRequest } from 'next/server'

import { getApiBaseUrl, hasAuthSession } from '@/app/api/_lib/controlPlane'
import { unauthorized, withErrorHandling } from '@/app/api/_lib/errors'
import { proxyJson } from '@/app/api/_lib/proxy'
import { validateRequest } from '@/app/api/_lib/validation'

import {
  approvalResolveSchema,
  normalizeApprovalMutationConflict,
  validateApprovalRequestId,
} from '@/app/api/pico/approvals/_validation'

export const dynamic = 'force-dynamic'

export async function POST(
  request: NextRequest,
  context: { params: Promise<{ requestId: string }> }
) {
  return withErrorHandling(async () => {
    if (!hasAuthSession(request)) {
      return unauthorized()
    }

    const { requestId } = await context.params
    const requestIdValidation = validateApprovalRequestId(requestId)
    if (!requestIdValidation.success) {
      return requestIdValidation.response
    }

    const payloadValidation = await validateRequest(approvalResolveSchema, request)
    if (!payloadValidation.success) {
      return payloadValidation.response
    }

    return normalizeApprovalMutationConflict(
      await proxyJson(request, `${getApiBaseUrl()}/v1/approvals/${encodeURIComponent(requestIdValidation.requestId)}/approve`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(payloadValidation.data),
        fallbackMessage: 'Failed to approve request',
      }),
    )
  })(request)
}
