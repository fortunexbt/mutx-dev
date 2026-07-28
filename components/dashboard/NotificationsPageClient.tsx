"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { BellRing, ShieldAlert, Webhook } from "lucide-react";

import { readJson } from "@/components/app/http";
import { getDashboardRequestAccessFailure } from "@/components/dashboard/dashboardRequestAccess";
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

type DashboardStatus = "idle" | "running" | "success" | "warning" | "error";
type AggregateSourceStatus =
  | "ok"
  | "partial"
  | "unauthenticated"
  | "forbidden"
  | "error";

type NotificationItem = {
  id: string;
  kind: "alert" | "approval" | "webhook" | "governance" | "runtime";
  title: string;
  detail: string;
  status: DashboardStatus;
  createdAt: string | null;
  source: string;
  href: string | null;
  meta: string | null;
};

type NotificationsPayload = {
  generatedAt: string;
  summary: {
    alerts: number | null;
    approvals: number | null;
    webhookFailures: number | null;
    runtimeIncidents: number | null;
    governancePendingApprovals: number | null;
  };
  sources: {
    alerts: AggregateSourceStatus;
    approvals: AggregateSourceStatus;
    webhooks: AggregateSourceStatus;
    runtime: AggregateSourceStatus;
    governance: AggregateSourceStatus;
  };
  items: NotificationItem[];
  partials: string[];
};

function safeNotificationHref(href: string | null) {
  if (!href?.startsWith("/")) return null;

  try {
    const parsed = new URL(href, "https://mutx.local");
    if (
      parsed.origin === "https://mutx.local" &&
      (parsed.pathname === "/dashboard" || parsed.pathname.startsWith("/dashboard/"))
    ) {
      return `${parsed.pathname}${parsed.search}${parsed.hash}`;
    }
  } catch {
    return null;
  }

  return null;
}

