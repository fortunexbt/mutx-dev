"use client";

import { Bot, Server, Shield, Users, HardDrive, Globe } from "lucide-react";

import type {
  DesktopStatusSource,
  DesktopStatusSourceFreshness,
  GovernanceRuntimeState,
} from "@/components/desktop/types";
import {
  DESKTOP_SOURCE_TONE_CLASS,
  getDesktopFreshnessPresentation,
} from "@/components/desktop/desktopVisualContract";
import { useDesktopStatus } from "@/components/desktop/useDesktopStatus";

type CardTone = "default" | "good" | "warn" | "bad";

const SOURCE_RANK: Record<DesktopStatusSourceFreshness, number> = {
  fresh: 0,
  checking: 1,
  stale: 2,
  unavailable: 3,
};

function StatusDot({ status }: { status: string }) {
  const color =
    status === "healthy" || status === "ready"
      ? "bg-[#4bd69b]"
      : status === "running" || status === "checking"
        ? "bg-[#58aaff]"
      : status === "degraded" || status === "warning" || status === "stopped"
        ? "bg-[#efb654]"
        : status === "error" || status === "unavailable"
          ? "bg-[#ff6d66]"
          : "bg-[#77766d]";

  return <span aria-hidden="true" className={`inline-block h-2 w-2 rounded-full ${color}`} />;
}

function DesktopCard({
  icon: Icon,
  title,
  children,
  tone = "default",
}: {
  icon: React.ElementType;
  title: string;
  children: React.ReactNode;
  tone?: CardTone;
}) {
  const borderColors = {
    default: "border-[#2b2b26]",
    good: "border-[#285a43]",
    warn: "border-[#65502b]",
    bad: "border-[#66302e]",
  };

  const iconColors = {
    default: "text-[#ff7545]",
    good: "text-[#4bd69b]",
    warn: "text-[#efb654]",
    bad: "text-[#ff6d66]",
  };

  return (
    <article className={`rounded-[6px] border bg-[#11120f] p-4 ${borderColors[tone]}`}>
      <div className="flex items-center gap-2">
        <Icon className={`h-4 w-4 ${iconColors[tone]}`} aria-hidden="true" />
        <span className="font-[family:var(--font-mono)] text-[9px] font-semibold uppercase tracking-[0.16em] text-[#8d867a]">
          {title}
        </span>
      </div>
      <div className="mt-3">{children}</div>
    </article>
  );
}

function formatEndpoint(value: string | null | undefined) {
  if (!value) {
    return null;
  }
  try {
    const endpoint = new URL(value);
    return endpoint.host;
  } catch {
    return "Configured endpoint";
  }
}

