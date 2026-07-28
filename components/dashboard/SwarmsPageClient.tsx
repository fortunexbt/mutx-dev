'use client'

import { useCallback, useEffect, useState } from 'react'
import type { FormEvent } from 'react'

import { readJson, writeJson } from '@/components/app/http'
import {
  dashboardRequestErrorMessage,
  getDashboardRequestAccessFailure,
} from '@/components/dashboard/dashboardRequestAccess'
import { DashboardDialog } from '@/components/dashboard/DashboardDialog'
import {
  LiveAuthRequired,
  LiveEmptyState,
  LiveErrorState,
  LiveForbidden,
  LiveLoading,
  LivePanel,
  asDashboardStatus,
  formatRelativeTime,
} from '@/components/dashboard/livePrimitives'
import { StatusBadge } from '@/components/dashboard/StatusBadge'

import type { components } from '@/app/types/api'

type Swarm = components['schemas']['SwarmResponse']
type SwarmList = components['schemas']['SwarmListResponse']
type SwarmCreate = components['schemas']['SwarmCreate']
type SwarmUpdate = components['schemas']['SwarmUpdate']
type SwarmBlueprint = components['schemas']['SwarmBlueprintResponse']
type PendingSwarmAction =
  | { kind: 'scale'; swarm: Swarm; replicas: number }
  | { kind: 'delete'; swarm: Swarm }

type CreateDraft = {
  name: string
  description: string
  agentIds: string
  minReplicas: string
  maxReplicas: string
}

type EditDraft = {
  name: string
  description: string
  minReplicas: string
  maxReplicas: string
}

const PAGE_SIZE = 16
const emptyCreateDraft: CreateDraft = {
  name: '',
  description: '',
  agentIds: '',
  minReplicas: '1',
  maxReplicas: '10',
}
const inputClass =
  'w-full rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-sm text-white outline-none transition placeholder:text-slate-600 focus:border-cyan-400/40'
const secondaryButtonClass =
  'min-h-11 rounded-lg border border-white/10 bg-white/[0.04] px-3 py-2 text-xs font-medium text-slate-300 transition hover:border-white/20 hover:text-white disabled:cursor-not-allowed disabled:opacity-50'
const primaryButtonClass =
  'min-h-11 rounded-lg border border-cyan-400/30 bg-cyan-400/10 px-3 py-2 text-xs font-semibold text-cyan-100 transition hover:border-cyan-300/50 disabled:cursor-not-allowed disabled:opacity-50'
const dangerButtonClass =
  'min-h-11 rounded-lg border border-rose-400/20 bg-rose-400/10 px-3 py-2 text-xs font-medium text-rose-200 transition hover:border-rose-300/40 disabled:cursor-not-allowed disabled:opacity-50'

function errorMessage(error: unknown, fallback: string) {
  return dashboardRequestErrorMessage(error, fallback)
}

function parseInteger(value: string, label: string) {
  const parsed = Number(value)
  if (!Number.isInteger(parsed)) throw new Error(`${label} must be a whole number.`)
  return parsed
}

function parseAgentIds(value: string) {
  return Array.from(
    new Set(
      value
        .split(/[\s,]+/)
        .map((item) => item.trim())
        .filter(Boolean),
    ),
  )
}

