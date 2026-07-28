import { normalizeMemoryPayload } from '../../components/dashboard/MemoryPageClient'

describe('memory dashboard payload normalization', () => {
  it('turns an incomplete response into a safe empty inventory', () => {
    expect(normalizeMemoryPayload({})).toEqual({
      generatedAt: '',
      assistant: null,
      sourceStatus: {
        assistant: 'error',
        sessions: 'error',
        documents: 'error',
        reasoning: 'error',
      },
      summary: {
        sessions: null,
        activeSessions: null,
        sources: null,
        documentJobs: null,
        documentArtifacts: null,
        reasoningJobs: null,
        reasoningArtifacts: null,
      },
      sessions: [],
      sources: [],
      documents: [],
      reasoning: [],
      partials: [
        'The memory proxy returned an incomplete payload; unavailable totals are shown as unknown.',
      ],
    })
  })

  it('keeps authoritative totals and omits records without identifiers', () => {
    const payload = normalizeMemoryPayload({
      summary: {
        sessions: 1,
        activeSessions: 1,
        sources: 1,
        documentJobs: 1,
        documentArtifacts: 2,
        reasoningJobs: 1,
        reasoningArtifacts: 3,
      },
      sourceStatus: {
        assistant: 'ok',
        sessions: 'partial',
        documents: 'ok',
        reasoning: 'ok',
      },
      sessions: [{ id: 'session-1', active: true }, { active: false }, null],
      sources: [{ source: 'gateway', count: 1 }],
      documents: [{ id: 'doc-1', artifacts: 2 }],
      reasoning: [{ id: 'reason-1', artifacts: 3 }, { artifacts: 4 }],
      partials: ['One session record was omitted because the upstream identifier was missing.'],
    })

    expect(payload.summary).toEqual({
      sessions: 1,
      activeSessions: 1,
      sources: 1,
      documentJobs: 1,
      documentArtifacts: 2,
      reasoningJobs: 1,
      reasoningArtifacts: 3,
    })
    expect(payload.sessions[0]).toMatchObject({
      id: 'session-1',
      label: 'session-1',
      source: 'unknown',
      channel: 'direct',
    })
    expect(payload.sessions).toHaveLength(1)
    expect(payload.reasoning).toHaveLength(1)
    expect(payload.sourceStatus.sessions).toBe('partial')
  })
})
