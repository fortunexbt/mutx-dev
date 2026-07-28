import { NextRequest } from "next/server";

import { getApiBaseUrl, hasAuthSession } from "@/app/api/_lib/controlPlane";
import { badRequest, unauthorized, withErrorHandling } from "@/app/api/_lib/errors";
import { proxyJson } from "@/app/api/_lib/proxy";

export const dynamic = "force-dynamic";

const MAX_CONTEXT_ID_LENGTH = 255;

export async function GET(request: NextRequest) {
  return withErrorHandling(async () => {
    if (!hasAuthSession(request)) {
      return unauthorized();
    }

    const runId = request.nextUrl.searchParams.get("run_id")?.trim() || null;
    const sessionId = request.nextUrl.searchParams.get("session_id")?.trim() || null;

    if (Boolean(runId) === Boolean(sessionId)) {
      return badRequest("Provide exactly one of run_id or session_id");
    }

    const contextId = runId ?? sessionId;
    if (!contextId || contextId.length > MAX_CONTEXT_ID_LENGTH) {
      return badRequest("Audit export context is invalid");
    }

    const targetUrl = new URL(`${getApiBaseUrl()}/v1/audit/export`);
    targetUrl.searchParams.set(runId ? "run_id" : "session_id", contextId);

    return proxyJson(request, targetUrl.toString(), {
      method: "GET",
      fallbackMessage: "Failed to export audit evidence",
    });
  })(request);
}
