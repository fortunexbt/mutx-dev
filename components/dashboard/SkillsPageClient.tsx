'use client'

import { useEffect, useMemo, useState } from 'react'

import { ApiRequestError, readJson } from '@/components/app/http'
import {
  dashboardRequestErrorMessage,
  getDashboardRequestAccessFailure,
} from '@/components/dashboard/dashboardRequestAccess'
import {
  LiveAuthRequired,
  LiveEmptyState,
  LiveErrorState,
  LiveForbidden,
  LiveLoading,
  LivePanel,
} from '@/components/dashboard/livePrimitives'
import { FeatureHint } from '@/components/dashboard/FeatureHint'
import { StatusBadge } from '@/components/dashboard/StatusBadge'

export type SkillLifecycleStatus =
  | 'available'
  | 'configured'
  | 'runtime_ready'
  | 'unavailable'
  | 'failed'

export type SkillRecord = {
  id: string
  name: string
  description: string
  author: string
  category: string
  source: string
  installed?: boolean
  configured?: boolean
  runtime_ready?: boolean
  status?: SkillLifecycleStatus
  reconciliation_required?: boolean
  status_detail?: string
  reconciliation_error?: string | null
  is_official?: boolean
  tags?: string[]
  path?: string | null
  canonical_name?: string | null
  upstream_path?: string | null
  upstream_repo?: string | null
  upstream_commit?: string | null
  license?: string | null
  available?: boolean
}

type BundleRecord = {
  id: string
  name: string
  summary: string
  description: string
  skill_ids: string[]
  skill_count: number
  available_skill_count: number
  unavailable_skill_ids: string[]
  recommended_template_id?: string | null
  recommended_swarm_blueprint_id?: string | null
  tags?: string[]
  source?: string
}

type AssistantOverviewEnvelope = {
  has_assistant: boolean
  assistant?: {
    agent_id: string
    name: string
  } | null
}

