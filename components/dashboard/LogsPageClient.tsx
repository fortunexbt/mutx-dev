"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowUpCircle, CheckCircle, Circle, XCircle } from "lucide-react";

import { type components } from "@/app/types/api";
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
  asDashboardStatus,
  formatDateTime,
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

type Run = components["schemas"]["RunResponse"];
type RunDetail = components["schemas"]["RunDetailResponse"];
type RunHistory = components["schemas"]["RunHistoryResponse"];
type RunTrace = components["schemas"]["RunTraceResponse"];

interface LogsPageClientProps {
  mode?: "logs" | "history";
}

function TraceIcon({ eventType }: { eventType: string }) {
  const normalizedType = eventType.toLowerCase();

  if (
    normalizedType.includes("error") ||
    normalizedType.includes("fail") ||
    normalizedType.includes("denied")
  ) {
    return <XCircle className="h-3.5 w-3.5 shrink-0 text-red-400" />;
  }
  if (normalizedType.includes("tool") || normalizedType.includes("request")) {
    return <ArrowUpCircle className="h-3.5 w-3.5 shrink-0 text-cyan-400" />;
  }
  if (
    normalizedType.includes("complete") ||
    normalizedType.includes("success") ||
    normalizedType.includes("promoted")
  ) {
    return <CheckCircle className="h-3.5 w-3.5 shrink-0 text-green-400" />;
  }
  return <Circle className="h-3.5 w-3.5 shrink-0 text-purple-400" />;
}

function formatRunDuration(
  run: Pick<RunDetail, "started_at" | "completed_at" | "status">,
) {
  if (!run.completed_at) {
    return run.status === "running" || run.status === "pending"
      ? "In progress"
      : "Not recorded";
  }

  const startedAt = new Date(run.started_at).getTime();
  const completedAt = new Date(run.completed_at).getTime();
  const durationMs = completedAt - startedAt;

  if (!Number.isFinite(durationMs) || durationMs < 0) return "N/A";
  if (durationMs < 1000) return `${durationMs}ms`;

  return `${(durationMs / 1000).toFixed(durationMs < 10_000 ? 2 : 1)}s`;
}

function TraceEntry({ trace }: { trace: RunTrace }) {
  const hasPayload = Object.keys(trace.payload).length > 0;

  return (
    <article className="rounded-lg border border-white/5 bg-white/[0.02] px-3 py-2 text-xs">
      <div className="flex items-start gap-3">
        <div className="mt-0.5 shrink-0">
          <TraceIcon eventType={trace.event_type} />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center justify-between gap-2">
            <span className="truncate font-mono text-white/80">{trace.event_type}</span>
            <span className="shrink-0 font-mono text-[10px] text-slate-500">
              #{trace.sequence}
            </span>
          </div>
          {trace.message ? (
            <p className="mt-1 whitespace-pre-wrap text-[11px] leading-5 text-slate-300">
              {trace.message}
            </p>
          ) : null}
          <div className="mt-1 flex items-center gap-2 text-[10px] text-slate-500">
            <span>{formatDateTime(trace.timestamp)}</span>
          </div>
        </div>
      </div>
      {hasPayload ? (
        <details className="mt-2 border-t border-white/5 pt-2">
          <summary className="cursor-pointer font-mono text-[10px] uppercase tracking-widest text-slate-500">
            Event payload
          </summary>
          <pre className="mt-2 max-h-40 overflow-auto whitespace-pre-wrap break-words rounded bg-black/20 p-2 text-[10px] text-slate-400">
            {JSON.stringify(trace.payload, null, 2)}
          </pre>
        </details>
      ) : null}
    </article>
  );
}

