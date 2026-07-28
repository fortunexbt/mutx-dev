'use client'

import { create } from 'zustand'
import { subscribeWithSelector } from 'zustand/middleware'

// ---------------------------------------------------------------------------
// Domain Interfaces — ported from mission-control src/store/index.ts
// Adapted for MUTX /v1/* API surface and existing dashboard routes.
// ---------------------------------------------------------------------------

export type AgentStatus = 'offline' | 'idle' | 'busy' | 'error'
export type TaskStatus =
  | 'backlog'
  | 'inbox'
  | 'assigned'
  | 'awaiting_owner'
  | 'in_progress'
  | 'review'
  | 'quality_review'
  | 'done'
  | 'failed'
export type TaskPriority = 'critical' | 'high' | 'medium' | 'low' | 'trivial'
export type DashboardStatus = 'idle' | 'running' | 'success' | 'error' | 'warning'
export type RunFlowStatus = 'pending' | 'running' | 'completed' | 'failed' | 'awaiting_owner'
export type LogLevel = 'info' | 'warn' | 'error' | 'debug'
export type InterfaceMode = 'essential' | 'full'

export interface CurrentUser {
  id: string
  username: string
  display_name: string
  role: 'admin' | 'operator' | 'viewer'
  workspace_id?: string
  tenant_id?: string
  provider?: string
  email?: string
  avatar_url?: string
}

export interface Agent {
  id: string
  name: string
  role: string
  session_key?: string
  soul_content?: string
  working_memory?: string
  status: AgentStatus
  last_seen?: string
  last_activity?: string
  created_at: string
  updated_at: string
  hidden?: boolean
  config?: Record<string, unknown>
  taskStats?: { total: number; completed: number; failed: number }
}

export interface Session {
  id: string
  key: string
  agent?: string
  channel?: string
  kind: string
  age: number
  model?: string
  tokens?: number
  flags: string[]
  active: boolean
  startTime?: string
  lastActivity?: string
  messageCount?: number
  cost?: number
  label?: string
}

export interface Task {
  id: string
  title: string
  description?: string
  status: TaskStatus
  priority: TaskPriority
  project_id?: string
  assigned_to?: string
  created_by: string
  created_at: string
  updated_at: string
  due_date?: string
  tags?: string[]
  github_issue_number?: number
  github_repo?: string
  github_status?: string
  metadata?: Record<string, unknown>
}

export interface Activity {
  id: string
  type: string
  entity_type: string
  entity_id: string
  actor: string
  description: string
  data?: Record<string, unknown>
  created_at: string
  entity?: { type: string; id: string; title?: string; name?: string; status?: string }
}

export interface Notification {
  id: string
  recipient: string
  type: string
  title: string
  message: string
  source_type?: string
  source_id?: string
  read_at?: string
  delivered_at?: string
  created_at: string
}

export interface LogEntry {
  id: string
  timestamp: string
  level: LogLevel
  source: string
  session?: string
  message: string
  data?: Record<string, unknown>
}

export interface Run {
  id: string
  agent_id?: string
  status: RunFlowStatus
  model?: string
  input_tokens?: number
  output_tokens?: number
  cost?: number
  started_at?: string
  completed_at?: string
  error?: string
  traces?: TraceEntry[]
}

export interface TraceEntry {
  id: string
  run_id: string
  step: number
  type: string
  name: string
  input?: unknown
  output?: unknown
  duration_ms?: number
  timestamp: string
}

export interface Deployment {
  id: string
  agent_id: string
  status: DashboardStatus
  version?: string
  created_at: string
  updated_at: string
  config?: Record<string, unknown>
}

export interface Budget {
  user_id: string
  plan: string
  credits_total: number
  credits_used: number
  credits_remaining: number
  reset_date: string
  usage_percentage: number
}

export interface MonitoringAlert {
  id: string
  type: string
  severity: 'info' | 'warning' | 'critical'
  message: string
  source?: string
  acknowledged: boolean
  created_at: string
  resolved_at?: string
}

export interface AnalyticsSummary {
  total_agents: number
  active_sessions: number
  total_runs: number
  total_cost: number
  total_tokens: number
  period: string
}

