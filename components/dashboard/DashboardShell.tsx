"use client";

import type { ReactNode } from "react";
import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { BookOpen, ChevronRight, Menu, Search, Settings2, X } from "lucide-react";

import { DesktopWindowShell } from "@/components/desktop/DesktopWindowShell";
import { useDesktopStatus } from "@/components/desktop/useDesktopStatus";
import {
  panelHref,
  useDashboardPathname,
  useNavigateToPanel,
  usePrefetchPanel,
} from "@/lib/navigation";
import { cn } from "@/lib/utils";

import {
  ALL_DASHBOARD_NAV_ITEMS,
  DASHBOARD_NAV_GROUPS,
  getDashboardNavHref,
  getDashboardNavPanel,
  isDashboardNavItemActive,
  type DashboardNavGroup,
} from "./dashboardNav";
import { DashboardCommandPalette } from "./DashboardCommandPalette";

interface DashboardShellProps {
  children: ReactNode;
  spaShellEnabled?: boolean;
}

interface DashboardNavProps {
  navigateToPanel: (panel: string) => void;
  pathname: string;
  prefetchPanel: (panel: string) => void;
  onNavigate?: () => void;
}

interface DashboardPaletteShortcutRegistry {
  subscribe: (listener: () => void) => () => void;
}

declare global {
  interface Window {
    __mutxDashboardPaletteShortcutRegistry?: DashboardPaletteShortcutRegistry;
  }
}

const GROUP_LABELS: Record<DashboardNavGroup["key"], string> = {
  home: "Workspace",
  core: "Operate",
  execution: "Inspect",
  admin: "Manage",
  support: "Extend",
};

const DASHBOARD_LEDGER_ITEMS = DASHBOARD_NAV_GROUPS.flatMap((group) => group.items);

function createDashboardPaletteShortcutRegistry(): DashboardPaletteShortcutRegistry {
  const listeners = new Set<() => void>();
  let pending = false;

  const handleKeyDown = (event: KeyboardEvent) => {
    if (window.mutxDesktop?.isDesktop) return;

    const isPaletteShortcut =
      (event.metaKey || event.ctrlKey) &&
      (event.key.toLowerCase() === "k" || event.code === "KeyK");
    const dashboardMounted = document.querySelector('[data-dashboard-theme="flight-recorder"]');
    if (!isPaletteShortcut || !dashboardMounted) return;

    event.preventDefault();
    event.stopPropagation();

    if (listeners.size === 0) {
      pending = true;
      return;
    }

    listeners.forEach((listener) => listener());
  };

  window.addEventListener("keydown", handleKeyDown, true);

  return {
    subscribe(listener) {
      listeners.add(listener);
      if (pending) {
        pending = false;
        listener();
      }

      return () => {
        listeners.delete(listener);
      };
    },
  };
}

const dashboardPaletteShortcutRegistry =
  typeof window === "undefined"
    ? null
    : (window.__mutxDashboardPaletteShortcutRegistry ??=
        createDashboardPaletteShortcutRegistry());

function getLedgerRecord(item: (typeof ALL_DASHBOARD_NAV_ITEMS)[number]) {
  const primaryIndex = DASHBOARD_LEDGER_ITEMS.indexOf(item);
  return primaryIndex >= 0 ? primaryIndex + 1 : ALL_DASHBOARD_NAV_ITEMS.indexOf(item) + 1;
}

