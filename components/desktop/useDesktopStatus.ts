"use client";

import {
  createElement,
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import type { DesktopStatus } from "@/components/desktop/types";

const UNAVAILABLE_SOURCE = {
  freshness: "unavailable" as const,
  observedAt: null,
  lastSuccessAt: null,
  lastError: null,
};
const STATUS_SOURCE_STALE_AFTER_MS = 90000;
const STATUS_SOURCE_REFRESH_MS = 30000;
const STATUS_SOURCE_NAMES: Array<keyof DesktopStatus["sources"]> = [
  "uiServer",
  "bridge",
  "context",
  "auth",
  "runtime",
  "governance",
  "sessions",
  "controlPlane",
];

const DEFAULT_STATUS: DesktopStatus = {
  mode: "unknown",
  apiUrl: null,
  apiHealth: "unknown",
  authenticated: false,
  user: null,
  openclaw: {
    binaryPath: null,
    health: "unknown",
    gatewayUrl: null,
  },
  faramesh: {
    available: false,
    socketPath: null,
    health: "unknown",
  },
  uiServer: {
    ready: false,
    state: "unknown",
    url: null,
    port: null,
    lastError: null,
    lastExitCode: null,
    attempt: 0,
    observedAt: null,
  },
  localControlPlane: {
    ready: false,
    path: null,
    state: "unknown",
    exists: null,
    lastError: null,
  },
  runtime: {
    state: "unknown",
    lastError: null,
  },
  assistant: {
    found: false,
    name: null,
    agentId: null,
    workspace: null,
    gatewayStatus: null,
    sessionCount: 0,
    state: "unknown",
    lastError: null,
  },
  bridge: {
    ready: false,
    state: "unknown",
    pythonCommand: null,
    scriptPath: null,
    lastError: null,
    lastExitCode: null,
  },
  cliAvailable: false,
  mutxVersion: null,
  sources: {
    uiServer: { ...UNAVAILABLE_SOURCE },
    bridge: { ...UNAVAILABLE_SOURCE },
    context: { ...UNAVAILABLE_SOURCE },
    auth: { ...UNAVAILABLE_SOURCE },
    runtime: { ...UNAVAILABLE_SOURCE },
    governance: { ...UNAVAILABLE_SOURCE },
    sessions: { ...UNAVAILABLE_SOURCE },
    controlPlane: { ...UNAVAILABLE_SOURCE },
  },
  lastUpdated: null,
};

export function markStaleDesktopSources(
  status: DesktopStatus,
  nowMs = Date.now(),
): DesktopStatus {
  let changed = false;
  const sources = { ...status.sources };

  STATUS_SOURCE_NAMES.forEach((sourceName) => {
    const source = status.sources[sourceName];
    const lastSuccessMs = source.lastSuccessAt ? Date.parse(source.lastSuccessAt) : Number.NaN;
    if (
      source.freshness === "fresh" &&
      Number.isFinite(lastSuccessMs) &&
      nowMs - lastSuccessMs > STATUS_SOURCE_STALE_AFTER_MS
    ) {
      sources[sourceName] = { ...source, freshness: "stale" };
      changed = true;
    }
  });

  return changed ? { ...status, sources } : status;
}

export interface DesktopStatusContextValue {
  status: DesktopStatus;
  loading: boolean;
  error: string | null;
  platformReady: boolean;
  refetch: () => Promise<void>;
  isDesktop: boolean;
}

const DesktopStatusContext = createContext<DesktopStatusContextValue | null>(null);

function useDesktopStatusState(active: boolean): DesktopStatusContextValue {
  const [status, setStatus] = useState<DesktopStatus>(DEFAULT_STATUS);
  const [loading, setLoading] = useState(active);
  const [error, setError] = useState<string | null>(null);
  const [isDesktop, setIsDesktop] = useState(false);
  const [platformReady, setPlatformReady] = useState(false);

  const fetchStatus = useCallback(async () => {
    if (!active) {
      return;
    }

    if (typeof window === "undefined") {
      return;
    }

    const desktopApi = window.mutxDesktop;
    const desktop = !!desktopApi?.isDesktop;
    setIsDesktop(desktop);
    setPlatformReady(true);

    if (!desktopApi?.isDesktop) {
      setLoading(false);
      return;
    }

    try {
      const desktopStatus = await desktopApi.getDesktopStatus();
      if (desktopStatus) {
        setStatus(markStaleDesktopSources(desktopStatus as DesktopStatus));
      }
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to fetch desktop status");
    } finally {
      setLoading(false);
    }
  }, [active]);

  useEffect(() => {
    if (!active) {
      return;
    }

    if (typeof window === "undefined") {
      return;
    }

    const desktopApi = window.mutxDesktop;
    const desktop = !!desktopApi?.isDesktop;
    setIsDesktop(desktop);
    setPlatformReady(true);

    if (!desktopApi?.isDesktop) {
      setLoading(false);
      return;
    }

    fetchStatus();

    const unsubscribe = desktopApi.onDesktopStatusChanged((newStatus) => {
      setStatus(markStaleDesktopSources(newStatus as DesktopStatus));
    });
    const staleInterval = window.setInterval(() => {
      setStatus((current) => markStaleDesktopSources(current));
    }, STATUS_SOURCE_REFRESH_MS);

    return () => {
      unsubscribe?.();
      window.clearInterval(staleInterval);
    };
  }, [active, fetchStatus]);

  return {
    status,
    loading: loading && isDesktop,
    error,
    platformReady,
    refetch: fetchStatus,
    isDesktop,
  };
}

export function DesktopStatusProvider({
  children,
}: {
  children: ReactNode;
}) {
  const value = useDesktopStatusState(true);
  const memoizedValue = useMemo(
    () => value,
    [value.error, value.isDesktop, value.loading, value.platformReady, value.refetch, value.status],
  );

  return createElement(DesktopStatusContext.Provider, { value: memoizedValue }, children);
}

export function useDesktopStatus() {
  const context = useContext(DesktopStatusContext);
  const fallback = useDesktopStatusState(!context);

  return context ?? fallback;
}
