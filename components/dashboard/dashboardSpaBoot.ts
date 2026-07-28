export type BootStatus = 'pending' | 'running' | 'complete' | 'warning' | 'error'

export type BootStepKey =
  | 'auth'
  | 'capabilities'
  | 'config'
  | 'connect'
  | 'agents'
  | 'sessions'
  | 'projects'
  | 'memory'
  | 'skills'

export type BootStep = {
  key: BootStepKey
  label: string
  detail: string
  status: BootStatus
}

export type BootOutcome = {
  phase: 'running' | 'ready' | 'degraded'
  settled: number
  complete: number
  warnings: number
  errors: number
  fullyReady: boolean
}

export type ControlPlaneEvidence = {
  latency: number
  status: 'healthy'
  database: 'ready'
  version: string | null
}

export type MemoryWarmupEvidence = {
  status: 'complete' | 'warning'
  detail: string
  issues: string[]
}

type Fetcher = (input: string | URL | Request, init?: RequestInit) => Promise<Response>

export const DASHBOARD_HEALTH_ROUTE = '/api/dashboard/health'
export const DASHBOARD_MEMORY_ROUTE = '/api/dashboard/memory'

const BOOT_STEP_DEFINITIONS: Array<Omit<BootStep, 'status'>> = [
  { key: 'auth', label: 'Operator', detail: 'Verify the active operator session.' },
  {
    key: 'capabilities',
    label: 'Runtime',
    detail: 'Identify the active browser or desktop runtime.',
  },
  {
    key: 'config',
    label: 'Workspace',
    detail: 'Load workspace access and interface preferences.',
  },
  {
    key: 'connect',
    label: 'Control plane',
    detail: 'Request live control-plane health evidence.',
  },
  { key: 'agents', label: 'Agents', detail: 'Read the current fleet registry.' },
  { key: 'sessions', label: 'Sessions', detail: 'Read active session presence.' },
  { key: 'projects', label: 'Templates', detail: 'Read deployable workspace templates.' },
  { key: 'memory', label: 'Memory', detail: 'Read the live memory inventory.' },
  { key: 'skills', label: 'Skills', detail: 'Read the available skill catalog.' },
]

export function createInitialBootSteps(): BootStep[] {
  return BOOT_STEP_DEFINITIONS.map((step) => ({ ...step, status: 'pending' }))
}

export function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

function extractErrorMessage(payload: unknown, fallback: string): string {
  if (!isRecord(payload)) return fallback

  for (const key of ['detail', 'error', 'message']) {
    const value = payload[key]
    if (typeof value === 'string' && value.trim()) return value.trim()
  }

  return fallback
}

export async function readDashboardJson(
  url: string,
  fallbackMessage: string,
  fetcher: Fetcher = fetch,
): Promise<unknown> {
  const response = await fetcher(url, { cache: 'no-store' })
  const payload = await response.json().catch(() => null)

  if (!response.ok) {
    throw new Error(extractErrorMessage(payload, fallbackMessage))
  }

  if (payload === null) {
    throw new Error(fallbackMessage)
  }

  return payload
}

export function extractCollection(payload: unknown, keys: string[]): unknown[] {
  if (Array.isArray(payload)) return payload
  if (!isRecord(payload)) {
    throw new Error('The control plane returned an invalid collection.')
  }

  for (const key of keys) {
    if (Array.isArray(payload[key])) return payload[key]
  }

  throw new Error('The control plane response did not include the expected collection.')
}

export async function probeControlPlane(
  fetcher: Fetcher = fetch,
  now: () => number = Date.now,
): Promise<ControlPlaneEvidence> {
  const startedAt = now()
  const payload = await readDashboardJson(
    DASHBOARD_HEALTH_ROUTE,
    'Control-plane health could not be verified.',
    fetcher,
  )

  if (!isRecord(payload)) {
    throw new Error('Control-plane health returned an invalid response.')
  }

  if (payload.status !== 'healthy' || payload.database !== 'ready') {
    const reason = extractErrorMessage(payload, 'Control plane reported a degraded state.')
    throw new Error(reason)
  }

  return {
    latency: Math.max(0, Math.round(now() - startedAt)),
    status: 'healthy',
    database: 'ready',
    version: typeof payload.version === 'string' ? payload.version : null,
  }
}

function pluralize(value: number, singular: string, plural = `${singular}s`) {
  return `${value} ${value === 1 ? singular : plural}`
}

export async function loadMemoryWarmup(fetcher: Fetcher = fetch): Promise<MemoryWarmupEvidence> {
  const payload = await readDashboardJson(
    DASHBOARD_MEMORY_ROUTE,
    'Memory inventory could not be read.',
    fetcher,
  )

  if (!isRecord(payload) || !isRecord(payload.summary) || typeof payload.generatedAt !== 'string') {
    throw new Error('Memory inventory returned an invalid response.')
  }

  const sessionCount =
    typeof payload.summary.sessions === 'number' && Number.isFinite(payload.summary.sessions)
      ? Math.max(0, Math.trunc(payload.summary.sessions))
      : 0
  const documentArtifacts =
    typeof payload.summary.documentArtifacts === 'number' &&
    Number.isFinite(payload.summary.documentArtifacts)
      ? Math.max(0, Math.trunc(payload.summary.documentArtifacts))
      : 0
  const reasoningArtifacts =
    typeof payload.summary.reasoningArtifacts === 'number' &&
    Number.isFinite(payload.summary.reasoningArtifacts)
      ? Math.max(0, Math.trunc(payload.summary.reasoningArtifacts))
      : 0
  const issues = Array.isArray(payload.partials)
    ? payload.partials.filter(
        (item): item is string =>
          typeof item === 'string' &&
          item.trim().length > 0 &&
          !item.toLowerCase().startsWith('memory inventory is read-only'),
      )
    : []
  const artifactCount = documentArtifacts + reasoningArtifacts
  const detail = `${pluralize(sessionCount, 'session')} and ${pluralize(
    artifactCount,
    'artifact',
  )} indexed${issues.length ? `; ${pluralize(issues.length, 'source')} unavailable` : ''}.`

  return {
    status: issues.length ? 'warning' : 'complete',
    detail,
    issues,
  }
}

export function summarizeBoot(steps: BootStep[]): BootOutcome {
  const complete = steps.filter((step) => step.status === 'complete').length
  const warnings = steps.filter((step) => step.status === 'warning').length
  const errors = steps.filter((step) => step.status === 'error').length
  const settled = complete + warnings + errors
  const running = steps.some((step) => step.status === 'pending' || step.status === 'running')
  const fullyReady = !running && warnings === 0 && errors === 0

  return {
    phase: running ? 'running' : fullyReady ? 'ready' : 'degraded',
    settled,
    complete,
    warnings,
    errors,
    fullyReady,
  }
}
