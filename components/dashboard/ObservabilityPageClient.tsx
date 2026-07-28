"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { ArrowRight } from "lucide-react";

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
  LiveKpiGrid,
  LiveLoading,
  LiveMiniStat,
  LiveMiniStatGrid,
  LivePanel,
  LiveStatCard,
  asDashboardStatus,
  formatRelativeTime,
} from "@/components/dashboard/livePrimitives";
import { StatusBadge } from "@/components/dashboard/StatusBadge";

import type { components } from "@/app/types/api";

type MutxRun = components["schemas"]["MutxRunResponse"];
type MutxRunDetail = components["schemas"]["MutxRunDetailResponse"];

interface TelemetryConfig {
  otel_enabled?: boolean;
  exporter_type?: string;
  endpoint?: string | null;
}

interface TelemetryHealth {
  configured?: boolean;
  endpoint_reachable?: boolean;
  using_grpc?: boolean;
  endpoint?: string | null;
}

interface SessionSummary {
  total: number;
  active: number;
  channels: number;
  sources: number;
  latestActivityAt: string | null;
}

interface ObservabilityResponse {
  items: MutxRun[];
  total: number;
  skip: number;
  limit: number;
  telemetry?: {
    config: TelemetryConfig | null;
    health: TelemetryHealth | null;
    errors: Record<string, string> | null;
  } | null;
  sessionSummary?: SessionSummary | null;
  sessionSummaryError?: string | null;
}