function formatCheckedAt(value: string | null) {
  if (!value) {
    return null;
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return null;
  }
  return parsed.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function combineSources(...sources: DesktopStatusSource[]): DesktopStatusSource {
  return sources.reduce((worst, source) =>
    SOURCE_RANK[source.freshness] > SOURCE_RANK[worst.freshness] ? source : worst,
  );
}

function SourceNote({ source }: { source: DesktopStatusSource }) {
  const presentation = getDesktopFreshnessPresentation(source.freshness);
  const checkedAt = formatCheckedAt(
    source.freshness === "stale" ? source.lastSuccessAt : source.observedAt,
  );
  const suffix = checkedAt ? ` · ${checkedAt}` : "";
  const label =
    source.freshness === "fresh"
      ? `${presentation.label}${suffix}`
      : source.freshness === "checking"
        ? `${presentation.label}…`
        : source.freshness === "stale"
          ? `${presentation.label}${suffix}`
          : `${presentation.label}${suffix}`;

  return (
    <p
      role="status"
      className={`mt-3 inline-flex rounded-full border px-2 py-1 font-[family:var(--font-mono)] text-[9px] font-semibold uppercase tracking-[0.12em] ${DESKTOP_SOURCE_TONE_CLASS[presentation.tone]}`}
    >
      {label}
    </p>
  );
}

function toneForSource(source: DesktopStatusSource, healthyTone: CardTone): CardTone {
  if (source.freshness === "unavailable") {
    return "bad";
  }
  if (source.freshness === "stale" || source.freshness === "checking") {
    return "warn";
  }
  return healthyTone;
}

export function getGovernancePresentation(
  state: GovernanceRuntimeState,
  sourceFreshness: DesktopStatusSourceFreshness = "fresh",
): { label: string; dot: string; tone: CardTone } {
  if (sourceFreshness === "unavailable") {
    return { label: "Unavailable", dot: "unavailable", tone: "bad" };
  }

  const presentations: Record<GovernanceRuntimeState, { label: string; dot: string; tone: CardTone }> = {
    running: { label: "Running", dot: "running", tone: "good" },
    stopped: { label: "Stopped", dot: "stopped", tone: "warn" },
    degraded: { label: "Degraded", dot: "degraded", tone: "warn" },
    not_installed: { label: "Not installed", dot: "unknown", tone: "default" },
    error: { label: "Error", dot: "error", tone: "bad" },
    unknown: { label: "Unknown", dot: "unknown", tone: "default" },
    unavailable: { label: "Unavailable", dot: "unavailable", tone: "bad" },
  };
  const presentation = presentations[state];

  return sourceFreshness === "fresh"
    ? presentation
    : { ...presentation, tone: "warn" };
}

export function DesktopStatusRow() {
  const { status, loading, error, isDesktop } = useDesktopStatus();

  if (!isDesktop) {
    return null;
  }

  if (loading) {
    return (
      <div role="status" aria-label="Loading desktop status" className="grid gap-2.5 sm:grid-cols-2 lg:grid-cols-4">
        {[1, 2, 3, 4].map((i) => (
          <div
            key={i}
            className="h-24 rounded-[6px] border border-[#2b2b26] bg-[#11120f] motion-safe:animate-pulse motion-reduce:animate-none"
          />
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <div role="alert" className="rounded-[6px] border border-[#66302e] bg-[#241312] p-4">
        <p className="text-sm text-[#ff9b96]">
          Desktop status is unavailable. Retry from Desktop Settings.
        </p>
      </div>
    );
  }

  const modeSource = status.sources.context;
  const gatewaySource = status.sources.runtime;
  const governanceSource = status.sources.governance;
  const assistantSource = combineSources(status.sources.runtime, status.sources.sessions);
  const modeTone = toneForSource(
    modeSource,
    status.mode === "local" ? "good" : status.mode === "hosted" ? "default" : "warn",
  );
  const gatewayTone = toneForSource(
    gatewaySource,
    status.openclaw.health === "healthy" || status.openclaw.health === "running"
      ? "good"
      : status.openclaw.health === "unknown"
        ? "default"
        : "warn",
  );
  const governance = getGovernancePresentation(
    status.faramesh.health,
    governanceSource.freshness,
  );
  const assistantTone = toneForSource(
    assistantSource,
    status.assistant.found ? "good" : "default",
  );
  const apiEndpoint = formatEndpoint(status.apiUrl);
  const gatewayEndpoint = formatEndpoint(status.openclaw.gatewayUrl);

  return (
    <section aria-labelledby="desktop-status-heading" className="space-y-3">
      <div className="flex items-center justify-between border-b border-[#34342e] pb-2">
        <h2 id="desktop-status-heading" className="font-[family:var(--font-mono)] text-[10px] font-semibold uppercase tracking-[0.16em] text-[#c8c0b0]">
          <span className="mr-2 text-[#ff7545]" aria-hidden="true">REC /</span>
          Desktop status
        </h2>
        {status.mutxVersion && (
          <span className="font-[family:var(--font-mono)] text-[10px] text-[#8d867a]">v{status.mutxVersion}</span>
        )}
      </div>

      {status.uiServer.state !== "ready" ? (
        <div role="alert" className="rounded-[6px] border border-[#66302e] bg-[#241312] p-3">
          <p className="text-sm text-[#ff9b96]">
            {status.uiServer.lastError ||
              "Desktop UI is still starting. Restart MUTX if it does not recover."}
          </p>
          <SourceNote source={status.sources.uiServer} />
        </div>
      ) : null}

      <div className="grid gap-2.5 sm:grid-cols-2 lg:grid-cols-4">
        <DesktopCard icon={Globe} title="Mode" tone={modeTone}>
          <div className="flex items-center gap-2">
            <StatusDot status={modeSource.freshness === "fresh" ? status.mode : modeSource.freshness} />
            <span className="text-sm font-medium capitalize text-[#eee9dc]">{status.mode}</span>
          </div>
          {apiEndpoint && <p className="mt-1 truncate font-[family:var(--font-mono)] text-[10px] text-[#999284]">{apiEndpoint}</p>}
          <SourceNote source={modeSource} />
        </DesktopCard>

        <DesktopCard icon={Server} title="Gateway" tone={gatewayTone}>
          <div className="flex items-center gap-2">
            <StatusDot
              status={gatewaySource.freshness === "fresh" ? status.openclaw.health : gatewaySource.freshness}
            />
            <span className="text-sm font-medium text-[#eee9dc]">{status.openclaw.health}</span>
          </div>
          {gatewayEndpoint && (
            <p className="mt-1 truncate font-[family:var(--font-mono)] text-[10px] text-[#999284]">{gatewayEndpoint}</p>
          )}
          <SourceNote source={gatewaySource} />
        </DesktopCard>

        <DesktopCard icon={Shield} title="Governance" tone={governance.tone}>
          <div className="flex items-center gap-2">
            <StatusDot status={governance.dot} />
            <span className="text-sm font-medium text-[#eee9dc]">{governance.label}</span>
          </div>
          <SourceNote source={governanceSource} />
        </DesktopCard>

        <DesktopCard icon={Bot} title="Assistant" tone={assistantTone}>
          {status.assistant.found ? (
            <>
              <p className="font-[family:var(--font-site-display)] text-lg font-medium text-[#eee9dc]">
                {status.assistant.name || "Unnamed assistant"}
              </p>
              <p className="text-xs text-[#8d867a]">Name</p>
              <div className="mt-2 flex items-center gap-2">
                <Users className="h-3 w-3 text-[#8d867a]" aria-hidden="true" />
                <span className="text-xs text-[#999284]">
                  {status.assistant.sessionCount === null
                    ? "Session count unavailable"
                    : `${status.assistant.sessionCount} sessions`}
                </span>
              </div>
            </>
          ) : (
            <p className="text-sm text-[#999284]">
              {assistantSource.freshness === "unavailable" ? "Unavailable" : "Not configured"}
            </p>
          )}
          <SourceNote source={assistantSource} />
        </DesktopCard>
      </div>

      {status.mode === "local" || status.localControlPlane.exists !== null ? (
        <div className="rounded-[6px] border border-[#2b2b26] bg-[#0c0d0b] p-3">
          <div className="flex items-center gap-2">
            <HardDrive className="h-4 w-4 text-[#ff7545]" aria-hidden="true" />
            <span className="text-xs text-[#aaa397]">
              Local control plane: {status.localControlPlane.ready ? "Ready" : "Not ready"}
            </span>
            <StatusDot status={status.localControlPlane.ready ? "ready" : status.localControlPlane.state} />
          </div>
          <SourceNote source={status.sources.controlPlane} />
        </div>
      ) : null}
    </section>
  );
}
