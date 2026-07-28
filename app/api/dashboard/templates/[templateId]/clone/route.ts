import { NextRequest } from "next/server";

import { getApiBaseUrl } from "@/app/api/_lib/controlPlane";
import { withErrorHandling } from "@/app/api/_lib/errors";
import { proxyJson } from "@/app/api/_lib/proxy";
import { readJsonBody } from "@/app/api/dashboard/templates/_lib/jsonBody";

export const dynamic = "force-dynamic";

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ templateId: string }> },
) {
  return withErrorHandling(async () => {
    const { templateId } = await params;
    const body = await readJsonBody(request);
    if (!body.ok) {
      return body.response;
    }
    return proxyJson(request, `${getApiBaseUrl()}/v1/templates/${encodeURIComponent(templateId)}/clone`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: body.body,
      fallbackMessage: "Failed to clone template",
    });
  })(request);
}
