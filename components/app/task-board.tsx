'use client'

import { useState, useEffect, useCallback } from 'react'
import { EmptyState } from '@/components/dashboard'
import { normalizeCollection } from '@/components/app/http'
import { cn } from '@/lib/utils'

interface Task {
  id: string
  title: string
  description?: string
  status: 'pending' | 'running' | 'done' | 'failed' | 'awaiting_owner'
  priority: 'low' | 'medium' | 'high' | 'critical'
  agentId?: string
  deploymentId?: string
  createdAt: number
  updatedAt: number
}

interface Agent {
  id: string
  name: string
  status: string
  created_at?: string
  updated_at?: string
}

interface Deployment {
  id: string
  name: string
  status: string
  created_at?: string
  updated_at?: string
}

const COLUMNS = [
  { key: 'pending', label: 'Pending', color: 'bg-slate-500/20 text-slate-400' },
  { key: 'awaiting_owner', label: 'Awaiting Owner', color: 'bg-amber-500/20 text-amber-400' },
  { key: 'running', label: 'Running', color: 'bg-blue-500/20 text-blue-400' },
  { key: 'done', label: 'Done', color: 'bg-emerald-500/20 text-emerald-400' },
  { key: 'failed', label: 'Failed', color: 'bg-red-500/20 text-red-400' },
] as const

const priorityColors: Record<string, string> = {
  low: 'border-l-emerald-500',
  medium: 'border-l-amber-500',
  high: 'border-l-orange-500',
  critical: 'border-l-red-500',
}

const priorityBadgeColors: Record<string, string> = {
  low: 'bg-emerald-500/15 text-emerald-300',
  medium: 'bg-amber-500/15 text-amber-300',
  high: 'bg-orange-500/15 text-orange-300',
  critical: 'bg-red-500/15 text-red-300',
}

function formatTimestamp(ts: number) {
  const diff = Date.now() - ts
  const minutes = Math.floor(diff / 60000)
  const hours = Math.floor(diff / 3600000)
  const days = Math.floor(diff / 86400000)
  if (minutes < 1) return 'Just now'
  if (minutes < 60) return `${minutes}m ago`
  if (hours < 24) return `${hours}h ago`
  return `${days}d ago`
}

function TaskCard({
  task,
  agent,
}: {
  task: Task
  agent?: Agent
}) {
  const [isDragging, setIsDragging] = useState(false)

  return (
    <div
      draggable
      onDragStart={() => setIsDragging(true)}
      onDragEnd={() => setIsDragging(false)}
      className={cn(
        'bg-white/[0.03] rounded-lg p-3 border border-white/5 border-l-4 cursor-grab active:cursor-grabbing',
        'hover:border-white/10 hover:bg-white/[0.05] transition-all',
        priorityColors[task.priority],
        isDragging ? 'opacity-50 scale-[0.97]' : ''
      )}
    >
      <div className="flex items-start justify-between gap-2 mb-2">
        <h4 className="text-sm font-medium text-white leading-tight line-clamp-2 flex-1">
          {task.title}
        </h4>
        <span className={cn(
          'text-[10px] px-1.5 py-0.5 rounded font-medium shrink-0',
          priorityBadgeColors[task.priority]
        )}>
          {task.priority}
        </span>
      </div>

      {task.description && (
        <p className="text-xs text-slate-500 line-clamp-2 mb-2">
          {task.description}
        </p>
      )}

      <div className="flex items-center justify-between mt-auto pt-2 border-t border-white/5">
        <div className="flex items-center gap-1.5 text-xs text-slate-500">
          {agent ? (
            <>
              <span className={cn(
                'w-1.5 h-1.5 rounded-full',
                agent.status === 'running' ? 'bg-emerald-400' :
                agent.status === 'failed' || agent.status === 'error' ? 'bg-red-400' :
                'bg-slate-500'
              )} />
              <span className="truncate max-w-[80px]">{agent.name}</span>
            </>
          ) : task.agentId ? (
            <span className="text-slate-600 italic">Unassigned</span>
          ) : null}
        </div>
        <div className="flex items-center gap-1.5">
          <span className="text-[10px] text-slate-600">{formatTimestamp(task.updatedAt)}</span>
        </div>
      </div>
    </div>
  )
}

