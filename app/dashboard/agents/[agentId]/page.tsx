"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  ArrowLeft,
  Bot,
  Calendar,
  Check,
  Copy,
  Loader2,
  Power,
  RefreshCcw,
  Rocket,
  Settings2,
  Trash2,
  UserCircle2,
} from "lucide-react";

import { ApiRequestError, readJson, writeJson } from "@/components/app/http";
import { DashboardDialog } from "@/components/dashboard/DashboardDialog";
import { EmptyState } from "@/components/dashboard/EmptyState";
import { RouteHeader } from "@/components/dashboard/RouteHeader";
import { StatusBadge } from "@/components/dashboard/StatusBadge";
import {
  LiveAuthRequired,
  LiveErrorState,
  LiveForbidden,
  LiveLoading,
  LiveMiniStat,
  LiveMiniStatGrid,
  LivePanel,
  asDashboardStatus,
  formatDateTime,
  formatRelativeTime,
} from "@/components/dashboard/livePrimitives";
import { dashboardTokens } from "@/components/dashboard/tokens";
import { type components } from "@/app/types/api";

type Agent = components["schemas"]["AgentDetailResponse"];
type BusyAction = "refresh" | "stop" | "deploy" | "delete" | null;
type LoadFailureKind = "forbidden" | "not-found" | "server" | "other" | null;
type AgentLifecycleAction = "deploy" | "stop" | "delete";

function agentAllowsLifecycleAction(status: string, action: AgentLifecycleAction) {
  if (status === "running") return action === "stop" || action === "delete";
  if (["stopped", "failed"].includes(status)) {
    return action === "deploy" || action === "delete";
  }
  if (status === "creating") return action === "delete";
  return false;
}

function agentErrorMessage(error: unknown, fallback: string) {
  if (!(error instanceof ApiRequestError)) {
    return fallback;
  }

  if (error.status === 401) return "Your session expired. Sign in again to operate this agent.";
  if (error.status === 403) return "You do not have permission to operate this agent.";
  if (error.status === 404) return "This agent no longer exists.";
  if (error.status >= 500) return `The control plane could not complete this request. ${fallback}`;
  return error.message || fallback;
}

function shortId(value: string) {
  return value.length <= 16 ? value : `${value.slice(0, 8)}...${value.slice(-4)}`;
}

function actionToneClass(tone: "neutral" | "primary" | "warning" | "danger") {
  switch (tone) {
    case "primary":
      return "border-sky-300/24 bg-sky-300/12 text-sky-100 hover:bg-sky-300/18";
    case "warning":
      return "border-amber-400/24 bg-amber-400/10 text-amber-200 hover:bg-amber-400/16";
    case "danger":
      return "border-rose-400/24 bg-rose-400/10 text-rose-200 hover:bg-rose-400/16";
    default:
      return "border-[#2f3c49] bg-[#10161d] text-[#dce3ec] hover:border-sky-300/18";
  }
}

function ActionButton({
  label,
  icon: Icon,
  tone = "neutral",
  busy = false,
  disabled = false,
  onClick,
}: {
  label: string;
  icon: typeof ArrowLeft;
  tone?: "neutral" | "primary" | "warning" | "danger";
  busy?: boolean;
  disabled?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled || busy}
      className={`inline-flex items-center gap-2 rounded-[12px] border px-3.5 py-2 text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-50 ${actionToneClass(tone)}`}
    >
      {busy ? <Loader2 className="h-4 w-4 motion-safe:animate-spin motion-reduce:animate-none" /> : <Icon className="h-4 w-4" />}
      {label}
    </button>
  );
}

