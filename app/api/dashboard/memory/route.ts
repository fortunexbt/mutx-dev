import { NextRequest, NextResponse } from "next/server";

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

function pickBoolean(record: Record<string, unknown>, keys: string[], fallback = false) {
  for (const key of keys) {
    const value = record[key];
    if (typeof value === "boolean") return value;
    if (value === "true" || value === 1) return true;
    if (value === "false" || value === 0) return false;
  }

  return fallback;
}

function normalizeStringList(value: unknown) {
  if (!Array.isArray(value)) return [];

  return value
    .filter((item): item is string => typeof item === "string")
    .map((item) => item.trim())
    .filter(Boolean);
}

function normalizeTimestamp(value: unknown) {
  if (value === null || value === undefined || value === "") return null;

  let date: Date;
  if (typeof value === "number" && Number.isFinite(value)) {
    if (value <= 0) return null;
    date = new Date(value < 1_000_000_000_000 ? value * 1000 : value);
  } else if (typeof value === "string") {
    const trimmed = value.trim();
    if (!trimmed) return null;

    const numeric = Number(trimmed);
    date = Number.isFinite(numeric)
      ? new Date(numeric < 1_000_000_000_000 ? numeric * 1000 : numeric)
      : new Date(trimmed);
  } else {
    return null;
  }

  return Number.isNaN(date.getTime()) ? null : date.toISOString();
}

function resultSummary(job: Record<string, unknown>) {
  const value = job.result_summary ?? job.resultSummary;
  if (typeof value === "string" && value.trim().length > 0) {
    return value;
  }

  if (!isRecord(value)) return null;
  return pickString(value, ["summary", "message", "result", "detail"]);
}

function normalizeAssistant(value: unknown) {
  if (!isRecord(value)) return null;

  return {
    name: pickString(value, ["name", "label", "assistant_id", "agent_id"]) ?? "Assistant",
    workspace: pickString(value, ["workspace", "assistant_id", "agent_id"]) ?? "unpublished",
    status: pickString(value, ["status", "onboarding_status"]) ?? "unknown",
  };
}

function normalizeSession(session: Record<string, unknown>) {
  const id = pickString(session, ["id", "key", "session_key"]);
  if (!id) return null;

  return {
    id,
    label: pickString(session, ["label", "agent", "name", "key", "session_key"]) ?? id,
    source: pickString(session, ["source"]) ?? "unknown",
    channel: pickString(session, ["channel"]) ?? "direct",
    active: pickBoolean(session, ["active"]),
    kind: pickString(session, ["kind", "type"]) ?? "session",
    model: pickString(session, ["model", "provider_model"]) ?? "unknown",
    lastActivity: normalizeTimestamp(
      session.last_activity ?? session.lastActivity ?? session.updated_at ?? session.updatedAt,
    ),
    flags: normalizeStringList(session.flags),
  };
}

