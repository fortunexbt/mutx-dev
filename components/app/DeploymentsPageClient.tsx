"use client";

import { useEffect, useState, useRef } from "react";
import Link from "next/link";
import {
  Activity,
  Calendar,
  Clock,
  Loader2,
  Plus,
  Power,
  RefreshCcw,
  RotateCcw,
  Server,
  Trash2,
  Copy,
  Check,
  X,
} from "lucide-react";
import { DeploymentSortSelect } from "./DeploymentSortSelect";

import { ApiRequestError, normalizeCollection, readJson, writeJson } from "@/components/app/http";
import { DashboardDialog } from "@/components/dashboard/DashboardDialog";
import { EmptyState as DashboardEmptyState } from "@/components/dashboard/EmptyState";
import { FilterBar } from "@/components/dashboard/FilterBar";
import { StatusBadge } from "@/components/dashboard/StatusBadge";
import {
  LiveAuthRequired,
  LiveKpiGrid,
  LiveMiniStat,
  LiveMiniStatGrid,
  LivePanel,
  LiveStatCard,
  asDashboardStatus,
  formatRelativeTime,
} from "@/components/dashboard/livePrimitives";
import { DeploymentHistory } from "./DeploymentHistory";
import { type components } from "@/app/types/api";

export type DeploymentAction = "start" | "stop" | "restart" | "scale" | "terminate";
export type DeploymentWithActions = components["schemas"]["DeploymentResponse"];
export type DeploymentActionCapabilities = {
  allowed_actions?: readonly DeploymentAction[];
};

type Deployment = DeploymentWithActions;
type Agent = components["schemas"]["AgentResponse"];

export function deploymentAllowsAction(
  deployment: DeploymentActionCapabilities,
  action: DeploymentAction,
) {
  return deployment.allowed_actions?.includes(action) ?? false;
}

export function deploymentErrorMessage(error: unknown, fallback: string) {
  if (!(error instanceof ApiRequestError)) {
    return fallback;
  }

  if (error.status === 401) return "Your session expired. Sign in again to operate deployments.";
  if (error.status === 403) return "You do not have permission to operate this deployment.";
  if (error.status === 404) return "This deployment no longer exists.";
  if (error.status >= 500) return `The control plane could not complete this request. ${fallback}`;
  return error.message || fallback;
}

function DeploymentCardSkeleton() {
  return (
    <div className="rounded-xl border border-white/5 bg-white/[0.02] p-5 motion-safe:animate-pulse motion-reduce:animate-none">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <div className="h-5 w-48 rounded bg-white/10" />
          <div className="mt-2 h-4 w-32 rounded bg-white/5" />
        </div>
        <div className="h-6 w-20 rounded-full bg-white/10" />
      </div>
      <div className="mt-4 grid gap-3 sm:grid-cols-3">
        <div className="h-12 rounded-lg bg-white/5" />
        <div className="h-12 rounded-lg bg-white/5" />
        <div className="h-12 rounded-lg bg-white/5" />
      </div>
      <div className="mt-4 flex gap-2">
        <div className="h-8 w-20 rounded bg-white/5" />
        <div className="h-8 w-20 rounded bg-white/5" />
        <div className="h-8 w-20 rounded bg-white/5" />
      </div>
    </div>
  );
}

interface DeploymentCardProps {
  deployment: Deployment;
  onRestart: (id: string) => void;
  onStop: (id: string) => void;
  onStart: (id: string) => void;
  onTerminate: (deployment: Deployment) => void;
  isProcessing: (id: string) => boolean;
  copiedId: string | null;
  onCopyId: (id: string) => void;
}

