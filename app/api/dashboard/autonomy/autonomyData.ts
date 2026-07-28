import { constants as fsConstants, promises as fs } from 'node:fs'
import path from 'node:path'

const MAX_SOURCE_BYTES = 2 * 1024 * 1024
const MAX_REPORTS = 20
const DEFAULT_STALE_AFTER_SECONDS = 20 * 60

type DataErrorCode =
  | 'invalid_root'
  | 'root_not_found'
  | 'data_not_found'
  | 'unsafe_path'
  | 'source_unavailable'
  | 'malformed_source'

export class AutonomyDataError extends Error {
  code: DataErrorCode

  constructor(code: DataErrorCode) {
    super(code)
    this.name = 'AutonomyDataError'
    this.code = code
  }
}

export type AutonomyQueueItem = {
  id?: string
  title?: string
  status?: string
  lane?: string
  runner?: string
  area?: string
  priority?: string
}

export type AutonomyDashboardPayload = {
  status: 'ok'
  scope: 'local-only'
  availability: 'complete' | 'partial'
  generatedAt: string
  freshness: {
    state: 'fresh' | 'stale' | 'unknown'
    heartbeatAt: string | null
    ageSeconds: number | null
    staleAfterSeconds: number
  }
  sources: {
    available: number
    missing: number
  }
  daemon: {
    reportedStatus: string
    live: boolean
    cycleCount: number | null
    lastCycleCompletedAt: string | null
    lastResultStatus: string | null
  }
  lanes: Array<{
    name: string
    paused: boolean
    reason: string | null
    updatedAt: string | null
  }>
  fleet: {
    roles: Array<{ id: string; lane: string; purpose: string }>
  }
  generatedTasks: Array<{
    id?: string
    title?: string
    area?: string
    priority?: string
    ownerRole?: string
    lane?: string
  }>
  queue: {
    counts: {
      queued: number
      running: number
      parked: number
      completed: number
      other: number
    }
    queued: AutonomyQueueItem[]
    running: AutonomyQueueItem[]
    parked: AutonomyQueueItem[]
    completed: AutonomyQueueItem[]
  }
  activeRunners: Array<{
    taskId?: string
    lane?: string
    runner?: string
    startedAt: string | null
  }>
  reports: Array<{
    taskId?: string
    lane?: string
    status?: string
    summary?: string
    updatedAt: string | null
  }>
}

type SourceResult<T> = {
  available: boolean
  value: T
}