export function ObservabilityPageClient() {
  const [loading, setLoading] = useState(true);
  const [authRequired, setAuthRequired] = useState(false);
  const [permissionDenied, setPermissionDenied] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [runs, setRuns] = useState<MutxRun[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [selectedRun, setSelectedRun] = useState<MutxRunDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [telemetry, setTelemetry] = useState<ObservabilityResponse["telemetry"]>(null);
  const [sessionSummary, setSessionSummary] = useState<SessionSummary | null>(null);
  const [sessionSummaryError, setSessionSummaryError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setLoading(true);
      setError(null);
      setAuthRequired(false);
      setPermissionDenied(false);

      try {
        const response = await readJson<ObservabilityResponse>("/api/dashboard/observability?limit=50");
        if (!cancelled) {
          setRuns(response.items ?? []);
          setTelemetry(response.telemetry ?? null);
          setSessionSummary(response.sessionSummary ?? null);
          setSessionSummaryError(response.sessionSummaryError ?? null);
          setSelectedRunId(response.items?.[0]?.id ?? null);
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
            setError(dashboardRequestErrorMessage(loadError, "Failed to load observability data"));
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

  useEffect(() => {
    const runId = selectedRunId;

    if (!runId) {
      setSelectedRun(null);
      setDetailLoading(false);
      setDetailError(null);
      return;
    }
    const activeRunId: string = runId;

    let cancelled = false;

    async function loadRunDetail() {
      setSelectedRun(null);
      setDetailLoading(true);
      setDetailError(null);

      try {
        const response = await readJson<MutxRunDetail>(
          `/api/dashboard/observability/runs/${encodeURIComponent(activeRunId)}`,
        );
        if (!cancelled) {
          setSelectedRun(response);
        }
      } catch (loadError) {
        if (!cancelled) {
          const accessFailure = getDashboardRequestAccessFailure(loadError);
          if (accessFailure === "authentication") {
            setAuthRequired(true);
          } else if (accessFailure === "permission") {
            setPermissionDenied(true);
          } else {
            setDetailError(dashboardRequestErrorMessage(loadError, "Failed to load run detail"));
          }
        }
      } finally {
        if (!cancelled) {
          setDetailLoading(false);
        }
      }
    }

    void loadRunDetail();
    return () => {
      cancelled = true;
    };
  }, [selectedRunId]);

  const totals = useMemo(() => {
    const completed = runs.filter((run) => run.status === "completed").length;
    const failed = runs.filter((run) => run.status === "failed").length;
    const running = runs.filter((run) => run.status === "running").length;
    return { completed, failed, running };
  }, [runs]);

  const telemetryStatus = useMemo(() => {
    if (telemetry?.errors) return "degraded";
    if (!telemetry?.health?.configured) return "not configured";
    if (telemetry.health.endpoint_reachable) return "healthy";
    return "unreachable";
  }, [telemetry]);

  const telemetryDetail = useMemo(() => {
    if (!telemetry?.health?.configured) {
      return "Telemetry exporter has not been configured yet.";
    }

    if (telemetry?.config?.endpoint) {
      return `${telemetry.config.exporter_type || "otlp"} · ${telemetry.config.endpoint}`;
    }

    return telemetry?.config?.exporter_type || "Configured without an endpoint summary.";
  }, [telemetry]);

  if (loading) return <LiveLoading title="Observability" />;
  if (authRequired) {
    return (
      <LiveAuthRequired
        title="Operator session required"
        message="Sign in to inspect agent run observability data."
      />
    );
  }
  if (permissionDenied) {
    return <LiveForbidden title="Observability permission required" message="Your account cannot inspect observability runs or detail. Selection controls are unavailable." />;
  }
  if (error) return <LiveErrorState title="Observability unavailable" message={error} />;

  return (
    <div className="space-y-4">
      <LiveKpiGrid>
        <LiveStatCard label="Total runs" value={String(runs.length)} detail="Agent runs tracked by MUTX observability." />
        <LiveStatCard
          label="Running"
          value={String(totals.running)}
          detail="Runs currently in progress."
          status={totals.running > 0 ? "running" : "idle"}
        />
        <LiveStatCard
          label="Completed"
          value={String(totals.completed)}
          detail="Runs that finished successfully."
          status="success"
        />
        <LiveStatCard
          label="Failed"
          value={String(totals.failed)}
          detail="Runs that encountered errors."
          status={totals.failed > 0 ? "error" : undefined}
        />
        <LiveStatCard
          label="Telemetry"
          value={telemetryStatus}
          detail={telemetryDetail}
          status={asDashboardStatus(telemetryStatus)}
        />
        <LiveStatCard
          label="Sessions"
          value={String(sessionSummary?.total ?? 0)}
          detail={
            sessionSummary
              ? `${sessionSummary.active} active · ${sessionSummary.channels} channels · ${sessionSummary.sources} sources`
              : "Session summary is not available from the current dashboard feed."
          }
          status={asDashboardStatus((sessionSummary?.active ?? 0) > 0 ? "running" : "idle")}
        />
      </LiveKpiGrid>

      <div className="grid gap-4 xl:grid-cols-[minmax(280px,0.72fr)_minmax(0,1.28fr)]">
        <div className="space-y-4">
          <LivePanel title="Telemetry rail" meta={telemetry?.config?.exporter_type || "runtime summary"}>
            <LiveMiniStatGrid>
              <LiveMiniStat
                label="Exporter"
                value={telemetry?.config?.exporter_type || "not configured"}
                detail={telemetry?.config?.endpoint || "No OTLP endpoint has been configured yet."}
              />
              <LiveMiniStat
                label="Reachability"
                value={
                  !telemetry?.health?.configured
                    ? "not configured"
                    : telemetry.health.endpoint_reachable
                      ? "reachable"
                      : "degraded"
                }
                detail={
                  telemetry?.health?.endpoint
                    ? `Health check via ${telemetry.health.endpoint}`
                    : "Health follows the configured telemetry backend."
                }
              />
              <LiveMiniStat
                label="Live sessions"
                value={String(sessionSummary?.total ?? 0)}
                detail={
                  sessionSummary
                    ? `${sessionSummary.active} active across ${sessionSummary.channels} channels and ${sessionSummary.sources} sources.`
                    : "Session summary is unavailable."
                }
              />
              <LiveMiniStat
                label="Last activity"
                value={
                  sessionSummary?.latestActivityAt
                    ? formatRelativeTime(sessionSummary.latestActivityAt)
                    : "Not recorded"
                }
                detail={
                  sessionSummary?.latestActivityAt
                    ? `Latest session activity ${sessionSummary.latestActivityAt}`
                    : "No recent session activity has been returned yet."
                }
              />
            </LiveMiniStatGrid>

            {telemetry?.errors ? (
              <div
                role="alert"
                aria-live="assertive"
                className="mt-4 rounded-xl border border-amber-500/20 bg-amber-500/10 p-3 text-sm text-amber-100"
              >
                {Object.entries(telemetry.errors).map(([scope, message]) => (
                  <div key={scope}>
                    <span className="font-medium capitalize">{scope}</span>
                    {" "}
                    {message}
                  </div>
                ))}
              </div>
            ) : null}

            {sessionSummaryError ? (
              <div
                role="alert"
                aria-live="assertive"
                className="mt-4 rounded-xl border border-amber-500/20 bg-amber-500/10 p-3 text-sm text-amber-100"
              >
                <span className="font-medium">Sessions</span>{" "}
                {sessionSummaryError}
              </div>
            ) : null}
          </LivePanel>

          <LivePanel title="Next routes" meta="follow the signal">
            <div className="space-y-3">
              {[
                {
                  href: "/dashboard/traces",
                  label: "Trace stream",
                  detail: "Inspect per-run trace events and sequence details.",
                },
                {
                  href: "/dashboard/sessions",
                  label: "Sessions",
                  detail: "Review channel activity, active sessions, and gateway posture.",
                },
                {
                  href: "/dashboard/security",
                  label: "Security",
                  detail: "Check auth and operator posture when observability degrades unexpectedly.",
                },
              ].map((destination) => (
                <Link
                  key={destination.href}
                  href={destination.href}
                  className="flex items-center justify-between rounded-xl border border-white/10 bg-white/[0.02] px-4 py-3 text-sm text-slate-300 transition hover:border-white/20 hover:text-white"
                >
                  <div>
                    <div className="font-medium text-white">{destination.label}</div>
                    <div className="mt-1 text-xs text-slate-500">{destination.detail}</div>
                  </div>
                  <ArrowRight className="h-4 w-4 shrink-0 text-cyan-300" />
                </Link>
              ))}
            </div>
          </LivePanel>
        </div>

        <div className="space-y-4">
          <LivePanel title="Agent Runs" meta={`${runs.length} records`}>
            {runs.length === 0 ? (
              <LiveEmptyState
                title="No runs yet"
                message="Agent run observability data will appear here once agents emit runs."
              />
            ) : (
              <div className="space-y-2">
                {runs.map((run) => (
                  <button
                    key={run.id}
                    type="button"
                    onClick={() => setSelectedRunId(run.id)}
                    aria-pressed={selectedRunId === run.id}
                    className={`w-full rounded-lg border p-3 text-left transition-colors ${
                      selectedRunId === run.id
                        ? "border-cyan-500/50 bg-cyan-500/10"
                        : "border-white/10 bg-white/[0.02] hover:bg-white/[0.05]"
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <span className="truncate font-mono text-sm text-white">{run.id.slice(0, 16)}...</span>
                      <StatusBadge
                        status={asDashboardStatus(run.status)}
                        label={run.status}
                      />
                    </div>
                    <div className="mt-1 text-xs text-slate-400">
                      {run.agent_id.slice(0, 12)} · {run.model || "no model"}
                    </div>
                    <div className="mt-1 text-xs text-slate-500">
                      {run.step_count} {run.step_count === 1 ? "step" : "steps"}
                    </div>
                    {run.cost ? (
                      <div className="mt-1 text-xs text-slate-500">
                        {run.cost.cost_usd != null
                          ? `$${run.cost.cost_usd.toFixed(4)}`
                          : "Cost unavailable"}
                        {" · "}
                        {(run.cost.total_tokens ??
                          run.cost.input_tokens + run.cost.output_tokens).toLocaleString()} tokens
                      </div>
                    ) : null}
                  </button>
                ))}
              </div>
            )}
          </LivePanel>

          <LivePanel title="Run Detail" meta={selectedRunId ? selectedRunId.slice(0, 16) : "-"}>
            {detailLoading ? (
              <LiveLoading title="Run detail" />
            ) : detailError ? (
              <LiveErrorState title="Run detail unavailable" message={detailError} />
            ) : selectedRun ? (
              <div className="space-y-4">
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <div className="text-xs text-slate-500">Status</div>
                    <div className="text-sm text-white">{selectedRun.status}</div>
                  </div>
                  <div>
                    <div className="text-xs text-slate-500">Agent</div>
                    <div className="truncate text-sm text-white">{selectedRun.agent_id}</div>
                  </div>
                  <div>
                    <div className="text-xs text-slate-500">Model</div>
                    <div className="text-sm text-white">{selectedRun.model || "-"}</div>
                  </div>
                  <div>
                    <div className="text-xs text-slate-500">Provider</div>
                    <div className="text-sm text-white">{selectedRun.provider || "-"}</div>
                  </div>
                  <div>
                    <div className="text-xs text-slate-500">Duration</div>
                    <div className="text-sm text-white">
                      {selectedRun.duration_ms != null
                        ? `${(selectedRun.duration_ms / 1000).toFixed(2)}s`
                        : "-"}
                    </div>
                  </div>
                  <div>
                    <div className="text-xs text-slate-500">Steps</div>
                    <div className="text-sm text-white">{selectedRun.steps.length}</div>
                  </div>
                </div>

                {selectedRun.cost && (
                  <div>
                    <div className="mb-2 text-xs text-slate-500">Cost Breakdown</div>
                    <div className="rounded-lg border border-white/10 bg-white/[0.02] p-3">
                      <div className="grid grid-cols-3 gap-2 text-center">
                        <div>
                          <div className="text-lg text-white">{selectedRun.cost.input_tokens.toLocaleString()}</div>
                          <div className="text-xs text-slate-500">Input</div>
                        </div>
                        <div>
                          <div className="text-lg text-white">{selectedRun.cost.output_tokens.toLocaleString()}</div>
                          <div className="text-xs text-slate-500">Output</div>
                        </div>
                        <div>
                          <div className="text-lg text-cyan-400">
                            {selectedRun.cost.cost_usd != null
                              ? `$${selectedRun.cost.cost_usd.toFixed(4)}`
                              : "N/A"}
                          </div>
                          <div className="text-xs text-slate-500">Cost</div>
                        </div>
                      </div>
                    </div>
                  </div>
                )}

                {selectedRun.steps.length > 0 ? (
                  <div>
                    <div className="mb-2 text-xs text-slate-500">Steps ({selectedRun.steps.length})</div>
                    <div className="max-h-64 space-y-1 overflow-y-auto">
                      {selectedRun.steps.map((step, i) => (
                        <div
                          key={step.id}
                          className="flex items-center gap-2 rounded border border-white/5 bg-white/[0.02] p-2 text-xs"
                        >
                          <span className="w-6 text-slate-500">{i + 1}</span>
                          <span
                            className={`rounded px-1.5 py-0.5 text-[10px] ${
                              step.type === "tool_call"
                                ? "bg-blue-500/20 text-blue-300"
                                : step.type === "reasoning"
                                  ? "bg-purple-500/20 text-purple-300"
                                  : "bg-slate-500/20 text-slate-300"
                            }`}
                          >
                            {step.type}
                          </span>
                          <span className="flex-1 truncate text-slate-300">
                            {step.tool_name || step.input_preview || step.output_preview || "No step details recorded"}
                          </span>
                          {step.success != null ? (
                            <span className={step.success ? "text-green-400" : "text-red-400"}>
                              {step.success ? "✓" : "✗"}
                            </span>
                          ) : null}
                          {step.duration_ms != null ? (
                            <span className="text-slate-500">{step.duration_ms}ms</span>
                          ) : null}
                        </div>
                      ))}
                    </div>
                  </div>
                ) : (
                  <LiveEmptyState
                    title="No steps recorded"
                    message="The run detail loaded successfully, but it does not contain execution steps."
                  />
                )}

                {selectedRun.error && (
                  <div>
                    <div className="mb-2 text-xs text-slate-500">Error</div>
                    <div className="rounded-lg border border-red-500/20 bg-red-500/10 p-3 text-sm text-red-300">
                      {selectedRun.error}
                    </div>
                  </div>
                )}
              </div>
            ) : selectedRunId ? (
              <LiveEmptyState
                title="Run detail not returned"
                message="The selected run did not return a detail record."
              />
            ) : (
              <LiveEmptyState title="No run selected" message="Select a run from the list to view details." />
            )}
          </LivePanel>
        </div>
      </div>
    </div>
  );
}
