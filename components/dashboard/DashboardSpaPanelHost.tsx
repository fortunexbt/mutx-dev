'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import {
  Activity,
  ArrowRight,
  Check,
  ChevronRight,
  Gauge,
  Loader2,
  MessageSquare,
  PanelRight,
  ShieldCheck,
  TriangleAlert,
  X,
} from 'lucide-react'

import { ErrorBoundary } from '@/components/app/ErrorBoundary'
import {
  DashboardContentRouter,
  hasFullModeAccess,
} from '@/components/dashboard/DashboardContentRouter'
import { DashboardDialog } from '@/components/dashboard/DashboardDialog'
import {
  type BootStatus,
  type BootStep,
  type BootStepKey,
  createInitialBootSteps,
  extractCollection,
  isRecord,
  loadMemoryWarmup,
  probeControlPlane,
  readDashboardJson,
  summarizeBoot,
} from '@/components/dashboard/dashboardSpaBoot'
import { useDesktopStatus } from '@/components/desktop/useDesktopStatus'
import { isEssentialPanel, resolveDashboardPanel } from '@/lib/dashboardPanels'
import { useDashboardPathname, useNavigateToPanel } from '@/lib/navigation'
import { type Agent, type Session, useMissionControl } from '@/lib/store'
import { cn } from '@/lib/utils'

type StepResult = {
  detail: string
  status?: Extract<BootStatus, 'complete' | 'warning'>
}

function getBootTone(status: BootStatus) {
  if (status === 'complete') {
    return 'border-emerald-400/30 bg-emerald-400/10 text-emerald-100'
  }
  if (status === 'warning') {
    return 'border-amber-400/30 bg-amber-400/10 text-amber-100'
  }
  if (status === 'error') {
    return 'border-rose-400/30 bg-rose-400/10 text-rose-100'
  }
  if (status === 'running') {
    return 'border-sky-400/30 bg-sky-400/10 text-sky-100'
  }
  return 'border-white/10 bg-white/[0.03] text-slate-300'
}

const BOOT_STATUS_LABELS: Record<BootStatus, string> = {
  pending: 'Queued',
  running: 'Checking',
  complete: 'Verified',
  warning: 'Partial',
  error: 'Failed',
}

function BootStatusIcon({ status }: { status: BootStatus }) {
  if (status === 'running') {
    return <Loader2 className='h-3.5 w-3.5 animate-spin motion-reduce:animate-none' aria-hidden='true' />
  }
  if (status === 'complete') {
    return <Check className='h-3.5 w-3.5' aria-hidden='true' />
  }
  if (status === 'warning') {
    return <TriangleAlert className='h-3.5 w-3.5' aria-hidden='true' />
  }
  if (status === 'error') {
    return <X className='h-3.5 w-3.5' aria-hidden='true' />
  }
  return null
}

function BootLedger({
  steps,
  compact = false,
  announce = true,
}: {
  steps: BootStep[]
  compact?: boolean
  announce?: boolean
}) {
  const outcome = summarizeBoot(steps)

  return (
    <div
      role={announce ? 'status' : undefined}
      aria-live={announce ? 'polite' : undefined}
      aria-atomic='false'
      aria-busy={announce ? outcome.phase === 'running' : undefined}
    >
      <ol className={cn('space-y-2', compact ? 'text-xs' : 'text-sm')} aria-label='Startup checks'>
        {steps.map((step, index) => (
          <li
            key={step.key}
            className={cn(
              'rounded-[5px] border px-3 py-3',
              compact ? 'space-y-1.5' : 'space-y-2',
              getBootTone(step.status),
            )}
          >
            <div className='flex items-center justify-between gap-3'>
              <div className='flex min-w-0 items-center gap-2'>
                <span
                  className='font-[family:var(--font-mono)] text-[10px] uppercase tracking-[0.18em] opacity-70'
                  aria-hidden='true'
                >
                  {String(index + 1).padStart(2, '0')}
                </span>
                <span className='truncate font-medium'>{step.label}</span>
              </div>
              <span className='flex shrink-0 items-center gap-1.5 font-[family:var(--font-mono)] text-[10px] uppercase tracking-[0.12em]'>
                <BootStatusIcon status={step.status} />
                {BOOT_STATUS_LABELS[step.status]}
              </span>
            </div>
            <p className='leading-5 text-slate-300/90'>{step.detail}</p>
          </li>
        ))}
      </ol>
    </div>
  )
}

