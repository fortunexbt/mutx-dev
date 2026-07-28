"use client";

import { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import {
  Activity,
  AlertTriangle,
  Bot,
  CheckCircle2,
  Copy,
  FileText,
  GitBranch,
  KeyRound,
  Loader2,
  LogOut,
  RefreshCcw,
  Rocket,
  ShieldCheck,
  Sparkles,
  UserCircle2,
  XCircle,
} from "lucide-react";

import { Card } from "@/components/ui/Card";
import { ApiRequestError, normalizeCollection, readJson } from "@/components/app/http";
import { type components } from "@/app/types/api";
import { getApiKeyLimit, getLatestActiveApiKey, getLatestRevokedApiKey } from "@/components/app/apiKeyHelpers";
import { LogsViewer, MetricsDashboard, StateTransitions } from "@/components/app/Observability";

type User = components["schemas"]["UserResponse"];
type Agent = components["schemas"]["AgentResponse"];
type Deployment = components["schemas"]["DeploymentResponse"];
type ApiKey = components["schemas"]["APIKeyResponse"];
type Health = components["schemas"]["HealthResponse"];
type CreateKeyResponse = components["schemas"]["APIKeyCreateResponse"];

function formatDate(value?: string | null) {
  if (!value) return "N/A";
  return new Date(value).toLocaleString();
}

function formatRelativeDate(value?: string | null) {
  if (!value) return "Not recorded";

  const then = new Date(value).getTime();
  if (Number.isNaN(then)) return "Invalid timestamp";

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

function StatusDot({ status }: { status: string }) {
  const color =
    status === "running" || status === "healthy"
      ? "bg-emerald-300"
      : status === "failed" || status === "error" || status === "unhealthy"
        ? "bg-rose-300"
        : "bg-amber-300";

  return <span className={`inline-block h-2.5 w-2.5 rounded-full ${color}`} />;
}

function statusTone(status: string) {
  if (status === "running" || status === "healthy") {
    return "bg-emerald-400/10 text-emerald-300 border-emerald-400/20";
  }

  if (status === "failed" || status === "error" || status === "unhealthy") {
    return "bg-rose-400/10 text-rose-300 border-rose-400/20";
  }

  return "bg-amber-400/10 text-amber-300 border-amber-400/20";
}

function maskApiKeyId(value: string) {
  if (value.length <= 10) return value;
  return `${value.slice(0, 6)}…${value.slice(-4)}`;
}

function getExpiryBadge(expiresAt?: string | null) {
  if (!expiresAt) return null;

  const expiresMs = new Date(expiresAt).getTime();
  if (Number.isNaN(expiresMs)) return null;

  const diffHours = (expiresMs - Date.now()) / (1000 * 60 * 60);
  if (diffHours <= 0) {
    return {
      label: 'Expired',
      tone: 'border-rose-500/30 bg-rose-500/10 text-rose-200',
    };
  }

  if (diffHours <= 24 * 7) {
    return {
      label: 'Expiring soon',
      tone: 'border-amber-400/30 bg-amber-400/10 text-amber-100',
    };
  }

  return null;
}

const walkthroughSteps = [
  {
    title: "Authenticate with operator context",
    description:
      "Start with the same ownership-aware boundary used by the dashboard and CLI before you touch fleet state.",
  },
  {
    title: "Inspect agents and deployments",
    description:
      "Verify agent records, deployment status, and the freshest deployment events before claiming anything is live.",
  },
  {
    title: "Prove non-browser API access",
    description:
      "Generate or rotate an operator key, copy the one-time secret, and show the quota and audit trail updating live.",
  },
  {
    title: "Close the loop on recovery",
    description:
      "Refresh health after a deployment change so teams can confirm the system recovered from the same dashboard.",
  },
] as const;

export function AppDashboardClient() {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [bootstrapping, setBootstrapping] = useState(true);
  const [error, setError] = useState("");
  const [copiedKey, setCopiedKey] = useState(false);
  const [user, setUser] = useState<User | null>(null);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [deployments, setDeployments] = useState<Deployment[]>([]);
  const [apiKeys, setApiKeys] = useState<ApiKey[]>([]);
  const [health, setHealth] = useState<Health | null>(null);
  const [apiKeyName, setApiKeyName] = useState("MUTX operator key");
  const [createdKey, setCreatedKey] = useState<CreateKeyResponse | null>(null);
  const [lastKeyAction, setLastKeyAction] = useState<"created" | "rotated">("created");
  const [selectedDeploymentId, setSelectedDeploymentId] = useState<string | null>(null);
  const [observabilityTab, setObservabilityTab] = useState<"logs" | "metrics" | "state">("logs");

  const selectedDeployment = selectedDeploymentId
    ? deployments.find(d => d.id === selectedDeploymentId)
    : deployments[0] ?? null;

  const runningAgents = (Array.isArray(agents) ? agents : []).filter((agent) => agent.status === "running").length;
  const healthyDeployments = (Array.isArray(deployments) ? deployments : []).filter(
    (deployment) => deployment.status === "running" || deployment.status === "healthy",
  ).length;
  const failedDeployments = (Array.isArray(deployments) ? deployments : []).filter(
    (deployment) => deployment.status === "failed" || deployment.status === "error",
  ).length;
  const activeKeys = (Array.isArray(apiKeys) ? apiKeys : []).filter((apiKey) => apiKey.is_active).length;
  const revokedKeys = apiKeys.length - activeKeys;
  const apiKeyLimit = getApiKeyLimit(user?.plan);
  const apiKeyCapacityRemaining = apiKeyLimit === null ? null : Math.max(apiKeyLimit - activeKeys, 0);
  const apiKeyLimitReached = apiKeyLimit !== null && activeKeys >= apiKeyLimit;
  const latestDeploymentEvent = deployments
    .flatMap((deployment) => normalizeCollection<{ created_at?: string | null; event_type?: string | null }>(deployment?.events, ["items", "events", "data"]))
    .sort(
      (left, right) =>
        new Date(right.created_at ?? 0).getTime() - new Date(left.created_at ?? 0).getTime(),
    )[0];
  const newestActiveKey = getLatestActiveApiKey(apiKeys);
  const newestRevokedKey = getLatestRevokedApiKey(apiKeys);
  const operatorReadiness = useMemo(() => {
    if (!user) {
      return {
        label: "auth required",
        tone: "bg-amber-400/10 text-amber-300 border-amber-400/20",
        detail: "Open an operator session to unlock live fleet, health, and key state.",
      };
    }

    if (health?.status !== "healthy") {
      return {
        label: "recovery path",
        tone: "bg-rose-400/10 text-rose-300 border-rose-400/20",
        detail: health?.error
          ? `Health check reports ${health.error}.`
          : "Control plane health still needs recovery confirmation.",
      };
    }

    if (!agents.length || !deployments.length) {
      return {
        label: "seed demo data",
        tone: "bg-amber-400/10 text-amber-300 border-amber-400/20",
        detail: "Auth is live, but the operator story gets stronger once agents and deployments exist.",
      };
    }

    if (activeKeys === 0) {
      return {
        label: "issue first key",
        tone: "bg-cyan-400/10 text-cyan-200 border-cyan-400/20",
        detail: "Fleet truth is visible. Generate an API key to complete the non-browser control path.",
      };
    }

    if (apiKeyLimitReached) {
      return {
        label: "quota edge proven",
        tone: "bg-amber-400/10 text-amber-300 border-amber-400/20",
        detail: "Key quota is saturated. Rotate or revoke one key live to show recovery from the limit edge.",
      };
    }

    return {
      label: "demo ready",
      tone: "bg-emerald-400/10 text-emerald-300 border-emerald-400/20",
      detail: "Auth, fleet, health, and API key lifecycle are all visible from one dashboard.",
    };
  }, [activeKeys, agents.length, apiKeyLimitReached, deployments.length, health?.error, health?.status, user]);
  const authBoundaryDetail = useMemo(() => {
    if (user?.email) return `Signed in as ${user.email}`;
    if (error) return error;
    if (bootstrapping) return "Checking for an existing operator session";
    return "No operator session established yet";
  }, [bootstrapping, error, user?.email]);

  const deploymentHealthDetail = useMemo(() => {
    if (!deployments.length) {
      return "No deployment heartbeat yet";
    }

    if (failedDeployments > 0) {
      return `${failedDeployments} deployment${failedDeployments === 1 ? "" : "s"} need attention`;
    }

    if (healthyDeployments === deployments.length) {
      return "All deployments look healthy";
    }

    return `${healthyDeployments}/${deployments.length} deployments healthy`;
  }, [deployments.length, failedDeployments, healthyDeployments]);

  const agentHealthDetail = useMemo(() => {
    if (!agents.length) {
      return "No agent runtime reported yet";
    }

    if (runningAgents === agents.length) {
      return "Every agent is running";
    }

    if (runningAgents === 0) {
      return "No agents are currently running";
    }

    return `${runningAgents}/${agents.length} agents running`;
  }, [agents.length, runningAgents]);

  const apiKeyPlanDetail = useMemo(() => {
    if (apiKeyLimit === null) {
      return `${activeKeys} active key${activeKeys === 1 ? "" : "s"} on an unlimited enterprise quota`;
    }

    if (apiKeyLimitReached) {
      return `Plan limit reached at ${activeKeys}/${apiKeyLimit} active keys`;
    }

    return `${apiKeyCapacityRemaining} slot${apiKeyCapacityRemaining === 1 ? "" : "s"} remain before the plan limit`;
  }, [activeKeys, apiKeyCapacityRemaining, apiKeyLimit, apiKeyLimitReached]);

  const summary = useMemo(
    () => [
      {
        label: "Agents",
        value: String(agents.length),
        detail:
          agents.length > 0
            ? `${runningAgents} running · ${agents.length - runningAgents} non-running`
            : "No agents provisioned yet",
        icon: Bot,
      },
      {
        label: "Deployments",
        value: String(deployments.length),
        detail:
          deployments.length > 0
            ? `${healthyDeployments} healthy · ${failedDeployments} failing`
            : "No deployments recorded yet",
        icon: Rocket,
      },
      {
        label: "API Keys",
        value: String(apiKeys.length),
        detail:
          apiKeys.length > 0
            ? apiKeyLimitReached
              ? `Active limit reached (${activeKeys}/${apiKeyLimit}) · ${revokedKeys} revoked`
              : apiKeyLimit === null
                ? `${activeKeys} active · unlimited plan capacity`
                : `${activeKeys}/${apiKeyLimit} active · ${apiKeyCapacityRemaining} slot${apiKeyCapacityRemaining === 1 ? "" : "s"} left`
            : apiKeyLimit === null
              ? "0 active · unlimited plan capacity"
              : `0/${apiKeyLimit} active · ${apiKeyLimit} slots available`,
        icon: KeyRound,
      },
      {
        label: "Health",
        value: health?.status || "unknown",
        detail:
          health?.timestamp
            ? `${health.error ? `${health.error} · ` : ""}Checked ${formatRelativeDate(health.timestamp)}`
            : health?.error
              ? health.error
              : "No freshness timestamp exposed",
        icon: Activity,
      },
    ],
    [
      activeKeys,
      agents.length,
      apiKeyCapacityRemaining,
      apiKeyLimit,
      apiKeyLimitReached,
      apiKeys.length,
      deployments.length,
      failedDeployments,
      health?.error,
      revokedKeys,
      health?.timestamp,
      health?.status,
      healthyDeployments,
      runningAgents,
    ],
  );

  function normalizeDashboardCollection<T extends { id?: string }>(data: unknown, keys?: string[]): T[] {
    return normalizeCollection<T>(data, keys).filter(
      (entry): entry is T => Boolean(entry && typeof entry === "object" && ("id" in entry || Object.keys(entry).length > 0)),
    );
  }

  function normalizeApiKeys(data: unknown): ApiKey[] {
    return normalizeDashboardCollection<ApiKey>(data, ["keys", "api_keys", "items", "data"]);
  }

  async function loadDashboard() {
    const [nextUser, nextHealth, rawAgents, rawDeployments, nextKeys] =
      await Promise.all([
        readJson<User>("/api/auth/me"),
        readJson<Health>("/api/dashboard/health"),
        readJson<object>("/api/dashboard/agents"),
        readJson<object>("/api/dashboard/deployments"),
        readJson<unknown>("/api/api-keys"),
      ]);

    setUser(nextUser);
    setHealth(nextHealth);
    setAgents(normalizeDashboardCollection<Agent>(rawAgents, ["agents", "items", "data"]));
    setDeployments(normalizeDashboardCollection<Deployment>(rawDeployments, ["deployments", "items", "data"]));
    setApiKeys(normalizeApiKeys(nextKeys));
  }

  useEffect(() => {
    let cancelled = false;

    async function bootstrap() {
      try {
        await loadDashboard();
      } catch (nextError) {
        if (!cancelled) {
          if (nextError instanceof ApiRequestError && nextError.status === 401) {
            setUser(null);
            setAgents([]);
            setDeployments([]);
            setApiKeys([]);
            setHealth(null);
            setError("");
          } else {
            setUser(null);
            setError(nextError instanceof Error ? nextError.message : "Failed to load dashboard");
          }
        }
      } finally {
        if (!cancelled) {
          setBootstrapping(false);
        }
      }
    }

    void bootstrap();

    return () => {
      cancelled = true;
    };
  }, []);

  async function handleAuthSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError("");
    setCreatedKey(null);

    try {
      const endpoint =
        mode === "login" ? "/api/auth/login" : "/api/auth/register";
      await readJson(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(
          mode === "login"
            ? { email, password }
            : { email, password, name: name || email.split("@")[0] },
        ),
      });

      await loadDashboard();
    } catch (nextError) {
      setError(
        nextError instanceof Error
          ? nextError.message
          : "Authentication failed",
      );
    } finally {
      setLoading(false);
    }
  }

  async function handleRefresh() {
    setRefreshing(true);
    setError("");

    try {
      await loadDashboard();
    } catch (nextError) {
      setError(
        nextError instanceof Error ? nextError.message : "Refresh failed",
      );
    } finally {
      setRefreshing(false);
    }
  }

  async function handleLogout() {
    setLoading(true);
    setError("");
    setCopiedKey(false);

    try {
      await fetch("/api/auth/logout", { method: "POST" });
      setUser(null);
      setAgents([]);
      setDeployments([]);
      setApiKeys([]);
      setHealth(null);
      setCreatedKey(null);
    } finally {
      setLoading(false);
    }
  }

  async function handleCreateKey(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError("");

    try {
      const payload = await readJson<CreateKeyResponse>("/api/api-keys", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: apiKeyName,
          expires_in_days: 30,
        }),
      });

      setLastKeyAction("created");
      setCreatedKey(payload);
      await loadDashboard();
    } catch (nextError) {
      setError(
        nextError instanceof Error
          ? nextError.message
          : "Failed to create API key",
      );
    } finally {
      setLoading(false);
    }
  }

  async function copyKey() {
    if (!createdKey?.key) return;

    try {
      await navigator.clipboard.writeText(createdKey.key);
      setCopiedKey(true);
      window.setTimeout(() => setCopiedKey(false), 2500);
    } catch (nextError) {
      setError(
        nextError instanceof Error
          ? nextError.message
          : "Failed to copy API key",
      );
    }
  }

  async function handleRevokeKey(keyId: string) {
    setLoading(true);
    setError("");

    try {
      await readJson(`/api/api-keys/${keyId}`, {
        method: "DELETE",
      });
      await loadDashboard();
    } catch (nextError) {
      setError(
        nextError instanceof Error
          ? nextError.message
          : "Failed to revoke API key",
      );
    } finally {
      setLoading(false);
    }
  }

  async function handleRotateKey(keyId: string) {
    setLoading(true);
    setError("");

    try {
      const payload = await readJson<CreateKeyResponse>(
        `/api/api-keys/${keyId}/rotate`,
        {
          method: "POST",
        },
      );
      setLastKeyAction("rotated");
      setCreatedKey(payload);
      await loadDashboard();
    } catch (nextError) {
      setError(
        nextError instanceof Error
          ? nextError.message
          : "Failed to rotate API key",
      );
    } finally {
      setLoading(false);
    }
  }

  if (!user) {
    return (
      <div className="grid gap-6 xl:grid-cols-[0.92fr_1.08fr]">
        <Card className="border border-white/5 bg-white/[0.01]">
          <div className="mb-6 flex items-center gap-3 text-cyan-400">
            <UserCircle2 className="h-6 w-6" />
            <h2 className="text-xl font-semibold text-white">
              Operator Console
            </h2>
          </div>

          <div className="mb-4 rounded-2xl border border-cyan-400/15 bg-cyan-400/5 p-4 text-sm text-slate-300">
            <div className="flex items-start gap-3">
              <Sparkles className="mt-0.5 h-4 w-4 shrink-0 text-cyan-300" />
              <div>
                <p className="font-medium text-white">Honest app state</p>
                <p className="mt-1 leading-relaxed text-slate-400">
                  This app only unlocks live dashboard data after a real session is
                  established through the control-plane auth proxy. Until then,
                  this signed-out view is the product boundary on purpose.
                </p>
              </div>
            </div>
          </div>

          <div className="mt-5 mb-6 inline-flex rounded-full border border-white/5 bg-white/[0.02] p-1 text-sm">
            {(["login", "register"] as const).map((value) => (
              <button
                key={value}
                type="button"
                onClick={() => setMode(value)}
                className={`rounded-full px-5 py-2 font-medium transition ${
                  mode === value
                    ? "bg-cyan-400/10 text-cyan-400"
                    : "text-slate-400 hover:text-white"
                }`}
              >
                {value === "login" ? "Login" : "Register"}
              </button>
            ))}
          </div>

          <form onSubmit={handleAuthSubmit} className="space-y-4">
            {mode === "register" ? (
              <input
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder="Operator name"
                className="w-full rounded-xl border border-white/10 bg-black/40 px-4 py-3 text-sm text-white placeholder:text-slate-600 focus:border-cyan-400 focus:outline-none focus:ring-1 focus:ring-cyan-400/20 transition-all"
              />
            ) : null}
            <input
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              placeholder="operator@company.com"
              required
              className="w-full rounded-xl border border-white/10 bg-black/40 px-4 py-3 text-sm text-white placeholder:text-slate-600 focus:border-cyan-400 focus:outline-none focus:ring-1 focus:ring-cyan-400/20 transition-all"
            />
            <input
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder="••••••••"
              required
              className="w-full rounded-xl border border-white/10 bg-black/40 px-4 py-3 text-sm text-white placeholder:text-slate-600 focus:border-cyan-400 focus:outline-none focus:ring-1 focus:ring-cyan-400/20 transition-all"
            />
            <button
              type="submit"
              disabled={loading}
              className="inline-flex w-full justify-center items-center gap-2 rounded-xl bg-cyan-400 px-5 py-3 text-sm font-semibold text-slate-950 transition hover:bg-cyan-300 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {loading ? (
                <Loader2 className="h-4 w-4 motion-safe:animate-spin motion-reduce:animate-none" />
              ) : (
                <ShieldCheck className="h-4 w-4" />
              )}
              {mode === "login" ? "Authenticate" : "Initialize Account"}
            </button>
          </form>

          {error ? (
            <div className="mt-4 flex items-center gap-2 rounded-xl border border-rose-500/20 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">
              <XCircle className="h-4 w-4 shrink-0" />
              {error}
            </div>
          ) : null}
        </Card>

        <Card className="border border-white/5 bg-white/[0.01]">
          <div className="mb-6 flex items-center gap-3 text-cyan-400">
            <Activity className="h-6 w-6" />
            <h2 className="text-xl font-semibold text-white">System Status</h2>
          </div>
          <div className="space-y-3">
            {[
              {
                label: "Auth Boundary",
                route: "/api/auth/*",
                status: authBoundaryDetail,
              },
              {
                label: "Agents",
                route: "/api/dashboard/agents",
                status: "Owned agents after login",
              },
              {
                label: "Deployments",
                route: "/api/dashboard/deployments",
                status: "Owned deployments after login",
              },
              {
                label: "API Keys",
                route: "/api/api-keys",
                status: "Operator credentials after login",
              },
              {
                label: "Health",
                route: "/api/dashboard/health",
                status: "Control plane status",
              },
            ].map((item) => (
              <div
                key={item.label}
                className="flex items-center justify-between rounded-xl border border-white/5 bg-white/[0.02] p-4 text-sm"
              >
                <div>
                  <p className="font-medium text-white">{item.label}</p>
                  <p className="mt-1 text-xs text-slate-500 font-[family:var(--font-mono)]">
                    {item.route}
                  </p>
                </div>
                <span className="inline-flex items-center gap-2 rounded-full bg-white/5 px-3 py-1 text-xs font-medium text-slate-300">
                  <span className="h-1.5 w-1.5 rounded-full bg-cyan-300" />
                  {item.status}
                </span>
              </div>
            ))}
          </div>

          <div className="mt-4 rounded-xl border border-amber-400/15 bg-amber-400/5 p-4 text-xs leading-relaxed text-slate-400">
            {bootstrapping
              ? "Checking for an existing operator session..."
              : "Checking for an existing operator session. No session detected yet. On localhost or demo paths, verify the API base URL and cookie flow before expecting fleet data here."}
          </div>
        </Card>

        <Card className="border border-white/5 bg-white/[0.01]">
          <div className="mb-4 flex items-center gap-3 text-cyan-300">
            <ShieldCheck className="h-6 w-6" />
            <h2 className="text-xl font-semibold text-white">Operator readiness</h2>
          </div>
          <span
            className={`inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-bold uppercase tracking-[0.24em] ${operatorReadiness.tone}`}
          >
            {operatorReadiness.label}
          </span>
          <p className="mt-3 text-sm leading-6 text-slate-300">{operatorReadiness.detail}</p>
        </Card>

        <Card className="border border-white/5 bg-white/[0.01]">
          <div className="mb-4 flex items-center gap-3 text-cyan-300">
            <p className="text-[10px] font-semibold uppercase tracking-[0.28em] text-cyan-200/75">Demo walkthrough</p>
          </div>

          <ol className="mt-2 space-y-3 text-white">
            {walkthroughSteps.map((step, index) => (
              <li key={step.title} className="rounded-lg border border-white/5 bg-black/20 px-3 py-3">
                <p className="text-xs font-semibold uppercase tracking-[0.22em] text-cyan-200">
                  Step {index + 1}
                </p>
                <p className="mt-2 text-sm font-medium text-white">{step.title}</p>
                <p className="mt-1 text-sm leading-6 text-slate-400">{step.description}</p>
              </li>
            ))}
          </ol>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <p className="text-xs uppercase tracking-[0.24em] text-cyan-200">
            Logged in
          </p>
          <h2 className="mt-2 text-2xl font-semibold text-white">
            Welcome back, {user.name}
          </h2>
          <p className="mt-1 text-sm text-slate-400">
            {user.email} · plan: {user.plan} · email verified:{" "}
            {user.is_email_verified ? "yes" : "no"}
          </p>
        </div>
        <div className="flex gap-3">
          <button
            type="button"
            onClick={handleRefresh}
            disabled={refreshing || loading}
            className="inline-flex items-center gap-2 rounded-2xl border border-white/10 bg-white/[0.03] px-4 py-3 text-sm transition hover:border-cyan-300/30 hover:text-white disabled:cursor-not-allowed disabled:opacity-60"
          >
            <RefreshCcw className={`h-4 w-4 ${refreshing ? "motion-safe:animate-spin motion-reduce:animate-none" : ""}`} />
            {refreshing ? "Refreshing" : "Refresh"}
          </button>
          <button
            type="button"
            onClick={handleLogout}
            className="inline-flex items-center gap-2 rounded-2xl border border-white/10 bg-white/[0.03] px-4 py-3 text-sm transition hover:border-rose-300/30 hover:text-white"
          >
            <LogOut className="h-4 w-4" />
            Logout
          </button>
        </div>
      </div>

      {error ? (
        <div className="flex items-center gap-2 rounded-2xl border border-rose-300/20 bg-rose-300/10 px-4 py-3 text-sm text-rose-100">
          <XCircle className="h-4 w-4" />
          {error}
        </div>
      ) : null}

      <div className="rounded-3xl border border-white/10 bg-gradient-to-br from-cyan-400/[0.12] via-black/40 to-emerald-400/[0.08] p-5 shadow-[0_24px_80px_rgba(0,0,0,0.24)]">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.28em] text-cyan-200/75">
              operator demo readiness
            </p>
            <h3 className="mt-2 text-2xl font-semibold tracking-tight text-white">
              Keep the story honest from auth to recovery.
            </h3>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-300">
              Show the product in the order an operator actually uses it: establish the session, verify fleet truth, prove non-browser key control, then refresh health after a change.
            </p>
          </div>
          <div className={`inline-flex items-center rounded-full border px-3 py-1.5 text-[11px] font-bold uppercase tracking-[0.24em] ${operatorReadiness.tone}`}>
            {operatorReadiness.label}
          </div>
        </div>

        <div className="mt-4 grid gap-3 xl:grid-cols-[1.2fr_0.8fr]">
          <div className="rounded-2xl border border-white/10 bg-black/25 p-4">
            <p className="text-[10px] font-semibold uppercase tracking-[0.24em] text-slate-400">current focus</p>
            <p className="mt-2 text-sm text-white">{operatorReadiness.detail}</p>
          </div>
          <div className="rounded-2xl border border-white/10 bg-black/25 p-4">
            <p className="text-[10px] font-semibold uppercase tracking-[0.24em] text-slate-400">latest deployment event</p>
            <p className="mt-2 text-sm text-white">
              {latestDeploymentEvent
                ? `${latestDeploymentEvent.event_type} · ${formatRelativeDate(latestDeploymentEvent.created_at)}`
                : "No deployment event exposed yet"}
            </p>
          </div>
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {summary.map(({ label, value, detail, icon: Icon }) => (
          <Card
            key={label}
            className="border border-white/5 bg-white/[0.01] p-5"
          >
            <div className="mb-4 flex items-center justify-between">
              <div className="inline-flex h-10 w-10 items-center justify-center rounded-xl bg-white/[0.03] text-cyan-400">
                <Icon className="h-5 w-5" />
              </div>
              <p className="text-[10px] font-bold uppercase tracking-widest text-slate-500">
                {label}
              </p>
            </div>

            <div className="flex items-center gap-3 text-white">
              {label === "Health" ? <StatusDot status={value} /> : null}
              <p className="text-3xl font-semibold capitalize tracking-tight">
                {value}
              </p>
            </div>
            <p className="mt-2 text-xs text-slate-500">{detail}</p>
            {label === "Health" ? (
              <>
                <p className="mt-2 text-xs text-slate-500 font-[family:var(--font-mono)]">
                  database: {health?.database || "unknown"}
                </p>
                {health?.error ? (
                  <p className="mt-2 text-xs text-rose-300">error: {health.error}</p>
                ) : null}
              </>
            ) : null}
          </Card>
        ))}
      </div>

      <div className="grid gap-6 xl:grid-cols-[1.5fr_1fr]">
        <div className="space-y-6">
          <Card className="border border-white/5 bg-white/[0.01] p-0 overflow-hidden">
            <div className="flex items-center justify-between border-b border-white/5 p-6">
              <div className="flex items-center gap-3 text-cyan-400">
                <Bot className="h-5 w-5" />
                <div>
                  <h3 className="text-lg font-semibold tracking-tight text-white">
                    Agent Fleet
                  </h3>
                  <p className="mt-1 text-xs text-slate-500">
                    Truthful view of agents returned by the authenticated control plane.
                  </p>
                </div>
              </div>
              <span className="inline-flex items-center gap-1.5 rounded-md bg-white/[0.03] px-2 py-1 text-xs font-medium text-slate-400">
                <span className="h-1.5 w-1.5 rounded-full bg-emerald-400"></span>
                Live sync
              </span>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="bg-white/[0.02] text-xs uppercase tracking-widest text-slate-400">
                  <tr>
                    <th className="px-6 py-4 font-medium">Identifier</th>
                    <th className="px-6 py-4 font-medium">Status</th>
                    <th className="px-6 py-4 font-medium">Created</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/5">
                  {refreshing ? (
                    <tr>
                      <td
                        colSpan={3}
                        className="px-6 py-12 text-center text-slate-500"
                      >
                        Refreshing live agent data…
                      </td>
                    </tr>
                  ) : agents.length ? (
                    agents.map((agent) => (
                      <tr
                        key={agent.id}
                        className="transition-colors hover:bg-white/[0.02]"
                      >
                        <td className="px-6 py-4 align-top">
                          <p className="font-medium text-slate-200">
                            {agent.name}
                          </p>
                          <p className="mt-1 text-xs font-[family:var(--font-mono)] text-slate-500">
                            {agent.id}
                          </p>
                        </td>
                        <td className="px-6 py-4 align-top capitalize">
                          <span
                            className={`inline-flex items-center gap-2 rounded-full border px-2.5 py-0.5 text-xs font-medium ${statusTone(agent.status)}`}
                          >
                            <StatusDot status={agent.status} />
                            {agent.status}
                          </span>
                        </td>
                        <td className="px-6 py-4 align-top text-xs text-slate-400">
                          <p className="font-[family:var(--font-mono)]">
                            {formatDate(agent.created_at)}
                          </p>
                          <p className="mt-1 text-slate-500">
                            {formatRelativeDate(agent.created_at)}
                          </p>
                        </td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td
                        colSpan={3}
                        className="px-6 py-12 text-center text-slate-500"
                      >
                        No agents found for this account yet.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </Card>

          <Card className="border border-white/5 bg-white/[0.01] p-0 overflow-hidden">
            <div className="flex items-center justify-between border-b border-white/5 p-6">
              <div className="flex items-center gap-3 text-emerald-400">
                <Rocket className="h-5 w-5" />
                <div>
                  <h3 className="text-lg font-semibold tracking-tight text-white">
                    Deployment Timeline
                  </h3>
                  <p className="mt-1 text-xs text-slate-500">
                    Current deployment state plus the freshest lifecycle event we can surface.
                  </p>
                </div>
              </div>
              {latestDeploymentEvent ? (
                <span className="rounded-full border border-emerald-400/15 bg-emerald-400/5 px-3 py-1 text-[10px] font-bold uppercase tracking-widest text-emerald-300">
                  latest event {formatRelativeDate(latestDeploymentEvent.created_at)}
                </span>
              ) : null}
            </div>

            <div className="space-y-3 p-6">
              <div className="grid gap-3 lg:grid-cols-3">
                <div className="rounded-xl border border-white/5 bg-white/[0.02] p-4 text-xs text-slate-300">
                  <p className="text-[10px] uppercase tracking-widest text-slate-500">Runtime signal</p>
                  <p className="mt-2 text-white">{agentHealthDetail}</p>
                </div>
                <div className="rounded-xl border border-white/5 bg-white/[0.02] p-4 text-xs text-slate-300">
                  <p className="text-[10px] uppercase tracking-widest text-slate-500">Deployment posture</p>
                  <p className="mt-2 text-white">{deploymentHealthDetail}</p>
                </div>
                <div className="rounded-xl border border-white/5 bg-white/[0.02] p-4 text-xs text-slate-300">
                  <p className="text-[10px] uppercase tracking-widest text-slate-500">Replica footprint</p>
                  <p className="mt-2 text-white">{deployments.reduce((sum, deployment) => sum + deployment.replicas, 0)} total replicas across the visible fleet</p>
                </div>
              </div>
              {refreshing ? (
                <div className="rounded-xl border border-white/5 border-dashed p-6 text-center text-sm text-slate-500">
                  Refreshing deployment state…
                </div>
              ) : deployments.length ? (
                deployments.map((deployment) => {
                  const latestEvent = deployment.events?.[deployment.events.length - 1];

                  return (
                    <div
                      key={deployment.id}
                      className="rounded-xl border border-white/5 bg-white/[0.02] p-4 transition hover:border-emerald-400/20"
                    >
                      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
                        <div>
                          <p className="font-medium text-white">{deployment.id}</p>
                          <p className="mt-1 text-xs text-slate-500">
                            Agent {deployment.agent_id}
                          </p>
                        </div>
                        <span
                          className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[10px] font-bold uppercase tracking-widest ${statusTone(deployment.status)}`}
                        >
                          <StatusDot status={deployment.status} />
                          {deployment.status}
                        </span>
                      </div>

                      <div className="grid gap-3 text-xs text-slate-400 sm:grid-cols-3">
                        <div className="rounded-lg border border-white/5 bg-black/20 p-3">
                          <p className="text-[10px] uppercase tracking-widest text-slate-500">
                            Replicas
                          </p>
                          <p className="mt-2 text-lg font-semibold text-white">
                            {deployment.replicas}
                          </p>
                        </div>
                        <div className="rounded-lg border border-white/5 bg-black/20 p-3">
                          <p className="text-[10px] uppercase tracking-widest text-slate-500">
                            Started
                          </p>
                          <p className="mt-2 font-[family:var(--font-mono)] text-[11px] text-slate-300">
                            {formatDate(deployment.started_at)}
                          </p>
                        </div>
                        <div className="rounded-lg border border-white/5 bg-black/20 p-3">
                          <p className="text-[10px] uppercase tracking-widest text-slate-500">
                            Ended
                          </p>
                          <p className="mt-2 font-[family:var(--font-mono)] text-[11px] text-slate-300">
                            {formatDate(deployment.ended_at)}
                          </p>
                        </div>
                      </div>

                      {latestEvent ? (
                        <div className="mt-3 rounded-lg border border-emerald-400/10 bg-emerald-400/[0.04] p-3 text-xs">
                          <div className="flex flex-wrap items-center justify-between gap-2">
                            <p className="font-medium text-emerald-300">
                              Latest event: {latestEvent.event_type}
                            </p>
                            <span className="text-slate-400">
                              {formatDate(latestEvent.created_at)} · {formatRelativeDate(latestEvent.created_at)}
                            </span>
                          </div>
                          <p className="mt-1 text-slate-300">
                            Status: {latestEvent.status}
                          </p>

                        </div>
                      ) : (
                        <div className="mt-3 rounded-lg border border-white/5 border-dashed p-3 text-xs text-slate-500">
                          No deployment event history is exposed for this record yet.
                        </div>
                      )}

                      {deployment.error_message ? (
                        <div className="mt-3 rounded-lg border border-rose-500/20 bg-rose-500/5 px-3 py-2 text-[11px] text-rose-200">
                          Error: {deployment.error_message}
                        </div>
                      ) : null}
                    </div>
                  );
                })
              ) : (
                <div className="rounded-xl border border-white/5 border-dashed p-6 text-center text-sm text-slate-500">
                  No deployments found for this account yet.
                </div>
              )}
            </div>
          </Card>

          {deployments.length > 0 && (
            <Card className="border border-white/5 bg-white/[0.01] p-0 overflow-hidden">
              <div className="flex items-center justify-between border-b border-white/5 p-4">
                <div className="flex items-center gap-3 text-cyan-400">
                  <Activity className="h-5 w-5" />
                  <div>
                    <h3 className="text-lg font-semibold tracking-tight text-white">
                      Observability
                    </h3>
                    <p className="mt-0.5 text-xs text-slate-500">
                      Logs, metrics, and state transitions
                    </p>
                  </div>
                </div>
              </div>

              <div className="border-b border-white/5 bg-white/[0.02] p-3">
                <div className="flex flex-wrap items-center gap-3">
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-slate-500">Deployment:</span>
                    <select
                      value={selectedDeploymentId ?? ""}
                      onChange={(e) => setSelectedDeploymentId(e.target.value || null)}
                      className="rounded-lg border border-white/10 bg-black/40 px-3 py-1.5 text-sm text-white focus:border-cyan-400 focus:outline-none focus:ring-1 focus:ring-cyan-400/20"
                    >
                      <option value="">Select a deployment</option>
                      {deployments.map((deployment) => (
                        <option key={deployment.id} value={deployment.id}>
                          {deployment.id.slice(0, 8)}... ({deployment.status})
                        </option>
                      ))}
                    </select>
                  </div>

                  <div className="flex items-center gap-1 rounded-lg border border-white/10 bg-black/40 p-1">
                    {([
                      { key: "logs", label: "Logs", icon: FileText },
                      { key: "metrics", label: "Metrics", icon: Activity },
                      { key: "state", label: "State", icon: GitBranch },
                    ] as const).map(({ key, label, icon: Icon }) => (
                      <button
                        key={key}
                        onClick={() => setObservabilityTab(key)}
                        className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition ${
                          observabilityTab === key
                            ? "bg-cyan-400/10 text-cyan-400"
                            : "text-slate-400 hover:text-white"
                        }`}
                      >
                        <Icon className="h-3.5 w-3.5" />
                        {label}
                      </button>
                    ))}
                  </div>
                </div>
              </div>

              <div className="p-4">
                {selectedDeployment ? (
                  <>
                    {observabilityTab === "logs" && (
                      <LogsViewer
                        deploymentId={selectedDeployment.id}
                        title={`Logs - ${selectedDeployment.id.slice(0, 8)}`}
                      />
                    )}
                    {observabilityTab === "metrics" && (
                      <MetricsDashboard
                        deploymentId={selectedDeployment.id}
                        title={`Metrics - ${selectedDeployment.id.slice(0, 8)}`}
                      />
                    )}
                    {observabilityTab === "state" && (
                      <StateTransitions
                        deploymentId={selectedDeployment.id}
                        title={`State - ${selectedDeployment.id.slice(0, 8)}`}
                      />
                    )}
                  </>
                ) : (
                  <div className="flex flex-col items-center justify-center py-12 text-slate-500">
                    <Activity className="mb-2 h-8 w-8 opacity-50" />
                    <p className="text-sm">Select a deployment to view observability data</p>
                  </div>
                )}
              </div>
            </Card>
          )}
        </div>

        <div className="space-y-6">
          <Card className="border border-white/5 bg-white/[0.01]">
            <div className="mb-6 flex items-center justify-between">
              <div className="flex items-center gap-3 text-amber-400">
                <KeyRound className="h-5 w-5" />
                <h3 className="text-lg font-semibold tracking-tight text-white">
                  API Keys
                </h3>
              </div>
              <span className="rounded-full border border-white/5 bg-white/[0.03] px-3 py-1 text-[10px] font-bold uppercase tracking-widest text-slate-400">
                Operator-owned
              </span>
            </div>

            <div className="mb-4 rounded-xl border border-amber-400/15 bg-amber-400/5 p-3 text-xs text-amber-100">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="font-medium text-white">Active key limit</p>
                <span className={`rounded-full px-2.5 py-1 text-[10px] font-bold uppercase tracking-widest ${apiKeyLimitReached ? "bg-rose-400/15 text-rose-200" : "bg-emerald-400/15 text-emerald-200"}`}>
                  {apiKeyLimit === null ? `${activeKeys} active · unlimited` : `${activeKeys}/${apiKeyLimit} active`}
                </span>
              </div>
              <p className="mt-2 leading-relaxed text-amber-50/80">
                {apiKeyLimit === null
                  ? "Enterprise plans can issue more active keys without hitting a quota wall. Revoked keys still remain visible for audit history."
                  : apiKeyLimitReached
                    ? "Create is blocked until you revoke or rotate an existing active key. Revoked keys stay visible for audit history."
                    : `${apiKeyCapacityRemaining} active slot${apiKeyCapacityRemaining === 1 ? "" : "s"} remain before the control plane blocks new key creation.`}
              </p>
            </div>

            <form onSubmit={handleCreateKey} className="mb-6 flex gap-2">
              <input
                value={apiKeyName}
                onChange={(event) => setApiKeyName(event.target.value)}
                placeholder="Key name..."
                className="min-w-0 flex-1 rounded-lg border border-white/10 bg-black/40 px-3 py-2 text-sm text-white placeholder:text-slate-600 focus:border-amber-400 focus:outline-none focus:ring-1 focus:ring-amber-400/20 transition-all"
              />
              <button
                type="submit"
                disabled={loading || apiKeyLimitReached}
                className="inline-flex shrink-0 items-center justify-center rounded-lg bg-amber-400 px-3 py-2 text-sm font-semibold text-amber-950 transition hover:bg-amber-300 disabled:opacity-50"
              >
                {loading ? (
                  <Loader2 className="h-4 w-4 motion-safe:animate-spin motion-reduce:animate-none" />
                ) : (
                  apiKeyLimitReached ? "Limit reached" : "Generate"
                )}
              </button>
            </form>

            {createdKey ? (
              <motion.div
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: "auto" }}
                className="mb-6 overflow-hidden rounded-lg border border-amber-400/30 bg-amber-400/10 p-4"
              >
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <p className="text-xs font-medium text-amber-200">
                      New key generated
                    </p>
                    <p className="mt-1 text-[11px] leading-relaxed text-amber-50/80">
                      {lastKeyAction === "rotated"
                        ? "Rotation succeeded. The previous key is now revoked, and this replacement secret is only shown once. Copy it now, then store it outside the dashboard before leaving this state."
                        : "This secret is only shown once. Copy it now, then store it outside the dashboard before refreshing or rotating again."}
                    </p>
                  </div>
                  <span className="rounded-full bg-amber-950/50 px-2.5 py-1 text-[10px] font-bold uppercase tracking-widest text-amber-200">
                    {lastKeyAction === "rotated" ? "rotation complete" : "one-time reveal"}
                  </span>
                </div>
                <div className="mt-3 flex items-center gap-2 rounded bg-black/40 px-3 py-2">
                  <code className="flex-1 truncate text-xs text-white">
                    {createdKey.key}
                  </code>
                  <span className="hidden text-[10px] font-medium uppercase tracking-widest text-amber-200 sm:inline">
                    {lastKeyAction === "rotated" ? "replacement key" : "new key"}
                  </span>
                  <button
                    type="button"
                    onClick={copyKey}
                    className="text-amber-400 hover:text-amber-300"
                  >
                    <Copy className="h-4 w-4" />
                  </button>
                </div>
                <p className="mt-2 text-[11px] text-amber-100/90">
                  {copiedKey
                    ? lastKeyAction === "rotated"
                      ? "Replacement key copied. The revoked predecessor remains visible below for audit proof."
                      : "Copied to clipboard. Store it before you refresh or leave this page."
                    : lastKeyAction === "rotated"
                      ? "Copy the replacement key now. The previous key is already revoked and this secret will not be shown again."
                      : "Copy now. This secret will not be shown again after you leave this state."}
                </p>
              </motion.div>
            ) : null}

            <div className="mb-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
              <div className="rounded-xl border border-white/5 bg-white/[0.02] p-3 text-xs text-slate-300">
                <p className="text-[10px] uppercase tracking-widest text-slate-500">
                  Newest active key
                </p>
                {newestActiveKey ? (
                  <>
                    <p className="mt-2 font-medium text-white">{newestActiveKey.name}</p>
                    <p className="mt-1 font-[family:var(--font-mono)] text-[11px] text-slate-500">
                      {maskApiKeyId(newestActiveKey.id)} · last used {formatRelativeDate(newestActiveKey.last_used)}
                    </p>
                  </>
                ) : (
                  <p className="mt-2 text-slate-500">No active key issued yet.</p>
                )}
              </div>
              <div className="rounded-xl border border-white/5 bg-white/[0.02] p-3 text-xs text-slate-300">
                <p className="text-[10px] uppercase tracking-widest text-slate-500">
                  Audit trail
                </p>
                {newestRevokedKey ? (
                  <>
                    <p className="mt-2 font-medium text-white">Most recent revoked key kept for history</p>
                    <p className="mt-1 font-[family:var(--font-mono)] text-[11px] text-slate-500">
                      {maskApiKeyId(newestRevokedKey.id)} · revoked key still visible in the ledger
                    </p>
                  </>
                ) : (
                  <p className="mt-2 text-slate-500">No revoked keys yet.</p>
                )}
              </div>
              <div className="rounded-xl border border-white/5 bg-white/[0.02] p-3 text-xs text-slate-300">
                <p className="text-[10px] uppercase tracking-widest text-slate-500">
                  Demo cue
                </p>
                <p className="mt-2 text-white">
                  {apiKeyLimit === null
                    ? "Generate, copy, and rotate keys without tripping a quota wall to show enterprise-grade operator throughput."
                    : apiKeyLimitReached
                      ? "Show the create button locking at the active limit, then rotate or revoke a key to reopen capacity live."
                      : activeKeys > 0
                        ? "Use the copy → rotate flow to prove one-time secret reveal and audit-safe revocation in a single path."
                        : "Generate the first operator key here to unlock a full non-browser auth lifecycle demo."}
                </p>
              </div>
            </div>

            <div className="space-y-2 max-h-[340px] overflow-y-auto pr-2 custom-scrollbar">
              {apiKeys.length ? (
                apiKeys.map((apiKey) => {
                  const lastUsedRelative = apiKey.last_used ? formatRelativeDate(apiKey.last_used) : "Never used";
                  const expiresRelative = apiKey.expires_at ? formatRelativeDate(apiKey.expires_at) : "No expiry";
                  const expiryBadge = getExpiryBadge(apiKey.expires_at);

                  return (
                  <div
                    key={apiKey.id}
                    className="rounded-lg border border-white/5 bg-white/[0.02] px-3 py-3 text-sm"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <p className="truncate font-medium text-slate-300">
                            {apiKey.name}
                          </p>
                          <span
                            className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium uppercase tracking-widest ${apiKey.is_active ? "bg-emerald-400/10 text-emerald-300" : "bg-white/5 text-slate-400"}`}
                          >
                            <span
                              className={`h-1.5 w-1.5 rounded-full ${apiKey.is_active ? "bg-emerald-300" : "bg-slate-500"}`}
                            />
                            {apiKey.is_active ? "Active" : "Revoked"}
                          </span>
                          {expiryBadge ? (
                            <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-medium uppercase tracking-widest ${expiryBadge.tone}`}>
                              {expiryBadge.label}
                            </span>
                          ) : null}
                        </div>
                        <p className="mt-2 font-[family:var(--font-mono)] text-[11px] text-slate-500">
                          {maskApiKeyId(apiKey.id)}
                        </p>
                        <div className="mt-2 space-y-1 font-[family:var(--font-mono)] text-[11px] text-slate-500">
                          <p>Created: {formatDate(apiKey.created_at)}</p>
                          <p>Last used: {formatDate(apiKey.last_used)} · {lastUsedRelative}</p>
                          <p>Expires: {formatDate(apiKey.expires_at)} · {expiresRelative}</p>
                        </div>
                        <div className="mt-3 flex flex-wrap gap-2 text-[10px] font-medium uppercase tracking-widest text-slate-400">
                          <span className="rounded-full border border-white/10 bg-black/20 px-2 py-1">
                            {apiKey.is_active ? "Usable right now" : "Audit-only record"}
                          </span>
                          {apiKey.last_used ? (
                            <span className="rounded-full border border-white/10 bg-black/20 px-2 py-1">
                              Seen {lastUsedRelative}
                            </span>
                          ) : (
                            <span className="rounded-full border border-white/10 bg-black/20 px-2 py-1">
                              Never presented to the API
                            </span>
                          )}
                        </div>
                      </div>
                      {apiKey.is_active ? (
                        <div className="flex items-center gap-2">
                          <button
                            type="button"
                            onClick={() => handleRotateKey(apiKey.id)}
                            disabled={loading}
                            className="rounded border border-cyan-500/30 px-2 py-1 text-[10px] font-medium uppercase tracking-widest text-cyan-300 transition hover:border-cyan-400 hover:text-cyan-200 disabled:cursor-not-allowed disabled:opacity-60"
                          >
                            Rotate
                          </button>
                          <button
                            type="button"
                            onClick={() => handleRevokeKey(apiKey.id)}
                            disabled={loading}
                            className="rounded border border-rose-500/30 px-2 py-1 text-[10px] font-medium uppercase tracking-widest text-rose-300 transition hover:border-rose-400 hover:text-rose-200 disabled:cursor-not-allowed disabled:opacity-60"
                          >
                            Revoke
                          </button>
                        </div>
                      ) : null}
                    </div>
                  </div>
                  );
                })
              ) : (
                <p className="py-4 text-center text-xs text-slate-500">
                  No keys provisioned yet. Generate one here to unlock non-browser operator access.
                </p>
              )}
            </div>
          </Card>

          <Card className="border border-white/5 bg-white/[0.01]">
            <div className="mb-4 flex items-center gap-3 text-cyan-300">
              {health?.status === "healthy" ? (
                <CheckCircle2 className="h-5 w-5" />
              ) : (
                <AlertTriangle className="h-5 w-5" />
              )}
              <h3 className="text-lg font-semibold tracking-tight text-white">
                Operator Readout
              </h3>
            </div>

            <div className="space-y-3 text-sm text-slate-300">
              <div className="rounded-xl border border-white/5 bg-white/[0.02] p-4">
                <p className="text-[10px] uppercase tracking-widest text-slate-500">
                  Current health posture
                </p>
                <p className="mt-2 text-white">
                  {health?.status === "healthy"
                    ? "Control plane looks reachable from the dashboard proxy."
                    : "Control plane state is degraded, unknown, or not yet verified from this session."}
                </p>
              </div>

              <div className="rounded-xl border border-white/5 bg-white/[0.02] p-4">
                <p className="text-[10px] uppercase tracking-widest text-slate-500">
                  Fleet signal
                </p>
                <p className="mt-2 text-white">
                  {agents.length || deployments.length
                    ? `${runningAgents}/${agents.length} agents are running, and ${healthyDeployments}/${deployments.length} deployments look healthy.`
                    : "This account has no live fleet records yet, which is shown honestly instead of filling the screen with placeholders."}
                </p>
              </div>

              <div className="rounded-xl border border-white/5 bg-white/[0.02] p-4">
                <p className="text-[10px] uppercase tracking-widest text-slate-500">
                  Key management
                </p>
                <p className="mt-2 text-white">
                  {activeKeys > 0
                    ? apiKeyLimit === null
                      ? `${activeKeys} active API key${activeKeys === 1 ? "" : "s"} can authenticate operator workflows right now, and this plan does not enforce a hard key cap.`
                      : apiKeyLimitReached
                        ? `${activeKeys} active API keys are already consuming the current ${apiKeyLimit}-key limit. Rotate or revoke one before creating another.`
                        : `${activeKeys} active API key${activeKeys === 1 ? "" : "s"} can authenticate operator workflows right now, with ${apiKeyCapacityRemaining} slot${apiKeyCapacityRemaining === 1 ? "" : "s"} still available.`
                    : apiKeyLimit === null
                      ? "No active API keys are present yet; enterprise capacity is open when you need non-browser access."
                      : `No active API keys are present yet; all ${apiKeyLimit} slots are available when you need non-browser access.`}
                </p>
              </div>

              <div className="rounded-xl border border-white/5 bg-white/[0.02] p-4">
                <p className="text-[10px] uppercase tracking-widest text-slate-500">
                  Plan quota truth
                </p>
                <p className="mt-2 text-white">{apiKeyPlanDetail}</p>
              </div>

              <div className="rounded-xl border border-white/5 bg-white/[0.02] p-4">
                <p className="text-[10px] uppercase tracking-widest text-slate-500">
                  Demo walkthrough
                </p>
                <ol className="mt-2 space-y-3 text-white">
                  {walkthroughSteps.map((step, index) => (
                    <li key={step.title} className="rounded-lg border border-white/5 bg-black/20 px-3 py-3">
                      <p className="text-xs font-semibold uppercase tracking-[0.22em] text-cyan-200">
                        Step {index + 1}
                      </p>
                      <p className="mt-2 text-sm font-medium text-white">{step.title}</p>
                      <p className="mt-1 text-sm leading-6 text-slate-400">{step.description}</p>
                    </li>
                  ))}
                </ol>
              </div>
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}