export interface OverviewData {
  agents: { total: number; active: number; idle: number; error: number }
  sessions: { total: number; active: number }
  runs: { total: number; pending: number; running: number; completed: number; failed: number }
  costs: { today: number; week: number; month: number }
}

export interface ConnectionStatus {
  isConnected: boolean
  url?: string
  lastConnected?: string
  reconnectAttempts: number
  latency?: number
  sseConnected?: boolean
}

export interface QueueDepthEntry {
  status: RunFlowStatus
  count: number
  label: string
}

export interface FlowStage {
  status: RunFlowStatus
  count: number
  maxCount: number
}

// ---------------------------------------------------------------------------
// Store State Shape
// ---------------------------------------------------------------------------

export interface MissionControlState {
  // -- Auth --
  currentUser: CurrentUser | null

  // -- Connection --
  connection: ConnectionStatus
  lastMessage: unknown | null

  // -- Boot --
  bootComplete: boolean
  capabilitiesChecked: boolean
  dashboardMode: 'local' | 'gateway'
  interfaceMode: InterfaceMode
  subscription: 'free' | 'pro' | 'enterprise' | null

  // -- Agents --
  agents: Agent[]
  selectedAgent: Agent | null

  // -- Sessions --
  sessions: Session[]
  selectedSession: Session | null

  // -- Runs --
  runs: Run[]

  // -- Tasks --
  tasks: Task[]
  selectedTask: Task | null

  // -- Activities --
  activities: Activity[]

  // -- Notifications --
  notifications: Notification[]
  unreadNotificationCount: number

  // -- Logs --
  logs: LogEntry[]
  logFilters: { level?: LogLevel; source?: string; session?: string }

  // -- Deployments --
  deployments: Deployment[]

  // -- Budgets --
  budget: Budget | null
  /** @deprecated Use budget. Kept as a compatibility view for existing consumers. */
  budgets: Budget[]

  // -- Monitoring --
  monitoringAlerts: MonitoringAlert[]

  // -- Analytics --
  analyticsSummary: AnalyticsSummary | null
  overview: OverviewData | null

  // -- UI State --
  activeTab: string
  sidebarExpanded: boolean
  collapsedGroups: string[]
  liveFeedOpen: boolean
  chatPanelOpen: boolean
  headerDensity: 'compact' | 'normal' | 'comfortable'
  dashboardLayout: string[] | null

  // -- Update availability --
  updateAvailable: string | null
  updateDismissedVersion: string | null
  bannerDismissed: boolean
}

// ---------------------------------------------------------------------------
// Store Actions
// ---------------------------------------------------------------------------

export interface MissionControlActions {
  // -- Auth --
  setCurrentUser: (user: CurrentUser | null) => void

  // -- Connection --
  setConnection: (status: Partial<ConnectionStatus>) => void
  setLastMessage: (msg: unknown) => void

  // -- Boot --
  setBootComplete: (complete: boolean) => void
  setCapabilitiesChecked: (checked: boolean) => void
  setDashboardMode: (mode: 'local' | 'gateway') => void
  setInterfaceMode: (mode: InterfaceMode) => void
  setSubscription: (sub: 'free' | 'pro' | 'enterprise' | null) => void

  // -- Agents --
  setAgents: (agents: Agent[]) => void
  setSelectedAgent: (agent: Agent | null) => void
  addAgent: (agent: Agent) => void
  updateAgent: (id: string, updates: Partial<Agent>) => void
  deleteAgent: (id: string) => void

  // -- Sessions --
  setSessions: (sessions: Session[]) => void
  setSelectedSession: (session: Session | null) => void
  updateSession: (key: string, updates: Partial<Session>) => void

  // -- Runs --
  setRuns: (runs: Run[]) => void

  // -- Tasks --
  setTasks: (tasks: Task[]) => void
  setSelectedTask: (task: Task | null) => void
  addTask: (task: Task) => void
  updateTask: (id: string, updates: Partial<Task>) => void
  deleteTask: (id: string) => void

  // -- Activities --
  setActivities: (activities: Activity[]) => void
  addActivity: (activity: Activity) => void

  // -- Notifications --
  setNotifications: (notifications: Notification[]) => void
  addNotification: (notification: Notification) => void
  markNotificationRead: (id: string) => void
  markAllNotificationsRead: () => void

