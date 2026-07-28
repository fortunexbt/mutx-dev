"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { GitBranchPlus, RefreshCw, ShieldCheck, Workflow } from "lucide-react";

import { readJson, writeJson } from "@/components/app/http";
import {
  dashboardRequestErrorMessage,
  getDashboardRequestAccessFailure,
} from "@/components/dashboard/dashboardRequestAccess";
import {
  LiveAuthRequired,
  LiveEmptyState,
  LiveErrorState,
  LiveForbidden,
  LiveKpiGrid,
  LiveLoading,
  LiveMiniStat,
  LiveMiniStatGrid,
  LivePanel,
  LiveStatCard,
  formatRelativeTime,
} from "@/components/dashboard/livePrimitives";
import { StatusBadge } from "@/components/dashboard/StatusBadge";

type OrchestrationPayload = {
  generatedAt: string;
  sourceStatus: {
    approvals: OrchestrationSourceStatus;
    runs: OrchestrationSourceStatus;
    sessions: OrchestrationSourceStatus;
    blueprints: OrchestrationSourceStatus;
    autonomy: OrchestrationSourceStatus;
  };
  summary: {
    pendingApprovals: number | null;
    recoveryWatch: number | null;
    blueprints: number | null;
    queuedAutonomy: number | null;
    runningAutonomy: number | null;
  };
  approvals: Array<{
    id: string;
    ownerId: string | null;
    reviewerId: string | null;
    canResolve: boolean;
    agentId: string | null;
    actionType: string;
    requester: string;
    status: string;
    createdAt: string | null;
  }>;
  recoveries: Array<{
    id: string;
    kind: "run" | "session";
    title: string;
    detail: string;
    status: string;
    createdAt: string | null;
    href: string;
  }>;
  blueprints: Array<{
    id: string;
    name: string;
    summary: string;
    recommendedAgents: string;
    roles: number;
    tags: string[];
  }>;
  autonomy: {
    queued: number;
    running: number;
    parked: number;
    completed: number;
    activeRunners: number;
  } | null;
  partials: string[];
};

type OrchestrationSourceStatus = "ok" | "partial" | "auth_error" | "error";

type ApprovalDecision = "approve" | "reject";

type ApprovalActionState = {
  pending: ApprovalDecision | null;
  failed: ApprovalDecision | null;
  error: string | null;
};

