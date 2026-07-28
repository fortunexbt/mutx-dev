"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  ChevronLeft,
  ChevronRight,
  Eye,
  RotateCw,
  ShieldX,
  UserRoundCheck,
} from "lucide-react";

import { ApiRequestError, readJson, writeJson } from "@/components/app/http";
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
  summarizeOperatorContext,
} from "@/components/dashboard/operatorContext";
import { StatusBadge } from "@/components/dashboard/StatusBadge";

const PAGE_SIZE = 20;
const APPROVAL_STATUSES = ["PENDING", "APPROVED", "REJECTED", "EXPIRED"] as const;

interface ApprovalRequest {
  id: string;
  owner_id: string;
  reviewer_id: string | null;
  can_resolve: boolean;
  agent_id: string;
  session_id: string;
  action_type: string;
  payload: Record<string, unknown>;
  status: string;
  requester: string;
  approver?: string | null;
  created_at: string;
  resolved_at?: string | null;
  comment?: string | null;
}

interface ApprovalListEnvelope {
  items: ApprovalRequest[];
  total: number;
  skip: number;
  limit: number;
  status?: string | null;
  agent_id?: string | null;
}

type ViewState = "loading" | "ready" | "auth" | "forbidden" | "error";
type Decision = "approve" | "reject";
type Notice = { tone: "success" | "error"; message: string };

const inputClassName =
  "min-h-11 w-full rounded-[4px] border border-[#3a3933] bg-[#0d0e0b] px-3 text-sm text-[#eee9dc] outline-none transition placeholder:text-[#6f6a61] focus:border-[#ff7545] focus:ring-1 focus:ring-[#ff7545]";

function buildApprovalsUrl(statusFilter: string, agentId: string, skip: number) {
  const query = new URLSearchParams({
    limit: String(PAGE_SIZE),
    skip: String(skip),
  });
  if (statusFilter) query.set("status", statusFilter);
  if (agentId.trim()) query.set("agent_id", agentId.trim());
  return `/api/dashboard/approvals?${query.toString()}`;
}

