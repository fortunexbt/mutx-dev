'use client'

import Link from 'next/link'
import { useSearchParams } from 'next/navigation'
import { useCallback, useEffect, useState } from 'react'
import { ArrowRight, Check, ExternalLink } from 'lucide-react'
import { useTranslations } from 'next-intl'

import { PicoContactForm } from '@/components/pico/PicoContactForm'
import { PicoLangSwitcher } from '@/components/pico/PicoLangSwitcher'
import { usePicoSession } from '@/components/pico/usePicoSession'
import { usePicoHref } from '@/lib/pico/navigation'
import {
  isPicoCheckoutResponse,
  isPicoPaidPlanId,
  isPicoSubscriptionResponse,
  type PicoPaidPlanId,
  type PicoSubscriptionResponse,
} from '@/lib/pico/payments'
import s from './PicoPricingPage.module.css'

type PlanId = 'free' | 'starter' | 'pro' | 'enterprise'
type PlanCopy = { name: string; price: string; period: string; description: string; features: string[]; cta: string }
type Notice = {
  tone: 'info' | 'success' | 'error'
  message: string
  action?:
    | { kind: 'retry-checkout'; label: string; planId: PicoPaidPlanId }
    | { kind: 'retry-sync'; label: string; planId: PicoPaidPlanId }
    | { kind: 'sign-in'; label: string; planId: PicoPaidPlanId }
}
type SubscriptionResult =
  | { ok: true; plan: PlanId }
  | { ok: false; status: number }

const PLANS: Array<{
  id: PlanId
  checkoutPlanId?: PicoPaidPlanId
  featured?: boolean
  external?: string
}> = [
  { id: 'free' },
  { id: 'starter', checkoutPlanId: 'starter', featured: true },
  { id: 'pro', checkoutPlanId: 'pro' },
  { id: 'enterprise', external: 'https://calendly.com/mutxdev' },
]

const ACTIVE_SUBSCRIPTION_STATUSES = new Set(['active', 'trialing', 'past_due'])
const CHECKOUT_CONFIRMATION_ATTEMPTS = 4
const CHECKOUT_CONFIRMATION_DELAY_MS = 750

function planFromSubscription(payload: PicoSubscriptionResponse): PlanId {
  const plan = payload.plan?.toLowerCase()
  if (isPicoPaidPlanId(plan) && payload.status && ACTIVE_SUBSCRIPTION_STATUSES.has(payload.status)) {
    return plan
  }
  return 'free'
}

async function loadSubscription(): Promise<SubscriptionResult> {
  try {
    const response = await fetch('/api/pico/checkout', {
      credentials: 'include',
      cache: 'no-store',
    })
    const payload: unknown = await response.json().catch(() => null)

    if (!response.ok) return { ok: false, status: response.status }
    if (!isPicoSubscriptionResponse(payload)) return { ok: false, status: 502 }

    return { ok: true, plan: planFromSubscription(payload) }
  } catch {
    return { ok: false, status: 0 }
  }
}

function waitForCheckoutSync() {
  return new Promise((resolve) => window.setTimeout(resolve, CHECKOUT_CONFIRMATION_DELAY_MS))
}

