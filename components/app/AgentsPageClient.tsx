"use client";

import { Component, type FormEvent, type ReactNode, type ErrorInfo, useState, useEffect, useRef } from "react";
import Link from "next/link";
import {
  ArrowRight,
  Bot,
  Calendar,
  Clock,
  Copy,
  Plus,
  Power,
  RefreshCcw,
  Search,
  X,
  Trash2,
  Loader2,
} from "lucide-react";

import { ApiRequestError, extractApiErrorMessage, normalizeCollection, readJson } from "@/components/app/http";
import { DashboardDialog } from "@/components/dashboard/DashboardDialog";
import { EmptyState as DashboardEmptyState } from "@/components/dashboard/EmptyState";
import { FilterBar } from "@/components/dashboard/FilterBar";
import { StatusBadge } from "@/components/dashboard/StatusBadge";
import {
  LiveAuthRequired,
  LiveKpiGrid,
  LiveMiniStat,
  LiveMiniStatGrid,
  LivePanel,
  LiveStatCard,
  asDashboardStatus,
  formatDateTime,
  formatRelativeTime,
} from "@/components/dashboard/livePrimitives";
import { type components } from "@/app/types/api";

type Agent = components["schemas"]["AgentResponse"];
type AgentListEnvelope = components["schemas"]["AgentListResponse"];
type AgentPendingAction = {
  agent: Agent;
  kind: "stop" | "delete";
};

const AGENTS_PAGE_SIZE = 20;
const CREATE_AGENT_FORM_ERROR_ID = "create-agent-form-error";

type AgentCreateRequest = {
  name: string;
  description?: string;
  type?: string;
  config?: Record<string, unknown>;
};

