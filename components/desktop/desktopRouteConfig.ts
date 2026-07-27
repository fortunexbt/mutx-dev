import type { LucideIcon } from "lucide-react";
import {
  Activity,
  BarChart3,
  BellRing,
  Bot,
  Brain,
  FileText,
  GitBranchPlus,
  History,
  KeyRound,
  Layers,
  LayoutGrid,
  ListTree,
  MemoryStick,
  MessagesSquare,
  Network,
  Radar,
  ShieldCheck,
  TerminalSquare,
  Users,
  Wallet,
  Webhook,
  Workflow,
} from "lucide-react";

export type DesktopRouteSection = "home" | "core" | "execution" | "admin" | "support";
export type DesktopRouteStage = "stable" | "preview" | "redirect";

export type DesktopRouteKey =
  | "home"
  | "agents"
  | "deployments"
  | "documents"
  | "reasoning"
  | "runs"
  | "monitoring"
  | "autonomy"
  | "traces"
  | "observability"
  | "sessions"
  | "apiKeys"
  | "budgets"
  | "webhooks"
  | "swarm"
  | "security"
  | "orchestration"
  | "memory"
  | "analytics"
  | "channels"
  | "templates"
  | "notifications"
  | "standup"
  | "history"
  | "skills"
  | "spawn"
  | "logs"
  | "control";

export const DASHBOARD_ROUTE_PATHS = {
  home: "/dashboard",
  agents: "/dashboard/agents",
  deployments: "/dashboard/deployments",
  documents: "/dashboard/documents",
  reasoning: "/dashboard/reasoning",
  runs: "/dashboard/runs",
  monitoring: "/dashboard/monitoring",
  autonomy: "/dashboard/autonomy",
  traces: "/dashboard/traces",
  observability: "/dashboard/observability",
  sessions: "/dashboard/sessions",
  apiKeys: "/dashboard/api-keys",
  budgets: "/dashboard/budgets",
  webhooks: "/dashboard/webhooks",
  swarm: "/dashboard/swarm",
  security: "/dashboard/security",
  orchestration: "/dashboard/orchestration",
  memory: "/dashboard/memory",
  analytics: "/dashboard/analytics",
  channels: "/dashboard/channels",
  templates: "/dashboard/templates",
  notifications: "/dashboard/notifications",
  standup: "/dashboard/standup",
  history: "/dashboard/history",
  skills: "/dashboard/skills",
  spawn: "/dashboard/spawn",
  logs: "/dashboard/logs",
  control: "/dashboard/control",
} as const satisfies Record<DesktopRouteKey, `/dashboard${string}`>;

export type DashboardRoutePath = (typeof DASHBOARD_ROUTE_PATHS)[DesktopRouteKey];

export interface DesktopRouteMeta {
  key: DesktopRouteKey;
  title: string;
  path: DashboardRoutePath;
  publicHref: DashboardRoutePath | null;
  description: string;
  badge: string;
  section: DesktopRouteSection;
  icon: LucideIcon;
  iconTone: string;
  stage?: DesktopRouteStage;
  showInPrimaryNav?: boolean;
  requiresAuth?: boolean;
  requiresAssistant?: boolean;
}

