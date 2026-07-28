"use client";

import { useMemo, useState } from "react";
import { motion } from "framer-motion";
import {
  Activity,
  BarChart3,
  ChevronDown,
  Clock,
  Gauge,
  History,
  Layers,
  Play,
  Search,
  Server,
  Settings,
  Terminal,
  Zap,
} from "lucide-react";

import { Card } from "@/components/ui/Card";

interface LogEntry {
  id: string;
  timestamp: string;
  level: "info" | "warn" | "error" | "debug";
  message: string;
  source: string;
}

interface MetricPoint {
  timestamp: string;
  value: number;
}

interface StateTransition {
  id: string;
  from: string;
  to: string;
  timestamp: string;
  trigger: string;
}

const mockLogs: LogEntry[] = [
  { id: "1", timestamp: "2026-03-14T21:05:32Z", level: "info", message: "Agent worker-001 started successfully", source: "agent-core" },
  { id: "2", timestamp: "2026-03-14T21:05:33Z", level: "debug", message: "Loading configuration from /etc/mutx/agent.yaml", source: "config-loader" },
  { id: "3", timestamp: "2026-03-14T21:05:34Z", level: "info", message: "Connected to control plane at wss://api.mutx.dev/ws", source: "ws-client" },
  { id: "4", timestamp: "2026-03-14T21:05:35Z", level: "info", message: "Heartbeat scheduled every 30s", source: "heartbeat" },
  { id: "5", timestamp: "2026-03-14T21:06:00Z", level: "info", message: "Task queue initialized with 3 workers", source: "task-queue" },
  { id: "6", timestamp: "2026-03-14T21:06:15Z", level: "warn", message: "High memory usage detected: 78%", source: "monitor" },
  { id: "7", timestamp: "2026-03-14T21:06:30Z", level: "info", message: "Processed task batch #1042 (50 tasks)", source: "task-executor" },
  { id: "8", timestamp: "2026-03-14T21:07:00Z", level: "error", message: "Failed to connect to redis cache: Connection refused", source: "cache-client" },
  { id: "9", timestamp: "2026-03-14T21:07:01Z", level: "info", message: "Retrying cache connection (attempt 2/5)", source: "cache-client" },
  { id: "10", timestamp: "2026-03-14T21:07:02Z", level: "info", message: "Cache connection restored", source: "cache-client" },
  { id: "11", timestamp: "2026-03-14T21:07:30Z", level: "debug", message: "Garbage collection completed: freed 128MB", source: "gc" },
  { id: "12", timestamp: "2026-03-14T21:08:00Z", level: "info", message: "Scaling up worker pool to 5 instances", source: "scaler" },
];

const mockMetrics: Record<string, MetricPoint[]> = {
  cpu: Array.from({ length: 20 }, (_, i) => ({
    timestamp: new Date(Date.now() - (19 - i) * 60000).toISOString(),
    value: 30 + Math.random() * 50 + (i > 15 ? 20 : 0),
  })),
  memory: Array.from({ length: 20 }, (_, i) => ({
    timestamp: new Date(Date.now() - (19 - i) * 60000).toISOString(),
    value: 60 + Math.random() * 25 + (i > 10 ? 10 : 0),
  })),
  requests: Array.from({ length: 20 }, (_, i) => ({
    timestamp: new Date(Date.now() - (19 - i) * 60000).toISOString(),
    value: Math.floor(100 + Math.random() * 400 + (i % 5) * 50),
  })),
  latency: Array.from({ length: 20 }, (_, i) => ({
    timestamp: new Date(Date.now() - (19 - i) * 60000).toISOString(),
    value: 20 + Math.random() * 80 + (i > 14 ? 30 : 0),
  })),
};

const mockStateTransitions: StateTransition[] = [
  { id: "1", from: "idle", to: "initializing", timestamp: "2026-03-14T21:05:30Z", trigger: "start" },
  { id: "2", from: "initializing", to: "ready", timestamp: "2026-03-14T21:05:35Z", trigger: "config_loaded" },
  { id: "3", from: "ready", to: "running", timestamp: "2026-03-14T21:05:36Z", trigger: "start_tasks" },
  { id: "4", from: "running", to: "degraded", timestamp: "2026-03-14T21:06:15Z", trigger: "memory_threshold" },
  { id: "5", from: "degraded", to: "running", timestamp: "2026-03-14T21:06:45Z", trigger: "gc_completed" },
  { id: "6", from: "running", to: "scaling", timestamp: "2026-03-14T21:07:00Z", trigger: "load_increase" },
  { id: "7", from: "scaling", to: "running", timestamp: "2026-03-14T21:08:00Z", trigger: "scale_complete" },
];

