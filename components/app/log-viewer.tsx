'use client'

import { useState, useEffect, useCallback, useRef } from 'react'
import { type components } from '@/app/types/api'
import { extractApiErrorMessage, normalizeCollection } from '@/components/app/http'
import { EmptyState } from '@/components/dashboard/EmptyState'
import { cn } from '@/lib/utils'

type LogEntry = components['schemas']['DeploymentLogsResponse']
type Deployment = components['schemas']['DeploymentResponse']
type DeploymentLogsHistoryResponse = components['schemas']['DeploymentLogsHistoryResponse']

interface LogFilters {
  level?: string
  search?: string
  deploymentId?: string
}

const MAX_LOG_BUFFER = 500

export function parseDeploymentLogs(payload: unknown): LogEntry[] {
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
    throw new Error('Invalid deployment logs response')
  }

  const { items } = payload as DeploymentLogsHistoryResponse
  if (!Array.isArray(items)) {
    throw new Error('Invalid deployment logs response')
  }

  return items
}

export async function fetchDeploymentLogs(
  deploymentId: string,
  level = '',
  request: typeof fetch = fetch,
): Promise<LogEntry[]> {
  const params = new URLSearchParams({ limit: '200' })
  if (level) params.set('level', level)

  const response = await request(
    `/api/deployments/${encodeURIComponent(deploymentId)}/logs?${params}`,
    { cache: 'no-store' },
  )
  const payload: unknown = await response.json().catch(() => ({}))

  if (!response.ok) {
    throw new Error(extractApiErrorMessage(payload, 'Failed to fetch logs'))
  }

  return parseDeploymentLogs(payload)
}

