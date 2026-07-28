"use client";

import { useEffect, useState, useCallback } from "react";
import {
  FileText,
  RefreshCcw,
  ChevronDown,
  ChevronUp,
  Clock,
  AlertCircle,
  Info,
  AlertTriangle,
  X,
} from "lucide-react";

import { Card } from "@/components/ui/Card";
import { type components } from "@/app/types/api";
import { extractApiErrorMessage, normalizeCollection } from "@/components/app/http";

type AgentLogResponse = components["schemas"]["AgentLogResponse"];
type DeploymentLogsResponse = components["schemas"]["DeploymentLogsResponse"];

type LogEntry = AgentLogResponse | DeploymentLogsResponse;

interface LogsViewerProps {
  agentId?: string;
  deploymentId?: string;
  title?: string;
}

const LOG_LEVELS = ["all", "debug", "info", "warning", "error"] as const;
type LogLevel = (typeof LOG_LEVELS)[number];

function getLogIcon(level: string) {
  const normalizedLevel = level?.toLowerCase() ?? "info";
  if (normalizedLevel === "error") return <AlertCircle className="h-3.5 w-3.5 text-rose-400" />;
  if (normalizedLevel === "warning" || normalizedLevel === "warn")
    return <AlertTriangle className="h-3.5 w-3.5 text-amber-400" />;
  return <Info className="h-3.5 w-3.5 text-cyan-400" />;
}

function getLogLevelColor(level: string): string {
  const normalizedLevel = level?.toLowerCase() ?? "info";
  if (normalizedLevel === "error") return "text-rose-400";
  if (normalizedLevel === "warning" || normalizedLevel === "warn") return "text-amber-400";
  if (normalizedLevel === "debug") return "text-slate-500";
  return "text-cyan-400";
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

function formatMetadata(metadata: string): string {
  try {
    return JSON.stringify(JSON.parse(metadata), null, 2);
  } catch {
    return metadata;
  }
}

async function fetchLogs<T>(url: string): Promise<T[]> {
  const response = await fetch(url, { cache: "no-store" });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(extractApiErrorMessage(payload, `Failed to fetch logs: ${response.statusText}`));
  }
  return normalizeCollection<T>(payload, ["logs", "items", "data"]);
}