function DeploymentCard({ deployment, onRestart, onStop, onStart, onTerminate, isProcessing, copiedId, onCopyId }: DeploymentCardProps) {
  const processing = isProcessing(deployment.id);
  const copied = copiedId === deployment.id;

  return (
    <article className="dashboard-entry rounded-[20px] border border-[#273543] bg-[linear-gradient(180deg,#18212b_0%,#0f151d_100%)] p-5 shadow-[0_18px_40px_rgba(1,5,11,0.22)] transition hover:border-emerald-300/26">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <p className="truncate text-sm font-medium text-white">
              {deployment.id}
            </p>
            <button
              type="button"
              onClick={() => onCopyId(deployment.id)}
              className="inline-flex items-center gap-1 rounded-full border border-[#293543] bg-[#10161d] px-2.5 py-1 text-[11px] text-slate-500 transition-colors hover:border-cyan-400/24 hover:text-cyan-300"
              title="Copy deployment ID"
            >
              {copied ? <Check className="h-3.5 w-3.5 text-emerald-400" /> : <Copy className="h-3.5 w-3.5" />}
              {copied ? "Copied" : "Copy ID"}
            </button>
          </div>
          <p className="mt-2 truncate text-xs text-slate-500 font-[family:var(--font-mono)]">
            Agent assignment: {deployment.agent_id}
          </p>
        </div>
        <StatusBadge status={asDashboardStatus(deployment.status)} label={deployment.status} />
      </div>
      <div className="mt-4">
        <LiveMiniStatGrid columns={3}>
          <LiveMiniStat label="Replicas" value={String(deployment.replicas)} detail="Desired runtime count" icon={Server} />
          <LiveMiniStat label="Started" value={formatRelativeTime(deployment.started_at)} detail="Initial rollout timestamp" icon={Calendar} />
          <LiveMiniStat label="Updated" value={formatRelativeTime(deployment.ended_at)} detail="Most recent deployment event" icon={Clock} />
        </LiveMiniStatGrid>
      </div>
      <div className="mt-4 flex flex-wrap gap-2">
        {deploymentAllowsAction(deployment, "restart") ? (
          <button
            type="button"
            className="inline-flex items-center gap-2 rounded-[12px] border border-[#293543] bg-[#0e141b] px-3 py-2 text-xs font-medium text-white transition hover:border-emerald-400/24 hover:bg-[#131c24] disabled:opacity-50"
            onClick={() => onRestart(deployment.id)}
            disabled={processing}
          >
            <RotateCcw className={`h-3.5 w-3.5 ${processing ? "motion-safe:animate-spin motion-reduce:animate-none" : ""}`} />
            Restart
          </button>
        ) : null}
        {deploymentAllowsAction(deployment, "stop") ? (
          <button
            type="button"
            className="inline-flex items-center gap-2 rounded-[12px] border border-[#293543] bg-[#0e141b] px-3 py-2 text-xs font-medium text-white transition hover:border-amber-400/24 hover:bg-[#131c24] disabled:opacity-50"
            onClick={() => onStop(deployment.id)}
            disabled={processing}
          >
            <Power className="h-3.5 w-3.5" />
            Stop
          </button>
        ) : null}
        {deploymentAllowsAction(deployment, "start") ? (
          <button
            type="button"
            className="inline-flex items-center gap-2 rounded-[12px] border border-[#293543] bg-[#0e141b] px-3 py-2 text-xs font-medium text-white transition hover:border-emerald-400/24 hover:bg-[#131c24] disabled:opacity-50"
            onClick={() => onStart(deployment.id)}
            disabled={processing}
          >
            <Power className="h-3.5 w-3.5" />
            Start
          </button>
        ) : null}
        <Link
          href={`/dashboard/logs?deploymentId=${encodeURIComponent(deployment.id)}`}
          className="inline-flex items-center gap-2 rounded-[12px] border border-[#293543] bg-[#0e141b] px-3 py-2 text-xs font-medium text-white transition hover:border-sky-300/24 hover:bg-[#131c24]"
        >
          <Activity className="h-3.5 w-3.5" />
          Logs
        </Link>
        <DeploymentHistory deploymentId={deployment.id} />
        {deploymentAllowsAction(deployment, "terminate") ? (
          <button
            type="button"
            className="inline-flex min-h-11 items-center gap-2 rounded-[12px] border border-rose-400/20 bg-rose-400/10 px-3 py-2 text-xs font-medium text-rose-300 transition hover:bg-rose-400/20 disabled:opacity-50"
            onClick={() => onTerminate(deployment)}
            disabled={processing}
          >
            <Trash2 className="h-3.5 w-3.5" />
            Terminate
          </button>
        ) : null}
      </div>
    </article>
  );
}

