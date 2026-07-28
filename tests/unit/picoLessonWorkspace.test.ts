import {
  createDefaultLessonWorkspace,
  normalizeLessonWorkspace,
  persistLessonWorkspace,
} from '../../components/pico/usePicoLessonWorkspace'

describe('pico lesson workspace', () => {
  it('creates a sane default workspace', () => {
    expect(createDefaultLessonWorkspace(3)).toEqual({
      activeStepIndex: 0,
      completedStepIndexes: [],
      notes: '',
      evidence: '',
      updatedAt: null,
    })
  })

  it('normalizes invalid workspace state against the lesson step count', () => {
    const normalized = normalizeLessonWorkspace(
      {
        activeStepIndex: 99,
        completedStepIndexes: [0, 0, 1, 9, -1],
        notes: 'keep this',
        evidence: 'real proof',
        updatedAt: '2026-04-12T10:00:00.000Z',
      },
      3,
    )

    expect(normalized).toEqual({
      activeStepIndex: 2,
      completedStepIndexes: [0, 1],
      notes: 'keep this',
      evidence: 'real proof',
      updatedAt: '2026-04-12T10:00:00.000Z',
    })
  })

  it('invokes the hosted persistence callback with the exact saved checkpoint', () => {
    const persistRemote = jest.fn()
    const workspace = {
      activeStepIndex: 2,
      completedStepIndexes: [0, 1, 2],
      notes: 'Fresh shell verification',
      evidence: 'Hermes returned a working command result.',
      updatedAt: '2026-04-12T10:00:00.000Z',
    }

    persistLessonWorkspace('install-hermes-locally', workspace, persistRemote)

    expect(persistRemote).toHaveBeenCalledTimes(1)
    expect(persistRemote).toHaveBeenCalledWith('install-hermes-locally', workspace)
  })
})