function downloadFile(content: string, filename: string, mime: string) {
  const blob = new Blob([content], { type: mime })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

function getLogLevelColor(level: string) {
  switch (level.toLowerCase()) {
    case 'error': return 'text-red-400'
    case 'warn': return 'text-amber-400'
    case 'info': return 'text-blue-400'
    case 'debug': return 'text-slate-500'
    default: return 'text-slate-300'
  }
}

function getLogLevelBg(level: string) {
  switch (level.toLowerCase()) {
    case 'error': return 'bg-red-500/10 border-red-500/20'
    case 'warn': return 'bg-amber-500/10 border-amber-500/20'
    case 'info': return 'bg-blue-500/10 border-blue-500/20'
    case 'debug': return 'bg-slate-500/10 border-slate-500/20'
    default: return 'bg-white/5 border-white/10'
  }
}

interface LogViewerProps {
  className?: string
  deploymentId?: string
}

export function LogViewer({ className, deploymentId }: LogViewerProps) {
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [deployments, setDeployments] = useState<Deployment[]>([])
  const [filters, setFilters] = useState<LogFilters>({
    level: '',
    search: '',
    deploymentId: deploymentId || '',
  })
  const [isAutoScroll, setIsAutoScroll] = useState(true)
  const [isDeploymentsLoading, setIsDeploymentsLoading] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [logsError, setLogsError] = useState<string | null>(null)
  const [deploymentsError, setDeploymentsError] = useState<string | null>(null)
  const logContainerRef = useRef<HTMLDivElement>(null)
  const loadedDeploymentIdRef = useRef<string | null>(null)
  const requestSequenceRef = useRef(0)
  const selectedDeploymentId = filters.deploymentId || deployments[0]?.id

  const fetchDeployments = useCallback(async () => {
    setIsDeploymentsLoading(true)
    try {
      setDeploymentsError(null)
      const res = await fetch('/api/dashboard/deployments')
      const data: unknown = await res.json().catch(() => ({}))
      if (!res.ok) {
        throw new Error(extractApiErrorMessage(data, 'Failed to fetch deployments'))
      }
      const deps = normalizeCollection<Deployment>(data, ['items', 'deployments', 'data'])
      setDeployments(deps)
    } catch (err) {
      setDeploymentsError(err instanceof Error ? err.message : 'Failed to fetch deployments')
    } finally {
      setIsDeploymentsLoading(false)
    }
  }, [])

  const fetchLogs = useCallback(async () => {
    const requestSequence = ++requestSequenceRef.current
    setIsLoading(true)
    try {
      setLogsError(null)
      if (!selectedDeploymentId) {
        loadedDeploymentIdRef.current = null
        setLogs([])
        return
      }

      if (loadedDeploymentIdRef.current !== selectedDeploymentId) {
        setLogs([])
      }

      const entries = await fetchDeploymentLogs(selectedDeploymentId, filters.level)
      if (requestSequence !== requestSequenceRef.current) return

      loadedDeploymentIdRef.current = selectedDeploymentId
      setLogs(entries.slice(0, MAX_LOG_BUFFER))
    } catch (err) {
      if (requestSequence !== requestSequenceRef.current) return

      setLogsError(err instanceof Error ? err.message : 'Failed to load logs')
    } finally {
      if (requestSequence === requestSequenceRef.current) {
        setIsLoading(false)
      }
    }
  }, [filters.level, selectedDeploymentId])

  useEffect(() => {
    fetchDeployments()
  }, [fetchDeployments])

  useEffect(() => {
    fetchLogs()
    return () => {
      requestSequenceRef.current += 1
    }
  }, [fetchLogs])

  useEffect(() => {
    if (!isAutoScroll) return
    const interval = setInterval(fetchLogs, 15000)
    return () => clearInterval(interval)
  }, [isAutoScroll, fetchLogs])

  useEffect(() => {
    if (isAutoScroll && logContainerRef.current) {
      logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight
    }
  }, [logs, isAutoScroll])

  const handleFilterChange = (key: keyof LogFilters, value: string) => {
    setFilters(prev => ({ ...prev, [key]: value }))
  }

  const handleScrollToBottom = () => {
    if (logContainerRef.current) {
      logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight
    }
  }

  const handleExportText = () => {
    const lines = filteredLogs.map(entry => {
      const ts = new Date(entry.timestamp).toISOString()
      return `[${ts}] [${entry.level.toUpperCase()}] [agent:${entry.agent_id}] ${entry.message}`
    })
    const filename = `mutx-logs-${new Date().toISOString().slice(0, 19).replace(/:/g, '-')}.log`
    downloadFile(lines.join('\n'), filename, 'text/plain')
  }

  const handleExportJson = () => {
    const filename = `mutx-logs-${new Date().toISOString().slice(0, 19).replace(/:/g, '-')}.json`
    downloadFile(JSON.stringify(filteredLogs, null, 2), filename, 'application/json')
  }

  const handleClear = () => {
    setLogs([])
  }

  const filteredLogs = logs.filter(entry => {
    if (filters.level && entry.level !== filters.level) return false
    if (filters.search) {
      const query = filters.search.toLowerCase()
      if (
        !entry.message.toLowerCase().includes(query) &&
        !entry.extra_data?.toLowerCase().includes(query)
      ) return false
    }
    return true
  })

  return (
    <div className={cn('flex flex-col h-full', className)}>
      <div className="p-4 border-b border-white/10">
        <div className="flex items-center justify-between mb-3">
          <div>
            <h2 className="text-lg font-semibold text-white">Log Viewer</h2>
            <p className="text-xs text-slate-500 mt-0.5">Real-time deployment logs</p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setIsAutoScroll(!isAutoScroll)}
              className={cn(
                'px-2.5 py-1 rounded text-xs font-medium border transition-colors',
                isAutoScroll
                  ? 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30'
                  : 'bg-white/5 text-slate-400 border-white/10 hover:text-white'
              )}
            >
              {isAutoScroll ? 'Auto-scroll On' : 'Auto-scroll Off'}
            </button>
            <button
              onClick={handleScrollToBottom}
              className="px-2.5 py-1 rounded text-xs font-medium border border-white/10 bg-white/[0.02] text-slate-400 hover:text-white hover:border-white/20 transition-colors"
            >
              Bottom
            </button>
            <button
              onClick={fetchLogs}
              className="px-2.5 py-1 rounded text-xs font-medium border border-white/10 bg-white/[0.02] text-slate-400 hover:text-white hover:border-white/20 transition-colors"
            >
              Refresh
            </button>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
          <div>
            <label className="block text-2xs text-slate-500 mb-1">Deployment</label>
            <select
              value={filters.deploymentId || ''}
              onChange={e => handleFilterChange('deploymentId', e.target.value)}
              className="w-full px-2.5 py-1.5 bg-black/30 text-slate-300 text-xs rounded border border-white/10 focus:outline-none focus:border-cyan-400/50"
            >
              <option value="">Latest deployment</option>
              {deploymentId && !deployments.some(dep => dep.id === deploymentId) ? (
                <option value={deploymentId}>Deployment {deploymentId.slice(0, 8)}</option>
              ) : null}
              {deployments.map(dep => (
                <option key={dep.id} value={dep.id}>
                  Deployment {dep.id.slice(0, 8)} · {dep.status}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-2xs text-slate-500 mb-1">Level</label>
            <select
              value={filters.level || ''}
              onChange={e => handleFilterChange('level', e.target.value)}
              className="w-full px-2.5 py-1.5 bg-black/30 text-slate-300 text-xs rounded border border-white/10 focus:outline-none focus:border-cyan-400/50"
            >
              <option value="">All levels</option>
              <option value="error">Error</option>
              <option value="warn">Warning</option>
              <option value="info">Info</option>
              <option value="debug">Debug</option>
            </select>
          </div>
          <div>
            <label className="block text-2xs text-slate-500 mb-1">Search</label>
            <input
              type="text"
              value={filters.search || ''}
              onChange={e => handleFilterChange('search', e.target.value)}
              placeholder="Search logs..."
              className="w-full px-2.5 py-1.5 bg-black/30 text-slate-300 text-xs rounded border border-white/10 focus:outline-none focus:border-cyan-400/50 placeholder:text-slate-600"
            />
          </div>
        </div>

        <div className="flex items-center gap-2 mt-2">
          <button
            onClick={handleExportText}
            disabled={filteredLogs.length === 0}
            className="px-2.5 py-1 rounded text-xs font-medium bg-emerald-500/15 text-emerald-300 border border-emerald-500/30 hover:bg-emerald-500/25 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            Export .log
          </button>
          <button
            onClick={handleExportJson}
            disabled={filteredLogs.length === 0}
            className="px-2.5 py-1 rounded text-xs font-medium bg-emerald-500/15 text-emerald-300 border border-emerald-500/30 hover:bg-emerald-500/25 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            Export .json
          </button>
          <button
            onClick={handleClear}
            disabled={logs.length === 0}
            className="px-2.5 py-1 rounded text-xs font-medium bg-red-500/15 text-red-300 border border-red-500/30 hover:bg-red-500/25 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            Clear
          </button>
        </div>
      </div>

      {deploymentsError && (
        <div className="bg-red-500/10 border border-red-500/20 text-red-300 p-3 mx-4 mt-4 rounded-lg text-xs flex justify-between items-center">
          <span>Deployment list unavailable: {deploymentsError}</span>
          <button onClick={() => setDeploymentsError(null)} className="text-red-400/60 hover:text-red-400">×</button>
        </div>
      )}

      {logsError && logs.length > 0 && (
        <div className="bg-red-500/10 border border-red-500/20 text-red-300 p-3 mx-4 mt-4 rounded-lg text-xs flex justify-between items-center">
          <span>Log refresh failed: {logsError}</span>
          <button onClick={() => setLogsError(null)} className="text-red-400/60 hover:text-red-400">×</button>
        </div>
      )}

      <div className="flex items-center justify-between px-4 py-2 text-xs text-slate-500 border-b border-white/5">
        <span>
          Showing {filteredLogs.length} of {logs.length} logs
          {logs.length >= MAX_LOG_BUFFER && (
            <span className="ml-2 px-1.5 py-0.5 rounded bg-amber-500/15 text-amber-400 border border-amber-500/25">
              Buffer full ({MAX_LOG_BUFFER})
            </span>
          )}
        </span>
        <span>
          Auto-scroll: {isAutoScroll ? 'On' : 'Off'}
          {logs.length > 0 && (
            <span className="ml-2">Last: {new Date(logs[logs.length - 1]?.timestamp).toLocaleTimeString()}</span>
          )}
        </span>
      </div>

      <div
        ref={logContainerRef}
        className="flex-1 overflow-auto p-4 font-mono text-sm space-y-1.5"
      >
        {(isDeploymentsLoading || isLoading) && logs.length === 0 ? (
          <div className="flex items-center justify-center h-32 text-slate-500">
            Loading logs...
          </div>
        ) : logsError ? (
          <EmptyState
            title="Logs unavailable"
            message={logsError}
            className="h-40 border-red-500/20 bg-red-500/[0.03]"
          />
        ) : !selectedDeploymentId ? (
          <EmptyState
            title="No deployment selected"
            message="Create or select a deployment to load its log records."
            className="h-40 border-white/5 bg-white/[0.02]"
          />
        ) : filteredLogs.length === 0 ? (
          <EmptyState
            title={filters.level || filters.search ? 'No logs match your filters' : 'No logs available'}
            message={filters.level || filters.search
              ? 'Try changing the level or search filters.'
              : 'The backend returned no log records for this deployment.'}
            className="h-40 border-white/5 bg-white/[0.02]"
          />
        ) : (
          filteredLogs.map(entry => (
            <div
              key={entry.id}
              className={cn(
                'border-l-4 pl-4 py-2 rounded-r',
                getLogLevelBg(entry.level)
              )}
            >
              <div className="flex items-start justify-between gap-2">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center space-x-2 text-xs">
                    <span className="text-slate-500">
                      {new Date(entry.timestamp).toLocaleTimeString()}
                    </span>
                    <span className={cn('font-medium uppercase', getLogLevelColor(entry.level))}>
                      {entry.level}
                    </span>
                    <span className="text-slate-500">[agent:{entry.agent_id.slice(0, 8)}]</span>
                  </div>
                  <div className="mt-1 text-slate-300 break-words whitespace-pre-wrap">
                    {entry.message}
                  </div>
                  {entry.extra_data && (
                    <details className="mt-1.5">
                      <summary className="cursor-pointer text-xs text-slate-600 hover:text-slate-400">
                        Data
                      </summary>
                      <pre className="mt-1 text-xs text-slate-600 overflow-auto max-h-24 bg-black/30 p-2 rounded">
                        {entry.extra_data}
                      </pre>
                    </details>
                  )}
                </div>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  )
}
