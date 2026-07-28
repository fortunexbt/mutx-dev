import { PICO_LOCALES } from '../../lib/pico/locale'
import { loadPicoMessages } from '../../lib/pico/messages'

type AuthModeCopy = {
  title: string
  subtitle: string
  submit: string
  loading: string
  toggleQuestion: string
  toggleAction: string
}

type AuthCopy = {
  eyebrow: string
  modes: {
    login: AuthModeCopy
    register: AuthModeCopy
  }
}

function authCopy(messages: unknown): AuthCopy {
  return (messages as { pico: { auth: AuthCopy } }).pico.auth
}

describe('rendered Pico auth copy', () => {
  it('uses the live PicoMUTX account language rendered by the English locale', async () => {
    const { messages } = await loadPicoMessages('en')
    const auth = authCopy(messages)

    expect(auth.eyebrow).toBe('PicoMUTX account')
    expect(auth.modes.login).toEqual({
      title: 'Sign in to PicoMUTX',
      subtitle: 'Use a provider or email to resume your saved progress.',
      submit: 'Sign in',
      loading: 'Signing in...',
      toggleQuestion: 'Need an account?',
      toggleAction: 'Create account',
    })
    expect(auth.modes.register).toEqual({
      title: 'Create your PicoMUTX account',
      subtitle: 'Create an account to save your progress and return to PicoMUTX anytime.',
      submit: 'Create account',
      loading: 'Creating...',
      toggleQuestion: 'Already have an account?',
      toggleAction: 'Sign in',
    })
  })

  it.each(PICO_LOCALES)('%s renders one branded live-account contract', async (locale) => {
    const { messages } = await loadPicoMessages(locale)
    const auth = authCopy(messages)
    const renderedCopy = JSON.stringify(auth)

    expect(auth.eyebrow).toContain('PicoMUTX')
    expect(auth.modes.login.title).toContain('PicoMUTX')
    expect(auth.modes.register.title).toContain('PicoMUTX')
    expect(auth.modes.login.submit.trim()).not.toBe('')
    expect(auth.modes.register.submit.trim()).not.toBe('')
    expect(renderedCopy).not.toMatch(
      /preview|waitlist|save your place|vorschau|vista previa|aperçu|anteprima|prévia|معاينة|プレビュー|미리보기|预览/i,
    )
  })
})
