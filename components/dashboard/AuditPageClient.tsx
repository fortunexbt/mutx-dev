"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  ChevronLeft,
  ChevronRight,
  Download,
  Eye,
  RotateCw,
  ShieldX,
} from "lucide-react";

import { ApiRequestError, readJson } from "@/components/app/http";
import { DashboardDialog } from "@/components/dashboard/DashboardDialog";
import {
  LiveAuthRequired,
  LiveEmptyState,
  LiveErrorState,
  LiveKpiGrid,
  LiveLoading,
  LivePanel,
  LiveStatCard,
  asDashboardStatus,
  formatDateTime,
  formatRelativeTime,
} from "@/components/dashboard/livePrimitives";
import {
  formatOperatorContext,
  safeOperatorFileSegment,
  summarizeOperatorContext,
} from "@/components/dashboard/operatorContext";
import { StatusBadge } from "@/components/dashboard/StatusBadge";

const PAGE_SIZE = 25;
const EVENT_TYPES = [
  "AGENT_START",
  "LLM_CALL",
  "TOOL_CALL",
  "POLICY_CHECK",
  "GUARDRAIL_TRIGGER",
  "AGENT_END",
] as const;

interface AuditEvent {
  event_id: string;
  agent_id: string;
  session_id: string;
  run_id?: string | null;
  span_id?: string | null;
  parent_span_id?: string | null;
  event_type: string;
  payload: Record<string, unknown>;
  timestamp: string;
  trace_id?: string | null;
  actor_type: string;
  actor_id?: string | null;
  actor_display?: string | null;
  policy_decision_id?: string | null;
  policy_refs?: string[];
  approval_id?: string | null;
  cost_record?: Record<string, unknown> | null;
  redaction_status: string;
  schema_version: string;
  previous_hash?: string | null;
  integrity_hash?: string | null;
}

interface AuditEventsEnvelope {
  events: AuditEvent[];
  total?: number | null;
}

interface AuditEvidenceExport {
  schema_version: string;
  algorithm: string;
  run_id?: string | null;
  session_id?: string | null;
  event_count: number;
  chain_root?: string | null;
  verified: boolean;
  errors: string[];
  events: AuditEvent[];
}

interface AuditFilters {
  agentId: string;
  sessionId: string;
  runId: string;
  eventType: string;
  startAt: string;
  endAt: string;
}

type ViewState = "loading" | "ready" | "auth" | "forbidden" | "error";

const EMPTY_FILTERS: AuditFilters = {
  agentId: "",
  sessionId: "",
  runId: "",
  eventType: "",
  startAt: "",
  endAt: "",
};

const inputClassName =
  "min-h-11 w-full rounded-[4px] border border-[#3a3933] bg-[#0d0e0b] px-3 text-sm text-[#eee9dc] outline-none transition placeholder:text-[#6f6a61] focus:border-[#ff7545] focus:ring-1 focus:ring-[#ff7545]";

function toIsoTimestamp(value: string) {
  if (!value) return null;
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? null : parsed.toISOString();
}

function eventStatus(eventType: string) {
  if (eventType === "GUARDRAIL_TRIGGER") return "error" as const;
  if (eventType === "POLICY_CHECK") return "warning" as const;
  if (eventType === "AGENT_END") return "success" as const;
  if (eventType === "AGENT_START") return "running" as const;
  return asDashboardStatus(eventType);
}

function actorLabel(event: AuditEvent) {
  return event.actor_display || event.actor_id || event.agent_id || "Unknown actor";
}

function buildAuditEventsUrl(filters: AuditFilters, skip: number) {
  const query = new URLSearchParams({
    limit: String(PAGE_SIZE + 1),
    skip: String(skip),
  });
  if (filters.agentId.trim()) query.set("agent_id", filters.agentId.trim());
  if (filters.sessionId.trim()) query.set("session_id", filters.sessionId.trim());
  if (filters.runId.trim()) query.set("run_id", filters.runId.trim());
  if (filters.eventType) query.set("event_type", filters.eventType);

  const startAt = toIsoTimestamp(filters.startAt);
  const endAt = toIsoTimestamp(filters.endAt);
  if (startAt) query.set("time_range_start", startAt);
  if (endAt) query.set("time_range_end", endAt);

  return `/api/dashboard/audit/events?${query.toString()}`;
}

