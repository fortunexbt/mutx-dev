import { readFileSync } from 'node:fs'
import { join } from 'node:path'

import {
  isPicoRouteActive,
  normalizePicoPathname,
  picoEntryHref,
  picoHref,
} from '@/lib/pico/navigation'
import { getPicoRouteSignal } from '@/components/pico/PicoSignalDiagram'
import en from '@/messages/en.json'

describe('pico landing copy', () => {
  const gatedLaunchPattern = /private beta|waitlist|pre-register|preregistr/i

  it('opens the shipped product path without gated-launch wording', () => {
    const picoMessages = en.pico

    expect(picoMessages.nav.cta).toMatch(/start|onboarding/i)
    expect(picoMessages.hero.cta).toMatch(/start|onboarding/i)
    expect(picoMessages.finalCta.ctaButton).toMatch(/start|onboarding/i)
    expect(picoMessages.contactForm.title).toMatch(/team|help|support/i)
    expect(JSON.stringify({
      nav: picoMessages.nav,
      hero: picoMessages.hero,
      finalCta: picoMessages.finalCta,
      faq: picoMessages.faq,
    })).not.toMatch(gatedLaunchPattern)
  })

  it('presents the landing diagnostic as an illustration, not a live record', () => {
    const source = readFileSync(join(process.cwd(), 'components/pico/PicoLandingPoster.tsx'), 'utf8')

    expect(source).not.toContain('PX-104')
    expect(en.pico.platform.sampleLabel).toMatch(/representative|sample/i)
    expect(source).toContain("t('platform.sampleLabel')")
    expect(source).toContain("aria-label={`${t('beforeAfter.eyebrow')}: ${t('platform.body')}`}")
  })

  it('connects landing actions to onboarding and the authoritative live plan ladder', () => {
    const source = readFileSync(join(process.cwd(), 'components/pico/PicoLandingPoster.tsx'), 'utf8')

    expect(source).toContain("usePicoHref()")
    expect(source).toContain("Link href={toHref('/onboarding')}")
    expect(source).toContain("['free', 'starter', 'pro', 'enterprise']")
    expect(source).toContain('livePlans.tiers.${tier}')
    expect(source).not.toContain("['trial', 'starter', 'pro', 'enterprise']")
  })

  it('keeps the commercial ladder and product promise aligned', () => {
    const truthMessages = en.pico
    const livePlans = truthMessages.pricingPage.livePlans

    expect(truthMessages.platform.title).toMatch(/stuck to shipped/i)
    expect(truthMessages.platform.howItWorks[0].title).toBe('Connect')
    expect(truthMessages.platform.howItWorks[1].title).toBe('Fix')
    expect(truthMessages.platform.howItWorks[2].title).toBe('Ship')
    expect(livePlans.tiers.free.price).toBe('$0')
    expect(livePlans.tiers.starter.price).toBe('$9')
    expect(livePlans.tiers.pro.price).toBe('$29')
    expect(livePlans.tiers.enterprise.price).toBe('Custom')
    expect(livePlans.tiers.starter.features).toContain('1,000 monthly credits')
    expect(livePlans.tiers.pro.features).toContain('10,000 monthly credits')
  })

  it('keeps onboarding href helpers host-aware for protected Pico routes', () => {
    expect(picoHref('/pico', '/onboarding')).toBe('/pico/onboarding')
    expect(picoHref('/', '/onboarding')).toBe('/onboarding')
    expect(picoEntryHref('/pico')).toBe('/pico/onboarding')
    expect(picoEntryHref('/')).toBe('/start')
  })

  it('treats canonical-host and internal Pico paths as the same product route', () => {
    expect(normalizePicoPathname('/pico/academy/first-run')).toBe('/academy/first-run')
    expect(normalizePicoPathname('/academy/first-run')).toBe('/academy/first-run')
    expect(isPicoRouteActive('/pico/academy/first-run', '/academy')).toBe(true)
    expect(isPicoRouteActive('/academy/first-run', '/academy')).toBe(true)
    expect(isPicoRouteActive('/autopilot', '/academy')).toBe(false)
    expect(getPicoRouteSignal('/academy/first-run').label).toBe('Lesson marker')
    expect(getPicoRouteSignal('/pico/support').label).toBe('Support marker')
  })
})
