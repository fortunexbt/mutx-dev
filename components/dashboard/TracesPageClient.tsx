"use client";

import { useEffect, useMemo, useState } from "react";

import { readJson } from "@/components/app/http";
import {
  dashboardRequestErrorMessage,
  getDashboardRequestAccessFailure,
} from "@/components/dashboard/dashboardRequestAccess";
import {
  LiveAuthRequired,
  LiveEmptyState,
  LiveErrorState,
  LiveForbidden,
  LiveLoading,
  LivePanel,
  asDashboardStatus,
  formatDateTime,
  formatRelativeTime,
} from "@/components/dashboard/livePrimitives";
import { StatusBadge } from "@/components/dashboard/StatusBadge";

import type { components } from "@/app/types/api";

type Run = components["schemas"]["RunResponse"] & {
  agent_id?: string | null;
  subject_label?: string | null;
  execution_mode?: string | null;
};
type RunHistory = components["schemas"]["RunHistoryResponse"];
type RunTrace = components["schemas"]["RunTraceResponse"];
type RunTraceHistory = components["schemas"]["RunTraceHistoryResponse"];

export function TracesPageClient() {
  const [loading, setLoading] = useState(true);
  const [authRequired, setAuthRequired] = useState(false);
  const [permissionDenied, setPermissionDenied] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [runs, setRuns] = useState<Run[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [traces, setTraces] = useState<RunTrace[]>([]);
  const [traceLoading, setTraceLoading] = useState(false);
  const [traceError, setTraceError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function loadRuns() {
      setLoading(true);
      setError(null);
      setAuthRequired(false);
      setPermissionDenied(false);

      try {
        const response = await readJson<RunHistory>("/api/dashboard/runs?limit=18");
        if (!cancelled) {
          const items = response.items ?? [];
          setRuns(items);
          setSelectedRunId(items[0]?.id ?? null);
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
            setError(dashboardRequestErrorMessage(loadError, "Failed to load runs"));
          }
          setLoading(false);
        }
      }
    }

    void loadRuns();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const runId = selectedRunId;

    if (!runId) {
      setTraces([]);
      setTraceLoading(false);
      setTraceError(null);
      return;
    }
    const activeRunId: string = runId;

    let cancelled = false;
    async function loadTraces() {
      setTraces([]);
      setTraceLoading(true);
      setTraceError(null);
      try {
        const response = await readJson<RunTraceHistory>(
          `/api/dashboard/runs/${encodeURIComponent(activeRunId)}/traces?limit=64`,
        );
        if (!cancelled) {
          setTraces(response.items ?? []);
        }
      } catch (loadError) {
        if (!cancelled) {
          const accessFailure = getDashboardRequestAccessFailure(loadError);
          if (accessFailure === "authentication") {
            setAuthRequired(true);
          } else if (accessFailure === "permission") {
            setPermissionDenied(true);
          } else {
            setTraceError(dashboardRequestErrorMessage(loadError, "Failed to load traces"));
          }
        }
      } finally {
        if (!cancelled) {
          setTraceLoading(false);
        }
      }
    }

    void loadTraces();
    return () => {
      cancelled = true;
    };
  }, [selectedRunId]);

  const selectedRun = useMemo(
    () => runs.find((run) => run.id === selectedRunId) ?? null,
    [runs, selectedRunId],
  );

  if (loading) return <LiveLoading title="Traces" />;
  if (authRequired) {
    return (
      <LiveAuthRequired
        title="Operator session required"
        message="Sign in to inspect run traces and correlated execution events."
      />
    );
  }
  if (permissionDenied) {
    return <LiveForbidden title="Trace permission required" message="Your account cannot inspect run traces. Run selection controls are unavailable." />;
  }
  if (error && runs.length === 0) return <LiveErrorState title="Trace explorer unavailable" message={error} />;
  if (runs.length === 0) {
    return (
      <LiveEmptyState
        title="No runs with traces"
        message="No agent runs have been recorded yet. Traces will appear here once runs are executed."
      />
    );
  }

  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(280px,0.92fr)_minmax(0,1.08fr)]">
      <LivePanel title="Traceable runs" meta={`${runs.length} runs`}>
        <div className="space-y-3">
          {runs.map((run) => {
            const active = run.id === selectedRunId;
            return (
              <button
                key={run.id}
                type="button"
                onClick={() => setSelectedRunId(run.id)}
                className={`w-full rounded-xl border p-4 text-left transition ${
                  active
                    ? "border-cyan-400/35 bg-cyan-400/10"
                    : "border-white/10 bg-white/[0.02] hover:border-white/20"
                }`}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="truncate font-mono text-sm text-white">{run.id}</p>
                    <p className="mt-1 text-sm text-slate-400">
                      {run.subject_label
                        ? `${run.subject_label} · ${run.execution_mode || "managed"}`
                        : run.agent_id
                          ? `Agent ${run.agent_id.slice(0, 8)}`
                          : "No agent binding"}
                    </p>
                  </div>
                  <StatusBadge status={asDashboardStatus(run.status)} label={run.status} />
                </div>
                <div className="mt-3 flex flex-wrap gap-2 text-xs text-slate-500">
                  <span>{run.trace_count} traces</span>
                  <span>{formatRelativeTime(run.started_at)}</span>
                </div>
              </button>
            );
          })}
        </div>
      </LivePanel>

      <LivePanel
        title="Trace stream"
        meta={selectedRun ? `${selectedRun.trace_count} events` : "no run selected"}
      >
        {selectedRun ? (
          <div className="space-y-4">
            <div className="rounded-xl border border-white/10 bg-white/[0.02] p-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="truncate font-mono text-sm text-white">{selectedRun.id}</p>
                  <p className="mt-1 text-sm text-slate-400">
                    {selectedRun.subject_label
                      ? `${selectedRun.subject_label} · ${selectedRun.execution_mode || "managed"}`
                      : selectedRun.agent_id
                        ? `Agent ${selectedRun.agent_id.slice(0, 8)}`
                        : "No agent binding"}{" "}
                    · started {formatRelativeTime(selectedRun.started_at)}
                  </p>
                </div>
                <StatusBadge status={asDashboardStatus(selectedRun.status)} label={selectedRun.status} />
              </div>
            </div>

            {traceLoading ? (
              <LiveLoading title="Trace stream" />
            ) : traceError ? (
              <LiveErrorState title="Trace stream unavailable" message={traceError} />
            ) : traces.length === 0 ? (
              <LiveEmptyState
                title="No trace events captured"
                message="This run exists, but the backend did not return trace rows for it yet."
              />
            ) : (
              <div className="space-y-3">
                {traces.map((trace) => (
                  <div key={trace.id} className="rounded-xl border border-white/10 bg-white/[0.02] p-4">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <p className="text-sm font-medium text-white">{trace.event_type}</p>
                        <p className="mt-1 text-sm text-slate-400">{trace.message || "No trace message captured."}</p>
                      </div>
                      <div className="text-right text-xs text-slate-500">
                        <div>#{trace.sequence}</div>
                        <div>{formatRelativeTime(trace.timestamp)}</div>
                      </div>
                    </div>
                    <p className="mt-2 text-xs text-slate-500">{formatDateTime(trace.timestamp)}</p>
                  </div>
                ))}
              </div>
            )}
          </div>
        ) : null}
      </LivePanel>
    </div>
  );
}
