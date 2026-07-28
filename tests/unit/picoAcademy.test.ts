import {
  applyLessonCompleted,
  createDefaultPicoProgress,
  derivePicoProgress,
  getLessonBySlug,
  getPicoLessonCompletionStatus,
  mergePicoProgress,
  normalizePicoProgress,
  selectTrack,
  updateLessonWorkspace,
  type PicoProgressState,
} from '../../lib/pico/academy'
import { answerPicoTutorQuestion } from '../../lib/pico/tutor'

const CHECKPOINT_AT = '2026-04-12T10:00:00.000Z'

function saveValidCheckpoint(progress: PicoProgressState, lessonSlug: string) {
  const lesson = getLessonBySlug(lessonSlug)
  if (!lesson) throw new Error(`Unknown lesson: ${lessonSlug}`)

  return updateLessonWorkspace(progress, lessonSlug, {
    activeStepIndex: lesson.steps.length - 1,
    completedStepIndexes: lesson.steps.map((_, index) => index),
    notes: '',
    evidence: `Verified checkpoint output for ${lessonSlug}`,
    updatedAt: CHECKPOINT_AT,
  })
}

function completeWithEvidence(progress: PicoProgressState, lessonSlug: string) {
  return applyLessonCompleted(saveValidCheckpoint(progress, lessonSlug), lessonSlug)
}

