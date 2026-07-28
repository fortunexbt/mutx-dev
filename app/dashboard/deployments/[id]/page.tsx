"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import {
  Activity,
  ArrowLeft,
  Calendar,
  Check,
  Copy,
  Loader2,
  Power,
  RefreshCcw,
  Server,
  ShieldAlert,
  Trash2,
} from "lucide-react";

import { ApiRequestError, readJson, writeJson } from "@/components/app/http";
import { DeploymentHistory } from "@/components/app/DeploymentHistory";
import {
  deploymentAllowsAction,
  deploymentErrorMessage,
  type DeploymentWithActions,
} from "@/components/app/DeploymentsPageClient";
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

type Deployment = DeploymentWithActions;
type DeploymentEvent = NonNullable<Deployment["events"]>[number];
type BusyAction = "refresh" | "start" | "stop" | "restart" | "scale" | "terminate" | null;
type LoadFailureKind = "forbidden" | "not-found" | "server" | "other" | null;

function shortId(value: string) {
  return value.length <= 16 ? value : `${value.slice(0, 8)}...${value.slice(-4)}`;
}

function actionToneClass(tone: "neutral" | "primary" | "danger") {
  switch (tone) {
    case "primary":
      return "border-sky-300/24 bg-sky-300/12 text-sky-100 hover:bg-sky-300/18";
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
  tone?: "neutral" | "primary" | "danger";
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

export default function DeploymentDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const deploymentId = typeof params?.id === "string" ? params.id : "";

  const [deployment, setDeployment] = useState<Deployment | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [loadFailureKind, setLoadFailureKind] = useState<LoadFailureKind>(null);
  const [authRequired, setAuthRequired] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [busyAction, setBusyAction] = useState<BusyAction>(null);
  const [scaleDialogOpen, setScaleDialogOpen] = useState(false);
  const [scaleReplicas, setScaleReplicas] = useState(1);
  const [terminateDialogOpen, setTerminateDialogOpen] = useState(false);
  const [copied, setCopied] = useState(false);

  async function loadDeployment(options?: { preserveLoading?: boolean }) {
    const preserveLoading = options?.preserveLoading ?? false;

    if (!preserveLoading) {
      setLoading(true);
    }

    try {
      const payload = await readJson<Deployment>(`/api/dashboard/deployments/${encodeURIComponent(deploymentId)}`);
      setDeployment(payload);
      setAuthRequired(false);
      setError(null);
      setLoadFailureKind(null);
    } catch (loadError) {
      if (loadError instanceof ApiRequestError && loadError.status === 401) {
        setAuthRequired(true);
        setDeployment(null);
        setError(null);
        setLoadFailureKind(null);
      } else if (loadError instanceof ApiRequestError && loadError.status === 404) {
        setAuthRequired(false);
        setDeployment(null);
        setError(null);
        setLoadFailureKind("not-found");
      } else {
        setAuthRequired(false);
        setError(deploymentErrorMessage(loadError, "Failed to load deployment."));
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
    if (!deploymentId) return;
    void loadDeployment();
  }, [deploymentId]);

  async function handleAction(action: Exclude<BusyAction, null>, runner: () => Promise<void>) {
    setActionError(null);
    setBusyAction(action);

    try {
      await runner();
    } catch (actionFailure) {
      if (actionFailure instanceof ApiRequestError && actionFailure.status === 401) {
        setAuthRequired(true);
        setDeployment(null);
      } else if (actionFailure instanceof ApiRequestError && actionFailure.status === 403) {
        setDeployment(null);
        setError(deploymentErrorMessage(actionFailure, "Deployment action denied."));
        setLoadFailureKind("forbidden");
        setScaleDialogOpen(false);
        setTerminateDialogOpen(false);
      } else if (actionFailure instanceof ApiRequestError && actionFailure.status === 404) {
        setDeployment(null);
        setLoadFailureKind("not-found");
      } else {
        setActionError(deploymentErrorMessage(actionFailure, "Deployment action failed."));
      }
    } finally {
      setBusyAction(null);
    }
  }

  const handleRefresh = () =>
    handleAction("refresh", async () => {
      await loadDeployment({ preserveLoading: true });
    });

  const handleStart = () =>
    handleAction("start", async () => {
      await writeJson<unknown>(
        `/api/dashboard/deployments/${encodeURIComponent(deploymentId)}?action=scale`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ replicas: Math.max(deployment?.replicas ?? 1, 1) }),
        },
      );
      await loadDeployment({ preserveLoading: true });
    });

  const handleStop = () =>
    handleAction("stop", async () => {
      await writeJson<unknown>(
        `/api/dashboard/deployments/${encodeURIComponent(deploymentId)}?action=scale`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ replicas: 0 }),
        },
      );
      await loadDeployment({ preserveLoading: true });
    });

  const handleRestart = () =>
    handleAction("restart", async () => {
      await writeJson<unknown>(`/api/dashboard/deployments/${encodeURIComponent(deploymentId)}?action=restart`, {
        method: "POST",
      });
      await loadDeployment({ preserveLoading: true });
    });

  const handleScale = () =>
    handleAction("scale", async () => {
      await writeJson<unknown>(
        `/api/dashboard/deployments/${encodeURIComponent(deploymentId)}?action=scale`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ replicas: scaleReplicas }),
        },
      );
      setScaleDialogOpen(false);
      await loadDeployment({ preserveLoading: true });
    });

  const handleTerminate = () =>
    handleAction("terminate", async () => {
      await writeJson(`/api/dashboard/deployments/${encodeURIComponent(deploymentId)}`, { method: "DELETE" });
      router.push("/dashboard/deployments");
    });

  const openScaleDialog = () => {
    if (!deployment) return;
    setScaleReplicas(Math.max(deployment.replicas, 1));
    setScaleDialogOpen(true);
  };

  const handleCopyId = async () => {
    if (!deployment) return;
    await navigator.clipboard.writeText(deployment.id);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1800);
  };

  const routeHeader = (
    <RouteHeader
      title={deployment ? `Deployment ${shortId(deployment.id)}` : "Deployment"}
      description="Inspect rollout state, timeline, and runtime metadata for this deployment record."
      icon={Server}
      iconTone="text-emerald-200 bg-emerald-400/10 border-emerald-400/20"
      badge="deployment detail"
      stats={[
        { label: "Status", value: deployment?.status || "loading", tone: deployment ? (asDashboardStatus(deployment.status) === "error" ? "danger" : asDashboardStatus(deployment.status) === "warning" ? "warning" : asDashboardStatus(deployment.status) === "success" || asDashboardStatus(deployment.status) === "running" ? "success" : "neutral") : "neutral" },
        { label: "Replicas", value: deployment ? String(deployment.replicas) : "--" },
      ]}
    />
  );
  const recentEvents: DeploymentEvent[] = deployment?.events?.slice(0, 6) ?? [];

  if (loading) {
    return (
      <div className="space-y-4">
        {routeHeader}
        <LiveLoading title="Deployment detail" />
      </div>
    );
  }

  if (authRequired) {
    return (
      <div className="space-y-4">
        {routeHeader}
        <LiveAuthRequired
          title="Operator session required"
          message="Sign in again to inspect this deployment record and use rollout actions from the dashboard."
        />
      </div>
    );
  }

  if (loadFailureKind === "not-found") {
    return (
      <div className="space-y-4">
        {routeHeader}
        <EmptyState
          title="Deployment not found"
          message="This deployment no longer exists or was removed from the current tenant."
          icon={<Server className="h-7 w-7" />}
        />
      </div>
    );
  }

  if (loadFailureKind === "forbidden") {
    return (
      <div className="space-y-4">
        {routeHeader}
        <LiveForbidden
          title="Deployment permission required"
          message={error || "Your account cannot inspect or operate this deployment. Rollout controls are unavailable."}
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
                ? "Deployment control plane unavailable"
                : "Deployment detail unavailable"
          }
          message={error}
        />
      </div>
    );
  }

  if (!deployment) {
    return (
      <div className="space-y-4">
        {routeHeader}
        <EmptyState
          title="Deployment not found"
          message="The requested deployment record could not be resolved from the dashboard API."
          icon={<Server className="h-7 w-7" />}
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
        <ActionButton label="Back to Deployments" icon={ArrowLeft} onClick={() => router.push("/dashboard/deployments")} />
        <ActionButton
          label="Refresh"
          icon={RefreshCcw}
          busy={busyAction === "refresh"}
          disabled={busyAction !== null}
          onClick={handleRefresh}
        />
        {deploymentAllowsAction(deployment, "start") ? (
          <ActionButton
            label="Start Deployment"
            icon={Power}
            tone="primary"
            busy={busyAction === "start"}
            disabled={busyAction !== null}
            onClick={handleStart}
          />
        ) : null}
        {deploymentAllowsAction(deployment, "stop") ? (
          <ActionButton
            label="Stop Deployment"
            icon={Power}
            busy={busyAction === "stop"}
            disabled={busyAction !== null}
            onClick={handleStop}
          />
        ) : null}
        {deploymentAllowsAction(deployment, "restart") ? (
          <ActionButton
            label="Restart Deployment"
            icon={RefreshCcw}
            tone="primary"
            busy={busyAction === "restart"}
            disabled={busyAction !== null}
            onClick={handleRestart}
          />
        ) : null}
        {deploymentAllowsAction(deployment, "scale") ? (
          <ActionButton
            label="Scale Deployment"
            icon={Server}
            disabled={busyAction !== null}
            onClick={openScaleDialog}
          />
        ) : null}
        <Link
          href={`/dashboard/logs?deploymentId=${encodeURIComponent(deployment.id)}`}
          className={`inline-flex items-center gap-2 rounded-[12px] border px-3.5 py-2 text-sm font-medium transition ${actionToneClass("neutral")}`}
        >
          <Activity className="h-4 w-4" />
          View Logs
        </Link>
        {deploymentAllowsAction(deployment, "terminate") ? (
          <ActionButton
            label="Terminate Deployment"
            icon={Trash2}
            tone="danger"
            disabled={busyAction !== null}
            onClick={() => setTerminateDialogOpen(true)}
          />
        ) : null}
      </div>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.2fr)_minmax(0,0.8fr)]">
        <LivePanel title="Deployment record" meta={shortId(deployment.id)}>
          <div className="space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-[16px] border border-[#24303d] bg-[#0a1017] px-4 py-3">
              <div className="min-w-0">
                <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-500">Identifier</p>
                <p className="mt-2 truncate font-[family:var(--font-mono)] text-sm text-slate-100">{deployment.id}</p>
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
              <LiveMiniStat label="Agent assignment" value={deployment.agent_id} detail="Source agent bound to this runtime record" icon={Server} />
              <LiveMiniStat label="Version" value={deployment.version || "Unknown"} detail="Reported rollout revision" icon={Server} />
              <LiveMiniStat label="Node" value={deployment.node_id || "Unassigned"} detail="Execution node for the current record" icon={Server} />
              <div
                className="rounded-[16px] border p-3"
                style={{
                  borderColor: dashboardTokens.borderSubtle,
                  backgroundColor: dashboardTokens.bgInset,
                }}
              >
                <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.16em]" style={{ color: dashboardTokens.textMuted }}>
                  <Activity className="h-3.5 w-3.5" />
                  <span>Status</span>
                </div>
                <div className="mt-2">
                  <StatusBadge status={asDashboardStatus(deployment.status)} label={deployment.status} />
                </div>
                <p className="mt-2 text-[11px] leading-5" style={{ color: dashboardTokens.textMuted }}>
                  Live runtime state reported for this deployment.
                </p>
              </div>
            </LiveMiniStatGrid>
          </div>
        </LivePanel>

        <LivePanel title="Timeline" meta="timestamps">
          <LiveMiniStatGrid>
            <LiveMiniStat
              label="Started"
              value={formatDateTime(deployment.started_at)}
              detail={formatRelativeTime(deployment.started_at)}
              icon={Calendar}
            />
            <LiveMiniStat
              label="Ended"
              value={formatDateTime(deployment.ended_at)}
              detail={formatRelativeTime(deployment.ended_at)}
              icon={Calendar}
            />
          </LiveMiniStatGrid>
        </LivePanel>

        <LivePanel title="Version posture" meta="rollback ready">
          <div className="rounded-[16px] border border-[#24303d] bg-[#0a1017] p-4">
            <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-500">
              Current rollout revision
            </p>
            <p className="mt-2 text-sm font-medium text-slate-100">
              {deployment.version || "Unknown"}
            </p>
            <p className="mt-3 text-sm leading-6 text-slate-400">
              Inspect recorded deployment snapshots and roll back to a known-good version
              without leaving this deployment record.
            </p>
            <div className="mt-4">
              <DeploymentHistory
                deploymentId={deployment.id}
                buttonLabel="Inspect version history"
                buttonClassName="inline-flex items-center gap-2 rounded-[12px] border border-[#2f3c49] bg-[#10161d] px-3.5 py-2 text-sm font-medium text-[#dce3ec] transition hover:border-sky-300/18"
                onRollbackComplete={() => loadDeployment({ preserveLoading: true })}
              />
            </div>
          </div>
        </LivePanel>
      </div>

      {deployment.error_message ? (
        <LivePanel title="Runtime error" meta="operator attention">
          <div className="flex items-start gap-3 rounded-[16px] border border-rose-400/18 bg-rose-400/8 px-4 py-3">
            <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0 text-rose-300" />
            <p className="text-sm leading-6 text-rose-100">{deployment.error_message}</p>
          </div>
        </LivePanel>
      ) : null}

      <LivePanel title="Recent events" meta={`${deployment.events?.length || 0} tracked`}>
        {recentEvents.length > 0 ? (
          <div className="space-y-3">
            {recentEvents.map((deploymentEvent, index) => (
              <article
                key={`${deploymentEvent.event_type}-${deploymentEvent.status}-${index}`}
                className="rounded-[16px] border border-[#24303d] bg-[#0a1017] px-4 py-3"
              >
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <p className="text-sm font-medium text-slate-100">{deploymentEvent.event_type}</p>
                  <StatusBadge
                    status={asDashboardStatus(deploymentEvent.status || "idle")}
                    label={deploymentEvent.status || "recorded"}
                  />
                </div>
                <p className="mt-2 text-xs text-slate-500">
                  Node {deploymentEvent.node_id || "unassigned"}
                  {deploymentEvent.error_message ? ` • ${deploymentEvent.error_message}` : ""}
                </p>
              </article>
            ))}
          </div>
        ) : (
          <p className="text-sm leading-6 text-slate-400">No deployment events are attached to this record yet.</p>
        )}
      </LivePanel>

      <DashboardDialog
        open={scaleDialogOpen}
        onOpenChange={setScaleDialogOpen}
        title="Scale Deployment"
        description="Set the desired runtime capacity for this active deployment."
        footer={
          <>
            <button
              type="button"
              onClick={() => setScaleDialogOpen(false)}
              disabled={busyAction === "scale"}
              className="rounded-[12px] border border-[#2e3946] bg-[#0d131a] px-4 py-2 text-sm font-medium text-slate-200 transition hover:border-sky-300/24 disabled:opacity-50"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={() => void handleScale()}
              disabled={busyAction !== null || scaleReplicas === deployment.replicas}
              className="rounded-[12px] bg-sky-400 px-4 py-2 text-sm font-medium text-[#071018] transition hover:bg-sky-300 disabled:opacity-50"
            >
              {busyAction === "scale" ? "Scaling..." : "Apply Scale"}
            </button>
          </>
        }
      >
        <label className="block text-sm font-medium text-slate-200" htmlFor="deployment-replicas">
          Desired replicas
        </label>
        <input
          id="deployment-replicas"
          type="number"
          min={1}
          max={10}
          value={scaleReplicas}
          onChange={(event) => {
            const nextReplicas = Number.parseInt(event.target.value, 10);
            setScaleReplicas(Number.isFinite(nextReplicas) ? Math.min(10, Math.max(1, nextReplicas)) : 1);
          }}
          className="mt-2 w-full rounded-[14px] border border-[#2e3946] bg-[#0b1017] px-4 py-3 text-sm text-white focus:border-sky-300/30 focus:outline-none"
        />
        <p className="mt-2 text-xs leading-5 text-slate-500">Active deployments support between 1 and 10 replicas.</p>
      </DashboardDialog>

      <DashboardDialog
        open={terminateDialogOpen}
        onOpenChange={setTerminateDialogOpen}
        title="Terminate Deployment"
        description="This stops the deployment permanently while retaining its lifecycle history."
        footer={
          <>
            <button
              type="button"
              onClick={() => setTerminateDialogOpen(false)}
              className="rounded-[12px] border border-[#2e3946] bg-[#0d131a] px-4 py-2 text-sm font-medium text-slate-200 transition hover:border-sky-300/24"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={() => {
                setTerminateDialogOpen(false);
                void handleTerminate();
              }}
              className="rounded-[12px] bg-rose-500/90 px-4 py-2 text-sm font-medium text-white transition hover:bg-rose-500"
            >
              Terminate Deployment
            </button>
          </>
        }
      >
        <p className="text-sm leading-6 text-slate-300">
          Deployment <span className="font-semibold text-white">{shortId(deployment.id)}</span> will move to the terminal killed state and cannot be restarted.
        </p>
      </DashboardDialog>
    </div>
  );
}
