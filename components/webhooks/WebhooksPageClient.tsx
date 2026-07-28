"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  Plus,
  Search,
  Trash2,
  Edit2,
  Play,
  Loader2,
  AlertCircle,
  CheckCircle2,
  Webhook,
  X,
  Eye,
  Clock,
  ChevronDown,
  ChevronUp,
  Copy,
  Check,
} from "lucide-react";
import { readJson, writeJson } from "@/components/app/http";
import {
  getWebhookDeliverySignal,
  getWebhookLifecycleState,
  type WebhookDeliverySignal,
} from "@/components/app/operatorReadiness";
import {
  LiveAuthRequired,
  Surface as Card,
  formatRelativeTime,
} from "@/components/dashboard/livePrimitives";
import { DashboardDialog } from "@/components/dashboard/DashboardDialog";
import { StatusBadge } from "@/components/dashboard/StatusBadge";

type WebhookDelivery = {
  id: string;
  event: string;
  payload: string;
  status_code: number | null;
  success: boolean;
  error_message: string | null;
  attempts: number;
  created_at: string;
  delivered_at: string | null;
};

type Webhook = {
  id: string;
  url: string;
  events: string[];
  is_active: boolean;
  created_at: string;
};

type CopyFeedback = {
  webhookId: string;
  status: "success" | "error";
  message: string;
};

type TestFeedback = {
  webhookId: string;
  message: string;
};

const WEBHOOK_SEARCH_ID = "webhook-search";
const WEBHOOK_URL_ID = "webhook-url";
const WEBHOOK_EVENTS_ID = "webhook-events";
const WEBHOOK_FORM_ERROR_ID = "webhook-form-error";

function normalizeStringList(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is string => typeof item === "string" && item.trim().length > 0);
}

function normalizeWebhooks(payload: unknown): Webhook[] {
  const container = payload && typeof payload === "object" ? (payload as Record<string, unknown>) : null;
  const rawWebhooks = Array.isArray(payload) ? payload : container?.webhooks ?? container?.items ?? container?.data ?? [];

  if (!Array.isArray(rawWebhooks)) return [];

  return rawWebhooks
    .map((entry) => {
      if (!entry || typeof entry !== "object") return null;
      const record = entry as Record<string, unknown>;
      const id = typeof record.id === "string" ? record.id : "";
      const url = typeof record.url === "string" ? record.url : "";
      if (!id || !url) return null;
      return {
        id,
        url,
        events: normalizeStringList(record.events),
        is_active: Boolean(record.is_active),
        created_at: typeof record.created_at === "string" ? record.created_at : "",
      } satisfies Webhook;
    })
    .filter((webhook): webhook is Webhook => Boolean(webhook));
}

function normalizeDeliveries(payload: unknown): WebhookDelivery[] {
  const container = payload && typeof payload === "object" ? (payload as Record<string, unknown>) : null;
  const rawDeliveries = Array.isArray(payload) ? payload : container?.deliveries ?? container?.items ?? container?.data ?? [];

  if (!Array.isArray(rawDeliveries)) return [];

  return rawDeliveries
    .map((entry) => {
      if (!entry || typeof entry !== "object") return null;
      const record = entry as Record<string, unknown>;
      const id = typeof record.id === "string" ? record.id : "";
      if (!id) return null;
      return {
        id,
        event: typeof record.event === "string" ? record.event : "unknown",
        payload: typeof record.payload === "string" ? record.payload : JSON.stringify(record.payload ?? {}, null, 2),
        status_code: typeof record.status_code === "number" ? record.status_code : null,
        success: Boolean(record.success),
        error_message: typeof record.error_message === "string" ? record.error_message : null,
        attempts: typeof record.attempts === "number" ? record.attempts : 0,
        created_at: typeof record.created_at === "string" ? record.created_at : new Date(0).toISOString(),
        delivered_at: typeof record.delivered_at === "string" ? record.delivered_at : null,
      } satisfies WebhookDelivery;
    })
    .filter((delivery): delivery is WebhookDelivery => Boolean(delivery));
}

