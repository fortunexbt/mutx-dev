"use client";

import type { FormEvent, ReactNode } from "react";
import { useEffect, useMemo, useState } from "react";
import {
  ArrowRight,
  Bot,
  Copy,
  FolderOpen,
  Globe,
  KeyRound,
  Loader2,
  Play,
  Plus,
  Power,
  RefreshCw,
  Shield,
  TerminalSquare,
  Trash2,
  Wrench,
  Zap,
} from "lucide-react";

import { DesktopOperatorCockpit } from "@/components/desktop/DesktopOperatorCockpit";
import {
  normalizeCollection,
  readJson,
  writeJson,
  type ApiRequestError,
} from "@/components/app/http";
import { RouteHeader } from "@/components/dashboard/RouteHeader";
import { StatusBadge } from "@/components/dashboard/StatusBadge";
import {
  LiveEmptyState,
  LiveErrorState,
  LiveKpiGrid,
  LivePanel,
  LiveStatCard,
  asDashboardStatus,
  formatCurrency,
  formatDateTime,
  formatRelativeTime,
} from "@/components/dashboard/livePrimitives";
import {
  DESKTOP_ROUTE_META,
  getDesktopRouteKeyForPath,
  getDesktopWindowRoleForPath,
  getDesktopWorkspacePaneForPath,
  type DesktopRouteKey,
} from "@/components/desktop/desktopRouteConfig";
import { DesktopJobNotice } from "@/components/desktop/DesktopJobNotice";
import {
  DESKTOP_ACTION_CLASS,
  DESKTOP_FOCUS_CLASS,
} from "@/components/desktop/desktopVisualContract";
import type {
  AssistantOverview,
  DesktopContextMenuItem,
  DesktopRuntimeContext,
  DesktopWindowPayload,
  GovernanceStatus,
  LocalSession,
  RuntimeInfo,
  SystemInfo,
} from "@/components/desktop/types";
import { useDesktopJob } from "@/components/desktop/useDesktopJob";
import { useDesktopDialog } from "@/components/desktop/useDesktopDialog";
import { useDesktopRouteNavigation } from "@/components/desktop/useDesktopRouteNavigation";
import { useDesktopStatus } from "@/components/desktop/useDesktopStatus";
import { useDesktopWindow } from "@/components/desktop/useDesktopWindow";
import { cn } from "@/lib/utils";

const HOSTED_API_URL = "https://api.mutx.dev";
const LOCAL_API_URL = "http://localhost:8000";
const RUN_SELECTION_STORAGE_KEY = "mutx.desktop.selectedRunId";

type AssistantOverviewState = AssistantOverview | { found: false; error?: string };

interface LocalSnapshotState {
  loading: boolean;
  error: string | null;
  runtimeContext: DesktopRuntimeContext | null;
  systemInfo: SystemInfo | null;
  runtimeInfo: RuntimeInfo | null;
  governance: GovernanceStatus | null;
  assistantOverview: AssistantOverviewState | null;
  sessions: LocalSession[];
  controlPlane: {
    ready: boolean;
    path: string;
    exists: boolean;
  } | null;
}

