import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { PICO_GENERATED_CONTENT } from '../../lib/pico/generatedContent'
import {
  PICO_LIVE_BUILD_LEDGER,
  validatePicoLiveBuildLedger,
} from '../../lib/pico/liveBuildLedger'

describe('Pico live build ledger', () => {
  it('stays aligned with the generated pack and Academy totals', () => {
    expect(validatePicoLiveBuildLedger()).toEqual({
      packDocsMatchGeneratedCount: true,
      lessonsMatchGeneratedCount: true,
      minutesMatchGeneratedCount: true,
    })
    expect(PICO_LIVE_BUILD_LEDGER.packDocs).toHaveLength(17)
    expect(PICO_LIVE_BUILD_LEDGER.academy.lessons).toHaveLength(12)
    expect(PICO_LIVE_BUILD_LEDGER.packDocs.map((document) => document.filename)).toEqual(
      expect.arrayContaining([
        'INSTALL_FLOW.md',
        'SAFETY_POLICY.md',
        'TAILSCALE_PLAYBOOK.md',
        'HERMES.md',
        'OPENCLAW.md',
        'NANOCLAW.md',
        'PICOCLAW.md',
      ]),
    )
  })

  it('exposes official stack sources and private-first access guidance', () => {
    expect(PICO_LIVE_BUILD_LEDGER.stacks).toHaveLength(4)
    expect(
      PICO_LIVE_BUILD_LEDGER.stacks.every((stack) => stack.repoUrl && stack.docsUrl),
    ).toBe(true)
    expect(PICO_LIVE_BUILD_LEDGER.remoteAccess.decisionDefaults).toEqual(
      expect.arrayContaining([
        expect.stringMatching(/tailscale ssh/i),
        expect.stringMatching(/tailscale serve/i),
        expect.stringMatching(/tailscale funnel/i),
      ]),
    )
    expect(PICO_LIVE_BUILD_LEDGER.refreshedAt).toBe(
      PICO_GENERATED_CONTENT.generatedAt,
    )
  })

  it('keeps Open notes anchored to useful content and removes timed navigation', () => {
    const onboardingSource = readFileSync(
      resolve(process.cwd(), 'components/pico/PicoOnboardingPageClient.tsx'),
      'utf8',
    )
    const returnSource = readFileSync(
      resolve(process.cwd(), 'components/pico/PicoBuildLedgerReturn.tsx'),
      'utf8',
    )

    expect(onboardingSource).toContain("toHref('/build-ledger#stack-notes')")
    expect(returnSource).not.toMatch(/setTimeout|location\.assign/)
    expect(returnSource).toContain("href = '/onboarding'")
    expect(returnSource).toContain('usePicoHref()')
  })

  it('publishes the ledger at its finished-product route and keeps /wip as a redirect only', () => {
    const ledgerPageSource = readFileSync(
      resolve(process.cwd(), 'app/pico/build-ledger/page.tsx'),
      'utf8',
    )
    const legacyPageSource = readFileSync(
      resolve(process.cwd(), 'app/pico/wip/page.tsx'),
      'utf8',
    )

    expect(ledgerPageSource).toContain("canonical: 'https://pico.mutx.dev/build-ledger'")
    expect(legacyPageSource).toContain("permanentRedirect(isPicoHost(host) ? '/build-ledger' : '/pico/build-ledger')")
    expect(legacyPageSource).not.toContain('pico-build-ledger')
  })

  it('keeps every ledger navigation target inside the active Pico route family', () => {
    const ledgerPageSource = readFileSync(
      resolve(process.cwd(), 'app/pico/build-ledger/page.tsx'),
      'utf8',
    )

    expect(ledgerPageSource).not.toMatch(/href=["'{`]\.\.\//)
    expect(ledgerPageSource).toContain('PicoBuildLedgerLink')
    expect(ledgerPageSource).toContain('href={`/academy/${lesson.slug}`}')
  })
})
