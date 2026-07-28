import type { DesktopWindowPayload } from "@/components/desktop/types";

export const DESKTOP_ROUTE_PAYLOAD_KEYS: Array<keyof DesktopWindowPayload> = [
  "pane",
  "tab",
  "agentId",
  "deploymentId",
  "runId",
  "sessionId",
];

const DESKTOP_ROUTE_ORIGIN = "https://desktop.mutx.local";

export function buildDesktopRouteHref(
  route: string,
  payload: DesktopWindowPayload = {},
) {
  const url = new URL(route, DESKTOP_ROUTE_ORIGIN);

  for (const key of DESKTOP_ROUTE_PAYLOAD_KEYS) {
    const value = payload[key];
    if (typeof value === "string" && value.trim()) {
      url.searchParams.set(key, value.trim());
    }
  }

  return `${url.pathname}${url.search}${url.hash}`;
}

export function navigateCurrentDesktopRoute(
  push: (href: string) => void,
  route: string,
  payload: DesktopWindowPayload = {},
) {
  const href = buildDesktopRouteHref(route, payload);
  push(href);
  return href;
}
