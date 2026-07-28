'use client'

import { useState, useEffect, useCallback } from 'react'
import { EmptyState } from '@/components/dashboard'
import { normalizeCollection } from '@/components/app/http'
import { cn } from '@/lib/utils'

interface ActivityEvent {
  id: string
  type: 'agent_created' | 'agent_status_change' | 'deployment_created' | 'deployment_updated' | 'deployment_failed'
  actor: string
  description: string
  timestamp: number
  entity?: {
    type: 'agent' | 'deployment'
    name: string
    status?: string
  }
}

interface Agent {
  id: string
  name: string
  status: string
  created_at: string
  updated_at: string
}

interface Deployment {
  id: string
  name: string
  status: string
  created_at: string
  updated_at: string
}

const activityIcons: Record<string, string> = {
  agent_created: '+',
  agent_status_change: '~',
  deployment_created: '^',
  deployment_updated: '#',
  deployment_failed: '!',
}

const activityColors: Record<string, string> = {
  agent_created: 'text-cyan-400',
  agent_status_change: 'text-blue-400',
  deployment_created: 'text-purple-400',
  deployment_updated: 'text-emerald-400',
  deployment_failed: 'text-red-400',
}

const activityBgColors: Record<string, string> = {
  agent_created: 'bg-cyan-500/15',
  agent_status_change: 'bg-blue-500/15',
  deployment_created: 'bg-purple-500/15',
  deployment_updated: 'bg-emerald-500/15',
  deployment_failed: 'bg-red-500/15',
}

function formatRelativeTime(timestamp: number) {
  const now = Date.now()
  const diffMs = now - timestamp
  const diffMinutes = Math.floor(diffMs / (1000 * 60))
  const diffHours = Math.floor(diffMs / (1000 * 60 * 60))
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24))

  if (diffMinutes < 1) return 'Just now'
  if (diffMinutes < 60) return `${diffMinutes}m ago`
  if (diffHours < 24) return `${diffHours}h ago`
  if (diffDays < 7) return `${diffDays}d ago`
  return new Date(timestamp).toLocaleDateString()
}

function groupByDay(events: ActivityEvent[]): Record<string, ActivityEvent[]> {
  const groups: Record<string, ActivityEvent[]> = {}
  for (const event of events) {
    const day = new Date(event.timestamp).toLocaleDateString(undefined, {
      weekday: 'long',
      month: 'short',
      day: 'numeric',
    })
    if (!groups[day]) groups[day] = []
    groups[day].push(event)
  }
  return groups
}

function TimelineRow({ event }: { event: ActivityEvent }) {
  return (
    <div className="flex items-start gap-2.5 pl-3 py-1.5 hover:bg-white/5 rounded-r transition-colors relative">
      <span className={cn(
        'absolute -left-[5px] top-3 w-2 h-2 rounded-full border-2',
        event.type === 'deployment_failed' ? 'border-red-400' :
        event.type.startsWith('deployment') ? 'border-purple-400' :
        event.type.startsWith('agent') ? 'border-cyan-400' :
        'border-slate-500'
      )} />
      <span className={cn(
        'w-5 h-5 rounded flex items-center justify-center text-2xs font-mono font-bold shrink-0',
        activityBgColors[event.type],
        activityColors[event.type]
      )}>
        {activityIcons[event.type] || '?'}
      </span>
      <div className="flex-1 min-w-0">
        <p className="text-xs text-slate-300">{event.description}</p>
        {event.entity?.name && (
          <p className="text-2xs text-slate-500 mt-0.5 truncate">
            {event.entity.name}
          </p>
        )}
      </div>
      <span className="text-2xs text-slate-500 font-mono shrink-0">
        {new Date(event.timestamp).toLocaleTimeString(undefined, {
          hour: '2-digit',
          minute: '2-digit',
        })}
      </span>
    </div>
  )
}

interface ActivityFeedProps {
  className?: string
  limit?: number
  autoRefresh?: boolean
  showFilters?: boolean
}