function LoadingState() {
  return (
    <div className="space-y-4">
      <DeploymentCardSkeleton />
      <DeploymentCardSkeleton />
      <DeploymentCardSkeleton />
    </div>
  );
}

interface CreateDeploymentDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  agents: Agent[];
  onSubmit: (agentId: string, replicas: number) => Promise<void>;
}

function CreateDeploymentDialog({ open, onOpenChange, agents, onSubmit }: CreateDeploymentDialogProps) {
  const [agentId, setAgentId] = useState("");
  const [replicas, setReplicas] = useState(1);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const fieldClassName =
    "w-full rounded-[14px] border border-[#2e3946] bg-[#0b1017] px-4 py-3 text-sm text-white focus:border-emerald-300/30 focus:outline-none";

  const availableAgents = agents.filter(a => a.status !== "deployed");

  useEffect(() => {
    if (open && availableAgents.length > 0 && !agentId) {
      setAgentId(availableAgents[0].id);
    }
  }, [open, availableAgents, agentId]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!agentId) return;

    setSubmitting(true);
    setError("");

    try {
      await onSubmit(agentId, replicas);
      onOpenChange(false);
      setAgentId("");
      setReplicas(1);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create deployment");
    } finally {
      setSubmitting(false);
    }
  };

  if (!open) return null;

  return (
    <DashboardDialog
      open={open}
      onOpenChange={onOpenChange}
      title="Create Deployment"
      description="Assign an agent to runtime capacity and create a new deployment record in the registry."
      footer={
        <>
          <button
            type="button"
            onClick={() => onOpenChange(false)}
            className="min-h-11 rounded-[12px] border border-[#2e3946] bg-[#0d131a] px-4 py-2 text-sm font-medium text-slate-200 transition hover:border-emerald-300/24"
          >
            Cancel
          </button>
          <button
            type="submit"
            form="create-deployment-form"
            disabled={submitting || !agentId || availableAgents.length === 0}
            className="min-h-11 rounded-[12px] bg-emerald-400 px-4 py-2 text-sm font-medium text-[#071018] transition hover:bg-emerald-300 disabled:opacity-50"
          >
            {submitting ? (
              <span className="flex items-center gap-2">
                <Loader2 className="h-4 w-4 motion-safe:animate-spin motion-reduce:animate-none" />
                Creating...
              </span>
            ) : (
              "Create Deployment"
            )}
          </button>
        </>
      }
    >
      <form id="create-deployment-form" onSubmit={handleSubmit} className="space-y-4">
          {error && (
            <div role="alert" className="rounded-[14px] border border-rose-400/20 bg-rose-400/10 p-3 text-sm text-rose-300">
              {error}
            </div>
          )}

          <div>
            <label htmlFor="deployment-agent" className="block text-sm font-medium text-slate-300 mb-2">
              Select Agent
            </label>
            <select
              id="deployment-agent"
              value={agentId}
              onChange={(e) => setAgentId(e.target.value)}
              className={fieldClassName}
              required
            >
              {availableAgents.length === 0 ? (
                <option value="">No available agents</option>
              ) : (
                availableAgents.map((agent) => (
                  <option key={agent.id} value={agent.id}>
                    {agent.name} ({agent.status})
                  </option>
                ))
              )}
            </select>
          </div>

          <div>
            <label htmlFor="deployment-create-replicas" className="block text-sm font-medium text-slate-300 mb-2">
              Replicas
            </label>
            <input
              id="deployment-create-replicas"
              type="number"
              min="1"
              max="10"
              value={replicas}
              onChange={(e) => setReplicas(Math.max(1, parseInt(e.target.value) || 1))}
              className={fieldClassName}
              required
            />
          </div>
      </form>
    </DashboardDialog>
  );
}

