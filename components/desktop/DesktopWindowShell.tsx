"use client";

import type { CSSProperties, KeyboardEvent as ReactKeyboardEvent, ReactNode } from "react";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  Activity,
  Brain,
  FolderOpen,
  LayoutPanelLeft,
  Radar,
  Search,
  Settings2,
  ShieldCheck,
  TerminalSquare,
} from "lucide-react";

import {
  DASHBOARD_ROUTE_PATHS,
  DESKTOP_ROUTE_META,
  DESKTOP_ROUTE_ORDER,
  getDesktopRouteKeyForPath,
  getDesktopWindowRoleForRoute,
  getDesktopWorkspacePaneForRoute,
  isDesktopRoutePathActive,
  type DesktopRouteSection,
} from "@/components/desktop/desktopRouteConfig";
import { getNextDesktopTabIndex } from "@/components/desktop/desktopTabNavigation";
import { useDesktopRouteNavigation } from "@/components/desktop/useDesktopRouteNavigation";
import { useDesktopStatus } from "@/components/desktop/useDesktopStatus";
import { useDesktopDialog } from "@/components/desktop/useDesktopDialog";
import { useDesktopWindow } from "@/components/desktop/useDesktopWindow";
import type { DesktopWindowPayload } from "@/components/desktop/types";
import {
  DESKTOP_ACTION_CLASS,
  DESKTOP_FOCUS_CLASS,
  DESKTOP_SOURCE_TONE_CLASS,
  getDesktopStateTone,
} from "@/components/desktop/desktopVisualContract";
import { cn } from "@/lib/utils";

type WorkspacePane = string;

type SettingsPane = "account" | "runtime" | "gateway" | "governance" | "advanced";
type AppRegionStyle = CSSProperties & {
  WebkitAppRegion?: "drag" | "no-drag";
};

const WORKSPACE_SECTIONS: Array<{ key: DesktopRouteSection; title: string }> = [
  { key: "home", title: "Workspace" },
  { key: "core", title: "Core Ops" },
  { key: "execution", title: "Execution" },
  { key: "admin", title: "Admin" },
  { key: "support", title: "Support" },
];

const WORKSPACE_GROUPS = WORKSPACE_SECTIONS.map((section) => ({
  title: section.title,
  items: DESKTOP_ROUTE_ORDER.filter((key) => {
    const meta = DESKTOP_ROUTE_META[key];
    return meta.section === section.key && getDesktopWindowRoleForRoute(key) === "workspace";
  }).map((key) => {
    const meta = DESKTOP_ROUTE_META[key];
    return {
      key,
      pane: getDesktopWorkspacePaneForRoute(key),
      label: meta.title,
      description: meta.description,
      href: meta.path,
      icon: meta.icon,
    };
  }),
})).filter((group) => group.items.length > 0);

const SETTINGS_PANES: Array<{
  pane: SettingsPane;
  label: string;
  description: string;
  icon: typeof Activity;
}> = [
  { pane: "account", label: "Account", description: "Operator identity and workspace binding.", icon: ShieldCheck },
  { pane: "runtime", label: "Runtime", description: "Local stack, workspace, and execution surfaces.", icon: LayoutPanelLeft },
  { pane: "gateway", label: "Gateway", description: "OpenClaw and gateway posture.", icon: Radar },
  { pane: "governance", label: "Governance", description: "Faramesh status and approvals.", icon: Brain },
  { pane: "advanced", label: "Advanced", description: "Bridge, diagnostics, and desktop internals.", icon: Settings2 },
];

function isEditableTarget(target: EventTarget | null) {
  if (!(target instanceof HTMLElement)) {
    return false;
  }

  const tagName = target.tagName.toLowerCase();
  return (
    target.isContentEditable ||
    tagName === "input" ||
    tagName === "textarea" ||
    tagName === "select"
  );
}

