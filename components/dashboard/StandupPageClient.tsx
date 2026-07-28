"use client";

import { useEffect, useState } from "react";

import { readJson } from "@/components/app/http";
import { getDashboardRequestAccessFailure } from "@/components/dashboard/dashboardRequestAccess";
import {
  LiveAuthRequired,
  LiveEmptyState,
  LiveErrorState,
  LiveForbidden,
  LiveKpiGrid,
  LiveLoading,
  LivePanel,
  LiveStatCard,
  formatRelativeTime,
} from "@/components/dashboard/livePrimitives";
import { StatusBadge } from "@/components/dashboard/StatusBadge";

type DashboardStatus = "idle" | "running" | "success" | "warning" | "error";
type AggregateSourceStatus =
  | "ok"
  | "partial"
  | "unauthenticated"
  | "forbidden"
  | "error";

type BriefItem = {
  id: string;
  title: string;
  detail: string;
  status: DashboardStatus;
  createdAt: string | null;
  source: string;
};

type StandupPayload = {
  generatedAt: string;
  focus: string;
  metrics: {
    openAlerts: number | null;
    pendingApprovals: number | null;
    failedRuns: number | null;
    queuedAutonomy: number | null;
  };
  sources: {
    alerts: AggregateSourceStatus;
    approvals: AggregateSourceStatus;
    runs: AggregateSourceStatus;
    webhooks: AggregateSourceStatus;
    autonomy: AggregateSourceStatus;
  };
  blockers: BriefItem[];
  watchlist: BriefItem[];
  completions: BriefItem[];
  partials: string[];
};

function BriefList({
  title,
  items,
  emptyTitle,
  emptyMessage,
  coverageComplete,
}: {
  title: string;
  items: BriefItem[];
  emptyTitle: string;
  emptyMessage: string;
  coverageComplete: boolean;
}) {
  return (
    <LivePanel title={title} meta={`${items.length} items`}>
      {items.length === 0 ? (
        <LiveEmptyState
          title={coverageComplete ? emptyTitle : `${title} coverage is incomplete`}
          message={
            coverageComplete
              ? emptyMessage
              : "One or more source feeds are unavailable, so this empty list is not confirmation of a successful zero."
          }
        />
      ) : (
        <div className="space-y-3">
          {items.map((item) => (
            <div
              key={item.id}
              className="rounded-2xl border border-white/10 bg-white/[0.03] p-4"
            >
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="text-sm font-medium text-white">{item.title}</p>
                  <p className="mt-1 text-sm text-slate-400">{item.detail}</p>
                </div>
                <StatusBadge status={item.status} label={item.source} />
              </div>
              <p className="mt-3 text-xs text-slate-500">
                {item.createdAt
                  ? `Observed ${formatRelativeTime(item.createdAt)}`
                  : "No observation timestamp"}
              </p>
            </div>
          ))}
        </div>
      )}
    </LivePanel>
  );
}

