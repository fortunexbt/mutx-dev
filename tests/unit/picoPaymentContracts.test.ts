import {
  isPicoCheckoutResponse,
  isPicoPaidPlanId,
  isPicoSubscriptionResponse,
} from '../../lib/pico/payments'

describe('Pico payment browser contracts', () => {
  it('accepts the backend checkout_url response without requiring a legacy url field', () => {
    expect(isPicoCheckoutResponse({
      checkout_url: 'https://checkout.stripe.test/cs_test',
      session_id: 'cs_test',
    })).toBe(true)
    expect(isPicoCheckoutResponse({
      url: 'https://checkout.stripe.test/cs_test',
      session_id: 'cs_test',
    })).toBe(false)
  })

  it.each(['starter', 'pro'])('accepts the stable paid plan id %s', (planId) => {
    expect(isPicoPaidPlanId(planId)).toBe(true)
  })

  it.each(['free', 'enterprise', 'price_starter', '', null])(
    'rejects unsupported or provider-specific plan input %p',
    (planId) => {
      expect(isPicoPaidPlanId(planId)).toBe(false)
    },
  )

  it('requires a plan field in subscription status payloads', () => {
    expect(isPicoSubscriptionResponse({
      plan: 'PRO',
      status: 'active',
      current_period_end: null,
      cancel_at_period_end: false,
      trial_end: null,
    })).toBe(true)
    expect(isPicoSubscriptionResponse({ status: 'active' })).toBe(false)
  })
})