interface CloudState {
  loading: boolean;
  error: string | null;
  authRequired: boolean;
  data: Record<string, unknown>;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function isAuthError(error: unknown) {
  if (!(error instanceof Error)) {
    return false;
  }

  const apiError = error as ApiRequestError & { status?: number };
  return apiError.status === 401 || apiError.status === 403;
}

function getErrorMessage(error: unknown, fallback = "Request failed") {
  if (error instanceof Error) {
    return error.message;
  }

  return fallback;
}

function pickString(
  value: Record<string, unknown> | null | undefined,
  keys: string[],
  fallback = "n/a",
) {
  for (const key of keys) {
    const candidate = value?.[key];
    if (typeof candidate === "string" && candidate.trim().length > 0) {
      return candidate;
    }
  }

  return fallback;
}

function pickNumber(
  value: Record<string, unknown> | null | undefined,
  keys: string[],
  fallback = 0,
) {
  for (const key of keys) {
    const candidate = value?.[key];
    if (typeof candidate === "number" && Number.isFinite(candidate)) {
      return candidate;
    }
  }

  return fallback;
}

function pickBoolean(
  value: Record<string, unknown> | null | undefined,
  keys: string[],
  fallback = false,
) {
  for (const key of keys) {
    const candidate = value?.[key];
    if (typeof candidate === "boolean") {
      return candidate;
    }
  }

  return fallback;
}

function pickStringArray(value: Record<string, unknown> | null | undefined, keys: string[]) {
  for (const key of keys) {
    const candidate = value?.[key];
    if (Array.isArray(candidate)) {
      return candidate.filter((entry): entry is string => typeof entry === "string" && entry.length > 0);
    }
  }

  return [] as string[];
}

function normalizeRecords(value: unknown, keys?: string[]) {
  return normalizeCollection<Record<string, unknown>>(value, keys).filter(isRecord);
}

function titleCase(value: string) {
  return value
    .replaceAll(/[_-]+/g, " ")
    .replaceAll(/\s+/g, " ")
    .trim();
}

function jsonPreview(value: unknown) {
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function formatCount(value: number) {
  return value.toLocaleString();
}

function maskValue(value: string) {
  if (value.length <= 12) {
    return value;
  }

  return `${value.slice(0, 6)}…${value.slice(-4)}`;
}

function SectionButton({
  label,
  icon: Icon,
  onClick,
  tone = "default",
  busy = false,
  disabled = false,
  type = "button",
}: {
  label: string;
  icon: typeof RefreshCw;
  onClick: () => void;
  tone?: "default" | "danger" | "primary";
  busy?: boolean;
  disabled?: boolean;
  type?: "button" | "submit";
}) {
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={busy || disabled}
      className={cn(
        `inline-flex items-center justify-center gap-2 px-3 ${DESKTOP_ACTION_CLASS}`,
        tone === "primary"
          ? "border-[#ff6a32] bg-[#ff571c] text-[#090a08] hover:bg-[#ff7545]"
          : tone === "danger"
            ? "border-[#66302e] bg-[#241312] text-[#ff9b96] hover:border-[#ff6d66]"
            : "border-[#48463e] bg-[#151612] text-[#c8c0b0] hover:border-[#777268] hover:text-[#eee9dc]",
      )}
    >
      {busy ? (
        <Loader2 className="h-4 w-4 motion-safe:animate-spin motion-reduce:animate-none" aria-hidden="true" />
      ) : (
        <Icon className="h-4 w-4" aria-hidden="true" />
      )}
      {label}
    </button>
  );
}

function InlineAlert({
  title,
  message,
  tone = "warning",
}: {
  title: string;
  message: string;
  tone?: "warning" | "danger";
}) {
  return (
    <div
      role={tone === "danger" ? "alert" : "status"}
      className={cn(
        "rounded-[6px] border px-4 py-4",
        tone === "danger"
          ? "border-[#66302e] bg-[#241312] text-[#ff9b96]"
          : "border-[#65502b] bg-[#211a0e] text-[#f4cc82]",
      )}
    >
      <p className="text-sm font-semibold">{title}</p>
      <p className="mt-1 text-sm leading-6 opacity-90">{message}</p>
    </div>
  );
}

function ValueList({
  items,
}: {
  items: Array<{ label: string; value: string }>;
}) {
  return (
    <div className="space-y-3">
      {items.map((item) => (
        <div key={`${item.label}-${item.value}`} className="flex items-start justify-between gap-4 text-sm">
          <span className="text-[#8d867a]">{item.label}</span>
          <span className="max-w-[65%] break-all text-right text-[#c8c0b0]">{item.value}</span>
        </div>
      ))}
    </div>
  );
}

function RecordStack({
  title,
  meta,
  records,
  emptyTitle,
  emptyMessage,
  renderRecord,
}: {
  title: string;
  meta?: string;
  records: Record<string, unknown>[];
  emptyTitle: string;
  emptyMessage: string;
  renderRecord: (record: Record<string, unknown>) => ReactNode;
}) {
  return (
    <LivePanel title={title} meta={meta}>
      {records.length === 0 ? (
        <LiveEmptyState title={emptyTitle} message={emptyMessage} />
      ) : (
        <div className="space-y-3">{records.map(renderRecord)}</div>
      )}
    </LivePanel>
  );
}

function SnapshotDetails({
  title,
  value,
  defaultOpen = false,
}: {
  title: string;
  value: unknown;
  defaultOpen?: boolean;
}) {
  return (
    <details
      open={defaultOpen}
      className="rounded-[6px] border border-[#2b2b26] bg-[#0c0d0b] p-4"
    >
      <summary className={cn("cursor-pointer text-sm font-semibold text-[#eee9dc]", DESKTOP_FOCUS_CLASS)}>{title}</summary>
      <pre className="mt-3 max-h-72 overflow-auto rounded-[4px] border border-[#34342e] bg-[#090a08] p-3 font-[family:var(--font-mono)] text-xs text-[#999284]">
        {jsonPreview(value)}
      </pre>
    </details>
  );
}

function InspectorFactGrid({
  items,
}: {
  items: Array<{ label: string; value: string; tone?: "neutral" | "success" | "warning" | "danger" }>;
}) {
  return (
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-1">
      {items.map((item) => (
        <div
          key={`${item.label}-${item.value}`}
          className={cn(
            "rounded-[4px] border px-4 py-3",
            item.tone === "success"
              ? "border-[#285a43] bg-[#0f2018]"
              : item.tone === "warning"
                ? "border-[#65502b] bg-[#211a0e]"
                : item.tone === "danger"
                  ? "border-[#66302e] bg-[#241312]"
                  : "border-[#34342e] bg-[#151612]",
          )}
        >
          <p className="font-[family:var(--font-mono)] text-[9px] font-semibold uppercase tracking-[0.16em] text-[#8d867a]">{item.label}</p>
          <p className="mt-2 text-sm font-semibold text-[#eee9dc]">{item.value}</p>
        </div>
      ))}
    </div>
  );
}

function SelectionCard({
  active,
  title,
  subtitle,
  detail,
  statusLabel,
  onClick,
  onContextMenu,
  footer,
}: {
  active: boolean;
  title: string;
  subtitle?: string;
  detail?: string;
  statusLabel?: string;
  onClick: () => void;
  onContextMenu?: () => void;
  footer?: ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      onContextMenu={(event) => {
        if (!onContextMenu) {
          return;
        }

        event.preventDefault();
        onContextMenu();
      }}
      className={cn(
        `group relative w-full overflow-hidden rounded-[4px] border px-3.5 py-3 text-left transition-colors ${DESKTOP_FOCUS_CLASS}`,
        active
          ? "border-[#663619] bg-[#21150f] shadow-[inset_3px_0_0_#ff571c]"
          : "border-[#2b2b26] bg-[#11120f] hover:border-[#48463e] hover:bg-[#151612]",
      )}
    >
      <span
        className={cn(
          "absolute inset-y-2 left-1.5 w-[2px] rounded-[4px] transition-colors",
          active ? "bg-[#ff571c]" : "bg-transparent group-hover:bg-[#48463e]",
        )}
      />
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate text-[13px] font-semibold text-[#eee9dc]">{title}</p>
          {subtitle ? <p className="mt-1 text-[12px] text-[#999284]">{subtitle}</p> : null}
        </div>
        {statusLabel ? (
          <StatusBadge status={asDashboardStatus(statusLabel)} label={statusLabel} />
        ) : null}
      </div>
      {detail ? <p className="mt-2.5 text-[12px] leading-5 text-[#999284]">{detail}</p> : null}
      {footer ? <div className="mt-4">{footer}</div> : null}
    </button>
  );
}

function ChipRow({
  items,
  emptyLabel = "No tags",
}: {
  items: string[];
  emptyLabel?: string;
}) {
  return items.length > 0 ? (
    <div className="flex flex-wrap gap-2">
      {items.map((item) => (
        <span
          key={item}
          className="rounded-full border border-[#34342e] bg-[#171813] px-2.5 py-1 font-[family:var(--font-mono)] text-[9px] uppercase tracking-[0.1em] text-[#aaa397]"
        >
          {item}
        </span>
      ))}
    </div>
  ) : (
    <p className="text-sm text-[#8d867a]">{emptyLabel}</p>
  );
}

function WorkbenchMetricStrip({
  items,
}: {
  items: Array<{
    label: string;
    value: string;
    detail: string;
    tone?: "neutral" | "success" | "warning" | "danger";
  }>;
}) {
  return (
    <div className="overflow-hidden rounded-[6px] border border-[#34342e] bg-[#0c0d0b]">
      <div className="grid gap-px bg-[#2b2b26] [grid-template-columns:repeat(auto-fit,minmax(180px,1fr))]">
        {items.map((item) => (
          <div
            key={`${item.label}-${item.value}`}
            className="bg-[#11120f] px-4 py-4"
          >
            <p className="font-[family:var(--font-mono)] text-[9px] font-semibold uppercase tracking-[0.16em] text-[#8d867a]">
              {item.label}
            </p>
            <p
              className={cn(
                "mt-2 font-[family:var(--font-mono)] text-lg font-medium tracking-[-0.03em]",
                item.tone === "success"
                  ? "text-[#78e3b4]"
                  : item.tone === "warning"
                    ? "text-[#f4cc82]"
                    : item.tone === "danger"
                      ? "text-[#ff9b96]"
                      : "text-[#eee9dc]",
              )}
            >
              {item.value}
            </p>
            <p className="mt-2 text-xs leading-5 text-[#999284]">{item.detail}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

function WorkbenchPane({
  title,
  meta,
  toolbar,
  children,
  className,
  bodyClassName,
}: {
  title: string;
  meta?: string;
  toolbar?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
}) {
  return (
    <section
      className={cn(
        "overflow-hidden rounded-[6px] border border-[#2b2b26] bg-[#11120f]",
        className,
      )}
    >
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[#2b2b26] bg-[#0c0d0b] px-4 py-3">
        <div className="min-w-0">
          <p className="font-[family:var(--font-mono)] text-[9px] font-semibold uppercase tracking-[0.16em] text-[#ff8355]">REC / {title}</p>
          {meta ? <p className="mt-1 text-xs text-[#999284]">{meta}</p> : null}
        </div>
        {toolbar ? <div className="flex flex-wrap items-center gap-2">{toolbar}</div> : null}
      </div>
      <div className={cn("p-4", bodyClassName)}>{children}</div>
    </section>
  );
}

function WorkbenchFrame({
  rail,
  detail,
  inspector,
}: {
  rail: ReactNode;
  detail: ReactNode;
  inspector?: ReactNode;
}) {
  return (
    <div
      className={cn(
        "grid gap-4",
        inspector
          ? "min-[1280px]:grid-cols-[minmax(280px,0.82fr)_minmax(0,1.18fr)_minmax(300px,0.9fr)] min-[1800px]:grid-cols-[minmax(320px,0.8fr)_minmax(0,1.32fr)_minmax(360px,0.98fr)]"
          : "min-[1200px]:grid-cols-[minmax(280px,0.82fr)_minmax(0,1.18fr)] min-[1800px]:grid-cols-[minmax(320px,0.78fr)_minmax(0,1.28fr)]",
      )}
    >
      <div className="space-y-4">{rail}</div>
      <div className="space-y-4">{detail}</div>
      {inspector ? <div className="space-y-4">{inspector}</div> : null}
    </div>
  );
}

function InspectorDrawer({
  open,
  title = "Inspector",
  onClose,
  children,
}: {
  open: boolean;
  title?: string;
  onClose: () => void;
  children: ReactNode;
}) {
  const dialogRef = useDesktopDialog<HTMLElement>(open, onClose);

  if (!open) {
    return null;
  }

  return (
    <div className="fixed inset-0 z-[110] flex justify-end bg-[#090a08]/84 motion-reduce:backdrop-blur-none">
      <button
        type="button"
        aria-label="Close inspector"
        className="flex-1 cursor-default"
        onClick={onClose}
      />
      <aside
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="desktop-inspector-title"
        tabIndex={-1}
        className="flex h-full w-full max-w-[430px] flex-col border-l border-[#48463e] bg-[#0d0e0c] shadow-[-24px_0_64px_rgba(0,0,0,0.48)]"
      >
        <div className="flex items-center justify-between gap-3 border-b border-[#34342e] bg-[#0c0d0b] px-4 py-3.5">
          <div>
            <p className="font-[family:var(--font-mono)] text-[9px] font-semibold uppercase tracking-[0.16em] text-[#ff8355]">
              Compact Inspector
            </p>
            <h2 id="desktop-inspector-title" className="mt-1 font-[family:var(--font-site-display)] text-base font-medium text-[#eee9dc]">
              {title}
            </h2>
          </div>
          <SectionButton label="Close" icon={ArrowRight} onClick={onClose} />
        </div>
        <div className="flex-1 overflow-y-auto p-4">{children}</div>
      </aside>
    </div>
  );
}

function useViewportWidth() {
  const [width, setWidth] = useState(() =>
    typeof window === "undefined" ? 1600 : window.innerWidth,
  );

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }

    const onResize = () => setWidth(window.innerWidth);
    onResize();
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  return width;
}

function buildCompanionRoute(destinationKey: DesktopRouteKey, detail: string) {
  const destination = DESKTOP_ROUTE_META[destinationKey];
  return {
    label: `Open ${destination.title}`,
    href: destination.path,
    detail,
  };
}

function getCompanionRoute(routeKey: DesktopRouteKey) {
  switch (routeKey) {
    case "agents":
      return buildCompanionRoute("spawn", "Jump to the native assistant creation lane.");
    case "deployments":
      return buildCompanionRoute("monitoring", "Check rollout health and alert pressure.");
    case "runs":
      return buildCompanionRoute("traces", "Pivot from run history into event drilldown.");
    case "monitoring":
      return buildCompanionRoute("logs", "Move into the machine-local failure surface.");
    case "traces":
      return buildCompanionRoute("runs", "Go back to the parent execution queue.");
    case "observability":
      return buildCompanionRoute("monitoring", "Compare event flow against live alert posture.");
    case "sessions":
      return buildCompanionRoute("channels", "Inspect the assistant communication contract.");
    case "apiKeys":
      return buildCompanionRoute("security", "See key posture alongside operator identity.");
    case "budgets":
      return buildCompanionRoute("analytics", "Compare spend with run and latency trends.");
    case "webhooks":
      return buildCompanionRoute("monitoring", "Watch for failed deliveries and alert overlap.");
    case "security":
      return buildCompanionRoute("apiKeys", "Operate directly on the current key ledger.");
    case "analytics":
      return buildCompanionRoute("budgets", "Return to cost posture and usage events.");
    case "swarm":
      return buildCompanionRoute("deployments", "Move from topology to replica actions.");
    case "channels":
      return buildCompanionRoute("sessions", "Inspect the live session feed for those channels.");
    case "history":
      return buildCompanionRoute("monitoring", "Use alert and health data as the audit anchor.");
    case "skills":
      return buildCompanionRoute("home", "Return to Overview for workspace maintenance.");
    case "spawn":
      return buildCompanionRoute("agents", "Review created assistants in the native registry.");
    case "logs":
      return buildCompanionRoute("control", "Go deeper into bridge and runtime diagnostics.");
    case "orchestration":
      return buildCompanionRoute("deployments", "Move to the live runtime surface while orchestration is still thin.");
    case "memory":
      return buildCompanionRoute("sessions", "Use session and workspace state as today’s memory proxy.");
  }
}

export function DesktopNativeRoutePage({
  routeKey,
}: {
  routeKey: DesktopRouteKey;
}) {
  if (routeKey === "home") {
    return <DesktopOperatorCockpit variant="home" />;
  }

  if (routeKey === "control") {
    return <DesktopOperatorCockpit variant="advanced" />;
  }

  const meta = DESKTOP_ROUTE_META[routeKey];
  const { currentWindow, openWindow, openPreferences, updateCurrentWindow } = useDesktopWindow();
  const navigateCurrentRoute = useDesktopRouteNavigation();
  const { status, refetch } = useDesktopStatus();
  const {
    job,
    resetJob,
    runDoctorJob,
    runControlPlaneStartJob,
    runControlPlaneStopJob,
    runGovernanceRestartJob,
    runRuntimeResyncJob,
    runSetupJob,
  } = useDesktopJob();

  const [localSnapshot, setLocalSnapshot] = useState<LocalSnapshotState>({
    loading: true,
    error: null,
    runtimeContext: null,
    systemInfo: null,
    runtimeInfo: null,
    governance: null,
    assistantOverview: null,
    sessions: [],
    controlPlane: null,
  });
  const [cloudState, setCloudState] = useState<CloudState>({
    loading: meta.requiresAuth ? status.authenticated : false,
    error: null,
    authRequired: false,
    data: {},
  });
  const [actionError, setActionError] = useState<string | null>(null);
  const [utilityBusy, setUtilityBusy] = useState<string | null>(null);
  const [authMode, setAuthMode] = useState<"login" | "register" | "local">("login");
  const [authName, setAuthName] = useState("Mario");
  const [authEmail, setAuthEmail] = useState("");
  const [authPassword, setAuthPassword] = useState("");
  const [authBusy, setAuthBusy] = useState(false);
  const [assistantName, setAssistantName] = useState("Operator Prime");
  const currentPayload = currentWindow.currentWindow.payload;
  const viewportWidth = useViewportWidth();
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(currentPayload.agentId || null);
  const [selectedDeploymentId, setSelectedDeploymentId] = useState<string | null>(
    currentPayload.deploymentId || null,
  );
  const [selectedRunId, setSelectedRunId] = useState<string | null>(currentPayload.runId || null);
  const [selectedAlertId, setSelectedAlertId] = useState<string | null>(null);
  const [selectedObservabilityId, setSelectedObservabilityId] = useState<string | null>(null);
  const [selectedCloudSessionId, setSelectedCloudSessionId] = useState<string | null>(
    currentPayload.sessionId || null,
  );
  const [selectedLocalSessionId, setSelectedLocalSessionId] = useState<string | null>(
    currentPayload.sessionId || null,
  );
  const [selectedTraceId, setSelectedTraceId] = useState<string | null>(null);

  const [agentDraft, setAgentDraft] = useState({
    name: "",
    description: "",
    type: "openai",
  });
  const [deploymentDraft, setDeploymentDraft] = useState({
    agentId: "",
    replicas: "1",
  });
  const [apiKeyName, setApiKeyName] = useState("Operator key");
  const [revealedKey, setRevealedKey] = useState<string | null>(null);
  const [webhookDraft, setWebhookDraft] = useState({
    url: "",
    events: "run.completed, deployment.failed",
    isActive: true,
  });
  const supportsRouteInspector = ["agents", "deployments", "runs", "traces", "sessions"].includes(routeKey);
  const inspectorPreferenceKey = `mutx.desktop.inspector.${currentWindow.currentRole}.${routeKey}`;
  const [inspectorPinned, setInspectorPinned] = useState(true);
  const [inspectorDrawerOpen, setInspectorDrawerOpen] = useState(false);
  const compactViewport = viewportWidth < 1200;
  const mediumViewport = viewportWidth >= 1200 && viewportWidth < 1600;
  const wideViewport = viewportWidth >= 1600;

  useEffect(() => {
    if (typeof window === "undefined" || !supportsRouteInspector) {
      return;
    }

    const saved = window.localStorage.getItem(inspectorPreferenceKey);
    if (saved === "hidden") {
      setInspectorPinned(false);
      return;
    }

    if (saved === "visible") {
      setInspectorPinned(true);
      return;
    }

    setInspectorPinned(true);
  }, [inspectorPreferenceKey, supportsRouteInspector]);

  useEffect(() => {
    if (!compactViewport) {
      setInspectorDrawerOpen(false);
    }
  }, [compactViewport]);

  const shouldShowInlineInspector =
    supportsRouteInspector && (wideViewport || (mediumViewport && inspectorPinned));
  const shouldShowInspectorAction = supportsRouteInspector && !wideViewport;

  const bridgeWarning = status.bridge.state === "error" || Boolean(status.bridge.lastError);
  const assistantMissing = Boolean(meta.requiresAssistant) && !status.assistant?.found;
  const localStackOffline = status.mode === "local" && !status.localControlPlane?.ready;
  const routeNeedsAuth = Boolean(meta.requiresAuth);
  const canLoadCloud = !routeNeedsAuth || status.authenticated;
  const shouldShowAuthPanel = routeNeedsAuth && !status.authenticated;

  function toggleInspector() {
    if (!supportsRouteInspector) {
      return;
    }

    if (compactViewport) {
      setInspectorDrawerOpen((current) => !current);
      return;
    }

    const nextPinned = !inspectorPinned;
    setInspectorPinned(nextPinned);
    if (typeof window !== "undefined") {
      window.localStorage.setItem(inspectorPreferenceKey, nextPinned ? "visible" : "hidden");
    }
  }

  async function syncWindowSelectionPayload(payload: DesktopWindowPayload) {
    await updateCurrentWindow({
      route: currentWindow.currentWindow.route,
      payload: {
        ...currentWindow.currentWindow.payload,
        ...payload,
      },
    });
  }

  async function openDesktopDestination(href: string, payload: DesktopWindowPayload = {}) {
    const destinationRole = getDesktopWindowRoleForPath(href);

    if (destinationRole === "settings") {
      await openPreferences(payload.pane || "advanced");
      return;
    }

    if (destinationRole === "sessions") {
      await openWindow("sessions", payload, href);
      return;
    }

    if (destinationRole === "traces") {
      const destinationKey = getDesktopRouteKeyForPath(href);
      await openWindow(
        "traces",
        {
          ...payload,
          tab: destinationKey === "logs" ? "logs" : payload.tab || "timeline",
        },
        href,
      );
      return;
    }

    const pane = getDesktopWorkspacePaneForPath(href);
    const nextPayload = {
      ...currentWindow.currentWindow.payload,
      ...payload,
      pane,
    };

    if (currentWindow.currentRole === "workspace") {
      navigateCurrentRoute(href, nextPayload);
      return;
    }

    await openWindow("workspace", nextPayload, href);
  }

  async function loadLocalSnapshot() {
    if (!window.mutxDesktop?.isDesktop) {
      return;
    }

    setLocalSnapshot((current) => ({ ...current, loading: true, error: null }));

    const [runtimeContext, runtimeInfo, governance, sessions, controlPlane] =
      await Promise.allSettled([
        window.mutxDesktop.getRuntimeContext(),
        window.mutxDesktop.bridge.runtime.inspect(),
        window.mutxDesktop.bridge.governance.status(),
        window.mutxDesktop.bridge.assistant.sessions(),
        window.mutxDesktop.bridge.controlPlane.status(),
      ]);

    const failures = [
      runtimeContext,
      runtimeInfo,
      governance,
      sessions,
      controlPlane,
    ]
      .filter((result) => result.status === "rejected")
      .map((result) => getErrorMessage((result as PromiseRejectedResult).reason, "Local snapshot failed"));

    setLocalSnapshot({
      loading: false,
      error: failures.length > 0 ? failures.join(" · ") : null,
      runtimeContext: runtimeContext.status === "fulfilled" ? runtimeContext.value : null,
      systemInfo: null,
      runtimeInfo: runtimeInfo.status === "fulfilled" ? runtimeInfo.value : null,
      governance: governance.status === "fulfilled" ? governance.value : null,
      assistantOverview: null,
      sessions: sessions.status === "fulfilled" ? sessions.value : [],
      controlPlane: controlPlane.status === "fulfilled" ? controlPlane.value : null,
    });
  }

  async function loadCloudData() {
    if (!canLoadCloud) {
      setCloudState({
        loading: false,
        error: null,
        authRequired: true,
        data: {},
      });
      return;
    }

    setCloudState((current) => ({ ...current, loading: true, error: null, authRequired: false }));

    try {
      let nextData: Record<string, unknown> = {};

      switch (routeKey) {
        case "agents":
          nextData = {
            agents: await readJson<unknown>("/api/dashboard/agents"),
            deployments: await readJson<unknown>("/api/dashboard/deployments"),
          };
          break;
        case "deployments":
          nextData = {
            deployments: await readJson<unknown>("/api/dashboard/deployments"),
            agents: await readJson<unknown>("/api/dashboard/agents"),
          };
          break;
        case "runs":
          nextData = {
            runs: await readJson<unknown>("/api/dashboard/runs?limit=24"),
          };
          {
            const runRecords = normalizeRecords(nextData.runs, ["items", "runs", "data"]);
            const storedRunId =
              typeof window === "undefined"
                ? ""
                : window.sessionStorage.getItem(RUN_SELECTION_STORAGE_KEY) || "";
            const nextRunId = selectedRunId || storedRunId || pickString(runRecords[0], ["id"], "");
            if (nextRunId) {
              nextData.traces = await readJson<unknown>(
                `/api/dashboard/runs/${encodeURIComponent(nextRunId)}/traces?limit=24`,
              );
              setSelectedRunId(nextRunId);
            }
          }
          break;
        case "monitoring":
          nextData = {
            health: await readJson<unknown>("/api/dashboard/health"),
            alerts: await readJson<unknown>("/api/dashboard/monitoring/alerts?limit=16"),
          };
          break;
        case "traces": {
          const runs = await readJson<unknown>("/api/dashboard/runs?limit=18");
          nextData = { runs };
          const runRecords = normalizeRecords(runs, ["items", "runs", "data"]);
          const storedRunId =
            typeof window === "undefined" ? "" : window.sessionStorage.getItem(RUN_SELECTION_STORAGE_KEY) || "";
          const nextRunId =
            selectedRunId ||
            storedRunId ||
            pickString(runRecords[0], ["id"], "");
          if (nextRunId) {
            nextData.traces = await readJson<unknown>(
              `/api/dashboard/runs/${encodeURIComponent(nextRunId)}/traces?limit=64`,
            );
            setSelectedRunId(nextRunId);
          }
          break;
        }
        case "observability":
          nextData = {
            observability: await readJson<unknown>("/api/dashboard/observability?limit=50"),
          };
          break;
        case "sessions":
          nextData = {
            sessions: await readJson<unknown>("/api/dashboard/sessions"),
            overview: await readJson<unknown>("/api/dashboard/assistant/overview"),
          };
          break;
        case "apiKeys":
          nextData = {
            keys: await readJson<unknown>("/api/api-keys"),
          };
          break;
        case "budgets":
          nextData = {
            budgets: await readJson<unknown>("/api/dashboard/budgets"),
            usage: await readJson<unknown>("/api/dashboard/budgets/usage?period_start=30d"),
            events: await readJson<unknown>("/api/dashboard/usage/events?limit=12"),
            summary: await readJson<unknown>("/api/dashboard/analytics/summary?period_start=30d"),
          };
          break;
        case "webhooks":
          nextData = {
            webhooks: await readJson<unknown>("/api/webhooks"),
          };
          break;
        case "swarm":
          nextData = {
            swarms: await readJson<unknown>("/api/dashboard/swarms?limit=16"),
          };
          break;
        case "security":
          nextData = {
            me: await readJson<unknown>("/api/auth/me"),
            keys: await readJson<unknown>("/api/api-keys"),
          };
          break;
        case "orchestration":
        case "memory":
        case "channels":
        case "history":
        case "skills":
        case "spawn":
        case "logs":
          nextData = {};
          break;
        case "analytics":
          nextData = {
            summary: await readJson<unknown>("/api/dashboard/analytics/summary?period_start=30d"),
            runsTrend: await readJson<unknown>(
              "/api/dashboard/analytics/timeseries?metric=runs&period_start=30d&interval=day",
            ),
            latencyTrend: await readJson<unknown>(
              "/api/dashboard/analytics/timeseries?metric=latency&period_start=30d&interval=day",
            ),
            costs: await readJson<unknown>("/api/dashboard/analytics/costs?period_start=30d"),
          };
          break;
      }

      setCloudState({
        loading: false,
        error: null,
        authRequired: false,
        data: nextData,
      });
    } catch (error) {
      setCloudState({
        loading: false,
        error: isAuthError(error) ? null : getErrorMessage(error, "Cloud data failed to load"),
        authRequired: isAuthError(error),
        data: {},
      });
    }
  }

  async function reloadAll() {
    await Promise.all([refetch(), loadLocalSnapshot(), loadCloudData()]);
  }

  useEffect(() => {
    void loadLocalSnapshot();
  }, [routeKey, status.authenticated, status.assistant?.found]);

  useEffect(() => {
    void loadCloudData();
  }, [routeKey, selectedRunId, status.authenticated, status.assistant?.found]);

  useEffect(() => {
    if (job.status === "completed") {
      void reloadAll();
    }
  }, [job.status]);

  useEffect(() => {
    if (!selectedRunId || typeof window === "undefined") {
      return;
    }

    window.sessionStorage.setItem(RUN_SELECTION_STORAGE_KEY, selectedRunId);
  }, [selectedRunId]);

  useEffect(() => {
    if (currentPayload.agentId && currentPayload.agentId !== selectedAgentId) {
      setSelectedAgentId(currentPayload.agentId);
    }
  }, [currentPayload.agentId, selectedAgentId]);

  useEffect(() => {
    if (currentPayload.deploymentId && currentPayload.deploymentId !== selectedDeploymentId) {
      setSelectedDeploymentId(currentPayload.deploymentId);
    }
  }, [currentPayload.deploymentId, selectedDeploymentId]);

  useEffect(() => {
    if (currentPayload.runId && currentPayload.runId !== selectedRunId) {
      setSelectedRunId(currentPayload.runId);
    }
  }, [currentPayload.runId, selectedRunId]);

  useEffect(() => {
    if (currentPayload.sessionId && currentPayload.sessionId !== selectedCloudSessionId) {
      setSelectedCloudSessionId(currentPayload.sessionId);
    }
    if (currentPayload.sessionId && currentPayload.sessionId !== selectedLocalSessionId) {
      setSelectedLocalSessionId(currentPayload.sessionId);
    }
  }, [currentPayload.sessionId, selectedCloudSessionId, selectedLocalSessionId]);

  useEffect(() => {
    if (selectedAgentId && currentPayload.agentId !== selectedAgentId) {
      void syncWindowSelectionPayload({ agentId: selectedAgentId });
    }
  }, [currentPayload.agentId, selectedAgentId]);

  useEffect(() => {
    if (selectedDeploymentId && currentPayload.deploymentId !== selectedDeploymentId) {
      void syncWindowSelectionPayload({ deploymentId: selectedDeploymentId });
    }
  }, [currentPayload.deploymentId, selectedDeploymentId]);

  useEffect(() => {
    if (selectedRunId && currentPayload.runId !== selectedRunId) {
      void syncWindowSelectionPayload({ runId: selectedRunId });
    }
  }, [currentPayload.runId, selectedRunId]);

  useEffect(() => {
    const selectedSessionId = selectedLocalSessionId || selectedCloudSessionId;
    if (selectedSessionId && currentPayload.sessionId !== selectedSessionId) {
      void syncWindowSelectionPayload({ sessionId: selectedSessionId });
    }
  }, [currentPayload.sessionId, selectedCloudSessionId, selectedLocalSessionId]);

  async function runUtilityAction(action: string, task: () => Promise<unknown>) {
    setActionError(null);
    setUtilityBusy(action);

    try {
      await task();
    } catch (error) {
      setActionError(getErrorMessage(error, "Desktop action failed"));
    } finally {
      setUtilityBusy(null);
    }
  }

  async function copyToClipboard(value: string, successLabel: string) {
    await runUtilityAction(`copy-${successLabel}`, async () => {
      await navigator.clipboard.writeText(value);
    });
  }

  async function showDesktopContextMenu(items: DesktopContextMenuItem[]) {
    if (!window.mutxDesktop?.isDesktop) {
      return;
    }

    const visibleItems = items.filter((item, index) => {
      if (item.type !== "separator") {
        return true;
      }

      const previous = items[index - 1];
      const next = items[index + 1];
      return previous?.type !== "separator" && next?.type !== "separator";
    });

    const result = await window.mutxDesktop.ui.showContextMenu(visibleItems);
    if (!result.success) {
      setActionError(result.error || "Could not open desktop context menu");
    }
  }

  async function ensureLocalMode() {
    await window.mutxDesktop!.setRuntimeContext({
      mode: "local",
      apiUrl: LOCAL_API_URL,
    });

    if (!status.localControlPlane?.ready) {
      await runControlPlaneStartJob();
    }

    await reloadAll();
  }

  async function submitInlineAuth(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setAuthBusy(true);
    setActionError(null);

    try {
      if (authMode === "local" && status.mode !== "local") {
        await ensureLocalMode();
      }

      const payload =
        authMode === "local"
          ? await readJson<Record<string, unknown>>("/api/auth/local-bootstrap", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ name: authName.trim() }),
            })
          : authMode === "register"
            ? await readJson<Record<string, unknown>>("/api/auth/register", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                  name: authName.trim(),
                  email: authEmail.trim(),
                  password: authPassword,
                }),
              })
            : await readJson<Record<string, unknown>>("/api/auth/login", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                  email: authEmail.trim(),
                  password: authPassword,
                }),
              });

