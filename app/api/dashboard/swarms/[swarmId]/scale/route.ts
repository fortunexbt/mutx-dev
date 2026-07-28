import { NextRequest } from "next/server";

import { getApiBaseUrl } from "@/app/api/_lib/controlPlane";
import { proxyJson } from "@/app/api/_lib/proxy";
import { withErrorHandling } from "@/app/api/_lib/errors";


export const dynamic = "force-dynamic";

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ swarmId: string }> },
) {
  return withErrorHandling(async () => {
    const { swarmId } = await params;
    const body = await request.json();
    return proxyJson(request, `${getApiBaseUrl()}/v1/swarms/${encodeURIComponent(swarmId)}/scale`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
      fallbackMessage: "Failed to scale swarm",
    });
  })(request);
}
