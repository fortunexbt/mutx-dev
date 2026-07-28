"use client";

import { useCallback, useEffect, useState } from "react";

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
  formatCurrency,
  formatDateTime,
  formatRelativeTime,
} from "@/components/dashboard/livePrimitives";

import type { components } from "@/app/types/api";

type Budget = components["schemas"]["BudgetResponse"];
type UsageBreakdown = components["schemas"]["UsageBreakdownResponse"];
type AnalyticsSummary = components["schemas"]["AnalyticsSummaryResponse"];
type UsageEvent = components["schemas"]["UsageEventResponse"];
type UsageEventList = components["schemas"]["UsageEventListResponse"];

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

const EVENTS_PAGE_SIZE = 12;
const secondaryButtonClass =
  "rounded-lg border border-white/10 bg-white/[0.04] px-3 py-2 text-xs font-medium text-slate-300 transition hover:border-white/20 hover:text-white disabled:cursor-not-allowed disabled:opacity-50";

function emptyResource<T>(): ResourceState<T> {
  return { data: null, error: null, stale: false };
}

function settleResource<T>(result: PromiseSettledResult<T>, fallback: string): SettledResource<T> {
  if (result.status === "fulfilled") return { data: result.value, authRequired: false, permissionDenied: false };
  const accessFailure = getDashboardRequestAccessFailure(result.reason);
  return {
    error: dashboardRequestErrorMessage(result.reason, fallback),
    authRequired: accessFailure === "authentication",
    permissionDenied: accessFailure === "permission",
  };
}

function mergeResource<T>(current: ResourceState<T>, next: SettledResource<T>): ResourceState<T> {
  if (next.data !== undefined) return { data: next.data, error: null, stale: false };
  return {
    data: current.data,
    error: next.error ?? "Request failed",
    stale: current.data !== null,
  };
}

export function resolveBudgetResources(
  results: [
    PromiseSettledResult<Budget>,
    PromiseSettledResult<UsageBreakdown>,
    PromiseSettledResult<AnalyticsSummary>,
    PromiseSettledResult<UsageEventList>,
  ],
) {
  return {
    budget: settleResource(results[0], "Failed to load budget envelope"),
    usage: settleResource(results[1], "Failed to load usage breakdown"),
    summary: settleResource(results[2], "Failed to load analytics summary"),
    events: settleResource(results[3], "Failed to load usage events"),
  };
}

