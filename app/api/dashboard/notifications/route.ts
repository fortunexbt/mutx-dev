import { NextRequest, NextResponse } from "next/server";

import {
  applyAuthCookies,
  authenticatedFetch,
  getApiBaseUrl,
  hasAuthSession,
} from "@/app/api/_lib/controlPlane";
import { unauthorized, withErrorHandling } from "@/app/api/_lib/errors";

export const dynamic = "force-dynamic";

const UPSTREAM_TIMEOUT_MS = 5_000;

type DashboardStatus = "idle" | "running" | "success" | "warning" | "error";

type ResourceStatus = "ok" | "unauthenticated" | "forbidden" | "error";
type AggregateSourceStatus = ResourceStatus | "partial";

type AuthTokens = {
  access_token: string;
  refresh_token?: string;
  expires_in: number;
};

type ResourceResult = {
  status: ResourceStatus;
  statusCode: number;
  data: unknown | null;
  error: string | null;
  tokenRefreshed: boolean;
  refreshedTokens?: AuthTokens;
};

type NotificationItem = {
  id: string;
  kind: "alert" | "approval" | "webhook" | "governance" | "runtime";
  title: string;
  detail: string;
  status: DashboardStatus;
  createdAt: string | null;
  source: string;
  href: string | null;
  meta: string | null;
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function asArray(value: unknown) {
  return Array.isArray(value) ? value : [];
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

function pickNumber(record: Record<string, unknown>, keys: string[]) {
  for (const key of keys) {
    const value = record[key];
    if (typeof value === "number" && Number.isFinite(value)) {
      return value;
    }
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

  if (isRecord(error)) {
    const nestedMessage = error.message;
    if (typeof nestedMessage === "string" && nestedMessage.trim().length > 0) {
      return nestedMessage;
    }
  }

  return fallback;
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

function asDashboardStatus(value: string | null | undefined): DashboardStatus {
  const normalized = (value ?? "").toLowerCase();

  if (
    normalized.includes("healthy") ||
    normalized.includes("success") ||
    normalized.includes("approved") ||
    normalized.includes("resolved") ||
    normalized.includes("active")
  ) {
    return "success";
  }

  if (
    normalized.includes("running") ||
    normalized.includes("pending") ||
    normalized.includes("queued")
  ) {
    return "running";
  }

  if (
    normalized.includes("warn") ||
    normalized.includes("defer") ||
    normalized.includes("stale")
  ) {
    return "warning";
  }

  if (
    normalized.includes("fail") ||
    normalized.includes("deny") ||
    normalized.includes("error") ||
    normalized.includes("forbidden")
  ) {
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

function mapAlertItems(payload: unknown) {
  return normalizeCollection(payload, ["items", "alerts", "data"])
    .filter(isRecord)
    .flatMap((alert) => {
      const id = pickString(alert, ["id"]);
      if (!id) return [];

      const resolved = alert.resolved === true || pickString(alert, ["resolved"]) === "true";
      return [{
        id,
        kind: "alert" as const,
        title: pickString(alert, ["message"]) ?? "Alert requires review",
        detail: pickString(alert, ["type"]) ?? "Monitoring alert",
        status: resolved ? "success" as const : "error" as const,
        createdAt: toIsoTimestamp(alert.created_at),
        source: "monitoring",
        href: "/dashboard/monitoring",
        meta: pickString(alert, ["agent_id"]),
        resolved,
      }];
    })
    .filter((item) => !item.resolved);
}

function mapApprovalItems(payload: unknown) {
  return normalizeCollection(payload, ["items", "data"])
    .filter(isRecord)
    .flatMap((approval) => {
      const id = pickString(approval, ["id"]);
      if (!id) return [];

      const status = pickString(approval, ["status"]) ?? "PENDING";
      return [{
        id,
        kind: "approval" as const,
        title: pickString(approval, ["action_type"]) ?? "Approval request",
        detail:
          pickString(approval, ["requester"]) ??
          pickString(approval, ["agent_id"]) ??
          "Approval requires operator attention.",
        status: asDashboardStatus(status),
        createdAt: toIsoTimestamp(approval.created_at),
        source: "approvals",
        href: "/dashboard/approvals",
        meta: pickString(approval, ["agent_id"]),
        approvalStatus: status,
      }];
    })
    .filter((item) => (item.approvalStatus ?? "").toUpperCase() === "PENDING");
}

function mapRuntimeItems(payload: unknown) {
  return asArray(payload)
    .filter(isRecord)
    .flatMap((agent) => {
      const agentId = pickString(agent, ["agent_id"]);
      if (!agentId) return [];

      const status = pickString(agent, ["status"]) ?? "unknown";
      return [{
        id: agentId,
        kind: "runtime" as const,
        title: agentId,
        detail:
          pickString(agent, ["error", "policy_name"]) ??
          `Supervisor status: ${status}`,
        status: asDashboardStatus(status),
        createdAt: toIsoTimestamp(agent.started_at),
        source: "runtime supervision",
        href: "/dashboard/security",
        meta: pickString(agent, ["pid"]),
        runtimeStatus: status,
      }];
    })
    .filter((item) => !["running", "active", "healthy"].includes((item.runtimeStatus ?? "").toLowerCase()));
}

function mapGovernanceItem(payload: unknown): NotificationItem | null {
  if (!isRecord(payload)) return null;

  const pendingApprovals = pickNumber(payload, ["pending_approvals"]);
  const status = pickString(payload, ["status"]) ?? "unknown";

  if ((pendingApprovals ?? 0) === 0 && status.toLowerCase() === "healthy") {
    return null;
  }

  return {
    id: "governance-status",
    kind: "governance",
    title: "Governance runtime posture",
    detail:
      pendingApprovals && pendingApprovals > 0
        ? `${pendingApprovals} approval decision${pendingApprovals === 1 ? "" : "s"} waiting in governance.`
        : `Runtime governance status: ${status}.`,
    status: asDashboardStatus(
      pendingApprovals && pendingApprovals > 0 ? "pending" : status,
    ),
    createdAt: null,
    source: "governance",
    href: "/dashboard/security",
    meta: pickString(payload, ["policy_name"]),
  };
}

function mapWebhookItems(deliveries: Array<Record<string, unknown>>) {
  return deliveries.flatMap((delivery) => {
    const id = pickString(delivery, ["id"]);
    if (!id) return [];

    return [{
      id,
      kind: "webhook" as const,
      title: pickString(delivery, ["event"]) ?? "Webhook delivery failed",
      detail:
        pickString(delivery, ["error_message"]) ??
        (pickNumber(delivery, ["status_code"])
          ? `HTTP ${pickNumber(delivery, ["status_code"])}`
          : "Delivery failed"),
      status: "error" as const,
      createdAt: toIsoTimestamp(delivery.created_at ?? delivery.delivered_at),
      source: "webhooks",
      href: "/dashboard/webhooks",
      meta: pickString(delivery, ["webhook_url", "webhook_id"]),
    }];
  });
}

export async function GET(request: NextRequest): Promise<NextResponse> {
  return withErrorHandling(async () => {
    if (!hasAuthSession(request)) {
      return unauthorized();
    }

    const apiBaseUrl = getApiBaseUrl();
    const [alerts, approvals, governance, supervised, webhooks] = await Promise.all([
      fetchResource(
        request,
        `${apiBaseUrl}/v1/monitoring/alerts?limit=12`,
        "Failed to fetch alerts",
      ),
      fetchResource(
        request,
        `${apiBaseUrl}/v1/approvals?status=PENDING&limit=12`,
        "Failed to fetch approvals",
      ),
      fetchResource(
        request,
        `${apiBaseUrl}/v1/runtime/governance/status`,
        "Failed to fetch governance runtime status",
      ),
      fetchResource(
        request,
        `${apiBaseUrl}/v1/runtime/governance/supervised/`,
        "Failed to fetch supervised runtime status",
      ),
      fetchResource(request, `${apiBaseUrl}/v1/webhooks`, "Failed to fetch webhooks"),
    ]);
    const baseResources = [alerts, approvals, governance, supervised, webhooks];

    const unauthenticatedResource = baseResources.find(
      (resource) => resource.status === "unauthenticated",
    );
    if (unauthenticatedResource) {
      return accessFailureResponse(
        request,
        unauthenticatedResource,
        baseResources,
        "Dashboard notification authentication expired.",
      );
    }

    if (baseResources.every((resource) => resource.status === "forbidden")) {
      return accessFailureResponse(
        request,
        baseResources[0],
        baseResources,
        "Dashboard notification access was denied.",
      );
    }

    const webhooksList = normalizeCollection(webhooks.data, ["items", "webhooks", "data"])
      .filter(isRecord)
      .filter((webhook) => Boolean(webhook.is_active))
      .slice(0, 8);

    const deliveryResults = await Promise.all(
      webhooksList.map(async (webhook) => {
        const webhookId = pickString(webhook, ["id"]);
        if (!webhookId) {
          return null;
        }

        const result = await fetchResource(
          request,
          `${apiBaseUrl}/v1/webhooks/${encodeURIComponent(webhookId)}/deliveries?success=false&limit=2`,
          "Failed to fetch webhook deliveries",
        );

        return {
          webhookId,
          webhookUrl: pickString(webhook, ["url"]),
          result,
        };
      }),
    );
    const deliveryResources = deliveryResults
      .filter((entry): entry is NonNullable<typeof entry> => Boolean(entry))
      .map((entry) => entry.result);
    const unauthenticatedDelivery = deliveryResources.find(
      (resource) => resource.status === "unauthenticated",
    );
    if (unauthenticatedDelivery) {
      return accessFailureResponse(
        request,
        unauthenticatedDelivery,
        [...baseResources, ...deliveryResources],
        "Dashboard notification authentication expired.",
      );
    }

    const alertIdentifierFailures = countMissingIdentifiers(
      alerts.data,
      ["items", "alerts", "data"],
      ["id"],
    );
    const approvalIdentifierFailures = countMissingIdentifiers(
      approvals.data,
      ["items", "data"],
      ["id"],
    );
    const runtimeIdentifierFailures = countMissingIdentifiers(
      supervised.data,
      [],
      ["agent_id"],
    );
    const activeWebhookIdentifierFailures = webhooksList.filter(
      (webhook) => !pickString(webhook, ["id"]),
    ).length;

    const alertsSourceStatus: AggregateSourceStatus =
      alerts.status !== "ok"
        ? alerts.status
        : hasCollectionPayload(alerts.data, ["items", "alerts", "data"])
          ? alertIdentifierFailures > 0 ? "partial" : "ok"
          : "error";
    const approvalsSourceStatus: AggregateSourceStatus =
      approvals.status !== "ok"
        ? approvals.status
        : hasCollectionPayload(approvals.data, ["items", "data"])
          ? approvalIdentifierFailures > 0 ? "partial" : "ok"
          : "error";
    const runtimeSourceStatus: AggregateSourceStatus =
      supervised.status !== "ok"
        ? supervised.status
        : Array.isArray(supervised.data)
          ? runtimeIdentifierFailures > 0 ? "partial" : "ok"
          : "error";
    const governanceSourceStatus: AggregateSourceStatus =
      governance.status !== "ok"
        ? governance.status
        : isRecord(governance.data)
          ? "ok"
          : "error";
    const alertItems = mapAlertItems(alerts.data);
    const approvalItems = mapApprovalItems(approvals.data);
    const approvalTotalValue = isRecord(approvals.data)
      ? pickNumber(approvals.data, ["total"]) ?? approvalItems.length
      : approvalItems.length;
    const approvalTotal = Math.max(0, Math.round(approvalTotalValue));
    const runtimeItems = supervised.status === "ok" ? mapRuntimeItems(supervised.data) : [];
    const governanceItem = governance.status === "ok" ? mapGovernanceItem(governance.data) : null;

    const webhookDeliveries = deliveryResults
      .filter((entry): entry is NonNullable<typeof entry> => Boolean(entry))
      .flatMap(({ webhookId, webhookUrl, result }) => {
        if (result.status !== "ok") {
          return [];
        }

        return normalizeCollection(result.data, ["items", "deliveries", "data"])
          .filter(isRecord)
          .filter((delivery) => delivery.success === false)
          .map((delivery) => ({
            ...delivery,
            webhook_id: webhookId,
            webhook_url: webhookUrl,
          }));
      });

    const webhookItems = mapWebhookItems(webhookDeliveries);
    const webhookDeliveryIdentifierFailures = deliveryResults.reduce((total, entry) => {
      if (!entry || entry.result.status !== "ok") return total;
      return total + countMissingIdentifiers(
        entry.result.data,
        ["items", "deliveries", "data"],
        ["id"],
      );
    }, 0);
    const webhookInventoryValid = hasCollectionPayload(webhooks.data, [
      "items",
      "webhooks",
      "data",
    ]);
    const webhookDeliveryPartial =
      activeWebhookIdentifierFailures > 0 ||
      webhookDeliveryIdentifierFailures > 0 ||
      deliveryResults.some((entry) => {
        if (!entry) return false;
        return (
          entry.result.status !== "ok" ||
          !hasCollectionPayload(entry.result.data, ["items", "deliveries", "data"])
        );
      });
    const webhookSourceStatus: AggregateSourceStatus =
      webhooks.status !== "ok"
        ? webhooks.status
        : !webhookInventoryValid
          ? "error"
        : webhookDeliveryPartial
          ? "partial"
          : "ok";
    const items = [
      ...alertItems,
      ...approvalItems,
      ...runtimeItems,
      ...webhookItems,
      ...(governanceItem ? [governanceItem] : []),
    ].sort((left, right) => {
      const leftTime = left.createdAt ? new Date(left.createdAt).getTime() : 0;
      const rightTime = right.createdAt ? new Date(right.createdAt).getTime() : 0;
      return rightTime - leftTime;
    });

    const partials: string[] = [
      "Governance notifications are summarized from runtime status because the backend does not expose a decision-by-decision event feed yet.",
    ];

    if (alertsSourceStatus !== "ok") {
      partials.push(
        alertIdentifierFailures > 0
          ? `${alertIdentifierFailures} monitoring alert record${alertIdentifierFailures === 1 ? " was" : "s were"} omitted because the upstream identifier was missing.`
          : alerts.error ?? "Monitoring alerts returned an invalid or unavailable payload.",
      );
    }

    if (approvalsSourceStatus !== "ok") {
      partials.push(
        approvalIdentifierFailures > 0
          ? `${approvalIdentifierFailures} approval record${approvalIdentifierFailures === 1 ? " was" : "s were"} omitted because the upstream identifier was missing.`
          : approvals.error ?? "Pending approvals returned an invalid or unavailable payload.",
      );
    }

    if (webhookSourceStatus !== "ok" && webhooks.status === "ok" && !webhookInventoryValid) {
      partials.push("Webhook inventory returned an invalid payload.");
    } else if (webhooks.status !== "ok") {
      partials.push(webhooks.error ?? "Webhook inventory is unavailable for this operator session.");
    }

    if (governanceSourceStatus !== "ok") {
      partials.push(
        governance.error ??
          "Governance runtime detail returned an invalid or unavailable payload.",
      );
    }

    if (runtimeSourceStatus !== "ok") {
      partials.push(
        runtimeIdentifierFailures > 0
          ? `${runtimeIdentifierFailures} supervised runtime record${runtimeIdentifierFailures === 1 ? " was" : "s were"} omitted because the upstream agent identifier was missing.`
          : supervised.error ??
            "Supervised runtime incidents returned an invalid or unavailable payload.",
      );
    }

    if (activeWebhookIdentifierFailures > 0) {
      partials.push(
        `${activeWebhookIdentifierFailures} active webhook record${activeWebhookIdentifierFailures === 1 ? " was" : "s were"} omitted because the upstream identifier was missing.`,
      );
    }

    if (webhookDeliveryIdentifierFailures > 0) {
      partials.push(
        `${webhookDeliveryIdentifierFailures} webhook delivery record${webhookDeliveryIdentifierFailures === 1 ? " was" : "s were"} omitted because the upstream identifier was missing.`,
      );
    }

    for (const deliveryResult of deliveryResults) {
      if (!deliveryResult) continue;

      const deliveryPayloadValid = hasCollectionPayload(deliveryResult.result.data, [
        "items",
        "deliveries",
        "data",
      ]);
      if (deliveryResult.result.status !== "ok" || !deliveryPayloadValid) {
        partials.push(
          deliveryResult.result.error ??
            `Webhook delivery history for ${deliveryResult.webhookId} returned an invalid or unavailable payload.`,
        );
      }
    }

    const governancePending = governance.status === "ok" && isRecord(governance.data)
      ? pickNumber(governance.data, ["pending_approvals"])
      : null;

    const nextResponse = NextResponse.json({
      generatedAt: new Date().toISOString(),
      summary: {
        alerts: alertsSourceStatus === "ok" ? alertItems.length : null,
        approvals: approvalsSourceStatus === "ok" ? approvalTotal : null,
        webhookFailures: webhookSourceStatus === "ok" ? webhookItems.length : null,
        runtimeIncidents: runtimeSourceStatus === "ok" ? runtimeItems.length : null,
        governancePendingApprovals: governancePending,
      },
      sources: {
        alerts: alertsSourceStatus,
        approvals: approvalsSourceStatus,
        webhooks: webhookSourceStatus,
        runtime: runtimeSourceStatus,
        governance: governanceSourceStatus,
      },
      items,
      partials,
    });

    const refreshedTokens = pickRefreshedTokens([
        alerts,
        approvals,
        governance,
        supervised,
        webhooks,
        ...deliveryResources,
      ]);

    if (refreshedTokens) {
      applyAuthCookies(nextResponse, request, refreshedTokens);
    }

    return nextResponse;
  })(request);
}