export function StandupPageClient() {
  const [loading, setLoading] = useState(true);
  const [authRequired, setAuthRequired] = useState(false);
  const [permissionDenied, setPermissionDenied] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [payload, setPayload] = useState<StandupPayload | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setLoading(true);
      setAuthRequired(false);
      setPermissionDenied(false);
      setError(null);

      try {
        const response = await readJson<StandupPayload>("/api/dashboard/standup");
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
            setError(loadError instanceof Error ? loadError.message : "Failed to load standup");
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

  if (loading) return <LiveLoading title="Standup" />;
  if (authRequired) {
    return (
      <LiveAuthRequired
        title="Operator session required"
        message="Sign in to generate a derived standup from live operator signals."
      />
    );
  }
  if (permissionDenied) {
    return (
      <LiveForbidden
        title="Standup permission required"
        message="Your account cannot inspect the workspace signals used for this standup. Derived brief actions are unavailable."
      />
    );
  }
  if (error) return <LiveErrorState title="Standup unavailable" message={error} />;
  if (!payload) {
    return (
      <LiveErrorState
        title="Standup unavailable"
        message="No standup payload was returned by the dashboard proxy."
      />
    );
  }

  return (
    <div className="space-y-4">
      <LiveKpiGrid>
        <LiveStatCard
          label="Open alerts"
          value={
            payload.metrics.openAlerts === null ? "Unknown" : String(payload.metrics.openAlerts)
          }
          detail="Monitoring blockers sampled into this brief."
          status={
            payload.metrics.openAlerts === null
              ? "idle"
              : payload.metrics.openAlerts > 0
                ? "error"
                : "success"
          }
        />
        <LiveStatCard
          label="Pending approvals"
          value={
            payload.metrics.pendingApprovals === null
              ? "Unknown"
              : String(payload.metrics.pendingApprovals)
          }
          detail="Approval decisions still waiting on operator review."
          status={
            payload.metrics.pendingApprovals === null
              ? "idle"
              : payload.metrics.pendingApprovals > 0
                ? "warning"
                : "success"
          }
        />
        <LiveStatCard
          label="Failed runs"
          value={
            payload.metrics.failedRuns === null ? "Unknown" : String(payload.metrics.failedRuns)
          }
          detail="Recent execution failures currently flagged in the watchlist."
          status={
            payload.metrics.failedRuns === null
              ? "idle"
              : payload.metrics.failedRuns > 0
                ? "error"
                : "success"
          }
        />
        <LiveStatCard
          label="Autonomy backlog"
          value={
            payload.metrics.queuedAutonomy === null
              ? "partial"
              : String(payload.metrics.queuedAutonomy)
          }
          detail="Local backlog only when the shell is running on the operator host."
          status={
            payload.metrics.queuedAutonomy && payload.metrics.queuedAutonomy > 0
              ? "warning"
              : payload.metrics.queuedAutonomy === null
                ? "idle"
                : "success"
          }
        />
      </LiveKpiGrid>

      <LivePanel
        title="Derived operator brief"
        meta={`updated ${formatRelativeTime(payload.generatedAt)}`}
      >
        <div className="rounded-3xl border border-white/10 bg-white/[0.03] p-5">
          <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-slate-500">
            Focus
          </p>
          <p className="mt-3 font-[family:var(--font-site-display)] text-[1.5rem] tracking-[-0.05em] text-white">
            {payload.focus}
          </p>
          <p className="mt-3 text-sm leading-6 text-slate-300">
            This brief is derived from the live alerts, approvals, runs, webhooks, and optional local autonomy feeds. It is intentionally read-only and does not pretend there is a persisted standup workflow behind it.
          </p>
        </div>
      </LivePanel>

      <div className="grid gap-4 xl:grid-cols-3">
        <BriefList
          title="Blockers"
          items={payload.blockers}
          emptyTitle="No blockers detected"
          emptyMessage="The current brief did not surface any blocking alerts, approvals, or webhook failures."
          coverageComplete={
            payload.sources.alerts === "ok" &&
            payload.sources.approvals === "ok" &&
            payload.sources.webhooks === "ok"
          }
        />
        <BriefList
          title="Watchlist"
          items={payload.watchlist}
          emptyTitle="Watchlist is clear"
          emptyMessage="No live or failed execution items were sampled into the watchlist."
          coverageComplete={payload.sources.runs === "ok"}
        />
        <BriefList
          title="Recent completions"
          items={payload.completions}
          emptyTitle="No recent completions"
          emptyMessage="Completed runs will show up here once recent execution history is available."
          coverageComplete={payload.sources.runs === "ok"}
        />
      </div>

      <LivePanel title="Coverage notes" meta={`${payload.partials.length} notes`}>
        {payload.partials.length === 0 ? (
          <LiveEmptyState
            title="Full brief coverage"
            message="All standup source feeds returned data for this operator session."
          />
        ) : (
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
        )}
      </LivePanel>
    </div>
  );
}
