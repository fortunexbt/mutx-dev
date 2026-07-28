import { readFileSync } from 'node:fs'
import { join } from 'node:path'

function readSource(relativePath: string) {
  return readFileSync(join(process.cwd(), relativePath), 'utf8')
}

describe('lane C accessibility contracts', () => {
  it('keeps the Pico welcome tour modal, announced, and focus-contained', () => {
    const source = readSource('components/pico/PicoWelcomeTour.tsx')

    expect(source).toContain('role="dialog"')
    expect(source).toContain('aria-modal="true"')
    expect(source).toContain('aria-labelledby={titleId}')
    expect(source).toContain("t('dialog.step', { current: stepIndex + 1, total: steps.length, eyebrow: step.eyebrow })")
    expect(source).toContain('role="status"')
    expect(source).toContain('aria-live="polite"')
    expect(source).toContain("event.key === 'Escape'")
    expect(source).toContain("event.key !== 'Tab'")
    expect(source).toContain("document.body.style.overflow = 'hidden'")
    expect(source).toContain('sibling.inert = true')
    expect(source).toContain('previousFocus.focus()')
    expect(source).toContain('initialFocusRef.current?.focus()')
  })

  it('associates tutor and webhook controls with labels, errors, and async state', () => {
    const tutorSource = readSource('components/pico/PicoTutorPageClient.tsx')
    const webhookSource = readSource('components/webhooks/WebhooksPageClient.tsx')

    expect(tutorSource).toContain('htmlFor={TUTOR_QUESTION_ID}')
    expect(tutorSource).toContain('id={TUTOR_QUESTION_ID}')
    expect(tutorSource).toContain('aria-invalid={Boolean(error)}')
    expect(tutorSource).toContain('id={TUTOR_QUESTION_ERROR_ID}')
    expect(tutorSource).toContain('aria-busy={loading}')
    expect(tutorSource).toContain('role="alert"')

    expect(webhookSource).toContain('htmlFor={WEBHOOK_SEARCH_ID}')
    expect(webhookSource).toContain('htmlFor={WEBHOOK_URL_ID}')
    expect(webhookSource).toContain('htmlFor={WEBHOOK_EVENTS_ID}')
    expect(webhookSource).toContain('aria-invalid={Boolean(formError)}')
    expect(webhookSource).toContain('aria-describedby={formError ? WEBHOOK_FORM_ERROR_ID : undefined}')
    expect(webhookSource).toContain('aria-busy={submitting}')
    expect(webhookSource).toContain('role="alert"')
  })
})
