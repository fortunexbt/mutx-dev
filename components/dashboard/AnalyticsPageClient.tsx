"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { readJson } from "@/components/app/http";
import {
  dashboardRequestErrorMessage,
  getDashboardRequestAccessFailure,
} from "@/components/dashboard/dashboardRequestAccess";
import {
  LiveAuthRequired,
  LiveEmptyState,
  LiveForbidden,
  LiveKpiGrid,
  LiveLoading,
  LivePanel,
  LiveStatCard,
  asDashboardStatus,
  formatDateTime,
} from "@/components/dashboard/livePrimitives";

import type { components } from "@/app/types/api";

type AnalyticsSummary = components["schemas"]["AnalyticsSummaryResponse"];
type AnalyticsTimeSeries = components["schemas"]["AnalyticsTimeSeries"];
type AnalyticsTimeSeriesResponse = components["schemas"]["AnalyticsTimeSeriesResponse"];
type CostSummary = components["schemas"]["CostSummaryResponse"];

type ResourceState<T> = {
  data: T | null;
  error: string | null;
  stale: boolean;
};

type SettledResource<T> = {
  data?: T;
  error?: string;
  authRequired: boolean;
  permissionDenied: boolean;
};

const ANALYTICS_WINDOW = "30d";
const ANALYTICS_INTERVAL = "day";
const secondaryButtonClass =
  "rounded-lg border border-white/10 bg-white/[0.04] px-3 py-2 text-xs font-medium text-slate-300 transition hover:border-white/20 hover:text-white disabled:cursor-not-allowed disabled:opacity-50";