async function createAgent(data: AgentCreateRequest): Promise<Agent> {
  return readJson<Agent>("/api/dashboard/agents", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

async function deleteAgent(agentId: string): Promise<void> {
  const response = await fetch(`/api/dashboard/agents/${encodeURIComponent(agentId)}`, {
    method: "DELETE",
    cache: "no-store",
  });

  if (!response.ok) {
    const payload = await response.json().catch(() => ({ detail: "Delete failed" }));
    throw new Error(extractApiErrorMessage(payload, "Delete failed"));
  }
}

async function stopAgent(agentId: string): Promise<{ status: string }> {
  return readJson<{ status: string }>(`/api/dashboard/agents/${encodeURIComponent(agentId)}?action=stop`, {
    method: "POST",
    cache: "no-store",
  });
}

function AgentCardSkeleton() {
  return (
    <div className="rounded-[6px] border border-[#2b2b26] bg-[#11120f] p-5 motion-safe:animate-pulse motion-reduce:animate-none">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <div className="h-5 w-32 rounded-[3px] bg-[#24251f]" />
          <div className="mt-2 h-4 w-48 rounded-[3px] bg-[#1b1c18]" />
        </div>
        <div className="h-6 w-20 rounded-[4px] bg-[#24251f]" />
      </div>
      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        <div className="h-12 rounded-[4px] bg-[#1b1c18]" />
        <div className="h-12 rounded-[4px] bg-[#1b1c18]" />
      </div>
    </div>
  );
}

function AgentCard({ agent, onDelete, onStop, deletingId, stoppingId }: { agent: Agent; onDelete: (agent: Agent) => void; onStop: (agent: Agent) => void; deletingId: string | null; stoppingId: string | null }) {
  const [copied, setCopied] = useState(false);
  const isDeleting = deletingId === agent.id;
  const isStopping = stoppingId === agent.id;
  const canStop = agent.status === "running";

  const copyId = async () => {
    await navigator.clipboard.writeText(agent.id);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <article className="dashboard-entry rounded-[4px] border border-[#2b2b26] bg-[#11120f] p-5 transition hover:border-[#48463e]">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-[4px] border border-[#663619] bg-[#21150f] text-[#ff8355]">
              <Bot className="h-5 w-5" aria-hidden="true" />
            </div>
            <div className="min-w-0">
              <h3 className="truncate text-[0.98rem] font-semibold tracking-[-0.02em] text-white">
                {agent.name}
              </h3>
              <div className="mt-1 flex flex-wrap items-center gap-2">
                <p className="max-w-full truncate font-[family:var(--font-mono)] text-[9px] text-[#8d867a]">
                  {agent.id}
                </p>
                <button
                  onClick={copyId}
                  className="inline-flex items-center gap-1.5 rounded-[4px] border border-[#34342e] bg-[#151612] px-2 py-1 text-[9px] text-[#aaa397] transition hover:border-[#ff6a32] hover:text-[#ff9a72]"
                >
                  <Copy className="h-3 w-3" aria-hidden="true" />
                  {copied ? "Copied" : "Copy ID"}
                </button>
              </div>
            </div>
          </div>

          {agent.description && (
            <p className="mt-3 text-sm text-slate-400 line-clamp-2">
              {agent.description}
            </p>
          )}
        </div>

        <StatusBadge status={asDashboardStatus(agent.status)} label={agent.status} />
      </div>

      <div className="mt-4">
        <LiveMiniStatGrid>
          <LiveMiniStat
            label="Created"
            value={formatDateTime(agent.created_at)}
            detail={formatRelativeTime(agent.created_at)}
            icon={Calendar}
          />
          <LiveMiniStat
            label="Updated"
            value={formatDateTime(agent.updated_at)}
            detail={formatRelativeTime(agent.updated_at)}
            icon={Clock}
          />
        </LiveMiniStatGrid>
      </div>

      {agent.config && Object.keys(agent.config).length > 0 && (
        <div className="mt-4 rounded-[4px] border border-[#2b2b26] bg-[#0c0d0b] p-3">
          <div className="mb-2 flex items-center gap-2 font-[family:var(--font-mono)] text-[8px] uppercase tracking-[0.16em] text-[#8d867a]">
            <span className="text-[#58aaff]" aria-hidden="true">CFG /</span> Configuration
          </div>
          <pre className="overflow-x-auto rounded-[4px] border border-[#34342e] bg-[#090a08] px-3 py-2 text-xs text-[#c8c0b0]">
            {JSON.stringify(agent.config, null, 2)}
          </pre>
        </div>
      )}

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <Link
          href={`/dashboard/agents/${encodeURIComponent(agent.id)}`}
          aria-label={`Inspect ${agent.name}`}
          className="inline-flex items-center gap-1.5 rounded-[4px] border border-[#294d6c] bg-[#101c26] px-3 py-2 text-xs text-[#8ac7ff] transition hover:border-[#58aaff] hover:text-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#58aaff]"
        >
          <ArrowRight className="h-3 w-3" aria-hidden="true" />
          Inspect
        </Link>
        <button
          onClick={() => onStop(agent)}
          disabled={isStopping || !canStop}
          className="inline-flex min-h-11 items-center gap-1.5 rounded-[4px] border border-[#34342e] bg-[#151612] px-3 py-2 text-xs text-[#aaa397] transition hover:border-[#8a6d38] hover:text-[#f4cc82] disabled:cursor-not-allowed disabled:opacity-50"
        >
          {isStopping ? (
            <Loader2 className="h-3 w-3 motion-safe:animate-spin motion-reduce:animate-none" />
          ) : (
            <Power className="h-3 w-3" />
          )}
          Stop
        </button>
        <button
          onClick={() => onDelete(agent)}
          disabled={isDeleting}
          className="inline-flex min-h-11 items-center gap-1.5 rounded-[4px] border border-[#34342e] bg-[#151612] px-3 py-2 text-xs text-[#aaa397] transition hover:border-[#7c3835] hover:text-[#ff9b96] disabled:cursor-not-allowed disabled:opacity-50"
        >
          {isDeleting ? (
            <Loader2 className="h-3 w-3 motion-safe:animate-spin motion-reduce:animate-none" />
          ) : (
            <Trash2 className="h-3 w-3" />
          )}
          Delete
        </button>
      </div>
    </article>
  );
}

function EmptyState() {
  return (
    <DashboardEmptyState
      title="Nothing here yet"
      message="No agents found. Authenticate and provision your first agent to see it in the fleet inventory."
      icon={<Bot className="h-8 w-8" />}
    />
  );
}

function LoadingState() {
  return (
    <div className="space-y-3">
      <AgentCardSkeleton />
      <AgentCardSkeleton />
      <AgentCardSkeleton />
    </div>
  );
}

interface CreateAgentModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
}

function CreateAgentModal({ isOpen, onClose, onSuccess }: CreateAgentModalProps) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [agentType, setAgentType] = useState("openai");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const fieldClassName =
    "w-full rounded-[4px] border border-[#3b3a33] bg-[#0c0d0b] px-4 py-3 text-sm text-[#eee9dc] placeholder:text-[#8d867a] focus:border-[#ff6a32] focus:outline-none";

  if (!isOpen) return null;

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");

    try {
      await createAgent({
        name,
        description: description || undefined,
        type: agentType,
      });
      setName("");
      setDescription("");
      setAgentType("openai");
      onSuccess();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create agent");
    } finally {
      setLoading(false);
    }
  };

  return (
    <DashboardDialog
      open={isOpen}
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
      title="Create Agent"
      description="Register a new agent in the fleet inventory and seed its initial runtime profile."
      footer={
        <>
          <button
            type="button"
            onClick={onClose}
            className="min-h-11 rounded-[4px] border border-[#3b3a33] bg-[#151612] px-4 py-2 text-sm font-medium text-[#c8c0b0] transition hover:border-[#777268] hover:text-white"
          >
            Cancel
          </button>
          <button
            type="submit"
            form="create-agent-form"
            disabled={loading || !name}
            className="min-h-11 rounded-[4px] border border-[#ff7545] bg-[#ff571c] px-4 py-2 text-sm font-semibold text-[#090a08] transition hover:bg-[#ff7545] disabled:cursor-not-allowed disabled:opacity-50"
          >
            {loading ? (
              <span className="flex items-center justify-center gap-2">
                <Loader2 className="h-4 w-4 motion-safe:animate-spin motion-reduce:animate-none" />
                Creating...
              </span>
            ) : (
              "Create Agent"
            )}
          </button>
        </>
      }
    >
      <form
        id="create-agent-form"
        onSubmit={handleSubmit}
        aria-describedby={error ? CREATE_AGENT_FORM_ERROR_ID : undefined}
        className="space-y-4"
      >
          <div>
            <label htmlFor="create-agent-name" className="block text-sm font-medium text-slate-400 mb-2">
              Name <span className="text-rose-400">*</span>
            </label>
            <input
              id="create-agent-name"
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              className={fieldClassName}
              placeholder="my-agent"
            />
          </div>

          <div>
            <label htmlFor="create-agent-description" className="block text-sm font-medium text-slate-400 mb-2">
              Description
            </label>
            <textarea
              id="create-agent-description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={3}
              className={`${fieldClassName} resize-none`}
              placeholder="Optional description..."
            />
          </div>

          <div>
            <label htmlFor="create-agent-type" className="block text-sm font-medium text-slate-400 mb-2">
              Type
            </label>
            <select
              id="create-agent-type"
              value={agentType}
              onChange={(e) => setAgentType(e.target.value)}
              className={fieldClassName}
            >
              <option value="openai">OpenAI</option>
              <option value="anthropic">Anthropic</option>
              <option value="langchain">LangChain</option>
              <option value="custom">Custom</option>
            </select>
          </div>

          {error && (
            <div
              id={CREATE_AGENT_FORM_ERROR_ID}
              role="alert"
              className="rounded-[4px] border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-200"
            >
              {error}
            </div>
          )}
      </form>
    </DashboardDialog>
  );
}

