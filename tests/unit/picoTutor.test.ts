import { getPicoTutorPromptChips } from '../../components/pico/picoTutorPrompts'
import { PICO_LESSONS } from '../../lib/pico/academy'
import {
  classifyTutorFailure,
  getPicoTutorAcademyGuidance,
  getPicoTutorPlanCapabilities,
  LatestTutorRequest,
  normalizeTutorConnectionPayload,
  normalizeTutorReplyPayload,
} from '../../lib/pico/tutor'

const starterEntitlement = {
  authenticated: true,
  plan: 'starter',
  tutorAccess: true,
  minimumPlan: 'starter',
  byokAccess: false,
  byokMinimumPlan: 'pro',
}

const generatedReply = {
  title: 'Install Hermes locally',
  summary: 'Use the install lane and verify PATH from a fresh shell.',
  answer: 'Use the install lane and verify PATH from a fresh shell.',
  confidence: 'high',
  nextActions: ['Install Hermes', 'Re-open the shell', 'Run command -v hermes'],
  lessons: [
    {
      id: 'install-hermes-locally',
      title: 'Install Hermes locally',
      href: '/pico/academy/install-hermes-locally',
    },
  ],
  docs: [
    {
      label: 'github.com',
      href: 'https://github.com/nousresearch/hermes-agent',
      sourcePath: 'github.com',
    },
  ],
  recommendedLessonIds: ['install-hermes-locally'],
  escalate: false,
  structured: {
    situation: 'Hermes is not on PATH after install.',
    diagnosis: 'This is an install verification problem.',
    steps: ['Re-open the shell', 'Run command -v hermes'],
    commands: [{ label: 'Verify binary', code: 'command -v hermes', language: 'bash' }],
    verify: ['The command resolves to a binary path.'],
    ifThisFails: ['Paste the failing install output.'],
    officialLinks: [
      {
        label: 'GitHub',
        href: 'https://github.com/nousresearch/hermes-agent',
        sourcePath: 'github.com',
      },
    ],
    sources: [
      {
        kind: 'knowledge_pack',
        title: 'Hermes',
        sourcePath: 'knowledge/pico_ops/HERMES.md',
      },
    ],
  },
  intent: 'install',
  skillLevel: 'intermediate',
  usedOfficialFallback: true,
  entitlement: starterEntitlement,
  generation: {
    provider: 'openai',
    source: 'platform',
    model: 'gpt-5-mini',
    responseId: 'chatcmpl-tutor-proof',
    completedAt: '2026-07-28T12:00:00Z',
  },
}

describe('Pico tutor payload normalization', () => {
  it('keeps a proof-bearing structured contract intact', () => {
    const reply = normalizeTutorReplyPayload(generatedReply)

    expect(reply?.structured.commands[0]?.code).toBe('command -v hermes')
    expect(reply?.generation.responseId).toBe('chatcmpl-tutor-proof')
    expect(reply?.entitlement.plan).toBe('starter')
  })

  it('refuses legacy or malformed output without generation proof', () => {
    const { generation: _generation, ...unprovenReply } = generatedReply

    expect(normalizeTutorReplyPayload(unprovenReply)).toBeNull()
    expect(normalizeTutorReplyPayload({ answer: 'looks plausible' })).toBeNull()
  })

  it('accepts only internally consistent provider status proof', () => {
    const platform = normalizeTutorConnectionPayload({
      provider: 'openai',
      status: 'platform',
      source: 'platform',
      connected: false,
      model: 'gpt-5-mini',
      message: 'Platform provider configured.',
      providerAvailable: true,
      canConnect: false,
      entitlement: starterEntitlement,
      proof: {
        kind: 'configured_platform_key',
        checkedAt: '2026-07-28T12:00:00Z',
      },
    })

    expect(platform?.status).toBe('platform')
    expect(
      normalizeTutorConnectionPayload({
        ...platform,
        status: 'connected',
        source: 'user',
        connected: true,
      }),
    ).toBeNull()
  })
})

describe('Pico tutor access and failures', () => {
  it.each([
    ['free', false, false],
    ['starter', true, false],
    ['pro', true, true],
    ['enterprise', true, true],
  ])('maps the %s plan without optimistic access', (plan, tutorAccess, byokAccess) => {
    expect(getPicoTutorPlanCapabilities(plan)).toEqual({ tutorAccess, byokAccess })
  })

  it.each([
    [401, 'unauthenticated', false],
    [403, 'plan_denied', false],
    [409, 'provider_required', false],
    [429, 'rate_limited', true],
    [503, 'model_unavailable', true],
  ])('classifies HTTP %i distinctly', (status, kind, retryable) => {
    expect(classifyTutorFailure(status, null)).toMatchObject({ kind, retryable })
  })

  it('aborts an older request lease and rejects its stale response', () => {
    const requests = new LatestTutorRequest()
    const first = requests.begin()
    const second = requests.begin()

    expect(first.signal.aborted).toBe(true)
    expect(requests.isCurrent(first)).toBe(false)
    expect(requests.isCurrent(second)).toBe(true)
    requests.finish(second)
    expect(requests.isCurrent(second)).toBe(false)
  })
})

describe('Pico tutor read-only Academy path', () => {
  const fallbackPrompts = [
    'My lesson is blocked at the first step. What should I check next?',
    'I pasted the command and still get a mismatch. Where is the break?',
  ]

  it('keeps exact Academy guidance without presenting it as generated output', () => {
    const lesson = PICO_LESSONS.find((item) => item.slug === 'install-hermes-locally') ?? null
    const guidance = getPicoTutorAcademyGuidance(lesson, 0)

    expect(guidance).toMatchObject({
      title: 'Install Hermes locally',
      href: '/academy/install-hermes-locally',
      validation: expect.any(String),
    })
  })

  it('hides live prompt chips for attached lessons or unavailable Tutor access', () => {
    const lesson = PICO_LESSONS.find((item) => item.slug === 'install-hermes-locally')

    expect(getPicoTutorPromptChips(lesson ?? null, fallbackPrompts)).toEqual([])
    expect(getPicoTutorPromptChips(null, fallbackPrompts, false)).toEqual([])
    expect(getPicoTutorPromptChips(null, fallbackPrompts)).toEqual(fallbackPrompts)
  })
})
