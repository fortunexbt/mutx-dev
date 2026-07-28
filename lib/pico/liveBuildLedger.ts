import builderManifest from '@/src/api/knowledge/pico_ops/manifest.json'

import { PICO_LESSONS, PICO_TRACKS } from '@/lib/pico/academy'
import { PICO_GENERATED_CONTENT } from '@/lib/pico/generatedContent'

const visiblePackDocs = builderManifest.docs.filter((document) => document.visible)

export const PICO_LIVE_BUILD_LEDGER = {
  generatedAt: PICO_GENERATED_CONTENT.generatedAt,
  refreshedAt: PICO_GENERATED_CONTENT.generatedAt,
  packDocs: visiblePackDocs.map((document) => ({
    id: document.id,
    filename: document.filename,
    topics: document.topics,
  })),
  academy: {
    totalMinutes: PICO_LESSONS.reduce((total, lesson) => total + lesson.estimatedMinutes, 0),
    lessons: PICO_LESSONS.map((lesson) => ({
      slug: lesson.slug,
      title: lesson.title,
      summary: lesson.summary,
      track: lesson.track,
      difficulty: lesson.difficulty,
      estimatedMinutes: lesson.estimatedMinutes,
    })),
    tracks: PICO_TRACKS.map((track) => ({
      slug: track.slug,
      title: track.title,
      outcome: track.outcome,
      lessonCount: track.lessons.length,
    })),
  },
  stacks: PICO_GENERATED_CONTENT.stacks.map((stack) => ({
    id: stack.id,
    name: stack.name,
    productProfile: stack.productProfile,
    installReality: stack.installRealities[0],
    strength: stack.strengths[0],
    repoUrl: stack.repoUrl,
    docsUrl: stack.docsUrl,
    live: stack.live,
  })),
  remoteAccess: PICO_GENERATED_CONTENT.remoteAccess,
} as const

export function validatePicoLiveBuildLedger() {
  return {
    packDocsMatchGeneratedCount:
      PICO_LIVE_BUILD_LEDGER.packDocs.length ===
      PICO_GENERATED_CONTENT.packSnapshot.visibleDocCount,
    lessonsMatchGeneratedCount:
      PICO_LIVE_BUILD_LEDGER.academy.lessons.length ===
      PICO_GENERATED_CONTENT.packSnapshot.lessonCount,
    minutesMatchGeneratedCount:
      PICO_LIVE_BUILD_LEDGER.academy.totalMinutes ===
      PICO_GENERATED_CONTENT.packSnapshot.totalLessonMinutes,
  }
}
