import type { LucideIcon } from "lucide-react";
import {
  Activity,
  BarChart3,
  BellRing,
  Bot,
  Brain,
  ClipboardCheck,
  FileText,
  Gavel,
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
export type DesktopRouteSurface = "native" | "shared" | "settings";

export type DesktopRouteKey =
  | "home"
  | "agents"
  | "deployments"
  | "documents"
  | "reasoning"
  | "runs"
  | "monitoring"
  | "approvals"
  | "audit"
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

export type DashboardRoutePath = `/dashboard${string}`;

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
  surface?: DesktopRouteSurface;
  stage?: DesktopRouteStage;
  showInPrimaryNav?: boolean;
  requiresAuth?: boolean;
  requiresAssistant?: boolean;
}

export const DESKTOP_ROUTE_META: Record<DesktopRouteKey, DesktopRouteMeta> = {
  home: {
    key: "home",
    title: "Overview",
    path: "/dashboard",
    publicHref: "/dashboard",
    description: "Native overview of desktop identity, runtime posture, and operator actions.",
    badge: "operator overview",
    section: "home",
    icon: Activity,
    iconTone: "text-cyan-300 bg-cyan-400/10",
  },
  agents: {
    key: "agents",
    title: "Agents",
    path: "/dashboard/agents",
    publicHref: "/dashboard/agents",
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
    path: "/dashboard/deployments",
    publicHref: "/dashboard/deployments",
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
    path: "/dashboard/documents",
    publicHref: "/dashboard/documents",
    description: "Document workflow templates, artifact handling, and hybrid managed or local execution.",
    badge: "execution",
    section: "execution",
    icon: FileText,
    iconTone: "text-amber-300 bg-amber-400/10",
    surface: "shared",
    requiresAuth: true,
  },
  reasoning: {
    key: "reasoning",
    title: "Reasoning",
    path: "/dashboard/reasoning",
    publicHref: "/dashboard/reasoning",
    description: "Autoreason refinement jobs with blind judging, artifact capture, and run-linked traces.",
    badge: "execution",
    section: "execution",
    icon: Brain,
    iconTone: "text-violet-300 bg-violet-400/10",
    surface: "shared",
    requiresAuth: true,
  },
  runs: {
    key: "runs",
    title: "Runs",
    path: "/dashboard/runs",
    publicHref: "/dashboard/runs",
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
    path: "/dashboard/monitoring",
    publicHref: "/dashboard/monitoring",
    description: "Alert pressure, gateway health, governance state, and operator-visible runtime condition.",
    badge: "core ops",
    section: "core",
    icon: BellRing,
    iconTone: "text-sky-300 bg-sky-400/10",
    requiresAuth: true,
  },
  approvals: {
    key: "approvals",
    title: "Approvals",
    path: "/dashboard/approvals",
    publicHref: "/dashboard/approvals",
    description: "Human review queue for sensitive actions, requester context, and canonical decisions.",
    badge: "human control gate",
    section: "core",
    icon: Gavel,
    iconTone: "text-amber-300 bg-amber-400/10",
    surface: "shared",
    requiresAuth: true,
  },
  audit: {
    key: "audit",
    title: "Audit",
    path: "/dashboard/audit",
    publicHref: "/dashboard/audit",
    description: "Attributable control-plane events, redacted evidence inspection, and scoped export.",
    badge: "governance ledger",
    section: "admin",
    icon: ClipboardCheck,
    iconTone: "text-emerald-300 bg-emerald-400/10",
    surface: "shared",
    requiresAuth: true,
  },
  autonomy: {
    key: "autonomy",
    title: "Autonomy",
    path: "/dashboard/autonomy",
    publicHref: "/dashboard/autonomy",
    description: "Local autonomy daemon, queue, runner, and report posture from the live workspace contract.",
    badge: "local autonomy",
    section: "execution",
    icon: Bot,
    iconTone: "text-fuchsia-300 bg-fuchsia-400/10",
    surface: "shared",
    stage: "stable",
    requiresAuth: true,
  },
  traces: {
    key: "traces",
    title: "Traces",
    path: "/dashboard/traces",
    publicHref: "/dashboard/traces",
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
    path: "/dashboard/observability",
    publicHref: "/dashboard/observability",
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
    path: "/dashboard/sessions",
    publicHref: "/dashboard/sessions",
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
    path: "/dashboard/api-keys",
    publicHref: "/dashboard/api-keys",
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
    path: "/dashboard/budgets",
    publicHref: "/dashboard/budgets",
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
    path: "/dashboard/webhooks",
    publicHref: "/dashboard/webhooks",
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
    path: "/dashboard/swarm",
    publicHref: "/dashboard/swarm",
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
    path: "/dashboard/security",
    publicHref: "/dashboard/security",
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
    path: "/dashboard/orchestration",
    publicHref: "/dashboard/orchestration",
    description: "Live workflow lanes, approvals, recovery posture, and autonomy queue context.",
    badge: "admin",
    section: "admin",
    icon: Network,
    iconTone: "text-sky-300 bg-sky-400/10",
    surface: "shared",
    stage: "stable",
    requiresAuth: true,
  },
  memory: {
    key: "memory",
    title: "Memory",
    path: "/dashboard/memory",
    publicHref: "/dashboard/memory",
    description: "Retained session context, source activity, and workspace memory artifacts.",
    badge: "admin",
    section: "admin",
    icon: MemoryStick,
    iconTone: "text-violet-300 bg-violet-400/10",
    surface: "shared",
    stage: "stable",
    requiresAuth: true,
  },
  analytics: {
    key: "analytics",
    title: "Analytics",
    path: "/dashboard/analytics",
    publicHref: "/dashboard/analytics",
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
    path: "/dashboard/channels",
    publicHref: "/dashboard/channels",
    description: "Channel posture, assistant bindings, and local communication defaults.",
    badge: "support",
    section: "support",
    icon: MessagesSquare,
    iconTone: "text-cyan-300 bg-cyan-400/10",
    surface: "shared",
    stage: "stable",
    requiresAuth: true,
    requiresAssistant: true,
  },
  templates: {
    key: "templates",
    title: "Templates",
    path: "/dashboard/templates",
    publicHref: "/dashboard/templates",
    description: "Starter and custom agent templates backed by the workspace catalog.",
    badge: "workspace",
    section: "support",
    icon: LayoutGrid,
    iconTone: "text-violet-300 bg-violet-400/10",
    surface: "shared",
    stage: "stable",
    requiresAuth: true,
  },
  notifications: {
    key: "notifications",
    title: "Notifications",
    path: "/dashboard/notifications",
    publicHref: "/dashboard/notifications",
    description: "Live operator notifications and read state from the dashboard contract.",
    badge: "support",
    section: "support",
    icon: BellRing,
    iconTone: "text-sky-300 bg-sky-400/10",
    surface: "shared",
    stage: "stable",
    requiresAuth: true,
  },
  standup: {
    key: "standup",
    title: "Standup",
    path: "/dashboard/standup",
    publicHref: "/dashboard/standup",
    description: "Current standup summary, blockers, and recent execution context.",
    badge: "support",
    section: "support",
    icon: Users,
    iconTone: "text-emerald-300 bg-emerald-400/10",
    surface: "shared",
    stage: "stable",
    requiresAuth: true,
  },
  history: {
    key: "history",
    title: "History",
    path: "/dashboard/history",
    publicHref: "/dashboard/history",
    description: "Live execution history with recorded run activity and trace context.",
    badge: "support",
    section: "support",
    icon: History,
    iconTone: "text-slate-200 bg-white/10",
    surface: "shared",
    stage: "stable",
    requiresAuth: true,
  },
  skills: {
    key: "skills",
    title: "Skills",
    path: "/dashboard/skills",
    publicHref: "/dashboard/skills",
    description: "Installed assistant capabilities and native workspace skill posture.",
    badge: "support",
    section: "support",
    icon: Brain,
    iconTone: "text-sky-300 bg-sky-400/10",
    surface: "shared",
    stage: "stable",
    requiresAuth: true,
    requiresAssistant: true,
  },
  spawn: {
    key: "spawn",
    title: "Spawn",
    path: "/dashboard/spawn",
    publicHref: "/dashboard/spawn",
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
    path: "/dashboard/logs",
    publicHref: "/dashboard/logs",
    description: "Real-time step timeline and execution log stream for agent runs.",
    badge: "execution trace",
    section: "support",
    icon: TerminalSquare,
    iconTone: "text-slate-200 bg-white/10",
    stage: "stable",
    requiresAuth: true,
  },
  control: {
    key: "control",
    title: "Settings",
    path: "/dashboard/control",
    publicHref: "/dashboard/control",
    description: "Bridge diagnostics, runtime repair, governance control, and desktop environment inspection.",
    badge: "advanced diagnostics",
    section: "support",
    icon: Activity,
    iconTone: "text-cyan-300 bg-cyan-400/10",
    surface: "settings",
  },
};

