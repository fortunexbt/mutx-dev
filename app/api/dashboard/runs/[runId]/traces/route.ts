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
    const targetUrl = new URL(
      `${getApiBaseUrl()}/v1/runs/${encodeURIComponent(runId)}/traces`,
    );
    request.nextUrl.searchParams.forEach((value, key) => {
      targetUrl.searchParams.set(key, value);
    });

    return proxyJson(request, targetUrl.toString(), {
      method: "GET",
      fallbackMessage: "Failed to fetch run traces",
    });
  })(request);
}
