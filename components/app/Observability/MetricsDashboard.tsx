"use client";

import { useCallback, useEffect, useState } from "react";
import {
  Activity,
  Cpu,
  HardDrive,
  RefreshCcw,
  TrendingUp,
  TrendingDown,
  Minus,
  Server,
} from "lucide-react";

import { Card } from "@/components/ui/Card";
import { type components } from "@/app/types/api";
import { extractApiErrorMessage, normalizeCollection } from "@/components/app/http";

type AgentMetricResponse = components["schemas"]["AgentMetricResponse"];
type DeploymentMetricsResponse = components["schemas"]["DeploymentMetricsResponse"];

type MetricEntry = AgentMetricResponse | DeploymentMetricsResponse;

interface MetricsDashboardProps {
  agentId?: string;
  deploymentId?: string;
  title?: string;
}

function formatTimestamp(timestamp?: string | null) {
  if (!timestamp) return "N/A";
  try {
    const date = new Date(timestamp);
    return date.toLocaleString();
  } catch {
    return "Invalid timestamp";
  }
}

function formatRelativeTime(timestamp?: string | null) {
  if (!timestamp) return "Never";

  const then = new Date(timestamp).getTime();
  if (Number.isNaN(then)) return "Invalid";

  const diffMs = then - Date.now();
  const rtf = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });
  const minutes = Math.round(diffMs / 60000);

  if (Math.abs(minutes) < 60) {
    return rtf.format(minutes, "minute");
  }

  const hours = Math.round(minutes / 60);
  if (Math.abs(hours) < 48) {
    return rtf.format(hours, "hour");
  }

  const days = Math.round(hours / 24);
  return rtf.format(days, "day");
}

function getUsageColor(value: number | null | undefined): string {
  if (value === null || value === undefined) return "text-slate-500";
  if (value >= 90) return "text-rose-400";
  if (value >= 70) return "text-amber-400";
  return "text-emerald-400";
}

function getUsageBgColor(value: number | null | undefined): string {
  if (value === null || value === undefined) return "bg-slate-500";
  if (value >= 90) return "bg-rose-400";
  if (value >= 70) return "bg-amber-400";
  return "bg-emerald-400";
}

function getTrendIcon(
  current: number | null,
  previous: number | null,
): React.ReactNode {
  if (current === null || previous === null || previous === 0) {
    return <Minus className="h-4 w-4 text-slate-500" />;
  }
  const change = ((current - previous) / previous) * 100;
  if (Math.abs(change) < 5) {
    return <Minus className="h-4 w-4 text-slate-500" />;
  }
  if (change > 0) {
    return <TrendingUp className="h-4 w-4 text-amber-400" />;
  }
  return <TrendingDown className="h-4 w-4 text-emerald-400" />;
}

async function fetchMetrics<T>(url: string): Promise<T[]> {
  const response = await fetch(url, { cache: "no-store" });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(extractApiErrorMessage(payload, `Failed to fetch metrics: ${response.statusText}`));
  }
  return normalizeCollection<T>(payload, ["metrics", "items", "data"]);
}

