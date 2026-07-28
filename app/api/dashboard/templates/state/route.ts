import { NextRequest } from "next/server";

import { getApiBaseUrl } from "@/app/api/_lib/controlPlane";
import { withErrorHandling } from "@/app/api/_lib/errors";
import { proxyJson } from "@/app/api/_lib/proxy";
import { readJsonBody } from "@/app/api/dashboard/templates/_lib/jsonBody";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  return withErrorHandling(async () => {
    return proxyJson(request, `${getApiBaseUrl()}/v1/templates/state`, {
      fallbackMessage: "Failed to fetch template catalog state",
    });
  })(request);
}

export async function PUT(request: NextRequest) {
  return withErrorHandling(async () => {
    const body = await readJsonBody(request);
    if (!body.ok) {
      return body.response;
    }
    return proxyJson(request, `${getApiBaseUrl()}/v1/templates/state`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: body.body,
      fallbackMessage: "Failed to update template catalog state",
    });
  })(request);
}
