import { NextRequest } from "next/server";

import { getApiBaseUrl } from "@/app/api/_lib/controlPlane";
import { proxyJson } from "@/app/api/_lib/proxy";
import { withErrorHandling } from "@/app/api/_lib/errors";


export const dynamic = "force-dynamic";

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ runId: string }> },
) {
  return withErrorHandling(async () => {
    const { runId } = await params;
    return proxyJson(request, `${getApiBaseUrl()}/v1/runs/${encodeURIComponent(runId)}`, {
      method: "GET",
      fallbackMessage: "Failed to fetch run",
    });
  })(request);
}
