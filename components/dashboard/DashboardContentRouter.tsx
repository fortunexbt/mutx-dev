'use client'

import type { ReactNode } from 'react'
import dynamic from 'next/dynamic'
import {
  Activity,
  ArrowUpRight,
  BarChart3,
  BellRing,
  Bot,
  Brain,
  ClipboardCheck,
  FileText,
  Gavel,
  GitBranchPlus,
  History,
  Key,
  LayoutGrid,
  LockKeyhole,
  Network,
  Radar,
  ShieldCheck,
  TerminalSquare,
  Users,
  Wallet,
  Webhook,
  Workflow,
} from 'lucide-react'

import { LoadingState } from '@/components/dashboard/LoadingState'
import { RouteHeader } from '@/components/dashboard/RouteHeader'
import { type InterfaceMode, useMissionControl } from '@/lib/store'
import {
  type DashboardPanelId,
  isPanelAccessibleInMode,
} from '@/lib/dashboardPanels'

export type DashboardSubscription = 'free' | 'pro' | 'enterprise' | null

export function hasFullModeAccess(
  subscription: DashboardSubscription,
): subscription is 'pro' | 'enterprise' {
  return subscription === 'pro' || subscription === 'enterprise'
}

const AgentsPageClient = dynamic(
  () => import('@/components/app/AgentsPageClient').then((mod) => mod.AgentsPageClient),
  { loading: () => <LoadingState variant='cards' count={3} /> },
)
const DeploymentsPageClient = dynamic(
  () => import('@/components/app/DeploymentsPageClient').then((mod) => mod.DeploymentsPageClient),
  { loading: () => <LoadingState variant='cards' count={3} /> },
)
const AnalyticsPageClient = dynamic(
  () => import('@/components/dashboard/AnalyticsPageClient').then((mod) => mod.AnalyticsPageClient),
  { loading: () => <LoadingState variant='cards' count={3} /> },
)
const ApiKeysPageClient = dynamic(
  () => import('@/components/dashboard/ApiKeysPageClient').then((mod) => mod.ApiKeysPageClient),
  { loading: () => <LoadingState variant='cards' count={3} /> },
)
const ApprovalsPageClient = dynamic(
  () => import('@/components/dashboard/ApprovalsPageClient').then((mod) => mod.ApprovalsPageClient),
  { loading: () => <LoadingState variant='rows' count={5} /> },
)
const AuditPageClient = dynamic(
  () => import('@/components/dashboard/AuditPageClient').then((mod) => mod.AuditPageClient),
  { loading: () => <LoadingState variant='rows' count={5} /> },
)
const AutonomyPageClient = dynamic(
  () => import('@/components/dashboard/AutonomyPageClient').then((mod) => mod.AutonomyPageClient),
  { loading: () => <LoadingState variant='cards' count={3} /> },
)
const BudgetsPageClient = dynamic(
  () => import('@/components/dashboard/BudgetsPageClient').then((mod) => mod.BudgetsPageClient),
  { loading: () => <LoadingState variant='cards' count={3} /> },
)
const ChannelsPageClient = dynamic(
  () => import('@/components/dashboard/ChannelsPageClient').then((mod) => mod.ChannelsPageClient),
  { loading: () => <LoadingState variant='cards' count={3} /> },
)
const DocumentsPageClient = dynamic(
  () => import('@/components/dashboard/DocumentsPageClient').then((mod) => mod.DocumentsPageClient),
  { loading: () => <LoadingState variant='cards' count={3} /> },
)
const DashboardOverviewPageClient = dynamic(
  () =>
    import('@/components/dashboard/DashboardOverviewPageClient').then(
      (mod) => mod.DashboardOverviewPageClient,
    ),
  { loading: () => <LoadingState variant='detail' count={3} /> },
)
const LogsPageClient = dynamic(
  () => import('@/components/dashboard/LogsPageClient').then((mod) => mod.LogsPageClient),
  { loading: () => <LoadingState variant='rows' count={5} /> },
)
const MemoryPageClient = dynamic(
  () => import('@/components/dashboard/MemoryPageClient').then((mod) => mod.MemoryPageClient),
  { loading: () => <LoadingState variant='cards' count={3} /> },
)
const MonitoringPageClient = dynamic(
  () => import('@/components/dashboard/MonitoringPageClient').then((mod) => mod.MonitoringPageClient),
  { loading: () => <LoadingState variant='cards' count={3} /> },
)
const ObservabilityPageClient = dynamic(
  () =>
    import('@/components/dashboard/ObservabilityPageClient').then(
      (mod) => mod.ObservabilityPageClient,
    ),
  { loading: () => <LoadingState variant='cards' count={3} /> },
)
const NotificationsPageClient = dynamic(
  () => import('@/components/dashboard/NotificationsPageClient').then((mod) => mod.NotificationsPageClient),
  { loading: () => <LoadingState variant='rows' count={4} /> },
)
const OrchestrationPageClient = dynamic(
  () => import('@/components/dashboard/OrchestrationPageClient').then((mod) => mod.OrchestrationPageClient),
  { loading: () => <LoadingState variant='cards' count={3} /> },
)
const OpenclawSetupSurface = dynamic(
  () =>
    import('@/components/dashboard/control/OpenclawSetupSurface').then(
      (mod) => mod.OpenclawSetupSurface,
    ),
  { loading: () => <LoadingState variant='detail' count={2} /> },
)
const ReasoningPageClient = dynamic(
  () => import('@/components/dashboard/ReasoningPageClient').then((mod) => mod.ReasoningPageClient),
  { loading: () => <LoadingState variant='cards' count={3} /> },
)
const RunsPageClient = dynamic(
  () => import('@/components/dashboard/RunsPageClient').then((mod) => mod.RunsPageClient),
  { loading: () => <LoadingState variant='cards' count={3} /> },
)
const SecurityPageClient = dynamic(
  () => import('@/components/dashboard/SecurityPageClient').then((mod) => mod.SecurityPageClient),
  { loading: () => <LoadingState variant='cards' count={3} /> },
)
const SessionsPageClient = dynamic(
  () => import('@/components/dashboard/SessionsPageClient').then((mod) => mod.SessionsPageClient),
  { loading: () => <LoadingState variant='cards' count={3} /> },
)
const SkillsPageClient = dynamic(
  () => import('@/components/dashboard/SkillsPageClient').then((mod) => mod.SkillsPageClient),
  { loading: () => <LoadingState variant='cards' count={3} /> },
)
const SwarmsPageClient = dynamic(
  () => import('@/components/dashboard/SwarmsPageClient').then((mod) => mod.SwarmsPageClient),
  { loading: () => <LoadingState variant='cards' count={3} /> },
)
const StandupPageClient = dynamic(
  () => import('@/components/dashboard/StandupPageClient').then((mod) => mod.StandupPageClient),
  { loading: () => <LoadingState variant='detail' count={2} /> },
)
const TemplateCatalogPageClient = dynamic(
  () =>
    import('@/components/dashboard/TemplateCatalogPageClient').then(
      (mod) => mod.TemplateCatalogPageClient,
    ),
  { loading: () => <LoadingState variant='cards' count={3} /> },
)
const TracesPageClient = dynamic(
  () => import('@/components/dashboard/TracesPageClient').then((mod) => mod.TracesPageClient),
  { loading: () => <LoadingState variant='cards' count={3} /> },
)
const WebhooksPageClient = dynamic(
  () => import('@/components/webhooks/WebhooksPageClient'),
  { loading: () => <LoadingState variant='cards' count={3} /> },
)

