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

type OverviewResourceStatus = "ok" | "unauthenticated" | "forbidden" | "error";

type OverviewResourceResult = {
  status: OverviewResourceStatus;
  statusCode: number;
  data: unknown | null;
  error: string | null;
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
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

async function fetchOverviewResource(
  request: NextRequest,
  url: string,
  fallbackMessage: string,
): Promise<{
  result: OverviewResourceResult;
  tokenRefreshed: boolean;
  refreshedTokens?: { access_token: string; refresh_token?: string; expires_in: number };
}> {
  try {
    const { response, tokenRefreshed, refreshedTokens } = await authenticatedFetch(request, url, {
      cache: "no-store",
      signal: AbortSignal.timeout(UPSTREAM_TIMEOUT_MS),
    });
    const payload = response.status === 204 ? null : await response.json().catch(() => null);

    if (response.ok && payload === null) {
      return {
        result: {
          status: "error",
          statusCode: 502,
          data: null,
          error: `${fallbackMessage}: upstream returned no data.`,
        },
        tokenRefreshed,
        refreshedTokens,
      };
    }

    return {
      result: {
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
      },
      tokenRefreshed,
      refreshedTokens,
    };
  } catch (error) {
    const errorName =
      error && typeof error === "object" && "name" in error ? String(error.name) : "";
    const timedOut = errorName === "AbortError" || errorName === "TimeoutError";

    return {
      result: {
        status: "error",
        statusCode: timedOut ? 504 : 502,
        data: null,
        error: timedOut
          ? `${fallbackMessage}: upstream request timed out.`
          : `${fallbackMessage}: upstream request failed.`,
      },
      tokenRefreshed: false,
    };
  }
}

export async function GET(request: NextRequest): Promise<NextResponse> {
  return withErrorHandling(async () => {
    if (!hasAuthSession(request)) {
      return unauthorized();
    }

    const apiBaseUrl = getApiBaseUrl();
    const authResponse = await authenticatedFetch(request, `${apiBaseUrl}/v1/auth/me`, {
      cache: "no-store",
      signal: AbortSignal.timeout(UPSTREAM_TIMEOUT_MS),
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

    const resourceEntries = await Promise.all(
      [
        ["agents", `${apiBaseUrl}/v1/agents?limit=20`, "Failed to fetch agents"],
        ["deployments", `${apiBaseUrl}/v1/deployments?limit=20`, "Failed to fetch deployments"],
        ["runs", `${apiBaseUrl}/v1/runs?limit=24`, "Failed to fetch runs"],
        ["alerts", `${apiBaseUrl}/v1/monitoring/alerts?limit=12`, "Failed to fetch alerts"],
        ["webhooks", `${apiBaseUrl}/v1/webhooks`, "Failed to fetch webhooks"],
        ["budget", `${apiBaseUrl}/v1/budgets`, "Failed to fetch budget"],
        ["health", `${apiBaseUrl}/health`, "Failed to fetch health"],
        [
          "runtime",
          `${apiBaseUrl}/v1/runtime/providers/openclaw`,
          "Failed to fetch OpenClaw runtime",
        ],
        [
          "onboarding",
          `${apiBaseUrl}/v1/onboarding?provider=openclaw`,
          "Failed to fetch OpenClaw onboarding state",
        ],
        ["securityMetrics", `${apiBaseUrl}/v1/security/metrics`, "Failed to fetch security metrics"],
        [
          "securityCompliance",
          `${apiBaseUrl}/v1/security/compliance`,
          "Failed to fetch security compliance",
        ],
        [
          "securityApprovals",
          `${apiBaseUrl}/v1/approvals?status=PENDING&limit=12`,
          "Failed to fetch security approvals",
        ],
        [
          "governanceCredentialBackends",
          `${apiBaseUrl}/v1/governance/credentials/backends`,
          "Failed to fetch governance credential backends",
        ],
        [
          "governanceTrust",
          `${apiBaseUrl}/v1/governance/trust`,
          "Failed to fetch governance trust",
        ],
        [
          "governanceLifecycle",
          `${apiBaseUrl}/v1/governance/lifecycle`,
          "Failed to fetch governance lifecycle",
        ],
        [
          "governanceDiscovery",
          `${apiBaseUrl}/v1/governance/discovery`,
          "Failed to fetch governance discovery",
        ],
        [
          "governanceAttestation",
          `${apiBaseUrl}/v1/governance/attestations`,
          "Failed to fetch governance attestation",
        ],
        [
          "governanceRuntimeStatus",
          `${apiBaseUrl}/v1/runtime/governance/status`,
          "Failed to fetch governance runtime status",
        ],
        [
          "governedSupervision",
          `${apiBaseUrl}/v1/runtime/governance/supervised/`,
          "Failed to fetch governed supervision",
        ],
        [
          "governedProfiles",
          `${apiBaseUrl}/v1/runtime/governance/supervised/profiles`,
          "Failed to fetch governed profiles",
        ],
      ].map(async ([key, url, fallbackMessage]) => {
        const resource = await fetchOverviewResource(request, url, fallbackMessage);
        return { key, resource };
      }),
    );

    const unauthenticatedResource = resourceEntries.find(
      ({ resource }) => resource.result.status === "unauthenticated",
    );
    const forbiddenResource = resourceEntries.every(
      ({ resource }) => resource.result.status === "forbidden",
    )
      ? resourceEntries[0]
      : undefined;
    const accessFailure = unauthenticatedResource ?? forbiddenResource;

    if (accessFailure) {
      const nextResponse = NextResponse.json(
        {
          detail:
            accessFailure.resource.result.error ??
            (accessFailure.resource.result.status === "unauthenticated"
              ? "Dashboard overview authentication expired."
              : "Dashboard overview access was denied."),
        },
        { status: accessFailure.resource.result.statusCode },
      );
      const refreshedTokens =
        resourceEntries.find(({ resource }) => resource.tokenRefreshed)?.resource.refreshedTokens ||
        authResponse.refreshedTokens;

      if (refreshedTokens) {
        applyAuthCookies(nextResponse, request, refreshedTokens);
      }

      return nextResponse;
    }

    const resources = Object.fromEntries(
      resourceEntries.map(({ key, resource }) => [key, resource.result]),
    );
    const refreshedTokens =
      resourceEntries.find(({ resource }) => resource.tokenRefreshed)?.resource.refreshedTokens ||
      authResponse.refreshedTokens;

    const nextResponse = NextResponse.json({
      session: authPayload,
      generatedAt: new Date().toISOString(),
      resources,
    });

    if (refreshedTokens) {
      applyAuthCookies(nextResponse, request, refreshedTokens);
    }

    return nextResponse;
  })(request);
}
