import { readFileSync } from 'node:fs'
import { join } from 'node:path'

import { getPicoDirection, PICO_LOCALES, resolvePicoLocale } from '@/lib/pico/locale'
import { loadPicoMessages } from '@/lib/pico/messages'

type MessageTree = Record<string, unknown>

function flatten(value: unknown, prefix = '', output = new Map<string, string>()) {
  if (typeof value === 'string') {
    output.set(prefix, value)
    return output
  }

  if (Array.isArray(value)) {
    value.forEach((child, index) => flatten(child, `${prefix}.${index}`, output))
    return output
  }

  if (value && typeof value === 'object') {
    for (const [key, child] of Object.entries(value)) {
      flatten(child, prefix ? `${prefix}.${key}` : key, output)
    }
  }

  return output
}

describe('Pico locale contracts', () => {
  beforeAll(() => {
    jest.spyOn(console, 'warn').mockImplementation(() => undefined)
  })

  afterAll(() => {
    jest.restoreAllMocks()
  })

  it('normalizes locale variants and derives Arabic direction from one canonical helper', () => {
    expect(resolvePicoLocale('pt-BR')).toBe('pt')
    expect(resolvePicoLocale('ar-SA')).toBe('ar')
    expect(resolvePicoLocale('unknown')).toBe('en')
    expect(getPicoDirection('ar')).toBe('rtl')
    expect(getPicoDirection('de')).toBe('ltr')
  })

  it('loads the same effective key shape for all ten locales', async () => {
    const warning = jest.mocked(console.warn)
    warning.mockClear()
    const english = await loadPicoMessages('en')
    const englishKeys = [...flatten(english.messages as MessageTree).keys()].sort()

    for (const locale of PICO_LOCALES) {
      const loaded = await loadPicoMessages(locale)
      expect(loaded.locale).toBe(locale)
      expect([...flatten(loaded.messages as MessageTree).keys()].sort()).toEqual(englishKeys)
    }

    expect(warning).not.toHaveBeenCalled()
  })

  it('builds effective English from defaults and raw catalog-only branches', async () => {
    const english = await loadPicoMessages('en')
    const messages = flatten(english.messages as MessageTree)

    expect(messages.get('pico.authRecovery.verifyEmail.verifying')).toBe(
      'Verifying your email...',
    )
    expect(messages.get('pico.autopilotPage.shell.title')).toEqual(
      expect.any(String),
    )
  })

  it('resolves every generated-content lookup instead of rendering raw message keys', async () => {
    const generatedLookupPaths = [
      'pico.buildLedger.remote.defaults.3',
      'pico.buildLedger.remote.defaults.4',
      ...(['fresh', 'stale', 'unavailable'] as const).flatMap((state) => [
        `pico.autopilotPage.runtimePresentation.${state}.label`,
        `pico.autopilotPage.runtimePresentation.${state}.detail`,
      ]),
      ...[0, 1, 2].flatMap((index) => [
        `pico.autopilotPage.visuals.${index}.index`,
        `pico.autopilotPage.visuals.${index}.label`,
        `pico.autopilotPage.visuals.${index}.title`,
        `pico.autopilotPage.visuals.${index}.caption`,
        `pico.tutorPage.form.questionProtocol.${index}`,
        `pico.onboardingPage.protocol.items.${index}.title`,
        `pico.onboardingPage.protocol.items.${index}.body`,
      ]),
      ...['stack', 'os', 'provider', 'goal'].map(
        (field) => `pico.onboardingPage.coach.fields.${field}`,
      ),
      ...['npm', 'brew', 'binary', 'manual'].map(
        (method) => `pico.onboardingPage.runtime.installMethods.${method}`,
      ),
      ...['client_required', 'healthy', 'degraded', 'offline', 'warning', 'unknown'].map(
        (status) => `pico.onboardingPage.runtime.statusOptions.${status}`,
      ),
      ...['hermes', 'openclaw', 'nanoclaw', 'picoclaw'].flatMap((stack) => [
        `pico.onboardingPage.stack.items.${stack}.whyNow`,
        `pico.onboardingPage.stack.items.${stack}.latestSignal`,
      ]),
    ]

    for (const locale of PICO_LOCALES) {
      const loaded = await loadPicoMessages(locale)
      const messages = flatten(loaded.messages as MessageTree)
      const rawCatalog = JSON.parse(
        readFileSync(join(process.cwd(), 'messages', `${locale}.json`), 'utf8'),
      ) as MessageTree
      const rawMessages = flatten(rawCatalog)

      for (const path of generatedLookupPaths) {
        const message = messages.get(path)
        expect(message).toEqual(expect.any(String))
        expect(message).not.toBe(path)
        expect(message).not.toMatch(/^pico\./)

        const rawMessage = rawMessages.get(path)
        expect(rawMessage).toEqual(expect.any(String))
        expect(rawMessage).not.toBe(path)
        expect(rawMessage).not.toMatch(/^pico\./)
      }
    }
  })

  it('keeps locale announcements translated and the Free Tutor promise truthful', async () => {
    const english = await loadPicoMessages('en')
    const englishMessages = flatten(english.messages as MessageTree)

    expect(englishMessages.get('pico.content.planMatrix.free.tutor')).toBe(
      'Read-only Academy guidance',
    )

    for (const locale of PICO_LOCALES.filter((candidate) => candidate !== 'en')) {
      const loaded = await loadPicoMessages(locale)
      const messages = flatten(loaded.messages as MessageTree)
      expect(messages.get('pico.localeSwitcher.changedTo')).toContain('{language}')
      expect(messages.get('pico.localeSwitcher.changedTo')).not.toBe(
        englishMessages.get('pico.localeSwitcher.changedTo'),
      )
      expect(messages.get('pico.content.planMatrix.free.tutor')).not.toMatch(
        /daily|diario|quotidien|giornaliero|毎日|매일|每日|يومي/i,
      )
    }
  })

  it('describes the reachable session banner as a PicoMUTX account flow', async () => {
    for (const locale of PICO_LOCALES) {
      const loaded = await loadPicoMessages(locale)
      const messages = flatten(loaded.messages as MessageTree)
      const loadingBody = messages.get('pico.sessionBanner.loading.body')
      const accountChip = messages.get('pico.sessionBanner.anonymous.chips.picoHostAuth')

      expect(loadingBody).toContain('PicoMUTX')
      expect(accountChip).toContain('PicoMUTX')
      expect(`${loadingBody} ${accountChip}`).not.toMatch(
        /local preview|host[- ]auth|host authentication|host de Pico|hôte Pico|host pico|Pico ホスト|Pico 호스트|Pico 主机|مضيف بيكو/i,
      )
    }
  })
})
