"use client";

import { useEffect, useState } from "react";
import { Bot, Cpu, GitBranch, TerminalSquare } from "lucide-react";

import { ApiRequestError, readJson } from "@/components/app/http";
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
  formatDateTime,
  formatRelativeTime,
} from "@/components/dashboard/livePrimitives";
import { StatusBadge } from "@/components/dashboard/StatusBadge";

import type {
  AutonomyDashboardPayload,
  AutonomyQueueItem,
} from "@/app/api/dashboard/autonomy/autonomyData";

type ErrorPresentation = {
  kind: "auth" | "forbidden" | "error";
  title: string;
  message: string;
};

export function getAutonomyErrorPresentation(status: number | null): ErrorPresentation {
  if (status === 401) {
    return {
      kind: "auth",
      title: "Operator session required",
      message: "Sign in to inspect this authenticated local autonomy snapshot.",
    };
  }
  if (status === 403) {
    return {
      kind: "forbidden",
      title: "Local autonomy access denied",
      message: "This session is not running in an approved desktop or local capability context.",
    };
  }
  if (status === 404) {
    return {
      kind: "error",
      title: "Local autonomy data not found",
      message: "The configured local workspace does not contain an autonomy snapshot yet.",
    };
  }
  if (status === 503) {
    return {
      kind: "error",
      title: "Local autonomy unavailable",
      message: "The local capability is not configured, or its data could not be read safely.",
    };
  }
  if (status !== null && status >= 500) {
    return {
      kind: "error",
      title: "Autonomy service error",
      message: "The dashboard could not verify the local autonomy snapshot.",
    };
  }
  return {
    kind: "error",
    title: "Autonomy connection unavailable",
    message: "The local autonomy endpoint could not be reached.",
  };
}

export function getAutonomySnapshotPresentation(data: AutonomyDashboardPayload) {
  if (data.freshness.state === "stale") {
    return {
      snapshotLabel: "stale local snapshot",
      snapshotStatus: "warning" as const,
      daemonValue: "stale snapshot",
      heartbeatDetail: data.freshness.heartbeatAt
        ? `Last recorded heartbeat ${formatRelativeTime(data.freshness.heartbeatAt)}; current execution is not verified.`
        : "No current heartbeat is available.",
      operationalStateVerified: false,
    };
  }

  if (data.freshness.state === "unknown") {
    return {
      snapshotLabel: "liveness unknown",
      snapshotStatus: "warning" as const,
      daemonValue: "not verified",
      heartbeatDetail: "No valid local heartbeat is available, so current execution is not verified.",
      operationalStateVerified: false,
    };
  }

  if (!data.daemon.live) {
    return {
      snapshotLabel: "fresh file · daemon not active",
      snapshotStatus: "warning" as const,
      daemonValue: data.daemon.reportedStatus,
      heartbeatDetail: `Heartbeat recorded ${formatRelativeTime(data.freshness.heartbeatAt)}; the daemon did not report an active state.`,
      operationalStateVerified: false,
    };
  }

  return {
    snapshotLabel: "fresh local heartbeat",
    snapshotStatus: "success" as const,
    daemonValue: data.daemon.reportedStatus,
    heartbeatDetail: `Heartbeat ${formatRelativeTime(data.freshness.heartbeatAt)}`,
    operationalStateVerified: true,
  };
}

