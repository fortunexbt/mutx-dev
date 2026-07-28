import {
  skillLifecyclePresentation,
  skillsFromMutationEnvelope,
  type SkillRecord,
} from '../../components/dashboard/SkillsPageClient'

function skill(overrides: Partial<SkillRecord> = {}): SkillRecord {
  return {
    id: 'browser_control',
    name: 'Browser Control',
    description: 'Drive a browser.',
    author: 'mutx',
    category: 'Tools',
    source: 'catalog',
    available: true,
    ...overrides,
  }
}

describe('skill lifecycle presentation', () => {
  it('treats legacy installed-only data as configured, not runtime ready', () => {
    expect(skillLifecyclePresentation(skill({ installed: true }))).toMatchObject({
      status: 'configured',
      label: 'Configured',
      configured: true,
      runtimeReady: false,
    })
  })

  it('distinguishes available, runtime-ready, unavailable, and failed records', () => {
    expect(skillLifecyclePresentation(skill())).toMatchObject({
      status: 'available',
      label: 'Available',
      runtimeReady: false,
    })
    expect(
      skillLifecyclePresentation(
        skill({ status: 'runtime_ready', configured: true, runtime_ready: true }),
      ),
    ).toMatchObject({ status: 'runtime_ready', label: 'Runtime ready', runtimeReady: true })
    expect(
      skillLifecyclePresentation(skill({ status: 'unavailable', available: false })),
    ).toMatchObject({ status: 'unavailable', label: 'Unavailable', runtimeReady: false })
    expect(
      skillLifecyclePresentation(
        skill({
          status: 'failed',
          configured: true,
          reconciliation_error: 'Runtime rejected the manifest.',
        }),
      ),
    ).toMatchObject({
      status: 'failed',
      label: 'Failed',
      configured: true,
      runtimeReady: false,
      detail: 'Runtime rejected the manifest.',
    })
  })

  it('uses the returned mutation skill list and rejects missing persistence envelopes', () => {
    const configured = skill({ status: 'configured', configured: true })

    expect(
      skillsFromMutationEnvelope({
        status: 'configured',
        reconciliation_required: true,
        skills: [configured],
      }),
    ).toEqual([configured])
    expect(() => skillsFromMutationEnvelope({ status: 'configured' })).toThrow(
      'did not return the persisted skill state',
    )
  })
})
