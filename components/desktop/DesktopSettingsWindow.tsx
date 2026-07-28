"use client";

import { useCallback, useEffect, useState } from "react";
import {
  FolderOpen,
  LogOut,
  Power,
  RefreshCw,
  Shield,
  TerminalSquare,
  Wrench,
} from "lucide-react";

import { LiveEmptyState, LivePanel, formatDateTime } from "@/components/dashboard/livePrimitives";
import { DesktopJobNotice } from "@/components/desktop/DesktopJobNotice";
import {
  DESKTOP_ACTION_CLASS,
} from "@/components/desktop/desktopVisualContract";
import type {
  GovernanceStatus,
  RuntimeInfo,
} from "@/components/desktop/types";
import { useDesktopJob } from "@/components/desktop/useDesktopJob";
import { useDesktopStatus } from "@/components/desktop/useDesktopStatus";
import { useDesktopWindow } from "@/components/desktop/useDesktopWindow";

function PreferencesButton({
  label,
  onClick,
  icon: Icon,
  disabled = false,
  busy = false,
  tone = "default",
}: {
  label: string;
  onClick: () => void;
  icon: typeof RefreshCw;
  disabled?: boolean;
  busy?: boolean;
  tone?: "default" | "danger";
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled || busy}
      className={`inline-flex items-center gap-2 px-3 ${DESKTOP_ACTION_CLASS} ${
        tone === "danger"
          ? "border-[#66302e] bg-[#241312] text-[#ff9b96] hover:border-[#ff6d66]"
          : "border-[#48463e] bg-[#151612] text-[#c8c0b0] hover:border-[#777268] hover:text-[#eee9dc]"
      }`}
    >
      <Icon className={`h-4 w-4 ${busy ? "motion-safe:animate-spin motion-reduce:animate-none" : ""}`} aria-hidden="true" />
      {label}
    </button>
  );
}