const DESKTOP_ROUTE_SECTION_ORDER: DesktopRouteSection[] = [
  "home",
  "core",
  "execution",
  "admin",
  "support",
];

export const DESKTOP_ROUTE_ORDER = (Object.keys(DESKTOP_ROUTE_META) as DesktopRouteKey[]).sort(
  (left, right) =>
    DESKTOP_ROUTE_SECTION_ORDER.indexOf(DESKTOP_ROUTE_META[left].section) -
    DESKTOP_ROUTE_SECTION_ORDER.indexOf(DESKTOP_ROUTE_META[right].section),
);

export const DASHBOARD_ROUTE_PATHS = Object.fromEntries(
  DESKTOP_ROUTE_ORDER.map((key) => [key, DESKTOP_ROUTE_META[key].path]),
) as Record<DesktopRouteKey, DashboardRoutePath>;

export const PRIMARY_DESKTOP_ROUTE_ORDER: DesktopRouteKey[] = DESKTOP_ROUTE_ORDER.filter(
  (key) => DESKTOP_ROUTE_META[key].showInPrimaryNav !== false,
);

export const STABLE_DESKTOP_ROUTE_ORDER: DesktopRouteKey[] = DESKTOP_ROUTE_ORDER.filter(
  (key) => (DESKTOP_ROUTE_META[key].stage ?? "stable") === "stable",
);