export default function AgentDetailPage() {
  const params = useParams<{ agentId: string }>();
  const router = useRouter();
  const agentId = typeof params?.agentId === "string" ? params.agentId : "";

  const [agent, setAgent] = useState<Agent | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [loadFailureKind, setLoadFailureKind] = useState<LoadFailureKind>(null);
  const [authRequired, setAuthRequired] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [busyAction, setBusyAction] = useState<BusyAction>(null);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [copied, setCopied] = useState(false);

  async function loadAgent(options?: { preserveLoading?: boolean }) {
    const preserveLoading = options?.preserveLoading ?? false;

    if (!preserveLoading) {
      setLoading(true);
    }

    try {
      const payload = await readJson<Agent>(`/api/dashboard/agents/${encodeURIComponent(agentId)}`);
      setAgent(payload);
      setAuthRequired(false);
      setError(null);
      setLoadFailureKind(null);
    } catch (loadError) {
      if (loadError instanceof ApiRequestError && loadError.status === 401) {
        setAuthRequired(true);
        setAgent(null);
        setError(null);
        setLoadFailureKind(null);
      } else if (loadError instanceof ApiRequestError && loadError.status === 404) {
        setAuthRequired(false);
        setAgent(null);
        setError(null);
        setLoadFailureKind("not-found");
      } else {
        setAuthRequired(false);
        setError(agentErrorMessage(loadError, "Failed to load agent."));
        setLoadFailureKind(
          loadError instanceof ApiRequestError && loadError.status === 403
            ? "forbidden"
            : loadError instanceof ApiRequestError && loadError.status >= 500
              ? "server"
              : "other",
        );
      }
    } finally {
      if (!preserveLoading) {
        setLoading(false);
      }
    }
  }

  useEffect(() => {
    if (!agentId) return;
    void loadAgent();
  }, [agentId]);

  async function handleAction(action: Exclude<BusyAction, null>, runner: () => Promise<void>) {
    setActionError(null);
    setBusyAction(action);

    try {
      await runner();
    } catch (actionFailure) {
      if (actionFailure instanceof ApiRequestError && actionFailure.status === 401) {
        setAuthRequired(true);
        setAgent(null);
      } else if (actionFailure instanceof ApiRequestError && actionFailure.status === 403) {
        setAgent(null);
        setError(agentErrorMessage(actionFailure, "Agent action denied."));
        setLoadFailureKind("forbidden");
        setDeleteDialogOpen(false);
      } else if (actionFailure instanceof ApiRequestError && actionFailure.status === 404) {
        setAgent(null);
        setLoadFailureKind("not-found");
      } else {
        setActionError(agentErrorMessage(actionFailure, "Agent action failed."));
      }
    } finally {
      setBusyAction(null);
    }
  }

  const handleRefresh = () =>
    handleAction("refresh", async () => {
      await loadAgent({ preserveLoading: true });
    });

  const handleStop = () =>
    handleAction("stop", async () => {
      await writeJson<unknown>(`/api/dashboard/agents/${encodeURIComponent(agentId)}?action=stop`, {
        method: "POST",
      });
      await loadAgent({ preserveLoading: true });
    });

  const handleDeploy = () =>
    handleAction("deploy", async () => {
      await writeJson<unknown>(`/api/dashboard/agents/${encodeURIComponent(agentId)}?action=deploy`, {
        method: "POST",
      });
      await loadAgent({ preserveLoading: true });
    });

  const handleDelete = () =>
    handleAction("delete", async () => {
      await writeJson(`/api/dashboard/agents/${encodeURIComponent(agentId)}`, { method: "DELETE" });
      router.push("/dashboard/agents");
    });

  const handleCopyId = async () => {
    if (!agent) return;
    await navigator.clipboard.writeText(agent.id);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1800);
  };

  const canDeploy = agent ? agentAllowsLifecycleAction(agent.status, "deploy") : false;
  const canStop = agent ? agentAllowsLifecycleAction(agent.status, "stop") : false;
  const canDelete = agent ? agentAllowsLifecycleAction(agent.status, "delete") : false;

  const routeHeader = (
    <RouteHeader
      title={agent?.name || "Agent"}
      description={
        agent?.description ||
        "Inspect identity, lifecycle, and configuration for this MUTX agent record."
      }
      icon={Bot}
      iconTone="text-sky-200 bg-sky-400/10 border-sky-400/20"
      badge="agent detail"
      stats={[
        { label: "Status", value: agent?.status || "loading", tone: agent ? (asDashboardStatus(agent.status) === "error" ? "danger" : asDashboardStatus(agent.status) === "warning" ? "warning" : asDashboardStatus(agent.status) === "success" || asDashboardStatus(agent.status) === "running" ? "success" : "neutral") : "neutral" },
        { label: "Type", value: agent?.type || "pending" },
      ]}
    />
  );

  if (loading) {
    return (
      <div className="space-y-4">
        {routeHeader}
        <LiveLoading title="Agent detail" />
      </div>
    );
  }

  if (authRequired) {
    return (
      <div className="space-y-4">
        {routeHeader}
        <LiveAuthRequired
          title="Operator session required"
          message="Sign in again to inspect this agent record and use lifecycle actions from the dashboard."
        />
      </div>
    );
  }

  if (loadFailureKind === "not-found") {
    return (
      <div className="space-y-4">
        {routeHeader}
        <EmptyState
          title="Agent not found"
          message="This agent no longer exists or was removed from the current tenant."
          icon={<Bot className="h-7 w-7" />}
        />
      </div>
    );
  }

  if (loadFailureKind === "forbidden") {
    return (
      <div className="space-y-4">
        {routeHeader}
        <LiveForbidden
          title="Agent permission required"
          message={error || "Your account cannot inspect or operate this agent. Lifecycle controls are unavailable."}
        />
      </div>
    );
  }

  if (error) {
    return (
      <div className="space-y-4">
        {routeHeader}
        <LiveErrorState
          title={
            loadFailureKind === "server"
                ? "Agent control plane unavailable"
                : "Agent detail unavailable"
          }
          message={error}
        />
      </div>
    );
  }

  if (!agent) {
    return (
      <div className="space-y-4">
        {routeHeader}
        <EmptyState
          title="Agent not found"
          message="The requested agent record could not be resolved from the dashboard API."
          icon={<Bot className="h-7 w-7" />}
        />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {routeHeader}

      {actionError ? (
        <div role="alert" className="rounded-[16px] border border-rose-400/20 bg-rose-400/10 px-4 py-3 text-sm text-rose-200">
          {actionError}
        </div>
      ) : null}

      <div className="flex flex-wrap items-center gap-2">
        <ActionButton label="Back to Agents" icon={ArrowLeft} onClick={() => router.push("/dashboard/agents")} />
        <ActionButton
          label="Refresh"
          icon={RefreshCcw}
          busy={busyAction === "refresh"}
          disabled={busyAction !== null}
          onClick={handleRefresh}
        />
        {canStop ? (
          <ActionButton
            label="Stop Agent"
            icon={Power}
            tone="warning"
            busy={busyAction === "stop"}
            disabled={busyAction !== null}
            onClick={handleStop}
          />
        ) : null}
        {canDeploy ? (
          <ActionButton
            label="Deploy Agent"
            icon={Rocket}
            tone="primary"
            busy={busyAction === "deploy"}
            disabled={busyAction !== null}
            onClick={handleDeploy}
          />
        ) : null}
        {canDelete ? (
          <ActionButton
            label="Delete Agent"
            icon={Trash2}
            tone="danger"
            disabled={busyAction !== null}
            onClick={() => setDeleteDialogOpen(true)}
          />
        ) : null}
      </div>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.2fr)_minmax(0,0.8fr)]">
        <LivePanel title="Agent record" meta={shortId(agent.id)}>
          <div className="space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-[16px] border border-[#24303d] bg-[#0a1017] px-4 py-3">
              <div className="min-w-0">
                <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-500">Identifier</p>
                <p className="mt-2 truncate font-[family:var(--font-mono)] text-sm text-slate-100">{agent.id}</p>
              </div>
              <button
                type="button"
                onClick={handleCopyId}
                className="inline-flex items-center gap-2 rounded-[12px] border border-[#2f3c49] bg-[#10161d] px-3 py-2 text-xs text-slate-200 transition hover:border-sky-300/24"
              >
                {copied ? <Check className="h-4 w-4 text-emerald-300" /> : <Copy className="h-4 w-4" />}
                {copied ? "Copied" : "Copy ID"}
              </button>
            </div>

            <LiveMiniStatGrid columns={2}>
              <LiveMiniStat label="Type" value={agent.type} detail="Configured execution profile" icon={Settings2} />
              <LiveMiniStat
                label="Config version"
                value={String(agent.config_version)}
                detail="Current stored config revision"
                icon={Settings2}
              />
              <LiveMiniStat
                label="Owner"
                value={shortId(agent.user_id)}
                detail="User record attached to this agent"
                icon={UserCircle2}
              />
              <div
                className="rounded-[16px] border p-3"
                style={{
                  borderColor: dashboardTokens.borderSubtle,
                  backgroundColor: dashboardTokens.bgInset,
                }}
              >
                <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.16em]" style={{ color: dashboardTokens.textMuted }}>
                  <Bot className="h-3.5 w-3.5" />
                  <span>Status</span>
                </div>
                <div className="mt-2">
                  <StatusBadge status={asDashboardStatus(agent.status)} label={agent.status} />
                </div>
                <p className="mt-2 text-[11px] leading-5" style={{ color: dashboardTokens.textMuted }}>
                  Runtime lifecycle signal currently reported by the control plane.
                </p>
              </div>
            </LiveMiniStatGrid>
          </div>
        </LivePanel>

        <LivePanel title="Lifecycle" meta="timestamps">
          <LiveMiniStatGrid>
            <LiveMiniStat
              label="Created"
              value={formatDateTime(agent.created_at)}
              detail={formatRelativeTime(agent.created_at)}
              icon={Calendar}
            />
            <LiveMiniStat
              label="Updated"
              value={formatDateTime(agent.updated_at)}
              detail={formatRelativeTime(agent.updated_at)}
              icon={Calendar}
            />
          </LiveMiniStatGrid>
        </LivePanel>
      </div>

      <LivePanel title="Configuration snapshot" meta={agent.config ? "live payload" : "no config"}>
        {agent.config ? (
          <pre className="overflow-x-auto rounded-[16px] border border-[#23303d] bg-[#091018] px-4 py-3 text-xs leading-6 text-slate-300">
            {JSON.stringify(agent.config, null, 2)}
          </pre>
        ) : (
          <p className="text-sm leading-6 text-slate-400">No structured config payload is stored for this agent yet.</p>
        )}
      </LivePanel>

      <DashboardDialog
        open={deleteDialogOpen}
        onOpenChange={setDeleteDialogOpen}
        title="Delete Agent"
        description="This removes the agent record from the dashboard registry. This action cannot be undone."
        footer={
          <>
            <button
              type="button"
              onClick={() => setDeleteDialogOpen(false)}
              className="rounded-[12px] border border-[#2e3946] bg-[#0d131a] px-4 py-2 text-sm font-medium text-slate-200 transition hover:border-sky-300/24"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={() => {
                setDeleteDialogOpen(false);
                void handleDelete();
              }}
              className="rounded-[12px] bg-rose-500/90 px-4 py-2 text-sm font-medium text-white transition hover:bg-rose-500"
            >
              Delete Agent
            </button>
          </>
        }
      >
        <p className="text-sm leading-6 text-slate-300">
          Agent <span className="font-semibold text-white">{agent.name}</span> will be removed from the fleet inventory.
        </p>
      </DashboardDialog>
    </div>
  );
}