type DaemonSource = {
  daemon: Omit<AutonomyDashboardPayload['daemon'], 'live'>
  activeRunners: AutonomyDashboardPayload['activeRunners']
  heartbeatAt: string | null
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

function isMissingFileError(error: unknown) {
  return isRecord(error) && error.code === 'ENOENT'
}

function isWithinRoot(root: string, candidate: string) {
  const relative = path.relative(root, candidate)
  return relative === '' || (!relative.startsWith(`..${path.sep}`) && relative !== '..' && !path.isAbsolute(relative))
}

function escapeRegExp(value: string) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

function redactAbsolutePaths(value: string, root: string) {
  const rootRedacted = value.replace(new RegExp(escapeRegExp(root), 'g'), '[redacted]')
  const windowsRedacted = rootRedacted.replace(
    /(^|[^A-Za-z0-9\\])(?:[A-Za-z]:\\)(?:[^\\\s"'<>()[\]{},;]+\\)*[^\\\s"'<>()[\]{},;]*/g,
    '$1[redacted]',
  )

  return windowsRedacted.replace(
    /(^|[^A-Za-z0-9/])\/(?!\/)(?:[^/\s"'<>()[\]{},;]+(?:\/[^/\s"'<>()[\]{},;]+)*)/g,
    '$1[redacted]',
  )
}

function safeText(value: unknown, root: string, maxLength = 200) {
  if (typeof value !== 'string') return undefined

  const normalized = redactAbsolutePaths(value, root).replace(/[\r\n\t]+/g, ' ').trim()
  return normalized.length > 0 ? normalized.slice(0, maxLength) : undefined
}

function safeDate(value: unknown) {
  if (typeof value !== 'string') return null
  const timestamp = Date.parse(value)
  return Number.isFinite(timestamp) ? new Date(timestamp).toISOString() : null
}

function safeCount(value: unknown) {
  return typeof value === 'number' && Number.isSafeInteger(value) && value >= 0 ? value : null
}

function malformed(): never {
  throw new AutonomyDataError('malformed_source')
}

export async function resolveAutonomyRoot(configuredRoot: string) {
  if (!path.isAbsolute(configuredRoot)) {
    throw new AutonomyDataError('invalid_root')
  }

  let resolvedRoot: string
  try {
    resolvedRoot = await fs.realpath(configuredRoot)
  } catch (error) {
    if (isMissingFileError(error)) {
      throw new AutonomyDataError('root_not_found')
    }
    throw new AutonomyDataError('source_unavailable')
  }

  if (resolvedRoot === path.parse(resolvedRoot).root) {
    throw new AutonomyDataError('invalid_root')
  }

  try {
    const rootStat = await fs.stat(resolvedRoot)
    if (!rootStat.isDirectory()) {
      throw new AutonomyDataError('root_not_found')
    }
  } catch (error) {
    if (error instanceof AutonomyDataError) throw error
    if (isMissingFileError(error)) {
      throw new AutonomyDataError('root_not_found')
    }
    throw new AutonomyDataError('source_unavailable')
  }

  return resolvedRoot
}

export async function resolveAutonomyReadPath(resolvedRoot: string, relativePath: string) {
  if (
    !path.isAbsolute(resolvedRoot) ||
    path.isAbsolute(relativePath) ||
    relativePath.split(/[\\/]/).some((part) => part === '..')
  ) {
    throw new AutonomyDataError('unsafe_path')
  }

  const candidate = path.resolve(resolvedRoot, relativePath)
  if (!isWithinRoot(resolvedRoot, candidate)) {
    throw new AutonomyDataError('unsafe_path')
  }

  try {
    await fs.lstat(candidate)
  } catch (error) {
    if (isMissingFileError(error)) return null
    throw new AutonomyDataError('source_unavailable')
  }

  let canonicalPath: string
  try {
    canonicalPath = await fs.realpath(candidate)
  } catch {
    throw new AutonomyDataError('source_unavailable')
  }

  if (!isWithinRoot(resolvedRoot, canonicalPath)) {
    throw new AutonomyDataError('unsafe_path')
  }

  try {
    const sourceStat = await fs.stat(canonicalPath)
    if (!sourceStat.isFile()) {
      throw new AutonomyDataError('source_unavailable')
    }
  } catch (error) {
    if (error instanceof AutonomyDataError) throw error
    throw new AutonomyDataError('source_unavailable')
  }

  return canonicalPath
}

async function readSourceText(resolvedRoot: string, relativePath: string) {
  const canonicalPath = await resolveAutonomyReadPath(resolvedRoot, relativePath)
  if (!canonicalPath) return null

  let handle: Awaited<ReturnType<typeof fs.open>> | null = null
  try {
    handle = await fs.open(canonicalPath, fsConstants.O_RDONLY | fsConstants.O_NOFOLLOW)
    const sourceStat = await handle.stat()
    if (!sourceStat.isFile() || sourceStat.size > MAX_SOURCE_BYTES) {
      throw new AutonomyDataError('source_unavailable')
    }
    return await handle.readFile({ encoding: 'utf8' })
  } catch (error) {
    if (error instanceof AutonomyDataError) throw error
    throw new AutonomyDataError('source_unavailable')
  } finally {
    await handle?.close().catch(() => undefined)
  }
}

async function readJsonSource<T>(
  resolvedRoot: string,
  relativePath: string,
  fallback: T,
  parser: (value: unknown, root: string) => T,
): Promise<SourceResult<T>> {
  const raw = await readSourceText(resolvedRoot, relativePath)
  if (raw === null) return { available: false, value: fallback }

  try {
    return { available: true, value: parser(JSON.parse(raw), resolvedRoot) }
  } catch (error) {
    if (error instanceof AutonomyDataError) throw error
    throw new AutonomyDataError('malformed_source')
  }
}

function parseDaemon(value: unknown, root: string): DaemonSource {
  if (!isRecord(value)) malformed()

  const lastResult = value.last_result
  if (lastResult !== undefined && lastResult !== null && !isRecord(lastResult)) malformed()

  const rawRunners = value.active_runners ?? []
  if (!Array.isArray(rawRunners) || !rawRunners.every(isRecord)) malformed()

  return {
    daemon: {
      reportedStatus: safeText(value.status, root, 48) ?? 'unknown',
      cycleCount: safeCount(value.cycle_count),
      lastCycleCompletedAt: safeDate(value.last_cycle_completed_at),
      lastResultStatus: isRecord(lastResult) ? (safeText(lastResult.status, root, 48) ?? null) : null,
    },
    activeRunners: rawRunners.slice(0, 100).map((runner) => ({
      taskId: safeText(runner.task_id, root, 120),
      lane: safeText(runner.lane, root, 80),
      runner: safeText(runner.runner, root, 80),
      startedAt: safeDate(runner.started_at),
    })),
    heartbeatAt: safeDate(value.heartbeat_at),
  }
}

function parseLanes(value: unknown, root: string): AutonomyDashboardPayload['lanes'] {
  if (!isRecord(value)) malformed()
  const lanes = value.lanes ?? {}
  if (!isRecord(lanes) || !Object.values(lanes).every(isRecord)) malformed()

  return Object.entries(lanes).slice(0, 100).map(([name, state]) => {
    const laneState = state as Record<string, unknown>
    return {
      name: safeText(name, root, 80) ?? 'unnamed lane',
      paused: laneState.paused === true,
      reason: safeText(laneState.reason, root, 240) ?? null,
      updatedAt: safeDate(laneState.updated_at),
    }
  })
}

function parseFleet(value: unknown, root: string): AutonomyDashboardPayload['fleet'] {
  if (!isRecord(value)) malformed()
  const roles = value.roles ?? []
  if (!Array.isArray(roles) || !roles.every(isRecord)) malformed()

  return {
    roles: roles.slice(0, 250).map((role) => {
      const id = safeText(role.id, root, 100)
      if (!id) malformed()

      return {
        id,
        lane: safeText(role.lane, root, 80) ?? 'unassigned',
        purpose: safeText(role.purpose, root, 240) ?? 'No purpose reported',
      }
    }),
  }
}

function parseGeneratedTasks(value: unknown, root: string): AutonomyDashboardPayload['generatedTasks'] {
  if (!Array.isArray(value) || !value.every(isRecord)) malformed()

  return value.slice(0, 100).map((task) => ({
    id: safeText(task.id, root, 120),
    title: safeText(task.title, root, 240),
    area: safeText(task.area, root, 100),
    priority: safeText(task.priority, root, 48),
    ownerRole: safeText(task.owner_role, root, 100),
    lane: safeText(task.lane, root, 80),
  }))
}

function parseQueueItem(item: Record<string, unknown>, root: string): AutonomyQueueItem {
  return {
    id: safeText(item.id, root, 120),
    title: safeText(item.title, root, 240),
    status: safeText(item.status, root, 48)?.toLowerCase(),
    lane: safeText(item.lane, root, 80),
    runner: safeText(item.runner, root, 80),
    area: safeText(item.area, root, 100),
    priority: safeText(item.priority, root, 48),
  }
}

function emptyQueue(): AutonomyDashboardPayload['queue'] {
  return {
    counts: { queued: 0, running: 0, parked: 0, completed: 0, other: 0 },
    queued: [],
    running: [],
    parked: [],
    completed: [],
  }
}

function parseQueue(value: unknown, root: string): AutonomyDashboardPayload['queue'] {
  if (!isRecord(value)) malformed()
  const rawItems = value.items ?? []
  if (!Array.isArray(rawItems) || !rawItems.every(isRecord)) malformed()

  const items = rawItems.map((item) => parseQueueItem(item, root))
  const queue = emptyQueue()

  for (const item of items) {
    if (item.status === 'queued') queue.counts.queued += 1
    else if (item.status === 'running') queue.counts.running += 1
    else if (item.status === 'parked') queue.counts.parked += 1
    else if (item.status === 'completed') queue.counts.completed += 1
    else queue.counts.other += 1
  }

  queue.queued = items.filter((item) => item.status === 'queued').slice(0, 20)
  queue.running = items.filter((item) => item.status === 'running').slice(0, 20)
  queue.parked = items.filter((item) => item.status === 'parked').slice(0, 20)
  queue.completed = items.filter((item) => item.status === 'completed').slice(0, 10)
  return queue
}

async function readReports(resolvedRoot: string): Promise<SourceResult<AutonomyDashboardPayload['reports']>> {
  const raw = await readSourceText(resolvedRoot, 'reports/autonomy-status.jsonl')
  if (raw === null) return { available: false, value: [] }

  const lines = raw.split('\n').filter((line) => line.trim().length > 0).slice(-MAX_REPORTS)
  const reports = lines.map((line) => {
    let value: unknown
    try {
      value = JSON.parse(line)
    } catch {
      malformed()
    }
    if (!isRecord(value)) malformed()

    return {
      taskId: safeText(value.task_id, resolvedRoot, 120),
      lane: safeText(value.lane, resolvedRoot, 80),
      status: safeText(value.status, resolvedRoot, 48),
      summary: safeText(value.summary, resolvedRoot, 320),
      updatedAt: safeDate(value.updated_at),
    }
  })

  return { available: true, value: reports }
}

function staleAfterSeconds(value: string | undefined) {
  if (!value) return DEFAULT_STALE_AFTER_SECONDS
  const parsed = Number(value)
  if (!Number.isFinite(parsed)) return DEFAULT_STALE_AFTER_SECONDS
  return Math.min(Math.max(Math.trunc(parsed), 30), 24 * 60 * 60)
}

function freshnessFor(
  heartbeatAt: string | null,
  reportedStatus: string,
  nowMs: number,
  thresholdSeconds: number,
) {
  if (!heartbeatAt) {
    return {
      freshness: {
        state: 'unknown' as const,
        heartbeatAt: null,
        ageSeconds: null,
        staleAfterSeconds: thresholdSeconds,
      },
      live: false,
    }
  }

  const ageMs = nowMs - Date.parse(heartbeatAt)
  if (!Number.isFinite(ageMs) || ageMs < -60_000) {
    return {
      freshness: {
        state: 'unknown' as const,
        heartbeatAt,
        ageSeconds: null,
        staleAfterSeconds: thresholdSeconds,
      },
      live: false,
    }
  }

  const ageSeconds = Math.max(0, Math.floor(ageMs / 1000))
  const state = ageSeconds <= thresholdSeconds ? ('fresh' as const) : ('stale' as const)
  const liveStatuses = new Set(['active', 'healthy', 'idle', 'running'])

  return {
    freshness: {
      state,
      heartbeatAt,
      ageSeconds,
      staleAfterSeconds: thresholdSeconds,
    },
    live: state === 'fresh' && liveStatuses.has(reportedStatus.toLowerCase()),
  }
}

export async function loadAutonomySnapshot(
  configuredRoot: string,
  options: { nowMs?: number; staleAfterSeconds?: string } = {},
): Promise<AutonomyDashboardPayload> {
  const resolvedRoot = await resolveAutonomyRoot(configuredRoot)
  const emptyDaemon: DaemonSource = {
    daemon: {
      reportedStatus: 'unknown',
      cycleCount: null,
      lastCycleCompletedAt: null,
      lastResultStatus: null,
    },
    activeRunners: [],
    heartbeatAt: null,
  }

  const [daemon, lanes, fleet, generatedTasks, queue, reports] = await Promise.all([
    readJsonSource(resolvedRoot, '.autonomy/daemon-status.json', emptyDaemon, parseDaemon),
    readJsonSource(resolvedRoot, '.autonomy/lane-state.json', [], parseLanes),
    readJsonSource(resolvedRoot, '.autonomy/fleet.json', { roles: [] }, parseFleet),
    readJsonSource(resolvedRoot, '.autonomy/generated-tasks.json', [], parseGeneratedTasks),
    readJsonSource(resolvedRoot, 'mutx-engineering-agents/dispatch/action-queue.json', emptyQueue(), parseQueue),
    readReports(resolvedRoot),
  ])

  const sourceResults = [daemon, lanes, fleet, generatedTasks, queue, reports]
  const availableSources = sourceResults.filter((source) => source.available).length
  if (availableSources === 0) {
    throw new AutonomyDataError('data_not_found')
  }

  const nowMs = options.nowMs ?? Date.now()
  const thresholdSeconds = staleAfterSeconds(options.staleAfterSeconds)
  const { freshness, live } = freshnessFor(
    daemon.value.heartbeatAt,
    daemon.value.daemon.reportedStatus,
    nowMs,
    thresholdSeconds,
  )

  return {
    status: 'ok',
    scope: 'local-only',
    availability: availableSources === sourceResults.length ? 'complete' : 'partial',
    generatedAt: new Date(nowMs).toISOString(),
    freshness,
    sources: {
      available: availableSources,
      missing: sourceResults.length - availableSources,
    },
    daemon: {
      ...daemon.value.daemon,
      live,
    },
    lanes: lanes.value,
    fleet: fleet.value,
    generatedTasks: generatedTasks.value,
    queue: queue.value,
    activeRunners: daemon.value.activeRunners,
    reports: reports.value,
  }
}
