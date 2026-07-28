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

type AuthTokens = {
  access_token: string;
  refresh_token?: string;
  expires_in: number;
};

type ResourceStatus = "ok" | "partial" | "auth_error" | "error";

type ResourceResult = {
  status: ResourceStatus;
  statusCode: number;
  data: unknown | null;
  error: string | null;
  tokenRefreshed: boolean;
  refreshedTokens?: AuthTokens;
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function normalizeCollection(payload: unknown, keys: string[] = ["items", "data", "sessions"]) {
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

function hasCollection(payload: unknown, keys: string[]) {
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

function collectionTotal(payload: unknown, fallback: number) {
  if (!isRecord(payload)) return fallback;

  const total = payload.total;
  return typeof total === "number" && Number.isFinite(total)
    ? Math.max(0, Math.round(total))
    : fallback;
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

async function fetchResource(
  request: NextRequest,
  url: string,
  fallbackMessage: string,
): Promise<ResourceResult> {
  const { response, tokenRefreshed, refreshedTokens } = await authenticatedFetch(request, url, {
    cache: "no-store",
  });
  const payload = response.status === 204 ? null : await response.json().catch(() => null);

  return {
    status: response.ok
      ? "ok"
      : response.status === 401 || response.status === 403
        ? "auth_error"
        : "error",
    statusCode: response.status,
    data: response.ok ? payload : null,
    error: response.ok ? null : extractErrorMessage(payload, fallbackMessage),
    tokenRefreshed,
    refreshedTokens,
  };
}

function pickRefreshedTokens(results: Array<{ tokenRefreshed: boolean; refreshedTokens?: AuthTokens }>) {
  return results.find((result) => result.tokenRefreshed)?.refreshedTokens;
}

async function readJsonFile<T>(filePath: string): Promise<{ available: boolean; value: T | null }> {
  try {
    const raw = await fs.readFile(filePath, "utf-8");
    return { available: true, value: JSON.parse(raw) as T };
  } catch {
    return { available: false, value: null };
  }
}

async function readAutonomySnapshot() {
  if (process.env.NODE_ENV !== "development") {
    return {
      available: false,
      error: "Autonomy queue data is local-only and not available in this shell.",
      data: null as null | {
        queued: number;
        running: number;
        parked: number;
        completed: number;
        activeRunners: number;
      },
    };
  }

  const repoRoot = process.env.MUTX_REPO_ROOT || process.cwd();
  const autonomyDir = path.join(repoRoot, ".autonomy");
  const queueResult = await readJsonFile<{ items?: Array<{ status?: string }> }>(
    path.join(repoRoot, "mutx-engineering-agents/dispatch/action-queue.json"),
  );
  const daemonResult = await readJsonFile<{ active_runners?: unknown[] }>(
    path.join(autonomyDir, "daemon-status.json"),
  );

  if (!queueResult.available || !daemonResult.available) {
    return {
      available: false,
      error: "Local autonomy queue or daemon status is unavailable; zero backlog is not assumed.",
      data: null,
    };
  }

  const items = Array.isArray(queueResult.value?.items) ? queueResult.value.items : [];
  const counts = items.reduce<Record<string, number>>((acc, item) => {
    const key = item.status || "unknown";
    acc[key] = (acc[key] || 0) + 1;
    return acc;
  }, {});

  return {
    available: true,
    error: null,
    data: {
      queued: counts.queued ?? 0,
      running: counts.running ?? 0,
      parked: counts.parked ?? 0,
      completed: counts.completed ?? 0,
      activeRunners: Array.isArray(daemonResult.value?.active_runners)
        ? daemonResult.value.active_runners.length
        : 0,
    },
  };
}

export async function GET(request: NextRequest): Promise<NextResponse> {
  return withErrorHandling(async () => {
    if (!hasAuthSession(request)) {
      return unauthorized();
    }

    const apiBaseUrl = getApiBaseUrl();
    const authResponse = await authenticatedFetch(request, `${apiBaseUrl}/v1/auth/me`, {
      cache: "no-store",
    });
    const authPayload = await authResponse.response
      .json()
      .catch(() => ({ detail: "Failed to fetch current operator" }));

    if (!authResponse.response.ok) {
      const nextResponse = NextResponse.json(authPayload, {
        status: authResponse.response.status,
      });

      if (authResponse.tokenRefreshed && authResponse.refreshedTokens) {
        applyAuthCookies(nextResponse, request, authResponse.refreshedTokens);
      }

      return nextResponse;
    }

    const [approvals, runs, sessions, blueprints, autonomy] = await Promise.all([
      fetchResource(request, `${apiBaseUrl}/v1/approvals?status=PENDING&limit=12`, "Failed to fetch approvals"),
      fetchResource(request, `${apiBaseUrl}/v1/runs?limit=18`, "Failed to fetch runs"),
      fetchResource(request, `${apiBaseUrl}/v1/sessions?limit=18`, "Failed to fetch sessions"),
      fetchResource(request, `${apiBaseUrl}/v1/swarms/blueprints`, "Failed to fetch swarm blueprints"),
      readAutonomySnapshot(),
    ]);

    const approvalRecords = normalizeCollection(approvals.data, ["items", "data"])
      .filter(isRecord)
      .filter(
        (approval) => (pickString(approval, ["status"]) ?? "PENDING").toUpperCase() === "PENDING",
      );
    const runRecords = normalizeCollection(runs.data, ["items", "data"]).filter(isRecord);
    const failedRunRecords = runRecords.filter((run) =>
      ["failed", "error"].includes((pickString(run, ["status"]) ?? "unknown").toLowerCase()),
    );
    const sessionRecords = normalizeCollection(sessions.data, ["sessions", "items", "data"])
      .filter(isRecord)
      .filter((session) => !session.active);
    const blueprintRecords = normalizeCollection(blueprints.data, ["items", "data"])
      .filter(isRecord);
    const missingApprovalIds = approvalRecords.filter(
      (approval) => !pickString(approval, ["id"]),
    ).length;
    const missingRunIds = failedRunRecords.filter((run) => !pickString(run, ["id"])).length;
    const missingSessionIds = sessionRecords.filter(
      (session) => !pickString(session, ["id", "session_id", "key"]),
    ).length;
    const missingBlueprintIds = blueprintRecords.filter(
      (blueprint) => !pickString(blueprint, ["id"]),
    ).length;
    const approvalCollectionValid = hasCollection(approvals.data, ["items", "data"]);
    const runCollectionValid = hasCollection(runs.data, ["items", "data"]);
    const sessionCollectionValid = hasCollection(sessions.data, ["sessions", "items", "data"]);
    const blueprintCollectionValid = hasCollection(blueprints.data, ["items", "data"]);

    const approvalItems = approvalRecords.flatMap((approval) => {
      const id = pickString(approval, ["id"]);
      if (!id) return [];
      return [{
        id,
        ownerId: pickString(approval, ["owner_id"]),
        reviewerId: pickString(approval, ["reviewer_id"]),
        canResolve: approval.can_resolve === true,
        agentId: pickString(approval, ["agent_id"]),
        actionType: pickString(approval, ["action_type"]) ?? "approval",
        requester: pickString(approval, ["requester"]) ?? "operator",
        status: pickString(approval, ["status"]) ?? "PENDING",
        createdAt: toIsoTimestamp(approval.created_at),
      }];
    });
    const approvalsComplete =
      approvals.status === "ok" && approvalCollectionValid && missingApprovalIds === 0;
    const runsComplete = runs.status === "ok" && runCollectionValid && missingRunIds === 0;
    const sessionsComplete =
      sessions.status === "ok" && sessionCollectionValid && missingSessionIds === 0;
    const blueprintsComplete =
      blueprints.status === "ok" && blueprintCollectionValid && missingBlueprintIds === 0;
    const pendingApprovalTotal = approvalsComplete
      ? collectionTotal(approvals.data, approvalItems.length)
      : null;

    const runRecoveries = failedRunRecords.flatMap((run) => {
        const id = pickString(run, ["id"]);
        if (!id) return [];
        const status = pickString(run, ["status"]) ?? "unknown";
        return [{
          id,
          kind: "run" as const,
          title:
            pickString(run, ["subject_label", "agent_id"]) ??
            "Execution recovery",
          detail:
            pickString(run, ["error_message", "output_text"]) ??
            `Run status: ${status}`,
          status,
          createdAt: toIsoTimestamp(run.completed_at ?? run.started_at ?? run.created_at),
          href: "/dashboard/runs",
        }];
      });

    const sessionRecoveries = sessionRecords.flatMap((session) => {
      const id = pickString(session, ["id", "session_id", "key"]);
      if (!id) return [];
      return [{
        id,
        kind: "session" as const,
        title:
          pickString(session, ["agent", "assistant", "name"]) ??
          "Inactive session",
        detail:
          pickString(session, ["source", "channel"]) ??
          "Session is present but not currently active.",
        status: "inactive",
        createdAt: toIsoTimestamp(session.last_activity ?? session.lastActivity),
        href: "/dashboard/sessions",
      }];
    });

    const recoveries = [...runRecoveries, ...sessionRecoveries]
      .sort((left, right) => {
        const leftTime = left.createdAt ? new Date(left.createdAt).getTime() : 0;
        const rightTime = right.createdAt ? new Date(right.createdAt).getTime() : 0;
        return rightTime - leftTime;
      })
      .slice(0, 12);

    const blueprintItems = blueprintRecords.flatMap((blueprint) => {
      const id = pickString(blueprint, ["id"]);
      if (!id) return [];
      return [{
        id,
        name: pickString(blueprint, ["name"]) ?? "Blueprint",
        summary: pickString(blueprint, ["summary"]) ?? "Coordination blueprint",
        recommendedAgents: `${blueprint.recommended_min_agents ?? 1}-${blueprint.recommended_max_agents ?? 1}`,
        roles: Array.isArray(blueprint.roles) ? blueprint.roles.length : 0,
        tags: Array.isArray(blueprint.tags)
          ? blueprint.tags.filter(
              (tag): tag is string => typeof tag === "string" && tag.trim().length > 0,
            )
          : [],
      }];
    });

    const partials: string[] = [
      "Recovery and blueprint data are read-only; pending approval requests can be decided from this board.",
    ];

    if (approvals.status !== "ok") {
      partials.push(approvals.error ?? "Approval queue detail is unavailable.");
    }
    if (runs.status !== "ok") {
      partials.push(runs.error ?? "Run recovery detail is unavailable.");
    }
    if (sessions.status !== "ok") {
      partials.push(sessions.error ?? "Session recovery detail is unavailable.");
    }
    if (blueprints.status !== "ok") {
      partials.push(blueprints.error ?? "Swarm blueprint inventory is unavailable.");
    }
    if (!autonomy.available && autonomy.error) {
      partials.push(autonomy.error);
    }
    if (approvals.status === "ok" && !approvalCollectionValid) {
      partials.push("Approval queue returned an invalid collection envelope.");
    }
    if (runs.status === "ok" && !runCollectionValid) {
      partials.push("Run recovery data returned an invalid collection envelope.");
    }
    if (sessions.status === "ok" && !sessionCollectionValid) {
      partials.push("Session recovery data returned an invalid collection envelope.");
    }
    if (blueprints.status === "ok" && !blueprintCollectionValid) {
      partials.push("Blueprint inventory returned an invalid collection envelope.");
    }
    if (missingApprovalIds > 0) {
      partials.push(
        `${missingApprovalIds} approval record${missingApprovalIds === 1 ? " was" : "s were"} omitted because the upstream identifier was missing.`,
      );
    }
    if (missingRunIds > 0) {
      partials.push(
        `${missingRunIds} failed run record${missingRunIds === 1 ? " was" : "s were"} omitted because the upstream identifier was missing.`,
      );
    }
    if (missingSessionIds > 0) {
      partials.push(
        `${missingSessionIds} inactive session record${missingSessionIds === 1 ? " was" : "s were"} omitted because the upstream identifier was missing.`,
      );
    }
    if (missingBlueprintIds > 0) {
      partials.push(
        `${missingBlueprintIds} blueprint record${missingBlueprintIds === 1 ? " was" : "s were"} omitted because the upstream identifier was missing.`,
      );
    }

    const nextResponse = NextResponse.json({
      generatedAt: new Date().toISOString(),
      sourceStatus: {
        approvals:
          approvals.status === "ok" && (!approvalCollectionValid || missingApprovalIds > 0)
            ? "partial"
            : approvals.status,
        runs:
          runs.status === "ok" && (!runCollectionValid || missingRunIds > 0)
            ? "partial"
            : runs.status,
        sessions:
          sessions.status === "ok" && (!sessionCollectionValid || missingSessionIds > 0)
            ? "partial"
            : sessions.status,
        blueprints:
          blueprints.status === "ok" && (!blueprintCollectionValid || missingBlueprintIds > 0)
            ? "partial"
            : blueprints.status,
        autonomy: autonomy.available ? "ok" : "partial",
      },
      summary: {
        pendingApprovals: pendingApprovalTotal,
        recoveryWatch: runsComplete && sessionsComplete ? recoveries.length : null,
        blueprints: blueprintsComplete ? blueprintItems.length : null,
        queuedAutonomy: autonomy.data?.queued ?? null,
        runningAutonomy: autonomy.data?.running ?? null,
      },
      approvals: approvalItems,
      recoveries,
      blueprints: blueprintItems,
      autonomy: autonomy.available ? autonomy.data : null,
      partials,
    });

    const refreshedTokens =
      authResponse.refreshedTokens || pickRefreshedTokens([approvals, runs, sessions, blueprints]);

    if (refreshedTokens) {
      applyAuthCookies(nextResponse, request, refreshedTokens);
    }

    return nextResponse;
  })(request);
}
