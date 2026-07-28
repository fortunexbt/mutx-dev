"use client";

import { useCallback, useEffect, useState } from "react";

import { readJson, writeJson } from "@/components/app/http";
import {
  dashboardRequestErrorMessage,
  getDashboardRequestAccessFailure,
} from "@/components/dashboard/dashboardRequestAccess";
import { DashboardDialog } from "@/components/dashboard/DashboardDialog";
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
  formatRelativeTime,
} from "@/components/dashboard/livePrimitives";
import { StatusBadge } from "@/components/dashboard/StatusBadge";

import type { components } from "@/app/types/api";

type Alert = components["schemas"]["AlertResponse"];
type AlertList = components["schemas"]["AlertListResponse"];
type PendingAlertAction = {
  alert: Alert;
  resolved: boolean;
};

const PAGE_SIZE = 16;
const secondaryButtonClass =
  "min-h-11 rounded-lg border border-white/10 bg-white/[0.04] px-3 py-2 text-xs font-medium text-slate-300 transition hover:border-white/20 hover:text-white disabled:cursor-not-allowed disabled:opacity-50";
const primaryButtonClass =
  "min-h-11 rounded-lg border border-cyan-400/30 bg-cyan-400/10 px-3 py-2 text-xs font-semibold text-cyan-100 transition hover:border-cyan-300/50 disabled:cursor-not-allowed disabled:opacity-50";

