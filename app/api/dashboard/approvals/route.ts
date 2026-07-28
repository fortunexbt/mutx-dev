import { NextRequest } from "next/server";

import { getApiBaseUrl, hasAuthSession } from "@/app/api/_lib/controlPlane";
import { unauthorized, withErrorHandling } from "@/app/api/_lib/errors";
import { proxyJson } from "@/app/api/_lib/proxy";

export const dynamic = "force-dynamic";

const APPROVAL_QUERY_PARAMETERS = ["status", "agent_id", "skip", "limit"] as const;

export async function GET(request: NextRequest) {
  return withErrorHandling(async () => {
    if (!hasAuthSession(request)) {
      return unauthorized();
    }

    const targetUrl = new URL(`${getApiBaseUrl()}/v1/approvals`);
    APPROVAL_QUERY_PARAMETERS.forEach((parameter) => {
      const value = request.nextUrl.searchParams.get(parameter);
      if (value !== null) targetUrl.searchParams.set(parameter, value);
    });

    return proxyJson(request, targetUrl.toString(), {
      method: "GET",
      fallbackMessage: "Failed to fetch approvals",
    });
  })(request);
}