export function DeploymentsPageClient() {
  const [deployments, setDeployments] = useState<Deployment[]>([]);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");
  const [authRequired, setAuthRequired] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const searchInputRef = useRef<HTMLInputElement>(null);
  const [sortBy, setSortBy] = useState<"date"|"status"|"agent">("date");
  const [processingIds, setProcessingIds] = useState<Set<string>>(new Set());
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [isMac] = useState(false);
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [terminationTarget, setTerminationTarget] = useState<Deployment | null>(null);
  const [terminationError, setTerminationError] = useState("");
  const [actionNotice, setActionNotice] = useState("");

  const runningDeployments = deployments.filter(
    (d) => d.status === "running",
  ).length;

  const lastUpdated = deployments.length > 0
    ? deployments.reduce((latest, d) => {
        const dDate = d.started_at ? new Date(d.started_at).getTime() : 0;
        return dDate > latest ? dDate : latest;
      }, 0)
    : null;

  const filteredDeployments = deployments
    .filter(
      (deployment) =>
        deployment.id.toLowerCase().includes(searchQuery.toLowerCase()) ||
        deployment.agent_id.toLowerCase().includes(searchQuery.toLowerCase()) ||
        deployment.status.toLowerCase().includes(searchQuery.toLowerCase()),
    )
    .sort((a, b) => {
      if (sortBy === "date") {
        const aDate = a.started_at ? new Date(a.started_at).getTime() : 0;
        const bDate = b.started_at ? new Date(b.started_at).getTime() : 0;
        return bDate - aDate;
      }
      if (sortBy === "status") return a.status.localeCompare(b.status);
      return a.agent_id.localeCompare(b.agent_id);
    });

  async function loadDeployments() {
    try {
      const data = await readJson<unknown>("/api/dashboard/deployments");
      const deploymentsData = normalizeCollection<Deployment>(data, ["deployments", "items", "data"]).filter(
        (entry): entry is Deployment => Boolean(entry && typeof entry === "object" && "id" in entry),
      );

      setDeployments(deploymentsData);
      setAuthRequired(false);
      setError("");
    } catch (err) {
      if (err instanceof ApiRequestError && err.status === 401) {
        setDeployments([]);
        setAgents([]);
        setAuthRequired(true);
        setError("Sign in to view and operate deployments.");
        return;
      }

      setAuthRequired(false);
      setError(deploymentErrorMessage(err, "Failed to load deployments."));
    }
  }

  async function loadAgents() {
    try {
      const data = await readJson<unknown>("/api/dashboard/agents");
      const agentsData = normalizeCollection<Agent>(data, ["agents", "items", "data"]).filter(
        (entry): entry is Agent => Boolean(entry && typeof entry === "object" && "id" in entry),
      );

      setAgents(agentsData);
    } catch (err) {
      if (err instanceof ApiRequestError && err.status === 401) {
        setAgents([]);
        return;
      }

      console.error("Failed to load agents:", err);
    }
  }

  async function handleCreateDeployment(agentId: string, replicas: number) {
    setProcessingIds(prev => new Set(prev).add("create"));
    try {
      await writeJson<unknown>("/api/dashboard/deployments", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ agent_id: agentId, replicas }),
      });
      await loadDeployments();
    } catch (err) {
      if (err instanceof ApiRequestError && err.status === 401) {
        setAuthRequired(true);
      }
      throw new Error(deploymentErrorMessage(err, "Failed to create deployment."), { cause: err });
    } finally {
      setProcessingIds(prev => {
        const next = new Set(prev);
        next.delete("create");
        return next;
      });
    }
  }

  async function handleRestart(deploymentId: string) {
    setProcessingIds(prev => new Set(prev).add(deploymentId));
    try {
      await writeJson<unknown>(`/api/dashboard/deployments/${encodeURIComponent(deploymentId)}?action=restart`, {
        method: "POST",
      });
      await loadDeployments();
    } catch (err) {
      if (err instanceof ApiRequestError && err.status === 401) setAuthRequired(true);
      setError(deploymentErrorMessage(err, "Failed to restart deployment."));
    } finally {
      setProcessingIds(prev => {
        const next = new Set(prev);
        next.delete(deploymentId);
        return next;
      });
    }
  }

  async function handleStop(deploymentId: string) {
    setProcessingIds(prev => new Set(prev).add(deploymentId));
    try {
      await writeJson<unknown>(`/api/dashboard/deployments/${encodeURIComponent(deploymentId)}?action=scale`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ replicas: 0 }),
      });
      await loadDeployments();
    } catch (err) {
      if (err instanceof ApiRequestError && err.status === 401) setAuthRequired(true);
      setError(deploymentErrorMessage(err, "Failed to stop deployment."));
    } finally {
      setProcessingIds(prev => {
        const next = new Set(prev);
        next.delete(deploymentId);
        return next;
      });
    }
  }

  async function handleStart(deploymentId: string) {
    setProcessingIds(prev => new Set(prev).add(deploymentId));
    try {
      const deployment = deployments.find(d => d.id === deploymentId);
      await writeJson<unknown>(`/api/dashboard/deployments/${encodeURIComponent(deploymentId)}?action=scale`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ replicas: deployment?.replicas || 1 }),
      });
      await loadDeployments();
    } catch (err) {
      if (err instanceof ApiRequestError && err.status === 401) setAuthRequired(true);
      setError(deploymentErrorMessage(err, "Failed to start deployment."));
    } finally {
      setProcessingIds(prev => {
        const next = new Set(prev);
        next.delete(deploymentId);
        return next;
      });
    }
  }

  function requestTermination(deployment: Deployment) {
    if (processingIds.has(deployment.id)) return;
    setTerminationError("");
    setActionNotice("");
    setTerminationTarget(deployment);
  }

  async function handleTerminate() {
    if (!terminationTarget || processingIds.has(terminationTarget.id)) return;

    const deployment = terminationTarget;
    const deploymentId = deployment.id;

    setProcessingIds(prev => new Set(prev).add(deploymentId));
    setError("");
    setTerminationError("");
    try {
      await writeJson(`/api/dashboard/deployments/${encodeURIComponent(deploymentId)}`, {
        method: "DELETE",
      });
      await loadDeployments();
      setActionNotice(`Terminated deployment ${deploymentId}.`);
      setTerminationTarget(null);
    } catch (err) {
      if (err instanceof ApiRequestError && err.status === 401) setAuthRequired(true);
      const message = deploymentErrorMessage(err, "Failed to terminate deployment.");
      setTerminationError(message);
      setError(message);
    } finally {
      setProcessingIds(prev => {
        const next = new Set(prev);
        next.delete(deploymentId);
        return next;
      });
    }
  }

  function isProcessing(id: string) {
    return processingIds.has(id);
  }

  const handleCopyId = async (id: string) => {
    await navigator.clipboard.writeText(id);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  useEffect(() => {
    let cancelled = false;

    async function bootstrap() {
      try {
        await Promise.all([loadDeployments(), loadAgents()]);
      } catch {
        // Error already handled in loadDeployments
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void bootstrap();

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const interval = setInterval(() => {
      void loadDeployments();
    }, 30000);

    return () => clearInterval(interval);
  }, []);

  // Keyboard shortcut: Cmd/Ctrl + K to focus search, Escape to clear
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        searchInputRef.current?.focus();
      }
      if (e.key === 'Escape' && document.activeElement === searchInputRef.current) {
        setSearchQuery('');
        searchInputRef.current?.blur();
      }
    }

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, []);

  async function handleRefresh() {
    setRefreshing(true);
    await Promise.all([loadDeployments(), loadAgents()]);
    setRefreshing(false);
  }

  if (loading) {
    return (
      <div className="space-y-4">
        <LoadingState />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <CreateDeploymentDialog
        open={createDialogOpen}
        onOpenChange={setCreateDialogOpen}
        agents={agents}
        onSubmit={handleCreateDeployment}
      />

      <DashboardDialog
        open={Boolean(terminationTarget)}
        onOpenChange={(open) => {
          if (!open && terminationTarget && !processingIds.has(terminationTarget.id)) {
            setTerminationTarget(null);
            setTerminationError("");
          }
        }}
        title="Terminate deployment"
        description="End this deployment's runtime lifecycle permanently."
        footer={
          <>
            <button
              type="button"
              data-autofocus
              onClick={() => {
                setTerminationTarget(null);
                setTerminationError("");
              }}
              disabled={Boolean(terminationTarget && processingIds.has(terminationTarget.id))}
              className="min-h-11 w-full rounded-[12px] border border-[#2e3946] bg-[#0d131a] px-4 py-2 text-sm font-medium text-slate-200 transition hover:border-emerald-300/24 disabled:cursor-not-allowed disabled:opacity-50 sm:w-auto"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={() => void handleTerminate()}
              disabled={Boolean(terminationTarget && processingIds.has(terminationTarget.id))}
              className="inline-flex min-h-11 w-full items-center justify-center gap-2 rounded-[12px] border border-rose-400/30 bg-rose-400/15 px-4 py-2 text-sm font-semibold text-rose-200 transition hover:bg-rose-400/25 disabled:cursor-not-allowed disabled:opacity-50 sm:w-auto"
            >
              {terminationTarget && processingIds.has(terminationTarget.id) ? (
                <>
                  <Loader2 className="h-4 w-4 motion-safe:animate-spin motion-reduce:animate-none" aria-hidden="true" />
                  Terminating…
                </>
              ) : (
                "Terminate Deployment"
              )}
            </button>
          </>
        }
      >
        <div
          aria-busy={Boolean(terminationTarget && processingIds.has(terminationTarget.id))}
          className="space-y-4 text-start"
        >
          <div className="rounded-[12px] border border-[#2e3946] bg-[#0b1017] p-3">
            <p dir="ltr" className="break-all text-start text-sm font-semibold text-white">
              {terminationTarget?.id}
            </p>
            <p dir="ltr" className="mt-1 break-all text-start text-xs text-slate-400">
              Agent {terminationTarget?.agent_id} · {terminationTarget?.replicas} replicas
            </p>
          </div>
          <p className="text-sm leading-6 text-slate-300">
            Deployment history will remain available, but this deployment cannot be restarted after termination.
          </p>
          {terminationError ? (
            <div role="alert" className="rounded-[12px] border border-rose-400/20 bg-rose-400/10 p-3 text-sm text-rose-300">
              Deployment termination failed: {terminationError}
            </div>
          ) : null}
        </div>
      </DashboardDialog>

      {actionNotice ? (
        <div role="status" aria-live="polite" aria-atomic="true" className="rounded-[18px] border border-emerald-400/20 bg-emerald-400/10 p-4 text-sm text-emerald-200">
          {actionNotice}
        </div>
      ) : null}

      {error && !authRequired && (
        <div role="alert" className="flex items-center justify-between gap-4 rounded-[18px] border border-rose-400/20 bg-rose-400/10 p-4 text-sm text-rose-300">
          <div className="flex items-center gap-3">
            <span>{error}</span>
            <button
              onClick={async () => {
                setError("");
                await Promise.all([loadDeployments(), loadAgents()]);
              }}
              className="inline-flex items-center gap-1.5 rounded-lg border border-rose-400/30 bg-rose-400/20 px-3 py-1 text-xs font-medium text-rose-200 transition hover:bg-rose-400/30"
            >
              <RefreshCcw className="h-3.5 w-3.5" />
              Retry
            </button>
          </div>
          <button
            type="button"
            onClick={() => setError("")}
            aria-label="Dismiss deployment error"
            className="text-rose-300 hover:text-white"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      )}

      <LiveKpiGrid>
        <LiveStatCard
          label="Deployments"
          value={String(deployments.length)}
          detail="Total runtime records returned by the deployment registry."
          status={asDashboardStatus(deployments.length > 0 ? "running" : "idle")}
        />
        <LiveStatCard
          label="Running"
          value={String(runningDeployments)}
          detail="Deployments currently reporting live runtime state."
          status={asDashboardStatus(runningDeployments > 0 ? "running" : "idle")}
        />
        <LiveStatCard
          label="Last Updated"
          value={lastUpdated ? formatRelativeTime(new Date(lastUpdated).toISOString()) : "N/A"}
          detail="Freshest deployment activity visible in the current registry."
          status={asDashboardStatus(lastUpdated ? "running" : "idle")}
        />
        <LiveStatCard
          label="Search Scope"
          value={searchQuery ? `${filteredDeployments.length} visible` : "registry"}
          detail="Search matches deployment id, agent id, and status."
          status={asDashboardStatus(searchQuery ? "active" : "idle")}
        />
      </LiveKpiGrid>

      <FilterBar
        searchValue={searchQuery}
        onSearchChange={setSearchQuery}
        searchInputRef={searchInputRef}
        searchPlaceholder={
          isMac
            ? "Search deployments by ID, agent ID, or status... (⌘K)"
            : "Search deployments by ID, agent ID, or status... (Ctrl+K)"
        }
        onReset={() => setSearchQuery("")}
        trailing={
          <div className="flex flex-wrap items-center gap-2">
            <DeploymentSortSelect value={sortBy} onChange={setSortBy} />
            <button
              onClick={handleRefresh}
              disabled={refreshing}
              className="inline-flex items-center gap-2 rounded-[14px] border border-[#2f3c49] bg-[#10161d] px-3.5 py-2 text-sm font-medium text-white transition hover:border-emerald-300/30 disabled:opacity-50"
            >
              {refreshing ? (
                <Loader2 className="h-4 w-4 motion-safe:animate-spin motion-reduce:animate-none" />
              ) : (
                <RefreshCcw className="h-4 w-4" />
              )}
              {refreshing ? "Refreshing..." : "Refresh"}
            </button>
            <button
              onClick={() => setCreateDialogOpen(true)}
              className="inline-flex items-center gap-2 rounded-[14px] border border-emerald-400/20 bg-emerald-400/12 px-3.5 py-2 text-sm font-medium text-emerald-300 transition hover:bg-emerald-400/20"
            >
              <Plus className="h-4 w-4" />
              New Deployment
            </button>
          </div>
        }
      />

      {authRequired ? (
        <LiveAuthRequired
          title="Operator session required"
          message="Sign in again to load the real deployment inventory, rollout actions, and runtime posture for this tenant."
        />
      ) : filteredDeployments.length === 0 ? (
        <DashboardEmptyState
          title="No deployments found"
          message={
            searchQuery
              ? "Try adjusting your search query."
              : "Deployments will appear here when agents are deployed."
          }
          icon={<Server className="h-8 w-8" />}
          cta={
            !searchQuery ? (
              <button
                onClick={() => setCreateDialogOpen(true)}
                className="inline-flex items-center gap-2 rounded-[12px] bg-emerald-400 px-4 py-2 text-sm font-medium text-[#071018] hover:bg-emerald-300"
              >
                <Plus className="h-4 w-4" />
                Create Deployment
              </button>
            ) : undefined
          }
        />
      ) : (
        <LivePanel title="Deployment registry" meta={`${filteredDeployments.length} visible`}>
          <div className="space-y-3">
            {filteredDeployments.map((deployment) => (
              <DeploymentCard
                key={deployment.id}
                deployment={deployment}
                onRestart={handleRestart}
                onStop={handleStop}
                onStart={handleStart}
                onTerminate={requestTermination}
                isProcessing={isProcessing}
                copiedId={copiedId}
                onCopyId={handleCopyId}
              />
            ))}
          </div>
        </LivePanel>
      )}
    </div>
  );
}