function emptyResource<T>(): ResourceState<T> {
  return { data: null, error: null, stale: false };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function isNullableFiniteNumber(value: unknown): value is number | null {
  return value === null || (typeof value === "number" && Number.isFinite(value));
}

function isAnalyticsSummary(value: unknown): value is AnalyticsSummary {
  return (
    isRecord(value) &&
    typeof value.total_agents === "number" &&
    typeof value.active_agents === "number" &&
    typeof value.total_deployments === "number" &&
    typeof value.active_deployments === "number" &&
    typeof value.total_runs === "number" &&
    typeof value.successful_runs === "number" &&
    typeof value.failed_runs === "number" &&
    typeof value.total_api_calls === "number" &&
    isNullableFiniteNumber(value.avg_latency_ms) &&
    typeof value.period_start === "string" &&
    typeof value.period_end === "string"
  );
}

function isAnalyticsTimeSeriesResponse(value: unknown): value is AnalyticsTimeSeriesResponse {
  return (
    isRecord(value) &&
    typeof value.metric === "string" &&
    typeof value.interval === "string" &&
    Array.isArray(value.data) &&
    value.data.every(
      (point) =>
        isRecord(point) &&
        typeof point.timestamp === "string" &&
        isNullableFiniteNumber(point.value),
    ) &&
    typeof value.period_start === "string" &&
    typeof value.period_end === "string"
  );
}

function isCostSummary(value: unknown): value is CostSummary {
  return (
    isRecord(value) &&
    typeof value.total_credits_used === "number" &&
    typeof value.credits_remaining === "number" &&
    typeof value.credits_total === "number" &&
    isRecord(value.usage_by_event_type) &&
    isRecord(value.usage_by_agent) &&
    typeof value.period_start === "string" &&
    typeof value.period_end === "string"
  );
}

function settleValidated<T>(
  result: PromiseSettledResult<unknown>,
  validator: (value: unknown) => value is T,
  requestFallback: string,
  contractError: string,
): SettledResource<T> {
  if (result.status === "rejected") {
    const accessFailure = getDashboardRequestAccessFailure(result.reason);
    return {
      error: dashboardRequestErrorMessage(result.reason, requestFallback),
      authRequired: accessFailure === "authentication",
      permissionDenied: accessFailure === "permission",
    };
  }
  if (!validator(result.value)) return { error: contractError, authRequired: false, permissionDenied: false };
  return { data: result.value, authRequired: false, permissionDenied: false };
}

function mergeResource<T>(current: ResourceState<T>, next: SettledResource<T>): ResourceState<T> {
  if (next.data !== undefined) return { data: next.data, error: null, stale: false };
  return {
    data: current.data,
    error: next.error ?? "Request failed",
    stale: current.data !== null,
  };
}

export function resolveAnalyticsResources(
  results: [
    PromiseSettledResult<unknown>,
    PromiseSettledResult<unknown>,
    PromiseSettledResult<unknown>,
    PromiseSettledResult<unknown>,
  ],
) {
  return {
    summary: settleValidated(
      results[0],
      isAnalyticsSummary,
      "Failed to load analytics summary",
      "Analytics summary payload did not match the expected contract.",
    ),
    runTrend: settleValidated(
      results[1],
      isAnalyticsTimeSeriesResponse,
      "Failed to load run trend",
      "Run trend payload did not match the expected contract.",
    ),
    latencyTrend: settleValidated(
      results[2],
      isAnalyticsTimeSeriesResponse,
      "Failed to load latency trend",
      "Latency trend payload did not match the expected contract.",
    ),
    costs: settleValidated(
      results[3],
      isCostSummary,
      "Failed to load analytics costs",
      "Analytics cost payload did not match the expected contract.",
    ),
  };
}

function formatShortDate(value: string) {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function formatValue(value: number, kind: "count" | "latency") {
  if (kind === "latency") return `${Math.round(value)}ms`;
  return Math.round(value).toLocaleString();
}

function rankUsage(values: Record<string, number> | undefined) {
  return Object.entries(values ?? {}).sort((left, right) => right[1] - left[1]);
}

function TrendStrip({
  title,
  description,
  data,
  kind,
  error,
  stale,
}: {
  title: string;
  description: string;
  data: AnalyticsTimeSeries[];
  kind: "count" | "latency";
  error?: string | null;
  stale?: boolean;
}) {
  if (data.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-white/10 bg-white/[0.02] p-4">
        <p className="text-sm font-medium text-white">{title}</p>
        <p className="mt-2 text-sm text-slate-400">{description}</p>
        <p
          role={error ? "alert" : undefined}
          aria-live={error ? "assertive" : undefined}
          className={`mt-3 text-xs ${error ? "text-amber-200" : "text-slate-500"}`}
        >
          {error ? `Unavailable: ${error}` : "No trend samples returned for this metric yet."}
        </p>
      </div>
    );
  }

  const samples = data.slice(-7);
  const peak = Math.max(
    ...samples.flatMap((point) => (point.value === null ? [] : [point.value])),
    1,
  );

  return (
    <div className="rounded-xl border border-white/10 bg-white/[0.02] p-4">
      <div className="flex items-center justify-between gap-3">
        <p className="text-sm font-medium text-white">{title}</p>
        {stale ? <span className="text-[10px] uppercase tracking-[0.16em] text-amber-200">stale</span> : null}
      </div>
      <p className="mt-2 text-sm text-slate-400">{description}</p>
      {error ? (
        <p role="alert" aria-live="assertive" className="mt-2 text-xs text-amber-200">
          Refresh failed: {error}
        </p>
      ) : null}
      <div className="mt-4 space-y-3">
        {samples.map((point) => {
          const width = point.value === null ? 0 : Math.max((point.value / peak) * 100, 6);
          return (
            <div key={`${title}-${point.timestamp}`} className="space-y-1.5">
              <div className="flex items-center justify-between gap-3 text-xs text-slate-500">
                <span>{formatShortDate(point.timestamp)}</span>
                <span>{point.value === null ? "Unavailable" : formatValue(point.value, kind)}</span>
              </div>
              <div className="h-2 rounded-full bg-white/[0.05]">
                <div className="h-2 rounded-full bg-cyan-400/80" style={{ width: `${width}%` }} />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export function AnalyticsPageClient() {
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [authRequired, setAuthRequired] = useState(false);
  const [permissionDenied, setPermissionDenied] = useState(false);
  const [summaryState, setSummaryState] = useState<ResourceState<AnalyticsSummary>>(emptyResource);
  const [runTrendState, setRunTrendState] = useState<ResourceState<AnalyticsTimeSeriesResponse>>(emptyResource);
  const [latencyTrendState, setLatencyTrendState] = useState<ResourceState<AnalyticsTimeSeriesResponse>>(emptyResource);
  const [costState, setCostState] = useState<ResourceState<CostSummary>>(emptyResource);
  const [lastUpdated, setLastUpdated] = useState<string | null>(null);

  const load = useCallback(async (initial = false) => {
    if (initial) setLoading(true);
    else setRefreshing(true);
    setAuthRequired(false);
    setPermissionDenied(false);

    const results = await Promise.allSettled([
      readJson<unknown>(`/api/dashboard/analytics/summary?period_start=${ANALYTICS_WINDOW}`),
      readJson<unknown>(
        `/api/dashboard/analytics/timeseries?metric=runs&period_start=${ANALYTICS_WINDOW}&interval=${ANALYTICS_INTERVAL}`,
      ),
      readJson<unknown>(
        `/api/dashboard/analytics/timeseries?metric=latency&period_start=${ANALYTICS_WINDOW}&interval=${ANALYTICS_INTERVAL}`,
      ),
      readJson<unknown>(`/api/dashboard/analytics/costs?period_start=${ANALYTICS_WINDOW}`),
    ]);
    const snapshot = resolveAnalyticsResources(results);

    if (
      snapshot.summary.permissionDenied ||
      snapshot.runTrend.permissionDenied ||
      snapshot.latencyTrend.permissionDenied ||
      snapshot.costs.permissionDenied
    ) {
      setPermissionDenied(true);
    } else if (
      snapshot.summary.authRequired ||
      snapshot.runTrend.authRequired ||
      snapshot.latencyTrend.authRequired ||
      snapshot.costs.authRequired
    ) {
      setAuthRequired(true);
    } else {
      setSummaryState((current) => mergeResource(current, snapshot.summary));
      setRunTrendState((current) => mergeResource(current, snapshot.runTrend));
      setLatencyTrendState((current) => mergeResource(current, snapshot.latencyTrend));
      setCostState((current) => mergeResource(current, snapshot.costs));
      if (snapshot.summary.data || snapshot.runTrend.data || snapshot.latencyTrend.data || snapshot.costs.data) {
        setLastUpdated(new Date().toISOString());
      }
    }
    setLoading(false);
    setRefreshing(false);
  }, []);

  useEffect(() => {
    void load(true);
  }, [load]);

  const summary = summaryState.data;
  const runTrend = runTrendState.data;
  const latencyTrend = latencyTrendState.data;
  const costs = costState.data;
  const successRate = useMemo(() => {
    if (!summary) return null;
    if (summary.total_runs === 0) return 0;
    return Math.round((summary.successful_runs / summary.total_runs) * 100);
  }, [summary]);
  const eventMix = useMemo(
    () => rankUsage(costs?.usage_by_event_type as Record<string, number> | undefined),
    [costs],
  );
  const resourceMix = useMemo(
    () => rankUsage(costs?.usage_by_agent as Record<string, number> | undefined),
    [costs],
  );

  if (loading) return <LiveLoading title="Analytics" />;
  if (authRequired) {
    return (
      <LiveAuthRequired
        title="Operator session required"
        message="Sign in to inspect trend data, latency posture, and usage analytics."
      />
    );
  }
  if (permissionDenied) {
    return <LiveForbidden title="Analytics permission required" message="Your account cannot read usage analytics. Refresh and trend controls are unavailable." />;
  }

  const resourceIssues = [
    ["Summary", summaryState] as const,
    ["Run trend", runTrendState] as const,
    ["Latency trend", latencyTrendState] as const,
    ["Costs", costState] as const,
  ].filter((entry) => entry[1].error);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-white/10 bg-white/[0.02] px-4 py-3">
        <div>
          <p className="text-sm font-medium text-white">Analytics data snapshot</p>
          <p className="mt-1 text-xs text-slate-500">
            {lastUpdated ? `Last successful resource update ${formatDateTime(lastUpdated)}` : "No resource has loaded successfully yet."}
          </p>
        </div>
        <button className={secondaryButtonClass} onClick={() => void load(false)} disabled={refreshing}>
          {refreshing ? "Refreshing…" : "Refresh"}
        </button>
      </div>

      {resourceIssues.length > 0 ? (
        <div role="alert" aria-live="assertive" className="rounded-xl border border-amber-400/20 bg-amber-400/10 px-4 py-3 text-sm text-amber-100">
          <p className="font-medium">Partial analytics data</p>
          <ul className="mt-2 space-y-1 text-xs text-amber-100/80">
            {resourceIssues.map(([label, state]) => (
              <li key={label}>
                {label}: {state.error}{state.stale ? " — showing previously loaded data (stale)." : " — unavailable."}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      <LiveKpiGrid>
        <LiveStatCard
          label="Success rate"
          value={successRate === null ? "Unavailable" : `${successRate}%`}
          detail={summary ? `${summary.successful_runs} successful runs vs ${summary.failed_runs} failed.` : summaryState.error || "Summary was not returned."}
          status={summary ? asDashboardStatus(summary.failed_runs > 0 ? "warning" : "healthy") : "error"}
        />
        <LiveStatCard
          label="Active agents"
          value={summary ? `${summary.active_agents}/${summary.total_agents}` : "Unavailable"}
          detail={summary ? `${summary.active_deployments} active deployments across ${summary.total_deployments} total.` : summaryState.error || "Summary was not returned."}
          status={summary ? asDashboardStatus(summary.active_agents > 0 ? "healthy" : "idle") : "error"}
        />
        <LiveStatCard
          label="API calls"
          value={summary ? summary.total_api_calls.toLocaleString() : "Unavailable"}
          detail={summary ? `${summary.total_runs.toLocaleString()} runs were recorded in this period.` : summaryState.error || "Summary was not returned."}
          status={summary ? undefined : "error"}
        />
        <LiveStatCard
          label="Avg latency"
          value={
            summary?.avg_latency_ms == null
              ? "Unavailable"
              : `${Math.round(summary.avg_latency_ms)}ms`
          }
          detail={costs ? `${Math.round(costs.total_credits_used).toLocaleString()} tracked credits in the same window.` : costState.error || "Tracked credits were not returned."}
          status={
            !summary
              ? "error"
              : summary.avg_latency_ms === null
                ? asDashboardStatus("idle")
                : asDashboardStatus(summary.avg_latency_ms > 500 ? "warning" : "healthy")
          }
        />
      </LiveKpiGrid>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.1fr)_minmax(340px,0.9fr)]">
        <div className="space-y-4">
          <LivePanel title="Trend lane" meta="30d window">
            <div className="grid gap-4 lg:grid-cols-2">
              <TrendStrip
                title="Run volume"
                description="Daily run counts from the analytics timeseries endpoint."
                data={runTrend?.data ?? []}
                kind="count"
                error={runTrendState.error}
                stale={runTrendState.stale}
              />
              <TrendStrip
                title="Latency"
                description="Daily latency averages returned by analytics."
                data={latencyTrend?.data ?? []}
                kind="latency"
                error={latencyTrendState.error}
                stale={latencyTrendState.stale}
              />
            </div>
          </LivePanel>

          <LivePanel title="Analytics snapshot" meta={summaryState.stale ? "stale" : "current period"}>
            {!summary ? (
              <LiveEmptyState title="Analytics summary unavailable" message={summaryState.error || "No summary payload was returned."} />
            ) : (
              <div className="grid gap-3 sm:grid-cols-2">
                {[
                  { label: "Period start", value: formatShortDate(summary.period_start) },
                  { label: "Period end", value: formatShortDate(summary.period_end) },
                  { label: "Total deployments", value: summary.total_deployments.toLocaleString() },
                  { label: "Failed runs", value: summary.failed_runs.toLocaleString() },
                ].map((item) => (
                  <div key={item.label} className="rounded-xl border border-white/10 bg-white/[0.02] p-4">
                    <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-500">{item.label}</p>
                    <p className="mt-2 text-lg font-semibold text-white">{item.value}</p>
                  </div>
                ))}
              </div>
            )}
          </LivePanel>
        </div>

        <LivePanel title="Cost profile" meta={costState.stale ? "stale" : costs ? "analytics costs" : "unavailable"}>
          {!costs ? (
            <LiveEmptyState title="Cost profile unavailable" message={costState.error || "No tracked credit payload was returned."} />
          ) : (
            <div className="space-y-4">
              {costState.error ? <p className="text-xs text-amber-200">Refresh failed: {costState.error}</p> : null}
              <div className="rounded-xl border border-white/10 bg-white/[0.02] p-4">
                <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-500">Credit envelope</p>
                <p className="mt-2 text-lg font-semibold text-white">{Math.round(costs.total_credits_used).toLocaleString()} used</p>
                <p className="mt-1 text-sm text-slate-400">
                  {Math.round(costs.credits_remaining).toLocaleString()} remaining out of {Math.round(costs.credits_total).toLocaleString()} tracked credits.
                </p>
              </div>

              <div className="space-y-3">
                <div>
                  <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-500">By event type</p>
                  <div className="mt-2 space-y-2">
                    {eventMix.length === 0 ? (
                      <p className="text-sm text-slate-400">No event-type breakdown returned.</p>
                    ) : eventMix.map(([label, value]) => (
                      <div key={label} className="flex items-center justify-between gap-3 rounded-xl border border-white/10 bg-black/20 px-3 py-2.5">
                        <span className="truncate text-sm text-white">{label}</span>
                        <span className="text-xs text-slate-400">{Math.round(value).toLocaleString()}</span>
                      </div>
                    ))}
                  </div>
                </div>

                <div>
                  <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-500">By resource</p>
                  <div className="mt-2 space-y-2">
                    {resourceMix.length === 0 ? (
                      <p className="text-sm text-slate-400">No resource breakdown returned.</p>
                    ) : resourceMix.map(([label, value]) => (
                      <div key={label} className="flex items-center justify-between gap-3 rounded-xl border border-white/10 bg-black/20 px-3 py-2.5">
                        <span className="truncate font-mono text-xs text-white">{label}</span>
                        <span className="text-xs text-slate-400">{Math.round(value).toLocaleString()}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          )}
        </LivePanel>
      </div>
    </div>
  );
}
