"use client";

import { useEffect } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

import { DESKTOP_ROUTE_PAYLOAD_KEYS } from "@/components/desktop/desktopRouteNavigation";
import { useDesktopWindow } from "@/components/desktop/useDesktopWindow";
import type { DesktopWindowPayload } from "@/components/desktop/types";
import {
  DASHBOARD_ROUTE_PATHS,
  getDesktopWindowRoleForPath,
  getDesktopWorkspacePaneForPath,
} from "@/components/desktop/desktopRouteConfig";

export function DesktopRouteListener() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const { updateCurrentWindow } = useDesktopWindow();

  useEffect(() => {
    if (typeof window === "undefined" || !window.mutxDesktop?.isDesktop) {
      return;
    }

    const unsubscribe = window.mutxDesktop.onNavigate((route) => {
      if (typeof route === "string" && route.startsWith("/")) {
        router.push(route);
      }
    });

    return () => {
      unsubscribe?.();
    };
  }, [router]);

  useEffect(() => {
    if (typeof window === "undefined" || !window.mutxDesktop?.isDesktop || !pathname) {
      return;
    }

    const payload: DesktopWindowPayload = {};
    for (const key of DESKTOP_ROUTE_PAYLOAD_KEYS) {
      const value = searchParams?.get(key);
      if (value) {
        payload[key] = value;
      }
    }

    const destinationRole = getDesktopWindowRoleForPath(pathname);
    if (destinationRole === "workspace" && !payload.pane) {
      payload.pane = getDesktopWorkspacePaneForPath(pathname);
    }

    if (destinationRole === "traces" && !payload.tab) {
      payload.tab = pathname === DASHBOARD_ROUTE_PATHS.logs ? "logs" : "timeline";
    }

    void updateCurrentWindow({
      route: pathname,
      payload,
    });
  }, [pathname, searchParams, updateCurrentWindow]);

  return null;
}