  // -- Logs --
  addLog: (entry: LogEntry) => void
  setLogFilters: (filters: Partial<MissionControlState['logFilters']>) => void
  clearLogs: () => void

  // -- Deployments --
  setDeployments: (deployments: Deployment[]) => void

  // -- Budgets --
  setBudget: (budget: Budget | null) => void
  setBudgets: (budgets: Budget[]) => void

  // -- Monitoring --
  setMonitoringAlerts: (alerts: MonitoringAlert[]) => void

  // -- Analytics --
  setAnalyticsSummary: (summary: AnalyticsSummary | null) => void
  setOverview: (overview: OverviewData | null) => void

  // -- UI --
  setActiveTab: (tab: string) => void
  toggleSidebar: () => void
  setSidebarExpanded: (expanded: boolean) => void
  toggleGroup: (group: string) => void
  toggleLiveFeed: () => void
  setChatPanelOpen: (open: boolean) => void
  setHeaderDensity: (density: MissionControlState['headerDensity']) => void
  setDashboardLayout: (layout: string[] | null) => void

  // -- Update --
  setUpdateAvailable: (version: string | null) => void
  dismissUpdate: () => void
  dismissBanner: () => void

  // -- Async fetch actions --
  fetchAgents: () => Promise<void>
  fetchSessions: () => Promise<void>
  fetchRuns: () => Promise<void>
  fetchOverview: () => Promise<void>
  fetchAnalyticsSummary: () => Promise<void>
  fetchMonitoringAlerts: () => Promise<void>
  fetchBudgets: () => Promise<void>
  fetchDeployments: () => Promise<void>

  // -- Boot sequence --
  boot: () => Promise<void>
}

// ---------------------------------------------------------------------------
// localStorage helpers — prefix 'mutx-' to avoid collision with MC's 'mc-'
// ---------------------------------------------------------------------------

function loadFromLocalStorage<T>(key: string, fallback: T): T {
  if (typeof window === 'undefined') return fallback
  try {
    const raw = localStorage.getItem(`mutx-${key}`)
    return raw ? (JSON.parse(raw) as T) : fallback
  } catch {
    return fallback
  }
}

function saveToLocalStorage(key: string, value: unknown): void {
  if (typeof window === 'undefined') return
  try {
    localStorage.setItem(`mutx-${key}`, JSON.stringify(value))
  } catch {
    // localStorage full or unavailable — silent degrade
  }
}

// ---------------------------------------------------------------------------
// Dashboard response helpers
// ---------------------------------------------------------------------------

const EMPTY_RESPONSE = Symbol('empty dashboard response')

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function errorSuffix(error: unknown): string {
  return error instanceof Error && error.message ? `: ${error.message}` : ''
}

async function fetchDashboardJson(
  path: string,
  options: { allowNoContent?: boolean } = {}
): Promise<unknown | typeof EMPTY_RESPONSE> {
  let response: Response

  try {
    response = await fetch(path)
  } catch (error) {
    throw new Error(`[MUTX Store] Request to ${path} failed${errorSuffix(error)}`, {
      cause: error,
    })
  }

  if (!response.ok) {
    const statusText = response.statusText ? ` ${response.statusText}` : ''
    throw new Error(`[MUTX Store] Request to ${path} failed with ${response.status}${statusText}`)
  }

  if (response.status === 204) {
    if (options.allowNoContent) return EMPTY_RESPONSE
    throw new Error(`[MUTX Store] Request to ${path} returned 204 without required JSON`)
  }

  try {
    return await response.json()
  } catch (error) {
    throw new Error(
      `[MUTX Store] Request to ${path} returned invalid JSON${errorSuffix(error)}`,
      { cause: error }
    )
  }
}

function normalizeCollection<T>(
  path: string,
  payload: unknown | typeof EMPTY_RESPONSE,
  envelopeKeys: readonly string[]
): T[] {
  if (payload === EMPTY_RESPONSE) return []
  if (Array.isArray(payload)) return payload as T[]

  if (isRecord(payload)) {
    for (const key of ['items', ...envelopeKeys, 'data']) {
      const candidate = payload[key]
      if (Array.isArray(candidate)) return candidate as T[]
    }
  }

  throw new Error(`[MUTX Store] Request to ${path} returned an invalid collection payload`)
}

