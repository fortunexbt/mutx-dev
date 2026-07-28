import { getLessonBySlug, searchLessonCorpus, type PicoLesson } from '@/lib/pico/academy'

export type PicoTutorPlan = 'free' | 'starter' | 'pro' | 'enterprise'

export type PicoTutorEntitlement = {
  authenticated: true
  plan: PicoTutorPlan
  tutorAccess: boolean
  minimumPlan: 'starter'
  byokAccess: boolean
  byokMinimumPlan: 'pro'
}

export type PicoTutorGenerationProof = {
  provider: 'openai'
  source: 'user' | 'platform'
  model: string
  responseId: string
  completedAt: string
}

export type PicoTutorAnswer = {
  answer: string
  lessonSlug: string | null
  lessonTitle: string | null
  matches: Array<{
    slug: string
    title: string
    score: number
    reason: string
  }>
  nextActions: string[]
  escalationReason: string | null
}

export type PicoTutorCommand = {
  label: string
  code: string
  language: string
  note?: string | null
}

export type PicoTutorSource = {
  kind: 'lesson' | 'knowledge_pack' | 'official'
  title: string
  sourcePath: string
  href?: string | null
  excerpt?: string | null
}

export type PicoTutorStructuredReply = {
  situation: string
  diagnosis: string
  steps: string[]
  commands: PicoTutorCommand[]
  verify: string[]
  ifThisFails: string[]
  officialLinks: Array<{
    label: string
    href: string
    sourcePath: string
  }>
  sources: PicoTutorSource[]
  nextQuestion?: string | null
}

export type PicoTutorReply = {
  title: string
  summary: string
  answer: string
  confidence: 'high' | 'medium' | 'low'
  nextActions: string[]
  lessons: Array<{ id: string; title: string; href: string }>
  docs: Array<{ label: string; href: string; sourcePath: string }>
  recommendedLessonIds: string[]
  escalate: boolean
  escalationReason?: string
  structured: PicoTutorStructuredReply
  intent: 'choose' | 'install' | 'repair' | 'migrate' | 'compare' | 'tailscale' | 'optimize' | 'integrate'
  skillLevel: 'beginner' | 'intermediate' | 'advanced'
  usedOfficialFallback: boolean
  entitlement: PicoTutorEntitlement
  generation: PicoTutorGenerationProof
}

export type PicoTutorProviderProof = {
  kind: 'validated_user_key' | 'configured_platform_key'
  checkedAt: string
  validatedAt?: string | null
}

export type PicoTutorConnection = {
  provider: 'openai'
  status: 'connected' | 'platform' | 'disconnected' | 'error'
  source: 'user' | 'platform' | 'none'
  connected: boolean
  model: string
  maskedKey?: string | null
  connectedAt?: string | null
  validatedAt?: string | null
  message: string
  providerAvailable: boolean
  canConnect: boolean
  entitlement: PicoTutorEntitlement
  proof?: PicoTutorProviderProof | null
}

export type PicoTutorFailureKind =
  | 'unauthenticated'
  | 'plan_denied'
  | 'provider_required'
  | 'rate_limited'
  | 'model_unavailable'
  | 'malformed_response'
  | 'unknown'

export type PicoTutorFailure = {
  kind: PicoTutorFailureKind
  message: string
  retryable: boolean
}

export type PicoTutorAcademyGuidance = {
  title: string
  objective: string
  nextStep: string
  validation: string
  href: string
}

export type TutorRequestLease = {
  id: number
  signal: AbortSignal
}

export class LatestTutorRequest {
  private active: { id: number; controller: AbortController } | null = null
  private sequence = 0

  begin(): TutorRequestLease {
    this.cancel()
    const controller = new AbortController()
    const id = ++this.sequence
    this.active = { id, controller }
    return { id, signal: controller.signal }
  }

  isCurrent(lease: TutorRequestLease): boolean {
    return this.active?.id === lease.id && !lease.signal.aborted
  }

  finish(lease: TutorRequestLease): void {
    if (this.active?.id === lease.id) {
      this.active = null
    }
  }

