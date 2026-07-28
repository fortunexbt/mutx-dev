import { NextRequest } from "next/server";

import { getApiBaseUrl } from "@/app/api/_lib/controlPlane";
import { withErrorHandling } from "@/app/api/_lib/errors";
import { proxyJson } from "@/app/api/_lib/proxy";


export const dynamic = "force-dynamic";

export async function GET(
  request: NextRequest,
  context: { params: Promise<{ agentId: string }> },
) {
  return withErrorHandling(async () => {
    const { agentId } = await context.params;
    return proxyJson(
      request,
      `${getApiBaseUrl()}/v1/assistant/${encodeURIComponent(agentId)}/skills`,
      { fallbackMessage: "Failed to fetch assistant skills" },
    );
  })(request);
}
