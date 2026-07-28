import { NextRequest } from "next/server";

import { getApiBaseUrl } from "@/app/api/_lib/controlPlane";
import { proxyJson } from "@/app/api/_lib/proxy";
import { withErrorHandling } from "@/app/api/_lib/errors";


export const dynamic = "force-dynamic";

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ swarmId: string }> },
) {
  return withErrorHandling(async () => {
    const { swarmId } = await params;
    return proxyJson(request, `${getApiBaseUrl()}/v1/swarms/${encodeURIComponent(swarmId)}`, {
      method: "GET",
      fallbackMessage: "Failed to fetch swarm",
    });
  })(request);
}

export async function PATCH(
  request: NextRequest,
  { params }: { params: Promise<{ swarmId: string }> },
) {
  return withErrorHandling(async () => {
    const { swarmId } = await params;
    const body = await request.json();
    return proxyJson(request, `${getApiBaseUrl()}/v1/swarms/${encodeURIComponent(swarmId)}`, {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
      fallbackMessage: "Failed to update swarm",
    });
  })(request);
}

export async function DELETE(
  request: NextRequest,
  { params }: { params: Promise<{ swarmId: string }> },
) {
  return withErrorHandling(async () => {
    const { swarmId } = await params;
    return proxyJson(request, `${getApiBaseUrl()}/v1/swarms/${encodeURIComponent(swarmId)}`, {
      method: "DELETE",
      fallbackMessage: "Failed to delete swarm",
    });
  })(request);
}