function DashboardNav({
  navigateToPanel,
  pathname,
  prefetchPanel,
  onNavigate,
}: DashboardNavProps) {
  return (
    <nav className="space-y-6" aria-label="Dashboard navigation">
      {DASHBOARD_NAV_GROUPS.map((group, groupIndex) => (
        <div key={group.key}>
          <p className="mb-2 flex items-center gap-2 border-b border-[#292a25] px-2 pb-2 font-[family:var(--font-mono)] text-[11px] font-semibold uppercase tracking-[0.16em] text-[#8d867a]">
            <span className="text-[#ff6a32]" aria-hidden="true">
              {String(groupIndex + 1).padStart(2, "0")}
            </span>
            <span>{GROUP_LABELS[group.key]}</span>
          </p>
          <div className="space-y-1">
            {group.items.map((item) => {
              const active = isDashboardNavItemActive(pathname, item);
              const panel = getDashboardNavPanel(item.key);
              const recordIndex = getLedgerRecord(item);
              const href = pathname.startsWith("/dashboard")
                ? panelHref(panel)
                : getDashboardNavHref(pathname, item);
              const ItemIcon = item.icon;
              const itemClassName = cn(
                "group relative flex min-h-11 items-center gap-2.5 rounded-[4px] border px-2.5 py-2 text-[12px] transition-[background-color,border-color,color] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#ff7847]",
                active
                  ? "border-[#34342e] bg-[#171813] font-medium text-[#f0ebdf] shadow-[inset_3px_0_0_#ff571c]"
                  : "border-transparent text-[#aaa397] hover:border-[#2b2b26] hover:bg-[#12130f] hover:text-[#eee9dc]",
              );
              const itemContent = (
                <>
                  <span
                    className={cn(
                      "w-5 shrink-0 font-[family:var(--font-mono)] text-[11px] tabular-nums tracking-[0.06em]",
                      active ? "text-[#ff8355]" : "text-[#8d867a] group-hover:text-[#aaa397]",
                    )}
                    aria-hidden="true"
                  >
                    {String(recordIndex).padStart(2, "0")}
                  </span>
                  <ItemIcon
                    className={cn(
                      "h-3.5 w-3.5 shrink-0",
                      active ? "text-[#ff6a32]" : "text-[#737067] group-hover:text-[#b6afa2]",
                    )}
                    aria-hidden="true"
                  />
                  <span className="truncate">{item.title}</span>
                  {active ? (
                    <ChevronRight className="ml-auto h-3.5 w-3.5 text-[#58aaff]" aria-hidden="true" />
                  ) : null}
                </>
              );

              if (!href) {
                return (
                  <span
                    key={item.key}
                    aria-disabled="true"
                    title={`${item.description} Browser route unavailable.`}
                    className={cn(itemClassName, "cursor-not-allowed opacity-55")}
                  >
                    {itemContent}
                  </span>
                );
              }

              return (
                <Link
                  key={item.key}
                  href={href}
                  aria-current={active ? "page" : undefined}
                  title={item.description}
                  onFocus={() => prefetchPanel(panel)}
                  onMouseEnter={() => prefetchPanel(panel)}
                  onClick={(event) => {
                    if (pathname.startsWith("/dashboard")) {
                      event.preventDefault();
                      navigateToPanel(panel);
                    }
                    onNavigate?.();
                  }}
                  className={itemClassName}
                >
                  {itemContent}
                </Link>
              );
            })}
          </div>
        </div>
      ))}
    </nav>
  );
}

function MutxBrand() {
  return (
    <Link
      href="/dashboard"
      className="flex min-h-11 items-center gap-3 rounded-[4px] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-[#ff7847]"
      aria-label="MUTX dashboard home"
    >
      <span className="relative grid h-8 w-8 grid-cols-[5px_1fr] overflow-hidden rounded-[3px] border border-[#48463e] bg-[#11120f]" aria-hidden="true">
        <span className="bg-[#ff571c]" />
        <span className="grid grid-cols-2 gap-[3px] p-[5px]">
          <span className="bg-[#eee9dc]" />
          <span className="bg-[#5d5a52]" />
          <span className="bg-[#5d5a52]" />
          <span className="bg-[#58aaff]" />
        </span>
      </span>
      <span>
        <span className="block font-[family:var(--font-site-body)] text-[16px] font-semibold leading-none tracking-[-0.045em] text-[#eee9dc]">
          MUTX
        </span>
        <span className="mt-1 block font-[family:var(--font-mono)] text-[11px] uppercase leading-none tracking-[0.14em] text-[#827d72]">
          Flight recorder
        </span>
      </span>
    </Link>
  );
}