type QueueNotice = {
  status: "success" | "error";
  message: string;
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function stringValue(value: unknown, fallback: string) {
  return typeof value === "string" && value.trim().length > 0 ? value : fallback;
}

function nullableString(value: unknown) {
  return typeof value === "string" && value.trim().length > 0 ? value : null;
}

function countValue(value: unknown, fallback = 0) {
  return typeof value === "number" && Number.isFinite(value)
    ? Math.max(0, Math.round(value))
    : fallback;
}

function nullableCount(value: unknown, fallback: number | null = null) {
  return typeof value === "number" && Number.isFinite(value)
    ? Math.max(0, Math.round(value))
    : fallback;
}

function sourceStatusValue(value: unknown): OrchestrationSourceStatus {
  return value === "ok" || value === "partial" || value === "auth_error" || value === "error"
    ? value
    : "error";
}

function recordList(value: unknown) {
  return Array.isArray(value) ? value.filter(isRecord) : [];
}

function safeDashboardHref(value: unknown, fallback: string) {
  if (typeof value !== "string" || !value.startsWith("/")) return fallback;

  try {
    const parsed = new URL(value, "https://mutx.local");
    if (
      parsed.origin === "https://mutx.local" &&
      (parsed.pathname === "/dashboard" || parsed.pathname.startsWith("/dashboard/"))
    ) {
      return `${parsed.pathname}${parsed.search}${parsed.hash}`;
    }
  } catch {
    return fallback;
  }

  return fallback;
}

function normalizeOrchestrationPayload(value: unknown): OrchestrationPayload {
  const payload = isRecord(value) ? value : {};

  const approvalRecords = recordList(payload.approvals);
  const approvals = approvalRecords.flatMap((approval) => {
    const id = nullableString(approval.id);
    if (!id) return [];
    return [{
      id,
      ownerId: nullableString(approval.ownerId),
      reviewerId: nullableString(approval.reviewerId),
      canResolve: approval.canResolve === true,
      agentId: nullableString(approval.agentId),
      actionType: stringValue(approval.actionType, "Approval request"),
      requester: stringValue(approval.requester, "Unknown requester"),
      status: stringValue(approval.status, "PENDING"),
      createdAt: nullableString(approval.createdAt),
    }];
  });

  const recoveryRecords = recordList(payload.recoveries);
  const recoveries = recoveryRecords.flatMap((recovery) => {
    const id = nullableString(recovery.id);
    if (!id) return [];
    const kind = recovery.kind === "session" ? ("session" as const) : ("run" as const);

    return [{
      id,
      kind,
      title: stringValue(recovery.title, "Recovery item"),
      detail: stringValue(recovery.detail, "No recovery detail was returned."),
      status: stringValue(recovery.status, "unknown"),
      createdAt: nullableString(recovery.createdAt),
      href: safeDashboardHref(
        recovery.href,
        kind === "session" ? "/dashboard/sessions" : "/dashboard/runs",
      ),
    }];
  });

  const blueprintRecords = recordList(payload.blueprints);
  const blueprints = blueprintRecords.flatMap((blueprint) => {
    const id = nullableString(blueprint.id);
    if (!id) return [];
    return [{
      id,
      name: stringValue(blueprint.name, "Blueprint"),
      summary: stringValue(blueprint.summary, "No blueprint summary was returned."),
      recommendedAgents: stringValue(blueprint.recommendedAgents, "not specified"),
      roles: countValue(blueprint.roles),
      tags: Array.isArray(blueprint.tags)
        ? blueprint.tags.filter(
            (tag): tag is string => typeof tag === "string" && tag.trim().length > 0,
          )
        : [],
    }];
  });

  const autonomyRecord = isRecord(payload.autonomy) ? payload.autonomy : null;
  const autonomy = autonomyRecord
    ? {
        queued: countValue(autonomyRecord.queued),
        running: countValue(autonomyRecord.running),
        parked: countValue(autonomyRecord.parked),
        completed: countValue(autonomyRecord.completed),
        activeRunners: countValue(autonomyRecord.activeRunners),
      }
    : null;

  const summary = isRecord(payload.summary) ? payload.summary : {};
  const sourceStatus = isRecord(payload.sourceStatus) ? payload.sourceStatus : {};
  const partials = Array.isArray(payload.partials)
    ? payload.partials.filter(
        (note): note is string => typeof note === "string" && note.trim().length > 0,
      )
    : [];
  const responseIsIncomplete =
    !isRecord(value) ||
    !isRecord(payload.summary) ||
    !isRecord(payload.sourceStatus) ||
    !Array.isArray(payload.approvals) ||
    !Array.isArray(payload.recoveries) ||
    !Array.isArray(payload.blueprints) ||
    !Array.isArray(payload.partials);

  if (responseIsIncomplete) {
    partials.push(
      "The orchestration proxy returned an incomplete payload; unavailable collections are shown as empty.",
    );
  }
  if (approvalRecords.length > approvals.length) {
    partials.push("Approval records without authoritative identifiers were omitted.");
  }
  if (recoveryRecords.length > recoveries.length) {
    partials.push("Recovery records without authoritative identifiers were omitted.");
  }
  if (blueprintRecords.length > blueprints.length) {
    partials.push("Blueprint records without authoritative identifiers were omitted.");
  }

  return {
    generatedAt: stringValue(payload.generatedAt, new Date().toISOString()),
    sourceStatus: {
      approvals: sourceStatusValue(sourceStatus.approvals),
      runs: sourceStatusValue(sourceStatus.runs),
      sessions: sourceStatusValue(sourceStatus.sessions),
      blueprints: sourceStatusValue(sourceStatus.blueprints),
      autonomy: sourceStatusValue(sourceStatus.autonomy),
    },
    summary: {
      pendingApprovals: nullableCount(summary.pendingApprovals),
      recoveryWatch: nullableCount(summary.recoveryWatch),
      blueprints: nullableCount(summary.blueprints),
      queuedAutonomy: nullableCount(summary.queuedAutonomy, autonomy?.queued ?? null),
      runningAutonomy: nullableCount(summary.runningAutonomy, autonomy?.running ?? null),
    },
    approvals,
    recoveries,
    blueprints,
    autonomy,
    partials: [...new Set(partials)],
  };
}

function statusForRecovery(status: string) {
  const normalized = status.toLowerCase();
  if (normalized.includes("fail") || normalized.includes("error")) return "error" as const;
  if (normalized.includes("running") || normalized.includes("pending")) return "running" as const;
  if (normalized.includes("inactive")) return "warning" as const;
  return "idle" as const;
}

async function fetchOrchestration() {
  const response = await readJson<unknown>("/api/dashboard/orchestration");
  return normalizeOrchestrationPayload(response);
}

function actionErrorMessage(error: unknown, fallback: string) {
  return dashboardRequestErrorMessage(error, fallback);
}

export function OrchestrationPageClient() {
  const [loading, setLoading] = useState(true);
  const [authRequired, setAuthRequired] = useState(false);
  const [permissionDenied, setPermissionDenied] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [payload, setPayload] = useState<OrchestrationPayload | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [queueNotice, setQueueNotice] = useState<QueueNotice | null>(null);
  const [approvalActions, setApprovalActions] = useState<
    Record<string, ApprovalActionState>
  >({});

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setLoading(true);
      setAuthRequired(false);
      setPermissionDenied(false);
      setError(null);

      try {
        const response = await fetchOrchestration();
        if (!cancelled) {
          setPayload(response);
          setLoading(false);
        }
      } catch (loadError) {
        if (!cancelled) {
          const accessFailure = getDashboardRequestAccessFailure(loadError);
          if (accessFailure === "authentication") {
            setAuthRequired(true);
          } else if (accessFailure === "permission") {
            setPermissionDenied(true);
          } else {
            setError(
              loadError instanceof Error ? loadError.message : "Failed to load orchestration",
            );
          }
          setLoading(false);
        }
      }
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  async function refreshQueue(
    successMessage = "Approval queue refreshed.",
    failureMessage = "Approval queue refresh failed",
    clearNotice = true,
  ) {
    setRefreshing(true);
    if (clearNotice) {
      setQueueNotice(null);
    }

    try {
      setPayload(await fetchOrchestration());
      setQueueNotice({ status: "success", message: successMessage });
    } catch (refreshError) {
      const accessFailure = getDashboardRequestAccessFailure(refreshError);
      if (accessFailure === "authentication") {
        setAuthRequired(true);
      } else if (accessFailure === "permission") {
        setPermissionDenied(true);
      } else {
        setQueueNotice({
          status: "error",
          message: `${failureMessage}: ${actionErrorMessage(refreshError, "request failed")}`,
        });
      }
    } finally {
      setRefreshing(false);
    }
  }

  async function resolveApproval(approvalId: string, decision: ApprovalDecision) {
    setQueueNotice(null);
    setApprovalActions((current) => ({
      ...current,
      [approvalId]: { pending: decision, failed: null, error: null },
    }));

    try {
      await writeJson<unknown>(
        `/api/dashboard/approvals/${encodeURIComponent(approvalId)}/${decision}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({}),
        },
      );
    } catch (decisionError) {
      const accessFailure = getDashboardRequestAccessFailure(decisionError);
      if (accessFailure === "authentication") {
        setAuthRequired(true);
        return;
      }
      if (accessFailure === "permission") {
        setApprovalActions((current) => ({
          ...current,
          [approvalId]: {
            pending: null,
            failed: decision,
            error: "You are no longer eligible to resolve this approval request",
          },
        }));
        return;
      }
      setApprovalActions((current) => ({
        ...current,
        [approvalId]: {
          pending: null,
          failed: decision,
          error: actionErrorMessage(
            decisionError,
            `Failed to ${decision} approval request`,
          ),
        },
      }));
      return;
    }

    setPayload((current) =>
      current
        ? {
            ...current,
            summary: {
              ...current.summary,
              pendingApprovals:
                current.summary.pendingApprovals === null
                  ? null
                  : Math.max(0, current.summary.pendingApprovals - 1),
            },
            approvals: current.approvals.filter((approval) => approval.id !== approvalId),
          }
        : current,
    );
    setApprovalActions((current) => {
      const next = { ...current };
      delete next[approvalId];
      return next;
    });

    const pastTense = decision === "approve" ? "approved" : "rejected";
    setQueueNotice({
      status: "success",
      message: `Approval ${pastTense}. Refreshing the queue…`,
    });
    await refreshQueue(
      `Approval ${pastTense} and queue refreshed.`,
      `Approval ${pastTense}, but queue refresh failed`,
      false,
    );
  }

  if (loading) return <LiveLoading title="Orchestration" />;
  if (authRequired) {
    return (
      <LiveAuthRequired
        title="Operator session required"
        message="Sign in to inspect approvals, recovery watchlists, and blueprint posture."
      />
    );
  }
  if (permissionDenied) {
    return <LiveForbidden title="Orchestration permission required" message="Your account cannot resolve approvals or refresh orchestration state. Approval actions are unavailable." />;
  }
  if (error) return <LiveErrorState title="Orchestration unavailable" message={error} />;
  if (!payload) {
    return (
      <LiveErrorState
        title="Orchestration unavailable"
        message="No orchestration payload was returned by the dashboard proxy."
      />
    );
  }

  return (
    <div className="space-y-4">
      <LiveKpiGrid>
        <LiveStatCard
          label="Approval queue"
          value={
            payload.summary.pendingApprovals === null
              ? "Unknown"
              : String(payload.summary.pendingApprovals)
          }
          detail="Pending operator approvals currently visible in the control plane."
          status={
            payload.summary.pendingApprovals === null
              ? "warning"
              : payload.summary.pendingApprovals > 0
                ? "warning"
                : "success"
          }
        />
        <LiveStatCard
          label="Recovery watch"
          value={
            payload.summary.recoveryWatch === null
              ? "Unknown"
              : String(payload.summary.recoveryWatch)
          }
          detail="Failed runs and inactive sessions sampled into the read-only recovery lane."
          status={
            payload.summary.recoveryWatch === null
              ? "warning"
              : payload.summary.recoveryWatch > 0
                ? "error"
                : "success"
          }
        />
        <LiveStatCard
          label="Blueprints"
          value={
            payload.summary.blueprints === null
              ? "Unknown"
              : String(payload.summary.blueprints)
          }
          detail="Curated swarm blueprints currently available to operators."
          status={
            payload.summary.blueprints === null
              ? "warning"
              : payload.summary.blueprints > 0
                ? "success"
                : "idle"
          }
        />
        <LiveStatCard
          label="Autonomy backlog"
          value={payload.summary.queuedAutonomy === null ? "partial" : String(payload.summary.queuedAutonomy)}
          detail="Local autonomy queue when the shell is running on the operator host."
          status={
            payload.summary.queuedAutonomy && payload.summary.queuedAutonomy > 0
              ? "warning"
              : payload.summary.queuedAutonomy === null
                ? "idle"
                : "success"
          }
        />
      </LiveKpiGrid>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.15fr)_minmax(340px,0.85fr)]">
        <LivePanel
          title="Approval queue"
          meta={`${payload.summary.pendingApprovals ?? "unknown"} pending · ${payload.approvals.length} shown`}
        >
          <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
            <p className="text-xs text-slate-500">
              Approve or reject requests, then refresh to reconcile the visible queue.
            </p>
            <button
              type="button"
              onClick={() => void refreshQueue()}
              disabled={refreshing}
              aria-busy={refreshing}
              className="inline-flex items-center gap-2 rounded-lg border border-white/15 px-3 py-2 text-xs font-medium text-slate-200 transition hover:border-cyan-400/40 hover:text-white disabled:cursor-wait disabled:opacity-60"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${refreshing ? "motion-safe:animate-spin motion-reduce:animate-none" : ""}`} />
              {refreshing ? "Refreshing…" : "Refresh queue"}
            </button>
          </div>

          {queueNotice ? (
            <div
              role={queueNotice.status === "error" ? "alert" : "status"}
              className={`mb-3 rounded-xl border px-4 py-3 text-sm ${
                queueNotice.status === "error"
                  ? "border-rose-400/25 bg-rose-400/10 text-rose-100"
                  : "border-emerald-400/25 bg-emerald-400/10 text-emerald-100"
              }`}
            >
              <div className="flex flex-wrap items-center justify-between gap-3">
                <span>{queueNotice.message}</span>
                {queueNotice.status === "error" ? (
                  <button
                    type="button"
                    onClick={() => void refreshQueue()}
                    disabled={refreshing}
                    className="rounded-lg border border-rose-200/30 px-2.5 py-1.5 text-xs font-semibold text-rose-50 transition hover:border-rose-100/60 disabled:cursor-wait disabled:opacity-60"
                  >
                    Retry refresh
                  </button>
                ) : null}
              </div>
            </div>
          ) : null}

          {payload.approvals.length === 0 ? (
            <LiveEmptyState
              title={
                payload.sourceStatus.approvals === "ok"
                  ? "Approval queue is clear"
                  : "Approval queue coverage is incomplete"
              }
              message={
                payload.sourceStatus.approvals === "ok"
                  ? "No visible pending approval requests are currently blocking operator work."
                  : "The approval feed is unavailable or malformed, so this empty queue is not a verified zero."
              }
            />
          ) : (
            <div className="space-y-3">
              {payload.approvals.map((approval) => {
                const actionState = approvalActions[approval.id];
                const isPending = Boolean(actionState?.pending);

                return (
                  <div
                    key={approval.id}
                    className="rounded-2xl border border-white/10 bg-white/[0.03] p-4"
                  >
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="text-sm font-medium text-white">{approval.actionType}</p>
                        <p className="mt-1 text-sm text-slate-400">
                          {approval.requester}
                          {approval.agentId ? ` · ${approval.agentId}` : ""}
                        </p>
                      </div>
                      <StatusBadge status="warning" label={approval.status} />
                    </div>
                    <p className="mt-3 text-xs text-slate-500">
                      {approval.createdAt
                        ? `Opened ${formatRelativeTime(approval.createdAt)}`
                        : "No approval timestamp"}
                    </p>

                    {actionState?.error ? (
                      <p className="mt-3 text-sm text-rose-200" role="alert">
                        {actionState.error}. Choose retry when the control plane is ready.
                      </p>
                    ) : null}

                    <div className="mt-4 flex flex-wrap gap-2">
                      {approval.canResolve ? (
                        <>
                          <button
                            type="button"
                            onClick={() => void resolveApproval(approval.id, "approve")}
                            disabled={isPending || refreshing}
                            aria-busy={actionState?.pending === "approve"}
                            className="rounded-lg border border-emerald-400/30 bg-emerald-400/10 px-3 py-2 text-xs font-semibold text-emerald-100 transition hover:border-emerald-300/60 hover:bg-emerald-400/15 disabled:cursor-wait disabled:opacity-60"
                          >
                            {actionState?.pending === "approve"
                              ? "Approving…"
                              : actionState?.failed === "approve"
                                ? "Retry approve"
                                : "Approve"}
                          </button>
                          <button
                            type="button"
                            onClick={() => void resolveApproval(approval.id, "reject")}
                            disabled={isPending || refreshing}
                            aria-busy={actionState?.pending === "reject"}
                            className="rounded-lg border border-rose-400/30 bg-rose-400/10 px-3 py-2 text-xs font-semibold text-rose-100 transition hover:border-rose-300/60 hover:bg-rose-400/15 disabled:cursor-wait disabled:opacity-60"
                          >
                            {actionState?.pending === "reject"
                              ? "Rejecting…"
                              : actionState?.failed === "reject"
                                ? "Retry reject"
                                : "Reject"}
                          </button>
                        </>
                      ) : null}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </LivePanel>

        <div className="space-y-4">
          <LivePanel title="Workflow board" meta="read-only">
            <LiveMiniStatGrid columns={2}>
              <LiveMiniStat
                label="Autonomy queued"
                value={
                  payload.autonomy ? String(payload.autonomy.queued) : "not available"
                }
                detail="Local queue items waiting for pickup"
                icon={Workflow}
              />
              <LiveMiniStat
                label="Autonomy running"
                value={
                  payload.autonomy ? String(payload.autonomy.running) : "not available"
                }
                detail="Local workers currently executing"
                icon={ShieldCheck}
              />
              <LiveMiniStat
                label="Active runners"
                value={
                  payload.autonomy ? String(payload.autonomy.activeRunners) : "not available"
                }
                detail="Current local worker count"
              />
              <LiveMiniStat
                label="Blueprint roles"
                value={String(payload.blueprints.reduce((sum, blueprint) => sum + blueprint.roles, 0))}
                detail="Role count across the visible blueprint catalog"
                icon={GitBranchPlus}
              />
            </LiveMiniStatGrid>
          </LivePanel>

          <LivePanel title="Coverage notes" meta={`${payload.partials.length} notes`}>
            <div className="space-y-3">
              {payload.partials.map((note) => (
                <div
                  key={note}
                  className="rounded-2xl border border-white/10 bg-white/[0.03] px-4 py-3"
                >
                  <p className="text-sm leading-6 text-slate-300">{note}</p>
                </div>
              ))}
            </div>
          </LivePanel>
        </div>
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <LivePanel title="Recovery watchlist" meta={`${payload.recoveries.length} items`}>
          {payload.recoveries.length === 0 ? (
            <LiveEmptyState
              title={
                payload.sourceStatus.runs === "ok" && payload.sourceStatus.sessions === "ok"
                  ? "Recovery lane is clear"
                  : "Recovery coverage is incomplete"
              }
              message={
                payload.sourceStatus.runs === "ok" && payload.sourceStatus.sessions === "ok"
                  ? "No failed runs or inactive sessions were sampled into the watchlist."
                  : "Run or session recovery data is unavailable or malformed, so this empty lane is not a verified zero."
              }
            />
          ) : (
            <div className="space-y-3">
              {payload.recoveries.map((item) => (
                <div
                  key={item.id}
                  className="rounded-2xl border border-white/10 bg-white/[0.03] p-4"
                >
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-white">{item.title}</p>
                      <p className="mt-1 text-sm text-slate-400">{item.detail}</p>
                    </div>
                    <StatusBadge
                      status={statusForRecovery(item.status)}
                      label={item.kind}
                    />
                  </div>
                  <p className="mt-3 text-xs text-slate-500">
                    {item.createdAt
                      ? `Observed ${formatRelativeTime(item.createdAt)}`
                      : "No observation timestamp"}
                  </p>
                  <Link
                    href={item.href}
                    className="mt-3 inline-flex text-xs font-semibold text-cyan-300 transition hover:text-cyan-200"
                  >
                    Open {item.kind} destination
                  </Link>
                </div>
              ))}
            </div>
          )}
        </LivePanel>

        <LivePanel title="Blueprint catalog" meta={`${payload.blueprints.length} blueprints`}>
          {payload.blueprints.length === 0 ? (
            <LiveEmptyState
              title={
                payload.sourceStatus.blueprints === "ok"
                  ? "No blueprints available"
                  : "Blueprint coverage is incomplete"
              }
              message={
                payload.sourceStatus.blueprints === "ok"
                  ? "Swarm blueprints will appear here once orchestration presets are published."
                  : "The blueprint feed is unavailable or malformed, so this empty catalog is not a verified zero."
              }
            />
          ) : (
            <div className="space-y-3">
              {payload.blueprints.map((blueprint) => (
                <div
                  key={blueprint.id}
                  className="rounded-2xl border border-white/10 bg-white/[0.03] p-4"
                >
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-white">{blueprint.name}</p>
                      <p className="mt-1 text-sm text-slate-400">{blueprint.summary}</p>
                    </div>
                    <StatusBadge status="success" label={`${blueprint.recommendedAgents} agents`} />
                  </div>
                  <p className="mt-3 text-xs text-slate-500">
                    {blueprint.roles} roles
                    {blueprint.tags.length > 0 ? ` · ${blueprint.tags.join(", ")}` : ""}
                  </p>
                </div>
              ))}
            </div>
          )}
        </LivePanel>
      </div>
    </div>
  );
}