function normalizeJob(job: Record<string, unknown>) {
  const id = pickString(job, ["id"]);
  if (!id) return null;

  return {
    id,
    templateId: pickString(job, ["template_id", "templateId"]) ?? "unpublished",
    status: pickString(job, ["status"]) ?? "unknown",
    executionMode: pickString(job, ["execution_mode", "executionMode"]) ?? "unknown",
    artifacts: artifactCount(job),
    createdAt: normalizeTimestamp(job.created_at ?? job.createdAt),
    updatedAt: normalizeTimestamp(job.updated_at ?? job.updatedAt),
    resultSummary: resultSummary(job),
    errorMessage: pickString(job, ["error_message", "errorMessage"]),
  };
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

function artifactCount(job: Record<string, unknown>) {
  if (Array.isArray(job.artifacts)) return job.artifacts.length;
  if (typeof job.artifacts === "number" && Number.isFinite(job.artifacts)) {
    return Math.max(0, Math.trunc(job.artifacts));
  }

  return 0;
}

function pickRefreshedTokens(results: Array<{ tokenRefreshed: boolean; refreshedTokens?: AuthTokens }>) {
  return results.find((result) => result.tokenRefreshed)?.refreshedTokens;
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

    const overview = await fetchResource(
      request,
      `${apiBaseUrl}/v1/assistant/overview`,
      "Failed to fetch assistant overview",
    );
    const assistant =
      overview.status === "ok" && isRecord(overview.data) && isRecord(overview.data.assistant)
        ? overview.data.assistant
        : null;
    const agentId = assistant ? pickString(assistant, ["agent_id", "id"]) : null;

    const sessions = await fetchResource(
      request,
      agentId
        ? `${apiBaseUrl}/v1/sessions?agent_id=${encodeURIComponent(agentId)}`
        : `${apiBaseUrl}/v1/sessions`,
      "Failed to fetch assistant sessions",
    );
    const documentJobs = await fetchResource(
      request,
      `${apiBaseUrl}/v1/documents/jobs?limit=20`,
      "Failed to fetch document jobs",
    );
    const reasoningJobs = await fetchResource(
      request,
      `${apiBaseUrl}/v1/reasoning/jobs?limit=20`,
      "Failed to fetch reasoning jobs",
    );

    const sessionRecords = normalizeCollection(sessions.data, ["sessions", "items", "data"])
      .filter(isRecord);
    const documentRecords = normalizeCollection(documentJobs.data, ["items", "data"])
      .filter(isRecord);
    const reasoningRecords = normalizeCollection(reasoningJobs.data, ["items", "data"])
      .filter(isRecord);
    const missingSessionIds = sessionRecords.filter(
      (session) => !pickString(session, ["id", "key", "session_key"]),
    ).length;
    const missingDocumentIds = documentRecords.filter((job) => !pickString(job, ["id"])).length;
    const missingReasoningIds = reasoningRecords.filter((job) => !pickString(job, ["id"])).length;
    const sessionCollectionValid = hasCollection(sessions.data, ["sessions", "items", "data"]);
    const documentCollectionValid = hasCollection(documentJobs.data, ["items", "data"]);
    const reasoningCollectionValid = hasCollection(reasoningJobs.data, ["items", "data"]);
    const sessionItems = sessionRecords.flatMap((session) => {
      const normalized = normalizeSession(session);
      return normalized ? [normalized] : [];
    });
    const documentItems = documentRecords.flatMap((job) => {
      const normalized = normalizeJob(job);
      return normalized ? [normalized] : [];
    });
    const reasoningItems = reasoningRecords.flatMap((job) => {
      const normalized = normalizeJob(job);
      return normalized ? [normalized] : [];
    });
    const sessionComplete =
      sessions.status === "ok" && sessionCollectionValid && missingSessionIds === 0;
    const documentsComplete =
      documentJobs.status === "ok" && documentCollectionValid && missingDocumentIds === 0;
    const reasoningComplete =
      reasoningJobs.status === "ok" && reasoningCollectionValid && missingReasoningIds === 0;
    const sourceCounts = new Map<string, number>();
    for (const session of sessionItems) {
      sourceCounts.set(session.source, (sourceCounts.get(session.source) ?? 0) + 1);
    }
    const sources = [...sourceCounts.entries()]
      .map(([source, count]) => ({ source, count }))
      .sort((left, right) => right.count - left.count || left.source.localeCompare(right.source));
    const partials = [
      "Memory inventory is read-only and derived from live sessions plus artifact-producing jobs.",
    ];

    if (overview.status !== "ok") partials.push(overview.error ?? "Assistant overview is unavailable.");
    if (sessions.status !== "ok") partials.push(sessions.error ?? "Session memory is unavailable.");
    if (documentJobs.status !== "ok") partials.push(documentJobs.error ?? "Document jobs are unavailable.");
    if (reasoningJobs.status !== "ok") partials.push(reasoningJobs.error ?? "Reasoning jobs are unavailable.");
    if (sessions.status === "ok" && !sessionCollectionValid) {
      partials.push("Session memory returned an invalid collection envelope.");
    }
    if (documentJobs.status === "ok" && !documentCollectionValid) {
      partials.push("Document jobs returned an invalid collection envelope.");
    }
    if (reasoningJobs.status === "ok" && !reasoningCollectionValid) {
      partials.push("Reasoning jobs returned an invalid collection envelope.");
    }
    if (missingSessionIds > 0) {
      partials.push(
        `${missingSessionIds} session record${missingSessionIds === 1 ? " was" : "s were"} omitted because the upstream identifier was missing.`,
      );
    }
    if (missingDocumentIds > 0) {
      partials.push(
        `${missingDocumentIds} document job record${missingDocumentIds === 1 ? " was" : "s were"} omitted because the upstream identifier was missing.`,
      );
    }
    if (missingReasoningIds > 0) {
      partials.push(
        `${missingReasoningIds} reasoning job record${missingReasoningIds === 1 ? " was" : "s were"} omitted because the upstream identifier was missing.`,
      );
    }

    const nextResponse = NextResponse.json({
      generatedAt: new Date().toISOString(),
      assistant: normalizeAssistant(assistant),
      sourceStatus: {
        assistant: overview.status,
        sessions:
          sessions.status === "ok" && (!sessionCollectionValid || missingSessionIds > 0)
            ? "partial"
            : sessions.status,
        documents:
          documentJobs.status === "ok" && (!documentCollectionValid || missingDocumentIds > 0)
            ? "partial"
            : documentJobs.status,
        reasoning:
          reasoningJobs.status === "ok" && (!reasoningCollectionValid || missingReasoningIds > 0)
            ? "partial"
            : reasoningJobs.status,
      },
      summary: {
        sessions: sessionComplete ? sessionItems.length : null,
        activeSessions: sessionComplete
          ? sessionItems.filter((session) => session.active).length
          : null,
        sources: sessionComplete ? sources.length : null,
        documentJobs: documentsComplete ? documentItems.length : null,
        documentArtifacts: documentsComplete
          ? documentItems.reduce((sum, job) => sum + job.artifacts, 0)
          : null,
        reasoningJobs: reasoningComplete ? reasoningItems.length : null,
        reasoningArtifacts: reasoningComplete
          ? reasoningItems.reduce((sum, job) => sum + job.artifacts, 0)
          : null,
      },
      sessions: sessionItems,
      sources,
      documents: documentItems,
      reasoning: reasoningItems,
      partials,
    });

    const refreshedTokens =
      authResponse.refreshedTokens ||
      pickRefreshedTokens([overview, sessions, documentJobs, reasoningJobs]);

    if (refreshedTokens) {
      applyAuthCookies(nextResponse, request, refreshedTokens);
    }

    return nextResponse;
  })(request);
}
