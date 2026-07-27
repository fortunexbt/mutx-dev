import type { LucideIcon } from "lucide-react";

import {
  DESKTOP_ROUTE_META,
  PRIMARY_DESKTOP_ROUTE_ORDER,
  type DashboardRoutePath,
  type DesktopRouteKey,
  type DesktopRouteSection,
} from "@/components/desktop/desktopRouteConfig";

export interface DashboardNavItem {
  key: DesktopRouteKey;
  title: string;
  description: string;
  href: DashboardRoutePath;
  publicHref: DashboardRoutePath | null;
  icon: LucideIcon;
  group: DesktopRouteSection;
}

export interface DashboardNavGroup {
  key: DashboardNavItem["group"];
  title?: string;
  items: DashboardNavItem[];
}

export const ALL_DASHBOARD_NAV_ITEMS: DashboardNavItem[] = (
  Object.keys(DESKTOP_ROUTE_META) as DesktopRouteKey[]
).map((key) => {
  const meta = DESKTOP_ROUTE_META[key];
  return {
    key,
    title: meta.title,
    description: meta.description,
    href: meta.path,
    publicHref: meta.publicHref,
    icon: meta.icon,
    group: meta.section,
  };
});

export const DASHBOARD_NAV_ITEMS: DashboardNavItem[] = PRIMARY_DESKTOP_ROUTE_ORDER.map((key) =>
  ALL_DASHBOARD_NAV_ITEMS.find((item) => item.key === key)!,
);

export const DASHBOARD_NAV_GROUPS: DashboardNavGroup[] = [
  {
    key: "home",
    items: DASHBOARD_NAV_ITEMS.filter((item) => item.group === "home"),
  },
  {
    key: "core",
    title: "Core Ops",
    items: DASHBOARD_NAV_ITEMS.filter((item) => item.group === "core"),
  },
  {
    key: "execution",
    title: "Execution",
    items: DASHBOARD_NAV_ITEMS.filter((item) => item.group === "execution"),
  },
  {
    key: "admin",
    title: "Admin",
    items: DASHBOARD_NAV_ITEMS.filter((item) => item.group === "admin"),
  },
  {
    key: "support",
    title: "Support",
    items: DASHBOARD_NAV_ITEMS.filter((item) => item.group === "support"),
  },
];

const DASHBOARD_NAV_PANELS: Partial<Record<DashboardNavItem["key"], string>> = {
  home: "overview",
  sessions: "chat",
  apiKeys: "api-keys",
  budgets: "cost-tracker",
  orchestration: "tasks",
  analytics: "tokens",
  history: "activity",
  control: "settings",
  autonomy: "cron",
};

export function getDashboardNavPanel(key: DashboardNavItem["key"]): string {
  return DASHBOARD_NAV_PANELS[key] ?? key;
}

function normalizePathname(pathname: string): string {
  if (pathname !== "/" && pathname.endsWith("/")) {
    return pathname.slice(0, -1);
  }

  return pathname;
}

export function getDashboardNavHref(
  pathname: string,
  item: DashboardNavItem,
): DashboardRoutePath | null {
  const normalizedPath = normalizePathname(pathname);
  const usesInternalDashboardPath =
    normalizedPath === "/dashboard" ||
    normalizedPath.startsWith("/dashboard/") ||
    normalizedPath === "/app" ||
    normalizedPath.startsWith("/app/");

  return usesInternalDashboardPath ? item.href : item.publicHref;
}

export function isDashboardNavItemActive(pathname: string, item: DashboardNavItem): boolean {
  const normalizedPath = normalizePathname(pathname);
  const activeRoots = [item.href, item.publicHref]
    .filter((href): href is DashboardRoutePath => href !== null)
    .map(normalizePathname);

  if (activeRoots.includes("/dashboard") || activeRoots.includes("/")) {
    return normalizedPath === "/" || normalizedPath === "/dashboard" || normalizedPath === "/overview";
  }

  return activeRoots.some((root) => normalizedPath === root || normalizedPath.startsWith(`${root}/`));
}
