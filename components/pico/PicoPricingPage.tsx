'use client'

import Link from 'next/link'
import { useSearchParams } from 'next/navigation'
import { useState } from 'react'
import { ArrowRight, Check, ExternalLink } from 'lucide-react'
import { useTranslations } from 'next-intl'

import { PicoContactForm } from '@/components/pico/PicoContactForm'
import { PicoLangSwitcher } from '@/components/pico/PicoLangSwitcher'
import { usePicoSession } from '@/components/pico/usePicoSession'
import { usePicoHref } from '@/lib/pico/navigation'
import s from './PicoPricingPage.module.css'

type PlanId = 'free' | 'starter' | 'pro' | 'enterprise'
type PlanCopy = { name: string; price: string; period: string; description: string; features: string[]; cta: string }

const PLANS: Array<{ id: PlanId; priceId: string | null; featured?: boolean; external?: string }> = [
  { id: 'free', priceId: null },
  { id: 'starter', priceId: 'price_1TMrgMLqNfXHzKqSL3dPg1JS', featured: true },
  { id: 'pro', priceId: 'price_1TMrdKLqNfXHzKqS15LrJt9C' },
  { id: 'enterprise', priceId: null, external: 'https://calendly.com/mutxdev' },
]

export function PicoPricingPage() {
  const t = useTranslations('pico.pricingPage')
  const navT = useTranslations('pico.nav')
  const searchParams = useSearchParams()
  const toHref = usePicoHref()
  const session = usePicoSession()
  const [formOpen, setFormOpen] = useState(false)
  const [loading, setLoading] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const currentPlan = session.status === 'authenticated' ? session.user.plan?.toLowerCase() : null
  const requestedPlan = searchParams.get('plan')
  const plans = PLANS.map((plan) => ({ ...plan, ...(t.raw(`livePlans.tiers.${plan.id}`) as PlanCopy) }))

  async function checkout(planId: string, priceId: string) {
    setLoading(planId)
    setError(null)
    try {
      const response = await fetch('/api/pico/checkout', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ priceId }),
      })
      if (response.status === 401) {
        const returnPath = `${toHref('/pricing')}?plan=${encodeURIComponent(planId)}`
        window.location.href = `/login?next=${encodeURIComponent(returnPath)}`
        return
      }
      const payload = await response.json().catch(() => null)
      if (!response.ok || typeof payload?.url !== 'string') throw new Error(t('livePlans.checkoutError'))
      window.location.href = payload.url
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : t('livePlans.checkoutError'))
    } finally {
      setLoading(null)
    }
  }

  return (
    <div className={s.page} data-testid="pico-pricing-route">
      <PicoContactForm open={formOpen} onClose={() => setFormOpen(false)} source="pico-pricing" />
      <header className={s.nav}>
        <Link href={toHref('/')} className={s.brand} aria-label="Pico home">
          <span aria-hidden="true">PX</span>
          <strong>Pico</strong>
          <small>/ MUTX</small>
        </Link>
        <nav aria-label="Pico pricing navigation">
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
                <p className={s.price}>{plan.price}<small>{plan.period}</small></p>
                <p className={s.description}>{plan.description}</p>
                <ul>{plan.features.map((feature) => <li key={feature}><Check />{feature}</li>)}</ul>
                {isCurrent ? <span className={s.current}>{t('livePlans.currentPlan')}</span> : plan.priceId ? (
                  <button
                    type="button"
                    disabled={loading === plan.id}
                    aria-busy={loading === plan.id}
                    onClick={() => checkout(plan.id, plan.priceId!)}
                  >
                    {loading === plan.id ? t('livePlans.loading') : plan.cta}
                    <ArrowRight />
                  </button>
                ) : plan.external ? (
                  <a href={plan.external} target="_blank" rel="noopener noreferrer">{plan.cta}<ExternalLink /></a>
                ) : (
                  <Link href={toHref('/onboarding')}>{plan.cta}<ArrowRight /></Link>
                )}
              </article>
            )
          })}
        </section>

        {error ? <p className={s.error} role="alert">{error}</p> : null}
        <section className={s.final}>
          <p>{t('subtitle')}</p>
          <button type="button" onClick={() => setFormOpen(true)}>{t('secondaryCta')} <ArrowRight /></button>
        </section>
      </main>
    </div>
  )
}
