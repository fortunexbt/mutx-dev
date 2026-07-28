"use client";

import { useEffect, useState } from "react";
import { Database, FileStack, Sparkles } from "lucide-react";

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
  formatRelativeTime,
} from "@/components/dashboard/livePrimitives";
import { StatusBadge } from "@/components/dashboard/StatusBadge";

type MemoryPayload = {
  generatedAt: string;
  assistant: {
    name: string;
    workspace: string;
    status: string;
  } | null;
  sourceStatus: {
    assistant: MemorySourceStatus;
    sessions: MemorySourceStatus;
    documents: MemorySourceStatus;
    reasoning: MemorySourceStatus;
  };
  summary: {
    sessions: number | null;
    activeSessions: number | null;
    sources: number | null;
    documentJobs: number | null;
    documentArtifacts: number | null;
    reasoningJobs: number | null;
    reasoningArtifacts: number | null;
  };
  sessions: Array<{
    id: string;
    label: string;
    source: string;
    channel: string;
    active: boolean;
    kind: string;
    model: string;
    lastActivity: string | null;
    flags: string[];
  }>;
  sources: Array<{ source: string; count: number }>;
  documents: Array<{
    id: string;
    templateId: string;
    status: string;
    executionMode: string;
    artifacts: number;
    createdAt: string | null;
    updatedAt: string | null;
    resultSummary: string | null;
    errorMessage: string | null;
  }>;
  reasoning: Array<{
    id: string;
    templateId: string;
    status: string;
    executionMode: string;
    artifacts: number;
    createdAt: string | null;
    updatedAt: string | null;
    resultSummary: string | null;
    errorMessage: string | null;
  }>;
  partials: string[];
};

type MemorySourceStatus = "ok" | "partial" | "auth_error" | "error";

type MemorySession = MemoryPayload["sessions"][number];
type MemoryJob = MemoryPayload["documents"][number];

