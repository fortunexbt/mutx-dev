import { NextResponse } from "next/server";

import {
  MUTX_RELEASE_NOTES_URL,
  buildReleaseNotesUrl,
  fetchLatestStableDesktopRelease,
} from "@/lib/desktopRelease";

export const dynamic = "force-dynamic";

export async function GET() {
  const release = await fetchLatestStableDesktopRelease();
  const response = NextResponse.redirect(
    release ? buildReleaseNotesUrl(release.version) : MUTX_RELEASE_NOTES_URL,
  );
  response.headers.set("Cache-Control", "private, no-store");
  return response;
}