export default function WebhooksPageClient() {
  const [webhooks, setWebhooks] = useState<Webhook[]>([]);
  const [deliverySignals, setDeliverySignals] = useState<Record<string, WebhookDeliverySignal>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [editingWebhook, setEditingWebhook] = useState<Webhook | null>(null);
  const [viewingDeliveries, setViewingDeliveries] = useState<Webhook | null>(null);
  const [deliveries, setDeliveries] = useState<WebhookDelivery[]>([]);
  const [loadingDeliveries, setLoadingDeliveries] = useState(false);
  const [expandedDelivery, setExpandedDelivery] = useState<string | null>(null);
  const [formData, setFormData] = useState({ url: "", events: "", is_active: true });
  const [submitting, setSubmitting] = useState(false);
  const [testingId, setTestingId] = useState<string | null>(null);
  const [testFeedback, setTestFeedback] = useState<TestFeedback | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Webhook | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [copyFeedback, setCopyFeedback] = useState<CopyFeedback | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const deliverySignalRequestRef = useRef(0);
  const copyFeedbackTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    fetchWebhooks();
  }, []);

  useEffect(() => {
    if (viewingDeliveries) {
      fetchDeliveries(viewingDeliveries.id);
    }
  }, [viewingDeliveries]);

  useEffect(() => {
    return () => {
      if (copyFeedbackTimeoutRef.current) {
        clearTimeout(copyFeedbackTimeoutRef.current);
      }
    };
  }, []);

  // Filter webhooks based on search query
  const filteredWebhooks = searchQuery
    ? webhooks.filter(w =>
        w.url.toLowerCase().includes(searchQuery.toLowerCase()) ||
        w.id.toLowerCase().includes(searchQuery.toLowerCase()) ||
        w.events.some(e => e.toLowerCase().includes(searchQuery.toLowerCase()))
      )
    : webhooks;

  const readinessSummary = useMemo(() => {
    const summary = {
      active: 0,
      attention: 0,
      healthy: 0,
      notExercised: 0,
    };

    for (const webhook of webhooks) {
      if (!webhook.is_active) continue;
      summary.active += 1;

      const signal = deliverySignals[webhook.id];
      if (!signal) continue;

      if (signal.status === "success") {
        summary.healthy += 1;
      }
      if (signal.status === "warning" || signal.status === "error") {
        summary.attention += 1;
      }
      if (signal.label === "not exercised") {
        summary.notExercised += 1;
      }
    }

    return summary;
  }, [deliverySignals, webhooks]);

  const hasAuthError = Boolean(error && /unauthorized|forbidden|auth|token|sign in|login/i.test(error));

  async function fetchWebhooks() {
    try {
      setLoading(true);
      setError(null);
      const data = await readJson<unknown>("/api/webhooks");
      const nextWebhooks = normalizeWebhooks(data);
      setWebhooks(nextWebhooks);
      void hydrateDeliverySignals(nextWebhooks);
    } catch (err) {
      setWebhooks([]);
      setDeliverySignals({});
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }

  async function hydrateDeliverySignals(nextWebhooks: Webhook[]) {
    const requestId = ++deliverySignalRequestRef.current;

    const nextSignals = await Promise.all(
      nextWebhooks.map(async (webhook) => {
        if (!webhook.is_active) {
          return [webhook.id, getWebhookDeliverySignal(webhook, [])] as const;
        }

        try {
          const payload = await readJson<unknown>(`/api/webhooks/${webhook.id}/deliveries?limit=5`);
          return [webhook.id, getWebhookDeliverySignal(webhook, normalizeDeliveries(payload))] as const;
        } catch (deliveryError) {
          return [
            webhook.id,
            {
              detail:
                deliveryError instanceof Error
                  ? deliveryError.message
                  : "Failed to load recent delivery history.",
              label: "delivery data unavailable",
              lastDeliveryAt: null,
              lastStatusCode: null,
              recentAttempts: 0,
              recentFailures: 0,
              status: "warning",
            } satisfies WebhookDeliverySignal,
          ] as const;
        }
      }),
    );

    if (requestId !== deliverySignalRequestRef.current) return;
    setDeliverySignals(Object.fromEntries(nextSignals));
  }

  async function fetchDeliveries(webhookId: string) {
    try {
      setLoadingDeliveries(true);
      setError(null);
      const data = await readJson<unknown>(`/api/webhooks/${webhookId}/deliveries`);
      setDeliveries(normalizeDeliveries(data));
    } catch (err) {
      setDeliveries([]);
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoadingDeliveries(false);
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    setFormError(null);
    try {
      const method = editingWebhook ? "PATCH" : "POST";
      const url = editingWebhook
        ? `/api/webhooks/${editingWebhook.id}`
        : "/api/webhooks";

      await writeJson<unknown>(url, {
        method,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          is_active: formData.is_active,
          url: formData.url,
          events: formData.events.split(",").map((e) => e.trim()).filter(Boolean),
        }),
      });

      setShowForm(false);
      setEditingWebhook(null);
      setFormData({ url: "", events: "", is_active: true });
      await fetchWebhooks();
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unknown error";
      setError(message);
      setFormError(message);
    } finally {
      setSubmitting(false);
    }
  }

  function requestDelete(webhook: Webhook) {
    if (deletingId) return;
    setDeleteError(null);
    setDeleteTarget(webhook);
  }

  async function handleDelete() {
    if (!deleteTarget || deletingId) return;

    const webhook = deleteTarget;
    setDeletingId(webhook.id);

    try {
      setError(null);
      setDeleteError(null);
      await writeJson<unknown>(`/api/webhooks/${webhook.id}`, { method: "DELETE" });
      await fetchWebhooks();
      setDeleteTarget(null);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unknown error";
      setDeleteError(message);
      setError(message);
    } finally {
      setDeletingId(null);
    }
  }

  async function handleTest(id: string) {
    if (testingId) return;

    setTestingId(id);
    setError(null);
    setTestFeedback(null);
    try {
      const response = await writeJson<{ message?: string }>(`/api/webhooks/${id}/test`, {
        method: "POST",
      });
      await hydrateDeliverySignals(webhooks);
      setTestFeedback({
        webhookId: id,
        message: response.message || "Test event delivered successfully.",
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setTestingId(null);
    }
  }

  async function handleCopyId(id: string) {
    if (copyFeedbackTimeoutRef.current) {
      clearTimeout(copyFeedbackTimeoutRef.current);
    }

    try {
      if (!navigator.clipboard?.writeText) {
        throw new Error("Clipboard API unavailable");
      }

      await navigator.clipboard.writeText(id);
      setCopyFeedback({
        webhookId: id,
        status: "success",
        message: "Webhook ID copied to clipboard.",
      });
    } catch {
      setCopyFeedback({
        webhookId: id,
        status: "error",
        message: "Could not copy the webhook ID. Clipboard access was denied.",
      });
    }

    copyFeedbackTimeoutRef.current = setTimeout(() => {
      setCopyFeedback(null);
      copyFeedbackTimeoutRef.current = null;
    }, 3000);
  }

  function startEdit(webhook: Webhook) {
    setFormError(null);
    setEditingWebhook(webhook);
    setFormData({
      url: webhook.url,
      events: webhook.events.join(", "),
      is_active: webhook.is_active,
    });
    setShowForm(true);
  }

  function formatJson(payload: string): string {
    try {
      return JSON.stringify(JSON.parse(payload), null, 2);
    } catch {
      return payload;
    }
  }

  if (loading) {
    return (
      <div
        role="status"
        aria-live="polite"
        aria-busy="true"
        className="flex items-center justify-center p-12"
      >
        <Loader2 aria-hidden="true" className="h-8 w-8 animate-spin text-muted-foreground" />
        <span className="sr-only">Loading webhooks</span>
      </div>
    );
  }

  return (
    <div className="min-w-0 space-y-6">
      <p role="status" aria-live="polite" aria-atomic="true" className="sr-only">
        {copyFeedback?.message ?? ""}
      </p>
      <DashboardDialog
        open={Boolean(deleteTarget)}
        onOpenChange={(open) => {
          if (!open && !deletingId) {
            setDeleteTarget(null);
            setDeleteError(null);
          }
        }}
        title="Delete webhook"
        description="Permanently remove this webhook route from MUTX."
        footer={
          <>
            <button
              type="button"
              data-autofocus
              onClick={() => {
                setDeleteTarget(null);
                setDeleteError(null);
              }}
              disabled={Boolean(deletingId)}
              className="min-h-11 w-full rounded-md border px-4 py-2 text-sm font-medium transition hover:bg-accent disabled:cursor-not-allowed disabled:opacity-50 sm:w-auto"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={() => void handleDelete()}
              disabled={Boolean(deletingId)}
              className="inline-flex min-h-11 w-full items-center justify-center gap-2 rounded-md bg-destructive px-4 py-2 text-sm font-semibold text-destructive-foreground transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50 sm:w-auto"
            >
              {deletingId ? (
                <>
                  <Loader2 aria-hidden="true" className="h-4 w-4 animate-spin" />
                  Deleting…
                </>
              ) : (
                "Delete Webhook"
              )}
            </button>
          </>
        }
      >
        <div aria-busy={Boolean(deletingId)} className="space-y-4 text-start">
          <div className="rounded-md border border-white/10 bg-black/20 p-3">
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">
              Webhook target
            </p>
            <p dir="ltr" className="mt-2 break-all text-start text-sm text-white">
              {deleteTarget?.url}
            </p>
            <p dir="ltr" className="mt-1 break-all text-start font-mono text-xs text-muted-foreground">
              {deleteTarget?.id}
            </p>
          </div>
          <p className="text-sm leading-6 text-muted-foreground">
            MUTX will stop sending the configured events to this endpoint. This deletion cannot be undone.
          </p>
          {deleteError ? (
            <div role="alert" className="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
              Webhook deletion failed: {deleteError}
            </div>
          ) : null}
        </div>
      </DashboardDialog>
      {error && (
        <div
          id={formError ? WEBHOOK_FORM_ERROR_ID : undefined}
          role="alert"
          className="flex items-center gap-2 p-4 bg-destructive/10 text-destructive rounded-md"
        >
          <AlertCircle aria-hidden="true" className="h-4 w-4 flex-shrink-0" />
          <span className="min-w-0 flex-1 break-words">{error}</span>
          <button
            type="button"
            onClick={() => {
              setError(null);
              setFormError(null);
            }}
            className="flex min-h-8 min-w-8 items-center justify-center rounded hover:bg-destructive/20"
            aria-label="Dismiss error"
          >
            <X aria-hidden="true" className="h-4 w-4" />
          </button>
        </div>
      )}

      {!showForm && !viewingDeliveries && webhooks.length > 0 && (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <Card className="p-4">
            <p className="text-xs uppercase tracking-[0.18em] text-muted-foreground">Active routes</p>
            <p className="mt-2 text-2xl font-semibold">{readinessSummary.active}</p>
            <p className="mt-2 text-xs text-muted-foreground">Webhooks that can accept test or live deliveries.</p>
          </Card>
          <Card className="p-4">
            <p className="text-xs uppercase tracking-[0.18em] text-muted-foreground">Healthy sample</p>
            <p className="mt-2 text-2xl font-semibold">{readinessSummary.healthy}</p>
            <p className="mt-2 text-xs text-muted-foreground">Active routes whose recent delivery sample is succeeding.</p>
          </Card>
          <Card className="p-4">
            <p className="text-xs uppercase tracking-[0.18em] text-muted-foreground">Attention needed</p>
            <p className="mt-2 text-2xl font-semibold">{readinessSummary.attention}</p>
            <p className="mt-2 text-xs text-muted-foreground">Routes currently failing, recovering, stale, or missing delivery data.</p>
          </Card>
          <Card className="p-4">
            <p className="text-xs uppercase tracking-[0.18em] text-muted-foreground">Not exercised</p>
            <p className="mt-2 text-2xl font-semibold">{readinessSummary.notExercised}</p>
            <p className="mt-2 text-xs text-muted-foreground">Active routes with no recorded delivery attempts yet.</p>
          </Card>
        </div>
      )}

      {viewingDeliveries && (
        <Card className="min-w-0 p-4 sm:p-6">
          <div className="mb-4 flex min-w-0 items-center justify-between gap-3">
            <h2 className="text-lg font-semibold">Delivery History</h2>
            <button
              type="button"
              onClick={() => {
                setViewingDeliveries(null);
                setDeliveries([]);
                setExpandedDelivery(null);
              }}
              className="flex min-h-9 min-w-9 flex-shrink-0 items-center justify-center rounded-md hover:bg-accent"
              aria-label="Close delivery history"
            >
              <X aria-hidden="true" className="h-4 w-4" />
            </button>
          </div>
          <p className="mb-4 min-w-0 break-all text-sm text-muted-foreground">
            {viewingDeliveries.url}
          </p>
          {loadingDeliveries ? (
            <div
              role="status"
              aria-live="polite"
              aria-busy="true"
              className="flex items-center justify-center p-8"
            >
              <Loader2 aria-hidden="true" className="h-6 w-6 animate-spin text-muted-foreground" />
              <span className="sr-only">Loading delivery history</span>
            </div>
          ) : deliveries.length === 0 ? (
            <p className="text-center text-muted-foreground py-8">
              No deliveries yet
            </p>
          ) : (
            <div className="max-h-96 min-w-0 space-y-2 overflow-x-hidden overflow-y-auto">
              {deliveries.map((delivery, index) => {
                const deliveryDetailsId = `webhook-delivery-details-${index}`;
                const isExpanded = expandedDelivery === delivery.id;

                return (
                  <div
                    key={delivery.id}
                    className="min-w-0 overflow-hidden rounded-md border"
                  >
                    <button
                      type="button"
                      onClick={() =>
                        setExpandedDelivery(isExpanded ? null : delivery.id)
                      }
                      aria-expanded={isExpanded}
                      aria-controls={deliveryDetailsId}
                      aria-label={`${isExpanded ? "Collapse" : "Expand"} ${delivery.event} delivery details`}
                      className="flex w-full min-w-0 flex-col items-stretch gap-2 p-3 text-left hover:bg-accent/50 sm:flex-row sm:items-center sm:justify-between"
                    >
                      <div className="flex min-w-0 flex-wrap items-center gap-2 sm:gap-3">
                        {delivery.success ? (
                          <CheckCircle2 aria-hidden="true" className="h-4 w-4 flex-shrink-0 text-green-500" />
                        ) : (
                          <AlertCircle aria-hidden="true" className="h-4 w-4 flex-shrink-0 text-red-500" />
                        )}
                        <span className="min-w-0 break-all font-mono text-sm">{delivery.event}</span>
                        {delivery.status_code && (
                          <span
                            className={`flex-shrink-0 rounded px-2 py-0.5 text-xs ${
                              delivery.status_code >= 200 && delivery.status_code < 300
                                ? "bg-green-500/20 text-green-400"
                                : "bg-red-500/20 text-red-400"
                            }`}
                          >
                            {delivery.status_code}
                          </span>
                        )}
                      </div>
                      <div className="flex min-w-0 items-center justify-between gap-3 sm:flex-shrink-0 sm:justify-end">
                        <span className="flex min-w-0 items-center gap-1 break-words text-xs text-muted-foreground">
                          <Clock aria-hidden="true" className="h-3 w-3 flex-shrink-0" />
                          {new Date(delivery.created_at).toLocaleString()}
                        </span>
                        {isExpanded ? (
                          <ChevronUp aria-hidden="true" className="h-4 w-4 flex-shrink-0" />
                        ) : (
                          <ChevronDown aria-hidden="true" className="h-4 w-4 flex-shrink-0" />
                        )}
                      </div>
                    </button>
                    <div
                      id={deliveryDetailsId}
                      hidden={!isExpanded}
                      className="min-w-0 border-t bg-muted/30 p-3"
                    >
                      <p className="text-xs text-muted-foreground mb-2">
                        Payload:
                      </p>
                      <pre className="max-h-64 min-w-0 overflow-x-hidden overflow-y-auto whitespace-pre-wrap break-all rounded bg-black/50 p-3 text-xs">
                        {formatJson(delivery.payload)}
                      </pre>
                      {delivery.error_message && (
                        <p className="mt-2 break-words text-xs text-red-400">
                          Error: {delivery.error_message}
                        </p>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </Card>
      )}

      {!showForm && !viewingDeliveries && webhooks.length > 0 && (
        <div className="relative mb-4">
          <label htmlFor={WEBHOOK_SEARCH_ID} className="sr-only">
            Search webhooks
          </label>
          <Search
            aria-hidden="true"
            className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-500"
          />
          <input
            id={WEBHOOK_SEARCH_ID}
            type="search"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search webhooks by URL, ID, or event"
            className="w-full rounded-lg border border-white/10 bg-black/40 py-2 pl-10 pr-4 text-sm text-white placeholder:text-slate-600 focus:border-cyan-400 focus:outline-none"
          />
        </div>
      )}

      {!showForm && !viewingDeliveries && filteredWebhooks.length > 0 && (
        <div className="flex justify-end">
          <button
            onClick={() => {
              setShowForm(true);
              setFormError(null);
              setEditingWebhook(null);
              setFormData({ url: "", events: "", is_active: true });
            }}
            className="flex w-full items-center justify-center gap-2 rounded-md bg-primary px-4 py-2 text-primary-foreground hover:bg-primary/90 sm:w-auto"
          >
            <Plus className="h-4 w-4" />
            Add Webhook
          </button>
        </div>
      )}

      {showForm && !viewingDeliveries && (
        <Card className="min-w-0 p-4 sm:p-6">
          <h2 className="text-lg font-semibold mb-4">
            {editingWebhook ? "Edit Webhook" : "Add New Webhook"}
          </h2>
          <form onSubmit={handleSubmit} aria-busy={submitting} className="space-y-4">
            <div>
              <label htmlFor={WEBHOOK_URL_ID} className="block text-sm font-medium mb-1">
                URL
              </label>
              <input
                id={WEBHOOK_URL_ID}
                type="url"
                value={formData.url}
                onChange={(e) => setFormData({ ...formData, url: e.target.value })}
                aria-invalid={Boolean(formError)}
                aria-describedby={formError ? WEBHOOK_FORM_ERROR_ID : undefined}
                placeholder="https://your-server.com/webhook"
                className="min-w-0 w-full px-3 py-2 border rounded-md bg-background"
                required
              />
            </div>
            <div>
              <label htmlFor={WEBHOOK_EVENTS_ID} className="block text-sm font-medium mb-1">
                Events (comma-separated)
              </label>
              <input
                id={WEBHOOK_EVENTS_ID}
                type="text"
                value={formData.events}
                onChange={(e) =>
                  setFormData({ ...formData, events: e.target.value })
                }
                aria-invalid={Boolean(formError)}
                aria-describedby={formError ? WEBHOOK_FORM_ERROR_ID : undefined}
                placeholder="agent.started, deployment.finished"
                className="min-w-0 w-full px-3 py-2 border rounded-md bg-background"
              />
            </div>
            {editingWebhook && (
              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  id="active"
                  checked={formData.is_active}
                  onChange={(e) =>
                    setFormData({ ...formData, is_active: e.target.checked })
                  }
                  className="h-4 w-4"
                />
                <label htmlFor="active" className="text-sm font-medium">
                  Active
                </label>
              </div>
            )}
            <div className="flex flex-wrap gap-2">
              <button
                type="submit"
                disabled={submitting}
                className="px-4 py-2 bg-primary text-primary-foreground rounded-md hover:bg-primary/90 disabled:opacity-50"
              >
                {submitting ? (
                  <>
                    <Loader2 aria-hidden="true" className="h-4 w-4 animate-spin" />
                    <span className="sr-only">Saving webhook</span>
                  </>
                ) : (
                  "Save"
                )}
              </button>
              <button
                type="button"
                onClick={() => {
                  setShowForm(false);
                  setFormError(null);
                  setEditingWebhook(null);
                }}
                className="px-4 py-2 border rounded-md hover:bg-accent"
              >
                Cancel
              </button>
            </div>
          </form>
        </Card>
      )}

      {hasAuthError && !showForm && !viewingDeliveries ? (
        <LiveAuthRequired
          title="Operator session required"
          message="Sign in to load webhook routes, test deliveries, and replay history from the live event surface."
        />
      ) : filteredWebhooks.length === 0 && !showForm && !viewingDeliveries ? (
        <Card className="min-w-0 p-4 text-center sm:p-12">
          <Webhook className="h-12 w-12 mx-auto mb-4 text-muted-foreground" />
          <h3 className="text-lg font-semibold mb-2">No webhooks configured</h3>
          <p className="text-muted-foreground mb-4">
            Add a webhook to receive real-time notifications
          </p>
          <button
            onClick={() => {
              setShowForm(true);
              setFormError(null);
            }}
            className="px-4 py-2 bg-primary text-primary-foreground rounded-md hover:bg-primary/90"
          >
            <Plus className="h-4 w-4 mr-2 inline" />
            Add Your First Webhook
          </button>
        </Card>
      ) : (
        !viewingDeliveries && (
          <div className="space-y-4">
            {filteredWebhooks.map((webhook) => {
              const lifecycle = getWebhookLifecycleState(webhook);
              const currentCopyFeedback =
                copyFeedback?.webhookId === webhook.id ? copyFeedback : null;
              const deliverySignal =
                deliverySignals[webhook.id] ??
                ({
                  detail: "Loading recent delivery sample.",
                  label: "probing",
                  lastDeliveryAt: null,
                  lastStatusCode: null,
                  recentAttempts: 0,
                  recentFailures: 0,
                  status: "idle",
                } satisfies WebhookDeliverySignal);

              return (
                <Card key={webhook.id} className="min-w-0 p-4">
                  <div className="flex min-w-0 flex-col items-stretch gap-4 sm:flex-row sm:items-start sm:justify-between">
                    <div className="min-w-0 flex-1 space-y-2">
                      <div className="flex min-w-0 flex-wrap items-center gap-2">
                        <code className="max-w-full min-w-0 whitespace-normal break-all rounded bg-muted px-2 py-1 text-sm">
                          {webhook.url}
                        </code>
                        <StatusBadge status={lifecycle.status} label={lifecycle.label} />
                        <StatusBadge status={deliverySignal.status} label={deliverySignal.label} />
                        <button
                          type="button"
                          onClick={() => handleCopyId(webhook.id)}
                          className="flex min-h-8 min-w-8 flex-shrink-0 items-center justify-center rounded text-slate-500 transition-colors hover:bg-accent hover:text-cyan-400"
                          aria-label={`Copy webhook ID ${webhook.id}`}
                          title={
                            currentCopyFeedback?.status === "error"
                              ? currentCopyFeedback.message
                              : "Copy webhook ID"
                          }
                        >
                          {currentCopyFeedback?.status === "success" ? (
                            <Check aria-hidden="true" className="h-4 w-4 text-emerald-400" />
                          ) : currentCopyFeedback?.status === "error" ? (
                            <AlertCircle aria-hidden="true" className="h-4 w-4 text-red-400" />
                          ) : (
                            <Copy aria-hidden="true" className="h-4 w-4" />
                          )}
                        </button>
                      </div>
                      <div className="flex gap-1 flex-wrap">
                        {webhook.events.map((event) => (
                          <span
                            key={event}
                            className="max-w-full break-all rounded bg-secondary px-2 py-0.5 text-xs"
                          >
                            {event}
                          </span>
                        ))}
                      </div>
                      <p className="break-words text-xs text-muted-foreground">
                        Created {new Date(webhook.created_at).toLocaleString()}
                        {deliverySignal.lastDeliveryAt
                          ? ` · last delivery ${formatRelativeTime(deliverySignal.lastDeliveryAt)}`
                          : ""}
                      </p>
                      <p className="break-words text-xs text-muted-foreground">{deliverySignal.detail}</p>
                      {testFeedback?.webhookId === webhook.id ? (
                        <div
                          role="status"
                          aria-live="polite"
                          aria-atomic="true"
                          className="flex items-start gap-2 rounded-md border border-emerald-400/20 bg-emerald-400/10 px-3 py-2 text-start text-xs text-emerald-200"
                        >
                          <CheckCircle2 aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0" />
                          <span className="min-w-0 break-words">{testFeedback.message}</span>
                        </div>
                      ) : null}
                      {deliverySignal.lastStatusCode ? (
                        <p className="text-xs text-muted-foreground">
                          Latest HTTP status {deliverySignal.lastStatusCode} across {deliverySignal.recentAttempts} sampled attempt
                          {deliverySignal.recentAttempts === 1 ? "" : "s"}.
                        </p>
                      ) : null}
                    </div>
                    <div className="grid w-full grid-cols-2 gap-2 sm:flex sm:w-auto sm:flex-shrink-0">
                      <button
                        type="button"
                        onClick={() => setViewingDeliveries(webhook)}
                        className="flex min-h-11 min-w-11 items-center justify-center gap-2 rounded-md border border-white/10 px-2 hover:bg-accent sm:border-transparent"
                        aria-label="View delivery history"
                        title="View delivery history"
                      >
                        <Eye aria-hidden="true" className="h-4 w-4" />
                        <span className="text-xs sm:sr-only">History</span>
                      </button>
                      <button
                        type="button"
                        onClick={() => handleTest(webhook.id)}
                        disabled={testingId !== null}
                        className="flex min-h-11 min-w-11 items-center justify-center gap-2 rounded-md border border-white/10 px-2 hover:bg-accent disabled:opacity-50 sm:border-transparent"
                        aria-label="Test webhook"
                        title="Test webhook"
                      >
                        {testingId === webhook.id ? (
                          <Loader2 aria-hidden="true" className="h-4 w-4 animate-spin" />
                        ) : (
                          <Play aria-hidden="true" className="h-4 w-4" />
                        )}
                        <span className="text-xs sm:sr-only">Test</span>
                      </button>
                      <button
                        type="button"
                        onClick={() => startEdit(webhook)}
                        className="flex min-h-11 min-w-11 items-center justify-center gap-2 rounded-md border border-white/10 px-2 hover:bg-accent sm:border-transparent"
                        aria-label="Edit webhook"
                        title="Edit webhook"
                      >
                        <Edit2 aria-hidden="true" className="h-4 w-4" />
                        <span className="text-xs sm:sr-only">Edit</span>
                      </button>
                      <button
                        type="button"
                        onClick={() => requestDelete(webhook)}
                        disabled={deletingId !== null}
                        className="flex min-h-11 min-w-11 items-center justify-center gap-2 rounded-md border border-white/10 px-2 text-destructive hover:bg-accent disabled:opacity-50 sm:border-transparent"
                        aria-label="Delete webhook"
                        title="Delete webhook"
                      >
                        <Trash2 aria-hidden="true" className="h-4 w-4" />
                        <span className="text-xs sm:sr-only">Delete</span>
                      </button>
                    </div>
                  </div>
                </Card>
              );
            })}
          </div>
        )
      )}
    </div>
  );
}