export function BudgetsPageClient() {
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [authRequired, setAuthRequired] = useState(false);
  const [permissionDenied, setPermissionDenied] = useState(false);
  const [budgetState, setBudgetState] = useState<ResourceState<Budget>>(emptyResource);
  const [usageState, setUsageState] = useState<ResourceState<UsageBreakdown>>(emptyResource);
  const [summaryState, setSummaryState] = useState<ResourceState<AnalyticsSummary>>(emptyResource);
  const [eventsState, setEventsState] = useState<ResourceState<UsageEventList>>(emptyResource);
  const [lastUpdated, setLastUpdated] = useState<string | null>(null);

  const load = useCallback(async (initial = false) => {
    if (initial) setLoading(true);
    else setRefreshing(true);
    setAuthRequired(false);
    setPermissionDenied(false);

    const results = await Promise.allSettled([
      readJson<Budget>("/api/dashboard/budgets"),
      readJson<UsageBreakdown>("/api/dashboard/budgets/usage?period_start=30d"),
      readJson<AnalyticsSummary>("/api/dashboard/analytics/summary?period_start=30d"),
      readJson<UsageEventList>(`/api/dashboard/usage/events?skip=0&limit=${EVENTS_PAGE_SIZE}`),
    ]);
    const snapshot = resolveBudgetResources(results);

    if (
      snapshot.budget.permissionDenied ||
      snapshot.usage.permissionDenied ||
      snapshot.summary.permissionDenied ||
      snapshot.events.permissionDenied
    ) {
      setPermissionDenied(true);
    } else if (
      snapshot.budget.authRequired ||
      snapshot.usage.authRequired ||
      snapshot.summary.authRequired ||
      snapshot.events.authRequired
    ) {
      setAuthRequired(true);
    } else {
      setBudgetState((current) => mergeResource(current, snapshot.budget));
      setUsageState((current) => mergeResource(current, snapshot.usage));
      setSummaryState((current) => mergeResource(current, snapshot.summary));
      setEventsState((current) => mergeResource(current, snapshot.events));
      if (
        snapshot.budget.data ||
        snapshot.usage.data ||
        snapshot.summary.data ||
        snapshot.events.data
      ) {
        setLastUpdated(new Date().toISOString());
      }
    }
    setLoading(false);
    setRefreshing(false);
  }, []);

  useEffect(() => {
    void load(true);
  }, [load]);

  async function loadMoreEvents() {
    const currentEnvelope = eventsState.data;
    if (!currentEnvelope) return;
    setLoadingMore(true);
    try {
      const response = await readJson<UsageEventList>(
        `/api/dashboard/usage/events?skip=${currentEnvelope.items.length}&limit=${EVENTS_PAGE_SIZE}`,
      );
      setEventsState((current) => {
        const existing = current.data?.items ?? [];
        const known = new Set(existing.map((event) => event.id));
        return {
          data: {
            ...response,
            items: [...existing, ...response.items.filter((event) => !known.has(event.id))],
          },
          error: null,
          stale: false,
        };
      });
      setLastUpdated(new Date().toISOString());
    } catch (loadError) {
      const accessFailure = getDashboardRequestAccessFailure(loadError);
      if (accessFailure === "authentication") setAuthRequired(true);
      else if (accessFailure === "permission") setPermissionDenied(true);
      else {
        setEventsState((current) => ({
          ...current,
          error: dashboardRequestErrorMessage(loadError, "Failed to load more usage events"),
          stale: current.data !== null,
        }));
      }
    } finally {
      setLoadingMore(false);
    }
  }

  if (loading) return <LiveLoading title="Budgets" />;
  if (authRequired) {
    return (
      <LiveAuthRequired
        title="Operator session required"
        message="Sign in to inspect credit posture, usage breakdowns, and operator cost trends."
      />
    );
  }
  if (permissionDenied) {
    return <LiveForbidden title="Budget permission required" message="Your account cannot read budget or usage resources. Refresh and pagination controls are unavailable." />;
  }

  const budget = budgetState.data;
  const usage = usageState.data;
  const summary = summaryState.data;
  const eventEnvelope = eventsState.data;
  const events: UsageEvent[] = eventEnvelope?.items ?? [];
  const resourceIssues = [
    ["Budget", budgetState] as const,
    ["Usage breakdown", usageState] as const,
    ["Analytics summary", summaryState] as const,
    ["Usage events", eventsState] as const,
  ].filter((entry) => entry[1].error);

  const creditsRemaining = budget?.credits_remaining ?? usage?.credits_remaining;
  const creditsUsed = budget?.credits_used ?? usage?.total_credits_used;
  const creditsTotal = budget?.credits_total ?? usage?.credits_total;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-white/10 bg-white/[0.02] px-4 py-3">
        <div>
          <p className="text-sm font-medium text-white">Budget data snapshot</p>
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
          <p className="font-medium">Partial budget data</p>
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
          label="Credits remaining"
          value={creditsRemaining === undefined ? "Unavailable" : formatCurrency(creditsRemaining)}
          detail={
            budget
              ? `${budget.plan} plan with reset on ${new Date(budget.reset_date).toLocaleDateString()}.`
              : creditsTotal === undefined
                ? "Neither the budget envelope nor usage breakdown returned credit data."
                : `${formatCurrency(creditsTotal)} tracked in the usage envelope; plan reset metadata unavailable.`
          }
          status={
            budget
              ? asDashboardStatus(budget.usage_percentage >= 80 ? "warning" : "healthy")
              : creditsRemaining === undefined
                ? "error"
                : undefined
          }
        />
        <LiveStatCard
          label="Credits used"
          value={creditsUsed === undefined ? "Unavailable" : formatCurrency(creditsUsed)}
          detail={
            budget
              ? `${budget.usage_percentage}% of the current envelope has been consumed.`
              : usage
                ? `Usage captured from ${formatRelativeTime(usage.period_start)} through ${formatRelativeTime(usage.period_end)}.`
                : "Usage totals were not returned."
          }
        />
        <LiveStatCard
          label="API calls"
          value={summary ? summary.total_api_calls.toLocaleString() : "Unavailable"}
          detail={
            summary
              ? `${summary.total_runs.toLocaleString()} runs across ${summary.total_agents.toLocaleString()} agents in the current period.`
              : summaryState.error || "Analytics summary was not returned."
          }
          status={summary ? undefined : "error"}
        />
        <LiveStatCard
          label="Latency"
          value={
            summary?.avg_latency_ms == null
              ? "Unavailable"
              : `${Math.round(summary.avg_latency_ms)}ms`
          }
          detail={summary ? "Average latency reported over the selected window." : summaryState.error || "Latency was not returned."}
          status={
            !summary
              ? "error"
              : summary.avg_latency_ms === null
                ? asDashboardStatus("idle")
                : asDashboardStatus(summary.avg_latency_ms > 500 ? "warning" : "healthy")
          }
        />
      </LiveKpiGrid>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.15fr)_minmax(320px,0.85fr)]">
        <div className="grid gap-4">
          <LivePanel title="Usage by agent" meta={usage ? `${usage.usage_by_agent.length} agents` : "unavailable"}>
            {!usage ? (
              <LiveEmptyState title="Usage breakdown unavailable" message={usageState.error || "No usage breakdown was returned."} />
            ) : usage.usage_by_agent.length === 0 ? (
              <LiveEmptyState title="No billable agent usage yet" message="No agent-scoped usage exists in this period." />
            ) : (
              <div className="space-y-3">
                {usage.usage_by_agent.map((agent) => (
                  <div key={agent.agent_id} className="rounded-xl border border-white/10 bg-white/[0.02] p-4">
                    <div className="flex items-center justify-between gap-3">
                      <div className="min-w-0">
                        <p className="truncate text-sm font-medium text-white">{agent.agent_name}</p>
                        <p className="mt-1 text-xs text-slate-500">{agent.event_count} tracked events</p>
                      </div>
                      <p className="text-sm font-semibold text-white">{formatCurrency(agent.credits_used)}</p>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </LivePanel>

          <LivePanel title="Usage events" meta={eventEnvelope ? `${events.length} of ${eventEnvelope.total} rows` : "unavailable"}>
            {eventsState.error ? (
              <div role="alert" className="mb-4 rounded-xl border border-amber-400/20 bg-amber-400/10 px-4 py-3 text-sm text-amber-100">
                Usage events request failed: {eventsState.error}{eventsState.stale ? " Existing rows are stale." : ""}
              </div>
            ) : null}
            {!eventEnvelope ? (
              <LiveEmptyState title="Usage events unavailable" message="The event resource did not return data." />
            ) : events.length === 0 ? (
              <LiveEmptyState title="No usage events returned" message="No tracked usage events exist yet." />
            ) : (
              <div className="space-y-3">
                {events.map((event) => (
                  <div key={event.id} className="rounded-xl border border-white/10 bg-white/[0.02] p-4">
                    <div className="flex items-center justify-between gap-3">
                      <div>
                        <p className="text-sm font-medium text-white">{event.event_type}</p>
                        <p className="mt-1 text-xs text-slate-500">{event.resource_id || "no resource id"}</p>
                      </div>
                      <div className="text-right">
                        <p className="text-sm text-slate-300">{formatCurrency(event.credits_used)}</p>
                        <p className="mt-1 text-xs text-slate-500">{formatRelativeTime(event.created_at)}</p>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
            {eventEnvelope?.has_more ? (
              <div className="mt-4 flex justify-center border-t border-white/10 pt-4">
                <button className={secondaryButtonClass} onClick={() => void loadMoreEvents()} disabled={loadingMore}>
                  {loadingMore ? "Loading…" : `Load more (${events.length} of ${eventEnvelope.total})`}
                </button>
              </div>
            ) : null}
          </LivePanel>
        </div>

        <LivePanel title="Spend mix" meta={usage ? `${usage.usage_by_type.length} event types` : "unavailable"}>
          {!usage ? (
            <LiveEmptyState title="Spend mix unavailable" message={usageState.error || "No usage breakdown was returned."} />
          ) : usage.usage_by_type.length === 0 ? (
            <LiveEmptyState title="No spend mix yet" message="No usage event types exist in this period." />
          ) : (
            <div className="space-y-3">
              {usage.usage_by_type.map((item) => (
                <div key={item.event_type} className="rounded-xl border border-white/10 bg-white/[0.02] p-4">
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <p className="text-sm font-medium text-white">{item.event_type}</p>
                      <p className="mt-1 text-xs text-slate-500">{item.event_count} tracked events</p>
                    </div>
                    <p className="text-sm font-semibold text-white">{formatCurrency(item.credits_used)}</p>
                  </div>
                </div>
              ))}
            </div>
          )}
        </LivePanel>
      </div>
    </div>
  );
}