const DESKTOP_ROUTE_MATCH_ORDER = [...DESKTOP_ROUTE_ORDER].sort(
  (left, right) => DESKTOP_ROUTE_META[right].path.length - DESKTOP_ROUTE_META[left].path.length,
);

const LEGACY_WORKSPACE_PANES: Partial<Record<DesktopRouteKey, string>> = {
  home: "overview",
  agents: "fleet",
  deployments: "rollouts",
  runs: "operations",
  apiKeys: "api-keys",
  orchestration: "automation",
};

export type DesktopRouteWindowRole = "workspace" | "sessions" | "traces" | "settings";

function normalizeDesktopPath(pathname: string | null | undefined) {
  const path = pathname?.split(/[?#]/, 1)[0] || "/dashboard";
  return path.length > 1 ? path.replace(/\/+$/, "") : path;
}

export function isDesktopRoutePathActive(
  pathname: string | null | undefined,
  routeKey: DesktopRouteKey,
) {
  const path = normalizeDesktopPath(pathname);
  const routePath = DESKTOP_ROUTE_META[routeKey].path;

  if (routeKey === "home") {
    return path === routePath;
  }

  return path === routePath || path.startsWith(`${routePath}/`);
}

export function getDesktopRouteKeyForPath(pathname: string | null | undefined): DesktopRouteKey {
  return (
    DESKTOP_ROUTE_MATCH_ORDER.find((key) => isDesktopRoutePathActive(pathname, key)) ?? "home"
  );
}

export function getDesktopRouteSurface(routeKey: DesktopRouteKey): DesktopRouteSurface {
  return DESKTOP_ROUTE_META[routeKey].surface ?? "native";
}

export function getDesktopWindowRoleForRoute(routeKey: DesktopRouteKey): DesktopRouteWindowRole {
  if (routeKey === "control") {
    return "settings";
  }

  if (routeKey === "sessions") {
    return "sessions";
  }

  if (routeKey === "traces" || routeKey === "logs") {
    return "traces";
  }

  return "workspace";
}

export function getDesktopWindowRoleForPath(
  pathname: string | null | undefined,
): DesktopRouteWindowRole {
  return getDesktopWindowRoleForRoute(getDesktopRouteKeyForPath(pathname));
}

export function getDesktopWorkspacePaneForRoute(routeKey: DesktopRouteKey) {
  return LEGACY_WORKSPACE_PANES[routeKey] ?? routeKey;
}

export function getDesktopWorkspacePaneForPath(pathname: string | null | undefined) {
  return getDesktopWorkspacePaneForRoute(getDesktopRouteKeyForPath(pathname));
}
