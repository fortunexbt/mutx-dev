import { type PicoLesson } from '@/lib/pico/academy'

export function getPicoTutorPromptChips(
  selectedLesson: PicoLesson | null,
  fallbackPrompts: readonly string[],
  tutorAvailable = true,
) {
  if (!tutorAvailable || selectedLesson) {
    return []
  }

  return [...fallbackPrompts]
}