export function NotificationsPageClient() {
  const [loading, setLoading] = useState(true);
  const [authRequired, setAuthRequired] = useState(false);
  const [permissionDenied, setPermissionDenied] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [payload, setPayload] = useState<NotificationsPayload | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setLoading(true);
      setAuthRequired(false);
      setPermissionDenied(false);
      setError(null);

      try {
        const response = await readJson<NotificationsPayload>("/api/dashboard/notifications");
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
              loadError instanceof Error ? loadError.message : "Failed to load notifications",
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

  const counts = useMemo(() => {
    const items = payload?.items ?? [];
    return {
      alerts: items.filter((item) => item.kind === "alert").length,
      approvals: items.filter((item) => item.kind === "approval").length,
      runtime: items.filter((item) => item.kind === "runtime").length,
      governance: items.filter((item) => item.kind === "governance").length,
      webhooks: items.filter((item) => item.kind === "webhook").length,
    };
  }, [payload]);

  const inboxCoverageComplete = payload
    ? [
        payload.sources.alerts,
        payload.sources.approvals,
        payload.sources.webhooks,
        payload.sources.runtime,
      ].every((status) => status === "ok")
    : false;

  if (loading) return <LiveLoading title="Notifications" />;
  if (authRequired) {
    return (
      <LiveAuthRequired
        title="Operator session required"
        message="Sign in to inspect alerts, approvals, webhook failures, and runtime incidents."
      />
    );
  }
  if (permissionDenied) {
    return (
      <LiveForbidden
        title="Notification permission required"
        message="Your account cannot inspect this workspace notification feed. Notification destinations and operator actions are unavailable."
      />
    );
  }
  if (error) return <LiveErrorState title="Notification feed unavailable" message={error} />;
  if (!payload) {
    return (
      <LiveErrorState
        title="Notification feed unavailable"
        message="No notification payload was returned by the dashboard proxy."
      />
    );
  }

  return (
    <div className="space-y-4">
      <LiveKpiGrid>
        <LiveStatCard
          label="Alerts"
          value={payload.summary.alerts === null ? "Unknown" : String(payload.summary.alerts)}
          detail="Open monitoring alerts sampled into the signal inbox."
          status={
            payload.summary.alerts === null
              ? "idle"
              : payload.summary.alerts > 0
                ? "error"
                : "success"
          }
        />
        <LiveStatCard
          label="Approvals"
          value={
            payload.summary.approvals === null ? "Unknown" : String(payload.summary.approvals)
          }
          detail="Pending approval requests still waiting on review."
          status={
            payload.summary.approvals === null
              ? "idle"
              : payload.summary.approvals > 0
                ? "warning"
                : "success"
          }
        />
        <LiveStatCard
          label="Webhook failures"
          value={
            payload.summary.webhookFailures === null
              ? "Unknown"
              : String(payload.summary.webhookFailures)
          }
          detail="Recent failing delivery attempts across active webhook routes."
          status={
            payload.summary.webhookFailures === null
              ? "idle"
              : payload.summary.webhookFailures > 0
                ? "error"
                : "success"
          }
        />
        <LiveStatCard
          label="Runtime incidents"
          value={
            payload.summary.runtimeIncidents === null
              ? "Unknown"
              : String(payload.summary.runtimeIncidents)
          }
          detail="Supervised runtime incidents surfaced by the governance layer when available."
          status={
            payload.summary.runtimeIncidents === null
              ? "idle"
              : payload.summary.runtimeIncidents > 0
                ? "error"
                : "success"
          }
        />
        <LiveStatCard
          label="Governance pending"
          value={
            payload.summary.governancePendingApprovals === null
              ? "partial"
              : String(payload.summary.governancePendingApprovals)
          }
          detail="Decision-by-decision governance events are not exposed yet, so this route shows runtime status summaries."
          status={
            payload.summary.governancePendingApprovals && payload.summary.governancePendingApprovals > 0
              ? "warning"
              : payload.summary.governancePendingApprovals === null
                ? "idle"
                : "success"
          }
        />
      </LiveKpiGrid>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.2fr)_minmax(320px,0.8fr)]">
        <LivePanel title="Operator inbox" meta={`${payload.items.length} signals`}>
          {payload.items.length === 0 ? (
            <LiveEmptyState
              title={inboxCoverageComplete ? "Inbox is clear" : "Inbox coverage is incomplete"}
              message={
                inboxCoverageComplete
                  ? "No alert, approval, webhook, or runtime signals are demanding operator attention right now."
                  : "One or more signal sources are unavailable, so the dashboard cannot confirm that the inbox is clear."
              }
            />
          ) : (
            <div className="space-y-3">
              {payload.items.map((item) => {
                const destination = safeNotificationHref(item.href);

                return (
                  <div
                    key={item.id}
                    className="rounded-2xl border border-white/10 bg-white/[0.03] p-4"
                  >
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="text-sm font-medium text-white">{item.title}</p>
                        <p className="mt-1 text-sm text-slate-400">{item.detail}</p>
                      </div>
                      <StatusBadge status={item.status} label={item.kind} />
                    </div>

                    <div className="mt-3 flex flex-wrap gap-2 text-xs text-slate-500">
                      <span>{item.source}</span>
                      {item.meta ? <span>· {item.meta}</span> : null}
                      {item.createdAt ? (
                        <span>· {formatRelativeTime(item.createdAt)}</span>
                      ) : null}
                    </div>

                    {destination ? (
                      <Link
                        href={destination}
                        className="mt-3 inline-flex text-xs font-semibold text-cyan-300 transition hover:text-cyan-200"
                      >
                        Open {item.source} destination
                      </Link>
                    ) : null}
                  </div>
                );
              })}
            </div>
          )}
        </LivePanel>

        <div className="space-y-4">
          <LivePanel title="Coverage" meta="read-only">
            <LiveMiniStatGrid columns={2}>
              <LiveMiniStat
                label="Monitoring"
                value={payload.sources.alerts === "ok" ? String(counts.alerts) : "Unknown"}
                detail="Alert items sampled from the monitoring contract."
                icon={ShieldAlert}
              />
              <LiveMiniStat
                label="Approvals"
                value={
                  payload.sources.approvals === "ok" ? String(counts.approvals) : "Unknown"
                }
                detail="Visible approval requests currently in PENDING state."
              />
              <LiveMiniStat
                label="Runtime"
                value={
                  payload.sources.runtime === "ok" && payload.sources.governance === "ok"
                    ? String(counts.runtime + counts.governance)
                    : "Unknown"
                }
                detail="Governance runtime and supervision summaries when the operator can see them."
                icon={BellRing}
              />
              <LiveMiniStat
                label="Webhooks"
                value={payload.sources.webhooks === "ok" ? String(counts.webhooks) : "Unknown"}
                detail="Failing delivery samples across active webhook routes."
                icon={Webhook}
              />
            </LiveMiniStatGrid>
          </LivePanel>

          <LivePanel title="Coverage notes" meta={`${payload.partials.length} notes`}>
            {payload.partials.length === 0 ? (
              <LiveEmptyState
                title="Full feed coverage"
                message="All notification sources returned a complete payload for this operator session."
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
      </div>
    </div>
  );
}