interface ErrorBoundaryState {
  hasError: boolean;
  error?: Error;
}

class AgentsErrorBoundary extends Component<{ children: ReactNode }, ErrorBoundaryState> {
  constructor(props: { children: ReactNode }) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error("Agents page error:", error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex flex-col items-center justify-center rounded-[6px] border border-[#2b2b26] bg-[#11120f] py-16 text-center">
          <div className="flex h-14 w-14 items-center justify-center rounded-[4px] border border-rose-500/30 bg-rose-500/10 text-rose-400">
            <X className="h-8 w-8" />
          </div>
          <h3 className="mt-6 text-lg font-semibold text-white">Something went wrong</h3>
          <p className="mt-2 max-w-sm text-sm text-slate-400">
            {this.state.error?.message || "An unexpected error occurred"}
          </p>
          <button
            onClick={() => window.location.reload()}
            className="mt-6 rounded-[4px] border border-[#3b3a33] bg-[#151612] px-6 py-2.5 text-sm font-medium text-white transition hover:border-[#777268]"
          >
            Reload Page
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}

export function AgentsPageClient() {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [totalAgents, setTotalAgents] = useState(0);
  const [nextSkip, setNextSkip] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");
  const [authRequired, setAuthRequired] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const searchInputRef = useRef<HTMLInputElement>(null);
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [stoppingId, setStoppingId] = useState<string | null>(null);
  const [pendingAction, setPendingAction] = useState<AgentPendingAction | null>(null);
  const [actionError, setActionError] = useState("");
  const [actionNotice, setActionNotice] = useState("");

  const runningAgents = agents.filter((a) => a.status === "running").length;
  const failedAgents = agents.filter(
    (a) => a.status === "failed" || a.status === "error",
  ).length;

  const filteredAgents = agents.filter(
    (agent) =>
      agent.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      agent.id.toLowerCase().includes(searchQuery.toLowerCase()) ||
      (agent.description?.toLowerCase().includes(searchQuery.toLowerCase()) ?? false),
  );

  async function loadAgents({ append = false, skip = 0 }: { append?: boolean; skip?: number } = {}) {
    try {
      const data = await readJson<unknown>(
        `/api/dashboard/agents?skip=${skip}&limit=${AGENTS_PAGE_SIZE}`,
      );
      const agentsData = normalizeCollection<Agent>(data, ["agents", "items", "data"]).filter(
        (entry): entry is Agent => Boolean(entry && typeof entry === "object" && "id" in entry),
      );
      const envelope = data && typeof data === "object" && !Array.isArray(data)
        ? data as Partial<AgentListEnvelope>
        : null;
      const pageSkip = typeof envelope?.skip === "number" ? envelope.skip : skip;
      const pageLimit = typeof envelope?.limit === "number" ? envelope.limit : AGENTS_PAGE_SIZE;
      const authoritativeTotal = typeof envelope?.total === "number"
        ? envelope.total
        : append
          ? skip + agentsData.length
          : agentsData.length;
      const authoritativeHasMore = typeof envelope?.has_more === "boolean"
        ? envelope.has_more
        : pageSkip + agentsData.length < authoritativeTotal;

      setAgents((current) => {
        if (!append) return agentsData;

        const existingIds = new Set(current.map((agent) => agent.id));
        return [...current, ...agentsData.filter((agent) => !existingIds.has(agent.id))];
      });
      setTotalAgents(authoritativeTotal);
      setNextSkip(pageSkip + Math.min(pageLimit, agentsData.length));
      setHasMore(authoritativeHasMore);
      setAuthRequired(false);
      setError("");
    } catch (err) {
      if (err instanceof ApiRequestError && err.status === 401) {
        setAgents([]);
        setTotalAgents(0);
        setNextSkip(0);
        setHasMore(false);
        setAuthRequired(true);
        setError("Sign in to view and operate agents.");
        return;
      }

      setAuthRequired(false);
      setError(err instanceof Error ? err.message : "Failed to load agents");
    }
  }

  useEffect(() => {
    let cancelled = false;

    async function bootstrap() {
      try {
        await loadAgents();
      } catch {
        // Error already handled in loadAgents
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void bootstrap();

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const searchParams = new URLSearchParams(window.location.search);
    if (searchParams.get("create") === "1") {
      setIsCreateModalOpen(true);
    }
  }, []);

  // Cmd/Ctrl + K belongs to the global command palette. Slash focuses this page's search.
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      const target = e.target;
      const isTypingTarget = target instanceof HTMLElement && (
        target.isContentEditable ||
        target.tagName === "INPUT" ||
        target.tagName === "SELECT" ||
        target.tagName === "TEXTAREA"
      );

      if (e.key === "/" && !e.metaKey && !e.ctrlKey && !e.altKey && !isTypingTarget) {
        e.preventDefault();
        searchInputRef.current?.focus();
      }
    }

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, []);

  async function handleRefresh() {
    setRefreshing(true);
    try {
      await loadAgents();
    } finally {
      setRefreshing(false);
    }
  }

  async function handleLoadMore() {
    setLoadingMore(true);
    try {
      await loadAgents({ append: true, skip: nextSkip });
    } finally {
      setLoadingMore(false);
    }
  }

  async function handleCreateSuccess() {
    await loadAgents();
  }

  function handleCloseCreateModal() {
    setIsCreateModalOpen(false);

    const url = new URL(window.location.href);
    if (url.searchParams.get("create") !== "1") return;

    url.searchParams.delete("create");
    const nextUrl = `${url.pathname}${url.search}${url.hash}`;
    window.history.replaceState(window.history.state, "", nextUrl);
  }

  function requestAgentAction(agent: Agent, kind: AgentPendingAction["kind"]) {
    if (deletingId || stoppingId) return;
    setActionError("");
    setActionNotice("");
    setPendingAction({ agent, kind });
  }

  async function confirmAgentAction() {
    if (!pendingAction || deletingId || stoppingId) return;

    const { agent, kind } = pendingAction;
    const fallback = kind === "delete" ? "Failed to delete agent" : "Failed to stop agent";
    setError("");
    setActionError("");
    if (kind === "delete") setDeletingId(agent.id);
    else setStoppingId(agent.id);

    try {
      if (kind === "delete") {
        await deleteAgent(agent.id);
        await loadAgents();
        setActionNotice(`Deleted agent ${agent.name} (${agent.id}).`);
      } else {
        await stopAgent(agent.id);
        setAgents((current) =>
          current.map((entry) =>
            entry.id === agent.id ? { ...entry, status: "stopped" } : entry,
          ),
        );
        setActionNotice(`Stopped agent ${agent.name} (${agent.id}).`);
      }
      setPendingAction(null);
    } catch (err) {
      const message = err instanceof Error ? err.message : fallback;
      setActionError(message);
      setError(message);
    } finally {
      setDeletingId(null);
      setStoppingId(null);
    }
  }

  if (loading) {
    return (
      <div className="space-y-4">
        <LoadingState />
      </div>
    );
  }

  return (
    <AgentsErrorBoundary>
      <div className="space-y-4">
        <DashboardDialog
          open={Boolean(pendingAction)}
          onOpenChange={(open) => {
            if (!open && !deletingId && !stoppingId) {
              setPendingAction(null);
              setActionError("");
            }
          }}
          title={pendingAction?.kind === "delete" ? "Delete agent" : "Stop agent"}
          description={
            pendingAction?.kind === "delete"
              ? "Permanently remove this agent record from the MUTX fleet."
              : "Request that MUTX stop this agent's active runtime."
          }
          footer={
            <>
              <button
                type="button"
                data-autofocus
                onClick={() => {
                  setPendingAction(null);
                  setActionError("");
                }}
                disabled={Boolean(deletingId || stoppingId)}
                className="min-h-11 w-full rounded-[4px] border border-[#3b3a33] bg-[#151612] px-4 py-2 text-sm font-medium text-[#c8c0b0] transition hover:border-[#777268] hover:text-white disabled:cursor-not-allowed disabled:opacity-50 sm:w-auto"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={() => void confirmAgentAction()}
                disabled={Boolean(deletingId || stoppingId)}
                className={pendingAction?.kind === "delete"
                  ? "inline-flex min-h-11 w-full items-center justify-center gap-2 rounded-[4px] border border-rose-400/30 bg-rose-400/15 px-4 py-2 text-sm font-semibold text-rose-200 transition hover:bg-rose-400/25 disabled:cursor-not-allowed disabled:opacity-50 sm:w-auto"
                  : "inline-flex min-h-11 w-full items-center justify-center gap-2 rounded-[4px] border border-amber-400/30 bg-amber-400/10 px-4 py-2 text-sm font-semibold text-amber-100 transition hover:bg-amber-400/20 disabled:cursor-not-allowed disabled:opacity-50 sm:w-auto"}
              >
                {deletingId || stoppingId ? (
                  <>
                    <Loader2 className="h-4 w-4 motion-safe:animate-spin motion-reduce:animate-none" aria-hidden="true" />
                    {pendingAction?.kind === "delete" ? "Deleting…" : "Stopping…"}
                  </>
                ) : pendingAction?.kind === "delete" ? (
                  "Delete Agent"
                ) : (
                  "Stop Agent"
                )}
              </button>
            </>
          }
        >
          <div aria-busy={Boolean(deletingId || stoppingId)} className="space-y-4 text-start">
            <div className="rounded-[4px] border border-[#2b2b26] bg-[#0c0d0b] p-3">
              <p className="text-sm font-semibold text-white">{pendingAction?.agent.name}</p>
              <p dir="ltr" className="mt-1 break-all text-start font-[family:var(--font-mono)] text-xs text-[#8d867a]">
                {pendingAction?.agent.id}
              </p>
            </div>
            <p className="text-sm leading-6 text-[#aaa397]">
              {pendingAction?.kind === "delete"
                ? "The agent record and its stored configuration will be deleted. This action cannot be undone."
                : "The agent record and configuration will remain available after its runtime is stopped."}
            </p>
            {actionError ? (
              <div role="alert" className="rounded-[4px] border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">
                {pendingAction?.kind === "delete" ? "Agent deletion" : "Agent stop"} failed: {actionError}
              </div>
            ) : null}
          </div>
        </DashboardDialog>

        {actionNotice ? (
          <div role="status" aria-live="polite" aria-atomic="true" className="rounded-[4px] border border-emerald-400/20 bg-emerald-400/10 px-4 py-3 text-sm text-emerald-200">
            {actionNotice}
          </div>
        ) : null}

        <LiveKpiGrid>
          <LiveStatCard
            label="Fleet"
            value={String(totalAgents)}
            detail={`${agents.length} loaded from the complete MUTX registry.`}
            status={asDashboardStatus(totalAgents > 0 ? "running" : "idle")}
          />
          <LiveStatCard
            label="Running"
            value={String(runningAgents)}
            detail="Running agents among the currently loaded records."
            status={asDashboardStatus(runningAgents > 0 ? "running" : "idle")}
          />
          <LiveStatCard
            label="Failed"
            value={String(failedAgents)}
            detail="Failed agents among the currently loaded records."
            status={asDashboardStatus(failedAgents > 0 ? "error" : "idle")}
          />
          <LiveStatCard
            label="Search Scope"
            value={searchQuery ? `${filteredAgents.length} visible` : "registry"}
            detail="Search matches name, id, and description across loaded records."
            status={asDashboardStatus(searchQuery ? "active" : "idle")}
          />
        </LiveKpiGrid>

        {error && !authRequired && (
          <div role="alert" className="flex items-center justify-between rounded-[4px] border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">
            <div className="flex items-center gap-2">
              <span className="font-medium">Error:</span> {error}
            </div>
            <button
              onClick={() => { setError(""); loadAgents(); }}
              className="rounded-[4px] border border-rose-500/30 bg-rose-500/20 px-3 py-1 text-xs font-medium text-rose-200 transition hover:bg-rose-500/30"
            >
              Retry
            </button>
          </div>
        )}

        <FilterBar
          searchValue={searchQuery}
          onSearchChange={setSearchQuery}
          searchInputRef={searchInputRef}
          searchPlaceholder="Search agents by name, ID, or description... (/ to focus)"
          onReset={() => setSearchQuery("")}
          trailing={
            <div className="flex flex-wrap items-center gap-2">
              <button
                onClick={handleRefresh}
                disabled={refreshing}
                className="inline-flex items-center gap-2 rounded-[4px] border border-[#3b3a33] bg-[#151612] px-3.5 py-2 text-sm text-[#c8c0b0] transition hover:border-[#777268] hover:text-white disabled:cursor-not-allowed disabled:opacity-60"
              >
                <RefreshCcw className={`h-4 w-4 ${refreshing ? "motion-safe:animate-spin motion-reduce:animate-none" : ""}`} />
                {refreshing ? "Refreshing" : "Refresh"}
              </button>
              <button
                onClick={() => setIsCreateModalOpen(true)}
                className="inline-flex items-center gap-2 rounded-[4px] border border-[#ff7545] bg-[#ff571c] px-3.5 py-2 text-sm font-semibold text-[#090a08] transition hover:bg-[#ff7545]"
              >
                <Plus className="h-4 w-4" />
                Create Agent
              </button>
            </div>
          }
        />

        {authRequired ? (
          <LiveAuthRequired
            title="Operator session required"
            message="Sign in to load fleet inventory, lifecycle actions, and per-agent configuration from the live API."
          />
        ) : agents.length === 0 ? (
          <EmptyState />
        ) : (
          <LivePanel
            title="Fleet registry"
            meta={`${filteredAgents.length} visible · ${agents.length} of ${totalAgents} loaded`}
            action={
              <span className="hidden rounded-[4px] border border-[#294d6c] bg-[#101c26] px-2.5 py-1 font-[family:var(--font-mono)] text-[8px] uppercase tracking-[0.14em] text-[#8ac7ff] sm:inline-flex">
                / search
              </span>
            }
          >
            {filteredAgents.length === 0 ? (
              <DashboardEmptyState
                title="No matching agents"
                message={
                  hasMore
                    ? "No loaded agents match yet. Load more records or adjust your search."
                    : "No agents match your search query. Try adjusting your search."
                }
                icon={<Search className="h-8 w-8" />}
              />
            ) : (
              <div className="grid gap-3 md:grid-cols-2 2xl:grid-cols-3">
                {filteredAgents.map((agent) => (
                  <AgentCard
                    key={agent.id}
                    agent={agent}
                    onDelete={(agent) => requestAgentAction(agent, "delete")}
                    onStop={(agent) => requestAgentAction(agent, "stop")}
                    deletingId={deletingId}
                    stoppingId={stoppingId}
                  />
                ))}
              </div>
            )}
            {hasMore ? (
              <div className="mt-4 flex justify-center border-t border-[#2b2b26] pt-4">
                <button
                  type="button"
                  onClick={handleLoadMore}
                  disabled={loadingMore}
                  className="inline-flex items-center gap-2 rounded-[4px] border border-[#3b3a33] bg-[#151612] px-4 py-2 text-sm font-medium text-[#c8c0b0] transition hover:border-[#777268] hover:text-white disabled:cursor-not-allowed disabled:opacity-60"
                >
                  <RefreshCcw className={`h-4 w-4 ${loadingMore ? "motion-safe:animate-spin motion-reduce:animate-none" : ""}`} aria-hidden="true" />
                  {loadingMore ? "Loading more..." : `Load more (${agents.length} of ${totalAgents})`}
                </button>
              </div>
            ) : null}
          </LivePanel>
        )}

        <CreateAgentModal
          isOpen={isCreateModalOpen}
          onClose={handleCloseCreateModal}
          onSuccess={handleCreateSuccess}
        />
      </div>
    </AgentsErrorBoundary>
  );
}