export function PicoPricingPage() {
  const t = useTranslations('pico.pricingPage')
  const navT = useTranslations('pico.nav')
  const searchParams = useSearchParams()
  const toHref = usePicoHref()
  const session = usePicoSession()
  const [formOpen, setFormOpen] = useState(false)
  const [loading, setLoading] = useState<PicoPaidPlanId | null>(null)
  const [notice, setNotice] = useState<Notice | null>(null)
  const [subscriptionPlan, setSubscriptionPlan] = useState<PlanId | null>(null)
  const [syncingPlan, setSyncingPlan] = useState<PicoPaidPlanId | null>(null)
  const [checkoutReturn] = useState(() => ({
    state: searchParams.get('checkout'),
    sessionId: searchParams.get('session_id'),
    planId: searchParams.get('plan'),
  }))
  const sessionPlan = session.status === 'authenticated' ? session.user.plan?.toLowerCase() : null
  const currentPlan = subscriptionPlan ?? sessionPlan
  const checkoutState = checkoutReturn.state
  const checkoutSessionId = checkoutReturn.sessionId
  const requestedPlan = searchParams.get('plan')
  const returnedPlan = isPicoPaidPlanId(checkoutReturn.planId) ? checkoutReturn.planId : null
  const plans = PLANS.map((plan) => ({ ...plan, ...(t.raw(`livePlans.tiers.${plan.id}`) as PlanCopy) }))
  const planName = useCallback(
    (planId: PicoPaidPlanId) => t(`livePlans.tiers.${planId}.name`),
    [t],
  )

  const cleanCheckoutUrl = useCallback(() => {
    const url = new URL(window.location.href)
    url.searchParams.delete('checkout')
    url.searchParams.delete('session_id')
    window.history.replaceState(window.history.state, '', `${url.pathname}${url.search}${url.hash}`)
  }, [])

  const confirmSubscription = useCallback(async (
    planId: PicoPaidPlanId,
    isActive: () => boolean = () => true,
  ) => {
    setSyncingPlan(planId)
    setNotice({ tone: 'info', message: t('checkout.confirming', { plan: planName(planId) }) })

    for (let attempt = 0; attempt < CHECKOUT_CONFIRMATION_ATTEMPTS; attempt += 1) {
      const result = await loadSubscription()
      if (!isActive()) return

      if (!result.ok) {
        setSyncingPlan(null)
        if (result.status === 401) {
          setNotice({
            tone: 'error',
            message: t('checkout.signInAgain'),
            action: { kind: 'sign-in', label: t('checkout.signIn'), planId },
          })
        } else if (result.status === 403) {
          setNotice({
            tone: 'error',
            message: t('checkout.billingForbidden'),
          })
        } else {
          setNotice({
            tone: 'error',
            message: t('checkout.refreshFailed'),
            action: { kind: 'retry-sync', label: t('checkout.retryRefresh'), planId },
          })
        }
        return
      }

      setSubscriptionPlan(result.plan)
      if (result.plan === planId) {
        setSyncingPlan(null)
        setNotice({
          tone: 'success',
          message: t('checkout.active', { plan: planName(planId) }),
        })
        return
      }

      if (attempt < CHECKOUT_CONFIRMATION_ATTEMPTS - 1) {
        await waitForCheckoutSync()
      }
    }

    if (!isActive()) return
    setSyncingPlan(null)
    setNotice({
      tone: 'info',
      message: t('checkout.stillSyncing'),
      action: { kind: 'retry-sync', label: t('checkout.refreshPlan'), planId },
    })
  }, [planName, t])

  useEffect(() => {
    if (!checkoutState) return
    cleanCheckoutUrl()

    if (checkoutState === 'canceled') {
      setNotice({
        tone: 'info',
        message: t('checkout.canceled'),
      })
      return
    }

    if (checkoutState !== 'success' || !returnedPlan || !checkoutSessionId) {
      setNotice({
        tone: 'error',
        message: t('checkout.incompleteReturn'),
      })
      return
    }

    let active = true
    void confirmSubscription(returnedPlan, () => active)
    return () => {
      active = false
    }
  }, [checkoutSessionId, checkoutState, cleanCheckoutUrl, confirmSubscription, returnedPlan])

  useEffect(() => {
    if (session.status !== 'authenticated' || checkoutState === 'success') return

    let active = true
    void loadSubscription().then((result) => {
      if (active && result.ok) setSubscriptionPlan(result.plan)
    })
    return () => {
      active = false
    }
  }, [checkoutState, session.status])

  async function checkout(planId: PicoPaidPlanId) {
    setLoading(planId)
    setNotice(null)
    try {
      const response = await fetch('/api/pico/checkout', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ planId }),
      })
      if (response.status === 401) {
        const returnPath = `${toHref('/pricing')}?plan=${encodeURIComponent(planId)}`
        window.location.href = `/login?next=${encodeURIComponent(returnPath)}`
        return
      }
      const payload: unknown = await response.json().catch(() => null)
      if (!response.ok) {
        const message = response.status === 403
          ? t('checkout.forbidden')
          : response.status === 503
            ? t('checkout.unavailable')
            : t('livePlans.checkoutError')
        setNotice(response.status === 403
          ? { tone: 'error', message }
          : {
              tone: 'error',
              message,
              action: { kind: 'retry-checkout', label: t('checkout.retryCheckout'), planId },
            })
        return
      }
      if (!isPicoCheckoutResponse(payload)) throw new Error(t('livePlans.checkoutError'))

      const checkoutUrl = new URL(payload.checkout_url, window.location.origin)
      if (checkoutUrl.protocol !== 'https:' && checkoutUrl.protocol !== 'http:') {
        throw new Error(t('livePlans.checkoutError'))
      }
      window.location.assign(checkoutUrl.toString())
    } catch {
      setNotice({
        tone: 'error',
        message: t('livePlans.checkoutError'),
        action: { kind: 'retry-checkout', label: t('checkout.retryCheckout'), planId },
      })
    } finally {
      setLoading(null)
    }
  }

  function handleNoticeAction(action: NonNullable<Notice['action']>) {
    if (action.kind === 'retry-checkout') {
      void checkout(action.planId)
      return
    }
    if (action.kind === 'retry-sync') {
      void confirmSubscription(action.planId)
      return
    }

    const returnPath = `${toHref('/pricing')}?plan=${encodeURIComponent(action.planId)}`
    window.location.href = `/login?next=${encodeURIComponent(returnPath)}`
  }

  return (
    <div className={s.page} data-testid="pico-pricing-route">
      <PicoContactForm open={formOpen} onClose={() => setFormOpen(false)} source="pico-pricing" />
      <header className={s.nav}>
        <Link href={toHref('/')} className={s.brand} aria-label={t('navigation.homeLabel')}>
          <span aria-hidden="true">PX</span>
          <strong>Pico</strong>
          <small>/ MUTX</small>
        </Link>
        <nav aria-label={t('navigation.label')}>
          <Link href={toHref('/')}>{t('returnToLanding')}</Link>
          <Link href={toHref('/support')}>{t('secondaryCta')}</Link>
          <PicoLangSwitcher />
          <button type="button" onClick={() => setFormOpen(true)}>{navT('cta')}</button>
        </nav>
      </header>

      <main id="main-content">
        <section className={s.hero}>
          <p>{t('eyebrow')}</p>
          <h1>{t('title')}</h1>
          <span>{t('subtitle')}</span>
        </section>

        {notice ? (
          <section
            className={`${s.notice} ${s[notice.tone]}`}
            role={notice.tone === 'error' ? 'alert' : 'status'}
            aria-live={notice.tone === 'error' ? 'assertive' : 'polite'}
            data-testid="pico-checkout-notice"
          >
            <p>{notice.message}</p>
            {notice.action ? (
              <button type="button" onClick={() => notice.action && handleNoticeAction(notice.action)}>
                {notice.action.label}
                <ArrowRight className="rtl-directional-icon" aria-hidden="true" />
              </button>
            ) : null}
          </section>
        ) : null}

        <section className={s.plans} aria-label={t('livePlans.label')} data-testid="pico-pricing-live-plans">
          {plans.map((plan, index) => {
            const isCurrent = currentPlan === plan.id
            const isRequested = requestedPlan === plan.id
            return (
              <article
                key={plan.id}
                className={[plan.featured ? s.featured : '', isRequested ? s.requested : ''].filter(Boolean).join(' ') || undefined}
              >
                <div className={s.planTop}><span>0{index + 1}</span>{plan.featured ? <b>{t('livePlans.badgePopular')}</b> : null}</div>
                <h2>{plan.name}</h2>
                <p className={s.price}><bdi dir="ltr">{plan.price}<small>{plan.period}</small></bdi></p>
                <p className={s.description}>{plan.description}</p>
                <ul>{plan.features.map((feature) => <li key={feature}><Check />{feature}</li>)}</ul>
                {isCurrent ? <span className={s.current} aria-label={`${plan.name}: ${t('livePlans.currentPlan')}`}>{t('livePlans.currentPlan')}</span> : plan.checkoutPlanId ? (
                  <button
                    type="button"
                    disabled={loading !== null || syncingPlan !== null}
                    aria-busy={loading === plan.id}
                    onClick={() => plan.checkoutPlanId && checkout(plan.checkoutPlanId)}
                  >
                    {loading === plan.id
                      ? t('livePlans.loading')
                      : syncingPlan === plan.id
                        ? t('checkout.confirmingShort')
                        : plan.cta}
                    <ArrowRight className="rtl-directional-icon" aria-hidden="true" />
                  </button>
                ) : plan.external ? (
                  <a href={plan.external}>{plan.cta}<ExternalLink aria-hidden="true" /></a>
                ) : (
                  <Link href={toHref('/onboarding')}>{plan.cta}<ArrowRight className="rtl-directional-icon" aria-hidden="true" /></Link>
                )}
              </article>
            )
          })}
        </section>
        <section className={s.final}>
          <p>{t('subtitle')}</p>
          <button type="button" onClick={() => setFormOpen(true)}>{t('secondaryCta')} <ArrowRight className="rtl-directional-icon" aria-hidden="true" /></button>
        </section>
      </main>
    </div>
  )
}