  cancel(): void {
    this.active?.controller.abort()
    this.active = null
  }
}

const RISKY_KEYWORDS = [
  'delete',
  'production',
  'billing',
  'payment',
  'credential',
  'token',
  'secret',
  'security',
  'breach',
] as const

export function answerPicoTutorQuestion(
  question: string,
  options?: { lessonSlug?: string | null },
): PicoTutorAnswer {
  const normalizedQuestion = question.trim()
  const lowerQuestion = normalizedQuestion.toLowerCase()
  const directLesson = options?.lessonSlug ? getLessonBySlug(options.lessonSlug) : null
  const matches = searchLessonCorpus(`${options?.lessonSlug ?? ''} ${normalizedQuestion}`)
  const best = directLesson ?? matches[0]?.lesson ?? null

  const riskyTopic = RISKY_KEYWORDS.find((keyword) => lowerQuestion.includes(keyword))
  if (!best) {
    return {
      answer:
        'I cannot match that to the shipped Pico lesson corpus yet. Use support and include the exact command, error, and what you expected to happen.',
      lessonSlug: null,
      lessonTitle: null,
      matches: [],
      nextActions: [
        'Open support and paste the exact command or stack trace.',
        'State which lesson you were following.',
        'Include the last step that actually worked.',
      ],
      escalationReason: 'No lesson match found.',
    }
  }

  if (riskyTopic) {
    return {
      answer: `This question touches ${riskyTopic}, which is where Tutor should be careful. Follow the steps below, then escalate before doing anything irreversible.`,
      lessonSlug: best.slug,
      lessonTitle: best.title,
      matches: matches.map((match) => ({
        slug: match.lesson.slug,
        title: match.lesson.title,
        score: match.score,
        reason: `Matched lesson objective and troubleshooting notes for ${match.lesson.title}.`,
      })),
      nextActions: [
        best.steps[0]?.body ?? 'Re-read the first step in the matched lesson.',
        best.validation,
        'Escalate with the exact command, environment, and intended action before executing the risky part.',
      ],
      escalationReason:
        'Security or irreversible action detected. Escalate before executing the risky step.',
    }
  }

  const nextActions = best.steps.slice(0, 3).map((step) => `${step.title}: ${step.body}`)
  const troubleshooting = best.troubleshooting[0]

  return {
    answer: [
      `Best match: ${best.title}.`,
      best.objective,
      `Do this next: ${nextActions[0] ?? best.validation}`,
      troubleshooting ? `Watch for this failure mode: ${troubleshooting}` : '',
      `Validation: ${best.validation}`,
    ]
      .filter(Boolean)
      .join(' '),
    lessonSlug: best.slug,
    lessonTitle: best.title,
    matches: matches.map((match) => ({
      slug: match.lesson.slug,
      title: match.lesson.title,
      score: match.score,
      reason: `Matched lesson body, troubleshooting, and validation steps for ${match.lesson.title}.`,
    })),
    nextActions,
    escalationReason:
      matches[0]?.score && matches[0].score >= 4
        ? null
        : 'Low-confidence match. Escalate if the first next action does not fix it.',
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

function isNonEmptyString(value: unknown): value is string {
  return typeof value === 'string' && value.trim().length > 0
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === 'string')
}

function isTutorEntitlement(value: unknown): value is PicoTutorEntitlement {
  if (!isRecord(value)) return false
  const plan = value.plan
  const expectedTutorAccess = plan !== 'free'
  const expectedByokAccess = plan === 'pro' || plan === 'enterprise'
  return (
    value.authenticated === true &&
    (plan === 'free' || plan === 'starter' || plan === 'pro' || plan === 'enterprise') &&
    typeof value.tutorAccess === 'boolean' &&
    value.minimumPlan === 'starter' &&
    typeof value.byokAccess === 'boolean' &&
    value.byokMinimumPlan === 'pro' &&
    value.tutorAccess === expectedTutorAccess &&
    value.byokAccess === expectedByokAccess
  )
}

function isTutorGenerationProof(value: unknown): value is PicoTutorGenerationProof {
  return (
    isRecord(value) &&
    value.provider === 'openai' &&
    (value.source === 'user' || value.source === 'platform') &&
    isNonEmptyString(value.model) &&
    isNonEmptyString(value.responseId) &&
    isNonEmptyString(value.completedAt)
  )
}

function isTutorStructuredReply(value: unknown): value is PicoTutorStructuredReply {
  if (!isRecord(value)) return false
  return (
    isNonEmptyString(value.situation) &&
    isNonEmptyString(value.diagnosis) &&
    isStringArray(value.steps) &&
    Array.isArray(value.commands) &&
    value.commands.every(
      (command) =>
        isRecord(command) &&
        isNonEmptyString(command.label) &&
        isNonEmptyString(command.code) &&
        isNonEmptyString(command.language),
    ) &&
    isStringArray(value.verify) &&
    isStringArray(value.ifThisFails) &&
    Array.isArray(value.officialLinks) &&
    value.officialLinks.every(
      (link) =>
        isRecord(link) &&
        isNonEmptyString(link.label) &&
        isNonEmptyString(link.href) &&
        isNonEmptyString(link.sourcePath),
    ) &&
    Array.isArray(value.sources) &&
    value.sources.every(
      (source) =>
        isRecord(source) &&
        (source.kind === 'lesson' || source.kind === 'knowledge_pack' || source.kind === 'official') &&
        isNonEmptyString(source.title) &&
        isNonEmptyString(source.sourcePath),
    )
  )
}

export function normalizeTutorReplyPayload(payload: unknown): PicoTutorReply | null {
  const raw = isRecord(payload) && isRecord(payload.reply) ? payload.reply : payload
  if (!isRecord(raw)) return null

  const confidence = raw.confidence
  const intent = raw.intent
  const skillLevel = raw.skillLevel
  if (
    !isNonEmptyString(raw.title) ||
    !isNonEmptyString(raw.summary) ||
    !isNonEmptyString(raw.answer) ||
    (confidence !== 'high' && confidence !== 'medium' && confidence !== 'low') ||
    !isStringArray(raw.nextActions) ||
    !Array.isArray(raw.lessons) ||
    !raw.lessons.every(
      (lesson) =>
        isRecord(lesson) &&
        isNonEmptyString(lesson.id) &&
        isNonEmptyString(lesson.title) &&
        isNonEmptyString(lesson.href),
    ) ||
    !Array.isArray(raw.docs) ||
    !raw.docs.every(
      (doc) =>
        isRecord(doc) &&
        isNonEmptyString(doc.label) &&
        isNonEmptyString(doc.href) &&
        isNonEmptyString(doc.sourcePath),
    ) ||
    !isStringArray(raw.recommendedLessonIds) ||
    typeof raw.escalate !== 'boolean' ||
    !isTutorStructuredReply(raw.structured) ||
    !(
      intent === 'choose' ||
      intent === 'install' ||
      intent === 'repair' ||
      intent === 'migrate' ||
      intent === 'compare' ||
      intent === 'tailscale' ||
      intent === 'optimize' ||
      intent === 'integrate'
    ) ||
    (skillLevel !== 'beginner' && skillLevel !== 'intermediate' && skillLevel !== 'advanced') ||
    typeof raw.usedOfficialFallback !== 'boolean' ||
    !isTutorEntitlement(raw.entitlement) ||
    !isTutorGenerationProof(raw.generation)
  ) {
    return null
  }

  return raw as PicoTutorReply
}

export function normalizeTutorConnectionPayload(payload: unknown): PicoTutorConnection | null {
  if (!isRecord(payload) || !isTutorEntitlement(payload.entitlement)) return null
  const proof = payload.proof
  const proofIsValid =
    proof == null ||
    (isRecord(proof) &&
      (proof.kind === 'validated_user_key' || proof.kind === 'configured_platform_key') &&
      isNonEmptyString(proof.checkedAt) &&
      (proof.validatedAt == null || isNonEmptyString(proof.validatedAt)))
  if (
    payload.provider !== 'openai' ||
    !(
      payload.status === 'connected' ||
      payload.status === 'platform' ||
      payload.status === 'disconnected' ||
      payload.status === 'error'
    ) ||
    !(payload.source === 'user' || payload.source === 'platform' || payload.source === 'none') ||
    typeof payload.connected !== 'boolean' ||
    !isNonEmptyString(payload.model) ||
    !isNonEmptyString(payload.message) ||
    typeof payload.providerAvailable !== 'boolean' ||
    typeof payload.canConnect !== 'boolean' ||
    payload.canConnect !== payload.entitlement.byokAccess ||
    !proofIsValid
  ) {
    return null
  }

  if (
    payload.status === 'connected' &&
    !(
      payload.connected === true &&
      payload.source === 'user' &&
      payload.providerAvailable === true &&
      isNonEmptyString(payload.validatedAt) &&
      isRecord(proof) &&
      proof.kind === 'validated_user_key' &&
      proof.validatedAt === payload.validatedAt
    )
  ) {
    return null
  }
  if (
    payload.status === 'platform' &&
    !(
      payload.connected === false &&
      payload.source === 'platform' &&
      payload.providerAvailable === true &&
      isRecord(proof) &&
      proof.kind === 'configured_platform_key'
    )
  ) {
    return null
  }
  if (
    (payload.status === 'disconnected' || payload.status === 'error') &&
    (payload.connected || payload.providerAvailable || payload.source !== 'none')
  ) {
    return null
  }

  return payload as PicoTutorConnection
}

export function getPicoTutorPlanCapabilities(plan: string | null | undefined) {
  const normalized = plan?.trim().toLowerCase()
  const level = normalized === 'enterprise' ? 3 : normalized === 'pro' ? 2 : normalized === 'starter' ? 1 : 0
  return {
    tutorAccess: level >= 1,
    byokAccess: level >= 2,
  }
}

function readFailureMessage(payload: unknown): string | null {
  if (!isRecord(payload)) return null
  if (typeof payload.detail === 'string' && payload.detail) return payload.detail
  if (isRecord(payload.detail) && typeof payload.detail.message === 'string') {
    return payload.detail.message
  }
  if (typeof payload.error === 'string' && payload.error) return payload.error
  if (isRecord(payload.error) && typeof payload.error.message === 'string') {
    return payload.error.message
  }
  return null
}

export function classifyTutorFailure(statusCode: number, payload: unknown): PicoTutorFailure {
  const message = readFailureMessage(payload)
  if (statusCode === 401) {
    return { kind: 'unauthenticated', message: message ?? 'Sign in to use live Tutor.', retryable: false }
  }
  if (statusCode === 402 || statusCode === 403) {
    return {
      kind: 'plan_denied',
      message: message ?? 'Your current plan does not include this Tutor capability.',
      retryable: false,
    }
  }
  if (statusCode === 409 || statusCode === 424) {
    return {
      kind: 'provider_required',
      message: message ?? 'No validated model provider is available for live Tutor.',
      retryable: false,
    }
  }
  if (statusCode === 429) {
    return {
      kind: 'rate_limited',
      message: message ?? 'Tutor is rate limited. Wait a moment and try again.',
      retryable: true,
    }
  }
  if (statusCode >= 500) {
    return {
      kind: 'model_unavailable',
      message: message ?? 'Tutor could not complete this request. Try again shortly.',
      retryable: true,
    }
  }
  return { kind: 'unknown', message: message ?? 'Tutor request failed.', retryable: false }
}

export function getPicoTutorAcademyGuidance(
  lesson: PicoLesson | null,
  activeStepIndex = 0,
): PicoTutorAcademyGuidance | null {
  if (!lesson) return null
  const safeIndex = Math.max(0, Math.min(activeStepIndex, lesson.steps.length - 1))
  const step = lesson.steps[safeIndex]
  return {
    title: lesson.title,
    objective: lesson.objective,
    nextStep: step ? `${step.title}: ${step.body}` : lesson.expectedResult,
    validation: lesson.validation,
    href: `/academy/${lesson.slug}`,
  }
}