function normalizeObject<T>(
  path: string,
  payload: unknown | typeof EMPTY_RESPONSE,
  envelopeKeys: readonly string[] = []
): T {
  if (!isRecord(payload)) {
    throw new Error(`[MUTX Store] Request to ${path} returned an invalid object payload`)
  }

  for (const key of envelopeKeys) {
    const candidate = payload[key]
    if (isRecord(candidate)) return candidate as T
  }

  return payload as T
}

function isBudget(value: unknown): value is Budget {
  return (
    isRecord(value) &&
    typeof value.user_id === 'string' &&
    typeof value.plan === 'string' &&
    typeof value.credits_total === 'number' &&
    typeof value.credits_used === 'number' &&
    typeof value.credits_remaining === 'number' &&
    typeof value.reset_date === 'string' &&
    typeof value.usage_percentage === 'number'
  )
}

function normalizeBudget(path: string, payload: unknown | typeof EMPTY_RESPONSE): Budget {
  const budget = normalizeObject<unknown>(path, payload, ['budget', 'data'])
  if (!isBudget(budget)) {
    throw new Error(`[MUTX Store] Request to ${path} returned an invalid budget payload`)
  }
  return budget
}

// ---------------------------------------------------------------------------
// Store definition
// ---------------------------------------------------------------------------

export type MissionControlStore = MissionControlState & MissionControlActions

