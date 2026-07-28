import { NextRequest } from "next/server";

import { getApiBaseUrl } from "@/app/api/_lib/controlPlane";
import { withErrorHandling } from "@/app/api/_lib/errors";
import { proxyJson } from "@/app/api/_lib/proxy";

export const dynamic = "force-dynamic";

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ sessionKey: string }> },
) {
  return withErrorHandling(async () => {
    const { sessionKey } = await params;
    return proxyJson(
      request,
      `${getApiBaseUrl()}/v1/sessions/${encodeURIComponent(sessionKey)}/transcript`,
      {
        method: "GET",
        fallbackMessage: "Failed to fetch session transcript",
      },
    );
  })(request);
}
