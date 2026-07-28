import { NextResponse } from "next/server";

import { fetchLatestStableDesktopRelease } from "@/lib/desktopRelease";

export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  const release = await fetchLatestStableDesktopRelease();
  const response = NextResponse.redirect(
    release?.assets.x64Dmg ?? new URL("/download/macos", request.url),
  );
  response.headers.set("Cache-Control", "private, no-store");
  return response;
}
