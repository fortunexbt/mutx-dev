import { createHash, randomUUID } from 'node:crypto'
import { NextResponse } from 'next/server'
import { z } from 'zod'

import { getApiBaseUrl } from '@/app/api/_lib/controlPlane'
import { badRequest, serviceUnavailable } from '@/app/api/_lib/errors'
import sql from '@/lib/db'

const CONTROL_PLANE_TIMEOUT_MS = 5_000
const IDEMPOTENCY_KEY_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._:-]{15,127}$/
const LEADS_FALLBACK_MESSAGE =
  'Lead capture is temporarily unavailable. Please email hello@mutx.dev if you need an immediate response.'

const optionalText = (maxLength: number) =>
  z
    .string()
    .trim()
    .max(maxLength)
    .transform((value) => value || undefined)
    .optional()

const leadCaptureSchema = z.object({
  email: z.string().trim().toLowerCase().max(255).email('Invalid email format'),
  name: optionalText(100),
  company: optionalText(200),
  message: optionalText(2_000),
  source: optionalText(120),
  tier: optionalText(50),
  interest: optionalText(80),
  locale: z
    .string()
    .trim()
    .toLowerCase()
    .regex(/^[a-z]{2}(?:-[a-z]{2})?$/, 'Invalid locale format')
    .optional(),
  productUpdatesConsent: z.boolean().optional(),
  honeypot: z.unknown().optional(),
})

type LeadCapturePayload = {
  company?: string
  email: string
  interest?: string
  locale?: string
  message?: string
  name?: string
  product_updates_consent: boolean
  source: string
  tier?: string
}

type LocalLeadRow = LeadCapturePayload & {
  id: string
  created_at: string
  content_hash: string | null
  notification_scheduled_at: string | null
}

function canonicalLeadContent(payload: LeadCapturePayload) {
  return JSON.stringify({
    company: payload.company ?? null,
    email: payload.email,
    interest: payload.interest ?? null,
    locale: payload.locale ?? null,
    message: payload.message ?? null,
    name: payload.name ?? null,
    product_updates_consent: payload.product_updates_consent,
    source: payload.source,
    tier: payload.tier ?? null,
  })
}

function contentHash(payload: LeadCapturePayload) {
  return createHash('sha256').update(canonicalLeadContent(payload), 'utf8').digest('hex')
}

function conflictResponse() {
  return NextResponse.json(
    {
      status: 'error',
      error: {
        code: 'IDEMPOTENCY_CONFLICT',
        message: 'This submission key was already used for different contact information.',
      },
    },
    { status: 409 },
  )
}

function validateIdempotencyKey(request: Request) {
  const header = request.headers.get('idempotency-key')
  if (header === null) return { key: undefined }
  const key = header.trim()
  if (!IDEMPOTENCY_KEY_PATTERN.test(key)) {
    return {
      response: badRequest(
        'Idempotency-Key must be 16-128 characters using letters, numbers, dot, underscore, colon, or hyphen.',
      ),
    }
  }
  return { key }
}

function shouldFallbackToLocalCapture(response: Response) {
  return response.status === 404 || response.status >= 500
}

