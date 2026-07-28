import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { renderToStaticMarkup } from 'react-dom/server'

import { SystemState } from '@/components/site/SystemState'

function source(relativePath: string) {
  return readFileSync(join(process.cwd(), relativePath), 'utf8')
}

function contrastRatio(foreground: string, background: string) {
  const luminance = (hex: string) => {
    const channels = hex
      .replace('#', '')
      .match(/.{2}/g)!
      .map((channel) => parseInt(channel, 16) / 255)
      .map((channel) =>
        channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4
      )

    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]
  }

  const foregroundLuminance = luminance(foreground)
  const backgroundLuminance = luminance(background)
  return (
    (Math.max(foregroundLuminance, backgroundLuminance) + 0.05) /
    (Math.min(foregroundLuminance, backgroundLuminance) + 0.05)
  )
}

describe('public and authentication QA contracts', () => {
  it('uses assertive alerts, polite statuses, and a focusable skip-link target', () => {
    const alert = renderToStaticMarkup(
      <SystemState
        code="AUTH-500"
        eyebrow="Authentication"
        title="Sign-in unavailable"
        description="Try again shortly."
        role="alert"
      />
    )
    const status = renderToStaticMarkup(
      <SystemState
        code="AUTH-200"
        eyebrow="Authentication"
        title="Checking session"
        description="This can take a moment."
        role="status"
      />
    )

    expect(alert).toContain('id="main-content"')
    expect(alert).toContain('tabindex="-1"')
    expect(alert).toContain('role="alert"')
    expect(alert).toContain('aria-live="assertive"')
    expect(status).toContain('role="status"')
    expect(status).toContain('aria-live="polite"')
  })

  it('keeps auth metadata and form hints above text contrast thresholds', () => {
    const authCss = source('components/site/AuthSurface.module.css')
    const marketingCss = source('components/site/marketing/MarketingCore.module.css')

    expect(authCss).toContain('color: #858178')
    expect(authCss).toContain('color: #6b675f')
    expect(marketingCss).toMatch(/::placeholder\s*\{\s*color:\s*#6b675f;/)
    expect(contrastRatio('#858178', '#0b0b0b')).toBeGreaterThanOrEqual(4.5)
    expect(contrastRatio('#6b675f', '#f3f0e8')).toBeGreaterThanOrEqual(4.5)
  })

  it('keeps the contact form bounded and gives success a next action', () => {
    const contact = source('components/ContactLeadForm.tsx')

    expect(contact).toContain('const normalizedMessage = message.trim()')
    expect(contact).toContain('messageRef.current?.focus()')
    expect(contact).toContain('maxLength={255}')
    expect(contact).toContain('maxLength={2000}')
    expect(contact).toContain('aria-busy={loading}')
    expect(contact).toContain('Send another inquiry')
    expect(contact).toContain('mailto:hello@mutx.dev')
  })

  it('only marks the exact product destination as the current page', () => {
    const navigation = source('components/site/PublicNav.tsx')

    expect(navigation).toContain('const productActive = item.label === "Product"')
    expect(navigation).toContain('const current = !item.external')
    expect(navigation).toContain('aria-current={current ? "page" : undefined}')
    expect(navigation).not.toContain('aria-current={active ? "page" : undefined}')
  })
})