export function AuditPageClient() {
  const [viewState, setViewState] = useState<ViewState>("loading");
  const [error, setError] = useState<string | null>(null);
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [total, setTotal] = useState<number | null>(null);
  const [hasNextPage, setHasNextPage] = useState(false);
  const [draftFilters, setDraftFilters] = useState<AuditFilters>(EMPTY_FILTERS);
  const [filters, setFilters] = useState<AuditFilters>(EMPTY_FILTERS);
  const [skip, setSkip] = useState(0);
  const [reloadToken, setReloadToken] = useState(0);
  const [selectedEvent, setSelectedEvent] = useState<AuditEvent | null>(null);
  const [exporting, setExporting] = useState(false);
  const [exportMessage, setExportMessage] = useState<string | null>(null);
  const [exportError, setExportError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();

    async function loadEvents() {
      setViewState("loading");
      setError(null);

      try {
        const response = await readJson<AuditEventsEnvelope>(
          buildAuditEventsUrl(filters, skip),
          { signal: controller.signal },
        );
        const returnedEvents = Array.isArray(response.events) ? response.events : [];
        const nextTotal = typeof response.total === "number" ? response.total : null;

        setEvents(returnedEvents.slice(0, PAGE_SIZE));
        setTotal(nextTotal);
        setHasNextPage(
          nextTotal === null
            ? returnedEvents.length > PAGE_SIZE
            : skip + PAGE_SIZE < nextTotal,
        );
        setViewState("ready");
      } catch (loadError) {
        if (controller.signal.aborted) return;
        if (loadError instanceof ApiRequestError && loadError.status === 401) {
          setViewState("auth");
        } else if (loadError instanceof ApiRequestError && loadError.status === 403) {
          setViewState("forbidden");
        } else {
          setError(loadError instanceof Error ? loadError.message : "Failed to load audit events");
          setViewState("error");
        }
      }
    }

    void loadEvents();
    return () => controller.abort();
  }, [filters, reloadToken, skip]);

  const exportContext = useMemo(() => {
    const runId = filters.runId.trim();
    const sessionId = filters.sessionId.trim();
    if (Boolean(runId) === Boolean(sessionId)) return null;
    return runId
      ? { parameter: "run_id", label: "run", value: runId }
      : { parameter: "session_id", label: "session", value: sessionId };
  }, [filters.runId, filters.sessionId]);

  const pageNumber = Math.floor(skip / PAGE_SIZE) + 1;
  const visibleRange = events.length === 0 ? "0" : `${skip + 1}–${skip + events.length}`;
  const chainedEvents = events.filter((event) => Boolean(event.integrity_hash)).length;
  const attributableEvents = events.filter((event) => Boolean(event.actor_id || event.agent_id)).length;

  function applyFilters(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSkip(0);
    setFilters({ ...draftFilters });
    setExportMessage(null);
    setExportError(null);
  }

  function clearFilters() {
    setDraftFilters(EMPTY_FILTERS);
    setFilters(EMPTY_FILTERS);
    setSkip(0);
    setExportMessage(null);
    setExportError(null);
  }

  async function exportEvidence() {
    if (!exportContext || exporting) return;

    setExporting(true);
    setExportMessage(null);
    setExportError(null);
    try {
      const query = new URLSearchParams({
        [exportContext.parameter]: exportContext.value,
      });
      const evidence = await readJson<AuditEvidenceExport>(
        `/api/dashboard/audit/export?${query.toString()}`,
      );
      const blob = new Blob([JSON.stringify(evidence, null, 2)], {
        type: "application/json",
      });
      const objectUrl = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = objectUrl;
      anchor.download = `mutx-audit-${exportContext.label}-${safeOperatorFileSegment(exportContext.value)}.json`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(objectUrl);
      setExportMessage(
        `${evidence.event_count} events exported · chain ${evidence.verified ? "verified" : "verification failed"}`,
      );
    } catch (exportFailure) {
      if (exportFailure instanceof ApiRequestError && exportFailure.status === 403) {
        setViewState("forbidden");
      } else if (exportFailure instanceof ApiRequestError && exportFailure.status === 401) {
        setViewState("auth");
      } else {
        setExportError(
          exportFailure instanceof Error ? exportFailure.message : "Failed to export evidence",
        );
      }
    } finally {
      setExporting(false);
    }
  }

  if (viewState === "loading") return <LiveLoading title="Audit evidence" />;
  if (viewState === "auth") {
    return (
      <LiveAuthRequired
        title="Operator session required"
        message="Sign in with an audit-authorized account to inspect attributable control-plane evidence."
      />
    );
  }
  if (viewState === "forbidden") {
    return (
      <LivePanel title="Audit access forbidden" meta="403 · role required">
        <div role="alert" className="flex items-start gap-3 text-sm text-[#c8c0b0]">
          <ShieldX className="mt-0.5 h-5 w-5 shrink-0 text-[#ff9b96]" aria-hidden="true" />
          <div>
            <p className="font-medium text-[#eee9dc]">This account cannot read the audit ledger.</p>
            <p className="mt-1 leading-6 text-[#999284]">
              Ask an administrator for the ADMIN or AUDIT_ADMIN role. Authentication succeeded,
              but the control plane denied this operation.
            </p>
          </div>
        </div>
      </LivePanel>
    );
  }
  if (viewState === "error") {
    return (
      <div className="space-y-3">
        <LiveErrorState title="Audit ledger unavailable" message={error || "Failed to load audit events"} />
        <button
          type="button"
          onClick={() => setReloadToken((value) => value + 1)}
          className="inline-flex min-h-11 items-center gap-2 rounded-[4px] border border-[#48463e] bg-[#151612] px-4 text-sm text-[#d8d1c4] transition hover:border-[#777268] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#ff7545]"
        >
          <RotateCw className="h-4 w-4" aria-hidden="true" />
          Retry audit query
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <LiveKpiGrid>
        <LiveStatCard
          label="Visible events"
          value={String(events.length)}
          detail={`Records ${visibleRange}${total === null ? " in the current query window" : ` of ${total}`}.`}
        />
        <LiveStatCard
          label="Attributable"
          value={String(attributableEvents)}
          detail="Events with a concrete actor or agent identifier."
          status={attributableEvents === events.length ? "success" : "warning"}
        />
        <LiveStatCard
          label="Hash chained"
          value={String(chainedEvents)}
          detail="Visible events carrying an integrity digest."
          status={chainedEvents === events.length && events.length > 0 ? "success" : "idle"}
        />
        <LiveStatCard
          label="Page"
          value={String(pageNumber).padStart(2, "0")}
          detail={hasNextPage ? "More matching evidence is available." : "End of the current result set."}
        />
      </LiveKpiGrid>

      <LivePanel title="Evidence query" meta="server-side filters">
        <form onSubmit={applyFilters} className="grid gap-3 lg:grid-cols-3">
          <label className="min-w-0 text-xs text-[#999284]">
            <span className="mb-1.5 block font-mono uppercase tracking-[0.12em]">Agent ID</span>
            <input
              value={draftFilters.agentId}
              onChange={(event) => setDraftFilters((current) => ({ ...current, agentId: event.currentTarget.value }))}
              className={inputClassName}
              placeholder="agent-…"
              autoComplete="off"
            />
          </label>
          <label className="min-w-0 text-xs text-[#999284]">
            <span className="mb-1.5 block font-mono uppercase tracking-[0.12em]">Session ID</span>
            <input
              value={draftFilters.sessionId}
              onChange={(event) => setDraftFilters((current) => ({ ...current, sessionId: event.currentTarget.value }))}
              className={inputClassName}
              placeholder="session-…"
              autoComplete="off"
            />
          </label>
          <label className="min-w-0 text-xs text-[#999284]">
            <span className="mb-1.5 block font-mono uppercase tracking-[0.12em]">Run ID</span>
            <input
              value={draftFilters.runId}
              onChange={(event) => setDraftFilters((current) => ({ ...current, runId: event.currentTarget.value }))}
              className={inputClassName}
              placeholder="run-…"
              autoComplete="off"
            />
          </label>
          <label className="min-w-0 text-xs text-[#999284]">
            <span className="mb-1.5 block font-mono uppercase tracking-[0.12em]">Event type</span>
            <select
              value={draftFilters.eventType}
              onChange={(event) => setDraftFilters((current) => ({ ...current, eventType: event.currentTarget.value }))}
              className={inputClassName}
            >
              <option value="">All event types</option>
              {EVENT_TYPES.map((eventType) => (
                <option key={eventType} value={eventType}>{eventType}</option>
              ))}
            </select>
          </label>
          <label className="min-w-0 text-xs text-[#999284]">
            <span className="mb-1.5 block font-mono uppercase tracking-[0.12em]">From</span>
            <input
              type="datetime-local"
              value={draftFilters.startAt}
              onChange={(event) => setDraftFilters((current) => ({ ...current, startAt: event.currentTarget.value }))}
              className={inputClassName}
            />
          </label>
          <label className="min-w-0 text-xs text-[#999284]">
            <span className="mb-1.5 block font-mono uppercase tracking-[0.12em]">Until</span>
            <input
              type="datetime-local"
              value={draftFilters.endAt}
              onChange={(event) => setDraftFilters((current) => ({ ...current, endAt: event.currentTarget.value }))}
              className={inputClassName}
            />
          </label>
          <div className="flex flex-wrap gap-2 lg:col-span-3">
            <button
              type="submit"
              className="inline-flex min-h-11 items-center justify-center rounded-[4px] border border-[#ff7545] bg-[#ff571c] px-4 text-sm font-semibold text-[#090a08] transition hover:bg-[#ff7545] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#ffb091]"
            >
              Apply query
            </button>
            <button
              type="button"
              onClick={clearFilters}
              className="inline-flex min-h-11 items-center justify-center rounded-[4px] border border-[#48463e] bg-[#151612] px-4 text-sm text-[#d8d1c4] transition hover:border-[#777268] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#ff7545]"
            >
              Clear filters
            </button>
          </div>
        </form>
      </LivePanel>

      <LivePanel
        title="Attributable event ledger"
        meta={`${visibleRange}${total === null ? "" : ` / ${total}`}`}
        action={
          <button
            type="button"
            onClick={exportEvidence}
            disabled={!exportContext || exporting}
            aria-describedby="audit-export-requirement"
            className="inline-flex min-h-10 items-center gap-2 rounded-[4px] border border-[#3d654f] bg-[#102019] px-3 text-xs font-semibold text-[#78e3b4] transition hover:border-[#78e3b4] disabled:cursor-not-allowed disabled:border-[#34342e] disabled:bg-[#151612] disabled:text-[#777268] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#78e3b4]"
          >
            <Download className="h-4 w-4" aria-hidden="true" />
            {exporting ? "Exporting…" : "Export evidence"}
          </button>
        }
      >
        <div id="audit-export-requirement" className="mb-4 text-xs leading-5 text-[#8d867a]">
          Evidence export requires exactly one applied Run ID or Session ID and exports that
          complete verified chain, independent of the other list filters.
        </div>
        {exportMessage ? <p role="status" className="mb-4 text-sm text-[#78e3b4]">{exportMessage}</p> : null}
        {exportError ? <p role="alert" className="mb-4 text-sm text-[#ff9b96]">{exportError}</p> : null}

        {events.length === 0 ? (
          <LiveEmptyState
            title="No matching audit events"
            message="The audit service returned an empty event envelope for this filter set. Clear or broaden the query to inspect other evidence."
          />
        ) : (
          <div className="space-y-2.5">
            {events.map((event) => (
              <article
                key={event.event_id}
                className="grid min-w-0 gap-3 rounded-[4px] border border-[#34342e] bg-[#10110e] p-3.5 sm:p-4 md:grid-cols-[minmax(0,1fr)_auto] md:items-center"
              >
                <div className="min-w-0">
                  <div className="flex min-w-0 flex-wrap items-center gap-2">
                    <StatusBadge status={eventStatus(event.event_type)} label={event.event_type} />
                    <span className="font-mono text-[11px] text-[#8d867a]">{formatRelativeTime(event.timestamp)}</span>
                  </div>
                  <p className="mt-2 break-words text-sm font-medium text-[#eee9dc]">
                    {actorLabel(event)}
                    <span className="font-normal text-[#777268]"> · {event.actor_type}</span>
                  </p>
                  <p className="mt-1 break-all font-mono text-[11px] leading-5 text-[#8d867a]">
                    agent {event.agent_id} · session {event.session_id}
                    {event.run_id ? ` · run ${event.run_id}` : ""}
                  </p>
                  <p className="mt-2 break-words text-xs leading-5 text-[#999284]">
                    {summarizeOperatorContext(event.payload)}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => setSelectedEvent(event)}
                  aria-label={`Inspect ${event.event_type} event ${event.event_id}`}
                  className="inline-flex min-h-11 items-center justify-center gap-2 rounded-[4px] border border-[#48463e] bg-[#151612] px-3 text-xs font-semibold text-[#d8d1c4] transition hover:border-[#777268] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#ff7545] md:justify-self-end"
                >
                  <Eye className="h-4 w-4" aria-hidden="true" />
                  Inspect event
                </button>
              </article>
            ))}
          </div>
        )}

        <nav aria-label="Audit event pages" className="mt-5 flex flex-wrap items-center justify-between gap-3 border-t border-[#34342e] pt-4">
          <p className="font-mono text-xs text-[#8d867a]">Page {pageNumber} · records {visibleRange}</p>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => setSkip((value) => Math.max(0, value - PAGE_SIZE))}
              disabled={skip === 0}
              className="inline-flex min-h-11 items-center gap-1 rounded-[4px] border border-[#48463e] bg-[#151612] px-3 text-xs text-[#d8d1c4] disabled:cursor-not-allowed disabled:opacity-40 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#ff7545]"
            >
              <ChevronLeft className="h-4 w-4" aria-hidden="true" /> Previous
            </button>
            <button
              type="button"
              onClick={() => setSkip((value) => value + PAGE_SIZE)}
              disabled={!hasNextPage}
              className="inline-flex min-h-11 items-center gap-1 rounded-[4px] border border-[#48463e] bg-[#151612] px-3 text-xs text-[#d8d1c4] disabled:cursor-not-allowed disabled:opacity-40 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#ff7545]"
            >
              Next <ChevronRight className="h-4 w-4" aria-hidden="true" />
            </button>
          </div>
        </nav>
      </LivePanel>

      <DashboardDialog
        open={Boolean(selectedEvent)}
        onOpenChange={(open) => { if (!open) setSelectedEvent(null); }}
        title={selectedEvent?.event_type || "Audit event"}
        description={selectedEvent ? `Event ${selectedEvent.event_id}` : undefined}
        className="max-h-[92vh] max-w-3xl"
      >
        {selectedEvent ? (
          <div className="max-h-[65vh] space-y-5 overflow-y-auto pr-1">
            <dl className="grid gap-3 text-xs sm:grid-cols-2">
              {[
                ["Actor", actorLabel(selectedEvent)],
                ["Actor type", selectedEvent.actor_type],
                ["Agent", selectedEvent.agent_id],
                ["Session", selectedEvent.session_id],
                ["Run", selectedEvent.run_id || "Not attached"],
                ["Timestamp", formatDateTime(selectedEvent.timestamp)],
                ["Trace", selectedEvent.trace_id || "Not attached"],
                ["Approval", selectedEvent.approval_id || "Not attached"],
                ["Redaction", selectedEvent.redaction_status],
                ["Schema", selectedEvent.schema_version],
              ].map(([label, value]) => (
                <div key={label} className="min-w-0 rounded-[4px] border border-[#34342e] bg-[#0d0e0b] p-3">
                  <dt className="font-mono uppercase tracking-[0.12em] text-[#777268]">{label}</dt>
                  <dd className="mt-1 break-all text-[#d8d1c4]">{value}</dd>
                </div>
              ))}
            </dl>

            <div>
              <h3 className="font-mono text-xs uppercase tracking-[0.12em] text-[#8d867a]">Redacted event context</h3>
              <pre className="mt-2 max-h-80 overflow-auto whitespace-pre-wrap break-words rounded-[4px] border border-[#34342e] bg-[#090a08] p-3 font-mono text-[11px] leading-5 text-[#c8c0b0]">
                {formatOperatorContext(selectedEvent.payload)}
              </pre>
            </div>

            {selectedEvent.cost_record ? (
              <div>
                <h3 className="font-mono text-xs uppercase tracking-[0.12em] text-[#8d867a]">Redacted cost record</h3>
                <pre className="mt-2 overflow-auto whitespace-pre-wrap break-words rounded-[4px] border border-[#34342e] bg-[#090a08] p-3 font-mono text-[11px] leading-5 text-[#c8c0b0]">
                  {formatOperatorContext(selectedEvent.cost_record)}
                </pre>
              </div>
            ) : null}

            <div className="rounded-[4px] border border-[#34342e] bg-[#10110e] p-3 text-xs leading-5 text-[#8d867a]">
              Integrity hash: <span className="break-all font-mono text-[#c8c0b0]">{selectedEvent.integrity_hash || "Not recorded"}</span>
            </div>
          </div>
        ) : null}
      </DashboardDialog>
    </div>
  );
}