export const DESKTOP_ROUTE_META: Record<DesktopRouteKey, DesktopRouteMeta> = {
  home: {
    key: "home",
    title: "Overview",
    path: DASHBOARD_ROUTE_PATHS.home,
    publicHref: DASHBOARD_ROUTE_PATHS.home,
    description: "Native mission control for desktop identity, runtime posture, and operator actions.",
    badge: "mission control",
    section: "home",
    icon: Activity,
    iconTone: "text-cyan-300 bg-cyan-400/10",
  },
  agents: {
    key: "agents",
    title: "Agents",
    path: DASHBOARD_ROUTE_PATHS.agents,
    publicHref: DASHBOARD_ROUTE_PATHS.agents,
    description: "Desktop-native registry for assistants, lifecycle control, and fleet ownership.",
    badge: "core ops",
    section: "core",
    icon: Bot,
    iconTone: "text-cyan-300 bg-cyan-400/10",
    requiresAuth: true,
  },
  deployments: {
    key: "deployments",
    title: "Deployments",
    path: DASHBOARD_ROUTE_PATHS.deployments,
    publicHref: DASHBOARD_ROUTE_PATHS.deployments,
    description: "Rollout posture, replica control, and runtime-aware deployment recovery.",
    badge: "core ops",
    section: "core",
    icon: Layers,
    iconTone: "text-emerald-300 bg-emerald-400/10",
    requiresAuth: true,
  },
  documents: {
    key: "documents",
    title: "Documents",
    path: DASHBOARD_ROUTE_PATHS.documents,
    publicHref: DASHBOARD_ROUTE_PATHS.documents,
    description: "Document workflow templates, artifact handling, and hybrid managed or local execution.",
    badge: "execution",
    section: "execution",
    icon: FileText,
    iconTone: "text-amber-300 bg-amber-400/10",
    requiresAuth: true,
  },
  reasoning: {
    key: "reasoning",
    title: "Reasoning",
    path: DASHBOARD_ROUTE_PATHS.reasoning,
    publicHref: DASHBOARD_ROUTE_PATHS.reasoning,
    description: "Autoreason refinement jobs with blind judging, artifact capture, and run-linked traces.",
    badge: "execution",
    section: "execution",
    icon: Brain,
    iconTone: "text-violet-300 bg-violet-400/10",
    requiresAuth: true,
  },
  runs: {
    key: "runs",
    title: "Runs",
    path: DASHBOARD_ROUTE_PATHS.runs,
    publicHref: DASHBOARD_ROUTE_PATHS.runs,
    description: "Recent execution history with direct machine-local follow-up actions.",
    badge: "core ops",
    section: "core",
    icon: History,
    iconTone: "text-cyan-300 bg-cyan-400/10",
    requiresAuth: true,
  },
  monitoring: {
    key: "monitoring",
    title: "Monitoring",
    path: DASHBOARD_ROUTE_PATHS.monitoring,
    publicHref: DASHBOARD_ROUTE_PATHS.monitoring,
    description: "Alert pressure, gateway health, governance state, and operator-visible runtime condition.",
    badge: "core ops",
    section: "core",
    icon: BellRing,
    iconTone: "text-sky-300 bg-sky-400/10",
    requiresAuth: true,
  },
  autonomy: {
    key: "autonomy",
    title: "Autonomy",
    path: DASHBOARD_ROUTE_PATHS.autonomy,
    publicHref: DASHBOARD_ROUTE_PATHS.autonomy,
    description: "Local autonomy daemon, queue, runner, and report posture from the live workspace contract.",
    badge: "local autonomy",
    section: "execution",
    icon: Bot,
    iconTone: "text-fuchsia-300 bg-fuchsia-400/10",
    stage: "preview",
    showInPrimaryNav: false,
  },
  traces: {
    key: "traces",
    title: "Traces",
    path: DASHBOARD_ROUTE_PATHS.traces,
    publicHref: DASHBOARD_ROUTE_PATHS.traces,
    description: "Trace exploration tied to real runs and machine-aware debugging context.",
    badge: "execution",
    section: "execution",
    icon: Workflow,
    iconTone: "text-sky-300 bg-sky-400/10",
    requiresAuth: true,
  },
  observability: {
    key: "observability",
    title: "Observability",
    path: DASHBOARD_ROUTE_PATHS.observability,
    publicHref: DASHBOARD_ROUTE_PATHS.observability,
    description: "Desktop-native event and telemetry surface over the live observability contracts.",
    badge: "execution",
    section: "execution",
    icon: Radar,
    iconTone: "text-emerald-300 bg-emerald-400/10",
    requiresAuth: true,
  },
  sessions: {
    key: "sessions",
    title: "Sessions",
    path: DASHBOARD_ROUTE_PATHS.sessions,
    publicHref: DASHBOARD_ROUTE_PATHS.sessions,
    description: "Local and cloud session activity in one native workspace.",
    badge: "execution",
    section: "execution",
    icon: Users,
    iconTone: "text-cyan-300 bg-cyan-400/10",
    requiresAuth: true,
    requiresAssistant: true,
  },
  apiKeys: {
    key: "apiKeys",
    title: "API Keys",
    path: DASHBOARD_ROUTE_PATHS.apiKeys,
    publicHref: DASHBOARD_ROUTE_PATHS.apiKeys,
    description: "Native key issuance, rotation, revocation, and one-time secret handling.",
    badge: "admin",
    section: "admin",
    icon: KeyRound,
    iconTone: "text-amber-300 bg-amber-400/10",
    requiresAuth: true,
  },
  budgets: {
    key: "budgets",
    title: "Usage",
    path: DASHBOARD_ROUTE_PATHS.budgets,
    publicHref: DASHBOARD_ROUTE_PATHS.budgets,
    description: "Usage, credit posture, and cost signals with local runtime context nearby.",
    badge: "admin",
    section: "admin",
    icon: Wallet,
    iconTone: "text-emerald-300 bg-emerald-400/10",
    requiresAuth: true,
  },
  webhooks: {
    key: "webhooks",
    title: "Connectors",
    path: DASHBOARD_ROUTE_PATHS.webhooks,
    publicHref: DASHBOARD_ROUTE_PATHS.webhooks,
    description: "Outbound delivery endpoints and test flows without leaving the desktop shell.",
    badge: "admin",
    section: "admin",
    icon: Webhook,
    iconTone: "text-fuchsia-300 bg-fuchsia-400/10",
    requiresAuth: true,
  },
  swarm: {
    key: "swarm",
    title: "Swarm",
    path: DASHBOARD_ROUTE_PATHS.swarm,
    publicHref: DASHBOARD_ROUTE_PATHS.swarm,
    description: "Grouped agent topology and scaling posture with native runtime context.",
    badge: "support",
    section: "support",
    icon: GitBranchPlus,
    iconTone: "text-cyan-300 bg-cyan-400/10",
    requiresAuth: true,
  },
  security: {
    key: "security",
    title: "Access",
    path: DASHBOARD_ROUTE_PATHS.security,
    publicHref: DASHBOARD_ROUTE_PATHS.security,
    description: "Operator session posture, token state, key inventory, and trust boundaries.",
    badge: "admin",
    section: "admin",
    icon: ShieldCheck,
    iconTone: "text-amber-300 bg-amber-400/10",
    requiresAuth: true,
  },
  orchestration: {
    key: "orchestration",
    title: "Orchestration",
    path: DASHBOARD_ROUTE_PATHS.orchestration,
    publicHref: DASHBOARD_ROUTE_PATHS.orchestration,
    description: "Workflow lanes, automation posture, and native desktop orchestration context.",
    badge: "admin",
    section: "admin",
    icon: Network,
    iconTone: "text-sky-300 bg-sky-400/10",
    stage: "preview",
    showInPrimaryNav: false,
    requiresAuth: true,
  },
  memory: {
    key: "memory",
    title: "Memory",
    path: DASHBOARD_ROUTE_PATHS.memory,
    publicHref: DASHBOARD_ROUTE_PATHS.memory,
    description: "Context retention posture, workspace memory readiness, and future memory controls.",
    badge: "admin",
    section: "admin",
    icon: MemoryStick,
    iconTone: "text-violet-300 bg-violet-400/10",
    stage: "preview",
    showInPrimaryNav: false,
    requiresAuth: true,
  },
  analytics: {
    key: "analytics",
    title: "Analytics",
    path: DASHBOARD_ROUTE_PATHS.analytics,
    publicHref: DASHBOARD_ROUTE_PATHS.analytics,
    description: "Trends, latency, and fleet activity summaries rendered in the native shell.",
    badge: "admin",
    section: "admin",
    icon: BarChart3,
    iconTone: "text-fuchsia-300 bg-fuchsia-400/10",
    requiresAuth: true,
  },
  channels: {
    key: "channels",
    title: "Channels",
    path: DASHBOARD_ROUTE_PATHS.channels,
    publicHref: DASHBOARD_ROUTE_PATHS.channels,
    description: "Channel posture, assistant bindings, and local communication defaults.",
    badge: "support",
    section: "support",
    icon: MessagesSquare,
    iconTone: "text-cyan-300 bg-cyan-400/10",
    stage: "preview",
    showInPrimaryNav: false,
    requiresAuth: true,
    requiresAssistant: true,
  },
  templates: {
    key: "templates",
    title: "Templates",
    path: DASHBOARD_ROUTE_PATHS.templates,
    publicHref: DASHBOARD_ROUTE_PATHS.templates,
    description: "Starter and custom agent templates backed by the workspace catalog.",
    badge: "workspace",
    section: "support",
    icon: LayoutGrid,
    iconTone: "text-violet-300 bg-violet-400/10",
    stage: "preview",
    showInPrimaryNav: false,
    requiresAuth: true,
  },
  notifications: {
    key: "notifications",
    title: "Notifications",
    path: DASHBOARD_ROUTE_PATHS.notifications,
    publicHref: DASHBOARD_ROUTE_PATHS.notifications,
    description: "Live operator notifications and read state from the dashboard contract.",
    badge: "support",
    section: "support",
    icon: BellRing,
    iconTone: "text-sky-300 bg-sky-400/10",
    stage: "preview",
    showInPrimaryNav: false,
    requiresAuth: true,
  },
  standup: {
    key: "standup",
    title: "Standup",
    path: DASHBOARD_ROUTE_PATHS.standup,
    publicHref: DASHBOARD_ROUTE_PATHS.standup,
    description: "Current standup summary, blockers, and recent execution context.",
    badge: "support",
    section: "support",
    icon: Users,
    iconTone: "text-emerald-300 bg-emerald-400/10",
    stage: "preview",
    showInPrimaryNav: false,
    requiresAuth: true,
  },
  history: {
    key: "history",
    title: "History",
    path: DASHBOARD_ROUTE_PATHS.history,
    publicHref: DASHBOARD_ROUTE_PATHS.history,
    description: "Native audit trail entrypoint for recent operator actions and local recovery context.",
    badge: "support",
    section: "support",
    icon: History,
    iconTone: "text-slate-200 bg-white/10",
    stage: "redirect",
    showInPrimaryNav: false,
    requiresAuth: true,
  },
  skills: {
    key: "skills",
    title: "Skills",
    path: DASHBOARD_ROUTE_PATHS.skills,
    publicHref: DASHBOARD_ROUTE_PATHS.skills,
    description: "Installed assistant capabilities and native workspace skill posture.",
    badge: "support",
    section: "support",
    icon: Brain,
    iconTone: "text-sky-300 bg-sky-400/10",
    stage: "preview",
    showInPrimaryNav: false,
    requiresAuth: true,
    requiresAssistant: true,
  },
  spawn: {
    key: "spawn",
    title: "Spawn",
    path: DASHBOARD_ROUTE_PATHS.spawn,
    publicHref: DASHBOARD_ROUTE_PATHS.spawn,
    description: "Native entrypoint for creating new assistants and local operator seat expansion.",
    badge: "support",
    section: "support",
    icon: ListTree,
    iconTone: "text-emerald-300 bg-emerald-400/10",
    stage: "redirect",
    showInPrimaryNav: false,
    requiresAuth: true,
  },
  logs: {
    key: "logs",
    title: "Logs",
    path: DASHBOARD_ROUTE_PATHS.logs,
    publicHref: DASHBOARD_ROUTE_PATHS.logs,
    description: "Real-time step timeline and execution log stream for agent runs.",
    badge: "execution trace",
    section: "support",
    icon: TerminalSquare,
    iconTone: "text-slate-200 bg-white/10",
    stage: "stable",
    showInPrimaryNav: false,
    requiresAuth: true,
  },
  control: {
    key: "control",
    title: "Settings",
    path: DASHBOARD_ROUTE_PATHS.control,
    publicHref: DASHBOARD_ROUTE_PATHS.control,
    description: "Bridge diagnostics, runtime repair, governance control, and desktop environment inspection.",
    badge: "advanced diagnostics",
    section: "support",
    icon: Activity,
    iconTone: "text-cyan-300 bg-cyan-400/10",
  },
};