      const accessToken = pickString(payload, ["access_token"], "");
      const refreshToken = pickString(payload, ["refresh_token"], "");
      if (authMode === "register" && payload.requires_email_verification === true) {
        throw new Error(
          payload.verification_email_sent === false
            ? "Account created, but the email provider did not accept the verification message. Retry verification from the web app when delivery is configured."
            : "Account created. Confirm the verification email before signing in to the desktop app.",
        );
      }
      if (!accessToken) {
        throw new Error("Authentication succeeded without an access token.");
      }

      await window.mutxDesktop!.bridge.auth.storeTokens(
        accessToken,
        refreshToken || undefined,
        authMode === "local" || status.mode === "local" ? LOCAL_API_URL : HOSTED_API_URL,
      );
      await reloadAll();
    } catch (error) {
      setActionError(getErrorMessage(error, "Authentication failed"));
    } finally {
      setAuthBusy(false);
    }
  }

  async function runAssistantSetup() {
    setActionError(null);

    try {
      await runSetupJob(
        status.mode === "local" ? "local" : "hosted",
        assistantName,
        status.openclaw?.binaryPath ? "import" : "install",
      );
      await reloadAll();
    } catch (error) {
      setActionError(getErrorMessage(error, "Setup failed"));
    }
  }

  async function createAgent(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setActionError(null);
    setUtilityBusy("create-agent");

    try {
      const payload = await writeJson<Record<string, unknown>>("/api/dashboard/agents", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: agentDraft.name.trim(),
          description: agentDraft.description.trim() || undefined,
          type: agentDraft.type,
        }),
      });
      const createdId = pickString(payload, ["id"], "");
      setAgentDraft({ name: "", description: "", type: "openai" });
      if (createdId) {
        setSelectedAgentId(createdId);
      }
      await loadCloudData();
    } catch (error) {
      setActionError(getErrorMessage(error, "Failed to create agent"));
    } finally {
      setUtilityBusy(null);
    }
  }

  async function mutateAgent(id: string, method: "stop" | "delete" | "deploy") {
    setActionError(null);
    setUtilityBusy(`${method}-${id}`);

    try {
      if (method === "stop" || method === "deploy") {
        await writeJson<unknown>(
          `/api/dashboard/agents/${encodeURIComponent(id)}?action=${method === "deploy" ? "deploy" : "stop"}`,
          {
            method: "POST",
          },
        );
      } else {
        await writeJson<unknown>(`/api/dashboard/agents/${encodeURIComponent(id)}`, {
          method: "DELETE",
        });
      }
      await loadCloudData();
    } catch (error) {
      setActionError(getErrorMessage(error, `Failed to ${method} agent`));
    } finally {
      setUtilityBusy(null);
    }
  }

  async function createDeployment(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setActionError(null);
    setUtilityBusy("create-deployment");

    try {
      const payload = await writeJson<Record<string, unknown>>("/api/dashboard/deployments", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          agent_id: deploymentDraft.agentId,
          replicas: Number(deploymentDraft.replicas || "1"),
        }),
      });
      const createdId = pickString(payload, ["id"], "");
      setDeploymentDraft((current) => ({ ...current, replicas: "1" }));
      if (createdId) {
        setSelectedDeploymentId(createdId);
      }
      await loadCloudData();
    } catch (error) {
      setActionError(getErrorMessage(error, "Failed to create deployment"));
    } finally {
      setUtilityBusy(null);
    }
  }

  async function mutateDeployment(id: string, action: "restart" | "delete" | "scale", replicas?: number) {
    setActionError(null);
    setUtilityBusy(`${action}-${id}`);

    try {
      if (action === "delete") {
        await writeJson<unknown>(`/api/dashboard/deployments/${encodeURIComponent(id)}`, {
          method: "DELETE",
        });
      } else if (action === "scale") {
        await writeJson<unknown>(`/api/dashboard/deployments/${encodeURIComponent(id)}?action=scale`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ replicas }),
        });
      } else {
        await writeJson<unknown>(`/api/dashboard/deployments/${encodeURIComponent(id)}?action=restart`, {
          method: "POST",
        });
      }
      await loadCloudData();
    } catch (error) {
      setActionError(getErrorMessage(error, `Failed to ${action} deployment`));
    } finally {
      setUtilityBusy(null);
    }
  }

  async function createApiKey(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setActionError(null);
    setUtilityBusy("create-key");

    try {
      const payload = await writeJson<Record<string, unknown>>("/api/api-keys", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: apiKeyName.trim() }),
      });
      setRevealedKey(pickString(payload, ["key"], ""));
      await loadCloudData();
    } catch (error) {
      setActionError(getErrorMessage(error, "Failed to create API key"));
    } finally {
      setUtilityBusy(null);
    }
  }

  async function mutateApiKey(id: string, action: "rotate" | "delete") {
    setActionError(null);
    setUtilityBusy(`${action}-key-${id}`);

    try {
      if (action === "rotate") {
        const payload = await writeJson<Record<string, unknown>>(`/api/api-keys/${id}/rotate`, {
          method: "POST",
        });
        setRevealedKey(pickString(payload, ["key"], ""));
      } else {
        await writeJson<unknown>(`/api/api-keys/${id}`, {
          method: "DELETE",
        });
      }
      await loadCloudData();
    } catch (error) {
      setActionError(getErrorMessage(error, `Failed to ${action} API key`));
    } finally {
      setUtilityBusy(null);
    }
  }

  async function createWebhook(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setActionError(null);
    setUtilityBusy("create-webhook");

    try {
      await writeJson<unknown>("/api/webhooks", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          url: webhookDraft.url.trim(),
          events: webhookDraft.events
            .split(",")
            .map((entry) => entry.trim())
            .filter(Boolean),
          is_active: webhookDraft.isActive,
        }),
      });
      setWebhookDraft({
        url: "",
        events: "run.completed, deployment.failed",
        isActive: true,
      });
      await loadCloudData();
    } catch (error) {
      setActionError(getErrorMessage(error, "Failed to create webhook"));
    } finally {
      setUtilityBusy(null);
    }
  }

  async function mutateWebhook(id: string, action: "test" | "delete") {
    setActionError(null);
    setUtilityBusy(`${action}-webhook-${id}`);

    try {
      await writeJson<unknown>(
        action === "test" ? `/api/webhooks/${id}/test` : `/api/webhooks/${id}`,
        { method: action === "test" ? "POST" : "DELETE" },
      );
      await loadCloudData();
    } catch (error) {
      setActionError(getErrorMessage(error, `Failed to ${action} webhook`));
    } finally {
      setUtilityBusy(null);
    }
  }

  const headerStats = useMemo(
    (): Array<{
      label: string;
      value: string;
      tone: "success" | "warning" | "danger";
    }> => [
      {
        label: "Operator",
        value: status.authenticated ? status.user?.email || "signed in" : "not signed in",
        tone: status.authenticated ? "success" : "warning",
      },
      {
        label: "Assistant",
        value: status.assistant?.found ? status.assistant.name || "bound" : "not bound",
        tone: status.assistant?.found ? "success" : "warning",
      },
      {
        label: "Bridge",
        value: status.bridge.state || "unknown",
        tone: status.bridge.ready ? "success" : status.bridge.state === "idle" || status.bridge.state === "starting" ? "warning" : "danger",
      },
      {
        label: "Local Stack",
        value: status.localControlPlane?.ready ? "online" : "stopped",
        tone: status.localControlPlane?.ready ? "success" : "warning",
      },
    ],
    [status],
  );

  const localRuntimeSummary = [
    {
      label: "Python",
      value: status.bridge.pythonCommand || "unknown",
      detail: status.bridge.ready
        ? "Desktop bridge is healthy."
        : status.bridge.state === "idle"
          ? "Desktop bridge is cold and will restart on demand."
        : status.bridge.state === "starting"
          ? "Desktop bridge is restarting."
          : status.bridge.lastError || "Bridge is degraded.",
      status: asDashboardStatus(
        status.bridge.ready
          ? "healthy"
          : status.bridge.state === "idle" || status.bridge.state === "starting"
            ? "warning"
            : "error",
      ),
    },
    {
      label: "Gateway",
      value: status.openclaw?.health || "unknown",
      detail: status.openclaw?.gatewayUrl || "Gateway URL is not configured.",
      status: asDashboardStatus(status.openclaw?.health),
    },
    {
      label: "Governance",
      value: status.faramesh?.available ? status.faramesh.health || "active" : "idle",
      detail: localSnapshot.governance?.provider || "No governance daemon available.",
      status: asDashboardStatus(status.faramesh?.health),
    },
    {
      label: "Workspace",
      value: status.assistant?.workspace ? maskValue(status.assistant.workspace) : "not bound",
      detail:
        status.assistant?.workspace ||
        localSnapshot.controlPlane?.path ||
        "No workspace or local control-plane path available yet.",
      status: asDashboardStatus(status.assistant?.workspace ? "ready" : "warning"),
    },
  ];

  const cloudAgents = normalizeRecords(cloudState.data.agents, ["items", "agents", "data"]);
  const cloudDeployments = normalizeRecords(cloudState.data.deployments, ["items", "deployments", "data"]);
  const cloudRuns = normalizeRecords(cloudState.data.runs, ["items", "runs", "data"]);
  const cloudAlerts = normalizeRecords(cloudState.data.alerts, ["items", "alerts", "data"]);
  const cloudObservability = normalizeRecords(cloudState.data.observability, ["items", "events", "data"]);
  const cloudSessions = normalizeRecords(cloudState.data.sessions, ["sessions", "items", "data"]);
  const cloudKeys = normalizeRecords(cloudState.data.keys, ["items", "keys", "api_keys", "data"]);
  const cloudWebhooks = normalizeRecords(cloudState.data.webhooks, ["webhooks", "items", "data"]);
  const cloudSwarms = normalizeRecords(cloudState.data.swarms, ["items", "swarms", "data"]);
  const cloudUsageEvents = normalizeRecords(cloudState.data.events, ["items", "events", "data"]);
  const cloudTraceEvents = normalizeRecords(cloudState.data.traces, ["items", "traces", "data"]);
  const cloudBudgetRecords = normalizeRecords(cloudState.data.budgets, ["items", "budgets", "data"]);
  const analyticsSummary = isRecord(cloudState.data.summary) ? cloudState.data.summary : null;
  const monitoringHealth = isRecord(cloudState.data.health) ? cloudState.data.health : null;
  const cloudOverview = isRecord(cloudState.data.overview) ? cloudState.data.overview : null;
  const cloudSecurityMe = isRecord(cloudState.data.me) ? cloudState.data.me : null;
  const cloudRunsTrend = normalizeRecords(cloudState.data.runsTrend, ["data", "items"]);
  const cloudLatencyTrend = normalizeRecords(cloudState.data.latencyTrend, ["data", "items"]);
  const cloudCosts = isRecord(cloudState.data.costs) ? cloudState.data.costs : null;
  const selectedAgent = cloudAgents.find((agent) => pickString(agent, ["id"], "") === selectedAgentId) || cloudAgents[0] || null;
  const selectedAgentKey = pickString(selectedAgent, ["id"], "");
  const selectedAgentDeployments = cloudDeployments.filter(
    (deployment) => pickString(deployment, ["agent_id"], "") === selectedAgentKey,
  );
  const selectedDeployment =
    cloudDeployments.find((deployment) => pickString(deployment, ["id"], "") === selectedDeploymentId) ||
    cloudDeployments[0] ||
    null;
  const selectedDeploymentReplicas = pickNumber(selectedDeployment, ["replicas"], 1);
  const selectedDeploymentAgent =
    cloudAgents.find(
      (agent) => pickString(agent, ["id"], "") === pickString(selectedDeployment, ["agent_id"], ""),
    ) || null;
  const selectedAlert =
    cloudAlerts.find((alert) => pickString(alert, ["id"], "") === selectedAlertId) || cloudAlerts[0] || null;
  const selectedObservability =
    cloudObservability.find((event) => pickString(event, ["id"], "") === selectedObservabilityId) ||
    cloudObservability[0] ||
    null;
  const selectedCloudSession =
    cloudSessions.find((session) => pickString(session, ["id", "session_id", "key"], "") === selectedCloudSessionId) ||
    (selectedLocalSessionId ? null : cloudSessions[0] || null);
  const selectedLocalSession =
    localSnapshot.sessions.find(
      (session) => session.id === selectedLocalSessionId,
    ) ||
    localSnapshot.sessions.find(
      (session) =>
        session.id === pickString(selectedCloudSession, ["id", "session_id", "key"], "") ||
        session.channel === pickString(selectedCloudSession, ["channel"], "") ||
        session.agent === pickString(selectedCloudSession, ["agent", "assistant", "assistant_name"], ""),
    ) || localSnapshot.sessions[0] || null;
  const selectedRun = cloudRuns.find((run) => pickString(run, ["id"], "") === selectedRunId) || cloudRuns[0] || null;
  const selectedTrace =
    cloudTraceEvents.find(
      (trace) =>
        pickString(trace, ["id"], `${pickNumber(trace, ["sequence"], 0)}`) === selectedTraceId,
    ) ||
    cloudTraceEvents[0] ||
    null;

  useEffect(() => {
    if (!selectedAgentId && cloudAgents.length > 0) {
      setSelectedAgentId(pickString(cloudAgents[0], ["id"], ""));
    }
  }, [cloudAgents, selectedAgentId]);

  useEffect(() => {
    if (!selectedDeploymentId && cloudDeployments.length > 0) {
      setSelectedDeploymentId(pickString(cloudDeployments[0], ["id"], ""));
    }
  }, [cloudDeployments, selectedDeploymentId]);

  useEffect(() => {
    if (selectedCloudSessionId || selectedLocalSessionId) {
      return;
    }

    const nextSessionId =
      pickString(cloudSessions[0], ["id", "session_id", "key"], "") || localSnapshot.sessions[0]?.id || "";
    if (!nextSessionId) {
      return;
    }

    setSelectedCloudSessionId((current) => current || nextSessionId);
    setSelectedLocalSessionId((current) => current || nextSessionId);
  }, [cloudSessions, localSnapshot.sessions, selectedCloudSessionId, selectedLocalSessionId]);

  useEffect(() => {
    if (cloudTraceEvents.length === 0) {
      if (selectedTraceId) {
        setSelectedTraceId(null);
      }
      return;
    }

    const hasSelectedTrace = cloudTraceEvents.some(
      (trace) =>
        pickString(trace, ["id"], `${pickNumber(trace, ["sequence"], 0)}`) === selectedTraceId,
    );

    if (!hasSelectedTrace) {
      setSelectedTraceId(
        pickString(cloudTraceEvents[0], ["id"], `${pickNumber(cloudTraceEvents[0], ["sequence"], 0)}`),
      );
    }
  }, [cloudTraceEvents, selectedTraceId]);
  const companionRoute = getCompanionRoute(routeKey);
  const primaryCollectionCount =
    routeKey === "agents"
      ? cloudAgents.length
      : routeKey === "deployments"
        ? cloudDeployments.length
        : routeKey === "runs"
          ? cloudRuns.length
          : routeKey === "monitoring"
            ? cloudAlerts.length
            : routeKey === "traces"
              ? cloudTraceEvents.length
              : routeKey === "observability"
                ? cloudObservability.length
                : routeKey === "sessions"
                  ? cloudSessions.length
                  : routeKey === "apiKeys"
                    ? cloudKeys.length
                    : routeKey === "budgets"
                      ? cloudUsageEvents.length
                      : routeKey === "webhooks"
                        ? cloudWebhooks.length
                        : routeKey === "analytics"
                          ? cloudRunsTrend.length
                          : routeKey === "swarm"
                            ? cloudSwarms.length
                            : 0;
  const cloudContractState = cloudState.authRequired
    ? "auth required"
    : cloudState.error
      ? "degraded"
      : cloudState.loading
        ? "loading"
        : "live";
  const inspectorFacts = [
    {
      label: "Cloud Contract",
      value: cloudContractState,
      tone:
        cloudContractState === "live"
          ? "success"
          : cloudContractState === "degraded"
            ? "danger"
            : "warning",
    },
    {
      label: "Primary Records",
      value: formatCount(primaryCollectionCount),
      tone: primaryCollectionCount > 0 ? "success" : "neutral",
    },
    {
      label: "Local Sessions",
      value: formatCount(localSnapshot.sessions.length),
      tone: localSnapshot.sessions.length > 0 ? "success" : "neutral",
    },
    {
      label: "Assistant Bind",
      value: status.assistant?.found ? status.assistant.name || "bound" : "missing",
      tone: status.assistant?.found ? "success" : "warning",
    },
    {
      label: "API Target",
      value: localSnapshot.runtimeContext?.mode || status.mode || "unknown",
      tone:
        (localSnapshot.runtimeContext?.mode || status.mode) === "local"
          ? "success"
          : "neutral",
    },
    {
      label: "Bridge Script",
      value: maskValue(status.bridge.scriptPath || "unknown"),
      tone: status.bridge.ready ? "neutral" : "danger",
    },
  ] as const;
  const inspectorRail = (
    <div className="space-y-4 [&_button]:focus-visible:outline [&_button]:focus-visible:outline-2 [&_button]:focus-visible:outline-offset-2 [&_button]:focus-visible:outline-[#ff7847] [&_input]:focus-visible:outline [&_input]:focus-visible:outline-2 [&_input]:focus-visible:outline-offset-2 [&_input]:focus-visible:outline-[#ff7847] [&_select]:focus-visible:outline [&_select]:focus-visible:outline-2 [&_select]:focus-visible:outline-offset-2 [&_select]:focus-visible:outline-[#ff7847]">
      <WorkbenchPane title="Route Inspector" meta="machine-aware">
        <div className="space-y-4">
          <div>
            <p className="text-sm font-semibold text-[#eee9dc]">{meta.title}</p>
            <p className="mt-2 text-sm leading-6 text-[#999284]">{meta.description}</p>
          </div>
          <InspectorFactGrid items={[...inspectorFacts]} />
        </div>
      </WorkbenchPane>

      <WorkbenchPane title="Next Move" meta="route-native">
        <div className="space-y-3">
          {companionRoute ? (
            <div className="rounded-[6px] border border-[#2b2b26] bg-[#11120f] p-4">
              <p className="text-sm font-semibold text-[#eee9dc]">{companionRoute.label}</p>
              <p className="mt-2 text-sm leading-6 text-[#999284]">{companionRoute.detail}</p>
              <div className="mt-4 flex flex-wrap gap-2">
                <SectionButton
                  label={companionRoute.label}
                  icon={ArrowRight}
                  tone="primary"
                  onClick={() => void openDesktopDestination(companionRoute.href)}
                />
              </div>
            </div>
          ) : null}

          <div className="rounded-[6px] border border-[#2b2b26] bg-[#11120f] p-4">
            <p className="text-sm font-semibold text-[#eee9dc]">Operator helpers</p>
            <div className="mt-4 flex flex-wrap gap-2">
              <SectionButton
                label="Copy Workspace"
                icon={Copy}
                disabled={!status.assistant?.workspace}
                onClick={() => void copyToClipboard(status.assistant?.workspace || "", "workspace")}
              />
              <SectionButton
                label="Copy Gateway"
                icon={Copy}
                disabled={!status.openclaw?.gatewayUrl}
                onClick={() => void copyToClipboard(status.openclaw?.gatewayUrl || "", "gateway")}
              />
              <SectionButton
                label="Copy Local Path"
                icon={Copy}
                disabled={!localSnapshot.controlPlane?.path}
                onClick={() => void copyToClipboard(localSnapshot.controlPlane?.path || "", "control-plane")}
              />
            </div>
          </div>
        </div>
      </WorkbenchPane>

      <WorkbenchPane title="Native Traces" meta="local snapshot">
        <div className="space-y-3">
          <ValueList
            items={[
              { label: "Runtime target", value: localSnapshot.runtimeContext?.apiUrl || status.apiUrl || "unknown" },
              { label: "Control plane path", value: localSnapshot.controlPlane?.path || "unknown" },
              { label: "Gateway config", value: pickString(localSnapshot.runtimeInfo?.openclaw || null, ["config_path"], "unknown") },
              { label: "Last sync", value: formatDateTime(status.lastUpdated) },
            ]}
          />
          <SnapshotDetails title="Local Snapshot" value={localSnapshot} />
          <SnapshotDetails title="Cloud Payload" value={cloudState.data} />
        </div>
      </WorkbenchPane>
    </div>
  );
  let routeInspectorContent: ReactNode = inspectorRail;

  const routeContent = (() => {
    switch (routeKey) {
      case "agents":
        return (
          <div className="space-y-4">
            <WorkbenchMetricStrip
              items={[
                {
                  label: "Registered",
                  value: formatCount(cloudAgents.length),
                  detail: "Desktop-visible assistants returned by the cloud contract.",
                  tone: cloudAgents.length > 0 ? "success" : "neutral",
                },
                {
                  label: "Running",
                  value: formatCount(
                    cloudAgents.filter(
                      (agent) => pickString(agent, ["status"], "").toLowerCase() === "running",
                    ).length,
                  ),
                  detail: "Agents already marked running and available for live work.",
                  tone: cloudAgents.some(
                    (agent) => pickString(agent, ["status"], "").toLowerCase() === "running",
                  )
                    ? "success"
                    : "neutral",
                },
                {
                  label: "Linked deploys",
                  value: formatCount(selectedAgentDeployments.length),
                  detail:
                    selectedAgent
                      ? `${pickString(selectedAgent, ["name"], "Selected agent")} is linked to ${selectedAgentDeployments.length} deployment records.`
                      : "Select an agent to inspect its rollout footprint.",
                  tone: selectedAgentDeployments.length > 0 ? "success" : "neutral",
                },
                {
                  label: "Workspace bind",
                  value: status.assistant?.workspace ? "ready" : "missing",
                  detail: status.assistant?.workspace || "No workspace is bound to the desktop operator yet.",
                  tone: status.assistant?.workspace ? "success" : "warning",
                },
              ]}
            />

            <WorkbenchFrame
              rail={
                <>
                  <WorkbenchPane
                    title="Agent Registry"
                    meta={`${cloudAgents.length} assistants`}
                    toolbar={
                      <StatusBadge
                        status={asDashboardStatus(cloudAgents.length > 0 ? "active" : "idle")}
                        label={cloudAgents.length > 0 ? "live" : "empty"}
                      />
                    }
                  >
                    {cloudAgents.length === 0 ? (
                      <LiveEmptyState
                        title="No agents yet"
                        message="Create the first desktop-visible agent and it will appear here immediately."
                      />
                    ) : (
                      <div className="space-y-2">
                        {cloudAgents.map((agent) => {
                          const id = pickString(agent, ["id"], "");
                          const statusLabel = pickString(agent, ["status"], "unknown");
                          return (
                            <SelectionCard
                              key={id}
                              active={id === selectedAgentKey}
                              title={pickString(agent, ["name"], "Unnamed agent")}
                              subtitle={`${pickString(agent, ["type"], "unknown")} · ${maskValue(id)}`}
                              detail={
                                pickString(agent, ["description"], "No description provided.") ||
                                "No description provided."
                              }
                              statusLabel={statusLabel}
                              onClick={() => setSelectedAgentId(id)}
                              onContextMenu={() =>
                                void showDesktopContextMenu([
                                  {
                                    label: "Inspect Agent",
                                    action: {
                                      type: "navigate.current",
                                      route: "/dashboard/agents",
                                      payload: { pane: "fleet", agentId: id },
                                    },
                                  },
                                  {
                                    label: "Open Sessions Window",
                                    action: {
                                      type: "window.open",
                                      role: "sessions",
                                      route: "/dashboard/sessions",
                                      payload: { agentId: id },
                                    },
                                  },
                                  {
                                    label: "Open Deployments",
                                    action: {
                                      type: "window.open",
                                      role: "workspace",
                                      route: "/dashboard/deployments",
                                      payload: { pane: "rollouts", agentId: id },
                                    },
                                  },
                                  { label: "separator", type: "separator" },
                                  {
                                    label: "Copy Agent ID",
                                    action: { type: "clipboard.copy", value: id },
                                  },
                                ])
                              }
                              footer={
                                <div className="flex items-center justify-between gap-3 text-xs text-[#8d867a]">
                                  <span>Updated {formatRelativeTime(pickString(agent, ["updated_at", "created_at"], ""))}</span>
                                  <span>{pickNumber(agent, ["deployment_count"], selectedAgentKey === id ? selectedAgentDeployments.length : 0)} deploys</span>
                                </div>
                              }
                            />
                          );
                        })}
                      </div>
                    )}
                  </WorkbenchPane>

                  <WorkbenchPane title="Provision Agent" meta="desktop-first create">
                    <form className="space-y-4" onSubmit={(event) => void createAgent(event)}>
                      <div className="grid gap-3">
                        <input
                          aria-label="Agent name"
                          value={agentDraft.name}
                          onChange={(event) => setAgentDraft((current) => ({ ...current, name: event.target.value }))}
                          placeholder="Operator Prime"
                          className="rounded-[6px] border border-[#2b3238] bg-[#0c1015] px-3 py-2.5 text-sm text-[#eee9dc] outline-none transition focus:border-[#5c6876]"
                        />
                        <select
                          aria-label="Agent provider"
                          value={agentDraft.type}
                          onChange={(event) => setAgentDraft((current) => ({ ...current, type: event.target.value }))}
                          className="rounded-[6px] border border-[#2b3238] bg-[#0c1015] px-3 py-2.5 text-sm text-[#eee9dc] outline-none transition focus:border-[#5c6876]"
                        >
                          <option value="openai">openai</option>
                          <option value="anthropic">anthropic</option>
                          <option value="custom">custom</option>
                        </select>
                      </div>
                      <textarea
                        aria-label="Agent description"
                        value={agentDraft.description}
                        onChange={(event) =>
                          setAgentDraft((current) => ({ ...current, description: event.target.value }))
                        }
                        rows={4}
                        placeholder="Describe the operator or assistant role."
                        className="w-full rounded-[6px] border border-[#2b3238] bg-[#0c1015] px-3 py-2.5 text-sm text-[#eee9dc] outline-none transition focus:border-[#5c6876]"
                      />
                      <SectionButton
                        label="Create Agent"
                        icon={Plus}
                        tone="primary"
                        busy={utilityBusy === "create-agent"}
                        onClick={() => undefined}
                        type="submit"
                      />
                    </form>
                  </WorkbenchPane>
                </>
              }
              detail={
                <>
                  <WorkbenchPane
                    title={selectedAgent ? pickString(selectedAgent, ["name"], "Agent Detail") : "Agent Detail"}
                    meta={selectedAgent ? maskValue(selectedAgentKey) : "none selected"}
                    toolbar={
                      selectedAgent ? (
                        <StatusBadge
                          status={asDashboardStatus(pickString(selectedAgent, ["status"], "unknown"))}
                          label={pickString(selectedAgent, ["status"], "unknown")}
                        />
                      ) : null
                    }
                  >
                    {selectedAgent ? (
                      <div className="space-y-5">
                        <div className="space-y-3">
                          <div className="flex flex-wrap items-start justify-between gap-3">
                            <div className="min-w-0">
                              <p className="text-[22px] font-semibold tracking-[-0.03em] text-[#f4f7fb]">
                                {pickString(selectedAgent, ["name"], "Unnamed agent")}
                              </p>
                              <p className="mt-2 max-w-3xl text-sm leading-6 text-[#94a0ad]">
                                {pickString(selectedAgent, ["description"], "No description provided.")}
                              </p>
                            </div>
                          </div>
                          <ValueList
                            items={[
                              { label: "Agent ID", value: selectedAgentKey || "unknown" },
                              { label: "Type", value: pickString(selectedAgent, ["type"], "unknown") },
                              { label: "Created", value: formatDateTime(pickString(selectedAgent, ["created_at"], "")) },
                              { label: "Updated", value: formatDateTime(pickString(selectedAgent, ["updated_at"], "")) },
                            ]}
                          />
                        </div>
                        <div className="grid gap-3 md:grid-cols-2">
                          <div className="rounded-[6px] border border-[#2b3238] bg-[#0c1015] px-4 py-3">
                            <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-[#7e8896]">
                              Workspace binding
                            </p>
                            <p className="mt-2 text-sm text-[#f4f7fb]">
                              {status.assistant?.workspace || "No workspace is bound to the operator yet."}
                            </p>
                          </div>
                          <div className="rounded-[6px] border border-[#2b3238] bg-[#0c1015] px-4 py-3">
                            <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-[#7e8896]">
                              Local runtime target
                            </p>
                            <p className="mt-2 text-sm text-[#f4f7fb]">
                              {localSnapshot.runtimeContext?.apiUrl || status.apiUrl || "unknown"}
                            </p>
                          </div>
                        </div>
                        <div className="flex flex-wrap gap-2">
                          <SectionButton
                            label="Stop selected"
                            icon={Power}
                            busy={utilityBusy === `stop-${selectedAgentKey}`}
                            disabled={pickString(selectedAgent, ["status"], "").toLowerCase() !== "running"}
                            onClick={() => void mutateAgent(selectedAgentKey, "stop")}
                          />
                          <SectionButton
                            label="Deploy selected"
                            icon={Play}
                            tone="primary"
                            busy={utilityBusy === `deploy-${selectedAgentKey}`}
                            onClick={() => void mutateAgent(selectedAgentKey, "deploy")}
                          />
                          <SectionButton
                            label="Open Sessions"
                            icon={ArrowRight}
                            onClick={() =>
                              void openDesktopDestination("/dashboard/sessions", {
                                agentId: selectedAgentKey || undefined,
                              })
                            }
                          />
                          <SectionButton
                            label="Delete selected"
                            icon={Trash2}
                            tone="danger"
                            busy={utilityBusy === `delete-${selectedAgentKey}`}
                            onClick={() => void mutateAgent(selectedAgentKey, "delete")}
                          />
                        </div>
                      </div>
                    ) : (
                      <LiveEmptyState
                        title="No selected agent"
                        message="Pick an agent from the registry to inspect ownership, lifecycle, and linked deployments."
                      />
                    )}
                  </WorkbenchPane>

                  <WorkbenchPane title="Deployment Footprint" meta={`${selectedAgentDeployments.length} linked`}>
                    {selectedAgentDeployments.length === 0 ? (
                      <LiveEmptyState
                        title="No deployments linked"
                        message="This agent has no deployment records yet, so rollout posture is still empty."
                      />
                    ) : (
                      <div className="space-y-2">
                        {selectedAgentDeployments.map((deployment) => {
                          const deploymentId = pickString(deployment, ["id"], "");
                          const replicas = pickNumber(deployment, ["replicas"], 1);
                          const deploymentStatus = pickString(deployment, ["status"], "unknown");
                          return (
                            <SelectionCard
                              key={deploymentId}
                              active={deploymentId === pickString(selectedDeployment, ["id"], "")}
                              title={deploymentId}
                              subtitle={`${replicas} replicas · ${deploymentStatus}`}
                              detail={`Started ${formatRelativeTime(pickString(deployment, ["started_at"], ""))}`}
                              statusLabel={deploymentStatus}
                              onClick={() => {
                                setSelectedDeploymentId(deploymentId);
                                void openDesktopDestination("/dashboard/deployments", {
                                  deploymentId,
                                  agentId: selectedAgentKey || undefined,
                                });
                              }}
                              onContextMenu={() =>
                                void showDesktopContextMenu([
                                  {
                                    label: "Inspect Deployment",
                                    action: {
                                      type: "window.open",
                                      role: "workspace",
                                      route: "/dashboard/deployments",
                                      payload: {
                                        pane: "rollouts",
                                        deploymentId,
                                        agentId: selectedAgentKey || undefined,
                                      },
                                    },
                                  },
                                  {
                                    label: "Open Agent",
                                    action: {
                                      type: "window.open",
                                      role: "workspace",
                                      route: "/dashboard/agents",
                                      payload: { pane: "fleet", agentId: selectedAgentKey || undefined },
                                    },
                                  },
                                  { label: "separator", type: "separator" },
                                  {
                                    label: "Copy Deployment ID",
                                    action: { type: "clipboard.copy", value: deploymentId },
                                  },
                                ])
                              }
                            />
                          );
                        })}
                      </div>
                    )}
                  </WorkbenchPane>
                </>
              }
              inspector={shouldShowInlineInspector ? routeInspectorContent : undefined}
            />
          </div>
        );

      case "deployments":
        return (
          <div className="space-y-4">
            <WorkbenchMetricStrip
              items={[
                {
                  label: "Deployments",
                  value: formatCount(cloudDeployments.length),
                  detail: "Live rollout records returned by the control plane.",
                  tone: cloudDeployments.length > 0 ? "success" : "neutral",
                },
                {
                  label: "Running",
                  value: formatCount(
                    cloudDeployments.filter(
                      (deployment) => pickString(deployment, ["status"], "").toLowerCase() === "running",
                    ).length,
                  ),
                  detail: "Deployments currently marked healthy and online.",
                  tone: cloudDeployments.some(
                    (deployment) => pickString(deployment, ["status"], "").toLowerCase() === "running",
                  )
                    ? "success"
                    : "neutral",
                },
                {
                  label: "Replica footprint",
                  value: formatCount(
                    cloudDeployments.reduce(
                      (total, deployment) => total + pickNumber(deployment, ["replicas"], 1),
                      0,
                    ),
                  ),
                  detail: "Total replicas under management in this fetch window.",
                  tone: cloudDeployments.length > 0 ? "neutral" : "warning",
                },
                {
                  label: "Local stack",
                  value: status.localControlPlane?.ready ? "online" : "offline",
                  detail: localSnapshot.controlPlane?.path || "Control plane path is not available.",
                  tone: status.localControlPlane?.ready ? "success" : "warning",
                },
              ]}
            />

            <WorkbenchFrame
              rail={
                <>
                  <WorkbenchPane
                    title="Deployment Rail"
                    meta={`${cloudDeployments.length} rollout records`}
                    toolbar={
                      <StatusBadge
                        status={asDashboardStatus(
                          cloudDeployments.some(
                            (deployment) =>
                              pickString(deployment, ["status"], "").toLowerCase() === "running",
                          )
                            ? "running"
                            : "idle",
                        )}
                        label={
                          cloudDeployments.some(
                            (deployment) =>
                              pickString(deployment, ["status"], "").toLowerCase() === "running",
                          )
                            ? "healthy"
                            : "idle"
                        }
                      />
                    }
                  >
                    {cloudDeployments.length === 0 ? (
                      <LiveEmptyState
                        title="No deployments yet"
                        message="Deploy an agent to make rollout posture and runtime recovery visible here."
                      />
                    ) : (
                      <div className="space-y-2">
                        {cloudDeployments.map((deployment) => {
                          const id = pickString(deployment, ["id"], "");
                          const statusLabel = pickString(deployment, ["status"], "unknown");
                          const replicas = pickNumber(deployment, ["replicas"], 1);
                          return (
                            <SelectionCard
                              key={id}
                              active={id === pickString(selectedDeployment, ["id"], "")}
                              title={id}
                              subtitle={`Agent ${pickString(deployment, ["agent_id"], "unknown")} · ${replicas} replicas`}
                              detail={`Started ${formatRelativeTime(pickString(deployment, ["started_at"], ""))}`}
                              statusLabel={statusLabel}
                              onClick={() => setSelectedDeploymentId(id)}
                              onContextMenu={() =>
                                void showDesktopContextMenu([
                                  {
                                    label: "Inspect Deployment",
                                    action: {
                                      type: "navigate.current",
                                      route: "/dashboard/deployments",
                                      payload: {
                                        pane: "rollouts",
                                        deploymentId: id,
                                        agentId: pickString(deployment, ["agent_id"], "") || undefined,
                                      },
                                    },
                                  },
                                  {
                                    label: "Open Agent",
                                    action: {
                                      type: "window.open",
                                      role: "workspace",
                                      route: "/dashboard/agents",
                                      payload: {
                                        pane: "fleet",
                                        agentId: pickString(deployment, ["agent_id"], "") || undefined,
                                      },
                                    },
                                  },
                                  { label: "separator", type: "separator" },
                                  {
                                    label: "Copy Deployment ID",
                                    action: { type: "clipboard.copy", value: id },
                                  },
                                ])
                              }
                            />
                          );
                        })}
                      </div>
                    )}
                  </WorkbenchPane>

                  <WorkbenchPane title="Launch Deployment" meta="replica action">
                    <form className="space-y-4" onSubmit={(event) => void createDeployment(event)}>
                      <select
                        aria-label="Deployment agent"
                        value={deploymentDraft.agentId}
                        onChange={(event) =>
                          setDeploymentDraft((current) => ({ ...current, agentId: event.target.value }))
                        }
                        className="w-full rounded-[6px] border border-[#2b3238] bg-[#0c1015] px-3 py-2.5 text-sm text-[#eee9dc] outline-none transition focus:border-[#5c6876]"
                      >
                        <option value="">Select an agent</option>
                        {cloudAgents.map((agent) => {
                          const id = pickString(agent, ["id"], "");
                          return (
                            <option key={id} value={id}>
                              {pickString(agent, ["name"], id)}
                            </option>
                          );
                        })}
                      </select>
                      <input
                        aria-label="Deployment replicas"
                        type="number"
                        min="1"
                        value={deploymentDraft.replicas}
                        onChange={(event) =>
                          setDeploymentDraft((current) => ({ ...current, replicas: event.target.value }))
                        }
                        className="w-full rounded-[6px] border border-[#2b3238] bg-[#0c1015] px-3 py-2.5 text-sm text-[#eee9dc] outline-none transition focus:border-[#5c6876]"
                      />
                      <SectionButton
                        label="Create Deployment"
                        icon={Play}
                        tone="primary"
                        busy={utilityBusy === "create-deployment"}
                        onClick={() => undefined}
                        type="submit"
                      />
                    </form>
                  </WorkbenchPane>
                </>
              }
              detail={
                <>
                  <WorkbenchPane
                    title="Deployment Detail"
                    meta={selectedDeployment ? maskValue(pickString(selectedDeployment, ["id"], "")) : "none selected"}
                    toolbar={
                      selectedDeployment ? (
                        <StatusBadge
                          status={asDashboardStatus(pickString(selectedDeployment, ["status"], "unknown"))}
                          label={pickString(selectedDeployment, ["status"], "unknown")}
                        />
                      ) : null
                    }
                  >
                    {selectedDeployment ? (
                      <div className="space-y-5">
                        <div>
                          <p className="font-mono text-[18px] text-[#f4f7fb]">
                            {pickString(selectedDeployment, ["id"], "unknown")}
                          </p>
                          <p className="mt-2 max-w-3xl text-sm leading-6 text-[#94a0ad]">
                            Agent {pickString(selectedDeployment, ["agent_id"], "unknown")} is allocated{" "}
                            {selectedDeploymentReplicas} replicas on this rollout.
                          </p>
                        </div>
                        <ValueList
                          items={[
                            {
                              label: "Started",
                              value: formatDateTime(pickString(selectedDeployment, ["started_at"], "")),
                            },
                            {
                              label: "Ended",
                              value: formatDateTime(pickString(selectedDeployment, ["ended_at"], "")),
                            },
                            { label: "Replicas", value: String(selectedDeploymentReplicas) },
                            { label: "Gateway", value: status.openclaw?.gatewayUrl || "not configured" },
                          ]}
                        />
                        <div className="grid gap-3 md:grid-cols-2">
                          <div className="rounded-[6px] border border-[#2b3238] bg-[#0c1015] px-4 py-3">
                            <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-[#7e8896]">
                              Control plane path
                            </p>
                            <p className="mt-2 text-sm text-[#f4f7fb]">
                              {localSnapshot.controlPlane?.path || "Unknown"}
                            </p>
                          </div>
                          <div className="rounded-[6px] border border-[#2b3238] bg-[#0c1015] px-4 py-3">
                            <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-[#7e8896]">
                              Runtime target
                            </p>
                            <p className="mt-2 text-sm text-[#f4f7fb]">
                              {localSnapshot.runtimeContext?.apiUrl || status.apiUrl || "unknown"}
                            </p>
                          </div>
                        </div>
                        <div className="flex flex-wrap gap-2">
                          <SectionButton
                            label="Restart deployment"
                            icon={RefreshCw}
                            busy={utilityBusy === `restart-${pickString(selectedDeployment, ["id"], "")}`}
                            onClick={() =>
                              void mutateDeployment(pickString(selectedDeployment, ["id"], ""), "restart")
                            }
                          />
                          <SectionButton
                            label="Scale -1"
                            icon={Power}
                            disabled={selectedDeploymentReplicas <= 1}
                            busy={utilityBusy === `scale-${pickString(selectedDeployment, ["id"], "")}`}
                            onClick={() =>
                              void mutateDeployment(
                                pickString(selectedDeployment, ["id"], ""),
                                "scale",
                                Math.max(1, selectedDeploymentReplicas - 1),
                              )
                            }
                          />
                          <SectionButton
                            label="Scale +1"
                            icon={Plus}
                            busy={utilityBusy === `scale-${pickString(selectedDeployment, ["id"], "")}`}
                            onClick={() =>
                              void mutateDeployment(
                                pickString(selectedDeployment, ["id"], ""),
                                "scale",
                                selectedDeploymentReplicas + 1,
                              )
                            }
                          />
                          <SectionButton
                            label="Delete deployment"
                            icon={Trash2}
                            tone="danger"
                            busy={utilityBusy === `delete-${pickString(selectedDeployment, ["id"], "")}`}
                            onClick={() =>
                              void mutateDeployment(pickString(selectedDeployment, ["id"], ""), "delete")
                            }
                          />
                        </div>
                      </div>
                    ) : (
                      <LiveEmptyState
                        title="No selected deployment"
                        message="Choose a deployment to inspect rollout posture, replica count, and recovery actions."
                      />
                    )}
                  </WorkbenchPane>

                  <WorkbenchPane title="Linked Agent" meta={selectedDeploymentAgent ? "resolved" : "missing"}>
                    {selectedDeploymentAgent ? (
                      <div className="space-y-4">
                        <div className="flex flex-wrap items-start justify-between gap-3">
                          <div>
                            <p className="text-base font-semibold text-[#eee9dc]">
                              {pickString(selectedDeploymentAgent, ["name"], "Unnamed agent")}
                            </p>
                            <p className="mt-2 text-sm leading-6 text-[#999284]">
                              {pickString(selectedDeploymentAgent, ["description"], "No description provided.")}
                            </p>
                          </div>
                          <StatusBadge
                            status={asDashboardStatus(pickString(selectedDeploymentAgent, ["status"], "unknown"))}
                            label={pickString(selectedDeploymentAgent, ["status"], "unknown")}
                          />
                        </div>
                        <ValueList
                          items={[
                            { label: "Agent ID", value: pickString(selectedDeploymentAgent, ["id"], "unknown") },
                            { label: "Type", value: pickString(selectedDeploymentAgent, ["type"], "unknown") },
                          ]}
                        />
                        <div className="flex flex-wrap gap-2">
                          <SectionButton
                            label="Open Agent"
                            icon={ArrowRight}
                            onClick={() => {
                              const agentId = pickString(selectedDeploymentAgent, ["id"], "");
                              setSelectedAgentId(agentId);
                              void openDesktopDestination("/dashboard/agents", {
                                agentId: agentId || undefined,
                              });
                            }}
                          />
                        </div>
                      </div>
                    ) : (
                      <LiveEmptyState
                        title="No linked agent record"
                        message="The deployment points at an agent that is not present in the current fetch window."
                      />
                    )}
                  </WorkbenchPane>
                </>
              }
              inspector={shouldShowInlineInspector ? routeInspectorContent : undefined}
            />
          </div>
        );

      case "runs":
        routeInspectorContent = (
          <div className="space-y-4">
            <WorkbenchPane
              title="Selected Trace"
              meta={selectedTrace ? `#${pickNumber(selectedTrace, ["sequence"], 0)}` : "no trace selected"}
            >
              {selectedTrace ? (
                <div className="space-y-4">
                  <div>
                    <p className="text-base font-semibold text-[#eee9dc]">
                      {pickString(selectedTrace, ["event_type"], "trace")}
                    </p>
                    <p className="mt-2 text-sm leading-6 text-[#999284]">
                      {pickString(selectedTrace, ["message"], "No trace message.")}
                    </p>
                  </div>
                  <ValueList
                    items={[
                      { label: "Sequence", value: String(pickNumber(selectedTrace, ["sequence"], 0)) },
                      {
                        label: "Timestamp",
                        value: formatDateTime(pickString(selectedTrace, ["timestamp"], "")),
                      },
                      { label: "Run", value: pickString(selectedRun, ["id"], "unknown") },
                      { label: "Agent", value: pickString(selectedRun, ["agent_id"], "unknown") },
                    ]}
                  />
                </div>
              ) : (
                <LiveEmptyState
                  title="No selected trace"
                  message="Pick a trace row from the transcript to inspect its exact timing and payload."
                />
              )}
            </WorkbenchPane>
            {inspectorRail}
          </div>
        );
        return (
          <div className="space-y-4">
            <WorkbenchMetricStrip
              items={[
                {
                  label: "Total runs",
                  value: formatCount(cloudRuns.length),
                  detail: "Recent execution records returned by the runs contract.",
                  tone: cloudRuns.length > 0 ? "success" : "neutral",
                },
                {
                  label: "In flight",
                  value: formatCount(
                    cloudRuns.filter((run) => !pickString(run, ["completed_at"], "")).length,
                  ),
                  detail: "Runs that have not yet reached a terminal timestamp.",
                  tone: cloudRuns.some((run) => !pickString(run, ["completed_at"], ""))
                    ? "success"
                    : "neutral",
                },
                {
                  label: "Failed",
                  value: formatCount(
                    cloudRuns.filter((run) =>
                      pickString(run, ["status"], "").toLowerCase().includes("fail"),
                    ).length,
                  ),
                  detail: "Runs still needing investigation or replay.",
                  tone: cloudRuns.some((run) =>
                    pickString(run, ["status"], "").toLowerCase().includes("fail"),
                  )
                    ? "warning"
                    : "neutral",
                },
                {
                  label: "Trace preview",
                  value: formatCount(cloudTraceEvents.length),
                  detail: "Trace rows currently loaded for the selected run.",
                  tone: cloudTraceEvents.length > 0 ? "success" : "neutral",
                },
              ]}
            />

            <WorkbenchFrame
              rail={
                <WorkbenchPane
                  title="Run Queue"
                  meta={`${cloudRuns.length} recent executions`}
                  toolbar={
                    <StatusBadge
                      status={asDashboardStatus(
                        cloudRuns.some((run) => !pickString(run, ["completed_at"], ""))
                          ? "running"
                          : "idle",
                      )}
                      label={cloudRuns.some((run) => !pickString(run, ["completed_at"], "")) ? "live" : "idle"}
                    />
                  }
                >
                  {cloudRuns.length === 0 ? (
                    <LiveEmptyState
                      title="No runs returned"
                      message="Run history will show here once the control plane has recent execution activity."
                    />
                  ) : (
                    <div className="space-y-2">
                      {cloudRuns.map((run) => {
                        const id = pickString(run, ["id"], "");
                        const statusLabel = pickString(run, ["status"], "unknown");
                        return (
                          <SelectionCard
                            key={id}
                            active={id === pickString(selectedRun, ["id"], "")}
                            title={id}
                            subtitle={`Agent ${pickString(run, ["agent_id"], "unknown")} · ${pickNumber(run, ["trace_count"], 0)} traces`}
                            detail={
                              pickString(run, ["error_message"], "") ||
                              pickString(run, ["output_text"], "") ||
                              `Started ${formatRelativeTime(pickString(run, ["started_at"], ""))}`
                            }
                            statusLabel={statusLabel}
                            onClick={() => setSelectedRunId(id)}
                            onContextMenu={() =>
                              void showDesktopContextMenu([
                                {
                                  label: "Inspect Run",
                                  action: {
                                    type: "navigate.current",
                                    route: "/dashboard/runs",
                                    payload: { pane: "operations", runId: id },
                                  },
                                },
                                {
                                  label: "Open Traces Window",
                                  action: {
                                    type: "window.open",
                                    role: "traces",
                                    route: "/dashboard/traces",
                                    payload: { runId: id, tab: "timeline" },
                                  },
                                },
                                {
                                  label: "Open Logs Tab",
                                  action: {
                                    type: "window.open",
                                    role: "traces",
                                    route: "/dashboard/logs",
                                    payload: { runId: id, tab: "logs" },
                                  },
                                },
                                { label: "separator", type: "separator" },
                                {
                                  label: "Copy Run ID",
                                  action: { type: "clipboard.copy", value: id },
                                },
                              ])
                            }
                            footer={
                              <div className="flex items-center justify-between gap-3 text-xs text-[#8d867a]">
                                <span>Started {formatRelativeTime(pickString(run, ["started_at"], ""))}</span>
                                <span>{pickNumber(run, ["trace_count"], 0)} traces</span>
                              </div>
                            }
                          />
                        );
                      })}
                    </div>
                  )}
                </WorkbenchPane>
              }
              detail={
                <>
                  <WorkbenchPane
                    title="Run Detail"
                    meta={selectedRun ? maskValue(pickString(selectedRun, ["id"], "")) : "none selected"}
                    toolbar={
                      selectedRun ? (
                        <StatusBadge
                          status={asDashboardStatus(pickString(selectedRun, ["status"], "unknown"))}
                          label={pickString(selectedRun, ["status"], "unknown")}
                        />
                      ) : null
                    }
                  >
                    {selectedRun ? (
                      <div className="space-y-5">
                        <div>
                          <p className="font-mono text-[18px] text-[#f4f7fb]">
                            {pickString(selectedRun, ["id"], "unknown")}
                          </p>
                          <p className="mt-2 max-w-3xl text-sm leading-6 text-[#94a0ad]">
                            Agent {pickString(selectedRun, ["agent_id"], "unknown")} started{" "}
                            {formatRelativeTime(pickString(selectedRun, ["started_at"], ""))}.
                          </p>
                        </div>
                        <ValueList
                          items={[
                            { label: "Started", value: formatDateTime(pickString(selectedRun, ["started_at"], "")) },
                            {
                              label: "Completed",
                              value: formatDateTime(pickString(selectedRun, ["completed_at"], "")),
                            },
                            { label: "Trace count", value: String(pickNumber(selectedRun, ["trace_count"], 0)) },
                            {
                              label: "Desktop target",
                              value: localSnapshot.runtimeContext?.apiUrl || status.apiUrl || "unknown",
                            },
                          ]}
                        />
                        <div className="flex flex-wrap gap-2">
                          <SectionButton
                            label="Open Traces"
                            icon={ArrowRight}
                            tone="primary"
                            onClick={() =>
                              void openDesktopDestination("/dashboard/traces", {
                                runId: pickString(selectedRun, ["id"], "") || undefined,
                              })
                            }
                          />
                          <SectionButton
                            label="Open Monitoring"
                            icon={ArrowRight}
                            onClick={() => void openDesktopDestination("/dashboard/monitoring")}
                          />
                          <SectionButton
                            label="Copy Run ID"
                            icon={Copy}
                            onClick={() =>
                              void copyToClipboard(pickString(selectedRun, ["id"], ""), "run")
                            }
                          />
                        </div>
                      </div>
                    ) : (
                      <LiveEmptyState
                        title="No selected run"
                        message="Choose a run to inspect timestamps, trace volume, and recovery actions."
                      />
                    )}
                  </WorkbenchPane>

                  <WorkbenchPane
                    title="Execution Transcript"
                    meta={`${cloudTraceEvents.length} trace rows loaded`}
                  >
                    {selectedRun ? (
                      <div className="space-y-4">
                        <div className="rounded-[6px] border border-[#2b3238] bg-[#0c1015] p-4">
                          <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-[#7e8896]">
                            Output
                          </p>
                          <p className="mt-3 whitespace-pre-wrap text-sm leading-6 text-[#c8c0b0]">
                            {pickString(selectedRun, ["error_message"], "") ||
                              pickString(selectedRun, ["output_text"], "") ||
                              "No run output or error text was captured in the current payload."}
                          </p>
                        </div>
                        {cloudTraceEvents.length > 0 ? (
                          <div className="space-y-2">
                            {cloudTraceEvents.slice(0, 6).map((trace) => {
                              const traceKey = pickString(
                                trace,
                                ["id"],
                                `${pickNumber(trace, ["sequence"], 0)}`,
                              );
                              return (
                                <SelectionCard
                                  key={traceKey}
                                  active={traceKey === pickString(selectedTrace, ["id"], `${pickNumber(selectedTrace, ["sequence"], 0)}`)}
                                  title={pickString(trace, ["event_type"], "trace")}
                                  subtitle={`#${pickNumber(trace, ["sequence"], 0)} · ${formatRelativeTime(pickString(trace, ["timestamp"], ""))}`}
                                  detail={pickString(trace, ["message"], "No trace message.")}
                                  onClick={() => setSelectedTraceId(traceKey)}
                                />
                              );
                            })}
                          </div>
                        ) : (
                          <LiveEmptyState
                            title="No trace preview"
                            message="The selected run did not return trace rows in the current preview window."
                          />
                        )}
                      </div>
                    ) : (
                      <LiveEmptyState
                        title="No selected run output"
                        message="Select a run to inspect output and nearby trace rows."
                      />
                    )}
                  </WorkbenchPane>
                </>
              }
              inspector={shouldShowInlineInspector ? routeInspectorContent : undefined}
            />
          </div>
        );

      case "monitoring":
        return (
          <div className="space-y-4">
            <LiveKpiGrid>
              <LiveStatCard
                label="Health"
                value={pickString(monitoringHealth, ["status"], "unknown")}
                detail={`Database ${pickString(monitoringHealth, ["database"], "unknown")} · ${formatDateTime(
                  pickString(monitoringHealth, ["timestamp"], ""),
                )}`}
                status={asDashboardStatus(pickString(monitoringHealth, ["status"], "unknown"))}
              />
              <LiveStatCard
                label="Open alerts"
                value={String(cloudAlerts.filter((alert) => !pickBoolean(alert, ["resolved"], false)).length)}
                detail={`${cloudAlerts.length} alert records returned from monitoring.`}
                status={asDashboardStatus(
                  cloudAlerts.some((alert) => !pickBoolean(alert, ["resolved"], false)) ? "warning" : "healthy",
                )}
              />
              <LiveStatCard
                label="Pending approvals"
                value={String(localSnapshot.governance?.pending_approvals ?? 0)}
                detail={`Governance decisions total ${localSnapshot.governance?.decisions_total ?? 0}.`}
                status={asDashboardStatus(
                  (localSnapshot.governance?.pending_approvals ?? 0) > 0 ? "warning" : "healthy",
                )}
              />
              <LiveStatCard
                label="Gateway"
                value={status.openclaw?.health || "unknown"}
                detail={status.openclaw?.gatewayUrl || "Gateway URL is not configured."}
                status={asDashboardStatus(status.openclaw?.health)}
              />
            </LiveKpiGrid>

            <div className="grid gap-4 xl:grid-cols-[minmax(320px,0.92fr)_minmax(0,1.08fr)]">
              <LivePanel title="Alert rail" meta={`${cloudAlerts.length} records`}>
                {cloudAlerts.length === 0 ? (
                  <LiveEmptyState
                    title="No alerts"
                    message="The monitoring surface will light up here when runtime or deployment alerts exist."
                  />
                ) : (
                  <div className="space-y-3">
                    {cloudAlerts.map((alert, index) => {
                      const id = pickString(alert, ["id"], `alert-${index}`);
                      const open = !pickBoolean(alert, ["resolved"], false);
                      return (
                        <SelectionCard
                          key={id}
                          active={id === pickString(selectedAlert, ["id"], "")}
                          title={titleCase(pickString(alert, ["type"], "alert"))}
                          subtitle={pickString(alert, ["agent_id"], "") ? `Agent ${pickString(alert, ["agent_id"], "")}` : "Runtime-wide alert"}
                          detail={pickString(alert, ["message"], "No alert message.")}
                          statusLabel={open ? "open" : "resolved"}
                          onClick={() => setSelectedAlertId(id)}
                          footer={
                            <p className="text-xs text-[#8d867a]">
                              Raised {formatRelativeTime(pickString(alert, ["created_at", "timestamp"], ""))}
                            </p>
                          }
                        />
                      );
                    })}
                  </div>
                )}
              </LivePanel>

              <div className="space-y-4">
                <LivePanel
                  title="Selected alert"
                  meta={selectedAlert ? titleCase(pickString(selectedAlert, ["type"], "alert")) : "no alert selected"}
                >
                  {selectedAlert ? (
                    <div className="space-y-4">
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div>
                          <p className="text-base font-semibold text-[#eee9dc]">
                            {titleCase(pickString(selectedAlert, ["type"], "alert"))}
                          </p>
                          <p className="mt-2 text-sm leading-6 text-[#999284]">
                            {pickString(selectedAlert, ["message"], "No alert message.")}
                          </p>
                        </div>
                        <StatusBadge
                          status={asDashboardStatus(
                            pickBoolean(selectedAlert, ["resolved"], false) ? "healthy" : "warning",
                          )}
                          label={pickBoolean(selectedAlert, ["resolved"], false) ? "resolved" : "open"}
                        />
                      </div>
                      <ValueList
                        items={[
                          { label: "Alert ID", value: pickString(selectedAlert, ["id"], "unknown") },
                          { label: "Agent ID", value: pickString(selectedAlert, ["agent_id"], "n/a") },
                          { label: "Raised", value: formatDateTime(pickString(selectedAlert, ["created_at", "timestamp"], "")) },
                          { label: "Gateway", value: status.openclaw?.gatewayUrl || "not configured" },
                        ]}
                      />
                      <div className="flex flex-wrap gap-2">
                        <SectionButton
                          label="Open Logs"
                          icon={ArrowRight}
                          tone="primary"
                          onClick={() => void openDesktopDestination("/dashboard/logs")}
                        />
                        <SectionButton
                          label="Open Advanced"
                          icon={ArrowRight}
                          onClick={() => void openDesktopDestination("/dashboard/control", { pane: "advanced" })}
                        />
                        <SectionButton
                          label="Restart Governance"
                          icon={Shield}
                          busy={job.id === "governanceRestart" && job.status === "running"}
                          onClick={() => void runGovernanceRestartJob()}
                        />
                      </div>
                    </div>
                  ) : (
                    <LiveEmptyState
                      title="No selected alert"
                      message="Select an alert to inspect its origin, state, and recovery path."
                    />
                  )}
                </LivePanel>

                <LivePanel title="Machine health rail" meta="desktop + governance">
                  <ValueList
                    items={[
                      { label: "Bridge", value: status.bridge.state || "unknown" },
                      { label: "Python", value: status.bridge.pythonCommand || "unknown" },
                      { label: "Gateway summary", value: localSnapshot.systemInfo?.openclaw.health.doctor_summary || "n/a" },
                      { label: "Policy summary", value: localSnapshot.systemInfo?.faramesh.health.doctor_summary || "n/a" },
                    ]}
                  />
                </LivePanel>
              </div>
            </div>
          </div>
        );

      case "traces": {
        routeInspectorContent = (
          <div className="space-y-4">
            <WorkbenchPane
              title="Trace Detail"
              meta={selectedTrace ? `#${pickNumber(selectedTrace, ["sequence"], 0)}` : "no trace selected"}
            >
              {selectedTrace ? (
                <div className="space-y-4">
                  <div>
                    <p className="text-base font-semibold text-[#eee9dc]">
                      {pickString(selectedTrace, ["event_type"], "trace")}
                    </p>
                    <p className="mt-2 text-sm leading-6 text-[#999284]">
                      {pickString(selectedTrace, ["message"], "No trace message.")}
                    </p>
                  </div>
                  <ValueList
                    items={[
                      { label: "Sequence", value: String(pickNumber(selectedTrace, ["sequence"], 0)) },
                      { label: "Timestamp", value: formatDateTime(pickString(selectedTrace, ["timestamp"], "")) },
                      { label: "Run ID", value: pickString(selectedRun, ["id"], "unknown") },
                      { label: "Agent ID", value: pickString(selectedRun, ["agent_id"], "unknown") },
                    ]}
                  />
                  <SnapshotDetails title="Trace payload" value={selectedTrace} />
                </div>
              ) : (
                <LiveEmptyState
                  title="No trace selected"
                  message="Select an event row to inspect the exact trace payload."
                />
              )}
            </WorkbenchPane>
            {inspectorRail}
          </div>
        );
        return (
          <div className="space-y-4">
            <WorkbenchMetricStrip
              items={[
                {
                  label: "Traceable runs",
                  value: formatCount(cloudRuns.length),
                  detail: "Runs loaded into the trace workbench.",
                  tone: cloudRuns.length > 0 ? "success" : "neutral",
                },
                {
                  label: "Trace rows",
                  value: formatCount(cloudTraceEvents.length),
                  detail: "Current event rows for the selected run.",
                  tone: cloudTraceEvents.length > 0 ? "success" : "neutral",
                },
                {
                  label: "Selected run",
                  value: selectedRun ? maskValue(pickString(selectedRun, ["id"], "")) : "none",
                  detail: selectedRun
                    ? `Agent ${pickString(selectedRun, ["agent_id"], "unknown")}`
                    : "Pick a run to load its event stream.",
                  tone: selectedRun ? "neutral" : "warning",
                },
                {
                  label: "Desktop target",
                  value: localSnapshot.runtimeContext?.mode || status.mode || "unknown",
                  detail: localSnapshot.runtimeContext?.apiUrl || status.apiUrl || "unknown",
                  tone:
                    (localSnapshot.runtimeContext?.mode || status.mode) === "local"
                      ? "success"
                      : "neutral",
                },
              ]}
            />

            <WorkbenchFrame
              rail={
                <WorkbenchPane title="Traceable Runs" meta={`${cloudRuns.length} runs`}>
                  {cloudRuns.length === 0 ? (
                    <LiveEmptyState
                      title="No traceable runs"
                      message="Once runs exist, the desktop route will let you drill into their trace streams here."
                    />
                  ) : (
                    <div className="space-y-2">
                      {cloudRuns.map((run) => {
                        const id = pickString(run, ["id"], "");
                        return (
                          <SelectionCard
                            key={id}
                            active={id === pickString(selectedRun, ["id"], "")}
                            title={id}
                            subtitle={`${pickString(run, ["status"], "unknown")} · ${pickNumber(run, ["trace_count"], 0)} traces`}
                            detail={`Started ${formatRelativeTime(pickString(run, ["started_at"], ""))}`}
                            onClick={() => setSelectedRunId(id)}
                            onContextMenu={() =>
                              void showDesktopContextMenu([
                                {
                                  label: "Open Timeline",
                                  action: {
                                    type: "navigate.current",
                                    route: "/dashboard/traces",
                                    payload: { runId: id, tab: "timeline" },
                                  },
                                },
                                {
                                  label: "Open Logs Tab",
                                  action: {
                                    type: "navigate.current",
                                    route: "/dashboard/logs",
                                    payload: { runId: id, tab: "logs" },
                                  },
                                },
                                { label: "separator", type: "separator" },
                                {
                                  label: "Copy Run ID",
                                  action: { type: "clipboard.copy", value: id },
                                },
                              ])
                            }
                          />
                        );
                      })}
                    </div>
                  )}
                </WorkbenchPane>
              }
              detail={
                <WorkbenchPane
                  title="Trace Stream"
                  meta={selectedRun ? pickString(selectedRun, ["id"], "") : "no run selected"}
                >
                  {cloudTraceEvents.length === 0 ? (
                    <LiveEmptyState
                      title="No trace events captured"
                      message="The selected run did not return trace rows yet."
                    />
                  ) : (
                    <div className="space-y-2">
                      {cloudTraceEvents.map((trace) => {
                        const traceKey = pickString(trace, ["id"], `${pickNumber(trace, ["sequence"], 0)}`);
                        return (
                          <SelectionCard
                            key={traceKey}
                            active={
                              traceKey ===
                              pickString(selectedTrace, ["id"], `${pickNumber(selectedTrace, ["sequence"], 0)}`)
                            }
                            title={pickString(trace, ["event_type"], "trace")}
                            subtitle={`#${pickNumber(trace, ["sequence"], 0)} · ${formatRelativeTime(pickString(trace, ["timestamp"], ""))}`}
                            detail={pickString(trace, ["message"], "No trace message.")}
                            onClick={() => setSelectedTraceId(traceKey)}
                            onContextMenu={() =>
                              void showDesktopContextMenu([
                                {
                                  label: "Open Logs Tab",
                                  action: {
                                    type: "navigate.current",
                                    route: "/dashboard/logs",
                                    payload: {
                                      runId: pickString(selectedRun, ["id"], "") || undefined,
                                      tab: "logs",
                                    },
                                  },
                                },
                                { label: "separator", type: "separator" },
                                {
                                  label: "Copy Trace ID",
                                  action: { type: "clipboard.copy", value: traceKey },
                                },
                              ])
                            }
                          />
                        );
                      })}
                    </div>
                  )}
                </WorkbenchPane>
              }
              inspector={shouldShowInlineInspector ? routeInspectorContent : undefined}
            />
          </div>
        );
      }

      case "observability":
        return (
          <div className="space-y-4">
            <LiveKpiGrid>
              <LiveStatCard
                label="Events"
                value={formatCount(cloudObservability.length)}
                detail="Rows currently loaded from the observability contract."
              />
              <LiveStatCard
                label="Degraded"
                value={formatCount(
                  cloudObservability.filter((event) => {
                    const level = pickString(event, ["status", "level"], "").toLowerCase();
                    return level.includes("error") || level.includes("warn");
                  }).length,
                )}
                detail="Events already signaling warning or error conditions."
                status={asDashboardStatus(
                  cloudObservability.some((event) => {
                    const level = pickString(event, ["status", "level"], "").toLowerCase();
                    return level.includes("error") || level.includes("warn");
                  })
                    ? "warning"
                    : "healthy",
                )}
              />
              <LiveStatCard
                label="Event types"
                value={formatCount(
                  new Set(
                    cloudObservability
                      .map((event) => pickString(event, ["event_type", "name", "metric"], ""))
                      .filter(Boolean),
                  ).size,
                )}
                detail="Distinct event categories in the current sample."
              />
              <LiveStatCard
                label="Local sessions"
                value={formatCount(localSnapshot.sessions.length)}
                detail="Machine-local sessions available to correlate with the feed."
              />
            </LiveKpiGrid>

            <div className="grid gap-4 xl:grid-cols-[minmax(320px,0.95fr)_minmax(0,1.05fr)]">
              <LivePanel title="Observability feed" meta={`${cloudObservability.length} events`}>
                {cloudObservability.length === 0 ? (
                  <LiveEmptyState
                    title="No observability events"
                    message="The live observability contract has not returned any rows yet."
                  />
                ) : (
                  <div className="space-y-3">
                    {cloudObservability.map((event, index) => {
                      const id = pickString(event, ["id"], `event-${index}`);
                      const statusLabel = pickString(event, ["status", "level"], "unknown");
                      return (
                        <SelectionCard
                          key={id}
                          active={id === pickString(selectedObservability, ["id"], "")}
                          title={pickString(event, ["event_type", "name", "metric"], "Observability event")}
                          subtitle={pickString(event, ["run_id", "agent_id"], "No run or agent attached")}
                          detail={pickString(event, ["message", "summary"], "No additional event message.")}
                          statusLabel={statusLabel}
                          onClick={() => setSelectedObservabilityId(id)}
                        />
                      );
                    })}
                  </div>
                )}
              </LivePanel>

              <LivePanel
                title="Selected event"
                meta={selectedObservability ? pickString(selectedObservability, ["id"], "selected") : "none selected"}
              >
                {selectedObservability ? (
                  <div className="space-y-4">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <p className="text-base font-semibold text-[#eee9dc]">
                          {pickString(selectedObservability, ["event_type", "name", "metric"], "Observability event")}
                        </p>
                        <p className="mt-2 text-sm leading-6 text-[#999284]">
                          {pickString(selectedObservability, ["message", "summary"], "No additional event message.")}
                        </p>
                      </div>
                      <StatusBadge
                        status={asDashboardStatus(pickString(selectedObservability, ["status", "level"], "unknown"))}
                        label={pickString(selectedObservability, ["status", "level"], "unknown")}
                      />
                    </div>
                    <ValueList
                      items={[
                        { label: "Run ID", value: pickString(selectedObservability, ["run_id"], "n/a") },
                        { label: "Agent ID", value: pickString(selectedObservability, ["agent_id"], "n/a") },
                        { label: "Timestamp", value: formatDateTime(pickString(selectedObservability, ["timestamp", "created_at"], "")) },
                        { label: "Desktop target", value: localSnapshot.runtimeContext?.apiUrl || status.apiUrl || "unknown" },
                      ]}
                    />
                    <ChipRow
                      items={pickStringArray(selectedObservability, ["tags", "flags"])}
                      emptyLabel="No tags were attached to this event."
                    />
                    <SnapshotDetails title="Selected event payload" value={selectedObservability} />
                  </div>
                ) : (
                  <LiveEmptyState
                    title="No selected event"
                    message="Pick an observability row to inspect its payload and route context."
                  />
                )}
              </LivePanel>
            </div>
          </div>
        );

      case "sessions":
        return (
          <div className="space-y-4">
            <WorkbenchMetricStrip
              items={[
                {
                  label: "Cloud sessions",
                  value: formatCount(cloudSessions.length),
                  detail: "Session rows currently returned by the gateway-backed contract.",
                  tone: cloudSessions.length > 0 ? "success" : "neutral",
                },
                {
                  label: "Local sessions",
                  value: formatCount(localSnapshot.sessions.length),
                  detail: "Machine-local session state discovered by the desktop bridge.",
                  tone: localSnapshot.sessions.length > 0 ? "success" : "neutral",
                },
                {
                  label: "Active",
                  value: formatCount(
                    cloudSessions.filter((session) => pickBoolean(session, ["active"], false)).length +
                      localSnapshot.sessions.filter((session) => session.active).length,
                  ),
                  detail: "Combined active cloud and local sessions.",
                  tone:
                    cloudSessions.some((session) => pickBoolean(session, ["active"], false)) ||
                    localSnapshot.sessions.some((session) => session.active)
                      ? "success"
                      : "neutral",
                },
                {
                  label: "Enabled channels",
                  value: String(
                    isRecord(cloudOverview?.assistant) && Array.isArray(cloudOverview.assistant.channels)
                      ? (cloudOverview.assistant.channels as Array<Record<string, unknown>>).filter((entry) =>
                          pickBoolean(entry, ["enabled"], false),
                        ).length
                      : 0,
                  ),
                  detail: status.openclaw?.gatewayUrl || "Gateway URL is not available yet.",
                  tone: status.assistant?.gatewayStatus === "healthy" ? "success" : "warning",
                },
              ]}
            />

            <WorkbenchFrame
              rail={
                <>
                  <WorkbenchPane title="Cloud Session Registry" meta={`${cloudSessions.length} records`}>
                    {cloudSessions.length === 0 ? (
                      <LiveEmptyState
                        title="No cloud sessions"
                        message="Session rows will appear here when the gateway reports them."
                      />
                    ) : (
                      <div className="space-y-2">
                        {cloudSessions.map((session, index) => {
                          const id = pickString(session, ["id", "session_id", "key"], `session-${index}`);
                          const active = pickBoolean(session, ["active"], false);
                          return (
                            <SelectionCard
                              key={id}
                              active={id === pickString(selectedCloudSession, ["id", "session_id", "key"], "")}
                              title={pickString(session, ["agent", "assistant", "assistant_name"], "Assistant session")}
                              subtitle={`${pickString(session, ["channel"], "unassigned")} · ${pickString(session, ["model"], "unknown model")}`}
                              detail={`Source ${pickString(session, ["source"], "gateway")} · ${pickString(session, ["age"], "age unknown")}`}
                              statusLabel={active ? "active" : "idle"}
                              onClick={() => {
                                setSelectedCloudSessionId(id);
                                setSelectedLocalSessionId(null);
                              }}
                              onContextMenu={() =>
                                void showDesktopContextMenu([
                                  {
                                    label: "Inspect Session",
                                    action: {
                                      type: "navigate.current",
                                      route: "/dashboard/sessions",
                                      payload: { sessionId: id },
                                    },
                                  },
                                  {
                                    label: "Open Channels",
                                    action: {
                                      type: "window.open",
                                      role: "workspace",
                                      route: "/dashboard/channels",
                                      payload: { pane: "channels", sessionId: id },
                                    },
                                  },
                                  { label: "separator", type: "separator" },
                                  {
                                    label: "Copy Session ID",
                                    action: { type: "clipboard.copy", value: id },
                                  },
                                ])
                              }
                            />
                          );
                        })}
                      </div>
                    )}
                  </WorkbenchPane>

                  <WorkbenchPane title="Local Session Feed" meta={`${localSnapshot.sessions.length} local`}>
                    {localSnapshot.sessions.length === 0 ? (
                      <LiveEmptyState
                        title="No local sessions"
                        message="Open the TUI or start a conversation to populate machine-local session state."
                      />
                    ) : (
                      <div className="space-y-2">
                        {localSnapshot.sessions.map((session) => (
                          <SelectionCard
                            key={session.id}
                            active={session.id === selectedLocalSession?.id}
                            title={session.agent || session.id}
                            subtitle={`${session.channel} · ${session.model}`}
                            detail={session.age}
                            statusLabel={session.active ? "active" : "idle"}
                            onClick={() => {
                              setSelectedLocalSessionId(session.id);
                              setSelectedCloudSessionId(null);
                            }}
                            onContextMenu={() =>
                              void showDesktopContextMenu([
                                {
                                  label: "Inspect Local Session",
                                  action: {
                                    type: "navigate.current",
                                    route: "/dashboard/sessions",
                                    payload: { sessionId: session.id },
                                  },
                                },
                                {
                                  label: "Open Channels",
                                  action: {
                                    type: "window.open",
                                    role: "workspace",
                                    route: "/dashboard/channels",
                                    payload: { pane: "channels", sessionId: session.id },
                                  },
                                },
                                { label: "separator", type: "separator" },
                                {
                                  label: "Copy Session ID",
                                  action: { type: "clipboard.copy", value: session.id },
                                },
                              ])
                            }
                          />
                        ))}
                      </div>
                    )}
                  </WorkbenchPane>
                </>
              }
              detail={
                <WorkbenchPane
                  title="Session Detail"
                  meta={
                    selectedCloudSession
                      ? pickString(selectedCloudSession, ["id", "session_id", "key"], "selected")
                      : selectedLocalSession
                        ? selectedLocalSession.id
                        : "none selected"
                  }
                  toolbar={
                    selectedCloudSession || selectedLocalSession ? (
                      <StatusBadge
                        status={asDashboardStatus(
                          pickBoolean(selectedCloudSession, ["active"], false) || selectedLocalSession?.active
                            ? "active"
                            : "idle",
                        )}
                        label={
                          pickBoolean(selectedCloudSession, ["active"], false) || selectedLocalSession?.active
                            ? "active"
                            : "idle"
                        }
                      />
                    ) : null
                  }
                >
                  {selectedCloudSession || selectedLocalSession ? (
                    <div className="space-y-5">
                      <div>
                        <p className="text-[20px] font-semibold tracking-[-0.03em] text-[#f4f7fb]">
                          {pickString(selectedCloudSession, ["agent", "assistant", "assistant_name"], "") ||
                            selectedLocalSession?.agent ||
                            "Assistant session"}
                        </p>
                        <p className="mt-2 text-sm leading-6 text-[#94a0ad]">
                          {pickString(selectedCloudSession, ["channel"], "") ||
                            selectedLocalSession?.channel ||
                            "unassigned"}{" "}
                          ·{" "}
                          {pickString(selectedCloudSession, ["model"], "") ||
                            selectedLocalSession?.model ||
                            "unknown model"}
                        </p>
                      </div>
                      <ValueList
                        items={[
                          {
                            label: "Cloud key",
                            value: pickString(selectedCloudSession, ["id", "session_id", "key"], "n/a"),
                          },
                          { label: "Local ID", value: selectedLocalSession?.id || "n/a" },
                          { label: "Gateway status", value: status.assistant?.gatewayStatus || "unknown" },
                          { label: "Workspace", value: status.assistant?.workspace || "not bound" },
                        ]}
                      />
                      <div className="grid gap-3 md:grid-cols-2">
                        <div className="rounded-[6px] border border-[#2b3238] bg-[#0c1015] px-4 py-3">
                          <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-[#7e8896]">
                            Session source
                          </p>
                          <p className="mt-2 text-sm text-[#f4f7fb]">
                            {pickString(selectedCloudSession, ["source"], "gateway") || "gateway"}
                          </p>
                        </div>
                        <div className="rounded-[6px] border border-[#2b3238] bg-[#0c1015] px-4 py-3">
                          <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-[#7e8896]">
                            Local age
                          </p>
                          <p className="mt-2 text-sm text-[#f4f7fb]">{selectedLocalSession?.age || "unknown"}</p>
                        </div>
                      </div>
                      <div className="flex flex-wrap gap-2">
                        <SectionButton
                          label="Open TUI"
                          icon={TerminalSquare}
                          onClick={() =>
                            void runUtilityAction("tui-session", async () => {
                              await window.mutxDesktop!.bridge.runtime.openSurface("tui");
                            })
                          }
                        />
                        <SectionButton
                          label="Open Channels"
                          icon={ArrowRight}
                          onClick={() => void openDesktopDestination("/dashboard/channels")}
                        />
                        <SectionButton
                          label="Reveal Workspace"
                          icon={FolderOpen}
                          disabled={!status.assistant?.workspace}
                          onClick={() =>
                            void runUtilityAction("reveal-session-workspace", async () => {
                              await window.mutxDesktop!.bridge.system.revealInFinder(status.assistant!.workspace!);
                            })
                          }
                        />
                      </div>
                    </div>
                  ) : (
                    <LiveEmptyState
                      title="No selected session"
                      message="Choose a cloud session or rely on the local session feed to inspect conversation posture."
                    />
                  )}
                </WorkbenchPane>
              }
              inspector={shouldShowInlineInspector ? routeInspectorContent : undefined}
            />
          </div>
        );

      case "apiKeys":
        return (
          <div className="grid gap-4 xl:grid-cols-[minmax(320px,0.88fr)_minmax(0,1.12fr)]">
            <LivePanel title="Key issuance" meta="create + reveal">
              <form className="space-y-4" onSubmit={(event) => void createApiKey(event)}>
                <input
                  aria-label="API key name"
                  value={apiKeyName}
                  onChange={(event) => setApiKeyName(event.target.value)}
                  placeholder="Operator key"
                  className="w-full rounded-[6px] border border-[#2b2b26] bg-[#11120f] px-3 py-2.5 text-sm text-[#eee9dc] outline-none"
                />
                <SectionButton
                  label="Create API Key"
                  icon={KeyRound}
                  tone="primary"
                  busy={utilityBusy === "create-key"}
                  onClick={() => undefined}
                  type="submit"
                />
              </form>

              {revealedKey ? (
                <div className="mt-4 rounded-[6px] border border-[#285a43] bg-[#0f2018] p-4">
                  <p className="font-[family:var(--font-mono)] text-[9px] font-semibold uppercase tracking-[0.16em] text-[#78e3b4]">One-time secret</p>
                  <p className="mt-2 break-all font-mono text-sm text-[#eee9dc]">{revealedKey}</p>
                </div>
              ) : null}
            </LivePanel>

            <RecordStack
              title="Key ledger"
              meta={`${cloudKeys.length} records`}
              records={cloudKeys}
              emptyTitle="No API keys"
              emptyMessage="Created and rotated keys will be listed here with their operator posture."
              renderRecord={(keyRecord) => {
                const id = pickString(keyRecord, ["id"], "");
                const statusLabel = pickString(keyRecord, ["status"], pickBoolean(keyRecord, ["is_active"], true) ? "active" : "inactive");
                return (
                  <div key={id} className="rounded-[6px] border border-[#2b2b26] bg-[#11120f] p-4">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <p className="text-sm font-semibold text-[#eee9dc]">{pickString(keyRecord, ["name"], "API key")}</p>
                        <p className="mt-1 font-mono text-xs text-[#8d867a]">{maskValue(id)}</p>
                      </div>
                      <StatusBadge status={asDashboardStatus(statusLabel)} label={statusLabel} />
                    </div>
                    <div className="mt-4 flex flex-wrap gap-2">
                      <SectionButton
                        label="Rotate"
                        icon={RefreshCw}
                        busy={utilityBusy === `rotate-key-${id}`}
                        onClick={() => void mutateApiKey(id, "rotate")}
                      />
                      <SectionButton
                        label="Revoke"
                        icon={Trash2}
                        tone="danger"
                        busy={utilityBusy === `delete-key-${id}`}
                        onClick={() => void mutateApiKey(id, "delete")}
                      />
                    </div>
                  </div>
                );
              }}
            />
          </div>
        );

      case "budgets":
        return (
          <div className="space-y-4">
            <LiveKpiGrid>
              <LiveStatCard
                label="Credits remaining"
                value={formatCurrency(pickNumber(isRecord(cloudBudgetRecords[0]) ? cloudBudgetRecords[0] : null, ["credits_remaining"], 0))}
                detail="Current remaining credits from the budget contract."
              />
              <LiveStatCard
                label="Total credits used"
                value={formatCurrency(pickNumber(cloudCosts, ["total_credits_used"], 0))}
                detail="Aggregated usage in the selected reporting window."
                status={asDashboardStatus(pickNumber(cloudCosts, ["total_credits_used"], 0) > 0 ? "running" : "idle")}
              />
              <LiveStatCard
                label="Usage events"
                value={formatCount(cloudUsageEvents.length)}
                detail="Recent usage events returned by the API."
              />
              <LiveStatCard
                label="Successful runs"
                value={formatCount(pickNumber(analyticsSummary, ["successful_runs"], 0))}
                detail="Successful runs counted in analytics."
              />
            </LiveKpiGrid>
            <RecordStack
              title="Budget usage events"
              meta={`${cloudUsageEvents.length} events`}
              records={cloudUsageEvents}
              emptyTitle="No usage events"
              emptyMessage="Budget event history will appear here once the API emits usage rows."
              renderRecord={(event) => (
                <div
                  key={pickString(event, ["id"], `usage-event-${pickString(event, ["created_at", "timestamp"], "fallback")}`)}
                  className="rounded-[6px] border border-[#2b2b26] bg-[#11120f] p-4"
                >
                  <p className="text-sm font-semibold text-[#eee9dc]">
                    {pickString(event, ["event_type", "type"], "usage event")}
                  </p>
                  <p className="mt-1 text-sm text-[#999284]">
                    {pickString(event, ["message", "description"], jsonPreview(event))}
                  </p>
                </div>
              )}
            />
          </div>
        );

      case "webhooks":
        return (
          <div className="grid gap-4 xl:grid-cols-[minmax(320px,0.9fr)_minmax(0,1.1fr)]">
            <LivePanel title="Create webhook" meta="native control">
              <form className="space-y-4" onSubmit={(event) => void createWebhook(event)}>
                <input
                  aria-label="Webhook endpoint URL"
                  value={webhookDraft.url}
                  onChange={(event) => setWebhookDraft((current) => ({ ...current, url: event.target.value }))}
                  placeholder="https://example.com/webhooks/mutx"
                  className="w-full rounded-[6px] border border-[#2b2b26] bg-[#11120f] px-3 py-2.5 text-sm text-[#eee9dc] outline-none"
                />
                <input
                  aria-label="Webhook event names"
                  value={webhookDraft.events}
                  onChange={(event) =>
                    setWebhookDraft((current) => ({ ...current, events: event.target.value }))
                  }
                  placeholder="run.completed, deployment.failed"
                  className="w-full rounded-[6px] border border-[#2b2b26] bg-[#11120f] px-3 py-2.5 text-sm text-[#eee9dc] outline-none"
                />
                <label className="flex items-center gap-2 text-sm text-[#c8c0b0]">
                  <input
                    type="checkbox"
                    checked={webhookDraft.isActive}
                    onChange={(event) =>
                      setWebhookDraft((current) => ({ ...current, isActive: event.target.checked }))
                    }
                  />
                  active
                </label>
                <SectionButton
                  label="Create Webhook"
                  icon={Zap}
                  tone="primary"
                  busy={utilityBusy === "create-webhook"}
                  onClick={() => undefined}
                  type="submit"
                />
              </form>
            </LivePanel>

            <RecordStack
              title="Webhook endpoints"
              meta={`${cloudWebhooks.length} endpoints`}
              records={cloudWebhooks}
              emptyTitle="No webhook endpoints"
              emptyMessage="Webhook endpoints will appear here as soon as they are registered."
              renderRecord={(webhook) => {
                const id = pickString(webhook, ["id"], "");
                return (
                  <div key={id} className="rounded-[6px] border border-[#2b2b26] bg-[#11120f] p-4">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <p className="text-sm font-semibold text-[#eee9dc]">{pickString(webhook, ["url"], "unknown url")}</p>
                        <p className="mt-1 text-sm text-[#999284]">
                          {pickStringArray(webhook, ["events"]).join(", ") || "No events configured"}
                        </p>
                      </div>
                      <StatusBadge
                        status={asDashboardStatus(pickBoolean(webhook, ["is_active"], false) ? "active" : "idle")}
                        label={pickBoolean(webhook, ["is_active"], false) ? "active" : "inactive"}
                      />
                    </div>
                    <div className="mt-4 flex flex-wrap gap-2">
                      <SectionButton
                        label="Test"
                        icon={Play}
                        busy={utilityBusy === `test-webhook-${id}`}
                        onClick={() => void mutateWebhook(id, "test")}
                      />
                      <SectionButton
                        label="Delete"
                        icon={Trash2}
                        tone="danger"
                        busy={utilityBusy === `delete-webhook-${id}`}
                        onClick={() => void mutateWebhook(id, "delete")}
                      />
                    </div>
                  </div>
                );
              }}
            />
          </div>
        );

      case "security":
        return (
          <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(320px,0.9fr)]">
            <LivePanel title="Operator security posture" meta="desktop context">
              <ValueList
                items={[
                  { label: "Cloud identity", value: pickString(cloudSecurityMe, ["email", "user.email"], status.user?.email || "unknown") },
                  { label: "Plan", value: status.user?.plan || pickString(cloudSecurityMe, ["plan"], "unknown") },
                  { label: "Runtime target", value: localSnapshot.runtimeContext?.apiUrl || status.apiUrl || "unknown" },
                  { label: "Gateway", value: status.openclaw?.gatewayUrl || "not configured" },
                ]}
              />
            </LivePanel>
            <LivePanel title="Credential inventory" meta={`${cloudKeys.length} keys`}>
              {cloudKeys.length === 0 ? (
                <LiveEmptyState
                  title="No keys returned"
                  message="The API key ledger is empty or unavailable for this operator."
                />
              ) : (
                <div className="space-y-3">
                  {cloudKeys.slice(0, 6).map((keyRecord, index) => (
                    <div
                      key={pickString(keyRecord, ["id"], `key-record-${index}`)}
                      className="rounded-[6px] border border-[#2b2b26] bg-[#11120f] p-4"
                    >
                      <p className="text-sm font-semibold text-[#eee9dc]">{pickString(keyRecord, ["name"], "API key")}</p>
                      <p className="mt-1 font-mono text-xs text-[#8d867a]">{maskValue(pickString(keyRecord, ["id"], ""))}</p>
                    </div>
                  ))}
                </div>
              )}
            </LivePanel>
          </div>
        );

      case "analytics":
        return (
          <div className="space-y-4">
            <LiveKpiGrid>
              <LiveStatCard
                label="Total runs"
                value={formatCount(pickNumber(analyticsSummary, ["total_runs"], 0))}
                detail="Runs counted in the selected analytics window."
              />
              <LiveStatCard
                label="Avg latency"
                value={`${Math.round(pickNumber(analyticsSummary, ["avg_latency_ms"], 0))}ms`}
                detail="Average latency over the current reporting window."
                status={asDashboardStatus("running")}
              />
              <LiveStatCard
                label="Active agents"
                value={formatCount(pickNumber(analyticsSummary, ["active_agents"], 0))}
                detail="Agents marked active in analytics."
              />
              <LiveStatCard
                label="Failed runs"
                value={formatCount(pickNumber(analyticsSummary, ["failed_runs"], 0))}
                detail="Failed runs in the selected window."
                status={asDashboardStatus(
                  pickNumber(analyticsSummary, ["failed_runs"], 0) > 0 ? "warning" : "healthy",
                )}
              />
            </LiveKpiGrid>
            <div className="grid gap-4 xl:grid-cols-2">
              <RecordStack
                title="Run trend samples"
                meta={`${cloudRunsTrend.length} points`}
                records={cloudRunsTrend}
                emptyTitle="No run trend samples"
                emptyMessage="Analytics has not returned run trend data yet."
                renderRecord={(point) => (
                  <div
                    key={`${pickString(point, ["timestamp"], "")}-${pickNumber(point, ["value"], 0)}`}
                    className="rounded-[6px] border border-[#2b2b26] bg-[#11120f] p-4"
                  >
                    <p className="text-sm font-semibold text-[#eee9dc]">{formatDateTime(pickString(point, ["timestamp"], ""))}</p>
                    <p className="mt-1 text-sm text-[#999284]">{pickNumber(point, ["value"], 0)} runs</p>
                  </div>
                )}
              />
              <RecordStack
                title="Latency trend samples"
                meta={`${cloudLatencyTrend.length} points`}
                records={cloudLatencyTrend}
                emptyTitle="No latency trend samples"
                emptyMessage="Analytics has not returned latency trend data yet."
                renderRecord={(point) => (
                  <div
                    key={`${pickString(point, ["timestamp"], "")}-${pickNumber(point, ["value"], 0)}`}
                    className="rounded-[6px] border border-[#2b2b26] bg-[#11120f] p-4"
                  >
                    <p className="text-sm font-semibold text-[#eee9dc]">{formatDateTime(pickString(point, ["timestamp"], ""))}</p>
                    <p className="mt-1 text-sm text-[#999284]">{Math.round(pickNumber(point, ["value"], 0))}ms latency</p>
                  </div>
                )}
              />
            </div>
          </div>
        );

      case "swarm":
        return (
          <RecordStack
            title="Swarm topology"
            meta={`${cloudSwarms.length} records`}
            records={cloudSwarms}
            emptyTitle="No swarms"
            emptyMessage="Grouped agent topology will appear here once the swarm contract has data."
            renderRecord={(swarm) => (
              <div
                key={pickString(swarm, ["id"], `swarm-${pickString(swarm, ["name"], "fallback")}`)}
                className="rounded-[6px] border border-[#2b2b26] bg-[#11120f] p-4"
              >
                <p className="text-sm font-semibold text-[#eee9dc]">{pickString(swarm, ["name", "id"], "Swarm")}</p>
                <p className="mt-1 text-sm text-[#999284]">{jsonPreview(swarm)}</p>
              </div>
            )}
          />
        );

      case "channels":
        return (
          <LivePanel title="Channel posture" meta="native support surface">
            <ValueList
              items={[
                { label: "Assistant", value: status.assistant?.name || "not bound" },
                { label: "Gateway status", value: status.assistant?.gatewayStatus || "unknown" },
                {
                  label: "Enabled channels",
                  value:
                    isRecord(cloudOverview?.assistant) && Array.isArray(cloudOverview.assistant.channels)
                      ? String(
                          (cloudOverview.assistant.channels as Array<Record<string, unknown>>).filter((entry) =>
                            pickBoolean(entry, ["enabled"], false),
                          ).length,
                        )
                      : "unknown",
                },
              ]}
            />
          </LivePanel>
        );

      case "history":
        return (
          <LivePanel title="Operator history" meta="native audit rail">
            <div className="space-y-3 text-sm text-[#c8c0b0]">
              <p>Recent activity is anchored in live runs, alerts, budgets, and local session state.</p>
              <p>Use this route as the desktop-native audit trail entrypoint instead of redirecting away from it.</p>
              <p>Last desktop sync: {formatDateTime(status.lastUpdated)}</p>
            </div>
          </LivePanel>
        );

      case "skills":
        return (
          <LivePanel title="Installed skills" meta="workspace posture">
            {localSnapshot.assistantOverview && "installed_skills" in localSnapshot.assistantOverview ? (
              <div className="space-y-3">
                {localSnapshot.assistantOverview.installed_skills.length === 0 ? (
                  <LiveEmptyState title="No installed skills" message="Skill inventory will appear here once the workspace reports them." />
                ) : (
                  localSnapshot.assistantOverview.installed_skills.map((skill) => (
                    <div key={skill.id} className="rounded-[6px] border border-[#2b2b26] bg-[#11120f] p-4">
                      <p className="text-sm font-semibold text-[#eee9dc]">{skill.name}</p>
                      <p className="mt-1 font-mono text-xs text-[#8d867a]">{skill.id}</p>
                    </div>
                  ))
                )}
              </div>
            ) : (
              <LiveEmptyState title="Assistant overview unavailable" message="Bind an assistant to inspect installed workspace skills." />
            )}
          </LivePanel>
        );

      case "spawn":
        return (
          <LivePanel title="Spawn new operator asset" meta="native entrypoint">
            <div className="space-y-4 text-sm text-[#c8c0b0]">
              <p>This route stays native in desktop mode and now points directly at the local agent/deployment bootstrap surface.</p>
              <SectionButton
                label="Open Agents"
                icon={Bot}
                tone="primary"
                onClick={() => void openDesktopDestination("/dashboard/agents")}
              />
            </div>
          </LivePanel>
        );

      case "logs":
        return (
          <LivePanel title="Machine logs and failures" meta="runtime posture">
            <ValueList
              items={[
                { label: "Bridge state", value: status.bridge.state || "unknown" },
                { label: "Last bridge error", value: status.bridge.lastError || "none" },
                { label: "Gateway health", value: status.openclaw?.health || "unknown" },
                { label: "Governance health", value: status.faramesh?.health || "unknown" },
              ]}
            />
          </LivePanel>
        );

      case "orchestration":
        return (
          <LivePanel title="Orchestration lane" meta="native admin surface">
            <div className="space-y-3 text-sm text-[#c8c0b0]">
              <p>This route is now native in desktop mode and reserved for future workflow contracts.</p>
              <p>Until those contracts exist, it stays honest about current runtime, operator, and governance posture.</p>
            </div>
          </LivePanel>
        );

      case "memory":
        return (
          <LivePanel title="Memory posture" meta="native admin surface">
            <div className="space-y-3 text-sm text-[#c8c0b0]">
              <p>Memory controls stay hidden until retention and retrieval semantics are backed by real contracts.</p>
              <p>The desktop route remains useful by showing workspace posture and leaving room for the real feature.</p>
            </div>
          </LivePanel>
        );
    }
  })();
  const resolvedRouteContent = routeContent ?? (
    <LiveEmptyState
      title={`${meta.title} native surface unavailable`}
      message="This desktop build does not have a native renderer for the canonical route. Use the shared dashboard surface for this route instead."
    />
  );

  return (
    <div className="space-y-4 [&_button]:focus-visible:outline [&_button]:focus-visible:outline-2 [&_button]:focus-visible:outline-offset-2 [&_button]:focus-visible:outline-[#ff7847] [&_input]:focus-visible:outline [&_input]:focus-visible:outline-2 [&_input]:focus-visible:outline-offset-2 [&_input]:focus-visible:outline-[#ff7847] [&_select]:focus-visible:outline [&_select]:focus-visible:outline-2 [&_select]:focus-visible:outline-offset-2 [&_select]:focus-visible:outline-[#ff7847]">
      <RouteHeader
        title={meta.title}
        description={meta.description}
        icon={meta.icon}
        iconTone={meta.iconTone}
        badge={meta.badge}
        stats={headerStats}
      />

      {bridgeWarning ? (
        <InlineAlert
          title="Bridge recovery"
          tone="danger"
          message={`${status.bridge.pythonCommand || "unknown interpreter"} · ${status.bridge.lastError || "Bridge is not healthy."}`}
        />
      ) : null}

      {localStackOffline ? (
        <InlineAlert
          title="Local stack stopped"
          message="This route is native, but the local control plane is offline. Bring it online to unlock machine-local actions."
        />
      ) : null}

      {cloudState.error ? (
        <InlineAlert title="Cloud route degraded" message={cloudState.error} />
      ) : null}

      {actionError ? (
        <InlineAlert title="Action failed" tone="danger" message={actionError} />
      ) : null}

      <DesktopJobNotice job={job} onDismiss={resetJob} />

      <LivePanel title="Desktop operator context" meta="shared action strip">
        <div className="flex flex-wrap gap-2">
          <SectionButton label="Refresh" icon={RefreshCw} onClick={() => void reloadAll()} busy={utilityBusy === "refresh"} />
          <SectionButton
            label="Run Doctor"
            icon={Wrench}
            tone="primary"
            busy={job.id === "doctor" && job.status === "running"}
            onClick={() => void runDoctorJob()}
          />
          <SectionButton
            label="Open TUI"
            icon={TerminalSquare}
            busy={utilityBusy === "tui"}
            onClick={() =>
              void runUtilityAction("tui", async () => {
                await window.mutxDesktop!.bridge.runtime.openSurface("tui");
              })
            }
          />
          <SectionButton
            label="Open Terminal"
            icon={Globe}
            busy={utilityBusy === "terminal"}
            onClick={() =>
              void runUtilityAction("terminal", async () => {
                await window.mutxDesktop!.bridge.system.openTerminal(
                  status.assistant?.workspace || localSnapshot.controlPlane?.path || undefined,
                );
              })
            }
          />
          <SectionButton
            label="Reveal Workspace"
            icon={FolderOpen}
            disabled={!status.assistant?.workspace}
            busy={utilityBusy === "workspace"}
            onClick={() =>
              void runUtilityAction("workspace", async () => {
                await window.mutxDesktop!.bridge.system.revealInFinder(status.assistant!.workspace!);
              })
            }
          />
          <SectionButton
            label={status.localControlPlane?.ready ? "Stop Local Stack" : "Start Local Stack"}
            icon={Power}
            busy={
              (job.id === "controlPlaneStart" || job.id === "controlPlaneStop") &&
              job.status === "running"
            }
            onClick={() =>
              void (status.localControlPlane?.ready ? runControlPlaneStopJob() : runControlPlaneStartJob())
            }
          />
          <SectionButton
            label="Resync Runtime"
            icon={RefreshCw}
            busy={job.id === "runtimeResync" && job.status === "running"}
            onClick={() => void runRuntimeResyncJob()}
          />
          <SectionButton
            label="Restart Governance"
            icon={Shield}
            busy={job.id === "governanceRestart" && job.status === "running"}
            onClick={() => void runGovernanceRestartJob()}
          />
          <SectionButton
            label="Overview"
            icon={ArrowRight}
            onClick={() => void openDesktopDestination("/dashboard")}
          />
          {shouldShowInspectorAction ? (
            <SectionButton
              label={
                compactViewport
                  ? inspectorDrawerOpen
                    ? "Hide Inspector"
                    : "Show Inspector"
                  : shouldShowInlineInspector
                    ? "Hide Inspector"
                    : "Show Inspector"
              }
              icon={ArrowRight}
              onClick={toggleInspector}
            />
          ) : null}
        </div>
      </LivePanel>

      <LiveKpiGrid>
        {localRuntimeSummary.map((item) => (
          <LiveStatCard
            key={item.label}
            label={item.label}
            value={item.value}
            detail={item.detail}
            status={item.status}
          />
        ))}
      </LiveKpiGrid>

      {shouldShowAuthPanel || cloudState.authRequired ? (
        <LivePanel title="Operator session required" meta="desktop-first identity">
          <div className="grid gap-4 xl:grid-cols-[minmax(320px,0.92fr)_minmax(0,1.08fr)]">
            <form className="space-y-4" onSubmit={(event) => void submitInlineAuth(event)}>
              <div className="flex flex-wrap gap-2">
                {(["login", "register", "local"] as const).map((mode) => (
                  <button
                    key={mode}
                    type="button"
                    onClick={() => setAuthMode(mode)}
                    className={cn(
                      "rounded-[6px] border px-3 py-2 text-sm transition",
                      authMode === mode
                        ? "border-[#663619] bg-[#21150f] text-[#ff8355]"
                        : "border-[#2b2b26] bg-[#11120f] text-[#c8c0b0]",
                    )}
                  >
                    {mode === "local" ? "Local Bootstrap" : mode === "register" ? "Register" : "Login"}
                  </button>
                ))}
              </div>
              {authMode !== "login" ? (
                <input
                  aria-label="Operator name"
                  value={authName}
                  onChange={(event) => setAuthName(event.target.value)}
                  placeholder="Name"
                  className="w-full rounded-[6px] border border-[#2b2b26] bg-[#11120f] px-3 py-2.5 text-sm text-[#eee9dc] outline-none"
                />
              ) : null}
              {authMode !== "local" ? (
                <>
                  <input
                    aria-label="Operator email"
                    value={authEmail}
                    onChange={(event) => setAuthEmail(event.target.value)}
                    placeholder="Email"
                    className="w-full rounded-[6px] border border-[#2b2b26] bg-[#11120f] px-3 py-2.5 text-sm text-[#eee9dc] outline-none"
                  />
                  <input
                    aria-label="Operator password"
                    type="password"
                    value={authPassword}
                    onChange={(event) => setAuthPassword(event.target.value)}
                    placeholder="Password"
                    className="w-full rounded-[6px] border border-[#2b2b26] bg-[#11120f] px-3 py-2.5 text-sm text-[#eee9dc] outline-none"
                  />
                </>
              ) : null}
              <SectionButton
                label={authMode === "local" ? "Bootstrap Locally" : authMode === "register" ? "Create Account" : "Sign In"}
                icon={authMode === "local" ? Zap : Power}
                tone="primary"
                busy={authBusy}
                onClick={() => undefined}
                type="submit"
              />
            </form>

            <div className="space-y-3">
              <InlineAlert
                title="Desktop-first operator context"
                message="Every native route can now recover auth inline. Use local bootstrap for machine-local control or sign in with a cloud session."
              />
              <InlineAlert
                title="Current runtime target"
                message={`${status.mode === "local" ? "Local" : "Hosted"} · ${localSnapshot.runtimeContext?.apiUrl || status.apiUrl || "unknown API"}`}
              />
            </div>
          </div>
        </LivePanel>
      ) : assistantMissing ? (
        <LivePanel title="Assistant binding required" meta="inline recovery">
          <div className="grid gap-4 xl:grid-cols-[minmax(320px,0.92fr)_minmax(0,1.08fr)]">
            <div className="space-y-4">
              <p className="text-sm leading-6 text-[#c8c0b0]">
                This route needs an assistant and workspace binding, but the current operator session does not have one yet.
              </p>
              <input
                aria-label="Assistant name"
                value={assistantName}
                onChange={(event) => setAssistantName(event.target.value)}
                className="w-full rounded-[6px] border border-[#2b2b26] bg-[#11120f] px-3 py-2.5 text-sm text-[#eee9dc] outline-none"
              />
              <div className="flex flex-wrap gap-2">
                <SectionButton label="Run Real Setup" icon={Play} tone="primary" onClick={() => void runAssistantSetup()} />
                <SectionButton
                  label="Overview"
                  icon={ArrowRight}
                  onClick={() => void openDesktopDestination("/dashboard")}
                />
                <SectionButton
                  label="Open Terminal"
                  icon={TerminalSquare}
                  onClick={() =>
                    void runUtilityAction("assistant-terminal", async () => {
                      await window.mutxDesktop!.bridge.system.openTerminal(localSnapshot.controlPlane?.path || undefined);
                    })
                  }
                />
              </div>
            </div>
            <div className="rounded-[6px] border border-[#2b2b26] bg-[#11120f] p-4">
              <p className="text-sm font-semibold text-[#eee9dc]">What setup will do</p>
              <p className="mt-2 text-sm leading-6 text-[#999284]">
                It drives the real desktop bridge setup flow, binds a workspace, and refreshes the native context without bouncing you into a separate product area.
              </p>
            </div>
          </div>
        </LivePanel>
      ) : null}

      {localSnapshot.loading || cloudState.loading ? (
        <div className="grid gap-4 2xl:grid-cols-[minmax(0,1fr)_340px]">
          <LivePanel title={`${meta.title} data`} meta="loading">
            <div className="grid gap-4 xl:grid-cols-2">
              {Array.from({ length: 4 }).map((_, index) => (
                <div key={index} className="h-28 motion-safe:animate-pulse motion-reduce:animate-none rounded-[6px] border border-[#2b2b26] bg-[#11120f]" />
              ))}
            </div>
          </LivePanel>
          <div className="space-y-4">
            <div className="h-40 motion-safe:animate-pulse motion-reduce:animate-none rounded-[6px] border border-[#2b2b26] bg-[#11120f]" />
            <div className="h-56 motion-safe:animate-pulse motion-reduce:animate-none rounded-[6px] border border-[#2b2b26] bg-[#11120f]" />
            <div className="h-64 motion-safe:animate-pulse motion-reduce:animate-none rounded-[6px] border border-[#2b2b26] bg-[#11120f]" />
          </div>
        </div>
      ) : localSnapshot.error && !routeContent ? (
        <LiveErrorState title={`${meta.title} unavailable`} message={localSnapshot.error} />
      ) : supportsRouteInspector ? (
        <>
          <div className="min-w-0">{resolvedRouteContent}</div>
          <InspectorDrawer
            open={compactViewport && inspectorDrawerOpen}
            title={`${meta.title} Inspector`}
            onClose={() => setInspectorDrawerOpen(false)}
          >
            {routeInspectorContent}
          </InspectorDrawer>
        </>
      ) : (
        <div className="grid gap-4 2xl:grid-cols-[minmax(0,1fr)_340px]">
          <div className="min-w-0">{resolvedRouteContent}</div>
          <div className="min-w-0">{inspectorRail}</div>
        </div>
      )}
    </div>
  );
}
