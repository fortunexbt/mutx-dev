"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { readJson } from "@/components/app/http";
import {
  LiveAuthRequired,
  LiveEmptyState,
  LiveErrorState,
  LiveForbidden,
  LiveKpiGrid,
  LiveLoading,
  LivePanel,
  LiveStatCard,
  QueueDepthBar,
  asDashboardStatus,
  formatRelativeTime,
} from "@/components/dashboard/livePrimitives";
import {
  dashboardRequestErrorMessage,
  getDashboardRequestAccessFailure,
} from "@/components/dashboard/dashboardRequestAccess";
import {
  hasNonterminalRunActivity,
  useAdaptiveActivityPolling,
} from "@/components/dashboard/useAdaptiveActivityPolling";
import { StatusBadge } from "@/components/dashboard/StatusBadge";

import type { components } from "@/app/types/api";

type Run = components["schemas"]["RunResponse"] & {
  agent_id?: string | null;
  subject_label?: string | null;
  subject_type?: string | null;
  template_id?: string | null;
  execution_mode?: string | null;
};
type RunHistory = components["schemas"]["RunHistoryResponse"];

export function RunsPageClient() {
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [authRequired, setAuthRequired] = useState(false);
  const [permissionDenied, setPermissionDenied] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [runs, setRuns] = useState<Run[]>([]);
  const [lastUpdated, setLastUpdated] = useState<string | null>(null);
  const requestRef = useRef<AbortController | null>(null);

  const loadRuns = useCallback(async (initial = false) => {
    requestRef.current?.abort();
    const controller = new AbortController();
    requestRef.current = controller;

    if (initial) setLoading(true);
    else setRefreshing(true);
    setError(null);

    try {
      const response = await readJson<RunHistory>("/api/dashboard/runs?limit=32", {
        signal: controller.signal,
      });
      if (controller.signal.aborted) return;

      setRuns(response.items ?? []);
      setLastUpdated(new Date().toISOString());
      setAuthRequired(false);
      setPermissionDenied(false);
    } catch (loadError) {
      if (controller.signal.aborted) return;

      const accessFailure = getDashboardRequestAccessFailure(loadError);
      if (accessFailure === "authentication") {
        setAuthRequired(true);
        setPermissionDenied(false);
      } else if (accessFailure === "permission") {
        setPermissionDenied(true);
        setAuthRequired(false);
      } else {
        setError(dashboardRequestErrorMessage(loadError, "Failed to load runs"));
      }
    } finally {
      if (requestRef.current === controller) {
        requestRef.current = null;
        setLoading(false);
        setRefreshing(false);
      }
    }
  }, []);

  useEffect(() => {
    void loadRuns(true);
    return () => {
      requestRef.current?.abort();
    };
  }, [loadRuns]);

  const hasNonterminalActivity = hasNonterminalRunActivity(runs);
  const pollingState = useAdaptiveActivityPolling({
    active: !loading && !refreshing && !authRequired && !permissionDenied && hasNonterminalActivity,
    poll: () => loadRuns(false),
  });

  const totals = useMemo(() => {
    const completed = runs.filter((run) => run.status === "completed").length;
    const failed = runs.filter((run) => run.status === "failed").length;
    const pending = runs.filter((run) => run.status === "created" || run.status === "queued").length;
    const running = runs.filter((run) => run.status === "running" && !run.completed_at).length;
    const live = runs.filter((run) => !run.completed_at).length;
    return { completed, failed, pending, running, live };
  }, [runs]);

  if (loading) return <LiveLoading title="Runs" />;
  if (authRequired) {
    return (
      <LiveAuthRequired
        title="Operator session required"
        message="Sign in to inspect live execution history and traceable run outcomes."
      />
    );
  }
  if (permissionDenied) {
    return (
      <LiveForbidden
        title="Runs permission required"
        message="Your account is signed in, but its role cannot read run history. Run controls and refresh actions are unavailable."
      />
    );
  }
  if (error && runs.length === 0) return <LiveErrorState title="Runs unavailable" message={error} />;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-white/10 bg-white/[0.02] px-4 py-3">
        <div>
          <p className="text-sm font-medium text-white">Run activity snapshot</p>
          <p className="mt-1 text-xs text-slate-500" role="status" aria-live="polite">
            {lastUpdated
              ? `Last updated ${formatRelativeTime(lastUpdated)}. ${hasNonterminalActivity ? pollingState.isOnline ? pollingState.isVisible ? "Checking active runs every 5 seconds." : "Checking active runs every 30 seconds while this tab is hidden." : "Polling paused while offline." : "Polling is idle because every loaded run is terminal."}`
              : "No successful refresh yet."}
          </p>
        </div>
        <button
          type="button"
          onClick={() => void loadRuns(false)}
          disabled={refreshing || !pollingState.isOnline}
          className="rounded-lg border border-white/10 bg-white/[0.04] px-3 py-2 text-xs font-medium text-slate-300 transition hover:border-white/20 hover:text-white disabled:cursor-not-allowed disabled:opacity-50 motion-reduce:transition-none"
        >
          {refreshing ? "Refreshing…" : pollingState.isOnline ? "Refresh now" : "Offline"}
        </button>
      </div>

      {error ? (
        <div role="alert" aria-live="assertive" className="rounded-xl border border-rose-400/20 bg-rose-400/10 px-4 py-3 text-sm text-rose-200">
          Run refresh failed: {error}. The last successful snapshot remains visible.
        </div>
      ) : null}

      <LiveKpiGrid>
        <LiveStatCard label="Total runs" value={String(runs.length)} detail="Recent execution records returned by the runs API." />
        <LiveStatCard
          label="Pending"
          value={String(totals.pending)}
          detail="Runs queued or created, awaiting agent pickup."
          status={asDashboardStatus(totals.pending > 0 ? "warning" : "idle")}
        />
        <LiveStatCard
          label="In flight"
          value={String(totals.running)}
          detail="Runs actively executing on an agent."
          status={asDashboardStatus(totals.running > 0 ? "running" : "idle")}
        />
        <LiveStatCard
          label="Completed"
          value={String(totals.completed)}
          detail="Runs that finished successfully in the current fetch window."
          status="success"
        />
        <LiveStatCard
          label="Failed"
          value={String(totals.failed)}
          detail="Runs that still need recovery or inspection."
          status={asDashboardStatus(totals.failed > 0 ? "failed" : "healthy")}
        />
      </LiveKpiGrid>

      <LivePanel title="Execution timeline" meta={`${runs.length} records`}>
        {runs.length === 0 ? (
          <LiveEmptyState
            title="No runs yet"
            message="Run history will show up here once an owned agent has executed inside MUTX."
          />
        ) : (
          <div className="space-y-4">
            <QueueDepthBar
              entries={[
                { status: "pending", count: totals.pending, label: "Pending" },
                { status: "running", count: totals.running, label: "Running" },
                { status: "completed", count: totals.completed, label: "Done" },
                { status: "failed", count: totals.failed, label: "Failed" },
              ]}
            />
            <div className="space-y-3">
              {runs.map((run) => (
              <div
                key={run.id}
                className="grid gap-3 rounded-xl border border-white/10 bg-white/[0.02] p-4 md:grid-cols-[minmax(0,1fr)_auto]"
              >
                <div className="min-w-0">
                  <p className="truncate font-mono text-sm text-white">{run.id}</p>
                  <p className="mt-1 text-sm text-slate-400">
                    {run.subject_label
                      ? `${run.subject_label} · ${run.execution_mode || "managed"}`
                      : run.agent_id
                        ? `Agent ${run.agent_id.slice(0, 8)}`
                        : "No agent binding"}{" "}
                    · {run.trace_count} traces
                  </p>
                  <div className="mt-2 flex flex-wrap gap-2 text-xs text-slate-500">
                    <span>started {formatRelativeTime(run.started_at)}</span>
                    <span>created {formatRelativeTime(run.created_at)}</span>
                    {run.completed_at ? <span>finished {formatRelativeTime(run.completed_at)}</span> : null}
                  </div>
                  {run.error_message ? (
                    <p className="mt-3 text-sm text-rose-300">{run.error_message}</p>
                  ) : run.output_text ? (
                    <p className="mt-3 line-clamp-2 text-sm text-slate-400">{run.output_text}</p>
                  ) : (
                    <p className="mt-3 text-sm text-slate-500">No output captured yet.</p>
                  )}
                </div>
                <div className="flex items-start justify-between gap-3 md:flex-col md:items-end">
                  <StatusBadge status={asDashboardStatus(run.status)} label={run.status} />
                  <div className="text-right text-xs text-slate-500">
                    <div>{run.trace_count} trace events</div>
                    <div>{run.completed_at ? "terminal" : "live"}</div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
      </LivePanel>
    </div>
  );
}
