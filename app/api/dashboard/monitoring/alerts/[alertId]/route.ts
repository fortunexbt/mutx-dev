import { NextRequest } from "next/server";

import { getApiBaseUrl } from "@/app/api/_lib/controlPlane";
import { withErrorHandling } from "@/app/api/_lib/errors";
import { proxyJson } from "@/app/api/_lib/proxy";

export const dynamic = "force-dynamic";

export async function PATCH(
  request: NextRequest,
  { params }: { params: Promise<{ alertId: string }> },
) {
  return withErrorHandling(async () => {
    const { alertId } = await params;
    const body = await request.json();
    return proxyJson(
      request,
      `${getApiBaseUrl()}/v1/monitoring/alerts/${encodeURIComponent(alertId)}`,
      {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(body),
        fallbackMessage: "Failed to update alert",
      },
    );
  })(request);
}
