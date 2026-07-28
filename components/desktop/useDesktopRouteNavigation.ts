"use client";

import { useCallback } from "react";
import { useRouter } from "next/navigation";

import { navigateCurrentDesktopRoute } from "@/components/desktop/desktopRouteNavigation";
import type { DesktopWindowPayload } from "@/components/desktop/types";

export function useDesktopRouteNavigation() {
  const router = useRouter();

  return useCallback(
    (route: string, payload: DesktopWindowPayload = {}) =>
      navigateCurrentDesktopRoute((href) => router.push(href), route, payload),
    [router],
  );
}