async function captureLeadLocally(
  payload: LeadCapturePayload,
  idempotencyKey: string | undefined,
): Promise<NextResponse | null> {
  if (!sql) return null

  const leadId = randomUUID()
  const createdAt = new Date().toISOString()
  const hash = contentHash(payload)
  const rows = await sql<LocalLeadRow[]>`
    INSERT INTO leads (
      id,
      email,
      name,
      company,
      message,
      source,
      tier,
      interest,
      locale,
      product_updates_consent,
      idempotency_key,
      content_hash,
      notification_scheduled_at,
      created_at
    )
    VALUES (
      ${leadId}::uuid,
      ${payload.email},
      ${payload.name ?? null},
      ${payload.company ?? null},
      ${payload.message ?? null},
      ${payload.source},
      ${payload.tier ?? null},
      ${payload.interest ?? null},
      ${payload.locale ?? null},
      ${payload.product_updates_consent},
      ${idempotencyKey ?? null},
      ${hash},
      NULL,
      ${createdAt}::timestamptz
    )
    ON CONFLICT (idempotency_key) DO NOTHING
    RETURNING
      id::text,
      email,
      name,
      company,
      message,
      source,
      tier,
      interest,
      locale,
      product_updates_consent,
      content_hash,
      notification_scheduled_at::text,
      created_at::text
  `

  let lead = rows[0]
  let replayed = false
  if (!lead && idempotencyKey) {
    const existingRows = await sql<LocalLeadRow[]>`
      SELECT
        id::text,
        email,
        name,
        company,
        message,
        source,
        tier,
        interest,
        locale,
        product_updates_consent,
        content_hash,
        notification_scheduled_at::text,
        created_at::text
      FROM leads
      WHERE idempotency_key = ${idempotencyKey}
      LIMIT 1
    `
    lead = existingRows[0]
    replayed = true
  }

  if (!lead) return null
  if (lead.content_hash !== hash) return conflictResponse()

  return NextResponse.json(
    {
      id: lead.id,
      email: lead.email,
      name: lead.name,
      company: lead.company,
      message: lead.message,
      source: lead.source,
      tier: lead.tier,
      interest: lead.interest,
      locale: lead.locale,
      product_updates_consent: lead.product_updates_consent,
      created_at: lead.created_at,
      success: true,
      status: 'accepted',
      persisted: true,
      replayed,
      notification_scheduled: Boolean(lead.notification_scheduled_at),
      follow_up: 'unavailable',
      message_to_submitter:
        'Your request was saved. Automated confirmation and team notification are currently unavailable.',
      fallback: 'local-db',
    },
    { status: replayed ? 200 : 201 },
  )
}

export async function capturePublicLead(
  request: Request,
  defaultSource: string,
): Promise<NextResponse> {
  const idempotency = validateIdempotencyKey(request)
  if (idempotency.response) return idempotency.response

  const rawBody: unknown = await request.json().catch(() => null)
  if (!rawBody || typeof rawBody !== 'object' || Array.isArray(rawBody)) {
    return badRequest('Invalid input')
  }
  if ((rawBody as Record<string, unknown>).honeypot) {
    return badRequest('Invalid input')
  }

  const validation = leadCaptureSchema.safeParse(rawBody)
  if (!validation.success) {
    return NextResponse.json(
      {
        status: 'error',
        error: {
          code: 'VALIDATION_ERROR',
          message: 'Request validation failed',
          details: validation.error.flatten().fieldErrors,
        },
      },
      { status: 400 },
    )
  }

  const payload: LeadCapturePayload = {
    email: validation.data.email,
    name: validation.data.name,
    company: validation.data.company,
    message: validation.data.message,
    source: validation.data.source || defaultSource,
    tier: validation.data.tier,
    interest: validation.data.interest,
    locale: validation.data.locale,
    product_updates_consent: validation.data.productUpdatesConsent === true,
  }

  try {
    const headers: Record<string, string> = { 'Content-Type': 'application/json' }
    if (idempotency.key) headers['Idempotency-Key'] = idempotency.key

    const response = await fetch(`${getApiBaseUrl()}/v1/leads`, {
      method: 'POST',
      headers,
      body: JSON.stringify(payload),
      cache: 'no-store',
      signal: AbortSignal.timeout(CONTROL_PLANE_TIMEOUT_MS),
    })
    const responsePayload: unknown = await response.json().catch(() => null)

    if (response.ok) {
      if (
        !responsePayload ||
        typeof responsePayload !== 'object' ||
        (responsePayload as Record<string, unknown>).persisted !== true
      ) {
        return NextResponse.json(
          {
            status: 'error',
            error: {
              code: 'INVALID_PERSISTENCE_ACKNOWLEDGEMENT',
              message: 'Lead capture did not return durable persistence acknowledgement.',
            },
          },
          { status: 502 },
        )
      }
      return NextResponse.json(responsePayload, { status: response.status })
    }

    if (!shouldFallbackToLocalCapture(response)) {
      return NextResponse.json(
        responsePayload ?? { detail: 'Lead capture was rejected' },
        { status: response.status },
      )
    }

    console.warn('Lead capture upstream unavailable; attempting local persistence fallback', {
      status: response.status,
    })
  } catch {
    console.warn('Lead capture upstream network request failed; attempting local persistence fallback')
  }

  try {
    const fallbackResponse = await captureLeadLocally(payload, idempotency.key)
    if (fallbackResponse) return fallbackResponse
  } catch {
    console.error('Lead capture local persistence fallback failed')
  }

  return serviceUnavailable(LEADS_FALLBACK_MESSAGE)
}