function WindowSwitcher({
  activeRole,
  onSelect,
  style,
}: {
  activeRole: "workspace" | "sessions" | "traces" | "settings";
  onSelect: (role: "workspace" | "sessions" | "traces" | "settings") => void;
  style?: AppRegionStyle;
}) {
  const items = [
    { role: "workspace", label: "Workspace" },
    { role: "sessions", label: "Sessions" },
    { role: "traces", label: "Traces" },
    { role: "settings", label: "Settings" },
  ] as const;

  return (
    <div
      role="group"
      aria-label="Desktop windows"
      className="inline-flex items-center gap-px rounded-[4px] border border-[#34342e] bg-[#090a08] p-1"
      style={style}
    >
      {items.map((item) => (
        <button
          key={item.role}
          type="button"
          onClick={() => onSelect(item.role)}
          aria-pressed={item.role === activeRole}
          className={cn(
            `min-h-9 rounded-[4px] border px-3 py-1.5 font-[family:var(--font-mono)] text-[10px] font-semibold uppercase tracking-[0.12em] transition-colors ${DESKTOP_FOCUS_CLASS}`,
            item.role === activeRole
              ? "border-[#663619] bg-[#21150f] text-[#ff8355] shadow-[inset_0_-2px_0_#ff571c]"
              : "border-transparent text-[#999284] hover:border-[#34342e] hover:bg-[#151612] hover:text-[#eee9dc]",
          )}
        >
          {item.label}
        </button>
      ))}
    </div>
  );
}