export const DESKTOP_ROUTE_ORDER: DesktopRouteKey[] = [
  "home",
  "agents",
  "deployments",
  "runs",
  "monitoring",
  "autonomy",
  "documents",
  "reasoning",
  "traces",
  "observability",
  "sessions",
  "apiKeys",
  "budgets",
  "analytics",
  "webhooks",
  "security",
  "orchestration",
  "memory",
  "swarm",
  "channels",
  "templates",
  "notifications",
  "standup",
  "history",
  "skills",
  "spawn",
  "logs",
  "control",
];

export const PRIMARY_DESKTOP_ROUTE_ORDER: DesktopRouteKey[] = DESKTOP_ROUTE_ORDER.filter(
  (key) => DESKTOP_ROUTE_META[key].showInPrimaryNav !== false,
);

const DESKTOP_ROUTE_PATH_TO_KEY = Object.values(DESKTOP_ROUTE_META).reduce<Record<string, DesktopRouteKey>>(
  (accumulator, meta) => {
    accumulator[meta.path] = meta.key;
    return accumulator;
  },
  {},
);

export function getDesktopRouteKeyForPath(pathname: string | null | undefined): DesktopRouteKey {
  if (!pathname) {
    return "home";
  }

  return DESKTOP_ROUTE_PATH_TO_KEY[pathname] || "home";
}