export function SwarmsPageClient() {
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [loadingMore, setLoadingMore] = useState(false)
  const [authRequired, setAuthRequired] = useState(false)
  const [permissionDenied, setPermissionDenied] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [catalogError, setCatalogError] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [actionNotice, setActionNotice] = useState<string | null>(null)
  const [actingId, setActingId] = useState<string | null>(null)
  const [swarms, setSwarms] = useState<Swarm[]>([])
  const [total, setTotal] = useState(0)
  const [hasMore, setHasMore] = useState(false)
  const [blueprints, setBlueprints] = useState<SwarmBlueprint[]>([])
  const [createDraft, setCreateDraft] = useState<CreateDraft>(emptyCreateDraft)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editDraft, setEditDraft] = useState<EditDraft | null>(null)
  const [scaleTargets, setScaleTargets] = useState<Record<string, string>>({})
  const [pendingAction, setPendingAction] = useState<PendingSwarmAction | null>(null)
  const [dialogError, setDialogError] = useState<string | null>(null)

  const loadInitial = useCallback(async () => {
    setLoading(true)
    setError(null)
    setCatalogError(null)
    setAuthRequired(false)
    setPermissionDenied(false)

    const [swarmResult, blueprintResult] = await Promise.allSettled([
      readJson<SwarmList>(`/api/dashboard/swarms?skip=0&limit=${PAGE_SIZE}`),
      readJson<SwarmBlueprint[]>('/api/dashboard/swarms/blueprints'),
    ])

    if (swarmResult.status === 'rejected') {
      const accessFailure = getDashboardRequestAccessFailure(swarmResult.reason)
      if (accessFailure === 'authentication') setAuthRequired(true)
      else if (accessFailure === 'permission') setPermissionDenied(true)
      else setError(errorMessage(swarmResult.reason, 'Failed to load swarms'))
      setLoading(false)
      return
    }

    setSwarms(swarmResult.value.items ?? [])
    setTotal(swarmResult.value.total)
    setHasMore(swarmResult.value.has_more)
    if (blueprintResult.status === 'fulfilled') {
      setBlueprints(Array.isArray(blueprintResult.value) ? blueprintResult.value : [])
    } else {
      const accessFailure = getDashboardRequestAccessFailure(blueprintResult.reason)
      if (accessFailure === 'authentication') setAuthRequired(true)
      else if (accessFailure === 'permission') setPermissionDenied(true)
      else setCatalogError(errorMessage(blueprintResult.reason, 'Failed to load swarm blueprints'))
    }
    setLoading(false)
  }, [])

  useEffect(() => {
    void loadInitial()
  }, [loadInitial])

  async function canonicalReload() {
    setRefreshing(true)
    setError(null)
    try {
      const limit = Math.min(100, Math.max(PAGE_SIZE, swarms.length))
      const response = await readJson<SwarmList>(`/api/dashboard/swarms?skip=0&limit=${limit}`)
      setSwarms(response.items ?? [])
      setTotal(response.total)
      setHasMore(response.has_more)
    } catch (loadError) {
      const accessFailure = getDashboardRequestAccessFailure(loadError)
      if (accessFailure === 'authentication') setAuthRequired(true)
      else if (accessFailure === 'permission') setPermissionDenied(true)
      else setError(errorMessage(loadError, 'Failed to refresh swarms'))
    } finally {
      setRefreshing(false)
    }
  }

  async function loadMore() {
    setLoadingMore(true)
    setActionError(null)
    try {
      const response = await readJson<SwarmList>(
        `/api/dashboard/swarms?skip=${swarms.length}&limit=${PAGE_SIZE}`,
      )
      setSwarms((current) => {
        const known = new Set(current.map((swarm) => swarm.id))
        return [...current, ...response.items.filter((swarm) => !known.has(swarm.id))]
      })
      setTotal(response.total)
      setHasMore(response.has_more)
    } catch (loadError) {
      const accessFailure = getDashboardRequestAccessFailure(loadError)
      if (accessFailure === 'authentication') setAuthRequired(true)
      else if (accessFailure === 'permission') setPermissionDenied(true)
      else setActionError(errorMessage(loadError, 'Failed to load more swarms'))
    } finally {
      setLoadingMore(false)
    }
  }

  async function createSwarm(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setActingId('create')
    setActionError(null)
    setActionNotice(null)

    try {
      const agentIds = parseAgentIds(createDraft.agentIds)
      if (agentIds.length === 0) throw new Error('Add at least one owned agent ID.')
      if (!createDraft.name.trim()) throw new Error('Swarm name is required.')
      const minReplicas = parseInteger(createDraft.minReplicas, 'Minimum replicas')
      const maxReplicas = parseInteger(createDraft.maxReplicas, 'Maximum replicas')
      if (minReplicas > maxReplicas) throw new Error('Minimum replicas cannot exceed maximum replicas.')

      const payload: SwarmCreate = {
        name: createDraft.name.trim(),
        description: createDraft.description.trim() || null,
        agent_ids: agentIds,
        min_replicas: minReplicas,
        max_replicas: maxReplicas,
      }
      await writeJson<Swarm>('/api/dashboard/swarms', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      setCreateDraft(emptyCreateDraft)
      setActionNotice(`Created swarm ${payload.name}.`)
      await canonicalReload()
    } catch (mutationError) {
      const accessFailure = getDashboardRequestAccessFailure(mutationError)
      if (accessFailure === 'authentication') setAuthRequired(true)
      else if (accessFailure === 'permission') setPermissionDenied(true)
      else setActionError(errorMessage(mutationError, 'Failed to create swarm'))
    } finally {
      setActingId(null)
    }
  }

  function beginEdit(swarm: Swarm) {
    setEditingId(swarm.id)
    setEditDraft({
      name: swarm.name,
      description: swarm.description ?? '',
      minReplicas: String(swarm.min_replicas),
      maxReplicas: String(swarm.max_replicas),
    })
    setActionError(null)
  }

  async function updateSwarm(event: FormEvent<HTMLFormElement>, swarm: Swarm) {
    event.preventDefault()
    if (!editDraft) return
    setActingId(swarm.id)
    setActionError(null)
    setActionNotice(null)

    try {
      const minReplicas = parseInteger(editDraft.minReplicas, 'Minimum replicas')
      const maxReplicas = parseInteger(editDraft.maxReplicas, 'Maximum replicas')
      if (!editDraft.name.trim()) throw new Error('Swarm name is required.')
      if (minReplicas > maxReplicas) throw new Error('Minimum replicas cannot exceed maximum replicas.')
      const payload: SwarmUpdate = {
        name: editDraft.name.trim(),
        description: editDraft.description.trim() || null,
        min_replicas: minReplicas,
        max_replicas: maxReplicas,
      }
      await writeJson<Swarm>(`/api/dashboard/swarms/${encodeURIComponent(swarm.id)}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      setEditingId(null)
      setEditDraft(null)
      setActionNotice(`Updated swarm ${payload.name}.`)
      await canonicalReload()
    } catch (mutationError) {
      const accessFailure = getDashboardRequestAccessFailure(mutationError)
      if (accessFailure === 'authentication') setAuthRequired(true)
      else if (accessFailure === 'permission') setPermissionDenied(true)
      else setActionError(errorMessage(mutationError, 'Failed to update swarm'))
    } finally {
      setActingId(null)
    }
  }

  function requestScaleSwarm(swarm: Swarm) {
    const fallback = swarm.agents[0]?.replicas || swarm.min_replicas
    let replicas: number
    try {
      replicas = parseInteger(scaleTargets[swarm.id] ?? String(fallback), 'Replica target')
    } catch (validationError) {
      setActionError(errorMessage(validationError, 'Replica target is invalid'))
      return
    }
    if (replicas < swarm.min_replicas || replicas > swarm.max_replicas) {
      setActionError(`Replica target must be between ${swarm.min_replicas} and ${swarm.max_replicas}.`)
      return
    }
    if (actingId) return
    setActionError(null)
    setActionNotice(null)
    setDialogError(null)
    setPendingAction({ kind: 'scale', swarm, replicas })
  }

  function requestDeleteSwarm(swarm: Swarm) {
    if (actingId) return
    setActionError(null)
    setActionNotice(null)
    setDialogError(null)
    setPendingAction({ kind: 'delete', swarm })
  }

  async function confirmSwarmAction() {
    if (!pendingAction || actingId) return

    const action = pendingAction
    const { swarm } = action

    setActingId(swarm.id)
    setActionError(null)
    setActionNotice(null)
    setDialogError(null)
    try {
      if (action.kind === 'scale') {
        await writeJson<Swarm>(`/api/dashboard/swarms/${encodeURIComponent(swarm.id)}/scale`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ replicas: action.replicas }),
        })
        setActionNotice(`Scaled ${swarm.name} to ${action.replicas} replicas per active deployment.`)
      } else {
        await writeJson(`/api/dashboard/swarms/${encodeURIComponent(swarm.id)}`, { method: 'DELETE' })
        setActionNotice(`Deleted swarm ${swarm.name}.`)
        if (editingId === swarm.id) {
          setEditingId(null)
          setEditDraft(null)
        }
      }
      await canonicalReload()
      setPendingAction(null)
    } catch (mutationError) {
      const accessFailure = getDashboardRequestAccessFailure(mutationError)
      if (accessFailure === 'authentication') setAuthRequired(true)
      else if (accessFailure === 'permission') setPermissionDenied(true)
      else {
        const message = errorMessage(
          mutationError,
          action.kind === 'scale' ? 'Failed to scale swarm' : 'Failed to delete swarm',
        )
        setActionError(message)
        setDialogError(message)
      }
    } finally {
      setActingId(null)
    }
  }

  if (loading) return <LiveLoading title='Swarms' />
  if (authRequired) {
    return (
      <LiveAuthRequired
        title='Operator session required'
        message='Sign in to create and control grouped agent swarms.'
      />
    )
  }
  if (permissionDenied) {
    return <LiveForbidden title='Swarm permission required' message='Your account cannot create or control agent swarms. Create, edit, scale, and delete controls are unavailable.' />
  }
  if (error && swarms.length === 0) return <LiveErrorState title='Swarm surface unavailable' message={error} />

  return (
    <div className='space-y-4'>
      <DashboardDialog
        open={Boolean(pendingAction)}
        onOpenChange={(open) => {
          if (!open && !actingId) {
            setPendingAction(null)
            setDialogError(null)
          }
        }}
        title={pendingAction?.kind === 'delete' ? 'Delete swarm' : 'Scale swarm'}
        description={
          pendingAction?.kind === 'delete'
            ? 'Permanently remove this swarm grouping from MUTX.'
            : 'Apply one replica target to every active deployment in this swarm.'
        }
        footer={(
          <>
            <button
              type='button'
              data-autofocus
              onClick={() => {
                setPendingAction(null)
                setDialogError(null)
              }}
              disabled={Boolean(actingId)}
              className={`${secondaryButtonClass} w-full text-sm sm:w-auto`}
            >
              Cancel
            </button>
            <button
              type='button'
              onClick={() => void confirmSwarmAction()}
              disabled={Boolean(actingId)}
              className={`${pendingAction?.kind === 'delete' ? dangerButtonClass : primaryButtonClass} w-full text-sm sm:w-auto`}
            >
              {actingId
                ? pendingAction?.kind === 'delete' ? 'Deleting…' : 'Scaling…'
                : pendingAction?.kind === 'delete' ? 'Delete Swarm' : 'Scale Swarm'}
            </button>
          </>
        )}
      >
        <div aria-busy={Boolean(actingId)} className='space-y-4 text-start'>
          <div className='rounded-xl border border-white/10 bg-black/20 p-3'>
            <p className='text-sm font-semibold text-white'>{pendingAction?.swarm.name}</p>
            <p dir='ltr' className='mt-1 break-all text-start font-mono text-xs text-slate-500'>
              {pendingAction?.swarm.id}
            </p>
          </div>
          <p className='text-sm leading-6 text-slate-300'>
            {pendingAction?.kind === 'delete'
              ? 'The swarm grouping will be removed. Its agents and deployments will remain available outside this group.'
              : `Every active deployment in this swarm will be scaled to ${pendingAction?.replicas ?? 0} replicas, which may change runtime capacity.`}
          </p>
          {dialogError ? (
            <div role='alert' className='rounded-xl border border-rose-400/20 bg-rose-400/10 px-4 py-3 text-sm text-rose-200'>
              Swarm action failed: {dialogError}
            </div>
          ) : null}
        </div>
      </DashboardDialog>

      {error ? (
        <div role='alert' className='rounded-xl border border-rose-400/20 bg-rose-400/10 px-4 py-3 text-sm text-rose-200'>
          Swarm refresh failed: {error}. Existing rows are retained.
        </div>
      ) : null}
      {actionError && !pendingAction ? (
        <div role='alert' className='rounded-xl border border-rose-400/20 bg-rose-400/10 px-4 py-3 text-sm text-rose-200'>
          Swarm action failed: {actionError}
        </div>
      ) : null}
      {actionNotice ? (
        <div role='status' aria-live='polite' aria-atomic='true' className='rounded-xl border border-emerald-400/20 bg-emerald-400/10 px-4 py-3 text-sm text-emerald-200'>
          {actionNotice}
        </div>
      ) : null}

      <LivePanel title='Create swarm' meta='backend-owned agents'>
        <form onSubmit={createSwarm} className='grid gap-3 lg:grid-cols-2'>
          <label className='space-y-1.5 text-xs text-slate-400'>
            <span>Name</span>
            <input
              className={inputClass}
              value={createDraft.name}
              onChange={(event) => setCreateDraft((current) => ({ ...current, name: event.target.value }))}
              required
              maxLength={255}
            />
          </label>
          <label className='space-y-1.5 text-xs text-slate-400'>
            <span>Owned agent IDs</span>
            <input
              className={inputClass}
              value={createDraft.agentIds}
              onChange={(event) => setCreateDraft((current) => ({ ...current, agentIds: event.target.value }))}
              placeholder='UUIDs separated by commas'
              required
            />
          </label>
          <label className='space-y-1.5 text-xs text-slate-400 lg:col-span-2'>
            <span>Description</span>
            <textarea
              className={inputClass}
              value={createDraft.description}
              onChange={(event) => setCreateDraft((current) => ({ ...current, description: event.target.value }))}
              rows={2}
              maxLength={1000}
            />
          </label>
          <div className='grid gap-3 sm:grid-cols-2'>
            <label className='space-y-1.5 text-xs text-slate-400'>
              <span>Minimum replicas</span>
              <input className={inputClass} type='number' min={1} max={10} value={createDraft.minReplicas} onChange={(event) => setCreateDraft((current) => ({ ...current, minReplicas: event.target.value }))} />
            </label>
            <label className='space-y-1.5 text-xs text-slate-400'>
              <span>Maximum replicas</span>
              <input className={inputClass} type='number' min={1} max={50} value={createDraft.maxReplicas} onChange={(event) => setCreateDraft((current) => ({ ...current, maxReplicas: event.target.value }))} />
            </label>
          </div>
          <div className='flex items-end justify-end'>
            <button className={primaryButtonClass} type='submit' disabled={actingId === 'create'}>
              {actingId === 'create' ? 'Creating…' : 'Create swarm'}
            </button>
          </div>
        </form>
      </LivePanel>

      <LivePanel title='Curated blueprints' meta={`${blueprints.length} orchestration presets`}>
        {catalogError ? (
          <div role='alert' className='rounded-xl border border-amber-400/20 bg-amber-400/10 px-4 py-3 text-sm text-amber-100'>
            Blueprint catalog unavailable: {catalogError}. Swarm controls remain available.
          </div>
        ) : blueprints.length === 0 ? (
          <LiveEmptyState title='No blueprints available yet' message='No orchestration presets were returned.' />
        ) : (
          <div className='grid gap-4 xl:grid-cols-2'>
            {blueprints.map((blueprint) => (
              <div key={blueprint.id} className='rounded-2xl border border-white/10 bg-white/[0.03] p-4'>
                <div className='flex flex-wrap items-start justify-between gap-3'>
                  <div className='min-w-0'>
                    <p className='text-base font-semibold text-white'>{blueprint.name}</p>
                    <p className='mt-1 text-sm text-slate-400'>{blueprint.summary}</p>
                  </div>
                  <StatusBadge status='success' label={`${blueprint.recommended_min_agents}-${blueprint.recommended_max_agents} agents`} />
                </div>
                <p className='mt-3 text-sm text-slate-300'>{blueprint.description}</p>
                <div className='mt-4 space-y-2'>
                  {(blueprint.roles ?? []).map((role) => (
                    <div key={`${blueprint.id}-${role.id}`} className='rounded-xl border border-white/10 bg-black/20 px-3 py-2.5'>
                      <div className='flex flex-wrap items-center justify-between gap-2'>
                        <p className='text-sm font-medium text-white'>{role.title}</p>
                        <span className='rounded-full border border-white/10 bg-white/[0.04] px-2 py-0.5 text-[10px] uppercase tracking-[0.18em] text-slate-400'>{role.bundle_id}</span>
                      </div>
                      <p className='mt-1 text-xs text-slate-500'>{role.goal}</p>
                    </div>
                  ))}
                </div>
                <div className='mt-4 flex flex-wrap items-end justify-between gap-3'>
                  <p className='max-w-2xl text-xs text-slate-500'>{blueprint.coordination_notes}</p>
                  <button
                    className={secondaryButtonClass}
                    type='button'
                    onClick={() => setCreateDraft((current) => ({
                      ...current,
                      name: blueprint.name,
                      description: blueprint.description,
                      minReplicas: String(Math.max(1, blueprint.recommended_min_agents)),
                      maxReplicas: String(Math.max(1, blueprint.recommended_max_agents)),
                    }))}
                  >
                    Prefill create form
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </LivePanel>

      <LivePanel
        title='Swarm topology'
        meta={`${swarms.length} of ${total} groups`}
        action={(
          <button className={secondaryButtonClass} onClick={() => void canonicalReload()} disabled={refreshing}>
            {refreshing ? 'Refreshing…' : 'Refresh'}
          </button>
        )}
      >
        {swarms.length === 0 ? (
          <LiveEmptyState title='No swarms configured yet' message='Create a swarm above to coordinate owned agents.' />
        ) : (
          <div className='grid gap-4 xl:grid-cols-2'>
            {swarms.map((swarm) => {
              const acting = actingId === swarm.id
              const fallbackReplicas = swarm.agents[0]?.replicas || swarm.min_replicas
              return (
                <div key={swarm.id} className='rounded-2xl border border-white/10 bg-white/[0.02] p-4'>
                  {editingId === swarm.id && editDraft ? (
                    <form onSubmit={(event) => void updateSwarm(event, swarm)} className='space-y-3'>
                      <input className={inputClass} value={editDraft.name} onChange={(event) => setEditDraft((current) => current ? ({ ...current, name: event.target.value }) : current)} required maxLength={255} />
                      <textarea className={inputClass} value={editDraft.description} onChange={(event) => setEditDraft((current) => current ? ({ ...current, description: event.target.value }) : current)} rows={2} maxLength={1000} />
                      <div className='grid gap-3 sm:grid-cols-2'>
                        <input aria-label='Minimum replicas' className={inputClass} type='number' min={1} max={10} value={editDraft.minReplicas} onChange={(event) => setEditDraft((current) => current ? ({ ...current, minReplicas: event.target.value }) : current)} />
                        <input aria-label='Maximum replicas' className={inputClass} type='number' min={1} max={50} value={editDraft.maxReplicas} onChange={(event) => setEditDraft((current) => current ? ({ ...current, maxReplicas: event.target.value }) : current)} />
                      </div>
                      <div className='flex flex-wrap gap-2'>
                        <button className={primaryButtonClass} type='submit' disabled={acting}>{acting ? 'Saving…' : 'Save changes'}</button>
                        <button className={secondaryButtonClass} type='button' onClick={() => { setEditingId(null); setEditDraft(null) }} disabled={acting}>Cancel</button>
                      </div>
                    </form>
                  ) : (
                    <>
                      <div className='flex flex-wrap items-start justify-between gap-3'>
                        <div className='min-w-0'>
                          <p className='truncate text-base font-semibold text-white'>{swarm.name}</p>
                          <p className='mt-1 text-sm text-slate-400'>{swarm.description || 'Grouped agent coordination surface'}</p>
                        </div>
                        <StatusBadge status={asDashboardStatus(swarm.agents.some((agent) => agent.replicas === 0) ? 'warning' : 'healthy')} label={`${swarm.agents.length} agents`} />
                      </div>

                      <div className='mt-4 grid gap-2 sm:grid-cols-2'>
                        <div className='rounded-xl border border-white/10 bg-black/20 px-3 py-2'>
                          <p className='text-[10px] uppercase tracking-[0.18em] text-slate-500'>Replica guardrail</p>
                          <p className='mt-2 text-sm text-white'>{swarm.min_replicas} min · {swarm.max_replicas} max</p>
                        </div>
                        <div className='rounded-xl border border-white/10 bg-black/20 px-3 py-2'>
                          <p className='text-[10px] uppercase tracking-[0.18em] text-slate-500'>Updated</p>
                          <p className='mt-2 text-sm text-white'>{formatRelativeTime(swarm.updated_at)}</p>
                        </div>
                      </div>

                      <div className='mt-4 space-y-2'>
                        {swarm.agents.map((agent) => (
                          <div key={agent.agent_id} className='flex items-center justify-between gap-3 rounded-xl border border-white/10 bg-black/20 px-3 py-2.5'>
                            <div className='min-w-0'>
                              <p className='truncate text-sm font-medium text-white'>{agent.agent_name}</p>
                              <p className='text-xs text-slate-500'>{agent.agent_id.slice(0, 8)}</p>
                            </div>
                            <div className='flex items-center gap-3'>
                              <span className='text-xs text-slate-400'>{agent.replicas} replicas</span>
                              <StatusBadge status={asDashboardStatus(agent.status)} label={agent.status} />
                            </div>
                          </div>
                        ))}
                      </div>

                      <div className='mt-4 flex flex-wrap items-end gap-2 border-t border-white/10 pt-3'>
                        <label className='space-y-1 text-xs text-slate-500'>
                          <span>Replicas per agent</span>
                          <input
                            aria-label={`Scale ${swarm.name}`}
                            className={`${inputClass} w-28`}
                            type='number'
                            min={swarm.min_replicas}
                            max={swarm.max_replicas}
                            value={scaleTargets[swarm.id] ?? String(fallbackReplicas)}
                            onChange={(event) => setScaleTargets((current) => ({ ...current, [swarm.id]: event.target.value }))}
                          />
                        </label>
                        <button className={primaryButtonClass} type='button' onClick={() => requestScaleSwarm(swarm)} disabled={acting}>Scale</button>
                        <button className={secondaryButtonClass} type='button' onClick={() => beginEdit(swarm)} disabled={acting}>Edit</button>
                        <button className={dangerButtonClass} type='button' onClick={() => requestDeleteSwarm(swarm)} disabled={acting}>{acting ? 'Working…' : 'Delete'}</button>
                      </div>
                    </>
                  )}
                </div>
              )
            })}
          </div>
        )}

        {hasMore ? (
          <div className='mt-4 flex justify-center border-t border-white/10 pt-4'>
            <button className={secondaryButtonClass} onClick={() => void loadMore()} disabled={loadingMore}>
              {loadingMore ? 'Loading…' : `Load more (${swarms.length} of ${total})`}
            </button>
          </div>
        ) : null}
      </LivePanel>
    </div>
  )
}