interface TaskBoardProps {
  className?: string
  initialTasks?: Task[]
}

export function TaskBoard({ className, initialTasks = [] }: TaskBoardProps) {
  const [tasks, setTasks] = useState<Task[]>(initialTasks)
  const [agents, setAgents] = useState<Agent[]>([])
  const [deployments, setDeployments] = useState<Deployment[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [draggedTask, setDraggedTask] = useState<Task | null>(null)
  const [dragOverColumn, setDragOverColumn] = useState<string | null>(null)

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

      const generatedTasks: Task[] = []

      for (const agent of agentsData) {
        const ts = new Date(agent.created_at ?? Date.now()).getTime()
        generatedTasks.push({
          id: `agent-${agent.id}`,
          title: `Manage agent: ${agent.name}`,
          description: `Monitor and manage the ${agent.name} agent lifecycle`,
          status: agent.status === 'running' ? 'running' :
                  agent.status === 'failed' || agent.status === 'error' ? 'failed' :
                  'pending',
          priority: agent.status === 'running' ? 'medium' :
                   agent.status === 'failed' || agent.status === 'error' ? 'high' : 'low',
          agentId: agent.id,
          createdAt: ts,
          updatedAt: ts,
        })
      }

      for (const dep of deploymentsData) {
        const ts = new Date(dep.created_at ?? Date.now()).getTime()
        generatedTasks.push({
          id: `dep-${dep.id}`,
          title: `Deployment: ${dep.name}`,
          description: `Track deployment status and health`,
          status: dep.status === 'running' ? 'running' :
                  dep.status === 'failed' || dep.status === 'error' ? 'failed' :
                  dep.status === 'done' ? 'done' : 'pending',
          priority: dep.status === 'failed' || dep.status === 'error' ? 'critical' :
                   dep.status === 'running' ? 'high' : 'low',
          deploymentId: dep.id,
          createdAt: ts,
          updatedAt: ts,
        })
      }

      setTasks(generatedTasks)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load tasks')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchData()
  }, [fetchData])

  const tasksByStatus = COLUMNS.reduce((acc, col) => {
    acc[col.key] = tasks.filter(t => t.status === col.key)
    return acc
  }, {} as Record<string, Task[]>)

  const getAgentById = (id?: string) => agents.find(a => a.id === id)

  const handleDragOver = (e: React.DragEvent, columnKey: string) => {
    e.preventDefault()
    setDragOverColumn(columnKey)
  }

  const handleDragLeave = () => {
    setDragOverColumn(null)
  }

  const handleDrop = async (e: React.DragEvent, newStatus: string) => {
    e.preventDefault()
    setDragOverColumn(null)
    if (!draggedTask || draggedTask.status === newStatus) {
      setDraggedTask(null)
      return
    }

    const _previousStatus = draggedTask.status
    setTasks(prev => prev.map(t =>
      t.id === draggedTask.id ? { ...t, status: newStatus as Task['status'], updatedAt: Date.now() } : t
    ))
    setDraggedTask(null)
  }

  if (loading) {
    return (
      <div className={cn('flex flex-col h-full', className)}>
        <div className="p-4 border-b border-white/10">
          <div className="h-7 w-32 rounded bg-white/5 motion-safe:animate-pulse motion-reduce:animate-none" />
        </div>
        <div className="flex-1 flex gap-4 p-4 overflow-x-auto">
          {COLUMNS.map(col => (
            <div key={col.key} className="flex-1 min-w-72">
              <div className="rounded-lg border border-white/5 bg-white/[0.02] flex flex-col min-h-64">
                <div className={cn('px-4 py-3 rounded-t-lg border-b border-white/5', col.color)}>
                  <div className="h-4 w-20 rounded bg-white/10 motion-safe:animate-pulse motion-reduce:animate-none" />
                </div>
                <div className="flex-1 p-3 space-y-3">
                  {[1, 2].map(i => (
                    <div key={i} className="h-20 rounded border border-l-2 border-white/5 border-l-slate-600 bg-white/[0.03] motion-safe:animate-pulse motion-reduce:animate-none" />
                  ))}
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    )
  }

  const hasData = agents.length > 0 || deployments.length > 0

  return (
    <div className={cn('flex flex-col h-full', className)}>
      <div className="flex items-center justify-between p-4 border-b border-white/10">
        <div>
          <h2 className="text-lg font-semibold text-white">Task Board</h2>
          <p className="text-xs text-slate-500 mt-0.5">Drag cards between columns to update status</p>
        </div>
        <button
          onClick={fetchData}
          className="px-3 py-1.5 rounded-lg border border-white/10 bg-white/[0.02] text-xs text-slate-400 hover:text-white hover:border-white/20 transition-colors"
        >
          Refresh
        </button>
      </div>

      {error && (
        <div className="bg-red-500/10 border border-red-500/20 text-red-300 p-3 mx-4 mt-4 rounded-lg text-xs flex justify-between items-center">
          <span>{error}</span>
          <button onClick={() => setError(null)} className="text-red-400/60 hover:text-red-400">×</button>
        </div>
      )}

      {hasData ? (
        <div className="flex-1 flex gap-4 p-4 overflow-x-auto">
          {COLUMNS.map(col => (
            <div
              key={col.key}
              onDragOver={e => handleDragOver(e, col.key)}
              onDragLeave={handleDragLeave}
              onDrop={e => handleDrop(e, col.key)}
              className={cn(
                'flex-1 min-w-72 rounded-lg border flex flex-col transition-colors',
                dragOverColumn === col.key
                  ? 'border-cyan-400/40 bg-cyan-500/5'
                  : 'border-white/5 bg-white/[0.02]'
              )}
            >
              <div className={cn('px-4 py-3 rounded-t-lg flex justify-between items-center border-b border-white/5', col.color)}>
                <h3 className="text-sm font-semibold tracking-wide">{col.label}</h3>
                <span className="text-xs font-mono bg-white/10 px-2 py-0.5 rounded min-w-[1.75rem] text-center">
                  {tasksByStatus[col.key]?.length || 0}
                </span>
              </div>

              <div className="flex-1 p-3 space-y-2.5 min-h-32 overflow-y-auto">
                {tasksByStatus[col.key]?.map(task => (
                  <div
                    key={task.id}
                    draggable
                    onDragStart={() => setDraggedTask(task)}
                    onDragEnd={() => { setDraggedTask(null); setDragOverColumn(null) }}
                    className={cn(
                      'cursor-grab active:cursor-grabbing',
                      draggedTask?.id === task.id ? 'opacity-50' : ''
                    )}
                  >
                    <TaskCard
                      task={task}
                      agent={task.agentId ? getAgentById(task.agentId) : undefined}
                    />
                  </div>
                ))}

                {tasksByStatus[col.key]?.length === 0 && (
                  <div className="flex flex-col items-center justify-center py-8 text-slate-600">
                    <svg className="w-6 h-6 mb-1.5 opacity-40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                      <rect x="3" y="3" width="18" height="18" rx="2" />
                      <path d="M9 12h6M12 9v6" strokeLinecap="round" />
                    </svg>
                    <span className="text-xs">Drop tasks here</span>
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="flex-1 p-4">
          <EmptyState
            title="No work items yet"
            message="Tasks will appear here once agents or deployments exist in this account."
            className="h-full border-white/5 bg-white/[0.02]"
          />
        </div>
      )}

      <div className="border-t border-white/5 p-3 bg-white/[0.02] text-xs text-slate-500">
        <div className="flex justify-between">
          <span>{tasks.length} total tasks</span>
          <span>{tasks.filter(t => t.status === 'running').length} running</span>
        </div>
      </div>
    </div>
  )
}
