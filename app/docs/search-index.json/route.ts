import { NextResponse } from "next/server";

import { createDocsSearchIndex } from "@/lib/docs/searchIndex";

export const dynamic = "force-dynamic";

export function GET(): NextResponse {
  if (process.env.NODE_ENV !== "development") {
    return new NextResponse(null, {
      status: 404,
      headers: { "Cache-Control": "no-store" },
    });
  }

  return NextResponse.json(createDocsSearchIndex(), {
    headers: { "Cache-Control": "no-store" },
  });
}
