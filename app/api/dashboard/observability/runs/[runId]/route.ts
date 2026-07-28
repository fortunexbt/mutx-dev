import { NextRequest } from "next/server";

import { getApiBaseUrl } from "@/app/api/_lib/controlPlane";
import { withErrorHandling } from "@/app/api/_lib/errors";
import { proxyJson } from "@/app/api/_lib/proxy";


export const dynamic = "force-dynamic";

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ runId: string }> },
) {
  return withErrorHandling(async () => {
    const { runId } = await params;
    const encodedRunId = encodeURIComponent(runId);

    return proxyJson(
      request,
      `${getApiBaseUrl()}/v1/observability/runs/${encodedRunId}`,
      {
        method: "GET",
        fallbackMessage: "Failed to fetch observability run detail",
      },
    );
  })(request);
}