export function LogsViewer({
  agentId,
  deploymentId,
  title = "Logs",
}: LogsViewerProps) {
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [levelFilter, setLevelFilter] = useState<LogLevel>("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [expandedLog, setExpandedLog] = useState<string | null>(null);
  const [autoRefresh, setAutoRefresh] = useState(false);

  const loadLogs = useCallback(async () => {
    if (!agentId && !deploymentId) return;

    setLoading(true);
    setError(null);

    try {
      let url = "";
      if (agentId) {
        url = `/api/dashboard/agents/${agentId}?path=logs`;
      } else if (deploymentId) {
        url = `/api/dashboard/deployments/${deploymentId}?path=logs`;
      }

      const data = await fetchLogs<LogEntry>(url);
      setLogs(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load logs");
    } finally {
      setLoading(false);
    }
  }, [agentId, deploymentId]);

  useEffect(() => {
    loadLogs();
  }, [loadLogs]);

  useEffect(() => {
    if (!autoRefresh) return;

    const interval = setInterval(loadLogs, 5000);
    return () => clearInterval(interval);
  }, [autoRefresh, loadLogs]);

  const filteredLogs = logs.filter((log) => {
    if (levelFilter !== "all" && log.level?.toLowerCase() !== levelFilter) {
      return false;
    }
    if (searchQuery) {
      const query = searchQuery.toLowerCase();
      return (
        log.message?.toLowerCase().includes(query) ||
        log.extra_data?.toLowerCase().includes(query)
      );
    }
    return true;
  });

  return (
    <Card className="border border-white/5 bg-white/[0.01] p-0 overflow-hidden">
      <div className="flex items-center justify-between border-b border-white/5 p-4">
        <div className="flex items-center gap-3 text-cyan-400">
          <FileText className="h-5 w-5" />
          <div>
            <h3 className="text-lg font-semibold tracking-tight text-white">
              {title}
            </h3>
            <p className="mt-0.5 text-xs text-slate-500">
              Real-time log stream from {agentId ? "agent" : "deployment"}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setAutoRefresh(!autoRefresh)}
            className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium transition ${
              autoRefresh
                ? "bg-cyan-400/10 text-cyan-400"
                : "bg-white/[0.03] text-slate-400 hover:text-white"
            }`}
          >
            <RefreshCcw className={`h-3.5 w-3.5 ${autoRefresh ? "motion-safe:animate-spin motion-reduce:animate-none" : ""}`} />
            {autoRefresh ? "Live" : "Paused"}
          </button>
          <button
            onClick={loadLogs}
            disabled={loading}
            className="inline-flex items-center gap-1.5 rounded-lg bg-white/[0.03] px-3 py-1.5 text-xs font-medium text-slate-400 transition hover:text-white disabled:opacity-50"
          >
            <RefreshCcw
              className={`h-3.5 w-3.5 ${loading ? "motion-safe:animate-spin motion-reduce:animate-none" : ""}`}
            />
          </button>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-3 border-b border-white/5 bg-white/[0.02] p-3">
        <div className="relative flex-1 min-w-[200px]">
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search logs..."
            className="w-full rounded-lg border border-white/10 bg-black/40 pl-3 pr-3 py-2 text-sm text-white placeholder:text-slate-600 focus:border-cyan-400 focus:outline-none focus:ring-1 focus:ring-cyan-400/20"
          />
          {searchQuery && (
            <button
              onClick={() => setSearchQuery("")}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 hover:text-white"
            >
              <X className="h-4 w-4" />
            </button>
          )}
        </div>

        <div className="flex items-center gap-1 rounded-lg border border-white/10 bg-black/40 p-1">
          {LOG_LEVELS.map((level) => (
            <button
              key={level}
              onClick={() => setLevelFilter(level)}
              className={`rounded-md px-3 py-1.5 text-xs font-medium capitalize transition ${
                levelFilter === level
                  ? "bg-cyan-400/10 text-cyan-400"
                  : "text-slate-400 hover:text-white"
              }`}
            >
              {level}
            </button>
          ))}
        </div>

        <span className="text-xs text-slate-500">
          {filteredLogs.length} of {logs.length} entries
        </span>
      </div>

      {error ? (
        <div className="flex items-center gap-2 border-b border-white/5 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">
          <AlertCircle className="h-4 w-4" />
          {error}
        </div>
      ) : null}

      <div className="max-h-[400px] overflow-y-auto custom-scrollbar">
        {loading && logs.length === 0 ? (
          <div className="flex items-center justify-center py-12 text-slate-500">
            <RefreshCcw className="mr-2 h-4 w-4 motion-safe:animate-spin motion-reduce:animate-none" />
            Loading logs...
          </div>
        ) : filteredLogs.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 text-slate-500">
            <FileText className="mb-2 h-8 w-8 opacity-50" />
            <p className="text-sm">No logs available</p>
            {searchQuery || levelFilter !== "all" ? (
              <button
                onClick={() => {
                  setSearchQuery("");
                  setLevelFilter("all");
                }}
                className="mt-2 text-xs text-cyan-400 hover:underline"
              >
                Clear filters
              </button>
            ) : null}
          </div>
        ) : (
          <div className="divide-y divide-white/5">
            {filteredLogs.map((log, index) => (
              <div
                key={log.id ?? `${log.timestamp}-${index}`}
                className="group px-4 py-3 transition hover:bg-white/[0.02]"
              >
                <div className="flex items-start gap-3">
                  <div className="mt-0.5">{getLogIcon(log.level)}</div>
                  <div className="flex-1 min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <span
                        className={`text-xs font-medium uppercase tracking-wider ${getLogLevelColor(log.level)}`}
                      >
                        {log.level ?? "info"}
                      </span>
                      <span className="flex items-center gap-1 text-xs text-slate-500">
                        <Clock className="h-3 w-3" />
                        {formatTimestamp(log.timestamp)}
                      </span>
                      {log.extra_data && (
                        <button
                          onClick={() =>
                            setExpandedLog(
                              expandedLog === log.id ? null : (log.id ?? null),
                            )
                          }
                          className="flex items-center gap-1 text-xs text-slate-500 transition hover:text-cyan-400"
                        >
                          {expandedLog === log.id ? (
                            <>
                              <ChevronUp className="h-3 w-3" />
                              Hide metadata
                            </>
                          ) : (
                            <>
                              <ChevronDown className="h-3 w-3" />
                              Show metadata
                            </>
                          )}
                        </button>
                      )}
                    </div>
                    <p className="mt-1.5 text-sm text-slate-300 font-[family:var(--font-mono)] break-all">
                      {log.message}
                    </p>
                    {expandedLog === log.id && log.extra_data && (
                      <div className="mt-2 rounded-lg border border-white/5 bg-black/40 p-3">
                        <p className="text-xs font-medium uppercase tracking-wider text-slate-500 mb-1">
                          Metadata
                        </p>
                        <pre className="text-xs text-slate-400 overflow-x-auto">
                          {formatMetadata(log.extra_data)}
                        </pre>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </Card>
  );
}