export function MetricsDashboard({
  agentId,
  deploymentId,
  title = "Metrics",
}: MetricsDashboardProps) {
  const [metrics, setMetrics] = useState<MetricEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadMetrics = useCallback(async function loadMetrics() {
    if (!agentId && !deploymentId) return;

    setLoading(true);
    setError(null);

    try {
      let url = "";
      if (agentId) {
        url = `/api/dashboard/agents/${agentId}?path=metrics`;
      } else if (deploymentId) {
        url = `/api/dashboard/deployments/${deploymentId}?path=metrics`;
      }

      const data = await fetchMetrics<MetricEntry>(url);
      setMetrics(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load metrics");
    } finally {
      setLoading(false);
    }
  }, [agentId, deploymentId]);

  useEffect(() => {
    loadMetrics();
    const interval = setInterval(loadMetrics, 10000);
    return () => clearInterval(interval);
  }, [agentId, deploymentId, loadMetrics]);

  const latestMetric = metrics[0];
  const previousMetric = metrics[1];

  const cpuTrend = getTrendIcon(
    latestMetric?.cpu_usage ?? null,
    previousMetric?.cpu_usage ?? null,
  );
  const memoryTrend = getTrendIcon(
    latestMetric?.memory_usage ?? null,
    previousMetric?.memory_usage ?? null,
  );

  return (
    <Card className="border border-white/5 bg-white/[0.01] p-0 overflow-hidden">
      <div className="flex items-center justify-between border-b border-white/5 p-4">
        <div className="flex items-center gap-3 text-emerald-400">
          <Activity className="h-5 w-5" />
          <div>
            <h3 className="text-lg font-semibold tracking-tight text-white">
              {title}
            </h3>
            <p className="mt-0.5 text-xs text-slate-500">
              Resource utilization from {agentId ? "agent" : "deployment"}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <span className="flex items-center gap-1.5 rounded-lg bg-emerald-400/10 px-2.5 py-1 text-[10px] font-medium text-emerald-400">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 motion-safe:animate-pulse motion-reduce:animate-none" />
            Live
          </span>
          <button
            onClick={loadMetrics}
            disabled={loading}
            className="inline-flex items-center gap-1.5 rounded-lg bg-white/[0.03] px-3 py-1.5 text-xs font-medium text-slate-400 transition hover:text-white disabled:opacity-50"
          >
            <RefreshCcw
              className={`h-3.5 w-3.5 ${loading ? "motion-safe:animate-spin motion-reduce:animate-none" : ""}`}
            />
          </button>
        </div>
      </div>

      {error ? (
        <div className="flex items-center gap-2 border-b border-white/5 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">
          {error}
        </div>
      ) : null}

      {loading && metrics.length === 0 ? (
        <div className="flex items-center justify-center py-12 text-slate-500">
          <RefreshCcw className="mr-2 h-4 w-4 motion-safe:animate-spin motion-reduce:animate-none" />
          Loading metrics...
        </div>
      ) : metrics.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-12 text-slate-500">
          <Server className="mb-2 h-8 w-8 opacity-50" />
          <p className="text-sm">No metrics available yet</p>
          <p className="text-xs text-slate-600 mt-1">
            Metrics will appear once the {agentId ? "agent" : "deployment"} starts reporting
          </p>
        </div>
      ) : (
        <>
          <div className="grid grid-cols-2 border-b border-white/5">
            <div className="border-r border-white/5 p-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Cpu className="h-4 w-4 text-cyan-400" />
                  <span className="text-xs font-medium uppercase tracking-wider text-slate-400">
                    CPU Usage
                  </span>
                </div>
                <div className="text-slate-500">{cpuTrend}</div>
              </div>
              <div className="mt-3 flex items-end gap-2">
                <span
                  className={`text-3xl font-semibold ${getUsageColor(latestMetric?.cpu_usage)}`}
                >
                  {latestMetric?.cpu_usage?.toFixed(1) ?? "—"}%
                </span>
              </div>
              <div className="mt-3 h-2 w-full overflow-hidden rounded-full bg-white/5">
                <div
                  className={`h-full transition-all duration-500 ${getUsageBgColor(latestMetric?.cpu_usage)}`}
                  style={{
                    width: `${latestMetric?.cpu_usage ?? 0}%`,
                  }}
                />
              </div>
              <p className="mt-2 text-xs text-slate-500">
                Last updated: {formatRelativeTime(latestMetric?.timestamp)}
              </p>
            </div>

            <div className="p-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <HardDrive className="h-4 w-4 text-violet-400" />
                  <span className="text-xs font-medium uppercase tracking-wider text-slate-400">
                    Memory Usage
                  </span>
                </div>
                <div className="text-slate-500">{memoryTrend}</div>
              </div>
              <div className="mt-3 flex items-end gap-2">
                <span
                  className={`text-3xl font-semibold ${getUsageColor(latestMetric?.memory_usage)}`}
                >
                  {latestMetric?.memory_usage?.toFixed(1) ?? "—"}%
                </span>
              </div>
              <div className="mt-3 h-2 w-full overflow-hidden rounded-full bg-white/5">
                <div
                  className={`h-full transition-all duration-500 ${getUsageBgColor(latestMetric?.memory_usage)}`}
                  style={{
                    width: `${latestMetric?.memory_usage ?? 0}%`,
                  }}
                />
              </div>
              <p className="mt-2 text-xs text-slate-500">
                Last updated: {formatRelativeTime(latestMetric?.timestamp)}
              </p>
            </div>
          </div>

          <div className="max-h-[200px] overflow-y-auto custom-scrollbar">
            <table className="w-full text-left text-xs">
              <thead className="bg-white/[0.02] text-slate-500 uppercase tracking-wider sticky top-0">
                <tr>
                  <th className="px-4 py-3 font-medium">Timestamp</th>
                  <th className="px-4 py-3 font-medium">CPU</th>
                  <th className="px-4 py-3 font-medium">Memory</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5">
                {metrics.map((metric, index) => (
                  <tr
                    key={metric.id ?? `${metric.timestamp}-${index}`}
                    className="transition-colors hover:bg-white/[0.02]"
                  >
                    <td className="px-4 py-3 font-[family:var(--font-mono)] text-slate-400">
                      {formatTimestamp(metric.timestamp)}
                    </td>
                    <td className={`px-4 py-3 font-medium ${getUsageColor(metric.cpu_usage)}`}>
                      {metric.cpu_usage?.toFixed(1) ?? "—"}%
                    </td>
                    <td className={`px-4 py-3 font-medium ${getUsageColor(metric.memory_usage)}`}>
                      {metric.memory_usage?.toFixed(1) ?? "—"}%
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </Card>
  );
}