export function ActivityFeed({
  className,
  limit = 50,
  autoRefresh = false,
  showFilters = true
}: ActivityFeedProps) {
  const [events, setEvents] = useState<ActivityEvent[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [autoRefreshOn, setAutoRefreshOn] = useState(autoRefresh)
  const [selectedEntity, setSelectedEntity] = useState<string>('')
  const [filterType, setFilterType] = useState<string>('')
  const [agents, setAgents] = useState<Agent[]>([])
  const [deployments, setDeployments] = useState<Deployment[]>([])

  const fetchData = useCallback(async () => {
    try {
      setError(null)
      const [agentsRes, deploymentsRes] = await Promise.all([
        fetch('/api/dashboard/agents').catch(() => null),
        fetch('/api/dashboard/deployments').catch(() => null),
      ])

      let agentsData: Agent[] = []
      let deploymentsData: Deployment[] = []

      if (agentsRes?.ok) {
        const data = await agentsRes.json()
        agentsData = normalizeCollection<Agent>(data, ['items', 'agents', 'data'])
        setAgents(agentsData)
      }

      if (deploymentsRes?.ok) {
        const data = await deploymentsRes.json()
        deploymentsData = normalizeCollection<Deployment>(data, ['items', 'deployments', 'data'])
        setDeployments(deploymentsData)
      }

      const newEvents: ActivityEvent[] = []

      for (const agent of agentsData) {
        const createdTs = new Date(agent.created_at).getTime()
        const updatedTs = new Date(agent.updated_at).getTime()
        const eventId = `agent-${agent.id}`

        newEvents.push({
          id: `${eventId}-created`,
          type: 'agent_created',
          actor: 'system',
          description: 'agent registered',
          timestamp: createdTs,
          entity: { type: 'agent', name: agent.name, status: agent.status }
        })

        if (updatedTs - createdTs > 60000) {
          newEvents.push({
            id: `${eventId}-status`,
            type: 'agent_status_change',
            actor: 'system',
            description: 'status changed',
            timestamp: updatedTs,
            entity: { type: 'agent', name: agent.name, status: agent.status }
          })
        }
      }

      for (const dep of deploymentsData) {
        const createdTs = new Date(dep.created_at).getTime()
        const updatedTs = new Date(dep.updated_at).getTime()
        const eventId = `dep-${dep.id}`

        newEvents.push({
          id: `${eventId}-created`,
          type: 'deployment_created',
          actor: 'system',
          description: 'deployment created',
          timestamp: createdTs,
          entity: { type: 'deployment', name: dep.name, status: dep.status }
        })

        if (dep.status === 'failed' || dep.status === 'error') {
          newEvents.push({
            id: `${eventId}-failed`,
            type: 'deployment_failed',
            actor: 'system',
            description: 'deployment failed',
            timestamp: updatedTs,
            entity: { type: 'deployment', name: dep.name, status: dep.status }
          })
        } else if (updatedTs - createdTs > 60000) {
          newEvents.push({
            id: `${eventId}-updated`,
            type: 'deployment_updated',
            actor: 'system',
            description: 'deployment updated',
            timestamp: updatedTs,
            entity: { type: 'deployment', name: dep.name, status: dep.status }
          })
        }
      }

      newEvents.sort((a, b) => b.timestamp - a.timestamp)
      setEvents(newEvents)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load activity')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchData()
  }, [fetchData])

  useEffect(() => {
    if (!autoRefreshOn) return
    const interval = setInterval(fetchData, 30000)
    return () => clearInterval(interval)
  }, [autoRefreshOn, fetchData])

  const filteredEvents = events.filter(event => {
    if (selectedEntity && event.entity?.name !== selectedEntity) return false
    if (filterType && event.type !== filterType) return false
    return true
  }).slice(0, limit)

  const allEntities = [
    ...agents.map(a => ({ name: a.name, type: 'agent' as const })),
    ...deployments.map(d => ({ name: d.name, type: 'deployment' as const }))
  ]

  const activityTypes = Array.from(new Set(events.map(e => e.type))).sort()
  const groupedByDay = groupByDay(filteredEvents)

  return (
    <div className={cn('flex flex-col', className)}>
      {showFilters && (
        <div className="p-4 border-b border-white/10 bg-white/[0.02]">
          <div className="flex items-center justify-between gap-3 mb-3">
            <div className="flex items-center gap-2">
              <h3 className="text-sm font-semibold text-white">Activity Feed</h3>
              <div className={cn(
                'w-2 h-2 rounded-full',
                autoRefreshOn
                  ? 'bg-emerald-400 motion-safe:animate-pulse motion-reduce:animate-none'
                  : 'bg-slate-600'
              )} />
            </div>
            <button
              onClick={() => setAutoRefreshOn(!autoRefreshOn)}
              className={cn(
                'px-2.5 py-1 rounded text-xs font-medium transition-colors border',
                autoRefreshOn
                  ? 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30'
                  : 'bg-white/5 text-slate-400 border-white/10 hover:text-white'
              )}
            >
              {autoRefreshOn ? 'Live' : 'Paused'}
            </button>
          </div>
          <div className="flex gap-3 flex-wrap">
            <select
              value={selectedEntity}
              onChange={e => setSelectedEntity(e.target.value)}
              className="bg-black/30 text-slate-300 text-xs rounded px-2.5 py-1.5 border border-white/10 focus:outline-none focus:border-cyan-400/50"
            >
              <option value="">All entities</option>
              {allEntities.map(entity => (
                <option key={`${entity.type}-${entity.name}`} value={entity.name}>
                  {entity.type === 'agent' ? '🤖' : '🚀'} {entity.name}
                </option>
              ))}
            </select>
            <select
              value={filterType}
              onChange={e => setFilterType(e.target.value)}
              className="bg-black/30 text-slate-300 text-xs rounded px-2.5 py-1.5 border border-white/10 focus:outline-none focus:border-cyan-400/50"
            >
              <option value="">All types</option>
              {activityTypes.map(type => (
                <option key={type} value={type}>
                  {activityIcons[type] || '•'} {type.replace(/_/g, ' ')}
                </option>
              ))}
            </select>
          </div>
        </div>
      )}

      {error && (
        <div className="bg-red-500/10 border border-red-500/20 text-red-300 p-3 mx-4 mt-4 rounded-lg text-xs">
          {error}
        </div>
      )}

      <div className="flex-1 overflow-y-auto">
        {loading && events.length === 0 ? (
          <div className="flex items-center justify-center py-12">
            <div className="text-slate-500 text-sm">Loading activity...</div>
          </div>
        ) : filteredEvents.length === 0 ? (
          <div className="p-4">
            <EmptyState
              title="No activity yet"
              message={selectedEntity || filterType
                ? 'Try clearing your filters to see agent and deployment activity.'
                : 'Activity will appear here as agents and deployments are created, updated, and fail.'}
              className="border-white/5 bg-white/[0.02]"
            />
          </div>
        ) : (
          <div className="space-y-2 p-4">
            {Object.entries(groupedByDay).map(([day, dayEvents]) => (
              <div key={day}>
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-xs font-semibold text-slate-500">{day}</span>
                  <span className="flex-1 h-px bg-white/5" />
                  <span className="text-2xs text-slate-600">{dayEvents.length} events</span>
                </div>
                <div className="space-y-1">
                  {dayEvents.map(event => (
                    <TimelineRow key={event.id} event={event} />
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="border-t border-white/5 p-3 bg-white/[0.02] text-xs text-slate-500">
        <div className="flex justify-between">
          <span>Showing {filteredEvents.length} events{filterType ? ` (filtered)` : ''}</span>
          <span>Last updated: {events.length > 0 ? formatRelativeTime(events[0]?.timestamp || Date.now()) : 'Never'}</span>
        </div>
      </div>
    </div>
  )
}