function ShellRoute({
  title,
  description,
  badge,
  icon: Icon,
  iconTone,
  stats,
  children,
}: {
  title: string
  description: string
  badge: string
  icon: typeof Activity
  iconTone: string
  stats: Array<{ label: string; value: string; tone?: 'success' | 'warning' | 'danger' }>
  children: ReactNode
}) {
  return (
    <div className='space-y-4'>
      <RouteHeader
        title={title}
        description={description}
        icon={Icon}
        iconTone={iconTone}
        badge={badge}
        stats={stats}
      />

      {children}
    </div>
  )
}

export function UpgradeNudge({
  panel,
  subscription,
}: {
  panel: DashboardPanelId
  subscription: DashboardSubscription
}) {
  const setInterfaceMode = useMissionControl((state) => state.setInterfaceMode)
  const canUseFullMode = hasFullModeAccess(subscription)
  const panelLabel = panel.replaceAll('-', ' ')

  return (
    <section
      aria-labelledby='full-mode-title'
      className='dashboard-entry overflow-hidden rounded-[6px] border border-[#34342e] bg-[linear-gradient(145deg,#151612_0%,#0c0d0b_72%)] shadow-[0_24px_80px_rgba(0,0,0,0.28)]'
    >
      <div className='grid gap-8 p-5 sm:p-7 lg:grid-cols-[minmax(0,1fr)_minmax(260px,0.42fr)] lg:items-end'>
        <div className='max-w-3xl'>
          <div className='flex flex-wrap items-center gap-2 font-[family:var(--font-mono)] text-[10px] font-semibold uppercase tracking-[0.16em] text-[#aaa397]'>
            <span className='inline-flex items-center gap-1.5 rounded-[3px] border border-[#4d3a2d] bg-[#1c100a] px-2.5 py-1 text-[#ff9b73]'>
              <LockKeyhole className='h-3.5 w-3.5' aria-hidden='true' />
              Essential view
            </span>
            <span>{subscription ? `${subscription} plan` : 'Plan unavailable'}</span>
          </div>

          <h1
            id='full-mode-title'
            className='mt-5 max-w-2xl font-[family:var(--font-site-display)] text-[clamp(2rem,5vw,4rem)] leading-[0.94] tracking-[-0.065em] text-[#eee9dc]'
          >
            {canUseFullMode
              ? 'Open the full workspace.'
              : subscription === 'free'
                ? 'This panel belongs to full mode.'
                : 'Plan access could not be verified.'}
          </h1>
          <p className='mt-5 max-w-2xl text-sm leading-7 text-[#aaa397] sm:text-[15px]'>
            {canUseFullMode
              ? `Your plan includes the ${panelLabel} panel. Switch views here and continue without leaving the current route.`
              : subscription === 'free'
                ? `The ${panelLabel} panel is available on Pro and Enterprise. Essential mode keeps the core fleet, task, session, activity, log, approval, and settings workflows available.`
                : 'The workspace did not infer a free plan from a failed check. Retry the entitlement request before changing your subscription.'}
          </p>

          <div className='mt-7 flex flex-wrap gap-3'>
            {canUseFullMode ? (
              <button
                type='button'
                aria-label={`Switch ${panelLabel} panel to full mode`}
                onClick={() => setInterfaceMode('full')}
                className='inline-flex min-h-11 items-center gap-2 rounded-[4px] bg-[#ff571c] px-4 text-sm font-semibold text-[#090a08] transition-colors hover:bg-[#ff7445] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#ff8d66] motion-reduce:transition-none'
              >
                Switch to full mode
                <ArrowUpRight className='h-4 w-4' aria-hidden='true' />
              </button>
            ) : subscription === 'free' ? (
              <a
                href='/pico/pricing?plan=pro'
                aria-label={`Compare plans for ${panelLabel} panel`}
                className='inline-flex min-h-11 items-center gap-2 rounded-[4px] bg-[#ff571c] px-4 text-sm font-semibold text-[#090a08] transition-colors hover:bg-[#ff7445] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#ff8d66] motion-reduce:transition-none'
              >
                Compare plans
                <ArrowUpRight className='h-4 w-4' aria-hidden='true' />
              </a>
            ) : (
              <button
                type='button'
                aria-label={`Retry plan check for ${panelLabel} panel`}
                onClick={() => window.location.reload()}
                className='inline-flex min-h-11 items-center gap-2 rounded-[4px] bg-[#ff571c] px-4 text-sm font-semibold text-[#090a08] transition-colors hover:bg-[#ff7445] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#ff8d66] motion-reduce:transition-none'
              >
                Retry plan check
                <ArrowUpRight className='h-4 w-4' aria-hidden='true' />
              </button>
            )}
            <a
              href='/dashboard'
              aria-label='Return to dashboard overview'
              className='inline-flex min-h-11 items-center gap-2 rounded-[4px] border border-[#45443c] bg-[#0c0d0b] px-4 text-sm font-medium text-[#d6d0c3] transition-colors hover:border-[#656258] hover:text-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#ff7847] motion-reduce:transition-none'
            >
              Return to overview
            </a>
          </div>
        </div>

        <dl className='grid gap-px overflow-hidden rounded-[5px] border border-[#34342e] bg-[#34342e]'>
          {[
            ['Requested panel', panelLabel],
            ['Current view', 'Essential'],
            ['Current plan', subscription || 'Unavailable'],
            ['Required plan', 'Pro or Enterprise'],
          ].map(([label, value]) => (
            <div key={label} className='flex items-center justify-between gap-5 bg-[#0c0d0b] px-4 py-3.5'>
              <dt className='font-[family:var(--font-mono)] text-[10px] uppercase tracking-[0.14em] text-[#918b80]'>
                {label}
              </dt>
              <dd className='text-end text-sm font-medium capitalize text-[#eee9dc]'>{value}</dd>
            </div>
          ))}
        </dl>
      </div>
    </section>
  )
}