export function DesktopSettingsWindow() {
  const { status, refetch } = useDesktopStatus();
  const { currentWindow } = useDesktopWindow();
  const {
    job,
    resetJob,
    runDoctorJob,
    runControlPlaneStartJob,
    runControlPlaneStopJob,
    runRuntimeResyncJob,
    runGovernanceRestartJob,
  } = useDesktopJob();
  const [runtimeInfo, setRuntimeInfo] = useState<RuntimeInfo | null>(null);
  const [governance, setGovernance] = useState<GovernanceStatus | null>(null);
  const [userDataPath, setUserDataPath] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const pane = currentWindow.currentWindow.payload.pane || "account";

  const loadPreferencesSnapshot = useCallback(async () => {
    if (typeof window === "undefined" || !window.mutxDesktop?.isDesktop) {
      return;
    }

    try {
      const [nextRuntimeInfo, nextGovernance, nextUserDataPath] = await Promise.all([
        window.mutxDesktop!.bridge.runtime.inspect(),
        window.mutxDesktop!.bridge.governance.status(),
        window.mutxDesktop!.getUserDataPath(),
      ]);
      setRuntimeInfo(nextRuntimeInfo);
      setGovernance(nextGovernance);
      setUserDataPath(nextUserDataPath);
      setError(null);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Failed to load preferences state");
    }
  }, []);

  useEffect(() => {
    void loadPreferencesSnapshot();
  }, [loadPreferencesSnapshot, pane]);

  useEffect(() => {
    if (job.status === "completed") {
      void loadPreferencesSnapshot();
    }
  }, [job.status, loadPreferencesSnapshot]);

  const sharedActions = (
    <div className="flex flex-wrap gap-2">
      <PreferencesButton
        label="Run Doctor"
        icon={Wrench}
        busy={job.id === "doctor" && job.status === "running"}
        onClick={() => void runDoctorJob()}
      />
      <PreferencesButton
        label="Open TUI"
        icon={TerminalSquare}
        disabled={!status.bridge?.ready}
        onClick={() => void window.mutxDesktop?.bridge.runtime.openSurface("tui")}
      />
      <PreferencesButton
        label="Reveal Workspace"
        icon={FolderOpen}
        disabled={!status.assistant?.workspace}
        onClick={() =>
          void window.mutxDesktop?.bridge.system.revealInFinder(status.assistant?.workspace || "")
        }
      />
    </div>
  );

  if (error) {
    return <LiveEmptyState title="Preferences unavailable" message={error} />;
  }

  return (
    <div className="space-y-4">
      <DesktopJobNotice job={job} onDismiss={resetJob} tone="light" />

      {pane === "account" ? (
        <>
          <LivePanel title="Operator Account" meta="identity + binding" action={sharedActions}>
            <div className="grid gap-4 md:grid-cols-2">
              <div className="rounded-[6px] border border-[#2b2b26] bg-[#0c0d0b] px-4 py-4">
                <p className="font-[family:var(--font-mono)] text-[9px] font-semibold uppercase tracking-[0.16em] text-[#8d867a]">
                  Signed-in operator
                </p>
                <p className="mt-2 font-[family:var(--font-site-display)] text-lg font-medium text-[#eee9dc]">
                  {status.user?.name || "No operator session"}
                </p>
                <p className="mt-1 text-sm text-[#999284]">{status.user?.email || "Sign in required"}</p>
                <p className="mt-4 text-sm text-[#999284]">Plan: {status.user?.plan || "n/a"}</p>
              </div>
              <div className="rounded-[6px] border border-[#2b2b26] bg-[#0c0d0b] px-4 py-4">
                <p className="font-[family:var(--font-mono)] text-[9px] font-semibold uppercase tracking-[0.16em] text-[#8d867a]">
                  Workspace binding
                </p>
                <p className="mt-2 break-all text-sm text-[#eee9dc]">
                  {status.assistant?.workspace || "No workspace bound to the desktop operator yet."}
                </p>
                <p className="mt-4 text-sm text-[#999284]">
                  Assistant: {status.assistant?.name || "Not configured"}
                </p>
              </div>
            </div>
            <div className="mt-4 flex flex-wrap gap-2">
              <PreferencesButton
                label="Log Out"
                icon={LogOut}
                tone="danger"
                onClick={() =>
                  void (async () => {
                    await window.mutxDesktop?.bridge.auth.logout();
                    await refetch();
                  })()
                }
              />
            </div>
          </LivePanel>
        </>
      ) : null}

      {pane === "runtime" ? (
        <>
          <LivePanel title="Runtime Control" meta="local machine runtime" action={sharedActions}>
            <div className="grid gap-4 md:grid-cols-2">
              <div className="rounded-[6px] border border-[#2b2b26] bg-[#0c0d0b] px-4 py-4">
                <p className="font-[family:var(--font-mono)] text-[9px] font-semibold uppercase tracking-[0.16em] text-[#8d867a]">
                  Control plane
                </p>
                <p className="mt-2 font-[family:var(--font-site-display)] text-lg font-medium text-[#eee9dc]">
                  {status.localControlPlane?.state === "ready"
                    ? "Online"
                    : status.localControlPlane?.state || "Unknown"}
                </p>
                <p className="mt-1 break-all text-sm text-[#999284]">
                  {status.localControlPlane?.path || "No local control plane path available."}
                </p>
                {status.localControlPlane?.lastError ? (
                  <p className="mt-3 text-sm text-[#f4cc82]">{status.localControlPlane.lastError}</p>
                ) : null}
              </div>
              <div className="rounded-[6px] border border-[#2b2b26] bg-[#0c0d0b] px-4 py-4">
                <p className="font-[family:var(--font-mono)] text-[9px] font-semibold uppercase tracking-[0.16em] text-[#8d867a]">
                  Runtime target
                </p>
                <p className="mt-2 font-[family:var(--font-site-display)] text-lg font-medium text-[#eee9dc]">{status.mode || "unknown"}</p>
                <p className="mt-1 break-all text-sm text-[#999284]">{status.apiUrl || "No API target configured."}</p>
                {status.runtime?.lastError ? (
                  <p className="mt-3 text-sm text-[#f4cc82]">{status.runtime.lastError}</p>
                ) : null}
              </div>
            </div>
            <div className="mt-4 flex flex-wrap gap-2">
              <PreferencesButton
                label={status.localControlPlane?.ready ? "Stop Local Stack" : "Start Local Stack"}
                icon={Power}
                busy={
                  (job.id === "controlPlaneStart" || job.id === "controlPlaneStop") &&
                  job.status === "running"
                }
                onClick={() =>
                  void (status.localControlPlane?.ready ? runControlPlaneStopJob() : runControlPlaneStartJob())
                }
              />
              <PreferencesButton
                label="Resync Runtime"
                icon={RefreshCw}
                busy={job.id === "runtimeResync" && job.status === "running"}
                onClick={() => void runRuntimeResyncJob()}
              />
            </div>
          </LivePanel>
        </>
      ) : null}

      {pane === "gateway" ? (
        <LivePanel title="Gateway" meta="openclaw posture" action={sharedActions}>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="rounded-[6px] border border-[#2b2b26] bg-[#0c0d0b] px-4 py-4">
              <p className="font-[family:var(--font-mono)] text-[9px] font-semibold uppercase tracking-[0.16em] text-[#8d867a]">Gateway health</p>
              <p className="mt-2 font-[family:var(--font-site-display)] text-lg font-medium text-[#eee9dc]">{status.openclaw?.health || "unknown"}</p>
              <p className="mt-1 break-all text-sm text-[#999284]">{status.openclaw?.gatewayUrl || "Gateway URL unavailable."}</p>
            </div>
            <div className="rounded-[6px] border border-[#2b2b26] bg-[#0c0d0b] px-4 py-4">
              <p className="font-[family:var(--font-mono)] text-[9px] font-semibold uppercase tracking-[0.16em] text-[#8d867a]">Gateway config</p>
              <p className="mt-2 break-all text-sm text-[#eee9dc]">
                {typeof runtimeInfo?.openclaw?.config_path === "string"
                  ? runtimeInfo.openclaw.config_path
                  : "No config path reported."}
              </p>
              <p className="mt-3 text-sm text-[#999284]">
                {typeof runtimeInfo?.openclaw?.gateway === "object" &&
                runtimeInfo?.openclaw?.gateway &&
                "doctor_summary" in runtimeInfo.openclaw.gateway &&
                typeof runtimeInfo.openclaw.gateway.doctor_summary === "string"
                  ? runtimeInfo.openclaw.gateway.doctor_summary
                  : "No doctor summary reported."}
              </p>
            </div>
          </div>
        </LivePanel>
      ) : null}

      {pane === "governance" ? (
        <LivePanel title="Governance" meta="faramesh" action={sharedActions}>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="rounded-[6px] border border-[#2b2b26] bg-[#0c0d0b] px-4 py-4">
              <p className="font-[family:var(--font-mono)] text-[9px] font-semibold uppercase tracking-[0.16em] text-[#8d867a]">Daemon status</p>
              <p className="mt-2 font-[family:var(--font-site-display)] text-lg font-medium text-[#eee9dc]">
                {status.faramesh?.available ? status.faramesh.health || "active" : "idle"}
              </p>
              <p className="mt-1 break-all text-sm text-[#999284]">
                {status.faramesh?.socketPath || "No local governance socket available."}
              </p>
            </div>
            <div className="rounded-[6px] border border-[#2b2b26] bg-[#0c0d0b] px-4 py-4">
              <p className="font-[family:var(--font-mono)] text-[9px] font-semibold uppercase tracking-[0.16em] text-[#8d867a]">Approval backlog</p>
              <p className="mt-2 font-[family:var(--font-mono)] text-lg font-medium text-[#eee9dc]">{governance?.pending_approvals ?? 0}</p>
              <p className="mt-1 text-sm text-[#999284]">
                Last decision {formatDateTime(governance?.last_decision_at || null)}
              </p>
            </div>
          </div>
          <div className="mt-4 flex flex-wrap gap-2">
            <PreferencesButton
              label="Restart Governance"
              icon={Shield}
              busy={job.id === "governanceRestart" && job.status === "running"}
              onClick={() => void runGovernanceRestartJob()}
            />
          </div>
        </LivePanel>
      ) : null}

      {pane === "advanced" ? (
        <LivePanel title="Advanced Desktop State" meta="bridge + internals" action={sharedActions}>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="rounded-[6px] border border-[#2b2b26] bg-[#0c0d0b] px-4 py-4">
              <p className="font-[family:var(--font-mono)] text-[9px] font-semibold uppercase tracking-[0.16em] text-[#8d867a]">Bridge</p>
              <p className="mt-2 break-all font-[family:var(--font-mono)] text-xs text-[#eee9dc]">{status.bridge.pythonCommand || "unknown"}</p>
              <p className="mt-1 break-all font-[family:var(--font-mono)] text-xs text-[#999284]">{status.bridge.scriptPath || "No bridge script path"}</p>
              <p className="mt-3 text-sm text-[#999284]">
                State {status.bridge.state || "unknown"}
                {status.bridge.lastError ? ` · ${status.bridge.lastError}` : ""}
              </p>
            </div>
            <div className="rounded-[6px] border border-[#2b2b26] bg-[#0c0d0b] px-4 py-4">
              <p className="font-[family:var(--font-mono)] text-[9px] font-semibold uppercase tracking-[0.16em] text-[#8d867a]">Desktop UI server</p>
              <p className="mt-2 break-all font-[family:var(--font-mono)] text-xs text-[#eee9dc]">{status.uiServer?.url || "No local UI server URL"}</p>
              <p className="mt-1 text-sm text-[#999284]">
                State {status.uiServer?.state || "unknown"}
                {status.uiServer?.lastError ? ` · ${status.uiServer.lastError}` : ""}
              </p>
            </div>
            <div className="rounded-[6px] border border-[#2b2b26] bg-[#0c0d0b] px-4 py-4 md:col-span-2">
              <p className="font-[family:var(--font-mono)] text-[9px] font-semibold uppercase tracking-[0.16em] text-[#8d867a]">User data path</p>
              <p className="mt-2 break-all font-[family:var(--font-mono)] text-xs text-[#eee9dc]">{userDataPath || "Unknown"}</p>
              <p className="mt-1 text-sm text-[#999284]">
                MUTX version {status.mutxVersion || "unknown"} · runtime state {status.runtime?.state || "unknown"}
              </p>
            </div>
          </div>
        </LivePanel>
      ) : null}
    </div>
  );
}
