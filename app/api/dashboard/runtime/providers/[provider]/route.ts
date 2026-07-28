import { NextRequest } from "next/server";

import { getApiBaseUrl } from "@/app/api/_lib/controlPlane";
import { withErrorHandling } from "@/app/api/_lib/errors";
import { proxyJson } from "@/app/api/_lib/proxy";


export const dynamic = "force-dynamic";

interface Params {
  params: Promise<{ provider: string }>;
}

export async function GET(request: NextRequest, context: Params) {
  return withErrorHandling(async () => {
    const { provider } = await context.params;
    return proxyJson(
      request,
      `${getApiBaseUrl()}/v1/runtime/providers/${encodeURIComponent(provider)}`,
      { fallbackMessage: "Failed to fetch provider runtime" },
    );
  })(request);
}