function QueueList({
  title,
  items,
  operationalStateVerified,
}: {
  title: string;
  items: AutonomyQueueItem[];
  operationalStateVerified: boolean;
}) {
  return (
    <LivePanel title={title} meta={`${items.length} items`}>
      {items.length === 0 ? (
        <LiveEmptyState title={`No ${title.toLowerCase()}`} message="Nothing to show in this bucket right now." />
      ) : (
        <div className="space-y-3">
          {items.map((item) => (
            <div key={item.id ?? item.title} className="rounded-xl border border-white/10 bg-white/[0.02] p-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="text-sm font-medium text-white">{item.title ?? item.id ?? "Unnamed task"}</p>
                  <p className="mt-1 text-xs text-slate-500">
                    {(item.id ?? "unknown")} · {item.area ?? "n/a"} · {item.lane ?? item.runner ?? "unassigned"}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  {item.priority ? <StatusBadge status={asDashboardStatus(item.priority)} label={item.priority} /> : null}
                  {item.status ? (
                    <StatusBadge
                      status={operationalStateVerified ? asDashboardStatus(item.status) : "warning"}
                      label={operationalStateVerified ? item.status : `reported ${item.status}`}
                    />
                  ) : null}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </LivePanel>
  );
}

export function AutonomyPageClient() {
  const [loading, setLoading] = useState(true);
  const [errorStatus, setErrorStatus] = useState<number | "network" | null>(null);
  const [data, setData] = useState<AutonomyDashboardPayload | null>(null);

  useEffect(() => {
    let cancelled = false;
    let hasSnapshot = false;
    let pollTimer: ReturnType<typeof setTimeout> | undefined;

    async function load() {
      if (!hasSnapshot) setLoading(true);
      setErrorStatus(null);
      try {
        const payload = await readJson<AutonomyDashboardPayload>("/api/dashboard/autonomy");
        if (!cancelled) {
          hasSnapshot = true;
          setData(payload);
          setLoading(false);
        }
      } catch (loadError) {
        if (!cancelled) {
          hasSnapshot = false;
          setData(null);
          setErrorStatus(loadError instanceof ApiRequestError ? loadError.status : "network");
          setLoading(false);
        }
      } finally {
        if (!cancelled) pollTimer = setTimeout(() => void load(), 10000);
      }
    }

    void load();
    return () => {
      cancelled = true;
      if (pollTimer) clearTimeout(pollTimer);
    };
  }, []);

  if (loading) return <LiveLoading title="Autonomy" />;
  if (errorStatus !== null || !data) {
    const error = getAutonomyErrorPresentation(
      typeof errorStatus === "number" ? errorStatus : null,
    );
    if (error.kind === "auth") {
      return <LiveAuthRequired title={error.title} message={error.message} />;
    }
    if (error.kind === "forbidden") {
      return <LiveForbidden title={error.title} message={error.message} />;
    }
    return <LiveErrorState title={error.title} message={error.message} />;
  }

  const daemonStatus = data.daemon.reportedStatus;
  const queueCounts = data.queue.counts;
  const presentation = getAutonomySnapshotPresentation(data);

  return (
    <div className="space-y-4">
      <LivePanel title="Local autonomy snapshot" meta="local-only · read-only">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="max-w-2xl">
            <p className="text-sm font-medium text-white">Configured local workspace</p>
            <p className="mt-1 text-xs leading-5 text-slate-500">
              This surface reads a constrained local capability. It does not expose the workspace path or assume local files prove current execution.
            </p>
          </div>
          <StatusBadge status={presentation.snapshotStatus} label={presentation.snapshotLabel} />
        </div>
        <p className="mt-3 text-xs text-slate-500">
          {data.availability === "partial"
            ? `${data.sources.missing} of ${data.sources.available + data.sources.missing} configured sources are unavailable; available data is shown as a partial snapshot.`
            : `All ${data.sources.available} configured sources were read safely.`}
        </p>
      </LivePanel>

      <LiveKpiGrid>
        <LiveStatCard
          label="Daemon"
          value={presentation.daemonValue}
          detail={presentation.heartbeatDetail}
          status={presentation.operationalStateVerified ? asDashboardStatus(daemonStatus) : "warning"}
        />
        <LiveStatCard
          label="Queue"
          value={String((queueCounts.queued ?? 0) + (queueCounts.running ?? 0) + (queueCounts.parked ?? 0))}
          detail={
            presentation.operationalStateVerified
              ? `${queueCounts.running} running · ${queueCounts.queued} queued · ${queueCounts.parked} parked`
              : `${queueCounts.running} reported running · ${queueCounts.queued} reported queued · ${queueCounts.parked} reported parked`
          }
          status={
            presentation.operationalStateVerified
              ? asDashboardStatus(queueCounts.running > 0 ? "running" : queueCounts.queued > 0 ? "queued" : daemonStatus)
              : "warning"
          }
        />
        <LiveStatCard
          label="Active runners"
          value={String(data.activeRunners.length)}
          detail={
            presentation.operationalStateVerified
              ? data.activeRunners.length > 0
                ? data.activeRunners.map((runner) => runner.lane ?? runner.runner ?? "runner").join(", ")
                : "No active workers in the fresh snapshot"
              : "Reported entries only; current worker execution is not verified"
          }
          status={
            presentation.operationalStateVerified
              ? asDashboardStatus(data.activeRunners.length > 0 ? "running" : "idle")
              : "warning"
          }
        />
        <LiveStatCard
          label="Generated tasks"
          value={String(data.generatedTasks.length)}
          detail={`${data.fleet.roles.length} configured local fleet roles`}
          status={asDashboardStatus(data.generatedTasks.length > 0 ? "queued" : "idle")}
        />
      </LiveKpiGrid>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.15fr)_minmax(320px,0.85fr)]">
        <LivePanel title="Daemon / runtime" meta={`local-only · ${data.freshness.state}`}>
          <LiveMiniStatGrid columns={2}>
            <LiveMiniStat label="Scope" value="Configured local workspace" icon={TerminalSquare} />
            <LiveMiniStat label="Recorded cycles" value={String(data.daemon.cycleCount ?? "unknown")} icon={Cpu} detail="Snapshot value; no host process details exposed" />
            <LiveMiniStat label="Recorded result" value={data.daemon.lastResultStatus ?? "unknown"} detail={formatDateTime(data.daemon.lastCycleCompletedAt)} icon={Bot} />
            <LiveMiniStat label="Fleet roles" value={String(data.fleet.roles.length)} detail="Local role configuration" icon={GitBranch} />
          </LiveMiniStatGrid>

          <div className="mt-4 space-y-3">
            {data.activeRunners.length === 0 ? (
              <LiveEmptyState
                title="No verified active runners"
                message={
                  presentation.operationalStateVerified
                    ? "The fresh local snapshot reports no worker currently executing a task."
                    : "Current worker execution cannot be inferred from this local snapshot."
                }
              />
            ) : (
              data.activeRunners.map((runner) => (
                <div key={`${runner.taskId}-${runner.startedAt}`} className="rounded-xl border border-white/10 bg-white/[0.02] p-4">
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <p className="text-sm font-medium text-white">{runner.taskId ?? "unnamed task"}</p>
                      <p className="mt-1 text-xs text-slate-500">
                        {runner.runner ?? runner.lane ?? "runner"}
                      </p>
                    </div>
                    <StatusBadge
                      status={presentation.operationalStateVerified ? "running" : "warning"}
                      label={presentation.operationalStateVerified ? (runner.lane ?? runner.runner ?? "running") : "reported runner"}
                    />
                  </div>
                  <p className="mt-3 text-xs text-slate-500">Recorded start {formatRelativeTime(runner.startedAt)}</p>
                </div>
              ))
            )}
          </div>
        </LivePanel>

        <LivePanel title="Lane state" meta={`${data.lanes.length} reported lanes`}>
          <div className="space-y-3">
            {data.lanes.map((lane) => (
              <div key={lane.name} className="rounded-xl border border-white/10 bg-white/[0.02] p-4">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="text-sm font-medium text-white">{lane.name}</p>
                    <p className="mt-1 text-xs text-slate-500">{lane.reason ?? "No pause reason reported"}</p>
                  </div>
                  <StatusBadge
                    status={presentation.operationalStateVerified ? asDashboardStatus(lane.paused ? "warning" : "healthy") : "warning"}
                    label={presentation.operationalStateVerified ? (lane.paused ? "paused" : "active") : (lane.paused ? "reported paused" : "reported active")}
                  />
                </div>
                <p className="mt-3 text-xs text-slate-500">Recorded {formatRelativeTime(lane.updatedAt)}</p>
              </div>
            ))}
          </div>
        </LivePanel>
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <QueueList title="Reported running tasks" items={data.queue.running} operationalStateVerified={presentation.operationalStateVerified} />
        <QueueList title="Reported queued tasks" items={data.queue.queued} operationalStateVerified={presentation.operationalStateVerified} />
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <QueueList title="Reported parked tasks" items={data.queue.parked} operationalStateVerified={presentation.operationalStateVerified} />
        <LivePanel title="Recent reports" meta={`${data.reports.length} records`}>
          {data.reports.length === 0 ? (
            <LiveEmptyState title="No reports in snapshot" message="The configured local source returned no report records." />
          ) : (
            <div className="space-y-3">
              {data.reports.map((report, index) => (
                <div key={`${report.taskId ?? "report"}-${index}`} className="rounded-xl border border-white/10 bg-white/[0.02] p-4">
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <p className="text-sm font-medium text-white">{report.taskId ?? "unknown task"}</p>
                      <p className="mt-1 text-xs text-slate-500">{report.summary ?? "No summary reported"}</p>
                    </div>
                    <StatusBadge
                      status={presentation.operationalStateVerified ? asDashboardStatus(report.status ?? "idle") : "warning"}
                      label={presentation.operationalStateVerified ? (report.status ?? "unknown") : `reported ${report.status ?? "unknown"}`}
                    />
                  </div>
                  <p className="mt-3 text-xs text-slate-500">{formatDateTime(report.updatedAt)}</p>
                </div>
              ))}
            </div>
          )}
        </LivePanel>
      </div>

      <LivePanel title="Fleet roles" meta={`${data.fleet.roles.length} configured`}>
        {data.fleet.roles.length ? (
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {data.fleet.roles.map((role) => (
              <div key={role.id} className="rounded-xl border border-white/10 bg-white/[0.02] p-4">
                <div className="flex items-center justify-between gap-3">
                  <p className="text-sm font-medium text-white">{role.id}</p>
                  <StatusBadge status={asDashboardStatus(role.lane)} label={role.lane} />
                </div>
                <p className="mt-2 text-xs leading-5 text-slate-500">{role.purpose}</p>
              </div>
            ))}
          </div>
        ) : (
          <LiveEmptyState title="No fleet roles configured" message="No role definitions were returned by the configured local source." />
        )}
      </LivePanel>
    </div>
  );
}
