import { NextRequest } from "next/server";

import { getApiBaseUrl, hasAuthSession } from "@/app/api/_lib/controlPlane";
import { unauthorized, withErrorHandling } from "@/app/api/_lib/errors";
import { proxyJson } from "@/app/api/_lib/proxy";

export const dynamic = "force-dynamic";

const AUDIT_QUERY_PARAMETERS = [
  "agent_id",
  "session_id",
  "run_id",
  "time_range_start",
  "time_range_end",
  "event_type",
  "limit",
  "skip",
] as const;

export async function GET(request: NextRequest) {
  return withErrorHandling(async () => {
    if (!hasAuthSession(request)) {
      return unauthorized();
    }

    const targetUrl = new URL(`${getApiBaseUrl()}/v1/audit/events`);
    AUDIT_QUERY_PARAMETERS.forEach((parameter) => {
      const value = request.nextUrl.searchParams.get(parameter);
      if (value !== null) targetUrl.searchParams.set(parameter, value);
    });

    return proxyJson(request, targetUrl.toString(), {
      method: "GET",
      fallbackMessage: "Failed to fetch audit events",
    });
  })(request);
}