export const useMissionControl = create<MissionControlStore>()(
  subscribeWithSelector((set, get) => ({
    // ===== Initial state =====

    // Auth
    currentUser: null,

    // Connection
    connection: {
      isConnected: false,
      reconnectAttempts: 0,
      sseConnected: false,
    },
    lastMessage: null,

    // Boot
    bootComplete: false,
    capabilitiesChecked: false,
    dashboardMode: 'local',
    interfaceMode: loadFromLocalStorage<InterfaceMode>('interface-mode', 'full'),
    subscription: null,

    // Agents
    agents: [],
    selectedAgent: null,

    // Sessions
    sessions: [],
    selectedSession: null,

    // Runs
    runs: [],

    // Tasks
    tasks: [],
    selectedTask: null,

    // Activities
    activities: [],

    // Notifications
    notifications: [],
    unreadNotificationCount: 0,

    // Logs
    logs: [],
    logFilters: {},

    // Deployments
    deployments: [],

    // Budgets
    budget: null,
    budgets: [],

    // Monitoring
    monitoringAlerts: [],

    // Analytics
    analyticsSummary: null,
    overview: null,

    // UI — hydrate from localStorage
    activeTab: 'overview',
    sidebarExpanded: loadFromLocalStorage('sidebar-expanded', true),
    collapsedGroups: loadFromLocalStorage<string[]>('sidebar-groups', []),
    liveFeedOpen: loadFromLocalStorage('livefeed-open', true),
    chatPanelOpen: false,
    headerDensity: loadFromLocalStorage<MissionControlState['headerDensity']>(
      'header-density',
      'normal'
    ),
    dashboardLayout: loadFromLocalStorage<string[] | null>('dashboard-layout', null),

    // Update
    updateAvailable: null,
    updateDismissedVersion: null,
    bannerDismissed: loadFromLocalStorage('banner-dismissed', false),

    // ===== Actions =====

    // -- Auth --
    setCurrentUser: (user) => set({ currentUser: user }),

    // -- Connection --
    setConnection: (status) =>
      set((state) => ({ connection: { ...state.connection, ...status } })),
    setLastMessage: (msg) => set({ lastMessage: msg }),

    // -- Boot --
    setBootComplete: (complete) => set({ bootComplete: complete }),
    setCapabilitiesChecked: (checked) => set({ capabilitiesChecked: checked }),
    setDashboardMode: (mode) => set({ dashboardMode: mode }),
    setInterfaceMode: (mode) => {
      saveToLocalStorage('interface-mode', mode)
      set({ interfaceMode: mode })
    },
    setSubscription: (sub) => set({ subscription: sub }),

    // -- Agents --
    setAgents: (agents) => set({ agents }),
    setSelectedAgent: (agent) => set({ selectedAgent: agent }),
    addAgent: (agent) => set((state) => ({ agents: [...state.agents, agent] })),
    updateAgent: (id, updates) =>
      set((state) => ({
        agents: state.agents.map((a) => (a.id === id ? { ...a, ...updates } : a)),
        selectedAgent:
          state.selectedAgent?.id === id
            ? { ...state.selectedAgent, ...updates }
            : state.selectedAgent,
      })),
    deleteAgent: (id) =>
      set((state) => ({
        agents: state.agents.filter((a) => a.id !== id),
        selectedAgent: state.selectedAgent?.id === id ? null : state.selectedAgent,
      })),

    // -- Sessions --
    setSessions: (sessions) => set({ sessions }),
    setSelectedSession: (session) => set({ selectedSession: session }),
    updateSession: (key, updates) =>
      set((state) => ({
        sessions: state.sessions.map((s) => (s.key === key ? { ...s, ...updates } : s)),
        selectedSession:
          state.selectedSession?.key === key
            ? { ...state.selectedSession, ...updates }
            : state.selectedSession,
      })),

    // -- Runs --
    setRuns: (runs) => set({ runs }),

    // -- Tasks --
    setTasks: (tasks) => set({ tasks }),
    setSelectedTask: (task) => set({ selectedTask: task }),
    addTask: (task) => set((state) => ({ tasks: [...state.tasks, task] })),
    updateTask: (id, updates) =>
      set((state) => ({
        tasks: state.tasks.map((t) => (t.id === id ? { ...t, ...updates } : t)),
        selectedTask:
          state.selectedTask?.id === id
            ? { ...state.selectedTask, ...updates }
            : state.selectedTask,
      })),
    deleteTask: (id) =>
      set((state) => ({
        tasks: state.tasks.filter((t) => t.id !== id),
        selectedTask: state.selectedTask?.id === id ? null : state.selectedTask,
      })),

    // -- Activities --
    setActivities: (activities) => set({ activities }),
    addActivity: (activity) =>
      set((state) => ({ activities: [activity, ...state.activities] })),

    // -- Notifications --
    setNotifications: (notifications) =>
      set({
        notifications,
        unreadNotificationCount: notifications.filter((n) => !n.read_at).length,
      }),
    addNotification: (notification) =>
      set((state) => ({
        notifications: [notification, ...state.notifications],
        unreadNotificationCount: notification.read_at
          ? state.unreadNotificationCount
          : state.unreadNotificationCount + 1,
      })),
    markNotificationRead: (id) =>
      set((state) => ({
        notifications: state.notifications.map((n) =>
          n.id === id ? { ...n, read_at: new Date().toISOString() } : n
        ),
        unreadNotificationCount: Math.max(0, state.unreadNotificationCount - 1),
      })),
    markAllNotificationsRead: () =>
      set((state) => ({
        notifications: state.notifications.map((n) => ({
          ...n,
          read_at: n.read_at ?? new Date().toISOString(),
        })),
        unreadNotificationCount: 0,
      })),

    // -- Logs --
    addLog: (entry) =>
      set((state) => ({ logs: [...state.logs, entry] })),
    setLogFilters: (filters) =>
      set((state) => ({ logFilters: { ...state.logFilters, ...filters } })),
    clearLogs: () => set({ logs: [] }),

    // -- Deployments --
    setDeployments: (deployments) => set({ deployments }),

    // -- Budgets --
    setBudget: (budget) => set({ budget, budgets: budget ? [budget] : [] }),
    setBudgets: (budgets) => set({ budgets, budget: budgets[0] ?? null }),

    // -- Monitoring --
    setMonitoringAlerts: (alerts) => set({ monitoringAlerts: alerts }),

    // -- Analytics --
    setAnalyticsSummary: (summary) => set({ analyticsSummary: summary }),
    setOverview: (overview) => set({ overview }),

    // -- UI --
    setActiveTab: (tab) => set({ activeTab: tab }),
    toggleSidebar: () =>
      set((state) => {
        const expanded = !state.sidebarExpanded
        saveToLocalStorage('sidebar-expanded', expanded)
        return { sidebarExpanded: expanded }
      }),
    setSidebarExpanded: (expanded) => {
      saveToLocalStorage('sidebar-expanded', expanded)
      set({ sidebarExpanded: expanded })
    },
    toggleGroup: (group) =>
      set((state) => {
        const groups = new Set(state.collapsedGroups)
        if (groups.has(group)) groups.delete(group)
        else groups.add(group)
        const arr = Array.from(groups)
        saveToLocalStorage('sidebar-groups', arr)
        return { collapsedGroups: arr }
      }),
    toggleLiveFeed: () =>
      set((state) => {
        const open = !state.liveFeedOpen
        saveToLocalStorage('livefeed-open', open)
        return { liveFeedOpen: open }
      }),
    setChatPanelOpen: (open) => set({ chatPanelOpen: open }),
    setHeaderDensity: (density) => {
      saveToLocalStorage('header-density', density)
      set({ headerDensity: density })
    },
    setDashboardLayout: (layout) => {
      saveToLocalStorage('dashboard-layout', layout)
      set({ dashboardLayout: layout })
    },

    // -- Update --
    setUpdateAvailable: (version) => set({ updateAvailable: version }),
    dismissUpdate: () =>
      set((state) => ({ updateDismissedVersion: state.updateAvailable })),
    dismissBanner: () => {
      saveToLocalStorage('banner-dismissed', true)
      set({ bannerDismissed: true })
    },

    // ===== Async fetch actions =====
    // These call the existing /api/dashboard/* proxy routes.

    fetchAgents: async () => {
      const path = '/api/dashboard/agents'
      const data = await fetchDashboardJson(path, { allowNoContent: true })
      set({ agents: normalizeCollection<Agent>(path, data, ['agents']) })
    },

    fetchSessions: async () => {
      const path = '/api/dashboard/sessions'
      const data = await fetchDashboardJson(path, { allowNoContent: true })
      set({ sessions: normalizeCollection<Session>(path, data, ['sessions']) })
    },

    fetchRuns: async () => {
      const path = '/api/dashboard/runs'
      const data = await fetchDashboardJson(path, { allowNoContent: true })
      set({ runs: normalizeCollection<Run>(path, data, ['runs']) })
    },

    fetchOverview: async () => {
      const path = '/api/dashboard/overview'
      const data = await fetchDashboardJson(path)
      set({ overview: normalizeObject<OverviewData>(path, data, ['overview', 'data']) })
    },

    fetchAnalyticsSummary: async () => {
      const path = '/api/dashboard/analytics/summary'
      const data = await fetchDashboardJson(path)
      set({
        analyticsSummary: normalizeObject<AnalyticsSummary>(path, data, [
          'summary',
          'data',
        ]),
      })
    },

    fetchMonitoringAlerts: async () => {
      const path = '/api/dashboard/monitoring/alerts'
      const data = await fetchDashboardJson(path, { allowNoContent: true })
      set({
        monitoringAlerts: normalizeCollection<MonitoringAlert>(path, data, ['alerts']),
      })
    },

    fetchBudgets: async () => {
      const path = '/api/dashboard/budgets'
      const data = await fetchDashboardJson(path)
      const budget = normalizeBudget(path, data)
      set({ budget, budgets: [budget] })
    },

    fetchDeployments: async () => {
      const path = '/api/dashboard/deployments'
      const data = await fetchDashboardJson(path, { allowNoContent: true })
      set({
        deployments: normalizeCollection<Deployment>(path, data, ['deployments']),
      })
    },

    // ===== Boot sequence =====
    // Parallel data preload — mirrors MC's 9-step Promise.allSettled pattern.
    boot: async () => {
      const state = get()
      if (state.bootComplete) return

      const results = await Promise.allSettled([
        get().fetchAgents(),
        get().fetchSessions(),
        get().fetchRuns(),
        get().fetchOverview(),
        get().fetchAnalyticsSummary(),
        get().fetchMonitoringAlerts(),
        get().fetchBudgets(),
        get().fetchDeployments(),
      ])

      // Log any failures (but don't crash the app)
      const failed = results.filter((r) => r.status === 'rejected')
      if (failed.length > 0 && typeof window !== 'undefined') {
        console.warn(
          `[MUTX Store] Boot completed with ${failed.length} failed fetch(es)`,
          failed.map((f) => (f as PromiseRejectedResult).reason)
        )
      }

      set({ bootComplete: true })
    },
  }))
)