export function DashboardShell({ children, spaShellEnabled }: DashboardShellProps) {
  const pathname = useDashboardPathname(Boolean(spaShellEnabled));
  const navigateToPanel = useNavigateToPanel();
  const prefetchPanel = usePrefetchPanel();
  const { status, isDesktop, platformReady } = useDesktopStatus();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [timecode, setTimecode] = useState("TC --:--:--Z");
  const drawerRef = useRef<HTMLElement>(null);
  const mobileTriggerRef = useRef<HTMLButtonElement>(null);
  const appContentRef = useRef<HTMLDivElement>(null);

  const activeItem = useMemo(
    () =>
      ALL_DASHBOARD_NAV_ITEMS.find((item) => isDashboardNavItemActive(pathname, item)) ??
      ALL_DASHBOARD_NAV_ITEMS[0],
    [pathname],
  );

  const activeGroup = GROUP_LABELS[activeItem.group];
  const activeRecord = getLedgerRecord(activeItem);
  const controlPlaneReady = status.localControlPlane?.ready || status.openclaw?.health === "healthy";

  useEffect(() => {
    setMobileOpen(false);
  }, [pathname]);

  useEffect(() => {
    const updateTimecode = () => {
      setTimecode(`TC ${new Date().toISOString().slice(11, 19)}Z`);
    };

    updateTimecode();
    const timer = window.setInterval(updateTimecode, 1000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    if (!mobileOpen) return;

    const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const previousOverflow = document.body.style.overflow;
    const appContent = appContentRef.current;
    appContent?.setAttribute("inert", "");
    document.body.style.overflow = "hidden";
    window.requestAnimationFrame(() => drawerRef.current?.querySelector<HTMLElement>("button, a")?.focus());

    const handleDrawerKeys = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        setMobileOpen(false);
        return;
      }

      if (event.key !== "Tab" || !drawerRef.current) return;
      const focusable = Array.from(
        drawerRef.current.querySelectorAll<HTMLElement>(
          'a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])',
        ),
      ).filter((element) => element.getClientRects().length > 0);
      if (!focusable.length) return;

      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };

    window.addEventListener("keydown", handleDrawerKeys);
    return () => {
      window.removeEventListener("keydown", handleDrawerKeys);
      appContent?.removeAttribute("inert");
      document.body.style.overflow = previousOverflow;
      (previousFocus?.isConnected ? previousFocus : mobileTriggerRef.current)?.focus({
        preventScroll: true,
      });
    };
  }, [mobileOpen]);

  useEffect(() => {
    return dashboardPaletteShortcutRegistry?.subscribe(() => setPaletteOpen(true));
  }, []);

  if (platformReady && isDesktop) {
    return <DesktopWindowShell>{children}</DesktopWindowShell>;
  }

  return (
    <div
      className="dashboard-app min-h-screen bg-[#090a08] text-[#eee9dc]"
      data-dashboard-theme="flight-recorder"
    >
      {mobileOpen ? (
        <div className="fixed inset-0 z-50 lg:hidden">
          <button
            type="button"
            className="absolute inset-0 bg-black/80"
            onClick={() => setMobileOpen(false)}
            aria-label="Close dashboard navigation"
            tabIndex={-1}
          />
          <aside
            id="dashboard-mobile-navigation"
            ref={drawerRef}
            role="dialog"
            aria-modal="true"
            aria-label="Dashboard navigation"
            className="relative flex h-full w-[min(88vw,18rem)] flex-col border-r border-[#383730] bg-[#080907] shadow-[24px_0_64px_rgba(0,0,0,0.55)]"
          >
            <div className="flex h-16 items-center justify-between border-b border-[#292a25] px-4">
              <MutxBrand />
              <button
                type="button"
                onClick={() => setMobileOpen(false)}
                className="flex h-11 w-11 items-center justify-center rounded-[4px] border border-[#34342e] bg-[#11120f] text-[#aaa397] transition hover:border-[#59564d] hover:text-[#eee9dc] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#ff7847]"
                aria-label="Close dashboard sidebar"
              >
                <X className="h-4 w-4" aria-hidden="true" />
              </button>
            </div>
            <div className="flex-1 overflow-y-auto px-3 py-5">
              <DashboardNav
                navigateToPanel={navigateToPanel}
                pathname={pathname}
                prefetchPanel={prefetchPanel}
                onNavigate={() => setMobileOpen(false)}
              />
            </div>
          </aside>
        </div>
      ) : null}

      <DashboardCommandPalette
        open={paletteOpen}
        onOpenChange={setPaletteOpen}
        navigateToPanel={navigateToPanel}
        prefetchPanel={prefetchPanel}
      />

      <div
        ref={appContentRef}
        className="min-h-screen lg:grid lg:grid-cols-[16.75rem_minmax(0,1fr)]"
      >
        <aside className="hidden h-screen flex-col border-r border-[#292a25] bg-[#080907] lg:sticky lg:top-0 lg:flex">
          <div className="flex h-16 items-center border-b border-[#292a25] px-5">
            <MutxBrand />
          </div>
          <div className="flex-1 overflow-y-auto px-3 py-5">
            <DashboardNav
              navigateToPanel={navigateToPanel}
              pathname={pathname}
              prefetchPanel={prefetchPanel}
            />
          </div>
          <div className="border-t border-[#292a25] px-5 py-4">
            <div className="mb-3 flex items-center justify-between font-[family:var(--font-mono)] text-[11px] uppercase tracking-[0.14em] text-[#8d867a]">
              <span>Channel / 01</span>
              <span>Secure</span>
            </div>
            <div className="flex items-center gap-2 text-[11px] text-[#b5aea1]">
              <span
                className={cn(
                  "dashboard-live-dot h-1.5 w-1.5 rounded-full",
                  controlPlaneReady ? "bg-[#4bd69b]" : "bg-[#efb654]",
                )}
                aria-hidden="true"
              />
              <span>{controlPlaneReady ? "Control plane connected" : "Browser workspace"}</span>
            </div>
            <p className="mt-2 truncate font-[family:var(--font-mono)] text-[11px] text-[#8d867a]">
              {status.user?.email || "Sign in to load workspace data"}
            </p>
          </div>
        </aside>

        <div className="min-w-0 bg-[#090a08]">
          <header className="sticky top-0 z-30 flex h-16 items-center border-b border-[#2b2b26] bg-[#0d0e0c] px-4 sm:px-6 lg:px-8">
            <button
              ref={mobileTriggerRef}
              type="button"
              onClick={() => setMobileOpen(true)}
              className="mr-3 flex h-11 w-11 items-center justify-center rounded-[4px] border border-[#393830] bg-[#131410] text-[#d6d0c3] transition hover:border-[#5c584f] hover:text-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#ff7847] lg:hidden"
              aria-label="Open dashboard sidebar"
              aria-controls="dashboard-mobile-navigation"
              aria-expanded={mobileOpen}
            >
              <Menu className="h-4 w-4" aria-hidden="true" />
            </button>

            <div className="min-w-0 border-l border-[#36362f] pl-3">
              <p className="flex items-center gap-2 truncate font-[family:var(--font-mono)] text-[11px] font-semibold uppercase tracking-[0.14em] text-[#918b80]">
                <span className="text-[#ff6a32]">REC {String(activeRecord).padStart(2, "0")}</span>
                <span aria-hidden="true">/</span>
                <span>{activeGroup}</span>
              </p>
              <p className="mt-1 truncate text-[14px] font-medium tracking-[-0.015em] text-[#eee9dc]">
                {activeItem.title}
              </p>
            </div>

            <div className="ml-auto flex items-center gap-1.5 sm:gap-2">
              <span className="mr-1 hidden border-r border-[#34342e] pr-4 font-[family:var(--font-mono)] text-[11px] tabular-nums tracking-[0.08em] text-[#8d867a] xl:inline">
                {timecode}
              </span>
              <button
                type="button"
                onClick={() => setPaletteOpen(true)}
                disabled={!platformReady}
                className="hidden min-h-11 min-w-11 items-center gap-2 rounded-[4px] border border-[#35352f] bg-[#11120f] px-3 text-[11px] text-[#aaa397] transition hover:border-[#56534b] hover:text-[#eee9dc] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#ff7847] disabled:cursor-wait disabled:opacity-50 md:inline-flex"
                aria-label="Open command palette"
                aria-keyshortcuts="Meta+K Control+K"
              >
                <Search className="h-3.5 w-3.5" aria-hidden="true" />
                <span>Find a surface</span>
                <kbd className="ml-2 rounded-[3px] border border-[#3b3a33] bg-[#090a08] px-1.5 py-0.5 font-[family:var(--font-mono)] text-[11px] text-[#7f7a70]">
                  &#8984;K
                </kbd>
              </button>
              <Link
                href="/docs"
                className="hidden min-h-11 min-w-11 items-center gap-2 rounded-[4px] border border-transparent px-3 text-[11px] text-[#918b80] transition hover:border-[#34342e] hover:bg-[#11120f] hover:text-[#eee9dc] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#ff7847] sm:inline-flex"
              >
                <BookOpen className="h-3.5 w-3.5" aria-hidden="true" />
                Docs
              </Link>
              <Link
                href="/dashboard/control"
                aria-label="Open settings"
                className="inline-flex min-h-11 min-w-11 items-center justify-center gap-2 rounded-[4px] border border-[#ff6a32] bg-[#ff571c] px-3.5 text-[11px] font-semibold text-[#090a08] transition hover:border-[#ff8b61] hover:bg-[#ff7545] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#ff9a72]"
              >
                <Settings2 className="h-3.5 w-3.5" aria-hidden="true" />
                <span className="hidden sm:inline">Settings</span>
              </Link>
            </div>
          </header>

          <main id="main-content" className="dashboard-content mx-auto w-full max-w-[100rem] px-4 py-6 sm:px-6 sm:py-8 lg:px-8 lg:py-9 xl:px-10">
            {children}
          </main>
        </div>
      </div>
    </div>
  );
}