function renderPanel(panel: DashboardPanelId) {
  switch (panel) {
    case 'overview':
      return (
        <ShellRoute
          title='Overview'
          description='Fleet posture, recent execution, alerts, delivery health, and budget state in one surface.'
          icon={Activity}
          iconTone='text-cyan-300 bg-cyan-400/10'
          badge='workspace overview'
          stats={[
            { label: 'Route', value: '/dashboard' },
            { label: 'Data', value: 'Aggregated sources' },
          ]}
        >
          <DashboardOverviewPageClient />
        </ShellRoute>
      )
    case 'agents':
      return (
        <ShellRoute
          title='Agents'
          description='Manage your MUTX agent registry, lifecycle operations, and per-agent configuration.'
          icon={Bot}
          iconTone='text-cyan-300 bg-cyan-400/10'
          badge='core surface'
          stats={[
            { label: 'Scope', value: 'Fleet registry' },
            { label: 'Data', value: 'Live API', tone: 'success' },
          ]}
        >
          <AgentsPageClient />
        </ShellRoute>
      )
    case 'deployments':
      return (
        <ShellRoute
          title='Deployments'
          description='Operate active MUTX deployments, rollout actions, and runtime-level fleet posture.'
          icon={GitBranchPlus}
          iconTone='text-emerald-400 bg-emerald-400/10'
          badge='core surface'
          stats={[
            { label: 'Scope', value: 'Runtime control' },
            { label: 'Data', value: 'Live API', tone: 'success' },
          ]}
        >
          <DeploymentsPageClient />
        </ShellRoute>
      )
    case 'documents':
      return (
        <ShellRoute
          title='Documents'
          description='Predict-RLM-backed document workflows with managed uploads, local desktop execution, and run-trace linkage.'
          icon={FileText}
          iconTone='text-amber-300 bg-amber-400/10'
          badge='document workflows'
          stats={[
            { label: 'Execution', value: 'Hybrid' },
            { label: 'Artifacts', value: 'Managed storage', tone: 'success' },
          ]}
        >
          <DocumentsPageClient />
        </ShellRoute>
      )
    case 'reasoning':
      return (
        <ShellRoute
          title='Reasoning'
          description='Autoreason refinement jobs with blind judging, persisted artifacts, and direct run-trace linkage.'
          icon={Brain}
          iconTone='text-violet-300 bg-violet-400/10'
          badge='autoreason v1'
          stats={[
            { label: 'Loop', value: 'A/B/AB' },
            { label: 'Judging', value: 'Blind panel', tone: 'success' },
          ]}
        >
          <ReasoningPageClient />
        </ShellRoute>
      )
    case 'runs':
      return (
        <ShellRoute
          title='Runs'
          description='Recent execution history, terminal state, and recovery context from the live runs contract.'
          icon={History}
          iconTone='text-cyan-300 bg-cyan-400/10'
          badge='execution surface'
          stats={[
            { label: 'Scope', value: 'Recent runs' },
            { label: 'Data', value: 'Live API', tone: 'success' },
          ]}
        >
          <RunsPageClient />
        </ShellRoute>
      )
    case 'monitoring':
      return (
        <ShellRoute
          title='Monitoring'
          description='Live health, open alerts, and control-plane status at a glance.'
          icon={BellRing}
          iconTone='text-sky-400 bg-sky-400/10'
          badge='monitoring surface'
          stats={[
            { label: 'Scope', value: 'Health + alerts' },
            { label: 'Source', value: 'Live API', tone: 'success' },
          ]}
        >
          <MonitoringPageClient />
        </ShellRoute>
      )
    case 'approvals':
      return (
        <ShellRoute
          title='Approval queue'
          description='Review requester intent and execution context, then resolve pending control-plane actions against the canonical approval envelope.'
          icon={Gavel}
          iconTone='text-amber-300 bg-amber-400/10'
          badge='human control gate'
          stats={[
            { label: 'Source', value: '/v1/approvals', tone: 'success' },
            { label: 'Decisions', value: 'Role enforced', tone: 'warning' },
          ]}
        >
          <ApprovalsPageClient />
        </ShellRoute>
      )
    case 'audit':
      return (
        <ShellRoute
          title='Audit evidence'
          description='Filter attributable control-plane events, inspect redacted context, and export verified evidence for one run or session.'
          icon={ClipboardCheck}
          iconTone='text-emerald-300 bg-emerald-400/10'
          badge='governance ledger'
          stats={[
            { label: 'Source', value: '/v1/audit/events', tone: 'success' },
            { label: 'Access', value: 'Audit role', tone: 'warning' },
          ]}
        >
          <AuditPageClient />
        </ShellRoute>
      )
    case 'activity':
      return (
        <ShellRoute
          title='History'
          description='Review recent control-plane runs and inspect the recorded activity and trace events for each execution.'
          icon={History}
          iconTone='text-slate-200 bg-white/10'
          badge='execution activity'
          stats={[
            { label: 'Source', value: 'Runs API' },
            { label: 'Data', value: 'Live', tone: 'success' },
          ]}
        >
          <LogsPageClient mode='history' />
        </ShellRoute>
      )
    case 'traces':
      return (
        <ShellRoute
          title='Traces'
          description='Correlated event streams anchored to real runs instead of a standalone synthetic log wall.'
          icon={Workflow}
          iconTone='text-sky-300 bg-sky-400/10'
          badge='trace explorer'
          stats={[
            { label: 'Scope', value: 'Run drilldown' },
            { label: 'Data', value: 'Live API', tone: 'success' },
          ]}
        >
          <TracesPageClient />
        </ShellRoute>
      )
    case 'observability':
      return (
        <ShellRoute
          title='Observability'
          description='Agent run observability powered by the MUTX Observability Schema.'
          icon={Radar}
          iconTone='text-emerald-300 bg-emerald-400/10'
          badge='observability surface'
          stats={[
            { label: 'Schema', value: 'MutxRun' },
            { label: 'Source', value: 'agent-run', tone: 'success' },
          ]}
        >
          <ObservabilityPageClient />
        </ShellRoute>
      )
    case 'chat':
      return (
        <ShellRoute
          title='Sessions'
          description='Assistant sessions, channel presence, and OpenClaw gateway availability from the live session contracts.'
          icon={Users}
          iconTone='text-cyan-300 bg-cyan-400/10'
          badge='session surface'
          stats={[
            { label: 'Scope', value: 'Gateway sessions' },
            { label: 'Data', value: 'Live API', tone: 'success' },
          ]}
        >
          <SessionsPageClient />
        </ShellRoute>
      )
    case 'api-keys':
      return (
        <ShellRoute
          title='API Keys'
          description='Create, rotate, revoke, and inspect API keys without leaving the dashboard.'
          icon={Key}
          iconTone='text-amber-300 bg-amber-400/10'
          badge='credential surface'
          stats={[
            { label: 'Scope', value: 'Keys only' },
            { label: 'Data', value: 'Live API', tone: 'success' },
          ]}
        >
          <ApiKeysPageClient />
        </ShellRoute>
      )
    case 'cost-tracker':
      return (
        <ShellRoute
          title='Budgets'
          description='Credit posture, spend separation, and usage breakdown anchored to the live budget and analytics contracts.'
          icon={Wallet}
          iconTone='text-emerald-300 bg-emerald-400/10'
          badge='cost surface'
          stats={[
            { label: 'Scope', value: 'Credits + usage' },
            { label: 'Data', value: 'Live API', tone: 'success' },
          ]}
        >
          <BudgetsPageClient />
        </ShellRoute>
      )
    case 'webhooks':
      return (
        <ShellRoute
          title='Webhooks'
          description='Manage outbound event endpoints and verify delivery behavior with truthful delivery history.'
          icon={Webhook}
          iconTone='text-fuchsia-300 bg-fuchsia-400/10'
          badge='integration surface'
          stats={[
            { label: 'Scope', value: 'Event delivery' },
            { label: 'Data', value: 'Live API', tone: 'success' },
          ]}
        >
          <WebhooksPageClient />
        </ShellRoute>
      )
    case 'security':
      return (
        <ShellRoute
          title='Security'
          description='Credential inventory, auth posture, and trust boundaries in the same surface as deployment and recovery.'
          icon={ShieldCheck}
          iconTone='text-amber-300 bg-amber-400/10'
          badge='security surface'
          stats={[
            { label: 'Scope', value: 'Auth + governance' },
            { label: 'Data', value: 'Live API', tone: 'success' },
          ]}
        >
          <SecurityPageClient />
        </ShellRoute>
      )
    case 'tasks':
      return (
        <ShellRoute
          title='Orchestration'
          description='Approvals, recovery lanes, blueprints, and autonomy queue posture from live orchestration data.'
          icon={Network}
          iconTone='text-sky-300 bg-sky-400/10'
          badge='orchestration surface'
          stats={[{ label: 'Scope', value: 'Workflow + recovery' }, { label: 'Data', value: 'Live API', tone: 'success' }]}
        >
          <OrchestrationPageClient />
        </ShellRoute>
      )
    case 'memory':
      return (
        <ShellRoute
          title='Memory'
          description='Retained session context, source activity, and workspace memory artifacts from the live contract.'
          icon={Brain}
          iconTone='text-violet-300 bg-violet-400/10'
          badge='memory surface'
          stats={[{ label: 'Scope', value: 'Context + artifacts' }, { label: 'Data', value: 'Live API', tone: 'success' }]}
        >
          <MemoryPageClient />
        </ShellRoute>
      )
    case 'tokens':
      return (
        <ShellRoute
          title='Analytics'
          description='Usage trends, latency posture, and activity summaries from the live analytics contracts.'
          icon={BarChart3}
          iconTone='text-fuchsia-300 bg-fuchsia-400/10'
          badge='analytics surface'
          stats={[
            { label: 'Scope', value: 'Trends + usage' },
            { label: 'Data', value: 'Live API', tone: 'success' },
          ]}
        >
          <AnalyticsPageClient />
        </ShellRoute>
      )
    case 'channels':
      return (
        <ShellRoute
          title='Channels'
          description='Assistant channel bindings, policy mode, sessions, and communication readiness from the live contract.'
          icon={Users}
          iconTone='text-cyan-300 bg-cyan-400/10'
          badge='assistant channels'
          stats={[{ label: 'Scope', value: 'Bindings + sessions' }, { label: 'Data', value: 'Live API', tone: 'success' }]}
        >
          <ChannelsPageClient />
        </ShellRoute>
      )
    case 'skills':
      return (
        <ShellRoute
          title='Skills'
          description='Pinned Orchestra Research imports, curated bundles, and runtime-ready skill inventory for live assistants.'
          icon={Brain}
          iconTone='text-cyan-300 bg-cyan-400/10'
          badge='skillpack control'
          stats={[
            { label: 'Catalog', value: 'ClawHub + Orchestra' },
            { label: 'Mode', value: 'Live install', tone: 'success' },
          ]}
        >
          <SkillsPageClient />
        </ShellRoute>
      )
    case 'logs':
      return (
        <ShellRoute
          title='Logs'
          description='Real-time step timeline and execution log for agent runs. Click any run to inspect its step sequence.'
          icon={TerminalSquare}
          iconTone='text-slate-200 bg-white/10'
          badge='execution trace'
          stats={[
            { label: 'Source', value: 'Observability API' },
            { label: 'Data', value: 'Live', tone: 'success' },
          ]}
        >
          <LogsPageClient />
        </ShellRoute>
      )
    case 'settings':
      return (
        <ShellRoute
          title='Settings'
          description='Bridge diagnostics, runtime repair, and setup flow for this workspace.'
          icon={Network}
          iconTone='text-cyan-300 bg-cyan-400/10'
          badge='advanced diagnostics'
          stats={[
            { label: 'Scope', value: 'Desktop + runtime' },
            { label: 'Data', value: 'Live API', tone: 'success' },
          ]}
        >
          <OpenclawSetupSurface />
        </ShellRoute>
      )
    case 'cron':
      return (
        <ShellRoute
          title='Autonomy'
          description='Local view for the live autonomy daemon, queue depth, active runners, and recent reports.'
          icon={Bot}
          iconTone='text-fuchsia-300 bg-fuchsia-400/10'
          badge='local autonomy surface'
          stats={[
            { label: 'Source', value: '.autonomy + queue', tone: 'success' },
            { label: 'Scope', value: 'Daemon + lanes + reports' },
          ]}
        >
          <AutonomyPageClient />
        </ShellRoute>
      )
    case 'swarm':
      return (
        <ShellRoute
          title='Swarm'
          description='Grouped agent topology and coordinated replica posture from the live swarm contract.'
          icon={GitBranchPlus}
          iconTone='text-cyan-300 bg-cyan-400/10'
          badge='swarm surface'
          stats={[
            { label: 'Scope', value: 'Grouped agents' },
            { label: 'Data', value: 'Live API', tone: 'success' },
          ]}
        >
          <SwarmsPageClient />
        </ShellRoute>
      )
    case 'templates':
      return (
        <ShellRoute
          title='Templates'
          description='Browse, clone, and deploy MUTX agent starter templates. Custom templates are editable and persisted to your catalog.'
          icon={LayoutGrid}
          iconTone='text-violet-300 bg-violet-400/10'
          badge='workspace'
          stats={[
            { label: 'Scope', value: 'Templates + custom' },
            { label: 'Source', value: 'API + local catalog' },
          ]}
        >
          <TemplateCatalogPageClient />
        </ShellRoute>
      )
    case 'notifications':
      return (
        <ShellRoute
          title='Notifications'
          description='Live alerts, pending approvals, webhook failures, and runtime incident summaries.'
          icon={BellRing}
          iconTone='text-amber-300 bg-amber-400/10'
          badge='signal inbox'
          stats={[{ label: 'Scope', value: 'Signals only' }, { label: 'Data', value: 'Aggregated signals' }]}
        >
          <NotificationsPageClient />
        </ShellRoute>
      )
    case 'standup':
      return (
        <ShellRoute
          title='Standup'
          description='A read-only brief synthesized from current alerts, approvals, runs, failures, and autonomy backlog.'
          icon={Activity}
          iconTone='text-cyan-300 bg-cyan-400/10'
          badge='derived brief'
          stats={[{ label: 'Scope', value: 'Read-only synthesis' }, { label: 'Data', value: 'Derived snapshot' }]}
        >
          <StandupPageClient />
        </ShellRoute>
      )
  }
}

export function DashboardContentRouter({
  panel,
  interfaceMode,
  subscription,
}: {
  panel: DashboardPanelId
  interfaceMode: InterfaceMode
  subscription: DashboardSubscription
}) {
  if (!isPanelAccessibleInMode(panel, interfaceMode)) {
    return <UpgradeNudge panel={panel} subscription={subscription} />
  }

  return renderPanel(panel)
}
