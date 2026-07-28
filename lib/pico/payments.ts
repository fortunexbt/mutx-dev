export const PICO_PAID_PLAN_IDS = ['starter', 'pro'] as const

export type PicoPaidPlanId = (typeof PICO_PAID_PLAN_IDS)[number]

export type PicoCheckoutResponse = {
  checkout_url: string
  session_id: string
}

export type PicoSubscriptionResponse = {
  plan: string | null
  status: string | null
  current_period_end: string | null
  cancel_at_period_end: boolean | null
  trial_end: string | null
}

export function isPicoPaidPlanId(value: unknown): value is PicoPaidPlanId {
  return typeof value === 'string' && PICO_PAID_PLAN_IDS.some((planId) => planId === value)
}

export function isPicoCheckoutResponse(value: unknown): value is PicoCheckoutResponse {
  if (!value || typeof value !== 'object') return false

  const payload = value as Partial<PicoCheckoutResponse>
  return (
    typeof payload.checkout_url === 'string' &&
    payload.checkout_url.length > 0 &&
    typeof payload.session_id === 'string' &&
    payload.session_id.length > 0
  )
}

export function isPicoSubscriptionResponse(value: unknown): value is PicoSubscriptionResponse {
  if (!value || typeof value !== 'object') return false

  const payload = value as Partial<PicoSubscriptionResponse>
  const isNullableString = (field: unknown) => field === null || typeof field === 'string'

  return (
    isNullableString(payload.plan) &&
    isNullableString(payload.status) &&
    isNullableString(payload.current_period_end) &&
    (payload.cancel_at_period_end === null || typeof payload.cancel_at_period_end === 'boolean') &&
    isNullableString(payload.trial_end)
  )
}
