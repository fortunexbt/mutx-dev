import {
  type PicoCapabilityUnlock,
  type PicoLesson,
  type PicoLevel,
  type PicoTrack,
} from '@/lib/pico/academy'

export type PicoContentTranslator = (key: string) => string

export function localizePicoLesson(
  lesson: PicoLesson,
  t: PicoContentTranslator,
): PicoLesson {
  const prefix = `lessons.${lesson.slug}`

  return {
    ...lesson,
    title: t(`${prefix}.title`),
    summary: t(`${prefix}.summary`),
    objective: t(`${prefix}.objective`),
    outcome: t(`${prefix}.outcome`),
    expectedResult: t(`${prefix}.expectedResult`),
    validation: t(`${prefix}.validation`),
    steps: lesson.steps.map((step, index) => ({
      ...step,
      title: t(`${prefix}.steps.${index}.title`),
      body: t(`${prefix}.steps.${index}.body`),
      note: step.note ? t(`${prefix}.steps.${index}.note`) : undefined,
    })),
    troubleshooting: lesson.troubleshooting.map((_, index) =>
      t(`${prefix}.troubleshooting.${index}`),
    ),
  }
}

export function localizePicoTrack(
  track: PicoTrack,
  t: PicoContentTranslator,
): PicoTrack {
  const prefix = `tracks.${track.slug}`

  return {
    ...track,
    title: t(`${prefix}.title`),
    outcome: t(`${prefix}.outcome`),
    intro: t(`${prefix}.intro`),
    checklist: track.checklist.map((_, index) => t(`${prefix}.checklist.${index}`)),
  }
}

export function localizePicoLevel(
  level: PicoLevel,
  t: PicoContentTranslator,
): PicoLevel {
  const prefix = `levels.${level.id}`

  return {
    ...level,
    title: t(`${prefix}.title`),
    objective: t(`${prefix}.objective`),
    projectOutcome: t(`${prefix}.projectOutcome`),
    completionState: t(`${prefix}.completionState`),
    badge: t(`${prefix}.badge`),
    recommendedNextStep: t(`${prefix}.recommendedNextStep`),
  }
}

export function localizePicoCapability(
  capability: PicoCapabilityUnlock,
  t: PicoContentTranslator,
): PicoCapabilityUnlock {
  const prefix = `capabilities.${capability.id}`

  return {
    ...capability,
    title: t(`${prefix}.title`),
    description: t(`${prefix}.description`),
    actionLabel: t(`${prefix}.actionLabel`),
  }
}