export function ApprovalsPageClient() {
  const [viewState, setViewState] = useState<ViewState>("loading");
  const [error, setError] = useState<string | null>(null);
  const [approvals, setApprovals] = useState<ApprovalRequest[]>([]);
  const [total, setTotal] = useState(0);
  const [statusFilter, setStatusFilter] = useState("");
  const [draftAgentId, setDraftAgentId] = useState("");
  const [agentId, setAgentId] = useState("");
  const [skip, setSkip] = useState(0);
  const [reloadToken, setReloadToken] = useState(0);
  const [selectedApproval, setSelectedApproval] = useState<ApprovalRequest | null>(null);
  const [comment, setComment] = useState("");
  const [decisionPending, setDecisionPending] = useState<Decision | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [notice, setNotice] = useState<Notice | null>(null);

  useEffect(() => {
    const controller = new AbortController();

    async function loadApprovals() {
      setViewState("loading");
      setError(null);

      try {
        const response = await readJson<ApprovalListEnvelope>(
          buildApprovalsUrl(statusFilter, agentId, skip),
          { signal: controller.signal },
        );
        setApprovals(Array.isArray(response.items) ? response.items : []);
        setTotal(Number.isFinite(response.total) ? response.total : 0);
        setViewState("ready");
      } catch (loadError) {
        if (controller.signal.aborted) return;
        if (loadError instanceof ApiRequestError && loadError.status === 401) {
          setViewState("auth");
        } else if (loadError instanceof ApiRequestError && loadError.status === 403) {
          setViewState("forbidden");
        } else {
          setError(loadError instanceof Error ? loadError.message : "Failed to load approvals");
          setViewState("error");
        }
      }
    }

    void loadApprovals();
    return () => controller.abort();
  }, [agentId, reloadToken, skip, statusFilter]);

  const currentPagePending = useMemo(
    () => approvals.filter((approval) => approval.status === "PENDING").length,
    [approvals],
  );
  const currentPageResolved = useMemo(
    () => approvals.filter((approval) => ["APPROVED", "REJECTED"].includes(approval.status)).length,
    [approvals],
  );
  const pageNumber = Math.floor(skip / PAGE_SIZE) + 1;
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const hasNextPage = skip + approvals.length < total;
  const visibleRange = approvals.length === 0 ? "0" : `${skip + 1}–${skip + approvals.length}`;

  function applyAgentFilter(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSkip(0);
    setAgentId(draftAgentId.trim());
    setNotice(null);
  }

  function clearFilters() {
    setStatusFilter("");
    setDraftAgentId("");
    setAgentId("");
    setSkip(0);
    setNotice(null);
  }

  function inspectApproval(approval: ApprovalRequest) {
    setSelectedApproval(approval);
    setComment("");
    setActionError(null);
  }

  async function reloadCanonicalEnvelope(selectedId: string) {
    const response = await readJson<ApprovalListEnvelope>(
      buildApprovalsUrl(statusFilter, agentId, skip),
    );
    const canonicalItems = Array.isArray(response.items) ? response.items : [];
    const canonicalTotal = Number.isFinite(response.total) ? response.total : 0;

    setApprovals(canonicalItems);
    setTotal(canonicalTotal);
    setSelectedApproval(canonicalItems.find((item) => item.id === selectedId) ?? null);

    if (canonicalTotal > 0 && skip >= canonicalTotal) {
      setSkip(Math.floor((canonicalTotal - 1) / PAGE_SIZE) * PAGE_SIZE);
    }
  }

  async function resolveApproval(decision: Decision) {
    if (
      !selectedApproval ||
      selectedApproval.status !== "PENDING" ||
      !selectedApproval.can_resolve ||
      decisionPending
    ) return;

    const selectedId = selectedApproval.id;
    let decisionAccepted = false;
    setDecisionPending(decision);
    setActionError(null);
    setNotice(null);

    try {
      await writeJson<ApprovalRequest>(
        `/api/dashboard/approvals/${encodeURIComponent(selectedId)}/${decision}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ comment: comment.trim() || null }),
        },
      );
      decisionAccepted = true;
      await reloadCanonicalEnvelope(selectedId);
      setNotice({
        tone: "success",
        message: `${decision === "approve" ? "Approval" : "Rejection"} recorded and the canonical queue reloaded.`,
      });
    } catch (decisionError) {
      if (decisionAccepted) {
        const message = "Decision was accepted, but the canonical approval envelope could not be reloaded. Retry the queue refresh before taking another action.";
        setActionError(message);
        setNotice({ tone: "error", message });
      } else if (decisionError instanceof ApiRequestError && decisionError.status === 401) {
        setViewState("auth");
      } else if (decisionError instanceof ApiRequestError && decisionError.status === 403) {
        const message = decisionError.message || "You are no longer eligible to resolve this request.";
        setActionError(message);
        setNotice({ tone: "error", message });
      } else if (
        decisionError instanceof ApiRequestError &&
        (decisionError.status === 400 || decisionError.status === 409)
      ) {
        const message = "Conflict: this request is no longer pending. The latest canonical state has been requested.";
        setActionError(message);
        setNotice({ tone: "error", message });
        try {
          await reloadCanonicalEnvelope(selectedId);
        } catch {
          setReloadToken((value) => value + 1);
        }
      } else {
        const message = decisionError instanceof Error ? decisionError.message : "Failed to resolve approval";
        setActionError(message);
        setNotice({ tone: "error", message });
      }
    } finally {
      setDecisionPending(null);
    }
  }

  if (viewState === "loading") return <LiveLoading title="Approval queue" />;
  if (viewState === "auth") {
    return (
      <LiveAuthRequired
        title="Operator session required"
        message="Sign in to review requester intent and resolve approval-gated actions."
      />
    );
  }
  if (viewState === "forbidden") {
    return (
      <LivePanel title="Approval access forbidden" meta="403 · permission denied">
        <div role="alert" className="flex items-start gap-3 text-sm text-[#c8c0b0]">
          <ShieldX className="mt-0.5 h-5 w-5 shrink-0 text-[#ff9b96]" aria-hidden="true" />
          <div>
            <p className="font-medium text-[#eee9dc]">This account cannot read the approval queue.</p>
            <p className="mt-1 leading-6 text-[#999284]">
              Authentication succeeded, but the control plane denied access. Ask an administrator
              to verify this operator&apos;s approval permissions.
            </p>
          </div>
        </div>
      </LivePanel>
    );
  }
  if (viewState === "error") {
    return (
      <div className="space-y-3">
        <LiveErrorState title="Approval queue unavailable" message={error || "Failed to load approvals"} />
        <button
          type="button"
          onClick={() => setReloadToken((value) => value + 1)}
          className="inline-flex min-h-11 items-center gap-2 rounded-[4px] border border-[#48463e] bg-[#151612] px-4 text-sm text-[#d8d1c4] transition hover:border-[#777268] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#ff7545]"
        >
          <RotateCw className="h-4 w-4" aria-hidden="true" />
          Retry approval query
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <LiveKpiGrid>
        <LiveStatCard
          label="Matching requests"
          value={String(total)}
          detail={`${statusFilter || "All statuses"}${agentId ? ` · agent ${agentId}` : ""}.`}
        />
        <LiveStatCard
          label="Pending here"
          value={String(currentPagePending)}
          detail="Pending decisions in the current canonical page."
          status={currentPagePending > 0 ? "warning" : "idle"}
        />
        <LiveStatCard
          label="Resolved here"
          value={String(currentPageResolved)}
          detail="Approved or rejected decisions in this page."
          status={currentPageResolved > 0 ? "success" : "idle"}
        />
        <LiveStatCard
          label="Page"
          value={`${pageNumber}/${pageCount}`}
          detail={`Records ${visibleRange} of ${total}.`}
        />
      </LiveKpiGrid>

      <LivePanel title="Queue filters" meta="canonical envelope">
        <form onSubmit={applyAgentFilter} className="grid gap-3 sm:grid-cols-2 lg:grid-cols-[minmax(0,240px)_minmax(0,1fr)_auto] lg:items-end">
          <label className="min-w-0 text-xs text-[#999284]">
            <span className="mb-1.5 block font-mono uppercase tracking-[0.12em]">Status</span>
            <select
              value={statusFilter}
              onChange={(event) => {
                setStatusFilter(event.currentTarget.value);
                setSkip(0);
                setNotice(null);
              }}
              className={inputClassName}
            >
              <option value="">All statuses</option>
              {APPROVAL_STATUSES.map((approvalStatus) => (
                <option key={approvalStatus} value={approvalStatus}>{approvalStatus}</option>
              ))}
            </select>
          </label>
          <label className="min-w-0 text-xs text-[#999284]">
            <span className="mb-1.5 block font-mono uppercase tracking-[0.12em]">Agent ID</span>
            <input
              value={draftAgentId}
              onChange={(event) => setDraftAgentId(event.currentTarget.value)}
              className={inputClassName}
              placeholder="Filter by exact agent ID"
              autoComplete="off"
            />
          </label>
          <div className="flex flex-wrap gap-2 sm:col-span-2 lg:col-span-1">
            <button
              type="submit"
              className="inline-flex min-h-11 items-center justify-center rounded-[4px] border border-[#ff7545] bg-[#ff571c] px-4 text-sm font-semibold text-[#090a08] transition hover:bg-[#ff7545] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#ffb091]"
            >
              Apply agent
            </button>
            <button
              type="button"
              onClick={clearFilters}
              className="inline-flex min-h-11 items-center justify-center rounded-[4px] border border-[#48463e] bg-[#151612] px-4 text-sm text-[#d8d1c4] transition hover:border-[#777268] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#ff7545]"
            >
              Clear
            </button>
          </div>
        </form>
      </LivePanel>

      {notice ? (
        <div
          role={notice.tone === "error" ? "alert" : "status"}
          className={`rounded-[4px] border px-4 py-3 text-sm ${
            notice.tone === "error"
              ? "border-[#66302e] bg-[#241312] text-[#ff9b96]"
              : "border-[#285a43] bg-[#0f2018] text-[#78e3b4]"
          }`}
        >
          {notice.message}
        </div>
      ) : null}

      <LivePanel title="Approval requests" meta={`${visibleRange} / ${total}`}>
        {approvals.length === 0 ? (
          <LiveEmptyState
            title="No matching approval requests"
            message={`The approval service returned an empty ${statusFilter || "all-status"} envelope for this page. Change the filter or return to an earlier page.`}
          />
        ) : (
          <div className="space-y-2.5">
            {approvals.map((approval) => (
              <article
                key={approval.id}
                className="grid min-w-0 gap-3 rounded-[4px] border border-[#34342e] bg-[#10110e] p-3.5 sm:p-4 md:grid-cols-[minmax(0,1fr)_auto] md:items-center"
              >
                <div className="min-w-0">
                  <div className="flex min-w-0 flex-wrap items-center gap-2">
                    <StatusBadge status={asDashboardStatus(approval.status)} label={approval.status} />
                    <span className="font-mono text-[11px] text-[#8d867a]">{formatRelativeTime(approval.created_at)}</span>
                  </div>
                  <p className="mt-2 break-words text-sm font-medium text-[#eee9dc]">
                    {approval.action_type}
                  </p>
                  <p className="mt-1 break-words text-xs leading-5 text-[#999284]">
                    Requested by <span className="text-[#d8d1c4]">{approval.requester}</span>
                  </p>
                  <p className="mt-1 break-all font-mono text-[11px] leading-5 text-[#8d867a]">
                    agent {approval.agent_id} · session {approval.session_id}
                  </p>
                  <p className="mt-2 break-words text-xs leading-5 text-[#999284]">
                    {summarizeOperatorContext(approval.payload)}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => inspectApproval(approval)}
                  aria-label={`Review ${approval.action_type} request ${approval.id}`}
                  className="inline-flex min-h-11 items-center justify-center gap-2 rounded-[4px] border border-[#48463e] bg-[#151612] px-3 text-xs font-semibold text-[#d8d1c4] transition hover:border-[#777268] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#ff7545] md:justify-self-end"
                >
                  <Eye className="h-4 w-4" aria-hidden="true" />
                  {approval.status === "PENDING" && approval.can_resolve
                    ? "Review decision"
                    : "Inspect request"}
                </button>
              </article>
            ))}
          </div>
        )}

        <nav aria-label="Approval request pages" className="mt-5 flex flex-wrap items-center justify-between gap-3 border-t border-[#34342e] pt-4">
          <p className="font-mono text-xs text-[#8d867a]">Page {pageNumber} of {pageCount} · records {visibleRange}</p>
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
        open={Boolean(selectedApproval)}
        onOpenChange={(open) => {
          if (!open && !decisionPending) {
            setSelectedApproval(null);
            setActionError(null);
          }
        }}
        title={selectedApproval?.action_type || "Approval request"}
        description={selectedApproval ? `Requested by ${selectedApproval.requester}` : undefined}
        className="max-h-[92vh] max-w-3xl"
        footer={
          selectedApproval?.status === "PENDING" && selectedApproval.can_resolve ? (
            <>
              <button
                type="button"
                onClick={() => resolveApproval("reject")}
                disabled={Boolean(decisionPending)}
                aria-busy={decisionPending === "reject"}
                className="inline-flex min-h-11 items-center justify-center rounded-[4px] border border-[#66302e] bg-[#241312] px-4 text-sm font-semibold text-[#ff9b96] transition hover:border-[#ff6d66] disabled:cursor-wait disabled:opacity-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#ff9b96]"
              >
                {decisionPending === "reject" ? "Rejecting…" : "Reject request"}
              </button>
              <button
                type="button"
                onClick={() => resolveApproval("approve")}
                disabled={Boolean(decisionPending)}
                aria-busy={decisionPending === "approve"}
                className="inline-flex min-h-11 items-center justify-center rounded-[4px] border border-[#3d654f] bg-[#0f2018] px-4 text-sm font-semibold text-[#78e3b4] transition hover:border-[#4bd69b] disabled:cursor-wait disabled:opacity-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#78e3b4]"
              >
                {decisionPending === "approve" ? "Approving…" : "Approve request"}
              </button>
            </>
          ) : undefined
        }
      >
        {selectedApproval ? (
          <div className="max-h-[62vh] space-y-5 overflow-y-auto pr-1">
            <div className="flex flex-wrap items-center gap-2">
              <StatusBadge status={asDashboardStatus(selectedApproval.status)} label={selectedApproval.status} />
              <span className="font-mono text-xs text-[#8d867a]">{formatDateTime(selectedApproval.created_at)}</span>
            </div>

            <dl className="grid gap-3 text-xs sm:grid-cols-2">
              {[
                ["Requester", selectedApproval.requester],
                ["Owner ID", selectedApproval.owner_id],
                ["Reviewer ID", selectedApproval.reviewer_id || "Not assigned"],
                ["Action", selectedApproval.action_type],
                ["Agent", selectedApproval.agent_id],
                ["Session", selectedApproval.session_id],
                ["Approver", selectedApproval.approver || "Not resolved"],
                ["Resolved", selectedApproval.resolved_at ? formatDateTime(selectedApproval.resolved_at) : "Not resolved"],
              ].map(([label, value]) => (
                <div key={label} className="min-w-0 rounded-[4px] border border-[#34342e] bg-[#0d0e0b] p-3">
                  <dt className="font-mono uppercase tracking-[0.12em] text-[#777268]">{label}</dt>
                  <dd className="mt-1 break-all text-[#d8d1c4]">{value}</dd>
                </div>
              ))}
            </dl>

            <div>
              <h3 className="font-mono text-xs uppercase tracking-[0.12em] text-[#8d867a]">Redacted action context</h3>
              <pre className="mt-2 max-h-72 overflow-auto whitespace-pre-wrap break-words rounded-[4px] border border-[#34342e] bg-[#090a08] p-3 font-mono text-[11px] leading-5 text-[#c8c0b0]">
                {formatOperatorContext(selectedApproval.payload)}
              </pre>
            </div>

            {selectedApproval.comment ? (
              <div className="rounded-[4px] border border-[#34342e] bg-[#10110e] p-3 text-sm leading-6 text-[#c8c0b0]">
                <span className="font-mono text-[10px] uppercase tracking-[0.12em] text-[#777268]">Resolution comment</span>
                <p className="mt-1 break-words">{selectedApproval.comment}</p>
              </div>
            ) : null}

            {selectedApproval.status === "PENDING" && selectedApproval.can_resolve ? (
              <label className="block text-xs text-[#999284]">
                <span className="mb-1.5 flex items-center gap-2 font-mono uppercase tracking-[0.12em]">
                  <UserRoundCheck className="h-4 w-4" aria-hidden="true" /> Decision comment
                </span>
                <textarea
                  value={comment}
                  onChange={(event) => setComment(event.currentTarget.value)}
                  maxLength={1000}
                  rows={4}
                  data-autofocus
                  placeholder="Optional rationale for the evidence record"
                  className={`${inputClassName} resize-y py-3`}
                />
                <span className="mt-1 block text-right font-mono text-[10px] text-[#777268]">{comment.length}/1000</span>
              </label>
            ) : null}

            {actionError ? <p role="alert" className="rounded-[4px] border border-[#66302e] bg-[#241312] p-3 text-sm leading-6 text-[#ff9b96]">{actionError}</p> : null}
            <p className="text-xs leading-5 text-[#777268]">
              Resolution permissions and state transitions are enforced by the control plane. A
              successful decision is not shown as final until this page reloads the canonical list envelope.
            </p>
          </div>
        ) : null}
      </DashboardDialog>
    </div>
  );
}