type TabType = "logs" | "metrics" | "state";

function formatTime(isoString: string) {
  const date = new Date(isoString);
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function formatRelativeTime(isoString: string) {
  const then = new Date(isoString).getTime();
  const diffMs = Date.now() - then;
  const diffMins = Math.floor(diffMs / 60000);
  if (diffMins < 1) return "just now";
  if (diffMins < 60) return `${diffMins}m ago`;
  const diffHours = Math.floor(diffMins / 60);
  return `${diffHours}h ago`;
}

function LogLevelBadge({ level }: { level: LogEntry["level"] }) {
  const colors = {
    info: "bg-cyan-400/10 text-cyan-300 border-cyan-400/20",
    warn: "bg-amber-400/10 text-amber-300 border-amber-400/20",
    error: "bg-rose-400/10 text-rose-300 border-rose-400/20",
    debug: "bg-slate-400/10 text-slate-300 border-slate-400/20",
  };
  return (
    <span className={`inline-flex items-center rounded border px-1.5 py-0.5 text-[10px] font-medium uppercase ${colors[level]}`}>
      {level}
    </span>
  );
}

function MetricChart({ data, color, label }: { data: MetricPoint[]; color: string; label: string }) {
  const maxValue = Math.max(...data.map((d) => d.value));
  const minValue = Math.min(...data.map((d) => d.value));
  const range = maxValue - minValue || 1;

  return (
    <div className="relative h-24 w-full overflow-hidden">
      <div className="absolute inset-0 flex items-end gap-0.5">
        {data.map((point, i) => {
          const height = ((point.value - minValue) / range) * 100;
          return (
            <motion.div
              key={i}
              initial={{ height: 0 }}
              animate={{ height: `${Math.max(height, 4)}%` }}
              transition={{ duration: 0.3, delay: i * 0.02 }}
              className={`flex-1 rounded-t-sm ${color}`}
            />
          );
        })}
      </div>
      <div className="absolute bottom-0 left-0 right-0 flex items-center justify-between text-[10px] text-slate-500">
        <span>{formatTime(data[0]?.timestamp || "")}</span>
        <span className="font-medium text-slate-300">{label}</span>
        <span>{formatTime(data[data.length - 1]?.timestamp || "")}</span>
      </div>
    </div>
  );
}

function StateMachineVisualization({ transitions }: { transitions: StateTransition[] }) {
  const states = ["idle", "initializing", "ready", "running", "degraded", "scaling", "stopped"];
  const stateColors: Record<string, string> = {
    idle: "border-slate-500 bg-slate-500/10 text-slate-400",
    initializing: "border-amber-500 bg-amber-500/10 text-amber-400",
    ready: "border-cyan-500 bg-cyan-500/10 text-cyan-400",
    running: "border-emerald-500 bg-emerald-500/10 text-emerald-400",
    degraded: "border-rose-500 bg-rose-500/10 text-rose-400",
    scaling: "border-violet-500 bg-violet-500/10 text-violet-400",
    stopped: "border-white/30 bg-white/5 text-slate-500",
  };

  const currentState = transitions[transitions.length - 1]?.to || "running";

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-2">
        {states.map((state) => {
          const isActive = state === currentState;
          const hasBeenIn = transitions.some((t) => t.from === state || t.to === state);
          return (
            <div
              key={state}
              className={`rounded-lg border px-3 py-2 text-xs font-medium uppercase tracking-wider transition-all ${
                isActive
                  ? stateColors[state]
                  : hasBeenIn
                    ? "border-white/20 bg-white/5 text-slate-400"
                    : "border-white/5 bg-white/[0.02] text-slate-600"
              }`}
            >
              {state}
              {isActive && <span className="ml-2 motion-safe:animate-pulse motion-reduce:animate-none">●</span>}
            </div>
          );
        })}
      </div>

      <div className="rounded-xl border border-white/5 bg-black/20 p-4">
        <div className="flex items-center gap-2 mb-3">
          <History className="h-4 w-4 text-slate-400" />
          <span className="text-xs font-medium uppercase tracking-wider text-slate-400">Recent Transitions</span>
        </div>
        <div className="space-y-2">
          {transitions.slice(-5).reverse().map((transition) => (
            <div key={transition.id} className="flex items-center gap-3 text-xs">
              <span className="font-medium text-slate-300">{transition.from}</span>
              <ChevronDown className="h-3 w-3 rotate-[-90deg] text-cyan-400" />
              <span className="font-medium text-emerald-300">{transition.to}</span>
              <span className="ml-auto text-slate-500">{transition.trigger}</span>
              <span className="text-slate-600">{formatRelativeTime(transition.timestamp)}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export function LogsMetricsStateClient() {
  const [activeTab, setActiveTab] = useState<TabType>("logs");
  const [logFilter, setLogFilter] = useState("");
  const [logLevelFilter, setLogLevelFilter] = useState<string | null>(null);
  const [selectedAgent, setSelectedAgent] = useState("worker-001");

  const filteredLogs = useMemo(() => {
    return mockLogs.filter((log) => {
      const matchesSearch = logFilter === "" ||
        log.message.toLowerCase().includes(logFilter.toLowerCase()) ||
        log.source.toLowerCase().includes(logFilter.toLowerCase());
      const matchesLevel = logLevelFilter === null || log.level === logLevelFilter;
      return matchesSearch && matchesLevel;
    });
  }, [logFilter, logLevelFilter]);

  const latestMetrics = useMemo(() => {
    return {
      cpu: mockMetrics.cpu[mockMetrics.cpu.length - 1]?.value || 0,
      memory: mockMetrics.memory[mockMetrics.memory.length - 1]?.value || 0,
      requests: mockMetrics.requests.reduce((sum, m) => sum + m.value, 0),
      latency: mockMetrics.latency[mockMetrics.latency.length - 1]?.value || 0,
    };
  }, []);

  return (
    <div className="space-y-6">
      <Card className="border border-white/5 bg-white/[0.01] p-0 overflow-hidden">
        <div className="flex flex-wrap items-center justify-between gap-4 border-b border-white/5 p-6">
          <div className="flex items-center gap-3 text-violet-400">
            <Activity className="h-5 w-5" />
            <div>
              <h3 className="text-lg font-semibold tracking-tight text-white">
                Observability Hub
              </h3>
              <p className="mt-1 text-xs text-slate-500">
                Real-time logs, metrics, and state transitions
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2 rounded-xl border border-white/10 bg-black/40 px-3 py-1.5">
            <Server className="h-3.5 w-3.5 text-slate-400" />
            <select
              value={selectedAgent}
              onChange={(e) => setSelectedAgent(e.target.value)}
              className="bg-transparent text-sm text-white focus:outline-none"
            >
              <option value="worker-001">worker-001</option>
              <option value="worker-002">worker-002</option>
              <option value="worker-003">worker-003</option>
            </select>
          </div>
        </div>

        <div className="flex gap-1 border-b border-white/5 px-6">
          {([
            { id: "logs" as const, label: "Logs", icon: Terminal },
            { id: "metrics" as const, label: "Metrics", icon: BarChart3 },
            { id: "state" as const, label: "State Transitions", icon: Layers },
          ]).map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex items-center gap-2 border-b-2 px-4 py-4 text-sm font-medium transition ${
                activeTab === tab.id
                  ? "border-violet-400 text-violet-300"
                  : "border-transparent text-slate-400 hover:text-white"
              }`}
            >
              <tab.icon className="h-4 w-4" />
              {tab.label}
            </button>
          ))}
        </div>

        <div className="p-6">
          {activeTab === "logs" && (
            <div className="space-y-4">
              <div className="flex flex-wrap gap-3">
                <div className="relative flex-1 min-w-[200px]">
                  <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" />
                  <input
                    type="text"
                    value={logFilter}
                    onChange={(e) => setLogFilter(e.target.value)}
                    placeholder="Search logs..."
                    className="w-full rounded-lg border border-white/10 bg-black/40 pl-10 pr-4 py-2 text-sm text-white placeholder:text-slate-600 focus:border-cyan-400 focus:outline-none"
                  />
                </div>
                <div className="flex items-center gap-1 rounded-lg border border-white/10 bg-black/40 p-1">
                  <button
                    onClick={() => setLogLevelFilter(null)}
                    className={`rounded-md px-3 py-1.5 text-xs font-medium transition ${
                      logLevelFilter === null
                        ? "bg-white/10 text-white"
                        : "text-slate-400 hover:text-white"
                    }`}
                  >
                    All
                  </button>
                  {(["info", "warn", "error", "debug"] as const).map((level) => (
                    <button
                      key={level}
                      onClick={() => setLogLevelFilter(level)}
                      className={`rounded-md px-3 py-1.5 text-xs font-medium uppercase transition ${
                        logLevelFilter === level
                          ? "bg-white/10 text-white"
                          : "text-slate-400 hover:text-white"
                      }`}
                    >
                      {level}
                    </button>
                  ))}
                </div>
              </div>

              <div className="rounded-xl border border-white/5 bg-black/20 font-[family:var(--font-mono)] text-xs">
                <div className="max-h-[320px] overflow-y-auto custom-scrollbar">
                  {filteredLogs.map((log) => (
                    <div
                      key={log.id}
                      className="flex items-start gap-3 border-b border-white/5 px-4 py-2.5 hover:bg-white/[0.02]"
                    >
                      <span className="shrink-0 text-slate-500">{formatTime(log.timestamp)}</span>
                      <LogLevelBadge level={log.level} />
                      <span className="shrink-0 text-slate-500">[{log.source}]</span>
                      <span className="text-slate-300">{log.message}</span>
                    </div>
                  ))}
                  {filteredLogs.length === 0 && (
                    <div className="p-8 text-center text-slate-500">
                      No logs match your filter
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

          {activeTab === "metrics" && (
            <div className="space-y-6">
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                <div className="rounded-xl border border-white/5 bg-white/[0.02] p-4">
                  <div className="flex items-center justify-between">
                    <span className="text-[10px] uppercase tracking-widest text-slate-500">CPU Usage</span>
                    <Gauge className="h-4 w-4 text-cyan-400" />
                  </div>
                  <p className="mt-3 text-2xl font-semibold text-white">{latestMetrics.cpu.toFixed(1)}%</p>
                  <div className="mt-2 h-1.5 rounded-full bg-white/10 overflow-hidden">
                    <div
                      className="h-full rounded-full bg-cyan-400"
                      style={{ width: `${Math.min(latestMetrics.cpu, 100)}%` }}
                    />
                  </div>
                </div>
                <div className="rounded-xl border border-white/5 bg-white/[0.02] p-4">
                  <div className="flex items-center justify-between">
                    <span className="text-[10px] uppercase tracking-widest text-slate-500">Memory</span>
                    <Activity className="h-4 w-4 text-emerald-400" />
                  </div>
                  <p className="mt-3 text-2xl font-semibold text-white">{latestMetrics.memory.toFixed(1)}%</p>
                  <div className="mt-2 h-1.5 rounded-full bg-white/10 overflow-hidden">
                    <div
                      className="h-full rounded-full bg-emerald-400"
                      style={{ width: `${Math.min(latestMetrics.memory, 100)}%` }}
                    />
                  </div>
                </div>
                <div className="rounded-xl border border-white/5 bg-white/[0.02] p-4">
                  <div className="flex items-center justify-between">
                    <span className="text-[10px] uppercase tracking-widest text-slate-500">Requests/min</span>
                    <Zap className="h-4 w-4 text-amber-400" />
                  </div>
                  <p className="mt-3 text-2xl font-semibold text-white">{latestMetrics.requests}</p>
                  <p className="mt-2 text-xs text-slate-500">Last 20 minutes</p>
                </div>
                <div className="rounded-xl border border-white/5 bg-white/[0.02] p-4">
                  <div className="flex items-center justify-between">
                    <span className="text-[10px] uppercase tracking-widest text-slate-500">Avg Latency</span>
                    <Clock className="h-4 w-4 text-violet-400" />
                  </div>
                  <p className="mt-3 text-2xl font-semibold text-white">{latestMetrics.latency.toFixed(0)}ms</p>
                  <p className="mt-2 text-xs text-slate-500">p95 response time</p>
                </div>
              </div>

              <div className="grid gap-4 lg:grid-cols-2">
                <div className="rounded-xl border border-white/5 bg-white/[0.02] p-4">
                  <div className="flex items-center justify-between mb-4">
                    <span className="text-[10px] uppercase tracking-widest text-slate-500">CPU & Memory</span>
                    <BarChart3 className="h-4 w-4 text-slate-400" />
                  </div>
                  <MetricChart data={mockMetrics.cpu} color="bg-cyan-400" label="CPU %" />
                  <div className="mt-2">
                    <MetricChart data={mockMetrics.memory} color="bg-emerald-400" label="Memory %" />
                  </div>
                </div>
                <div className="rounded-xl border border-white/5 bg-white/[0.02] p-4">
                  <div className="flex items-center justify-between mb-4">
                    <span className="text-[10px] uppercase tracking-widest text-slate-500">Requests & Latency</span>
                    <Activity className="h-4 w-4 text-slate-400" />
                  </div>
                  <MetricChart data={mockMetrics.requests} color="bg-amber-400" label="req/min" />
                  <div className="mt-2">
                    <MetricChart data={mockMetrics.latency} color="bg-violet-400" label="latency (ms)" />
                  </div>
                </div>
              </div>
            </div>
          )}

          {activeTab === "state" && (
            <div className="space-y-4">
              <div className="rounded-xl border border-white/5 bg-white/[0.02] p-4">
                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center gap-2">
                    <Layers className="h-4 w-4 text-violet-400" />
                    <span className="text-xs font-medium uppercase tracking-wider text-slate-400">Agent State Machine</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="flex items-center gap-1.5 rounded-full bg-emerald-400/10 px-2.5 py-1 text-[10px] font-medium text-emerald-300">
                      <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 motion-safe:animate-pulse motion-reduce:animate-none" />
                      Running
                    </span>
                  </div>
                </div>
                <StateMachineVisualization transitions={mockStateTransitions} />
              </div>

              <div className="grid gap-4 lg:grid-cols-2">
                <div className="rounded-xl border border-white/5 bg-white/[0.02] p-4">
                  <div className="flex items-center gap-2 mb-3">
                    <Play className="h-4 w-4 text-emerald-400" />
                    <span className="text-[10px] uppercase tracking-widest text-slate-500">Active Handlers</span>
                  </div>
                  <div className="space-y-2">
                    {[
                      { name: "task-executor", status: "active", tasks: 47 },
                      { name: "heartbeat", status: "active", tasks: 0 },
                      { name: "ws-client", status: "active", tasks: 0 },
                      { name: "scaler", status: "idle", tasks: 0 },
                    ].map((handler) => (
                      <div key={handler.name} className="flex items-center justify-between rounded-lg border border-white/5 bg-black/20 px-3 py-2">
                        <span className="text-xs font-[family:var(--font-mono)] text-slate-300">{handler.name}</span>
                        <div className="flex items-center gap-2">
                          <span className={`h-2 w-2 rounded-full ${handler.status === "active" ? "bg-emerald-400" : "bg-slate-500"}`} />
                          <span className="text-xs text-slate-500">{handler.status}</span>
                          {handler.tasks > 0 && (
                            <span className="rounded bg-cyan-400/10 px-1.5 py-0.5 text-[10px] text-cyan-300">{handler.tasks}</span>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
                <div className="rounded-xl border border-white/5 bg-white/[0.02] p-4">
                  <div className="flex items-center gap-2 mb-3">
                    <Settings className="h-4 w-4 text-amber-400" />
                    <span className="text-[10px] uppercase tracking-widest text-slate-500">Configuration</span>
                  </div>
                  <div className="space-y-2 font-[family:var(--font-mono)] text-xs">
                    <div className="flex justify-between rounded-lg border border-white/5 bg-black/20 px-3 py-2">
                      <span className="text-slate-500">worker_pool_size</span>
                      <span className="text-cyan-300">5</span>
                    </div>
                    <div className="flex justify-between rounded-lg border border-white/5 bg-black/20 px-3 py-2">
                      <span className="text-slate-500">heartbeat_interval</span>
                      <span className="text-cyan-300">30s</span>
                    </div>
                    <div className="flex justify-between rounded-lg border border-white/5 bg-black/20 px-3 py-2">
                      <span className="text-slate-500">max_memory_percent</span>
                      <span className="text-cyan-300">85%</span>
                    </div>
                    <div className="flex justify-between rounded-lg border border-white/5 bg-black/20 px-3 py-2">
                      <span className="text-slate-500">auto_scaling</span>
                      <span className="text-emerald-300">enabled</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      </Card>
    </div>
  );
}
