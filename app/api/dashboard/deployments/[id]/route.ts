import { NextRequest } from "next/server";

import { getApiBaseUrl } from "@/app/api/_lib/controlPlane";
import { proxyJson } from "@/app/api/_lib/proxy";
import { withErrorHandling, badRequest } from "@/app/api/_lib/errors";


export const dynamic = "force-dynamic";

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  return withErrorHandling(async () => {
    const { id } = await params;
    const encodedId = encodeURIComponent(id);
    const { searchParams } = new URL(request.url);
    const path = searchParams.get("path") || "";
    const targetUrl =
      path === "versions"
        ? `${getApiBaseUrl()}/v1/deployments/${encodedId}/versions`
        : path === "logs"
          ? `${getApiBaseUrl()}/v1/deployments/${encodedId}/logs`
          : path === "metrics"
            ? `${getApiBaseUrl()}/v1/deployments/${encodedId}/metrics`
            : `${getApiBaseUrl()}/v1/deployments/${encodedId}`;

    return proxyJson(request, targetUrl, {
      fallbackMessage:
        path === "versions"
          ? "Failed to fetch deployment versions"
          : path === "logs"
            ? "Failed to fetch deployment logs"
            : path === "metrics"
              ? "Failed to fetch deployment metrics"
              : "Failed to fetch deployment",
    });
  })(request);
}

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  return withErrorHandling(async () => {
    const { id } = await params;
    const encodedId = encodeURIComponent(id);
    const { searchParams } = new URL(request.url);
    const action = searchParams.get("action");

    if (!action) {
      return badRequest("Unknown action");
    }

    if (action === "restart") {
      return proxyJson(request, `${getApiBaseUrl()}/v1/deployments/${encodedId}/restart`, {
        method: "POST",
        fallbackMessage: "Failed to restart deployment",
      });
    }

    if (action === "rollback" || action === "scale") {
      const body = await request.json();
      const actionPath = action === "rollback" ? "rollback" : "scale";

      return proxyJson(request, `${getApiBaseUrl()}/v1/deployments/${encodedId}/${actionPath}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
        fallbackMessage:
          action === "rollback"
            ? "Failed to rollback deployment"
            : "Failed to scale deployment",
      });
    }

    return badRequest("Unknown action");
  })(request);
}

export async function DELETE(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  return withErrorHandling(async () => {
    const { id } = await params;
    return proxyJson(request, `${getApiBaseUrl()}/v1/deployments/${encodeURIComponent(id)}`, {
      method: "DELETE",
      fallbackMessage: "Failed to delete deployment",
    });
  })(request);
}