describe('pico academy progress', () => {
  it('unlocks XP and badges after the first two lessons', () => {
    let progress = createDefaultPicoProgress()
    progress = completeWithEvidence(progress, 'install-hermes-locally')
    progress = completeWithEvidence(progress, 'run-your-first-agent')

    const derived = derivePicoProgress(progress)

    expect(derived.completedLessonCount).toBe(2)
    expect(derived.xp).toBeGreaterThan(100)
    expect(derived.badges).toContain('First Spark')
    expect(derived.unlockedLessonSlugs).toContain('deploy-hermes-on-a-vps')
  })

  it('returns a lesson by slug', () => {
    expect(getLessonBySlug('set-a-cost-threshold')?.title).toBe('Set a cost threshold')
  })

  it('prefers the selected track when choosing the next lesson', () => {
    let progress = createDefaultPicoProgress()
    progress = completeWithEvidence(progress, 'install-hermes-locally')
    progress = completeWithEvidence(progress, 'run-your-first-agent')
    const selected = selectTrack(progress, 'deployed-agent')
    const derived = derivePicoProgress(selected)

    expect(derived.nextLesson?.slug).toBe('deploy-hermes-on-a-vps')
  })

  it('keeps local progress when remote auth state is still empty', () => {
    let local = createDefaultPicoProgress()
    local = completeWithEvidence(local, 'install-hermes-locally')

    const merged = mergePicoProgress(local, createDefaultPicoProgress())

    expect(merged.completedLessons).toContain('install-hermes-locally')
  })

  it('reconciles a remote completion marker with its newer local checkpoint', () => {
    const local = saveValidCheckpoint(createDefaultPicoProgress(), 'install-hermes-locally')
    const remote = {
      ...createDefaultPicoProgress(),
      completedLessons: ['install-hermes-locally'],
    }

    const merged = mergePicoProgress(local, remote)

    expect(merged.completedLessons).toEqual(['install-hermes-locally'])
    expect(merged.lessonWorkspaces['install-hermes-locally'].evidence).toContain(
      'Verified checkpoint output',
    )
  })

  it('rejects direct completion attempts without lesson workspace evidence', () => {
    const progress = createDefaultPicoProgress()
    const result = applyLessonCompleted(progress, 'install-hermes-locally')

    expect(result.completedLessons).toEqual([])
    expect(result.milestoneEvents).not.toContain('first_tutorial_completed')
    expect(getPicoLessonCompletionStatus(result, 'install-hermes-locally')).toMatchObject({
      canComplete: false,
      blocker: 'steps',
    })
  })

  it('rejects partial steps, placeholder evidence, and unsaved evidence', () => {
    const lessonSlug = 'install-hermes-locally'
    const lesson = getLessonBySlug(lessonSlug)
    if (!lesson) throw new Error('Expected install lesson')

    const partial = updateLessonWorkspace(createDefaultPicoProgress(), lessonSlug, {
      activeStepIndex: 0,
      completedStepIndexes: [0],
      notes: '',
      evidence: 'A complete-looking command output that cannot bypass missing steps.',
      updatedAt: CHECKPOINT_AT,
    })
    expect(getPicoLessonCompletionStatus(partial, lessonSlug).blocker).toBe('steps')
    expect(applyLessonCompleted(partial, lessonSlug).completedLessons).toEqual([])

    const placeholder = updateLessonWorkspace(createDefaultPicoProgress(), lessonSlug, {
      activeStepIndex: 2,
      completedStepIndexes: lesson.steps.map((_, index) => index),
      notes: '',
      evidence: 'done',
      updatedAt: CHECKPOINT_AT,
    })
    expect(getPicoLessonCompletionStatus(placeholder, lessonSlug).blocker).toBe('evidence')
    expect(applyLessonCompleted(placeholder, lessonSlug).completedLessons).toEqual([])

    const unsaved = updateLessonWorkspace(createDefaultPicoProgress(), lessonSlug, {
      activeStepIndex: 2,
      completedStepIndexes: lesson.steps.map((_, index) => index),
      notes: '',
      evidence: 'Hermes opened successfully from a fresh shell.',
      updatedAt: null,
    })
    expect(getPicoLessonCompletionStatus(unsaved, lessonSlug).blocker).toBe('persistence')
    expect(applyLessonCompleted(unsaved, lessonSlug).completedLessons).toEqual([])
  })

  it('accepts persisted evidence only after every prerequisite and step is complete', () => {
    let progress = createDefaultPicoProgress()
    const firstRunReady = saveValidCheckpoint(progress, 'run-your-first-agent')

    expect(getPicoLessonCompletionStatus(firstRunReady, 'run-your-first-agent')).toMatchObject({
      canComplete: false,
      blocker: 'prerequisite',
    })
    expect(applyLessonCompleted(firstRunReady, 'run-your-first-agent').completedLessons).toEqual([])

    progress = completeWithEvidence(progress, 'install-hermes-locally')
    progress = completeWithEvidence(progress, 'run-your-first-agent')

    expect(progress.completedLessons).toEqual([
      'install-hermes-locally',
      'run-your-first-agent',
    ])
    expect(getPicoLessonCompletionStatus(progress, 'run-your-first-agent')).toMatchObject({
      canComplete: true,
      isComplete: true,
      blocker: null,
    })
  })

  it('removes false or no-longer-evidenced completion markers while retaining resume state', () => {
    const spoofed = normalizePicoProgress({
      ...createDefaultPicoProgress(),
      startedLessons: ['install-hermes-locally'],
      completedLessons: ['install-hermes-locally'],
      milestoneEvents: ['first_tutorial_completed', 'first_agent_run'],
    })
    expect(spoofed.startedLessons).toEqual(['install-hermes-locally'])
    expect(spoofed.completedLessons).toEqual([])
    expect(spoofed.milestoneEvents).toEqual([])
    expect(derivePicoProgress(spoofed).unlockedCapabilities).toEqual([])

    const completed = completeWithEvidence(createDefaultPicoProgress(), 'install-hermes-locally')
    const reopened = updateLessonWorkspace(completed, 'install-hermes-locally', {
      ...completed.lessonWorkspaces['install-hermes-locally'],
      completedStepIndexes: [0, 1],
      updatedAt: '2026-04-12T10:05:00.000Z',
    })

    expect(reopened.completedLessons).toEqual([])
    expect(reopened.startedLessons).toContain('install-hermes-locally')
    expect(reopened.lessonWorkspaces['install-hermes-locally'].completedStepIndexes).toEqual([0, 1])
  })
})

describe('pico tutor', () => {
  it('routes scheduling questions to the workflow lesson', () => {
    const answer = answerPicoTutorQuestion('How do I schedule the workflow to run every day?')
    expect(answer.lessonSlug).toBe('create-a-scheduled-workflow')
    expect(answer.nextActions.length).toBeGreaterThan(0)
  })

  it('escalates risky topics instead of bluffing', () => {
    const answer = answerPicoTutorQuestion('Can I delete production credentials after changing billing?')
    expect(answer.escalationReason).not.toBeNull()
  })
})