type SkillLifecyclePresentation = {
  status: SkillLifecycleStatus
  badgeStatus: 'idle' | 'success' | 'error' | 'warning'
  label: string
  configured: boolean
  runtimeReady: boolean
  detail: string
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

export function skillsFromMutationEnvelope(payload: unknown): SkillRecord[] {
  if (!isRecord(payload) || !Array.isArray(payload.skills)) {
    throw new Error('The control plane did not return the persisted skill state')
  }

  const skills = payload.skills.filter(
    (item): item is SkillRecord => isRecord(item) && typeof item.id === 'string',
  )
  if (skills.length !== payload.skills.length) {
    throw new Error('The control plane returned an invalid skill state')
  }
  return skills
}

export function skillLifecyclePresentation(skill: SkillRecord): SkillLifecyclePresentation {
  const configured = skill.configured === true || skill.installed === true
  const runtimeReady = skill.status === 'runtime_ready' && skill.runtime_ready === true

  if (runtimeReady) {
    return {
      status: 'runtime_ready',
      badgeStatus: 'success',
      label: 'Runtime ready',
      configured: true,
      runtimeReady: true,
      detail:
        skill.status_detail || 'The assistant runtime reported successful skill reconciliation.',
    }
  }
  if (skill.status === 'failed') {
    return {
      status: 'failed',
      badgeStatus: 'error',
      label: 'Failed',
      configured,
      runtimeReady: false,
      detail: skill.reconciliation_error || skill.status_detail || 'Runtime reconciliation failed.',
    }
  }
  if (configured) {
    return {
      status: skill.status === 'unavailable' ? 'unavailable' : 'configured',
      badgeStatus: 'warning',
      label: skill.status === 'unavailable' ? 'Unavailable' : 'Configured',
      configured: true,
      runtimeReady: false,
      detail:
        skill.status_detail ||
        'Saved in the assistant configuration. Runtime reconciliation has not been proven.',
    }
  }
  if (skill.available === false || skill.status === 'unavailable') {
    return {
      status: 'unavailable',
      badgeStatus: 'warning',
      label: 'Unavailable',
      configured: false,
      runtimeReady: false,
      detail: skill.status_detail || 'The skill files are unavailable to this control plane.',
    }
  }
  return {
    status: 'available',
    badgeStatus: 'idle',
    label: 'Available',
    configured: false,
    runtimeReady: false,
    detail: skill.status_detail || 'Available to configure; runtime activation has not been requested.',
  }
}

function mutationEnvelopeDetail(payload: unknown, fallback: string) {
  if (!isRecord(payload)) return fallback
  if (typeof payload.detail === 'string' && payload.detail.trim()) return payload.detail
  if (isRecord(payload.detail) && typeof payload.detail.detail === 'string') {
    return payload.detail.detail
  }
  return fallback
}

function mutationNotice(payload: unknown): string {
  if (!isRecord(payload)) return 'Skill configuration saved.'
  return mutationEnvelopeDetail(payload, `Skill lifecycle status: ${String(payload.status || 'updated')}`)
}

export function SkillsPageClient() {
  const [loading, setLoading] = useState(true)
  const [authRequired, setAuthRequired] = useState(false)
  const [permissionDenied, setPermissionDenied] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [mutationError, setMutationError] = useState<string | null>(null)
  const [mutationStatus, setMutationStatus] = useState<string | null>(null)
  const [catalog, setCatalog] = useState<SkillRecord[]>([])
  const [bundles, setBundles] = useState<BundleRecord[]>([])
  const [assistantId, setAssistantId] = useState<string | null>(null)
  const [assistantName, setAssistantName] = useState<string | null>(null)
  const [assistantSkills, setAssistantSkills] = useState<SkillRecord[]>([])
  const [search, setSearch] = useState('')
  const [busySkillId, setBusySkillId] = useState<string | null>(null)
  const [busyBundleId, setBusyBundleId] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false

    async function load() {
      setLoading(true)
      setLoadError(null)
      setAuthRequired(false)
      setPermissionDenied(false)

      try {
        const [catalogPayload, bundlePayload, overview] = await Promise.all([
          readJson<SkillRecord[]>('/api/dashboard/clawhub/skills'),
          readJson<BundleRecord[]>('/api/dashboard/clawhub/bundles'),
          readJson<AssistantOverviewEnvelope>('/api/dashboard/assistant/overview'),
        ])

        let nextAssistantSkills: SkillRecord[] = []
        let nextAssistantId: string | null = null
        let nextAssistantName: string | null = null

        if (overview.has_assistant && overview.assistant?.agent_id) {
          nextAssistantId = overview.assistant.agent_id
          nextAssistantName = overview.assistant.name || null
          const assistantSkillPayload = await readJson<SkillRecord[]>(
            `/api/dashboard/assistant/${encodeURIComponent(overview.assistant.agent_id)}/skills`,
          )
          nextAssistantSkills = Array.isArray(assistantSkillPayload) ? assistantSkillPayload : []
        }

        if (!cancelled) {
          setCatalog(Array.isArray(catalogPayload) ? catalogPayload : [])
          setBundles(Array.isArray(bundlePayload) ? bundlePayload : [])
          setAssistantId(nextAssistantId)
          setAssistantName(nextAssistantName)
          setAssistantSkills(nextAssistantSkills)
          setLoading(false)
        }
      } catch (loadError) {
        if (!cancelled) {
          const accessFailure = getDashboardRequestAccessFailure(loadError)
          if (accessFailure === 'authentication') {
            setAuthRequired(true)
          } else if (accessFailure === 'permission') {
            setPermissionDenied(true)
          } else {
            setLoadError(dashboardRequestErrorMessage(loadError, 'Failed to load skill catalog'))
          }
          setLoading(false)
        }
      }
    }

    void load()
    return () => {
      cancelled = true
    }
  }, [])

  const assistantSkillById = useMemo(
    () => new Map(assistantSkills.map((skill) => [skill.id, skill])),
    [assistantSkills],
  )

  const filteredSkills = useMemo(() => {
    const needle = search.trim().toLowerCase()
    return catalog.filter((skill) => {
      if (!needle) return true
      return [skill.id, skill.name, skill.description, skill.category, ...(skill.tags || [])]
        .join(' ')
        .toLowerCase()
        .includes(needle)
    })
  }, [catalog, search])

  async function toggleSkill(skill: SkillRecord) {
    if (!assistantId) return
    setBusySkillId(skill.id)
    setMutationError(null)
    setMutationStatus(null)
    try {
      const currentSkill = assistantSkillById.get(skill.id) || skill
      const lifecycle = skillLifecyclePresentation(currentSkill)
      const endpoint = lifecycle.configured
        ? '/api/dashboard/clawhub/uninstall'
        : '/api/dashboard/clawhub/install'
      const response = await fetch(endpoint, {
        method: 'POST',
        credentials: 'include',
        cache: 'no-store',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ agent_id: assistantId, skill_id: skill.id }),
      })
      const payload: unknown = await response.json().catch(() => ({}))
      if (!response.ok) {
        throw new ApiRequestError(
          mutationEnvelopeDetail(payload, 'Failed to update skill configuration'),
          response.status,
        )
      }
      setAssistantSkills(skillsFromMutationEnvelope(payload))
      setMutationStatus(mutationNotice(payload))
    } catch (error) {
      const accessFailure = getDashboardRequestAccessFailure(error)
      if (accessFailure === 'authentication') setAuthRequired(true)
      else if (accessFailure === 'permission') setPermissionDenied(true)
      else setMutationError(dashboardRequestErrorMessage(error, 'Failed to update skill'))
    } finally {
      setBusySkillId(null)
    }
  }

  async function installBundle(bundleId: string) {
    if (!assistantId) return
    setBusyBundleId(bundleId)
    setMutationError(null)
    setMutationStatus(null)
    try {
      const response = await fetch('/api/dashboard/clawhub/install-bundle', {
        method: 'POST',
        credentials: 'include',
        cache: 'no-store',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ agent_id: assistantId, bundle_id: bundleId }),
      })
      const payload: unknown = await response.json().catch(() => ({}))
      if (!response.ok) {
        throw new ApiRequestError(
          mutationEnvelopeDetail(payload, 'Failed to configure skill bundle'),
          response.status,
        )
      }
      setAssistantSkills(skillsFromMutationEnvelope(payload))
      setMutationStatus(mutationNotice(payload))
    } catch (error) {
      const accessFailure = getDashboardRequestAccessFailure(error)
      if (accessFailure === 'authentication') setAuthRequired(true)
      else if (accessFailure === 'permission') setPermissionDenied(true)
      else setMutationError(dashboardRequestErrorMessage(error, 'Failed to configure skill bundle'))
    } finally {
      setBusyBundleId(null)
    }
  }

  if (loading) return <LiveLoading title='Skills' />
  if (authRequired) {
    return (
      <LiveAuthRequired
        title='Operator session required'
        message='Sign in to browse Orchestra Research imports and wire them into a live assistant.'
      />
    )
  }
  if (permissionDenied) {
    return <LiveForbidden title='Skill permission required' message='Your account cannot configure assistant skills. Install and removal controls are unavailable.' />
  }
  if (loadError) return <LiveErrorState title='Skill surface unavailable' message={loadError} />

  return (
    <div className='space-y-4'>
      {mutationError ? (
        <div role='alert' aria-live='assertive' className='rounded-2xl border border-rose-400/30 bg-rose-400/10 px-4 py-3 text-sm text-rose-100'>
          {mutationError}
        </div>
      ) : null}
      {mutationStatus ? (
        <div className='rounded-2xl border border-cyan-400/30 bg-cyan-400/10 px-4 py-3 text-sm text-cyan-100'>
          {mutationStatus}
        </div>
      ) : null}
      <LivePanel
        title='Curated bundles'
        meta={`${bundles.length} packs · ${assistantId ? `bound to ${assistantName || 'assistant'}` : 'no assistant bound'}`}
        action={
          <FeatureHint
            detail='Bundle actions persist assistant configuration. Runtime readiness appears only after explicit reconciliation evidence.'
          />
        }
      >
        {bundles.length === 0 ? (
          <LiveEmptyState
            title='No bundles available'
            message='Bundle catalog will appear here once the control plane exposes imported research stacks.'
          />
        ) : (
          <div className='grid gap-4 xl:grid-cols-2'>
            {bundles.map((bundle) => {
              const unavailable = bundle.unavailable_skill_ids?.length || 0
              return (
                <div key={bundle.id} className='rounded-2xl border border-white/10 bg-white/[0.03] p-4'>
                  <div className='flex flex-wrap items-start justify-between gap-3'>
                    <div className='min-w-0'>
                      <p className='text-base font-semibold text-white'>{bundle.name}</p>
                      <p className='mt-1 text-sm text-slate-400'>{bundle.summary}</p>
                    </div>
                    <StatusBadge
                      status={unavailable > 0 ? 'warning' : 'idle'}
                      label={`${bundle.available_skill_count}/${bundle.skill_count} available`}
                    />
                  </div>
                  <p className='mt-3 text-sm text-slate-300'>{bundle.description}</p>
                  <div className='mt-3 flex flex-wrap gap-2'>
                    {(bundle.tags || []).map((tag) => (
                      <span
                        key={`${bundle.id}-${tag}`}
                        className='rounded-full border border-white/10 bg-white/[0.04] px-2.5 py-1 text-[11px] uppercase tracking-[0.18em] text-slate-400'
                      >
                        {tag}
                      </span>
                    ))}
                  </div>
                  <div className='mt-4 grid gap-2 sm:grid-cols-2'>
                    <div className='rounded-xl border border-white/10 bg-black/20 px-3 py-2'>
                      <p className='text-[10px] uppercase tracking-[0.18em] text-slate-500'>Template</p>
                      <p className='mt-2 text-sm text-white'>
                        {bundle.recommended_template_id || 'Use bundle directly'}
                      </p>
                    </div>
                    <div className='rounded-xl border border-white/10 bg-black/20 px-3 py-2'>
                      <p className='text-[10px] uppercase tracking-[0.18em] text-slate-500'>Swarm blueprint</p>
                      <p className='mt-2 text-sm text-white'>
                        {bundle.recommended_swarm_blueprint_id || 'Single-agent capable'}
                      </p>
                    </div>
                  </div>
                  <div className='mt-4 flex items-center justify-between gap-3'>
                    <p className='text-xs text-slate-500'>
                      {unavailable > 0
                        ? `${unavailable} skill artifacts are unavailable to configure.`
                        : 'All bundle artifacts are available to configure; runtime activation is separate.'}
                    </p>
                    <button
                      type='button'
                      onClick={() => void installBundle(bundle.id)}
                      disabled={!assistantId || busyBundleId === bundle.id}
                      className='rounded-xl border border-cyan-400/40 bg-cyan-400/10 px-3 py-2 text-sm font-medium text-cyan-200 disabled:cursor-not-allowed disabled:opacity-50'
                    >
                      {busyBundleId === bundle.id ? 'Configuring…' : 'Configure bundle'}
                    </button>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </LivePanel>

      <LivePanel
        title='Skill catalog'
        meta={`${filteredSkills.length} visible`}
        action={
          <FeatureHint
            tone='boundary'
            detail='Configured means persisted intent. Runtime ready is reserved for reconciled activation reported by the assistant runtime.'
          />
        }
      >
        <div className='mb-4 flex flex-wrap items-center gap-3'>
          <input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder='Search skills, tags, categories…'
            className='w-full rounded-2xl border border-white/10 bg-black/30 px-4 py-3 text-sm text-white placeholder:text-slate-600 md:max-w-md'
          />
          <div className='rounded-full border border-white/10 bg-white/[0.03] px-3 py-1 text-xs text-slate-400'>
            {assistantId ? `Assistant bound: ${assistantName || assistantId}` : 'No assistant bound'}
          </div>
        </div>

        {filteredSkills.length === 0 ? (
          <LiveEmptyState
            title='No skills matched'
            message='Try a broader search or clear the current filters.'
          />
        ) : (
          <div className='grid gap-3 xl:grid-cols-2'>
            {filteredSkills.map((skill) => {
              const currentSkill = { ...skill, ...assistantSkillById.get(skill.id) }
              const lifecycle = skillLifecyclePresentation(currentSkill)
              const available = currentSkill.available !== false
              return (
                <div key={skill.id} className='rounded-2xl border border-white/10 bg-white/[0.02] p-4'>
                  <div className='flex flex-wrap items-start justify-between gap-3'>
                    <div className='min-w-0'>
                      <div className='flex flex-wrap items-center gap-2'>
                        <p className='text-base font-semibold text-white'>{skill.name}</p>
                        <span className='rounded-full border border-white/10 bg-white/[0.04] px-2 py-0.5 text-[10px] uppercase tracking-[0.18em] text-slate-400'>
                          {skill.category}
                        </span>
                      </div>
                      <p className='mt-1 text-sm text-slate-400'>{skill.description}</p>
                    </div>
                    <StatusBadge
                      status={lifecycle.badgeStatus}
                      label={lifecycle.label}
                    />
                  </div>

                  <div className='mt-3 flex flex-wrap gap-2'>
                    {(skill.tags || []).slice(0, 5).map((tag) => (
                      <span
                        key={`${skill.id}-${tag}`}
                        className='rounded-full border border-white/10 bg-black/20 px-2.5 py-1 text-[11px] uppercase tracking-[0.16em] text-slate-500'
                      >
                        {tag}
                      </span>
                    ))}
                  </div>

                  <div className='mt-4 grid gap-2 sm:grid-cols-2'>
                    <div className='rounded-xl border border-white/10 bg-black/20 px-3 py-2'>
                      <p className='text-[10px] uppercase tracking-[0.18em] text-slate-500'>Source</p>
                      <p className='mt-2 text-sm text-white'>{skill.source}</p>
                    </div>
                    <div className='rounded-xl border border-white/10 bg-black/20 px-3 py-2'>
                      <p className='text-[10px] uppercase tracking-[0.18em] text-slate-500'>Runtime path</p>
                      <p className='mt-2 truncate text-sm text-white'>
                        {skill.path || 'Artifact path not reported'}
                      </p>
                    </div>
                  </div>

                  <p className='mt-3 text-xs text-slate-400'>{lifecycle.detail}</p>

                  <div className='mt-4 flex items-end justify-between gap-3'>
                    <div>
                      <p className='text-xs text-slate-500'>
                        {skill.upstream_commit
                          ? `Pinned upstream commit ${skill.upstream_commit.slice(0, 7)} · ${skill.license || 'license unknown'}`
                          : skill.author}
                      </p>
                      {lifecycle.configured && !lifecycle.runtimeReady ? (
                        <p className='mt-1 text-[11px] text-amber-200/80'>
                          Reconciliation required before runtime use can be claimed.
                        </p>
                      ) : null}
                    </div>
                    <button
                      type='button'
                      onClick={() => void toggleSkill(skill)}
                      disabled={
                        !assistantId ||
                        (!available && !lifecycle.configured) ||
                        busySkillId === skill.id
                      }
                      className='rounded-xl border border-white/10 bg-white/[0.05] px-3 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-50'
                    >
                      {busySkillId === skill.id
                        ? 'Saving…'
                        : lifecycle.configured
                          ? 'Remove config'
                          : 'Configure'}
                    </button>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </LivePanel>
    </div>
  )
}
