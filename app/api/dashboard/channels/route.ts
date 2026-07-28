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

    const assistantRecord =
      overview.status === "ok" && isRecord(overview.data) && isRecord(overview.data.assistant)
        ? overview.data.assistant
        : null;
    const overviewPayloadValid =
      overview.status === "ok" &&
      isRecord(overview.data) &&
      typeof overview.data.has_assistant === "boolean" &&
      (overview.data.has_assistant === false || Boolean(assistantRecord));
    const hasAssistant =
      overviewPayloadValid &&
      isRecord(overview.data) &&
      Boolean(overview.data.has_assistant) &&
      Boolean(assistantRecord);
    const agentId = assistantRecord ? pickString(assistantRecord, ["agent_id"]) : null;

    const [channelsResult, sessionsResult] = hasAssistant && agentId
      ? await Promise.all([
          fetchResource(
            request,
            `${apiBaseUrl}/v1/assistant/${encodeURIComponent(agentId)}/channels`,
            "Failed to fetch assistant channels",
          ),
          fetchResource(
            request,
            `${apiBaseUrl}/v1/sessions?agent_id=${encodeURIComponent(agentId)}`,
            "Failed to fetch assistant sessions",
          ),
        ])
      : [
          { status: "ok", statusCode: 200, data: null, error: null, tokenRefreshed: false } as ResourceResult,
          { status: "ok", statusCode: 200, data: null, error: null, tokenRefreshed: false } as ResourceResult,
        ];

    const overviewChannelsValid = Boolean(
      assistantRecord && hasCollection(assistantRecord.channels, ["items", "data"]),
    );
    const liveChannelsValid = hasAssistant && agentId
      ? hasCollection(channelsResult.data, ["items", "data"])
      : true;
    const sessionCollectionValid = hasAssistant && agentId
      ? hasCollection(sessionsResult.data, ["sessions", "items", "data"])
      : true;
    const channelRecords = (
      channelsResult.status === "ok" && liveChannelsValid
        ? normalizeCollection(channelsResult.data, ["items", "data"])
        : overviewChannelsValid && assistantRecord
          ? normalizeCollection(assistantRecord.channels, ["items", "data"])
          : []
    ).filter(isRecord);
    const sessionRecords = normalizeCollection(sessionsResult.data, ["sessions", "items", "data"])
      .filter(isRecord);
    const missingChannelIds = channelRecords.filter(
      (channel) => !pickString(channel, ["id"]),
    ).length;
    const sessionsMissingChannels = sessionRecords.filter(
      (session) => !pickString(session, ["channel"]),
    ).length;
    const channelsComplete =
      overviewPayloadValid &&
      (!hasAssistant ||
        (Boolean(agentId) &&
          channelsResult.status === "ok" &&
          liveChannelsValid &&
          missingChannelIds === 0));
    const sessionsComplete =
      overviewPayloadValid &&
      (!hasAssistant ||
        (Boolean(agentId) &&
          sessionsResult.status === "ok" &&
          sessionCollectionValid &&
          sessionsMissingChannels === 0));

    const channels = channelRecords.flatMap((channel) => {
      const channelId = pickString(channel, ["id"]);
      if (!channelId) return [];
      const channelSessions = sessionRecords.filter(
        (session) => pickString(session, ["channel"]) === channelId,
      );
      const activeSessions = channelSessions.filter((session) => Boolean(session.active)).length;
      const latestActivity = channelSessions.reduce<string | null>((latest, session) => {
        const candidate = toIsoTimestamp(session.last_activity ?? session.lastActivity);
        if (!candidate) return latest;
        if (!latest) return candidate;
        return new Date(candidate).getTime() > new Date(latest).getTime() ? candidate : latest;
      }, null);
      const sources = Array.from(
        new Set(
          channelSessions
            .map((session) => pickString(session, ["source"]))
            .filter((value): value is string => Boolean(value)),
        ),
      );

      return [{
        id: channelId,
        label: pickString(channel, ["label"]) ?? channelId,
        enabled: Boolean(channel.enabled),
        mode: pickString(channel, ["mode"]) ?? "unknown",
        allowFrom: Array.isArray(channel.allow_from)
          ? channel.allow_from.filter(
              (entry): entry is string => typeof entry === "string" && entry.trim().length > 0,
            )
          : [],
        sessionCount: channelSessions.length,
        activeSessions,
        latestActivity,
        sources,
      }];
    });

    const sessionSourceMap = new Map<string, number>();
    for (const session of normalizeCollection(sessionsResult.data, ["sessions", "items", "data"]).filter(
      isRecord,
    )) {
      const source = pickString(session, ["source"]) ?? "unknown";
      sessionSourceMap.set(source, (sessionSourceMap.get(source) ?? 0) + 1);
    }

    const partials: string[] = [];

    if (overview.status !== "ok") {
      partials.push(overview.error ?? "Assistant overview is unavailable.");
    } else if (!overviewPayloadValid) {
      partials.push("Assistant overview returned an invalid envelope.");
    }

    if (hasAssistant && channelsResult.status !== "ok") {
      partials.push(
        channelsResult.error ??
          "Channel detail is unavailable, so the surface is falling back to assistant overview data.",
      );
    }

    if (hasAssistant && sessionsResult.status !== "ok") {
      partials.push(
        sessionsResult.error ??
          "Session activity is unavailable, so live channel counts are partial.",
      );
    }
    if (hasAssistant && !agentId) {
      partials.push(
        "Assistant overview did not publish an agent identifier, so channel and session totals are unavailable.",
      );
    }
    if (hasAssistant && channelsResult.status === "ok" && !liveChannelsValid) {
      partials.push("Assistant channels returned an invalid collection envelope.");
    }
    if (hasAssistant && sessionsResult.status === "ok" && !sessionCollectionValid) {
      partials.push("Assistant sessions returned an invalid collection envelope.");
    }
    if (missingChannelIds > 0) {
      partials.push(
        `${missingChannelIds} channel record${missingChannelIds === 1 ? " was" : "s were"} omitted because the upstream identifier was missing.`,
      );
    }
    if (sessionsMissingChannels > 0) {
      partials.push(
        `${sessionsMissingChannels} session record${sessionsMissingChannels === 1 ? " was" : "s were"} omitted from channel counts because the upstream channel identifier was missing.`,
      );
    }

    const nextResponse = NextResponse.json({
      generatedAt: new Date().toISOString(),
      hasAssistant,
      sourceStatus: {
        overview:
          overview.status === "ok" && !overviewPayloadValid ? "partial" : overview.status,
        channels: channelsComplete ? "ok" : "partial",
        sessions: sessionsComplete ? "ok" : "partial",
      },
      assistant: hasAssistant && assistantRecord
        ? {
            agentId,
            name: pickString(assistantRecord, ["name"]) ?? "Assistant",
            workspace: pickString(assistantRecord, ["workspace"]) ?? "default",
            status: pickString(assistantRecord, ["status"]) ?? "unknown",
            gatewayStatus: isRecord(assistantRecord.gateway)
              ? pickString(assistantRecord.gateway, ["status"]) ?? "unknown"
              : "unknown",
            gatewayUrl: isRecord(assistantRecord.gateway)
              ? pickString(assistantRecord.gateway, ["gateway_url"])
              : null,
            doctorSummary: isRecord(assistantRecord.gateway)
              ? pickString(assistantRecord.gateway, ["doctor_summary"]) ?? "No gateway doctor summary available."
              : "No gateway doctor summary available.",
            wakeups: Array.isArray(assistantRecord.wakeups) ? assistantRecord.wakeups : [],
          }
        : null,
      summary: {
        configuredChannels: channelsComplete ? channels.length : null,
        enabledChannels: channelsComplete
          ? channels.filter((channel) => channel.enabled).length
          : null,
        liveChannels: channelsComplete && sessionsComplete
          ? channels.filter((channel) => channel.activeSessions > 0).length
          : null,
        activeSessions: channelsComplete && sessionsComplete
          ? channels.reduce((sum, channel) => sum + channel.activeSessions, 0)
          : null,
        sources: sessionsComplete ? sessionSourceMap.size : null,
      },
      channels,
      sessionSources: Array.from(sessionSourceMap.entries()).map(([source, count]) => ({
        source,
        count,
      })),
      partials,
    });

    const refreshedTokens =
      authResponse.refreshedTokens ||
      pickRefreshedTokens([overview, channelsResult, sessionsResult]);

    if (refreshedTokens) {
      applyAuthCookies(nextResponse, request, refreshedTokens);
    }

    return nextResponse;
  })(request);
}