function PanelErrorFallback({ panelLabel }: { panelLabel: string }) {
  return (
    <div
      role='alert'
      className='rounded-[6px] border border-rose-400/30 bg-[rgba(69,29,24,0.44)] p-6 text-rose-100'
    >
      <p className='font-[family:var(--font-mono)] text-[10px] font-semibold uppercase tracking-[0.18em] text-rose-200'>
        Surface unavailable
      </p>
      <h2 className='mt-3 font-[family:var(--font-site-display)] text-[1.6rem] tracking-[-0.05em]'>
        {panelLabel} could not be displayed
      </h2>
      <p className='mt-3 max-w-2xl text-sm leading-6 text-rose-100/80'>
        The rest of your workspace is still available. Refresh this surface or move to another
        operator view while the issue is investigated.
      </p>
    </div>
  )
}

export function DashboardSpaPanelHost() {
  const { isDesktop } = useDesktopStatus()
  const pathname = useDashboardPathname(true)
  const navigateToPanel = useNavigateToPanel()
  const panel = resolveDashboardPanel(pathname)
  const bootStartedRef = useRef(false)
  const desktopRuntimeActive =
    typeof window !== 'undefined' ? Boolean(window.mutxDesktop?.isDesktop) : false

  const [
    connection,
    currentUser,
    interfaceMode,
    subscription,
    agents,
    sessions,
    monitoringAlerts,
    liveFeedOpen,
    chatPanelOpen,
    updateAvailable,
    bannerDismissed,
    setActiveTab,
    setBootComplete,
    setCapabilitiesChecked,
    setDashboardMode,
    setInterfaceMode,
    setSubscription,
    setConnection,
    setAgents,
    setSessions,
    toggleLiveFeed,
    setChatPanelOpen,
    dismissBanner,
  ] = useMissionControl((state) => [
    state.connection,
    state.currentUser,
    state.interfaceMode,
    state.subscription,
    state.agents,
    state.sessions,
    state.monitoringAlerts,
    state.liveFeedOpen,
    state.chatPanelOpen,
    state.updateAvailable,
    state.bannerDismissed,
    state.setActiveTab,
    state.setBootComplete,
    state.setCapabilitiesChecked,
    state.setDashboardMode,
    state.setInterfaceMode,
    state.setSubscription,
    state.setConnection,
    state.setAgents,
    state.setSessions,
    state.toggleLiveFeed,
    state.setChatPanelOpen,
    state.dismissBanner,
  ])

  const [orgName, setOrgName] = useState('MUTX')
  const [bootVisible, setBootVisible] = useState(true)
  const [bootSteps, setBootSteps] = useState<BootStep[]>(createInitialBootSteps)

  useEffect(() => {
    setActiveTab(panel)
  }, [panel, setActiveTab])

  useEffect(() => {
    if (isDesktop || bootStartedRef.current) return

    bootStartedRef.current = true
    let active = true
    let nextSteps = createInitialBootSteps()
    setBootSteps(nextSteps)
    setBootComplete(false)
    setCapabilitiesChecked(false)
    setInterfaceMode('essential')
    setSubscription(null)
    setConnection({
      isConnected: false,
      lastConnected: undefined,
      latency: undefined,
      reconnectAttempts: 0,
      sseConnected: false,
      url: window.location.origin,
    })

    const updateStep = (key: BootStepKey, status: BootStatus, detail?: string) => {
      nextSteps = nextSteps.map((step) =>
        step.key === key ? { ...step, status, detail: detail || step.detail } : step,
      )
      if (active) setBootSteps(nextSteps)
    }

    const runStep = async (key: BootStepKey, task: () => Promise<StepResult>) => {
      updateStep(key, 'running')
      try {
        const result = await task()
        updateStep(key, result.status || 'complete', result.detail)
      } catch (error) {
        updateStep(
          key,
          'error',
          error instanceof Error ? error.message : 'No usable response was returned.',
        )
      }
    }

    const runBoot = async () => {
      updateStep('capabilities', 'running')
      const nextDashboardMode = window.mutxDesktop?.isDesktop ? 'local' : 'gateway'
      setDashboardMode(nextDashboardMode)
      setCapabilitiesChecked(true)
      updateStep(
        'capabilities',
        'complete',
        nextDashboardMode === 'local'
          ? 'Desktop runtime confirmed.'
          : 'Secure browser gateway confirmed.',
      )

      if (!currentUser) {
        updateStep('auth', 'error', 'Operator session is not available.')
        for (const key of ['config', 'connect', 'agents', 'sessions', 'projects', 'memory', 'skills'] as const) {
          updateStep(key, 'warning', 'Skipped because operator access was not verified.')
        }
        setBootComplete(false)
        return
      }

      updateStep('auth', 'complete', `Verified ${currentUser.display_name}.`)

      await Promise.all([
        runStep('config', async () => {
          try {
            const payload = await readDashboardJson(
              '/api/dashboard/settings',
              'Workspace settings could not be loaded.',
            )
            if (!isRecord(payload)) throw new Error('Workspace settings returned an invalid response.')

            const configMode = payload.interfaceMode
            const configSubscription = payload.subscription
            if (configMode !== 'essential' && configMode !== 'full') {
              throw new Error('Workspace settings did not include a valid interface mode.')
            }
            if (
              configSubscription !== null &&
              configSubscription !== 'free' &&
              configSubscription !== 'pro' &&
              configSubscription !== 'enterprise'
            ) {
              throw new Error('Workspace settings did not include a valid subscription.')
            }

            setInterfaceMode(configMode)
            setSubscription(configSubscription)
            setOrgName(
              typeof payload.orgName === 'string' && payload.orgName.trim()
                ? payload.orgName.trim()
                : 'MUTX',
            )
            return {
              detail: configSubscription
                ? `${configMode === 'essential' ? 'Essential' : 'Full'} access · ${configSubscription} plan.`
                : 'Essential access · subscription could not be verified.',
              status: configSubscription ? 'complete' : 'warning',
            }
          } catch (error) {
            setInterfaceMode('essential')
            setSubscription(null)
            throw error
          }
        }),
        runStep('connect', async () => {
          try {
            const evidence = await probeControlPlane()
            setConnection({
              isConnected: true,
              lastConnected: new Date().toISOString(),
              latency: evidence.latency,
              reconnectAttempts: 0,
              sseConnected: false,
              url: window.location.origin,
            })
            return {
              detail: `Healthy control plane · database ready · ${evidence.latency} ms.`,
            }
          } catch (error) {
            setConnection({
              isConnected: false,
              lastConnected: undefined,
              latency: undefined,
              reconnectAttempts: 1,
              sseConnected: false,
              url: window.location.origin,
            })
            throw error
          }
        }),
      ])

      await Promise.all([
        runStep('agents', async () => {
          const payload = await readDashboardJson(
            '/api/dashboard/agents',
            'Agent registry could not be read.',
          )
          const items = extractCollection(payload, ['agents', 'items', 'data']) as Agent[]
          setAgents(items)
          return { detail: `${items.length} agent${items.length === 1 ? '' : 's'} available.` }
        }),
        runStep('sessions', async () => {
          const payload = await readDashboardJson(
            '/api/dashboard/sessions',
            'Session presence could not be read.',
          )
          const items = extractCollection(payload, ['sessions', 'items', 'data']) as Session[]
          setSessions(items)
          return { detail: `${items.length} session${items.length === 1 ? '' : 's'} present.` }
        }),
        runStep('projects', async () => {
          const payload = await readDashboardJson(
            '/api/dashboard/templates',
            'Template inventory could not be read.',
          )
          const items = extractCollection(payload, ['templates', 'items', 'data'])
          return { detail: `${items.length} template${items.length === 1 ? '' : 's'} available.` }
        }),
        runStep('memory', async () => {
          const evidence = await loadMemoryWarmup()
          return { detail: evidence.detail, status: evidence.status }
        }),
        runStep('skills', async () => {
          const payload = await readDashboardJson(
            '/api/dashboard/clawhub/skills',
            'Skill catalog could not be read.',
          )
          const items = extractCollection(payload, ['skills', 'items', 'data'])
          return { detail: `${items.length} skill${items.length === 1 ? '' : 's'} available.` }
        }),
      ])

      if (!active) return

      const outcome = summarizeBoot(nextSteps)
      setBootComplete(outcome.fullyReady)
      if (outcome.fullyReady) setBootVisible(false)
    }

    void runBoot()

    return () => {
      active = false
    }
  }, [
    currentUser,
    isDesktop,
    setAgents,
    setBootComplete,
    setCapabilitiesChecked,
    setConnection,
    setDashboardMode,
    setInterfaceMode,
    setSessions,
    setSubscription,
  ])

  const bootOutcome = useMemo(() => summarizeBoot(bootSteps), [bootSteps])
  const connectStep = bootSteps.find((step) => step.key === 'connect')
  const panelLabel = useMemo(
    () => panel.replace(/-/g, ' ').replace(/\b\w/g, (char) => char.toUpperCase()),
    [panel],
  )
  const bootTitle =
    bootOutcome.phase === 'ready'
      ? 'Workspace verified'
      : bootOutcome.phase === 'degraded'
        ? 'Workspace opened with issues'
        : 'Verifying your workspace'
  const bootDescription =
    bootOutcome.phase === 'ready'
      ? 'Every startup check returned usable evidence.'
      : bootOutcome.phase === 'degraded'
        ? `${bootOutcome.errors + bootOutcome.warnings} startup ${bootOutcome.errors + bootOutcome.warnings === 1 ? 'check needs' : 'checks need'} attention. Available surfaces remain usable.`
        : 'Checking your operator session, control plane, and live workspace inventory.'

  if (isDesktop) return null

  return (
    <div className='space-y-4'>
      {updateAvailable && !bannerDismissed ? (
        <div
          role='status'
          className='rounded-[6px] border border-sky-400/30 bg-sky-400/10 px-4 py-3 text-sm text-sky-50'
        >
          <div className='flex flex-wrap items-center justify-between gap-3'>
            <div>
              <p className='font-[family:var(--font-mono)] text-[10px] font-semibold uppercase tracking-[0.18em] text-sky-100'>
                Update ready
              </p>
              <p className='mt-1 text-sm text-sky-50/85'>
                MUTX {updateAvailable} is available for this workspace.
              </p>
            </div>
            <button
              type='button'
              onClick={dismissBanner}
              className='min-h-11 rounded-[4px] border border-sky-200/20 bg-[#11120f] px-3 text-xs font-medium text-sky-100 transition-colors hover:border-sky-200/40 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-300 motion-reduce:transition-none'
              aria-label={`Dismiss MUTX ${updateAvailable} update notice`}
            >
              Dismiss
            </button>
          </div>
        </div>
      ) : null}

      <section
        aria-labelledby='operator-workspace-title'
        className='rounded-[6px] border border-[#34342e] bg-[linear-gradient(180deg,#151612_0%,#0d0e0c_100%)] px-4 py-4 shadow-[0_1px_0_rgba(255,255,255,0.025)]'
      >
        <div className='flex flex-wrap items-start justify-between gap-5'>
          <div className='max-w-3xl space-y-3'>
            <div className='flex flex-wrap items-center gap-2 font-[family:var(--font-mono)] text-[10px] font-semibold uppercase tracking-[0.16em] text-[#aaa397]'>
              <span
                className={cn(
                  'inline-flex items-center gap-1.5 rounded-[3px] border px-2.5 py-1',
                  connectStep?.status === 'complete'
                    ? 'border-emerald-400/30 bg-emerald-400/10 text-emerald-200'
                    : connectStep?.status === 'error'
                      ? 'border-rose-400/30 bg-rose-400/10 text-rose-200'
                      : 'border-sky-400/30 bg-sky-400/10 text-sky-200',
                )}
              >
                <span className='h-1.5 w-1.5 rounded-full bg-current' aria-hidden='true' />
                {connectStep?.status === 'complete'
                  ? 'Control plane verified'
                  : connectStep?.status === 'error'
                    ? 'Control plane unavailable'
                    : 'Control plane checking'}
              </span>
              <span>{orgName}</span>
              <span aria-hidden='true'>/</span>
              <span>{interfaceMode} view</span>
            </div>
            <div>
              <h2
                id='operator-workspace-title'
                className='font-[family:var(--font-site-display)] text-[1.7rem] leading-[1.02] tracking-[-0.055em] text-[#eee9dc]'
              >
                Operate the live system from one workspace
              </h2>
              <p className='mt-2 max-w-3xl text-sm leading-6 text-[#aaa397]'>
                Move between fleet, session, memory, and governance views while startup evidence and
                degraded dependencies remain visible.
              </p>
            </div>
          </div>

          <div className='flex flex-wrap items-center gap-2'>
            <button
              type='button'
              onClick={toggleLiveFeed}
              className='inline-flex min-h-11 items-center gap-2 rounded-[4px] border border-[#3b3a33] bg-[#0c0d0b] px-3 text-xs font-medium text-[#d6d0c3] transition-colors hover:border-[#59564d] hover:text-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#ff7847] motion-reduce:transition-none'
              aria-expanded={liveFeedOpen}
              aria-controls='dashboard-readiness-panel'
            >
              <PanelRight className='h-4 w-4 text-[#58aaff]' aria-hidden='true' />
              {liveFeedOpen ? 'Hide readiness' : 'Show readiness'}
            </button>
            <button
              type='button'
              onClick={() => setChatPanelOpen(!chatPanelOpen)}
              className='inline-flex min-h-11 items-center gap-2 rounded-[4px] border border-[#3b3a33] bg-[#0c0d0b] px-3 text-xs font-medium text-[#d6d0c3] transition-colors hover:border-[#59564d] hover:text-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#ff7847] motion-reduce:transition-none'
              aria-expanded={chatPanelOpen}
              aria-haspopup='dialog'
            >
              <MessageSquare className='h-4 w-4 text-[#58aaff]' aria-hidden='true' />
              {chatPanelOpen ? 'Close session tools' : 'Open session tools'}
            </button>
            <div
              role='group'
              aria-label='Workspace interface mode'
              className='inline-flex items-center gap-1 rounded-[4px] border border-[#3b3a33] bg-[#0c0d0b] p-1 text-xs'
            >
              <button
                type='button'
                onClick={() => setInterfaceMode('essential')}
                aria-pressed={interfaceMode === 'essential'}
                className={cn(
                  'min-h-9 rounded-[3px] px-3 transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#ff7847] motion-reduce:transition-none',
                  interfaceMode === 'essential'
                    ? 'bg-[#eee9dc] text-[#090a08]'
                    : 'text-[#aaa397] hover:text-[#eee9dc]',
                )}
              >
                Essential
              </button>
              <button
                type='button'
                onClick={() => {
                  if (hasFullModeAccess(subscription)) setInterfaceMode('full')
                }}
                disabled={!hasFullModeAccess(subscription)}
                aria-pressed={interfaceMode === 'full'}
                className={cn(
                  'min-h-9 rounded-[3px] px-3 transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#ff7847] disabled:cursor-not-allowed disabled:opacity-40 motion-reduce:transition-none',
                  interfaceMode === 'full'
                    ? 'bg-[#ff571c] text-[#090a08]'
                    : 'text-[#aaa397] hover:text-[#eee9dc]',
                )}
              >
                Full
              </button>
            </div>
          </div>
        </div>

        <div className='mt-4 flex flex-wrap items-center gap-2 font-[family:var(--font-mono)] text-[10px] uppercase tracking-[0.12em] text-[#918b80]'>
          <span className='rounded-[3px] border border-[#34342e] bg-[#0c0d0b] px-2.5 py-1'>
            {currentUser?.display_name || 'Operator unverified'}
          </span>
          <span className='rounded-[3px] border border-[#34342e] bg-[#0c0d0b] px-2.5 py-1'>
            {subscription || 'Plan pending'}
          </span>
          <span className='rounded-[3px] border border-[#34342e] bg-[#0c0d0b] px-2.5 py-1'>
            {isEssentialPanel(panel) ? 'Essential surface' : 'Full surface'}
          </span>
        </div>
      </section>

      <div className='grid gap-4 xl:grid-cols-[minmax(0,1fr)_320px]'>
        <div className='min-w-0 space-y-4'>
          <ErrorBoundary key={panel} fallback={<PanelErrorFallback panelLabel={panelLabel} />}>
            <DashboardContentRouter
              panel={panel}
              interfaceMode={interfaceMode}
              subscription={subscription}
            />
          </ErrorBoundary>
        </div>

        <aside
          id='dashboard-readiness-panel'
          hidden={!liveFeedOpen}
          aria-label='Workspace readiness'
          className='space-y-4'
        >
          <section className='rounded-[6px] border border-[#34342e] bg-[linear-gradient(180deg,#151612_0%,#0d0e0c_100%)] p-4'>
            <div className='flex items-start justify-between gap-3'>
              <div>
                <p className='font-[family:var(--font-mono)] text-[10px] font-semibold uppercase tracking-[0.18em] text-[#ff8355]'>
                  Readiness
                </p>
                <p className='mt-2 text-sm leading-5 text-[#aaa397]'>
                  Evidence collected during this browser startup.
                </p>
              </div>
              <span className='rounded-[3px] border border-[#34342e] bg-[#0c0d0b] px-2.5 py-1 font-[family:var(--font-mono)] text-[10px] uppercase tracking-[0.12em] text-[#d6d0c3]'>
                {panelLabel}
              </span>
            </div>

            <div className='mt-4 grid gap-3'>
              <div className='rounded-[5px] border border-[#34342e] bg-[#0c0d0b] p-3'>
                <div className='flex items-center gap-2 font-[family:var(--font-mono)] text-[10px] font-semibold uppercase tracking-[0.14em] text-[#918b80]'>
                  <Gauge className='h-3.5 w-3.5 text-[#58aaff]' aria-hidden='true' />
                  Connection evidence
                </div>
                <dl className='mt-3 space-y-2 text-sm text-[#d6d0c3]'>
                  <div className='flex items-center justify-between gap-3'>
                    <dt>Control plane</dt>
                    <dd className={connection.isConnected ? 'text-emerald-300' : 'text-[#918b80]'}>
                      {connection.isConnected ? 'Verified' : 'Unverified'}
                    </dd>
                  </div>
                  <div className='flex items-center justify-between gap-3'>
                    <dt>Latency</dt>
                    <dd className='text-[#918b80]'>
                      {connection.isConnected && connection.latency !== undefined
                        ? `${connection.latency} ms`
                        : '—'}
                    </dd>
                  </div>
                  <div className='flex items-center justify-between gap-3'>
                    <dt>Runtime</dt>
                    <dd className='text-[#918b80]'>
                      {desktopRuntimeActive ? 'Desktop' : 'Browser gateway'}
                    </dd>
                  </div>
                </dl>
              </div>

              <div className='rounded-[5px] border border-[#34342e] bg-[#0c0d0b] p-3'>
                <div className='flex items-center gap-2 font-[family:var(--font-mono)] text-[10px] font-semibold uppercase tracking-[0.14em] text-[#918b80]'>
                  <Activity className='h-3.5 w-3.5 text-[#58aaff]' aria-hidden='true' />
                  Current inventory
                </div>
                <dl className='mt-3 space-y-2 text-sm text-[#d6d0c3]'>
                  <div className='flex items-center justify-between gap-3'>
                    <dt>Agents</dt>
                    <dd className='text-[#918b80]'>{agents.length}</dd>
                  </div>
                  <div className='flex items-center justify-between gap-3'>
                    <dt>Sessions</dt>
                    <dd className='text-[#918b80]'>{sessions.length}</dd>
                  </div>
                  <div className='flex items-center justify-between gap-3'>
                    <dt>Open alerts</dt>
                    <dd className='text-[#918b80]'>{monitoringAlerts.length}</dd>
                  </div>
                </dl>
              </div>

              <div className='rounded-[5px] border border-[#34342e] bg-[#0c0d0b] p-3'>
                <div className='flex items-center gap-2 font-[family:var(--font-mono)] text-[10px] font-semibold uppercase tracking-[0.14em] text-[#918b80]'>
                  <ShieldCheck className='h-3.5 w-3.5 text-[#4bd69b]' aria-hidden='true' />
                  Startup ledger
                </div>
                <div className='mt-3'>
                  <BootLedger steps={bootSteps} compact announce={!bootVisible} />
                </div>
              </div>
            </div>
          </section>
        </aside>
      </div>

      <DashboardDialog
        open={chatPanelOpen}
        onOpenChange={setChatPanelOpen}
        title='Session tools'
        description='Review current session presence or move into the full session workspace.'
        className='max-w-xl'
        footer={
          <button
            data-autofocus
            type='button'
            onClick={() => {
              setChatPanelOpen(false)
              navigateToPanel('chat')
            }}
            className='inline-flex min-h-11 items-center gap-2 rounded-[4px] border border-[#ff6a32] bg-[#ff571c] px-4 text-sm font-semibold text-[#090a08] transition-colors hover:bg-[#ff7545] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#ff9a72] motion-reduce:transition-none'
          >
            Open sessions
            <ArrowRight className='h-4 w-4' aria-hidden='true' />
          </button>
        }
      >
        <div className='space-y-4'>
          <div className='grid gap-3 sm:grid-cols-2'>
            <div className='rounded-[5px] border border-[#34342e] bg-[#0c0d0b] p-4'>
              <p className='font-[family:var(--font-mono)] text-[10px] font-semibold uppercase tracking-[0.14em] text-[#918b80]'>
                Sessions present
              </p>
              <p className='mt-3 text-2xl font-semibold text-[#eee9dc]'>{sessions.length}</p>
            </div>
            <div className='rounded-[5px] border border-[#34342e] bg-[#0c0d0b] p-4'>
              <p className='font-[family:var(--font-mono)] text-[10px] font-semibold uppercase tracking-[0.14em] text-[#918b80]'>
                Access
              </p>
              <p className='mt-3 text-sm leading-6 text-[#d6d0c3]'>
                Session tools remain available in both Essential and Full views.
              </p>
            </div>
          </div>
          <p className='text-sm leading-6 text-[#aaa397]'>
            Open the session workspace to inspect activity, ownership, and execution context without
            losing your current operator state.
          </p>
        </div>
      </DashboardDialog>

      <DashboardDialog
        open={bootVisible}
        onOpenChange={setBootVisible}
        title={bootTitle}
        description={bootDescription}
        className='max-w-3xl'
        footer={
          <button
            data-autofocus
            type='button'
            onClick={() => setBootVisible(false)}
            className='inline-flex min-h-11 items-center gap-2 rounded-[4px] border border-[#3b3a33] bg-[#0c0d0b] px-4 text-sm font-medium text-[#eee9dc] transition-colors hover:border-[#59564d] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#ff7847] motion-reduce:transition-none'
          >
            {bootOutcome.phase === 'running'
              ? 'Continue while checks run'
              : bootOutcome.phase === 'degraded'
                ? 'Continue with available data'
                : 'Enter workspace'}
            <ChevronRight className='h-4 w-4 text-[#58aaff]' aria-hidden='true' />
          </button>
        }
      >
        <div className='space-y-6'>
          <div className='flex flex-wrap items-center justify-between gap-3'>
            <div>
              <p className='font-[family:var(--font-mono)] text-[10px] font-semibold uppercase tracking-[0.18em] text-[#ff8355]'>
                Startup evidence
              </p>
              <p className='mt-2 text-sm text-[#aaa397]'>
                {bootOutcome.settled} of {bootSteps.length} checks settled
                {bootOutcome.errors ? ` · ${bootOutcome.errors} failed` : ''}
                {bootOutcome.warnings ? ` · ${bootOutcome.warnings} partial` : ''}
              </p>
            </div>
            <span
              className={cn(
                'rounded-[3px] border px-2.5 py-1 font-[family:var(--font-mono)] text-[10px] uppercase tracking-[0.14em]',
                bootOutcome.phase === 'ready'
                  ? 'border-emerald-400/30 bg-emerald-400/10 text-emerald-200'
                  : bootOutcome.phase === 'degraded'
                    ? 'border-amber-400/30 bg-amber-400/10 text-amber-200'
                    : 'border-sky-400/30 bg-sky-400/10 text-sky-200',
              )}
            >
              {bootOutcome.phase === 'ready'
                ? 'Verified'
                : bootOutcome.phase === 'degraded'
                  ? 'Attention needed'
                  : 'Checking'}
            </span>
          </div>

          <div
            role='progressbar'
            aria-label='Startup checks settled'
            aria-valuemin={0}
            aria-valuemax={bootSteps.length}
            aria-valuenow={bootOutcome.settled}
            className='rounded-full border border-[#34342e] bg-[#0c0d0b] p-1'
          >
            <div
              className={cn(
                'h-2 rounded-full transition-[width] duration-200 motion-reduce:transition-none',
                bootOutcome.phase === 'degraded'
                  ? 'bg-amber-400'
                  : 'bg-[linear-gradient(90deg,#ff571c_0%,#58aaff_100%)]',
              )}
              style={{ width: `${(bootOutcome.settled / bootSteps.length) * 100}%` }}
            />
          </div>

          <BootLedger steps={bootSteps} />
        </div>
      </DashboardDialog>
    </div>
  )
}
