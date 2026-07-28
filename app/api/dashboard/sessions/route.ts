import { NextRequest } from "next/server";

import { getApiBaseUrl } from "@/app/api/_lib/controlPlane";
import { withErrorHandling } from "@/app/api/_lib/errors";
import { proxyJson } from "@/app/api/_lib/proxy";


export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  return withErrorHandling(async () => {
    const query = request.nextUrl.search;
    return proxyJson(
      request,
      `${getApiBaseUrl()}/v1/sessions${query}`,
      { fallbackMessage: "Failed to fetch assistant sessions" },
    );
  })(request);
}

export async function DELETE(request: NextRequest) {
  return withErrorHandling(async () => {
    const body = await request.json();
    return proxyJson(request, `${getApiBaseUrl()}/v1/sessions`, {
      method: "DELETE",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
      fallbackMessage: "Failed to delete session",
    });
  })(request);
}
