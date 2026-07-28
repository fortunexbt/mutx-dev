'use client'

import Link from 'next/link'
import { useState } from 'react'
import { useTranslations } from 'next-intl'
import { ArrowRight, ArrowUpRight } from 'lucide-react'

import s from './PicoLandingPoster.module.css'
import { PicoContactForm } from './PicoContactForm'
import { PicoLangSwitcher } from './PicoLangSwitcher'
import { usePicoHref } from '@/lib/pico/navigation'

const PRICING_TIERS = ['free', 'starter', 'pro', 'enterprise'] as const

export function PicoLandingPoster() {
  const t = useTranslations('pico')
  const pricingT = useTranslations('pico.pricingPage')
  const toHref = usePicoHref()
  const [formOpen, setFormOpen] = useState(false)
  const steps = Array.from({ length: 3 }, (_, index) => ({
    title: t(`platform.howItWorks.${index}.title`),
    body: t(`platform.howItWorks.${index}.body`),
  }))
  const diagnosticEvents = [
    {
      index: '01',
      label: t('platform.howItWorks.0.title'),
      value: 'Python 3.11 · agent.py',
      state: t('beforeAfter.beforeLabel'),
      tone: 'trace',
    },
    {
      index: '02',
      label: t('problem.eyebrow'),
      value: t('problem.close'),
      state: t('platform.howItWorks.1.title'),
      tone: 'blocked',
    },
    {
      index: '03',
      label: t('beforeAfter.afterLabel'),
      value: t('beforeAfter.items.0.after'),
      state: t('beforeAfter.afterLabel'),
      tone: 'ready',
    },
    {
      index: '04',
      label: t('platform.howItWorks.2.title'),
      value: t('platform.howItWorks.2.body'),
      state: t('platform.howItWorks.2.title'),
      tone: 'waiting',
    },
  ]
  const evidenceRows = [
    {
      label: t('platform.howItWorks.0.title'),
      value: 'Python 3.11 · agent.py',
      state: t('beforeAfter.beforeLabel'),
      tone: 'pass',
    },
    {
      label: t('problem.eyebrow'),
      value: t('trustBar.items.0'),
      state: t('platform.howItWorks.1.title'),
      tone: 'blocked',
    },
    {
      label: t('platform.howItWorks.1.title'),
      value: t('trustBar.items.1'),
      state: t('beforeAfter.afterLabel'),
      tone: 'pass',
    },
    {
      label: t('platform.howItWorks.2.title'),
      value: t('trustBar.items.2'),
      state: t('platform.howItWorks.2.title'),
      tone: 'waiting',
    },
  ]
  const agents = Array.from({ length: 7 }, (_, index) => ({
    name: t(`agentSlider.items.${index}.name`),
    description: t(`agentSlider.items.${index}.description`),
  }))
  const pricingTiers = PRICING_TIERS.map((tier, index) => ({
    index: `0${index + 1}`,
    key: tier,
    name: pricingT(`livePlans.tiers.${tier}.name`),
    price: pricingT(`livePlans.tiers.${tier}.price`),
    period: pricingT(`livePlans.tiers.${tier}.period`),
    description: pricingT(`livePlans.tiers.${tier}.description`),
    priceNote: (pricingT.raw(`livePlans.tiers.${tier}.features`) as string[])
      .slice(0, 2)
      .join(' · '),
    cta: pricingT(`livePlans.tiers.${tier}.cta`),
    href: tier === 'free'
      ? toHref('/onboarding')
      : tier === 'enterprise'
        ? 'https://calendly.com/mutxdev'
        : `${toHref('/pricing')}?plan=${tier}`,
    recommended: tier === 'starter',
  }))

  return (
    <div data-testid="pico-landing" className={s.page}>
      <PicoContactForm open={formOpen} onClose={() => setFormOpen(false)} source="pico-contact" />

      <header className={s.nav}>
        <Link href={toHref('/')} className={s.brand} aria-label={t('nav.brand')}>
          <span aria-hidden="true">PX</span>
          <strong>Pico</strong>
          <small>{t('nav.brandTag')}</small>
        </Link>
        <nav aria-label={t('nav.sectionsLabel')}>
          <a href="#method">{t('platform.eyebrow')}</a>
          <PicoLangSwitcher />
          <Link href={toHref('/onboarding')} className={s.navCta}>{t('nav.cta')}</Link>
        </nav>
      </header>

      <main id="main-content">
        <section className={s.hero} aria-labelledby="pico-title">
          <div className={s.heroCopy}>
            <p className={s.eyebrow}>
              <span aria-hidden="true" /> {t('hero.badge')} / {t('platform.eyebrow')}
            </p>
            <h1 id="pico-title">
              {t('hero.title')}
              <span>{t('hero.titleAccent')}</span>
            </h1>
            <p className={s.lede}>{t('hero.subtitle')}</p>
            <p className={s.support}>{t('problem.body')}</p>
            <div className={s.heroActions}>
              <Link href={toHref('/onboarding')} className={s.primaryAction}>
                {t('hero.cta')} <ArrowRight className="rtl-directional-icon" aria-hidden="true" />
              </Link>
              <a href="#method">{t('hero.ctaSecondary')}</a>
            </div>
            <p className={s.rollout}>{t('hero.meta')}</p>
          </div>

          <div className={s.diagnosticWrap}>
            <div
              className={s.diagnostic}
              aria-label={`${t('beforeAfter.eyebrow')}: ${t('platform.body')}`}
            >
              <header className={s.diagnosticHeader}>
                <div>
                  <span>{t('platform.sampleLabel')} / {t('problem.eyebrow')}</span>
                  <strong>{t('platform.title')}</strong>
                </div>
                <p><i aria-hidden="true" /> {t('platform.howItWorks.1.title')}</p>
              </header>

              <div className={s.goalStrip}>
                <span>{t('platform.howItWorks.0.title')}</span>
                <p>{t('platform.howItWorks.0.body')}</p>
              </div>

              <ol className={s.diagnosticRail}>
                {diagnosticEvents.map((event) => (
                  <li key={event.index} data-tone={event.tone}>
                    <span className={s.traceNode} aria-hidden="true" />
                    <span className={s.eventIndex}>{event.index}</span>
                    <div>
                      <small>{event.label}</small>
                      <strong>{event.value}</strong>
                    </div>
                    <span className={s.eventState}>{event.state}</span>
                  </li>
                ))}
              </ol>

              <footer className={s.diagnosticFooter}>
                <div>
                  <span>{t('platform.howItWorks.1.title')}</span>
                  <strong>{t('problem.close')}</strong>
                </div>
                <code>agent.py → Python 3.11</code>
              </footer>
            </div>
            <p className={s.recordNote}>{t('platform.sampleLabel')} · {t('trustBar.items.0')}</p>
          </div>
        </section>

        <section id="method" className={s.method} aria-labelledby="method-title">
          <header className={s.methodHeader}>
            <p>{t('platform.eyebrow')}</p>
            <div>
              <h2 id="method-title">{t('platform.title')}</h2>
              <p>{t('platform.body')}</p>
            </div>
          </header>

          <div className={s.methodBoard}>
            <ol className={s.steps}>
              {steps.map((step, index) => (
                <li key={step.title}>
                  <div className={s.stepMeta}>
                    <span>0{index + 1}</span>
                  </div>
                  <div>
                    <h3>{step.title}</h3>
                    <p>{step.body}</p>
                  </div>
                  <span className={s.stepNode} aria-hidden="true" />
                </li>
              ))}
            </ol>

            <aside className={s.evidence} aria-label={t('beforeAfter.title')}>
              <header>
                <span>{t('platform.sampleLabel')}</span>
                <strong>{t('beforeAfter.title')}</strong>
              </header>
              <div className={s.evidenceRows}>
                {evidenceRows.map((row, index) => (
                  <div key={row.label}>
                    <span>0{index + 1}</span>
                    <p><small>{row.label}</small><strong>{row.value}</strong></p>
                    <i data-state={row.tone}>{row.state}</i>
                  </div>
                ))}
              </div>
              <footer>
                <span>{t('platform.howItWorks.1.title')}</span>
                <p>{t('beforeAfter.items.0.after')}</p>
              </footer>
            </aside>
          </div>
        </section>

        <section className={s.agentScope} aria-labelledby="agent-scope-title">
          <header className={s.agentScopeHeader}>
            <p>{t('nav.brand')} / {t('who.eyebrow')}</p>
            <div>
              <h2 id="agent-scope-title">{t('who.title')}</h2>
              <p>{t('who.forYou.0')}</p>
            </div>
          </header>

          <section
            className={s.agentGallery}
            aria-label={t('agentSlider.ariaLabel')}
            tabIndex={0}
            data-interactive="false"
            data-pause="false"
          >
            <div className={s.agentTrack}>
              {agents.map((agent, index) => (
                <article key={agent.name} data-agent-slider-card="primary">
                  <span>AG-0{index + 1}</span>
                  <h3>{agent.name}</h3>
                  <p>{agent.description}</p>
                </article>
              ))}
            </div>
          </section>
        </section>

        <section id="pricing" className={s.pricing} aria-labelledby="pricing-title">
          <header className={s.pricingHeader}>
            <div>
              <p>{pricingT('livePlans.label')}</p>
              <h2 id="pricing-title">{pricingT('livePlans.title')}</h2>
            </div>
            <p>{pricingT('livePlans.body')}</p>
          </header>

          <div className={s.pricingGrid}>
            {pricingTiers.map((tier) => (
              <article
                key={tier.key}
                className={s.pricingCard}
                data-recommended={tier.recommended ? 'true' : 'false'}
              >
                <header>
                  <span>{tier.index}</span>
                  {tier.recommended ? <em>{pricingT('livePlans.badgePopular')}</em> : null}
                </header>
                <div className={s.pricingName}>
                  <h3>{tier.name}</h3>
                  <p>
                    <bdi dir="ltr"><strong>{tier.price}</strong><span>{tier.period}</span></bdi>
                  </p>
                </div>
                <p className={s.pricingDescription}>{tier.description}</p>
                <p className={s.pricingNote}>
                  <span>{tier.priceNote}</span>
                </p>
                <Link href={tier.href} className={s.pricingAction}>
                  {tier.cta} <ArrowRight className="rtl-directional-icon" aria-hidden="true" />
                </Link>
              </article>
            ))}
          </div>
        </section>

        <section className={s.final} aria-labelledby="pico-final-title">
          <div>
            <p>{t('finalCta.eyebrow')}</p>
            <h2 id="pico-final-title">{t('finalCta.title')}</h2>
          </div>
          <div className={s.finalCopy}>
            <p>{t('finalCta.body')}</p>
            <div className={s.finalActions}>
              <Link href={toHref('/onboarding')} className={s.primaryAction}>
                {t('finalCta.ctaButton')} <ArrowRight className="rtl-directional-icon" aria-hidden="true" />
              </Link>
              <button type="button" onClick={() => setFormOpen(true)} className={s.secondaryAction}>
                {t('pricingPage.secondaryCta')}
              </button>
              <Link href="/">
                MUTX <ArrowUpRight aria-hidden="true" />
              </Link>
            </div>
          </div>
        </section>
      </main>
    </div>
  )
}