export function LogsPageClient({ mode = "logs" }: LogsPageClientProps) {
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [authRequired, setAuthRequired] = useState(false);
  const [permissionDenied, setPermissionDenied] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [runs, setRuns] = useState<Run[]>([]);
  const [totalRuns, setTotalRuns] = useState(0);
  const [selectedRun, setSelectedRun] = useState<RunDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<string | null>(null);
  const listRequestRef = useRef<AbortController | null>(null);
  const detailRequestRef = useRef<AbortController | null>(null);
  const selectedRunIdRef = useRef<string | null>(null);
  const isHistory = mode === "history";

  const handleAccessFailure = useCallback((loadError: unknown) => {
    const accessFailure = getDashboardRequestAccessFailure(loadError);
    if (accessFailure === "authentication") {
      setAuthRequired(true);
      setPermissionDenied(false);
      return true;
    }
    if (accessFailure === "permission") {
      setPermissionDenied(true);
      setAuthRequired(false);
      return true;
    }
    return false;
  }, []);

  const loadRunDetail = useCallback(async (runId: string, showLoading = true) => {
    detailRequestRef.current?.abort();
    const controller = new AbortController();
    detailRequestRef.current = controller;
    selectedRunIdRef.current = runId;

    if (showLoading) setDetailLoading(true);
    setDetailError(null);
    try {
      const detail = await readJson<RunDetail>(
        `/api/dashboard/runs/${encodeURIComponent(runId)}`,
        { signal: controller.signal },
      );
      if (controller.signal.aborted) return;

      setSelectedRun(detail);
      setAuthRequired(false);
      setPermissionDenied(false);
    } catch (detailLoadError) {
      if (controller.signal.aborted) return;
      if (!handleAccessFailure(detailLoadError)) {
        setDetailError(dashboardRequestErrorMessage(detailLoadError, "Failed to load run detail"));
      }
    } finally {
      if (detailRequestRef.current === controller) {
        detailRequestRef.current = null;
        if (showLoading) setDetailLoading(false);
      }
    }
  }, [handleAccessFailure]);

  const loadRuns = useCallback(async ({
    background = false,
    initial = false,
  }: {
    background?: boolean;
    initial?: boolean;
  } = {}) => {
    listRequestRef.current?.abort();
    const controller = new AbortController();
    listRequestRef.current = controller;

    if (initial) setLoading(true);
    else if (!background) setRefreshing(true);
    setError(null);

    try {
      const response = await readJson<RunHistory>("/api/dashboard/runs?limit=48", {
        signal: controller.signal,
      });
      if (controller.signal.aborted) return;

      const items = response.items ?? [];
      setRuns(items);
      setTotalRuns(response.total);
      setLastUpdated(new Date().toISOString());
      setAuthRequired(false);
      setPermissionDenied(false);

      const selectedId = selectedRunIdRef.current;
      const nextSelectedId = items.some((run) => run.id === selectedId)
        ? selectedId
        : items[0]?.id ?? null;
      selectedRunIdRef.current = nextSelectedId;

      if (nextSelectedId) {
        await loadRunDetail(nextSelectedId, initial);
      } else {
        setSelectedRun(null);
        setDetailError(null);
      }
    } catch (loadError) {
      if (controller.signal.aborted) return;
      if (!handleAccessFailure(loadError)) {
        setError(dashboardRequestErrorMessage(loadError, "Failed to load runs"));
      }
    } finally {
      if (listRequestRef.current === controller) {
        listRequestRef.current = null;
        setLoading(false);
        setRefreshing(false);
      }
    }
  }, [handleAccessFailure, loadRunDetail]);

  useEffect(() => {
    void loadRuns({ initial: true });
    return () => {
      listRequestRef.current?.abort();
      detailRequestRef.current?.abort();
    };
  }, [loadRuns]);

  const handleSelectRun = (runId: string) => {
    void loadRunDetail(runId, true);
  };

  const hasNonterminalActivity = hasNonterminalRunActivity(runs);
  const pollingState = useAdaptiveActivityPolling({
    active:
      !loading &&
      !refreshing &&
      !detailLoading &&
      !authRequired &&
      !permissionDenied &&
      hasNonterminalActivity,
    poll: () => loadRuns({ background: true }),
  });

  const totals = {
    completed: runs.filter((run) => run.status === "completed").length,
    failed: runs.filter((run) => run.status === "failed" || run.status === "error").length,
    running: runs.filter((run) => run.status === "running" || run.status === "pending").length,
  };

  const surfaceTitle = isHistory ? "History" : "Logs";

  if (loading) return <LiveLoading title={surfaceTitle} />;
  if (authRequired) {
    return (
      <LiveAuthRequired
        title="Operator session required"
        message={`Sign in to access the ${isHistory ? "execution history" : "trace log"}.`}
      />
    );
  }
  if (permissionDenied) {
    return (
      <LiveForbidden
        title={`${surfaceTitle} permission required`}
        message="Your account is signed in, but its role cannot read runs or trace details. Selection and refresh actions are unavailable."
      />
    );
  }
  if (error && runs.length === 0) return <LiveErrorState title={`${surfaceTitle} unavailable`} message={error} />;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-white/10 bg-white/[0.02] px-4 py-3">
        <div>
          <p className="text-sm font-medium text-white">{surfaceTitle} activity snapshot</p>
          <p className="mt-1 text-xs text-slate-500" role="status" aria-live="polite">
            {lastUpdated
              ? `Last updated ${formatRelativeTime(lastUpdated)}. ${hasNonterminalActivity ? pollingState.isOnline ? pollingState.isVisible ? "Checking active runs every 5 seconds." : "Checking active runs every 30 seconds while this tab is hidden." : "Polling paused while offline." : "Polling is idle because every loaded run is terminal."}`
              : "No successful refresh yet."}
          </p>
        </div>
        <button
          type="button"
          onClick={() => void loadRuns()}
          disabled={refreshing || !pollingState.isOnline}
          className="rounded-lg border border-white/10 bg-white/[0.04] px-3 py-2 text-xs font-medium text-slate-300 transition hover:border-white/20 hover:text-white disabled:cursor-not-allowed disabled:opacity-50 motion-reduce:transition-none"
        >
          {refreshing ? "Refreshing…" : pollingState.isOnline ? "Refresh now" : "Offline"}
        </button>
      </div>

      {error ? (
        <div role="alert" aria-live="assertive" className="rounded-xl border border-rose-400/20 bg-rose-400/10 px-4 py-3 text-sm text-rose-200">
          {surfaceTitle} refresh failed: {error}. The last successful snapshot remains visible.
        </div>
      ) : null}

      <LiveKpiGrid>
        <LiveStatCard
          label="Recorded runs"
          value={String(totalRuns)}
          detail={`${runs.length} most recent records loaded from the control plane.`}
        />
        <LiveStatCard
          label="Completed"
          value={String(totals.completed)}
          detail="Completed runs in the loaded activity window."
          status="success"
        />
        <LiveStatCard
          label="Failed"
          value={String(totals.failed)}
          detail="Failed runs in the loaded activity window."
          status={totals.failed > 0 ? "error" : undefined}
        />
        <LiveStatCard
          label="In flight"
          value={String(totals.running)}
          detail="Running or pending runs in the loaded activity window."
          status={totals.running > 0 ? "running" : "idle"}
        />
      </LiveKpiGrid>

      <div className="grid gap-4 xl:grid-cols-[minmax(260px,0.75fr)_minmax(0,1.25fr)]">
        <LivePanel
          title={isHistory ? "Execution history" : "Run log snapshot"}
          meta={`${runs.length} loaded`}
        >
          {runs.length === 0 ? (
            <LiveEmptyState
              title="No runs recorded"
              message="Run activity will appear here after the control plane records an execution."
            />
          ) : (
            <div className="space-y-1.5">
              {runs.map((run) => (
                <button
                  key={run.id}
                  type="button"
                  aria-pressed={selectedRun?.id === run.id}
                  onClick={() => handleSelectRun(run.id)}
                  className={`w-full rounded-lg border p-2.5 text-left transition-colors ${
                    selectedRun?.id === run.id
                      ? "border-cyan-500/40 bg-cyan-500/10"
                      : "border-white/8 bg-white/[0.02] hover:bg-white/[0.05]"
                  }`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="min-w-0 flex-1">
                      <span className="block truncate font-mono text-[11px] text-white/70">
                        {run.subject_label || run.id}
                      </span>
                      {run.subject_label ? (
                        <span className="block truncate font-mono text-[9px] text-slate-600">
                          {run.id}
                        </span>
                      ) : null}
                    </span>
                    <StatusBadge status={asDashboardStatus(run.status)} label={run.status} />
                  </div>
                  <div className="mt-1 flex flex-wrap items-center gap-2 text-[10px] text-slate-500">
                    <span>{formatRelativeTime(run.started_at)}</span>
                    <span>·</span>
                    <span>{run.trace_count} traces</span>
                    {run.execution_mode ? (
                      <>
                        <span>·</span>
                        <span>{run.execution_mode}</span>
                      </>
                    ) : null}
                  </div>
                </button>
              ))}
            </div>
          )}
        </LivePanel>

        <LivePanel
          title={isHistory ? "Run activity" : "Run traces"}
          meta={selectedRun ? selectedRun.id : "no selection"}
          action={
            selectedRun ? (
              <button
                type="button"
                onClick={() => void loadRunDetail(selectedRun.id, true)}
                className="rounded-lg border border-white/10 bg-white/5 px-2.5 py-1 text-[10px] text-slate-300 transition hover:border-white/20 hover:text-white"
              >
                Refresh
              </button>
            ) : undefined
          }
        >
          {detailLoading ? (
            <div className="space-y-2" aria-label="Loading run activity">
              {[1, 2, 3, 4].map((item) => (
                <div key={item} className="h-12 rounded-lg bg-white/5 motion-safe:animate-pulse motion-reduce:animate-none" />
              ))}
            </div>
          ) : detailError ? (
            <div
              role="alert"
              className="rounded-xl border border-red-500/20 bg-red-500/10 p-4 text-sm text-red-300"
            >
              {detailError}
            </div>
          ) : selectedRun ? (
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-3 rounded-lg border border-white/8 bg-white/[0.02] p-3">
                <div>
                  <div className="text-[10px] uppercase tracking-widest text-slate-500">Agent</div>
                  <div className="mt-0.5 truncate font-mono text-xs text-white/80">
                    {selectedRun.agent_id || "Unassigned"}
                  </div>
                </div>
                <div>
                  <div className="text-[10px] uppercase tracking-widest text-slate-500">Subject</div>
                  <div className="mt-0.5 truncate text-xs text-white/80">
                    {selectedRun.subject_label || selectedRun.subject_type || "General run"}
                  </div>
                </div>
                <div>
                  <div className="text-[10px] uppercase tracking-widest text-slate-500">Duration</div>
                  <div className="mt-0.5 text-xs text-white/80">
                    {formatRunDuration(selectedRun)}
                  </div>
                </div>
                <div>
                  <div className="text-[10px] uppercase tracking-widest text-slate-500">Status</div>
                  <div className="mt-0.5 text-xs text-white/80">{selectedRun.status}</div>
                </div>
              </div>

              {selectedRun.input_text || selectedRun.output_text ? (
                <div className="grid gap-2 md:grid-cols-2">
                  {selectedRun.input_text ? (
                    <div className="rounded-lg border border-white/8 bg-white/[0.02] p-3">
                      <div className="text-[10px] uppercase tracking-widest text-slate-500">Input</div>
                      <p className="mt-1 whitespace-pre-wrap text-xs leading-5 text-slate-300">
                        {selectedRun.input_text}
                      </p>
                    </div>
                  ) : null}
                  {selectedRun.output_text ? (
                    <div className="rounded-lg border border-white/8 bg-white/[0.02] p-3">
                      <div className="text-[10px] uppercase tracking-widest text-slate-500">Output</div>
                      <p className="mt-1 whitespace-pre-wrap text-xs leading-5 text-slate-300">
                        {selectedRun.output_text}
                      </p>
                    </div>
                  ) : null}
                </div>
              ) : null}

              {selectedRun.traces && selectedRun.traces.length > 0 ? (
                <div className="space-y-1">
                  <div className="mb-2 text-[10px] uppercase tracking-widest text-slate-500">
                    Traces ({selectedRun.traces.length})
                  </div>
                  <div className="max-h-[32rem] space-y-1 overflow-y-auto">
                    {selectedRun.traces.map((trace) => (
                      <TraceEntry key={trace.id} trace={trace} />
                    ))}
                  </div>
                </div>
              ) : (
                <LiveEmptyState
                  title="No trace data"
                  message="This run detail does not contain any recorded trace events."
                />
              )}

              {selectedRun.error_message ? (
                <div
                  role="alert"
                  className="rounded-lg border border-red-500/20 bg-red-500/10 p-3 text-xs text-red-300"
                >
                  <div className="mb-1 text-[10px] uppercase tracking-widest text-red-400">
                    Error
                  </div>
                  {selectedRun.error_message}
                </div>
              ) : null}
            </div>
          ) : (
            <LiveEmptyState
              title="No run selected"
              message="Select a run to inspect its recorded activity and trace events."
            />
          )}
        </LivePanel>
      </div>
    </div>
  );
}
