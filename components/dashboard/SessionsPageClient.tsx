"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { normalizeCollection, readJson, writeJson } from "@/components/app/http";
import {
  dashboardRequestErrorMessage,
  getDashboardRequestAccessFailure,
} from "@/components/dashboard/dashboardRequestAccess";
import { DashboardDialog } from "@/components/dashboard/DashboardDialog";
import {
  LiveAuthRequired,
  LiveEmptyState,
  LiveErrorState,
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

type AssistantOverviewEnvelope = components["schemas"]["AssistantOverviewEnvelope"];
type AssistantOverview = components["schemas"]["AssistantOverviewResponse"];
type SessionControlAction = components["schemas"]["SessionControlRequest"]["action"];
type SessionOperatorAction = SessionControlAction | "delete";

interface SessionRecord {
  id: string;
  key: string;
  agent: string;
  kind: string;
  age: string;
  model: string;
  tokens: string;
  channel: string;
  flags: string[];
  active: boolean;
  state: string;
  source: string;
  controllable: boolean;
  startTime: string | null;
  lastActivity: string | null;
}

interface SessionTranscript {
  session_key: string;
  messages: Array<Record<string, unknown>>;
  total_count: number;
}

interface PendingSessionAction {
  session: SessionRecord;
  action: SessionOperatorAction;
}

const secondaryButtonClass =
  "min-h-11 rounded-lg border border-white/10 bg-white/[0.04] px-3 py-2 text-xs font-medium text-slate-300 transition hover:border-white/20 hover:text-white disabled:cursor-not-allowed disabled:opacity-50";
const dangerButtonClass =
  "min-h-11 rounded-lg border border-rose-400/20 bg-rose-400/10 px-3 py-2 text-xs font-medium text-rose-200 transition hover:border-rose-300/40 disabled:cursor-not-allowed disabled:opacity-50";
const confirmButtonClass =
  "inline-flex min-h-11 w-full items-center justify-center rounded-lg border border-cyan-400/30 bg-cyan-400/10 px-4 py-2 text-sm font-semibold text-cyan-100 transition hover:border-cyan-300/50 disabled:cursor-not-allowed disabled:opacity-50 sm:w-auto";
const destructiveConfirmButtonClass =
  "inline-flex min-h-11 w-full items-center justify-center rounded-lg border border-rose-400/30 bg-rose-400/15 px-4 py-2 text-sm font-semibold text-rose-100 transition hover:border-rose-300/50 disabled:cursor-not-allowed disabled:opacity-50 sm:w-auto";

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function hasSessionCollectionPayload(value: unknown) {
  if (Array.isArray(value)) return true;
  if (!isRecord(value)) return false;
  return ["sessions", "items", "data"].some((key) => Array.isArray(value[key]));
}

function pickString(record: Record<string, unknown>, keys: string[], fallback = "") {
  for (const key of keys) {
    const value = record[key];
    if (typeof value === "string" && value.trim().length > 0) {
      return value;
    }
  }

  return fallback;
}

function pickBoolean(record: Record<string, unknown>, keys: string[], fallback = false) {
  for (const key of keys) {
    const value = record[key];
    if (typeof value === "boolean") {
      return value;
    }
  }

  return fallback;
}

function pickStringArray(record: Record<string, unknown>, keys: string[]) {
  for (const key of keys) {
    const value = record[key];
    if (Array.isArray(value)) {
      return value.filter((entry): entry is string => typeof entry === "string" && entry.length > 0);
    }
  }

  return [];
}

function toIsoTimestamp(value: unknown) {
  if (typeof value === "string" && value.trim().length > 0) {
    return value;
  }

  if (typeof value === "number" && Number.isFinite(value)) {
    const millis = value > 1_000_000_000_000 ? value : value * 1000;
    return new Date(millis).toISOString();
  }

  return null;
}

function normalizeSession(session: Record<string, unknown>): SessionRecord | null {
  const id = pickString(session, ["id", "session_id", "key"]);
  if (!id) return null;
  const source = pickString(session, ["source"], "gateway");
  const state = pickString(session, ["state", "status"], pickBoolean(session, ["active"]) ? "active" : "idle");
  const active = pickBoolean(session, ["active"], state === "active" || state === "running");

  return {
    id,
    key: pickString(session, ["key", "session_key"], id),
    agent: pickString(session, ["agent", "assistant", "assistant_name", "name", "display_name"], "Assistant session"),
    kind: pickString(session, ["kind", "type", "chat_type"], "session"),
    age: pickString(session, ["age"], "n/a"),
    model: pickString(session, ["model"], "unknown model"),
    tokens: pickString(session, ["tokens"], "n/a"),
    channel: pickString(session, ["channel", "platform"], "unassigned"),
    flags: pickStringArray(session, ["flags"]),
    active,
    state,
    source,
    controllable: source === "gateway" || source.startsWith("openclaw"),
    startTime: toIsoTimestamp(session.start_time ?? session.created_at),
    lastActivity: toIsoTimestamp(session.last_activity ?? session.updated_at),
  };
}

function extractAssistantOverview(payload: unknown): AssistantOverview | null {
  if (!isRecord(payload)) return null;

  const { assistant } = payload as AssistantOverviewEnvelope;
  return assistant ?? null;
}

function transcriptText(message: Record<string, unknown>) {
  for (const key of ["content", "text", "message"]) {
    const value = message[key];
    if (typeof value === "string" && value.trim()) return value;
    if (Array.isArray(value)) {
      const text = value
        .map((part) => (isRecord(part) ? pickString(part, ["text", "content"]) : String(part ?? "")))
        .filter(Boolean)
        .join("\n");
      if (text) return text;
    }
  }

  return JSON.stringify(message, null, 2);
}

export function SessionsPageClient() {
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [authRequired, setAuthRequired] = useState(false);
  const [permissionDenied, setPermissionDenied] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionNotice, setActionNotice] = useState<string | null>(null);
  const [actingKey, setActingKey] = useState<string | null>(null);
  const [sessions, setSessions] = useState<SessionRecord[]>([]);
  const [sessionCoverageNote, setSessionCoverageNote] = useState<string | null>(null);
  const [assistant, setAssistant] = useState<AssistantOverview | null>(null);
  const [selectedSession, setSelectedSession] = useState<SessionRecord | null>(null);
  const [transcript, setTranscript] = useState<SessionTranscript | null>(null);
  const [transcriptLoading, setTranscriptLoading] = useState(false);
  const [transcriptError, setTranscriptError] = useState<string | null>(null);
  const [pendingAction, setPendingAction] = useState<PendingSessionAction | null>(null);
  const [dialogError, setDialogError] = useState<string | null>(null);

  const loadSessions = useCallback(async (initial = false) => {
    if (initial) setLoading(true);
    else setRefreshing(true);
    setAuthRequired(false);
    setPermissionDenied(false);
    setError(null);

    try {
      await readJson<Record<string, unknown>>("/api/auth/me");
      const [sessionsResult, overviewResult] = await Promise.allSettled([
        readJson<unknown>("/api/dashboard/sessions"),
        readJson<unknown>("/api/dashboard/assistant/overview"),
      ]);

      if (sessionsResult.status === "rejected") throw sessionsResult.reason;
      if (
        overviewResult.status === "rejected" &&
        getDashboardRequestAccessFailure(overviewResult.reason)
      ) {
        throw overviewResult.reason;
      }

      const sessionRecords = normalizeCollection<Record<string, unknown>>(sessionsResult.value, [
        "sessions",
        "items",
        "data",
      ]);
      const nextSessions = sessionRecords
        .flatMap((session) => {
          const normalized = normalizeSession(session);
          return normalized ? [normalized] : [];
        })
        .sort((left, right) => {
          const leftTime = left.lastActivity ? new Date(left.lastActivity).getTime() : 0;
          const rightTime = right.lastActivity ? new Date(right.lastActivity).getTime() : 0;
          return rightTime - leftTime;
        });

      setSessions(nextSessions);
      const omittedSessions = sessionRecords.length - nextSessions.length;
      setSessionCoverageNote(
        !hasSessionCollectionPayload(sessionsResult.value)
          ? "The session endpoint returned an invalid collection envelope. Session totals are not verified."
          : omittedSessions > 0
          ? `${omittedSessions} session record${omittedSessions === 1 ? " was" : "s were"} omitted because the upstream identifier was missing. Session totals are not verified.`
          : null,
      );
      setAssistant(
        overviewResult.status === "fulfilled" ? extractAssistantOverview(overviewResult.value) : null,
      );
      setSelectedSession((current) =>
        current ? nextSessions.find((session) => session.key === current.key) ?? null : null,
      );
    } catch (loadError) {
      const accessFailure = getDashboardRequestAccessFailure(loadError);
      if (accessFailure === "authentication") setAuthRequired(true);
      else if (accessFailure === "permission") setPermissionDenied(true);
      else setError(dashboardRequestErrorMessage(loadError, "Failed to load sessions"));
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    void loadSessions(true);
  }, [loadSessions]);

  const activeSessions = useMemo(
    () => sessions.filter((session) => session.active).length,
    [sessions],
  );
  const channels = useMemo(
    () => Array.from(new Set(sessions.map((session) => session.channel).filter(Boolean))),
    [sessions],
  );
  const sources = useMemo(
    () => Array.from(new Set(sessions.map((session) => session.source).filter(Boolean))),
    [sessions],
  );

  async function loadTranscript(session: SessionRecord) {
    setSelectedSession(session);
    setTranscript(null);
    setTranscriptError(null);
    setTranscriptLoading(true);

    try {
      const response = await readJson<SessionTranscript>(
        `/api/dashboard/sessions/${encodeURIComponent(session.key)}/transcript`,
      );
      setTranscript(response);
    } catch (loadError) {
      const accessFailure = getDashboardRequestAccessFailure(loadError);
      if (accessFailure === "authentication") setAuthRequired(true);
      else if (accessFailure === "permission") setPermissionDenied(true);
      else setTranscriptError(dashboardRequestErrorMessage(loadError, "Failed to load session transcript"));
    } finally {
      setTranscriptLoading(false);
    }
  }

  function requestSessionAction(session: SessionRecord, action: SessionOperatorAction) {
    if (actingKey) return;
    setActionError(null);
    setActionNotice(null);
    setDialogError(null);
    setPendingAction({ session, action });
  }

  async function confirmSessionAction() {
    if (!pendingAction || actingKey) return;

    const { session, action } = pendingAction;

    setActingKey(session.key);
    setActionError(null);
    setActionNotice(null);
    setDialogError(null);
    try {
      if (action === "delete") {
        await writeJson("/api/dashboard/sessions", {
          method: "DELETE",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ session_key: session.key }),
        });
        setActionNotice(`Deleted session ${session.key}.`);
      } else {
        await writeJson(`/api/dashboard/sessions/${encodeURIComponent(session.key)}/control`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ action }),
        });
        setActionNotice(`${action[0].toUpperCase()}${action.slice(1)} applied to ${session.key}.`);
      }
      if ((action === "kill" || action === "delete") && selectedSession?.key === session.key) {
        setSelectedSession(null);
        setTranscript(null);
      }
      await loadSessions(false);
      setPendingAction(null);
    } catch (mutationError) {
      const accessFailure = getDashboardRequestAccessFailure(mutationError);
      if (accessFailure === "authentication") setAuthRequired(true);
      else if (accessFailure === "permission") setPermissionDenied(true);
      else {
        const message = dashboardRequestErrorMessage(
          mutationError,
          action === "delete" ? "Failed to delete session" : `Failed to ${action} session`,
        );
        setActionError(message);
        setDialogError(message);
      }
    } finally {
      setActingKey(null);
    }
  }

  if (loading) return <LiveLoading title="Sessions" />;
  if (authRequired) {
    return (
      <LiveAuthRequired
        title="Operator session required"
        message="Sign in to inspect assistant sessions, transcripts, and lifecycle controls."
      />
    );
  }
  if (permissionDenied) {
    return <LiveForbidden title="Session permission required" message="Your account cannot inspect or control assistant sessions. Transcript and lifecycle controls are unavailable." />;
  }
  if (error && sessions.length === 0) {
    return <LiveErrorState title="Session surface unavailable" message={error} />;
  }

  const enabledChannels = assistant?.channels?.filter((channel) => channel.enabled).length ?? 0;
  const gatewayStatus = assistant?.gateway.status ?? "unknown";
  const pendingVerb = pendingAction
    ? `${pendingAction.action[0].toUpperCase()}${pendingAction.action.slice(1)}`
    : "Confirm";
  const pendingIsDestructive = pendingAction?.action === "kill" || pendingAction?.action === "delete";
  const pendingConsequence = pendingAction?.action === "pause"
    ? "The gateway will move this active session to paused state until it is resumed."
    : pendingAction?.action === "resume"
      ? "The gateway will move this paused session back to active state."
      : pendingAction?.action === "kill"
        ? "The gateway will terminate this session. A terminated session cannot be resumed."
        : "The gateway session and its history will be removed. This action cannot be undone.";

  return (
    <div className="space-y-4">
      <DashboardDialog
        open={Boolean(pendingAction)}
        onOpenChange={(open) => {
          if (!open && !actingKey) {
            setPendingAction(null);
            setDialogError(null);
          }
        }}
        title={`${pendingVerb} session`}
        description={`Apply the ${pendingAction?.action ?? "selected"} action to this gateway session.`}
        footer={
          <>
            <button
              type="button"
              data-autofocus
              onClick={() => {
                setPendingAction(null);
                setDialogError(null);
              }}
              disabled={Boolean(actingKey)}
              className={`${secondaryButtonClass} w-full text-sm sm:w-auto`}
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={() => void confirmSessionAction()}
              disabled={Boolean(actingKey)}
              className={pendingIsDestructive ? destructiveConfirmButtonClass : confirmButtonClass}
            >
              {actingKey ? `${pendingVerb}…` : `${pendingVerb} Session`}
            </button>
          </>
        }
      >
        <div aria-busy={Boolean(actingKey)} className="space-y-4 text-start">
          <div className="rounded-xl border border-white/10 bg-black/20 p-3">
            <p className="text-sm font-semibold text-white">{pendingAction?.session.agent}</p>
            <p dir="ltr" className="mt-1 break-all text-start font-mono text-xs text-slate-400">
              {pendingAction?.session.key}
            </p>
          </div>
          <p className="text-sm leading-6 text-slate-300">{pendingConsequence}</p>
          {dialogError ? (
            <div role="alert" className="rounded-xl border border-rose-400/20 bg-rose-400/10 px-4 py-3 text-sm text-rose-200">
              Session action failed: {dialogError}
            </div>
          ) : null}
        </div>
      </DashboardDialog>

      {error ? (
        <div role="alert" aria-live="assertive" className="rounded-xl border border-rose-400/20 bg-rose-400/10 px-4 py-3 text-sm text-rose-200">
          Session refresh failed: {error}. Existing records are retained.
        </div>
      ) : null}
      {actionError && !pendingAction ? (
        <div role="alert" aria-live="assertive" className="rounded-xl border border-rose-400/20 bg-rose-400/10 px-4 py-3 text-sm text-rose-200">
          Session action failed: {actionError}
        </div>
      ) : null}
      {actionNotice ? (
        <div role="status" aria-live="polite" aria-atomic="true" className="rounded-xl border border-emerald-400/20 bg-emerald-400/10 px-4 py-3 text-sm text-emerald-200">
          {actionNotice}
        </div>
      ) : null}
      {sessionCoverageNote ? (
        <div role="status" className="rounded-xl border border-amber-400/20 bg-amber-400/10 px-4 py-3 text-sm text-amber-100">
          {sessionCoverageNote}
        </div>
      ) : null}

      <LiveKpiGrid>
        <LiveStatCard
          label="Sessions discovered"
          value={sessionCoverageNote ? "Unknown" : String(sessions.length)}
          detail={
            sessionCoverageNote
              ? `${sessions.length} identified records are shown; the total and active count are partial.`
              : `${activeSessions} sessions currently marked active.`
          }
          status={asDashboardStatus(
            sessionCoverageNote ? "warning" : activeSessions > 0 ? "running" : "idle",
          )}
        />
        <LiveStatCard
          label="Channels"
          value={String(Math.max(channels.length, enabledChannels))}
          detail={
            assistant
              ? `${enabledChannels} enabled OpenClaw channels on ${assistant.workspace}.`
              : "Channel coverage appears when assistant overview is available."
          }
        />
        <LiveStatCard
          label="Sources"
          value={sessionCoverageNote ? "Unknown" : String(sources.length)}
          detail={
            sessionCoverageNote
              ? "Source coverage is partial because unidentified session records were omitted."
              : sources.length > 0
                ? sources.join(", ")
                : "No session sources returned yet."
          }
        />
        <LiveStatCard
          label="Gateway"
          value={gatewayStatus}
          detail={assistant?.gateway.gateway_url || "Gateway URL has not been synced yet."}
          status={asDashboardStatus(gatewayStatus)}
        />
      </LiveKpiGrid>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.1fr)_minmax(340px,0.9fr)]">
        <LivePanel
          title="Session registry"
          meta={`${sessions.length} records`}
          action={(
            <button className={secondaryButtonClass} onClick={() => void loadSessions(false)} disabled={refreshing}>
              {refreshing ? "Refreshing…" : "Refresh"}
            </button>
          )}
        >
          {sessions.length === 0 ? (
            <LiveEmptyState
              title={
                sessionCoverageNote
                  ? "Session registry coverage is incomplete"
                  : "No sessions discovered yet"
              }
              message={
                sessionCoverageNote
                  ? "Unidentified upstream records were omitted, so this empty registry is not a verified zero."
                  : "Once a runtime reports activity, live sessions will appear here."
              }
            />
          ) : (
            <div className="space-y-3">
              {sessions.map((session) => {
                const acting = actingKey === session.key;
                return (
                  <div key={session.id} className="rounded-xl border border-white/10 bg-white/[0.02] p-4">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="truncate text-sm font-medium text-white">{session.agent}</p>
                        <p className="mt-1 break-all text-xs text-slate-500">{session.key}</p>
                        <p className="mt-1 text-xs text-slate-500">
                          {session.channel} · {session.kind} · {session.model}
                        </p>
                      </div>
                      <StatusBadge
                        status={asDashboardStatus(session.active ? "running" : session.state)}
                        label={session.state}
                      />
                    </div>

                    <div className="mt-3 grid gap-2 text-xs text-slate-500 sm:grid-cols-2">
                      <div>source {session.source}</div>
                      <div>tokens {session.tokens}</div>
                      <div>age {session.age}</div>
                      <div>
                        last activity {session.lastActivity ? formatRelativeTime(session.lastActivity) : "Not recorded"}
                      </div>
                    </div>

                    {session.flags.length > 0 ? (
                      <div className="mt-3 flex flex-wrap gap-2">
                        {session.flags.map((flag) => (
                          <span
                            key={`${session.id}-${flag}`}
                            className="rounded-full border border-white/10 bg-black/20 px-2 py-1 text-[10px] uppercase tracking-[0.16em] text-slate-400"
                          >
                            {flag}
                          </span>
                        ))}
                      </div>
                    ) : null}

                    {session.controllable ? (
                      <div className="mt-4 flex flex-wrap gap-2 border-t border-white/10 pt-3">
                        <button className={secondaryButtonClass} onClick={() => void loadTranscript(session)} disabled={acting}>
                          Transcript
                        </button>
                        <button
                          className={secondaryButtonClass}
                          onClick={() => requestSessionAction(session, session.active ? "pause" : "resume")}
                          disabled={acting}
                        >
                          {session.active ? "Pause" : "Resume"}
                        </button>
                        <button className={dangerButtonClass} onClick={() => requestSessionAction(session, "kill")} disabled={acting}>
                          Kill
                        </button>
                        <button className={dangerButtonClass} onClick={() => requestSessionAction(session, "delete")} disabled={acting}>
                          {acting ? "Working…" : "Delete"}
                        </button>
                      </div>
                    ) : (
                      <p className="mt-4 border-t border-white/10 pt-3 text-xs text-slate-500">
                        This local source exposes metadata only; gateway controls are unavailable.
                      </p>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </LivePanel>

        <LivePanel title="Gateway posture" meta={assistant ? assistant.runtime : "assistant overview"}>
          {!assistant ? (
            <LiveEmptyState
              title="Assistant overview not returned"
              message="No tracked OpenClaw assistant overview was returned for this operator."
            />
          ) : (
            <div className="space-y-3">
              <div className="rounded-xl border border-white/10 bg-white/[0.02] p-4">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="text-sm font-medium text-white">{assistant.name}</p>
                    <p className="mt-1 text-xs text-slate-500">{assistant.assistant_id}</p>
                  </div>
                  <StatusBadge status={asDashboardStatus(gatewayStatus)} label={gatewayStatus} />
                </div>
              </div>
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="rounded-xl border border-white/10 bg-black/20 px-3 py-3">
                  <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-500">Workspace</p>
                  <p className="mt-2 text-sm text-white">{assistant.workspace}</p>
                </div>
                <div className="rounded-xl border border-white/10 bg-black/20 px-3 py-3">
                  <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-500">Session count</p>
                  <p className="mt-2 text-sm text-white">{assistant.session_count}</p>
                </div>
                <div className="rounded-xl border border-white/10 bg-black/20 px-3 py-3">
                  <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-500">Gateway URL</p>
                  <p className="mt-2 break-all text-sm text-white">{assistant.gateway.gateway_url || "Not synced"}</p>
                </div>
                <div className="rounded-xl border border-white/10 bg-black/20 px-3 py-3">
                  <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-500">Last activity</p>
                  <p className="mt-2 text-sm text-white">
                    {assistant.last_activity ? formatDateTime(assistant.last_activity) : "Not recorded"}
                  </p>
                </div>
              </div>
            </div>
          )}
        </LivePanel>
      </div>

      {selectedSession ? (
        <LivePanel title="Session transcript" meta={`${transcript?.total_count ?? 0} messages`}>
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-sm font-medium text-white">{selectedSession.agent}</p>
              <p className="mt-1 break-all text-xs text-slate-500">{selectedSession.key}</p>
            </div>
            <button className={secondaryButtonClass} onClick={() => void loadTranscript(selectedSession)} disabled={transcriptLoading}>
              {transcriptLoading ? "Loading…" : "Reload transcript"}
            </button>
          </div>
          {transcriptError ? (
            <div role="alert" className="rounded-xl border border-rose-400/20 bg-rose-400/10 px-4 py-3 text-sm text-rose-200">
              Transcript unavailable: {transcriptError}
            </div>
          ) : transcriptLoading ? (
            <p className="text-sm text-slate-400">Loading the canonical gateway transcript…</p>
          ) : !transcript || transcript.messages.length === 0 ? (
            <LiveEmptyState title="No transcript messages" message="The gateway returned an empty history for this session." />
          ) : (
            <div className="max-h-[640px] space-y-3 overflow-y-auto pr-1">
              {transcript.messages.map((message, index) => {
                const role = pickString(message, ["role", "author", "type"], "message");
                const timestamp = toIsoTimestamp(message.timestamp ?? message.created_at);
                return (
                  <article key={`${transcript.session_key}-${index}`} className="rounded-xl border border-white/10 bg-black/20 p-4">
                    <div className="flex items-center justify-between gap-3">
                      <p className="text-xs font-semibold uppercase tracking-[0.16em] text-cyan-300">{role}</p>
                      {timestamp ? <time className="text-xs text-slate-500">{formatDateTime(timestamp)}</time> : null}
                    </div>
                    <p className="mt-3 whitespace-pre-wrap break-words text-sm leading-6 text-slate-300">
                      {transcriptText(message)}
                    </p>
                  </article>
                );
              })}
            </div>
          )}
        </LivePanel>
      ) : null}
    </div>
  );
}