export function MonitoringPageClient() {
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [authRequired, setAuthRequired] = useState(false);
  const [permissionDenied, setPermissionDenied] = useState(false);
  const [alertsError, setAlertsError] = useState<string | null>(null);
  const [healthError, setHealthError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionNotice, setActionNotice] = useState<string | null>(null);
  const [actingId, setActingId] = useState<string | null>(null);
  const [pendingAction, setPendingAction] = useState<PendingAlertAction | null>(null);
  const [dialogError, setDialogError] = useState<string | null>(null);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [total, setTotal] = useState(0);
  const [unresolvedCount, setUnresolvedCount] = useState<number | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const [health, setHealth] = useState<Record<string, unknown> | null>(null);
  const [lastUpdated, setLastUpdated] = useState<string | null>(null);

  const load = useCallback(async (initial = false) => {
    if (initial) setLoading(true);
    else setRefreshing(true);
    setAuthRequired(false);
    setPermissionDenied(false);
    setAlertsError(null);
    setHealthError(null);

    const [alertsResult, healthResult] = await Promise.allSettled([
      readJson<AlertList>(`/api/dashboard/monitoring/alerts?skip=0&limit=${PAGE_SIZE}`),
      readJson<Record<string, unknown>>("/api/dashboard/health"),
    ]);

    const failures = [alertsResult, healthResult]
      .filter((result): result is PromiseRejectedResult => result.status === "rejected")
      .map((result) => getDashboardRequestAccessFailure(result.reason));

    if (failures.includes("permission")) {
      setPermissionDenied(true);
    } else if (failures.includes("authentication")) {
      setAuthRequired(true);
    } else if (alertsResult.status === "fulfilled") {
      setAlerts(alertsResult.value.items ?? []);
      setTotal(alertsResult.value.total);
      setUnresolvedCount(alertsResult.value.unresolved_count);
      setHasMore(alertsResult.value.has_more);
    } else {
      setAlertsError(dashboardRequestErrorMessage(alertsResult.reason, "Failed to load alerts"));
    }

    if (healthResult.status === "fulfilled") {
      setHealth(healthResult.value);
    } else {
      setHealthError(dashboardRequestErrorMessage(healthResult.reason, "Failed to load control-plane health"));
    }

    if (alertsResult.status === "fulfilled" || healthResult.status === "fulfilled") {
      setLastUpdated(new Date().toISOString());
    }
    setLoading(false);
    setRefreshing(false);
  }, []);

  useEffect(() => {
    void load(true);
  }, [load]);

  async function loadMore() {
    setLoadingMore(true);
    setAlertsError(null);
    try {
      const response = await readJson<AlertList>(
        `/api/dashboard/monitoring/alerts?skip=${alerts.length}&limit=${PAGE_SIZE}`,
      );
      setAlerts((current) => {
        const known = new Set(current.map((alert) => alert.id));
        return [...current, ...response.items.filter((alert) => !known.has(alert.id))];
      });
      setTotal(response.total);
      setUnresolvedCount(response.unresolved_count);
      setHasMore(response.has_more);
      setLastUpdated(new Date().toISOString());
    } catch (loadError) {
      const accessFailure = getDashboardRequestAccessFailure(loadError);
      if (accessFailure === "authentication") setAuthRequired(true);
      else if (accessFailure === "permission") setPermissionDenied(true);
      else setAlertsError(dashboardRequestErrorMessage(loadError, "Failed to load more alerts"));
    } finally {
      setLoadingMore(false);
    }
  }

  function requestAlertAction(alert: Alert, resolved: boolean) {
    if (actingId) return;
    setActionError(null);
    setActionNotice(null);
    setDialogError(null);
    setPendingAction({ alert, resolved });
  }

  async function setAlertResolved() {
    if (!pendingAction || actingId) return;

    const { alert, resolved } = pendingAction;
    const verb = resolved ? "Resolve" : "Reopen";

    setActingId(alert.id);
    setActionError(null);
    setActionNotice(null);
    setDialogError(null);
    try {
      await writeJson<Alert>(`/api/dashboard/monitoring/alerts/${encodeURIComponent(alert.id)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ resolved }),
      });
      setActionNotice(
        `${resolved ? "Resolved" : "Reopened"} ${alert.type.replaceAll("_", " ")} alert ${alert.id}.`,
      );
      await load(false);
      setPendingAction(null);
    } catch (mutationError) {
      const accessFailure = getDashboardRequestAccessFailure(mutationError);
      if (accessFailure === "authentication") setAuthRequired(true);
      else if (accessFailure === "permission") setPermissionDenied(true);
      else {
        const message = dashboardRequestErrorMessage(
          mutationError,
          `Failed to ${verb.toLowerCase()} alert`,
        );
        setActionError(message);
        setDialogError(message);
      }
    } finally {
      setActingId(null);
    }
  }

  const healthStatus = typeof health?.status === "string" ? health.status : null;
  const databaseStatus = typeof health?.database === "string" ? health.database : null;
  const healthTimestamp = typeof health?.timestamp === "string" ? health.timestamp : null;
  const pendingVerb = pendingAction?.resolved ? "Resolve" : "Reopen";
  const pendingProgress = pendingAction?.resolved ? "Resolving…" : "Reopening…";

  if (loading) return <LiveLoading title="Monitoring" />;
  if (authRequired) {
    return (
      <LiveAuthRequired
        title="Operator session required"
        message="Sign in to inspect live health, paginated alerts, and resolution controls."
      />
    );
  }
  if (permissionDenied) {
    return <LiveForbidden title="Monitoring permission required" message="Your account cannot read or resolve monitoring alerts. Refresh, pagination, and resolution controls are unavailable." />;
  }

  return (
    <div className="space-y-4">
      <DashboardDialog
        open={Boolean(pendingAction)}
        onOpenChange={(open) => {
          if (!open && !actingId) {
            setPendingAction(null);
            setDialogError(null);
          }
        }}
        title={`${pendingVerb} alert`}
        description={
          pendingAction?.resolved
            ? "Move this alert out of the open monitoring queue."
            : "Return this alert to the open monitoring queue for operator follow-up."
        }
        footer={
          <>
            <button
              type="button"
              data-autofocus
              onClick={() => {
                setPendingAction(null);
                setDialogError(null);
              }}
              disabled={Boolean(actingId)}
              className={`${secondaryButtonClass} w-full text-sm sm:w-auto`}
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={() => void setAlertResolved()}
              disabled={Boolean(actingId)}
              className={`${primaryButtonClass} w-full text-sm sm:w-auto`}
            >
              {actingId ? pendingProgress : `${pendingVerb} Alert`}
            </button>
          </>
        }
      >
        <div aria-busy={Boolean(actingId)} className="space-y-4 text-start">
          <div className="rounded-xl border border-white/10 bg-black/20 p-3">
            <p className="text-sm font-semibold text-white">
              {pendingAction?.alert.type.replaceAll("_", " ")}
            </p>
            <p className="mt-1 text-sm text-slate-300">{pendingAction?.alert.message}</p>
            <p dir="ltr" className="mt-2 break-all text-start font-mono text-xs text-slate-500">
              Alert {pendingAction?.alert.id} · agent {pendingAction?.alert.agent_id}
            </p>
          </div>
          {pendingAction?.resolved ? (
            <p className="text-sm leading-6 text-slate-300">
              Resolving changes the monitoring workflow state; it does not remediate the underlying condition.
            </p>
          ) : null}
          {dialogError ? (
            <div role="alert" className="rounded-xl border border-rose-400/20 bg-rose-400/10 px-4 py-3 text-sm text-rose-200">
              Alert action failed: {dialogError}
            </div>
          ) : null}
        </div>
      </DashboardDialog>

      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-white/10 bg-white/[0.02] px-4 py-3">
        <div>
          <p className="text-sm font-medium text-white">Live monitoring snapshot</p>
          <p className="mt-1 text-xs text-slate-500">
            {lastUpdated ? `Last updated ${formatDateTime(lastUpdated)} (${formatRelativeTime(lastUpdated)})` : "No successful refresh yet."}
          </p>
        </div>
        <button className={primaryButtonClass} onClick={() => void load(false)} disabled={refreshing}>
          {refreshing ? "Refreshing…" : "Refresh now"}
        </button>
      </div>

      {actionError && !pendingAction ? (
        <div role="alert" className="rounded-xl border border-rose-400/20 bg-rose-400/10 px-4 py-3 text-sm text-rose-200">
          Alert action failed: {actionError}
        </div>
      ) : null}
      {actionNotice ? (
        <div role="status" aria-live="polite" aria-atomic="true" className="rounded-xl border border-emerald-400/20 bg-emerald-400/10 px-4 py-3 text-sm text-emerald-200">
          {actionNotice}
        </div>
      ) : null}

      <LiveKpiGrid>
        <LiveStatCard
          label="System status"
          value={healthStatus ?? "Unavailable"}
          detail={
            healthError
              ? `Health request failed: ${healthError}`
              : `Database ${databaseStatus ?? "not reported"}${healthTimestamp ? ` · checked ${formatRelativeTime(healthTimestamp)}` : ""}`
          }
          status={healthStatus ? asDashboardStatus(healthStatus) : "error"}
        />
        <LiveStatCard
          label="Open alerts"
          value={unresolvedCount === null ? "Unavailable" : String(unresolvedCount)}
          detail={alertsError ? `Alert request failed: ${alertsError}` : `${total} total alerts in the current result set.`}
          status={unresolvedCount === null ? "error" : asDashboardStatus(unresolvedCount > 0 ? "warning" : "healthy")}
        />
      </LiveKpiGrid>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.2fr)_minmax(320px,0.8fr)]">
        <LivePanel title="Alert rail" meta={`${alerts.length} of ${total} records`}>
          {alertsError ? (
            <div role="alert" className="mb-4 rounded-xl border border-rose-400/20 bg-rose-400/10 px-4 py-3 text-sm text-rose-200">
              Alerts unavailable: {alertsError}. Previously loaded rows remain visible.
            </div>
          ) : null}
          {alerts.length === 0 && !alertsError ? (
            <LiveEmptyState
              title="No alerts"
              message="Quota, deployment, and runtime failures will appear here when triggered."
            />
          ) : (
            <div className="space-y-3">
              {alerts.map((alert) => (
                <div key={alert.id} className="rounded-xl border border-white/10 bg-white/[0.02] p-4">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-white">{alert.type.replaceAll("_", " ")}</p>
                      <p className="mt-1 text-sm text-slate-400">{alert.message}</p>
                    </div>
                    <StatusBadge status={alert.resolved ? "success" : "warning"} label={alert.resolved ? "resolved" : "open"} />
                  </div>
                  <div className="mt-3 flex flex-wrap gap-3 text-xs text-slate-500">
                    <span>{formatRelativeTime(alert.created_at)}</span>
                    <span>{formatDateTime(alert.created_at)}</span>
                    <span>agent {alert.agent_id.slice(0, 8)}</span>
                    {alert.resolved_at ? <span>resolved {formatRelativeTime(alert.resolved_at)}</span> : null}
                  </div>
                  <div className="mt-4 border-t border-white/10 pt-3">
                    <button
                      className={secondaryButtonClass}
                      onClick={() => requestAlertAction(alert, !alert.resolved)}
                      disabled={actingId === alert.id}
                    >
                      {actingId === alert.id ? "Updating…" : alert.resolved ? "Reopen alert" : "Resolve alert"}
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
          {hasMore ? (
            <div className="mt-4 flex justify-center border-t border-white/10 pt-4">
              <button className={secondaryButtonClass} onClick={() => void loadMore()} disabled={loadingMore}>
                {loadingMore ? "Loading…" : `Load more (${alerts.length} of ${total})`}
              </button>
            </div>
          ) : null}
        </LivePanel>

        <LivePanel title="Health snapshot" meta="control plane">
          {healthError ? (
            <div role="alert" className="rounded-xl border border-rose-400/20 bg-rose-400/10 px-4 py-3 text-sm text-rose-200">
              Health unavailable: {healthError}. Alert data is loaded independently.
            </div>
          ) : health ? (
            <div className="space-y-3">
              <div className="rounded-xl border border-white/10 bg-white/[0.02] p-4">
                <div className="flex items-center justify-between gap-3">
                  <span className="text-sm text-slate-400">Status</span>
                  <StatusBadge status={asDashboardStatus(healthStatus)} label={healthStatus ?? "unknown"} />
                </div>
              </div>
              <div className="rounded-xl border border-white/10 bg-white/[0.02] p-4">
                <div className="flex items-center justify-between gap-3">
                  <span className="text-sm text-slate-400">Database</span>
                  <StatusBadge status={asDashboardStatus(databaseStatus)} label={databaseStatus ?? "unknown"} />
                </div>
              </div>
              {typeof health.uptime_seconds === "number" ? (
                <div className="rounded-xl border border-white/10 bg-white/[0.02] p-4 text-sm text-slate-400">
                  Uptime {Math.round(health.uptime_seconds).toLocaleString()} seconds
                </div>
              ) : null}
            </div>
          ) : (
            <LiveEmptyState title="No health snapshot" message="No successful health response has been recorded yet." />
          )}
        </LivePanel>
      </div>
    </div>
  );
}