function CommandPalette({
  open,
  query,
  onQueryChange,
  onClose,
  actions,
}: {
  open: boolean;
  query: string;
  onQueryChange: (value: string) => void;
  onClose: () => void;
  actions: Array<{ id: string; label: string; detail: string; onSelect: () => void }>;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const dialogRef = useDesktopDialog(open, onClose, inputRef);

  if (!open) {
    return null;
  }

  return (
    <div className="fixed inset-0 z-[120] flex items-start justify-center bg-[#090a08]/90 px-4 py-16 motion-reduce:backdrop-blur-none sm:py-20">
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="desktop-command-palette-title"
        tabIndex={-1}
        className="w-full max-w-[760px] overflow-hidden rounded-[8px] border border-[#48463e] bg-[#11120f] shadow-[0_24px_64px_rgba(0,0,0,0.48)]"
      >
        <h2 id="desktop-command-palette-title" className="sr-only">
          Desktop command palette
        </h2>
        <div className="flex items-center gap-3 border-b border-[#34342e] bg-[#0c0d0b] px-4 py-3 sm:px-5 sm:py-4">
          <Search className="h-4 w-4 text-[#ff7545]" aria-hidden="true" />
          <input
            ref={inputRef}
            aria-label="Search desktop commands"
            value={query}
            onChange={(event) => onQueryChange(event.target.value)}
            placeholder="Search windows, panes, and desktop actions"
            className="w-full bg-transparent text-sm text-[#eee9dc] outline-none placeholder:text-[#777268]"
          />
          <button
            type="button"
            onClick={onClose}
            aria-label="Close command palette"
            className={cn("rounded-[4px] border border-[#3b3a33] bg-[#151612] px-2.5 py-1.5 font-[family:var(--font-mono)] text-[10px] uppercase tracking-[0.12em] text-[#aaa397]", DESKTOP_FOCUS_CLASS)}
          >
            Esc
          </button>
        </div>
        <div className="max-h-[min(420px,60vh)] overflow-y-auto p-2 sm:p-3">
          {actions.length === 0 ? (
            <div className="rounded-[6px] border border-dashed border-[#34342e] bg-[#0c0d0b] px-4 py-10 text-center text-sm text-[#8d867a]">
              No matching desktop actions.
            </div>
          ) : (
            <div className="space-y-2">
              {actions.map((action) => (
                <button
                  key={action.id}
                  type="button"
                  onClick={() => {
                    action.onSelect();
                    onClose();
                  }}
                  className={cn("w-full rounded-[4px] border border-[#2b2b26] bg-[#0c0d0b] px-4 py-3 text-left transition-colors hover:border-[#663619] hover:bg-[#15120f]", DESKTOP_FOCUS_CLASS)}
                >
                  <p className="text-sm font-medium text-[#eee9dc]">{action.label}</p>
                  <p className="mt-1 text-[12px] leading-5 text-[#999284]">{action.detail}</p>
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export function DesktopWindowShell({ children }: { children: ReactNode }) {
  const { status } = useDesktopStatus();
  const { currentWindow, openWindow, openPreferences } = useDesktopWindow();
  const navigateCurrentRoute = useDesktopRouteNavigation();
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [paletteQuery, setPaletteQuery] = useState("");
  const isMac = typeof navigator !== "undefined" && navigator.platform.toLowerCase().includes("mac");
  const dragRegionStyle: AppRegionStyle = {
    WebkitAppRegion: "drag",
    paddingLeft: isMac ? 82 : 18,
  };
  const noDragRegionStyle: AppRegionStyle = { WebkitAppRegion: "no-drag" };

  const role = currentWindow.currentRole;
  const currentRoute = currentWindow.currentWindow.route;
  const workspacePane = (currentWindow.currentWindow.payload.pane || "overview") as WorkspacePane;
  const settingsPane = (currentWindow.currentWindow.payload.pane || "account") as SettingsPane;
  const tracesTab = currentWindow.currentWindow.payload.tab || "timeline";

  const workspaceItems = useMemo(() => WORKSPACE_GROUPS, []);
  const primaryWorkspaceGroups = useMemo(
    () =>
      WORKSPACE_GROUPS.map((group) => ({
        ...group,
        items: group.items.filter(
          (item) => DESKTOP_ROUTE_META[item.key].showInPrimaryNav !== false,
        ),
      })).filter((group) => group.items.length > 0),
    [],
  );
  const activeWorkspaceRouteKey = getDesktopRouteKeyForPath(currentRoute);
  const visibleWorkspaceItem =
    workspaceItems
      .flatMap((group) => group.items)
      .find((item) => item.key === activeWorkspaceRouteKey) || workspaceItems[0].items[0];

  const shellTitle =
    role === "workspace"
      ? visibleWorkspaceItem.label
      : role === "sessions"
        ? "Sessions"
        : role === "traces"
          ? tracesTab === "logs"
            ? "Trace Logs"
            : "Trace Explorer"
          : "Settings";

  const shellSubtitle =
    role === "workspace"
      ? visibleWorkspaceItem.description
      : role === "sessions"
        ? "Dedicated conversation and session workspace."
        : role === "traces"
          ? "Dedicated debugging workspace for runs, traces, and logs."
        : "Preferences and local desktop controls.";

  const lifecycleChips = useMemo(
    () => [
      {
        label: `UI ${status.uiServer?.state || "unknown"}`,
        tone: DESKTOP_SOURCE_TONE_CLASS[getDesktopStateTone(status.uiServer?.state)],
      },
      {
        label: `Bridge ${status.bridge?.state || "unknown"}`,
        tone: DESKTOP_SOURCE_TONE_CLASS[getDesktopStateTone(status.bridge?.state)],
      },
      {
        label: `Runtime ${status.runtime?.state || "unknown"}`,
        tone: DESKTOP_SOURCE_TONE_CLASS[getDesktopStateTone(status.runtime?.state)],
      },
    ],
    [status],
  );

  const shellDiagnostic = useMemo(() => {
    if (status.uiServer?.state && status.uiServer.state !== "ready") {
      return {
        title: "Desktop UI bootstrap is degraded",
        message:
          status.uiServer.lastError ||
          "The packaged dashboard surface is still starting or needs operator recovery.",
        tone: "danger",
      };
    }

    if (status.bridge?.state && status.bridge.state !== "ready" && status.bridge.state !== "idle") {
      return {
        title: "Desktop bridge is not fully ready",
        message:
          status.bridge.lastError ||
          "Desktop-native actions stay gated until the Python bridge completes its readiness probe.",
        tone: "warning",
      };
    }

    if (status.runtime?.state && status.runtime.state !== "ready") {
      return {
        title: "Runtime posture is degraded",
        message:
          status.runtime.lastError ||
          "The machine window state is restored, but the live runtime contract is not yet healthy.",
        tone: "warning",
      };
    }

    return null;
  }, [status]);

  const handleTraceTabKeyDown = (event: ReactKeyboardEvent<HTMLDivElement>) => {
    if (
      !["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key) ||
      !(event.target instanceof HTMLButtonElement) ||
      event.target.getAttribute("role") !== "tab"
    ) {
      return;
    }

    const tabs = Array.from(
      event.currentTarget.querySelectorAll<HTMLButtonElement>('[role="tab"]'),
    );
    const currentIndex = tabs.indexOf(event.target);
    if (currentIndex < 0 || tabs.length === 0) {
      return;
    }

    event.preventDefault();
    const isRtl = window.getComputedStyle(event.currentTarget).direction === "rtl";
    const nextIndex = getNextDesktopTabIndex(
      event.key,
      currentIndex,
      tabs.length,
      isRtl,
    );
    tabs[nextIndex]?.focus();
    tabs[nextIndex]?.click();
  };

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (isEditableTarget(event.target)) {
        return;
      }

      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setPaletteOpen((current) => !current);
      }

      if ((event.metaKey || event.ctrlKey) || event.altKey) {
        return;
      }

      if (event.key === "Escape") {
        setPaletteOpen(false);
        setPaletteQuery("");
        return;
      }

      if (paletteOpen) {
        return;
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [paletteOpen]);

  const paletteActions = useMemo(() => {
    const baseActions = [
      {
        id: "open-workspace",
        label: "Open Workspace Window",
        detail: "Focus the main control window.",
        onSelect: () => void openWindow("workspace", { pane: workspacePane }),
      },
      {
        id: "open-sessions",
        label: "Open Sessions Window",
        detail: "Focus or create the dedicated sessions window.",
        onSelect: () => void openWindow("sessions"),
      },
      {
        id: "open-traces",
        label: "Open Traces Window",
        detail: "Focus or create the dedicated traces window.",
        onSelect: () => void openWindow("traces", { tab: "timeline" }),
      },
      {
        id: "open-settings",
        label: "Open Settings",
        detail: "Open the preferences window.",
        onSelect: () => void openPreferences("account"),
      },
      {
        id: "open-tui",
        label: "Open TUI",
        detail: "Launch the terminal-native runtime surface.",
        onSelect: () => {
          void window.mutxDesktop?.bridge.runtime.openSurface("tui");
        },
      },
    ];

    const workspaceActions = primaryWorkspaceGroups.flatMap((group) =>
      group.items.map((item) => ({
        id: `workspace-${item.pane}`,
        label: `Go to ${item.label}`,
        detail: item.description,
        onSelect: () => void navigateCurrentRoute(item.href, { pane: item.pane }),
      })),
    );

    const settingsActions = SETTINGS_PANES.map((pane) => ({
      id: `settings-${pane.pane}`,
      label: `Open ${pane.label} Preferences`,
      detail: pane.description,
      onSelect: () => {
        void openPreferences(pane.pane);
      },
    }));
    return [...baseActions, ...workspaceActions, ...settingsActions].filter((action) => {
      const haystack = `${action.label} ${action.detail}`.toLowerCase();
      return haystack.includes(paletteQuery.trim().toLowerCase());
    });
  }, [navigateCurrentRoute, openPreferences, openWindow, paletteQuery, primaryWorkspaceGroups, workspacePane]);

  async function handleOpenWindow(
    nextRole: "workspace" | "sessions" | "traces" | "settings",
    payload: DesktopWindowPayload = {},
  ) {
    if (nextRole === "workspace") {
      await openWindow("workspace", { pane: workspacePane, ...payload });
      return;
    }

    if (nextRole === "settings") {
      await openPreferences((payload.pane as string) || "account");
      return;
    }

    await openWindow(nextRole, payload);
  }

  function selectWorkspacePane(item: (typeof WORKSPACE_GROUPS)[number]["items"][number]) {
    navigateCurrentRoute(item.href, {
      ...currentWindow.currentWindow.payload,
      pane: item.pane,
    });
  }

  function selectSettingsPane(pane: SettingsPane) {
    navigateCurrentRoute(DASHBOARD_ROUTE_PATHS.control, {
      ...currentWindow.currentWindow.payload,
      pane,
    });
  }

  function selectTracesTab(tab: string) {
    const nextRoute = tab === "logs" ? DASHBOARD_ROUTE_PATHS.logs : DASHBOARD_ROUTE_PATHS.traces;
    navigateCurrentRoute(nextRoute, {
      ...currentWindow.currentWindow.payload,
      tab,
    });
  }

  return (
    <div
      data-mutx-desktop="operator-shell"
      className="min-h-screen bg-[#090a08] font-[family:var(--font-site-body)] text-[#eee9dc]"
    >
      <CommandPalette
        open={paletteOpen}
        query={paletteQuery}
        onQueryChange={setPaletteQuery}
        onClose={() => {
          setPaletteOpen(false);
          setPaletteQuery("");
        }}
        actions={paletteActions}
      />

      <a
        href="#main-content"
        className={cn("sr-only z-[140] rounded-[4px] bg-[#ff571c] px-3 py-2 text-xs font-semibold text-[#090a08] focus:not-sr-only focus:fixed focus:left-3 focus:top-3", DESKTOP_FOCUS_CLASS)}
      >
        Skip to desktop workspace
      </a>

      <div className="min-h-screen w-full">
        <div className="min-h-screen overflow-hidden bg-[#090a08]">
          <div
            data-desktop-region="native-titlebar"
            className="grid min-h-[54px] grid-cols-[minmax(84px,1fr)_auto_minmax(240px,1fr)] items-center gap-3 border-b border-[#34342e] bg-[#0d0e0c] px-3 py-1.5"
            style={dragRegionStyle}
          >
            <div />
            <div className="justify-self-center">
              <WindowSwitcher
                activeRole={role}
                onSelect={(nextRole) => {
                  void handleOpenWindow(nextRole);
                }}
                style={noDragRegionStyle}
              />
            </div>

            <div className="flex items-center justify-self-end gap-1.5" style={noDragRegionStyle}>
              <button
                type="button"
                onClick={() => setPaletteOpen(true)}
                aria-label="Open desktop command palette"
                className={cn(DESKTOP_ACTION_CLASS, "inline-flex min-w-[164px] items-center justify-between gap-3 border-[#35352f] bg-[#11120f] px-3 text-[#aaa397] hover:border-[#56534b] hover:text-[#eee9dc]")}
              >
                <span className="inline-flex items-center gap-2">
                  <Search className="h-4 w-4 text-[#ff7545]" aria-hidden="true" />
                  <span className="hidden xl:inline">Search panes and actions</span>
                  <span className="xl:hidden">Search</span>
                </span>
                <span className="rounded-[4px] border border-[#3b3a33] bg-[#090a08] px-1.5 py-0.5 font-[family:var(--font-mono)] text-[9px] uppercase tracking-[0.12em] text-[#7f7a70]">
                  {isMac ? "⌘K" : "Ctrl+K"}
                </span>
              </button>
              <button
                type="button"
                onClick={() => void window.mutxDesktop?.bridge.runtime.openSurface("tui")}
                disabled={!status.bridge?.ready}
                className={cn(DESKTOP_ACTION_CLASS, "inline-flex items-center gap-2 border-[#35352f] bg-[#11120f] px-3 text-[#aaa397] hover:border-[#56534b] hover:text-[#eee9dc]")}
              >
                <TerminalSquare className="h-4 w-4" aria-hidden="true" />
                TUI
              </button>
              <button
                type="button"
                onClick={() => void openPreferences("account")}
                className={cn(DESKTOP_ACTION_CLASS, "inline-flex items-center gap-2 border-[#35352f] bg-[#11120f] px-3 text-[#aaa397] hover:border-[#56534b] hover:text-[#eee9dc]")}
              >
                <Settings2 className="h-4 w-4" aria-hidden="true" />
                Settings
              </button>
            </div>
          </div>

          <div className="border-b border-[#2b2b26] bg-[#0c0d0b] px-4 py-3">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="border-l-2 border-[#ff571c] pl-2 font-[family:var(--font-mono)] text-[9px] font-semibold uppercase tracking-[0.16em] text-[#ff8355]">
                    {role === "workspace"
                      ? "workspace"
                      : role === "sessions"
                        ? "sessions"
                        : role === "traces"
                          ? "traces"
                          : "settings"}
                  </span>
                  <p className="font-[family:var(--font-site-display)] text-[1.02rem] font-medium tracking-[-0.035em] text-[#eee9dc]">
                    {shellTitle}
                  </p>
                </div>
                <p className="mt-1 text-[12px] leading-5 text-[#999284]">{shellSubtitle}</p>
              </div>

              <div className="flex flex-wrap items-center gap-2">
                <span className="max-w-[220px] truncate rounded-[4px] border border-[#34342e] bg-[#151612] px-2.5 py-1.5 font-[family:var(--font-mono)] text-[9px] uppercase tracking-[0.1em] text-[#c8c0b0]">
                  {status.user?.email || "desktop session"}
                </span>
                <span className="rounded-[4px] border border-[#663619] bg-[#21150f] px-2.5 py-1.5 font-[family:var(--font-mono)] text-[9px] font-semibold uppercase tracking-[0.1em] text-[#ff8355]">
                  {status.mode === "local" ? "local runtime" : status.mode || "runtime unknown"}
                </span>
                {lifecycleChips.map((chip) => (
                  <span
                    key={chip.label}
                    className={`rounded-full border px-2.5 py-1.5 font-[family:var(--font-mono)] text-[9px] font-semibold uppercase tracking-[0.1em] ${chip.tone}`}
                  >
                    {chip.label}
                  </span>
                ))}
              </div>
            </div>
          </div>

          {shellDiagnostic ? (
            <div
              className={cn(
                "border-b px-5 py-3 text-sm",
                shellDiagnostic.tone === "danger"
                  ? DESKTOP_SOURCE_TONE_CLASS.danger
                  : DESKTOP_SOURCE_TONE_CLASS.warning,
              )}
            >
              <p className="font-medium">{shellDiagnostic.title}</p>
              <p className="mt-1 text-xs opacity-90">{shellDiagnostic.message}</p>
            </div>
          ) : null}

          <div className="flex min-h-[calc(100vh-7.25rem)] bg-[#090a08]">
            {role === "workspace" ? (
              <aside aria-label="Workspace routes" className="w-[clamp(210px,13vw,272px)] shrink-0 overflow-y-auto border-r border-[#292a25] bg-[#080907] px-2.5 py-4">
                <div className="flex h-full flex-col gap-4">
                  <div className="space-y-4">
                    {primaryWorkspaceGroups.map((group) => (
                      <div key={group.title} className="space-y-1.5">
                        <p className="border-b border-[#292a25] px-2 pb-2 font-[family:var(--font-mono)] text-[9px] font-semibold uppercase tracking-[0.16em] text-[#8d867a]">
                          {group.title}
                        </p>
                        {group.items.map((item) => {
                          const active = isDesktopRoutePathActive(currentRoute, item.key);
                          return (
                            <button
                              key={item.pane}
                              type="button"
                              onClick={() => void selectWorkspacePane(item)}
                              className={cn(
                                `w-full min-h-11 rounded-[4px] border px-2.5 py-2 text-left transition-colors ${DESKTOP_FOCUS_CLASS}`,
                                active
                                  ? "border-[#34342e] bg-[#171813] text-[#f0ebdf] shadow-[inset_3px_0_0_#ff571c]"
                                  : "border-transparent text-[#aaa397] hover:border-[#2b2b26] hover:bg-[#12130f] hover:text-[#eee9dc]",
                              )}
                            >
                              <div className="flex items-start gap-3">
                                <span
                                  className={cn(
                                    "flex h-7 w-7 shrink-0 items-center justify-center rounded-[4px] border",
                                    active ? "border-[#663619] bg-[#21150f] text-[#ff8355]" : "border-[#34342e] bg-[#11120f] text-[#777268]",
                                  )}
                                >
                                  <item.icon className="h-4 w-4" />
                                </span>
                                <div className="min-w-0">
                                  <p className="text-[12px] font-medium">{item.label}</p>
                                  <p className="mt-1 hidden text-[11px] leading-4 text-[#8d867a] 2xl:block">{item.description}</p>
                                </div>
                              </div>
                            </button>
                          );
                        })}
                      </div>
                    ))}
                  </div>
                  <div className="mt-auto rounded-[6px] border border-[#2b2b26] bg-[#0c0d0b] p-3">
                    <p className="font-[family:var(--font-mono)] text-[9px] font-semibold uppercase tracking-[0.16em] text-[#8d867a]">
                      Keyboard
                    </p>
                      <div className="mt-2 space-y-2 text-[11px] text-[#aaa397]">
                        <div className="flex items-center justify-between gap-3">
                          <span>Command palette</span>
                        <span className="rounded-[4px] border border-[#3b3a33] bg-[#090a08] px-2 py-0.5 font-[family:var(--font-mono)] text-[9px] uppercase tracking-[0.14em] text-[#7f7a70]">
                            {isMac ? "⌘K" : "Ctrl+K"}
                          </span>
                        </div>
                      </div>
                  </div>
                </div>
              </aside>
            ) : role === "settings" ? (
              <aside aria-label="Settings panes" className="w-[clamp(210px,13vw,264px)] shrink-0 overflow-y-auto border-r border-[#292a25] bg-[#080907] px-2.5 py-4">
                <div className="space-y-1.5">
                  {SETTINGS_PANES.map((item) => {
                    const active = item.pane === settingsPane;
                    return (
                      <button
                        key={item.pane}
                        type="button"
                        onClick={() => void selectSettingsPane(item.pane)}
                        className={cn(
                          `w-full min-h-11 rounded-[4px] border px-2.5 py-2 text-left transition-colors ${DESKTOP_FOCUS_CLASS}`,
                          active
                            ? "border-[#34342e] bg-[#171813] text-[#f0ebdf] shadow-[inset_3px_0_0_#ff571c]"
                            : "border-transparent text-[#aaa397] hover:border-[#2b2b26] hover:bg-[#12130f] hover:text-[#eee9dc]",
                        )}
                      >
                        <div className="flex items-start gap-3">
                          <span
                            className={cn(
                              "flex h-7 w-7 shrink-0 items-center justify-center rounded-[4px] border",
                              active ? "border-[#663619] bg-[#21150f] text-[#ff8355]" : "border-[#34342e] bg-[#11120f] text-[#777268]",
                            )}
                          >
                            <item.icon className="h-4 w-4" />
                          </span>
                          <div className="min-w-0">
                            <p className="text-[12px] font-medium">{item.label}</p>
                            <p className="mt-1 hidden text-[11px] leading-4 text-[#8d867a] 2xl:block">{item.description}</p>
                          </div>
                        </div>
                      </button>
                    );
                  })}
                </div>
              </aside>
            ) : null}

            <div className="flex min-w-0 flex-1 flex-col">
              {(role === "sessions" || role === "traces") && (
                <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[#2b2b26] bg-[#0c0d0b] px-4 py-2.5">
                  <div className="flex items-center gap-2">
                    {role === "traces" ? (
                      <div
                        role="tablist"
                        aria-label="Trace views"
                        onKeyDown={handleTraceTabKeyDown}
                        className="inline-flex items-center gap-px rounded-[4px] border border-[#34342e] bg-[#090a08] p-1"
                      >
                        {[
                          { label: "Timeline", tab: "timeline" },
                          { label: "Logs", tab: "logs" },
                        ].map((item) => (
                          <button
                            key={item.tab}
                            type="button"
                            role="tab"
                            aria-selected={tracesTab === item.tab}
                            onClick={() => void selectTracesTab(item.tab)}
                            className={cn(
                              `rounded-[4px] px-3 py-1.5 text-[12px] transition-colors ${DESKTOP_FOCUS_CLASS}`,
                              tracesTab === item.tab
                                ? "bg-[#21150f] text-[#ff8355]"
                                : "text-[#999284] hover:bg-[#151612] hover:text-[#eee9dc]",
                            )}
                          >
                            {item.label}
                          </button>
                        ))}
                      </div>
                    ) : (
                      <div className="rounded-[4px] border border-[#34342e] bg-[#151612] px-3 py-1.5 text-[11px] text-[#aaa397]">
                        Dedicated conversation workspace
                      </div>
                    )}
                  </div>

                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() =>
                        void window.mutxDesktop?.bridge.system.revealInFinder(
                          status.assistant?.workspace || "",
                        )
                      }
                      disabled={!status.assistant?.workspace}
                      className={cn(DESKTOP_ACTION_CLASS, "inline-flex items-center gap-2 border-[#35352f] bg-[#11120f] px-3 text-[#aaa397] hover:border-[#56534b] hover:text-[#eee9dc]")}
                    >
                      <FolderOpen className="h-4 w-4" aria-hidden="true" />
                      Reveal Files
                    </button>
                    <button
                      type="button"
                      onClick={() => void openWindow("workspace", { pane: "overview" })}
                      className={cn(DESKTOP_ACTION_CLASS, "inline-flex items-center gap-2 border-[#35352f] bg-[#11120f] px-3 text-[#aaa397] hover:border-[#56534b] hover:text-[#eee9dc]")}
                    >
                      <LayoutPanelLeft className="h-4 w-4" aria-hidden="true" />
                      Overview Window
                    </button>
                  </div>
                </div>
              )}

              <main id="main-content" tabIndex={-1} className="min-w-0 flex-1 overflow-y-auto bg-[#090a08] p-3 outline-none sm:p-4 2xl:p-5">{children}</main>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