function asRecord(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function asString(value: unknown, fallback: string) {
  return typeof value === "string" && value.trim().length > 0 ? value : fallback;
}

function asNullableString(value: unknown) {
  return typeof value === "string" && value.trim().length > 0 ? value : null;
}

function asCount(value: unknown, fallback = 0) {
  return typeof value === "number" && Number.isFinite(value)
    ? Math.max(0, Math.trunc(value))
    : fallback;
}

function asNullableCount(value: unknown, fallback: number | null = null) {
  return typeof value === "number" && Number.isFinite(value)
    ? Math.max(0, Math.trunc(value))
    : fallback;
}

function asSourceStatus(value: unknown): MemorySourceStatus {
  return value === "ok" || value === "partial" || value === "auth_error" || value === "error"
    ? value
    : "error";
}

function asStringList(value: unknown) {
  if (!Array.isArray(value)) return [];

  return value
    .filter((item): item is string => typeof item === "string")
    .map((item) => item.trim())
    .filter(Boolean);
}

function normalizeSession(value: unknown): MemorySession | null {
  const session = asRecord(value);
  if (!session) return null;

  const id = asNullableString(session.id);
  if (!id) return null;
  return {
    id,
    label: asString(session.label, id),
    source: asString(session.source, "unknown"),
    channel: asString(session.channel, "direct"),
    active: session.active === true,
    kind: asString(session.kind, "session"),
    model: asString(session.model, "unknown"),
    lastActivity: asNullableString(session.lastActivity),
    flags: asStringList(session.flags),
  };
}

function normalizeJob(value: unknown): MemoryJob | null {
  const job = asRecord(value);
  if (!job) return null;

  const id = asNullableString(job.id);
  if (!id) return null;

  return {
    id,
    templateId: asString(job.templateId, "unpublished"),
    status: asString(job.status, "unknown"),
    executionMode: asString(job.executionMode, "unknown"),
    artifacts: asCount(job.artifacts),
    createdAt: asNullableString(job.createdAt),
    updatedAt: asNullableString(job.updatedAt),
    resultSummary: asNullableString(job.resultSummary),
    errorMessage: asNullableString(job.errorMessage),
  };
}

export function normalizeMemoryPayload(value: unknown): MemoryPayload {
  const root = asRecord(value) ?? {};
  const summary = asRecord(root.summary) ?? {};
  const sourceStatus = asRecord(root.sourceStatus) ?? {};
  const assistantRecord = asRecord(root.assistant);
  const sessions = Array.isArray(root.sessions)
    ? root.sessions
        .map(normalizeSession)
        .filter((session): session is MemorySession => session !== null)
    : [];
  const sources = Array.isArray(root.sources)
    ? root.sources.flatMap((value) => {
        const source = asRecord(value);
        if (!source) return [];
        return [{ source: asString(source.source, "unknown"), count: asCount(source.count) }];
      })
    : [];
  const documents = Array.isArray(root.documents)
    ? root.documents
        .map(normalizeJob)
        .filter((job): job is MemoryJob => job !== null)
    : [];
  const reasoning = Array.isArray(root.reasoning)
    ? root.reasoning
        .map(normalizeJob)
        .filter((job): job is MemoryJob => job !== null)
    : [];

  const partials = asStringList(root.partials);
  const responseIsIncomplete =
    !asRecord(value) ||
    !asRecord(root.summary) ||
    !asRecord(root.sourceStatus) ||
    !Array.isArray(root.sessions) ||
    !Array.isArray(root.sources) ||
    !Array.isArray(root.documents) ||
    !Array.isArray(root.reasoning) ||
    !Array.isArray(root.partials);
  if (responseIsIncomplete) {
    partials.push(
      "The memory proxy returned an incomplete payload; unavailable totals are shown as unknown.",
    );
  }

  return {
    generatedAt: asString(root.generatedAt, ""),
    assistant: assistantRecord
      ? {
          name: asString(assistantRecord.name, "Assistant"),
          workspace: asString(assistantRecord.workspace, "unpublished"),
          status: asString(assistantRecord.status, "unknown"),
        }
      : null,
    sourceStatus: {
      assistant: asSourceStatus(sourceStatus.assistant),
      sessions: asSourceStatus(sourceStatus.sessions),
      documents: asSourceStatus(sourceStatus.documents),
      reasoning: asSourceStatus(sourceStatus.reasoning),
    },
    summary: {
      sessions: asNullableCount(summary.sessions),
      activeSessions: asNullableCount(summary.activeSessions),
      sources: asNullableCount(summary.sources),
      documentJobs: asNullableCount(summary.documentJobs),
      documentArtifacts: asNullableCount(summary.documentArtifacts),
      reasoningJobs: asNullableCount(summary.reasoningJobs),
      reasoningArtifacts: asNullableCount(summary.reasoningArtifacts),
    },
    sessions,
    sources,
    documents,
    reasoning,
    partials: [...new Set(partials)],
  };
}

export function MemoryPageClient() {
  const [loading, setLoading] = useState(true);
  const [authRequired, setAuthRequired] = useState(false);
  const [permissionDenied, setPermissionDenied] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [payload, setPayload] = useState<MemoryPayload | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setLoading(true);
      setAuthRequired(false);
      setPermissionDenied(false);
      setError(null);

      try {
        const response = await readJson<unknown>("/api/dashboard/memory");
        if (!cancelled) {
          setPayload(normalizeMemoryPayload(response));
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
            setError(dashboardRequestErrorMessage(loadError, "Failed to load memory"));
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

  if (loading) return <LiveLoading title="Memory" />;
  if (authRequired) {
    return (
      <LiveAuthRequired
        title="Operator session required"
        message="Sign in to inspect session context, document artifacts, and reasoning outputs."
      />
    );
  }
  if (permissionDenied) {
    return <LiveForbidden title="Memory permission required" message="Your account cannot read workspace memory or artifact context." />;
  }
  if (error) return <LiveErrorState title="Memory surface unavailable" message={error} />;
  if (!payload) {
    return (
      <LiveErrorState
        title="Memory surface unavailable"
        message="No memory payload was returned by the dashboard proxy."
      />
    );
  }

  return (
    <div className="space-y-4">
      <LiveKpiGrid>
        <LiveStatCard
          label="Sessions"
          value={payload.summary.sessions === null ? "Unknown" : String(payload.summary.sessions)}
          detail={
            payload.summary.activeSessions === null
              ? "Session coverage is incomplete; active context totals are not verified."
              : `${payload.summary.activeSessions} active context sessions are visible right now.`
          }
          status={
            payload.summary.activeSessions === null
              ? "warning"
              : payload.summary.activeSessions > 0
                ? "running"
                : "idle"
          }
        />
        <LiveStatCard
          label="Sources"
          value={payload.summary.sources === null ? "Unknown" : String(payload.summary.sources)}
          detail="Distinct context sources represented in the current inventory."
          status={
            payload.summary.sources === null
              ? "warning"
              : payload.summary.sources > 0
                ? "success"
                : "idle"
          }
        />
        <LiveStatCard
          label="Document artifacts"
          value={
            payload.summary.documentArtifacts === null
              ? "Unknown"
              : String(payload.summary.documentArtifacts)
          }
          detail={
            payload.summary.documentJobs === null
              ? "Document job coverage is incomplete."
              : `${payload.summary.documentJobs} document jobs currently retained in the dashboard feed.`
          }
          status={
            payload.summary.documentArtifacts === null
              ? "warning"
              : payload.summary.documentArtifacts > 0
                ? "success"
                : "idle"
          }
        />
        <LiveStatCard
          label="Reasoning artifacts"
          value={
            payload.summary.reasoningArtifacts === null
              ? "Unknown"
              : String(payload.summary.reasoningArtifacts)
          }
          detail={
            payload.summary.reasoningJobs === null
              ? "Reasoning job coverage is incomplete."
              : `${payload.summary.reasoningJobs} reasoning jobs currently retained in the dashboard feed.`
          }
          status={
            payload.summary.reasoningArtifacts === null
              ? "warning"
              : payload.summary.reasoningArtifacts > 0
                ? "success"
                : "idle"
          }
        />
      </LiveKpiGrid>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.1fr)_minmax(340px,0.9fr)]">
        <LivePanel title="Context inventory" meta={`${payload.sessions.length} sessions`}>
          {payload.sessions.length === 0 ? (
            <LiveEmptyState
              title={
                payload.sourceStatus.sessions === "ok"
                  ? "No session context discovered"
                  : "Session context coverage is incomplete"
              }
              message={
                payload.sourceStatus.sessions === "ok"
                  ? "Session context will appear here once assistants or local session sources report activity."
                  : "The session feed is unavailable or malformed, so this empty inventory is not a verified zero."
              }
            />
          ) : (
            <div className="space-y-3">
              {payload.sessions.map((session) => (
                <div
                  key={session.id}
                  className="rounded-2xl border border-white/10 bg-white/[0.03] p-4"
                >
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-white">{session.label}</p>
                      <p className="mt-1 text-sm text-slate-400">
                        {session.source} · {session.channel} · {session.model}
                      </p>
                    </div>
                    <StatusBadge
                      status={session.active ? "running" : "idle"}
                      label={session.active ? "active" : "inactive"}
                    />
                  </div>

                  <p className="mt-3 text-xs text-slate-500">
                    {session.lastActivity
                      ? `Last activity ${formatRelativeTime(session.lastActivity)}`
                      : "No activity timestamp published"}
                    {session.flags.length > 0 ? ` · flags: ${session.flags.join(", ")}` : ""}
                  </p>
                </div>
              ))}
            </div>
          )}
        </LivePanel>

        <div className="space-y-4">
          <LivePanel title="Coverage" meta={payload.assistant?.workspace ?? "read-only"}>
            <LiveMiniStatGrid columns={2}>
              <LiveMiniStat
                label="Assistant"
                value={payload.assistant?.name ?? "Not published"}
                detail={payload.assistant?.workspace ?? "No assistant workspace in payload"}
                icon={Database}
              />
              <LiveMiniStat
                label="Status"
                value={payload.assistant?.status ?? "unknown"}
                detail="Assistant workspace posture if an owned assistant runtime exists."
                icon={Sparkles}
              />
              <LiveMiniStat
                label="Document jobs"
                value={
                  payload.summary.documentJobs === null
                    ? "Unknown"
                    : String(payload.summary.documentJobs)
                }
                detail={
                  payload.summary.documentArtifacts === null
                    ? "Document feed incomplete"
                    : `${payload.summary.documentArtifacts} artifacts in current feed`
                }
                icon={FileStack}
              />
              <LiveMiniStat
                label="Reasoning jobs"
                value={
                  payload.summary.reasoningJobs === null
                    ? "Unknown"
                    : String(payload.summary.reasoningJobs)
                }
                detail={
                  payload.summary.reasoningArtifacts === null
                    ? "Reasoning feed incomplete"
                    : `${payload.summary.reasoningArtifacts} artifacts in current feed`
                }
              />
            </LiveMiniStatGrid>
          </LivePanel>

          <LivePanel title="Coverage notes" meta={`${payload.partials.length} notes`}>
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
          </LivePanel>
        </div>
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <LivePanel title="Document artifacts" meta={`${payload.documents.length} jobs`}>
          {payload.documents.length === 0 ? (
            <LiveEmptyState
              title={
                payload.sourceStatus.documents === "ok"
                  ? "No document jobs yet"
                  : "Document job coverage is incomplete"
              }
              message={
                payload.sourceStatus.documents === "ok"
                  ? "Document workflow outputs show up here once the document engine has created jobs or artifacts."
                  : "The document feed is unavailable or malformed, so this empty inventory is not a verified zero."
              }
            />
          ) : (
            <div className="space-y-3">
              {payload.documents.map((job) => (
                <div
                  key={job.id}
                  className="rounded-2xl border border-white/10 bg-white/[0.03] p-4"
                >
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-white">{job.templateId}</p>
                      <p className="mt-1 text-sm text-slate-400">
                        {job.executionMode} · {job.artifacts} artifacts
                      </p>
                    </div>
                    <StatusBadge status={job.status === "completed" ? "success" : "warning"} label={job.status} />
                  </div>
                  <p className="mt-3 text-xs text-slate-500">
                    {job.updatedAt ? `Updated ${formatRelativeTime(job.updatedAt)}` : "No update timestamp"}
                  </p>
                  {job.resultSummary ? (
                    <p className="mt-2 text-sm text-slate-300">{job.resultSummary}</p>
                  ) : job.errorMessage ? (
                    <p className="mt-2 text-sm text-rose-300">{job.errorMessage}</p>
                  ) : null}
                </div>
              ))}
            </div>
          )}
        </LivePanel>

        <LivePanel title="Reasoning artifacts" meta={`${payload.reasoning.length} jobs`}>
          {payload.reasoning.length === 0 ? (
            <LiveEmptyState
              title={
                payload.sourceStatus.reasoning === "ok"
                  ? "No reasoning jobs yet"
                  : "Reasoning job coverage is incomplete"
              }
              message={
                payload.sourceStatus.reasoning === "ok"
                  ? "Reasoning outputs appear here once MUTX has persisted reasoning jobs or artifacts."
                  : "The reasoning feed is unavailable or malformed, so this empty inventory is not a verified zero."
              }
            />
          ) : (
            <div className="space-y-3">
              {payload.reasoning.map((job) => (
                <div
                  key={job.id}
                  className="rounded-2xl border border-white/10 bg-white/[0.03] p-4"
                >
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-white">{job.templateId}</p>
                      <p className="mt-1 text-sm text-slate-400">
                        {job.executionMode} · {job.artifacts} artifacts
                      </p>
                    </div>
                    <StatusBadge status={job.status === "completed" ? "success" : "warning"} label={job.status} />
                  </div>
                  <p className="mt-3 text-xs text-slate-500">
                    {job.updatedAt ? `Updated ${formatRelativeTime(job.updatedAt)}` : "No update timestamp"}
                  </p>
                  {job.resultSummary ? (
                    <p className="mt-2 text-sm text-slate-300">{job.resultSummary}</p>
                  ) : job.errorMessage ? (
                    <p className="mt-2 text-sm text-rose-300">{job.errorMessage}</p>
                  ) : null}
                </div>
              ))}
            </div>
          )}
        </LivePanel>
      </div>
    </div>
  );
}
