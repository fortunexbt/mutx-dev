import { NextRequest, NextResponse } from "next/server";
import { promises as fs } from "node:fs";
import path from "node:path";

import {
  applyAuthCookies,
  authenticatedFetch,
  getApiBaseUrl,
  hasAuthSession,
} from "@/app/api/_lib/controlPlane";
import { unauthorized, withErrorHandling } from "@/app/api/_lib/errors";

export const dynamic = "force-dynamic";

const UPSTREAM_TIMEOUT_MS = 5_000;

type AuthTokens = {
  access_token: string;
  refresh_token?: string;
  expires_in: number;
};

type ResourceStatus = "ok" | "unauthenticated" | "forbidden" | "error";
type AggregateSourceStatus = ResourceStatus | "partial";
type DashboardStatus = "idle" | "running" | "success" | "warning" | "error";

type ResourceResult = {
  status: ResourceStatus;
  statusCode: number;
  data: unknown | null;
  error: string | null;
  tokenRefreshed: boolean;
  refreshedTokens?: AuthTokens;
};

type BriefItem = {
  id: string;
  title: string;
  detail: string;
  status: DashboardStatus;
  createdAt: string | null;
  source: string;
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function normalizeCollection(payload: unknown, keys: string[] = ["items", "data"]) {
  if (Array.isArray(payload)) return payload;
  if (!isRecord(payload)) return [];

  for (const key of keys) {
    const value = payload[key];
    if (Array.isArray(value)) {
      return value;
    }
  }

  return [];
}

function hasCollectionPayload(payload: unknown, keys: string[]) {
  if (Array.isArray(payload)) return true;
  if (!isRecord(payload)) return false;
  return keys.some((key) => Array.isArray(payload[key]));
}

function pickString(record: Record<string, unknown>, keys: string[]) {
  for (const key of keys) {
    const value = record[key];
    if (typeof value === "string" && value.trim().length > 0) {
      return value;
    }
  }

  return null;
}

function countMissingIdentifiers(
  payload: unknown,
  collectionKeys: string[],
  identifierKeys: string[],
) {
  return normalizeCollection(payload, collectionKeys).filter(
    (item) => !isRecord(item) || !pickString(item, identifierKeys),
  ).length;
}

function toIsoTimestamp(value: unknown) {
  if (typeof value === "string" && value.trim().length > 0) {
    const parsed = Date.parse(value);
    return Number.isNaN(parsed) ? null : new Date(parsed).toISOString();
  }

  if (typeof value === "number" && Number.isFinite(value)) {
    const millis = value > 1_000_000_000_000 ? value : value * 1000;
    return new Date(millis).toISOString();
  }

  return null;
}

function extractErrorMessage(payload: unknown, fallback: string) {
  if (typeof payload === "string" && payload.trim().length > 0) {
    return payload;
  }

  if (!isRecord(payload)) {
    return fallback;
  }

  const detail = payload.detail;
  if (typeof detail === "string" && detail.trim().length > 0) {
    return detail;
  }

  const message = payload.message;
  if (typeof message === "string" && message.trim().length > 0) {
    return message;
  }

  const error = payload.error;
  if (typeof error === "string" && error.trim().length > 0) {
    return error;
  }

  return fallback;
}

function asDashboardStatus(value: string | null | undefined): DashboardStatus {
  const normalized = (value ?? "").toLowerCase();

  if (
    normalized.includes("healthy") ||
    normalized.includes("success") ||
    normalized.includes("approved") ||
    normalized.includes("completed")
  ) {
    return "success";
  }

  if (normalized.includes("running") || normalized.includes("pending")) {
    return "running";
  }

  if (normalized.includes("warn") || normalized.includes("queued") || normalized.includes("stale")) {
    return "warning";
  }

  if (normalized.includes("fail") || normalized.includes("deny") || normalized.includes("error")) {
    return "error";
  }

  return "idle";
}

async function fetchResource(
  request: NextRequest,
  url: string,
  fallbackMessage: string,
): Promise<ResourceResult> {
  try {
    const { response, tokenRefreshed, refreshedTokens } = await authenticatedFetch(request, url, {
      cache: "no-store",
      signal: AbortSignal.timeout(UPSTREAM_TIMEOUT_MS),
    });
    const payload = response.status === 204 ? null : await response.json().catch(() => null);

    if (response.ok && payload === null) {
      return {
        status: "error",
        statusCode: 502,
        data: null,
        error: `${fallbackMessage}: upstream returned no data.`,
        tokenRefreshed,
        refreshedTokens,
      };
    }

    return {
      status: response.ok
        ? "ok"
        : response.status === 401
          ? "unauthenticated"
          : response.status === 403
            ? "forbidden"
            : "error",
      statusCode: response.status,
      data: response.ok ? payload : null,
      error: response.ok ? null : extractErrorMessage(payload, fallbackMessage),
      tokenRefreshed,
      refreshedTokens,
    };
  } catch (error) {
    const errorName =
      error && typeof error === "object" && "name" in error ? String(error.name) : "";
    const timedOut = errorName === "AbortError" || errorName === "TimeoutError";

    return {
      status: "error",
      statusCode: timedOut ? 504 : 502,
      data: null,
      error: timedOut
        ? `${fallbackMessage}: upstream request timed out.`
        : `${fallbackMessage}: upstream request failed.`,
      tokenRefreshed: false,
    };
  }
}

function pickRefreshedTokens(results: Array<{ tokenRefreshed: boolean; refreshedTokens?: AuthTokens }>) {
  return results.find((result) => result.tokenRefreshed)?.refreshedTokens;
}

function accessFailureResponse(
  request: NextRequest,
  failure: ResourceResult,
  resources: ResourceResult[],
  fallback: string,
) {
  const nextResponse = NextResponse.json(
    { detail: failure.error ?? fallback },
    { status: failure.statusCode },
  );
  const refreshedTokens = pickRefreshedTokens(resources);
  if (refreshedTokens) {
    applyAuthCookies(nextResponse, request, refreshedTokens);
  }
  return nextResponse;
}

async function readJsonFile<T>(filePath: string): Promise<{ available: boolean; value: T | null }> {
  try {
    const raw = await fs.readFile(filePath, "utf-8");
    return { available: true, value: JSON.parse(raw) as T };
  } catch {
    return { available: false, value: null };
  }
}

async function readAutonomyBacklog() {
  if (process.env.NODE_ENV !== "development") {
    return { count: null as number | null, note: "Autonomy backlog is local-only in this shell." };
  }

  const repoRoot = process.env.MUTX_REPO_ROOT || process.cwd();
  const queue = await readJsonFile<{ items?: Array<{ status?: string }> }>(
    path.join(repoRoot, "mutx-engineering-agents/dispatch/action-queue.json"),
  );
  if (!queue.available || !Array.isArray(queue.value?.items)) {
    return {
      count: null as number | null,
      note: "Local autonomy queue data is unavailable or malformed; zero backlog is not assumed.",
    };
  }

  const items = queue.value.items;
  return {
    count: items.filter((item) => item.status === "queued" || item.status === "running").length,
    note: null as string | null,
  };
}

async function loadWebhookFailures(
  request: NextRequest,
  apiBaseUrl: string,
): Promise<{
  items: BriefItem[];
  errors: string[];
  tokenResults: ResourceResult[];
  status: AggregateSourceStatus;
}> {
  const webhookList = await fetchResource(request, `${apiBaseUrl}/v1/webhooks`, "Failed to fetch webhooks");
  if (webhookList.status !== "ok") {
    return {
      items: [],
      errors: [webhookList.error ?? "Webhook inventory is unavailable."],
      tokenResults: [webhookList],
      status: webhookList.status,
    };
  }

  if (!hasCollectionPayload(webhookList.data, ["items", "webhooks", "data"])) {
    return {
      items: [],
      errors: ["Webhook inventory returned an invalid payload."],
      tokenResults: [webhookList],
      status: "error",
    };
  }

  const activeWebhooks = normalizeCollection(webhookList.data, ["items", "webhooks", "data"])
    .filter(isRecord)
    .filter((webhook) => Boolean(webhook.is_active))
    .slice(0, 6);
  const activeWebhookIdentifierFailures = activeWebhooks.filter(
    (webhook) => !pickString(webhook, ["id"]),
  ).length;

  const deliveries = await Promise.all(
    activeWebhooks.map(async (webhook) => {
      const webhookId = pickString(webhook, ["id"]);
      if (!webhookId) return null;
      const result = await fetchResource(
        request,
        `${apiBaseUrl}/v1/webhooks/${encodeURIComponent(webhookId)}/deliveries?success=false&limit=1`,
        "Failed to fetch webhook deliveries",
      );
      return { webhookId, url: pickString(webhook, ["url"]), result };
    }),
  );

  const items = deliveries
    .filter((entry): entry is NonNullable<typeof entry> => Boolean(entry))
    .flatMap(({ url, result }) => {
      if (
        result.status !== "ok" ||
        !hasCollectionPayload(result.data, ["items", "deliveries", "data"])
      ) {
        return [];
      }

      return normalizeCollection(result.data, ["items", "deliveries", "data"])
        .filter(isRecord)
        .filter((delivery) => delivery.success === false)
        .flatMap((delivery) => {
          const id = pickString(delivery, ["id"]);
          if (!id) return [];

          return [{
            id,
            title: pickString(delivery, ["event"]) ?? "Webhook delivery failed",
            detail:
              pickString(delivery, ["error_message"]) ??
              (pickString(delivery, ["status_code"])
                ? `HTTP ${pickString(delivery, ["status_code"])}`
                : url ?? "Webhook route"),
            status: "error" as const,
            createdAt: toIsoTimestamp(delivery.created_at ?? delivery.delivered_at),
            source: "webhooks",
          }];
        });
    });

  const errors: string[] = deliveries
    .filter((entry): entry is NonNullable<typeof entry> => Boolean(entry))
    .flatMap((entry) =>
      entry.result.status === "ok" &&
      hasCollectionPayload(entry.result.data, ["items", "deliveries", "data"])
        ? []
        : [entry.result.error ?? "Webhook delivery history returned an invalid payload."],
    );
  const deliveryIdentifierFailures = deliveries.reduce((total, entry) => {
    if (!entry || entry.result.status !== "ok") return total;
    return total + countMissingIdentifiers(
      entry.result.data,
      ["items", "deliveries", "data"],
      ["id"],
    );
  }, 0);

  if (activeWebhookIdentifierFailures > 0) {
    errors.push(
      `${activeWebhookIdentifierFailures} active webhook record${activeWebhookIdentifierFailures === 1 ? " was" : "s were"} omitted because the upstream identifier was missing.`,
    );
  }
  if (deliveryIdentifierFailures > 0) {
    errors.push(
      `${deliveryIdentifierFailures} webhook delivery record${deliveryIdentifierFailures === 1 ? " was" : "s were"} omitted because the upstream identifier was missing.`,
    );
  }

  return {
    items,
    errors,
    tokenResults: [
      webhookList,
      ...deliveries
        .filter((entry): entry is NonNullable<typeof entry> => Boolean(entry))
        .map((entry) => entry.result),
    ],
    status: errors.length > 0 ? "partial" : "ok",
  };
}

export async function GET(request: NextRequest): Promise<NextResponse> {
  return withErrorHandling(async () => {
    if (!hasAuthSession(request)) {
      return unauthorized();
    }

    const apiBaseUrl = getApiBaseUrl();
    const [alerts, approvals, runs, autonomy, webhookFailures] = await Promise.all([
      fetchResource(request, `${apiBaseUrl}/v1/monitoring/alerts?limit=10`, "Failed to fetch alerts"),
      fetchResource(request, `${apiBaseUrl}/v1/approvals?status=PENDING&limit=10`, "Failed to fetch approvals"),
      fetchResource(request, `${apiBaseUrl}/v1/runs?limit=16`, "Failed to fetch runs"),
      readAutonomyBacklog(),
      loadWebhookFailures(request, apiBaseUrl),
    ]);
    const upstreamSources = [alerts, approvals, runs];
    const authenticatedSources = [...upstreamSources, ...webhookFailures.tokenResults];
    const unauthenticatedResource = authenticatedSources.find(
      (resource) => resource.status === "unauthenticated",
    );

    if (unauthenticatedResource) {
      return accessFailureResponse(
        request,
        unauthenticatedResource,
        authenticatedSources,
        "Dashboard standup authentication expired.",
      );
    }

    if (
      upstreamSources.every((resource) => resource.status === "forbidden") &&
      webhookFailures.status === "forbidden"
    ) {
      return accessFailureResponse(
        request,
        upstreamSources[0],
        authenticatedSources,
        "Dashboard standup access was denied.",
      );
    }

    const alertCollectionKeys = ["items", "alerts", "data"];
    const approvalCollectionKeys = ["items", "data"];
    const runCollectionKeys = ["items", "runs", "data"];
    const alertIdentifierFailures = countMissingIdentifiers(
      alerts.data,
      alertCollectionKeys,
      ["id"],
    );
    const approvalIdentifierFailures = countMissingIdentifiers(
      approvals.data,
      approvalCollectionKeys,
      ["id"],
    );
    const runIdentifierFailures = countMissingIdentifiers(
      runs.data,
      runCollectionKeys,
      ["id"],
    );

    const alertsSourceStatus: AggregateSourceStatus =
      alerts.status !== "ok"
        ? alerts.status
        : hasCollectionPayload(alerts.data, alertCollectionKeys)
          ? alertIdentifierFailures > 0 ? "partial" : "ok"
          : "error";
    const approvalsSourceStatus: AggregateSourceStatus =
      approvals.status !== "ok"
        ? approvals.status
        : hasCollectionPayload(approvals.data, approvalCollectionKeys)
          ? approvalIdentifierFailures > 0 ? "partial" : "ok"
          : "error";
    const runsSourceStatus: AggregateSourceStatus =
      runs.status !== "ok"
        ? runs.status
        : hasCollectionPayload(runs.data, runCollectionKeys)
          ? runIdentifierFailures > 0 ? "partial" : "ok"
          : "error";

    const alertBlockers: BriefItem[] = normalizeCollection(alerts.data, alertCollectionKeys)
      .filter(isRecord)
      .filter((alert) => !alert.resolved)
      .flatMap((alert) => {
        const id = pickString(alert, ["id"]);
        if (!id) return [];
        return [{
          id,
          title: pickString(alert, ["message"]) ?? "Alert requires review",
          detail: pickString(alert, ["type"]) ?? "Monitoring alert",
          status: "error" as const,
          createdAt: toIsoTimestamp(alert.created_at),
          source: "alerts",
        }];
      });
    const approvalBlockers: BriefItem[] = normalizeCollection(approvals.data, approvalCollectionKeys)
      .filter(isRecord)
      .flatMap((approval) => {
        const id = pickString(approval, ["id"]);
        if (!id) return [];
        return [{
          id,
          title: pickString(approval, ["action_type"]) ?? "Pending approval",
          detail:
            pickString(approval, ["requester"]) ??
            pickString(approval, ["agent_id"]) ??
            "Approval requires an operator decision.",
          status: "warning" as const,
          createdAt: toIsoTimestamp(approval.created_at),
          source: "approvals",
        }];
      });

    const blockers: BriefItem[] = [
      ...alertBlockers,
      ...approvalBlockers,
      ...webhookFailures.items,
    ]
      .sort((left, right) => {
        const leftTime = left.createdAt ? new Date(left.createdAt).getTime() : 0;
        const rightTime = right.createdAt ? new Date(right.createdAt).getTime() : 0;
        return rightTime - leftTime;
      })
      .slice(0, 12);

    const runRecords = normalizeCollection(runs.data, runCollectionKeys).filter(isRecord);
    const identifiedRunRecords = runRecords.flatMap((run) => {
      const id = pickString(run, ["id"]);
      return id ? [{ id, run }] : [];
    });
    const failedRunCount = identifiedRunRecords.filter(({ run }) =>
      ["failed", "error"].includes((pickString(run, ["status"]) ?? "").toLowerCase()),
    ).length;
    const watchlist: BriefItem[] = identifiedRunRecords
      .map(({ id, run }) => {
        const status = pickString(run, ["status"]) ?? "unknown";
        return {
          id,
          title:
            pickString(run, ["subject_label", "agent_id"]) ??
            "Execution watch item",
          detail:
            pickString(run, ["error_message"]) ??
            `Run status: ${status}`,
          status: asDashboardStatus(status),
          createdAt: toIsoTimestamp(run.completed_at ?? run.started_at ?? run.created_at),
          source: "runs",
          runStatus: status,
        };
      })
      .filter((item) => ["failed", "error", "running", "queued", "created"].includes((item.runStatus ?? "").toLowerCase()))
      .map(({ runStatus: _runStatus, ...item }) => item)
      .slice(0, 10);

    const completions: BriefItem[] = identifiedRunRecords
      .map(({ id, run }) => {
        const status = pickString(run, ["status"]) ?? "unknown";
        return {
          id,
          title:
            pickString(run, ["subject_label", "agent_id"]) ??
            "Completed run",
          detail:
            pickString(run, ["output_text"]) ??
            `Run status: ${status}`,
          status: "success" as const,
          createdAt: toIsoTimestamp(run.completed_at ?? run.started_at ?? run.created_at),
          source: "runs",
          runStatus: status,
        };
      })
      .filter((item) => item.runStatus?.toLowerCase() === "completed")
      .map(({ runStatus: _runStatus, ...item }) => item)
      .slice(0, 6);

    const hasIncompleteBlockerCoverage =
      alertsSourceStatus !== "ok" ||
      approvalsSourceStatus !== "ok" ||
      webhookFailures.status !== "ok";
    const hasIncompleteRunCoverage = runsSourceStatus !== "ok";
    const focus =
      blockers.length > 0
        ? `Clear ${blockers.length} blocking signal${blockers.length === 1 ? "" : "s"} before opening new operator lanes.${hasIncompleteBlockerCoverage || hasIncompleteRunCoverage ? " Some standup sources are unavailable, so this blocker count is partial." : ""}`
      : watchlist.length > 0
          ? `Review ${watchlist.length} live or failed execution signal${watchlist.length === 1 ? "" : "s"} next.`
          : hasIncompleteBlockerCoverage || hasIncompleteRunCoverage
            ? "Some standup sources are unavailable. Restore coverage before treating this brief as clear."
            : completions.length > 0
              ? `No urgent blockers detected. Review ${completions.length} recent completion${completions.length === 1 ? "" : "s"} and close the loop.`
              : "No urgent signals detected across the current dashboard feeds.";

    const partials: string[] = [];
    if (alertsSourceStatus !== "ok") {
      partials.push(
        alertIdentifierFailures > 0
          ? `${alertIdentifierFailures} alert record${alertIdentifierFailures === 1 ? " was" : "s were"} omitted because the upstream identifier was missing.`
          : alerts.error ?? "Alert coverage returned an invalid or unavailable payload.",
      );
    }
    if (approvalsSourceStatus !== "ok") {
      partials.push(
        approvalIdentifierFailures > 0
          ? `${approvalIdentifierFailures} approval record${approvalIdentifierFailures === 1 ? " was" : "s were"} omitted because the upstream identifier was missing.`
          : approvals.error ?? "Approval coverage returned an invalid or unavailable payload.",
      );
    }
    if (runsSourceStatus !== "ok") {
      partials.push(
        runIdentifierFailures > 0
          ? `${runIdentifierFailures} run record${runIdentifierFailures === 1 ? " was" : "s were"} omitted because the upstream identifier was missing.`
          : runs.error ?? "Run coverage returned an invalid or unavailable payload.",
      );
    }
    partials.push(...webhookFailures.errors);
    if (autonomy.note) {
      partials.push(autonomy.note);
    }

    const nextResponse = NextResponse.json({
      generatedAt: new Date().toISOString(),
      focus,
      metrics: {
        openAlerts:
          alertsSourceStatus === "ok"
            ? alertBlockers.length
            : null,
        pendingApprovals:
          approvalsSourceStatus === "ok"
            ? approvalBlockers.length
            : null,
        failedRuns:
          runsSourceStatus === "ok"
            ? failedRunCount
            : null,
        queuedAutonomy: autonomy.count,
      },
      sources: {
        alerts: alertsSourceStatus,
        approvals: approvalsSourceStatus,
        runs: runsSourceStatus,
        webhooks: webhookFailures.status,
        autonomy: autonomy.count === null ? "partial" : "ok",
      },
      blockers,
      watchlist,
      completions,
      partials,
    });

    const refreshedTokens = pickRefreshedTokens([
      alerts,
      approvals,
      runs,
      ...webhookFailures.tokenResults,
    ]);

    if (refreshedTokens) {
      applyAuthCookies(nextResponse, request, refreshedTokens);
    }

    return nextResponse;
  })(request);
}
