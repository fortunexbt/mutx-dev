import { NextRequest } from "next/server";

import { getApiBaseUrl } from "@/app/api/_lib/controlPlane";
import { withErrorHandling } from "@/app/api/_lib/errors";
import { proxyJson } from "@/app/api/_lib/proxy";

export const dynamic = "force-dynamic";

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ sessionKey: string }> },
) {
  return withErrorHandling(async () => {
    const { sessionKey } = await params;
    const body = await request.json();
    return proxyJson(
      request,
      `${getApiBaseUrl()}/v1/sessions/${encodeURIComponent(sessionKey)}/control`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(body),
        fallbackMessage: "Failed to control session",
      },
    );
  })(request);
}
