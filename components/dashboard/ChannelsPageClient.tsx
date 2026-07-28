"use client";

import { useEffect, useState } from "react";
import { Globe2, MessagesSquare, Radio } from "lucide-react";

import { readJson } from "@/components/app/http";
import {
  dashboardRequestErrorMessage,
  getDashboardRequestAccessFailure,
} from "@/components/dashboard/dashboardRequestAccess";
import {
  LiveAuthRequired,
  LiveEmptyState,
  LiveErrorState,
  LiveForbidden,
  LiveKpiGrid,
  LiveLoading,
  LiveMiniStat,
  LiveMiniStatGrid,
  LivePanel,
  LiveStatCard,
  formatRelativeTime,
} from "@/components/dashboard/livePrimitives";
import { StatusBadge } from "@/components/dashboard/StatusBadge";

type ChannelPayload = {
  generatedAt: string;
  hasAssistant: boolean;
  sourceStatus: {
    overview: ChannelSourceStatus;
    channels: ChannelSourceStatus;
    sessions: ChannelSourceStatus;
  };
  assistant: {
    agentId: string | null;
    name: string;
    workspace: string;
    status: string;
    gatewayStatus: string;
    gatewayUrl: string | null;
    doctorSummary: string;
    wakeups: Array<{
      enabled?: boolean;
      schedule?: string | null;
      timezone?: string | null;
      label?: string | null;
    }>;
  } | null;
  summary: {
    configuredChannels: number | null;
    enabledChannels: number | null;
    liveChannels: number | null;
    activeSessions: number | null;
    sources: number | null;
  };
  channels: Array<{
    id: string;
    label: string;
    enabled: boolean;
    mode: string;
    allowFrom: string[];
    sessionCount: number;
    activeSessions: number;
    latestActivity: string | null;
    sources: string[];
  }>;
  sessionSources: Array<{ source: string; count: number }>;
  partials: string[];
};

type ChannelSourceStatus = "ok" | "partial" | "auth_error" | "error";

export function ChannelsPageClient() {
  const [loading, setLoading] = useState(true);
  const [authRequired, setAuthRequired] = useState(false);
  const [permissionDenied, setPermissionDenied] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [payload, setPayload] = useState<ChannelPayload | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setLoading(true);
      setAuthRequired(false);
      setPermissionDenied(false);
      setError(null);

      try {
        const response = await readJson<ChannelPayload>("/api/dashboard/channels");
        if (!cancelled) {
          setPayload(response);
          setLoading(false);
        }
      } catch (loadError) {
        if (!cancelled) {
          const accessFailure = getDashboardRequestAccessFailure(loadError);
          if (accessFailure === "authentication") {
            setAuthRequired(true);
          } else if (accessFailure === "permission") {
            setPermissionDenied(true);
          } else {
            setError(dashboardRequestErrorMessage(loadError, "Failed to load channels"));
          }
          setLoading(false);
        }
      }
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  if (loading) return <LiveLoading title="Channels" />;
  if (authRequired) {
    return (
      <LiveAuthRequired
        title="Operator session required"
        message="Sign in to inspect assistant channel bindings, session coverage, and gateway posture."
      />
    );
  }
  if (permissionDenied) {
    return <LiveForbidden title="Channel permission required" message="Your account cannot read assistant channel bindings or gateway posture." />;
  }
  if (error) return <LiveErrorState title="Channel surface unavailable" message={error} />;
  if (!payload) {
    return (
      <LiveErrorState
        title="Channel surface unavailable"
        message="No channel payload was returned by the dashboard proxy."
      />
    );
  }

  if (!payload.hasAssistant || !payload.assistant) {
    return (
      <LiveEmptyState
        title={
          payload.sourceStatus.overview === "ok"
            ? "No assistant channels yet"
            : "Assistant channel coverage is incomplete"
        }
        message={
          payload.sourceStatus.overview === "ok"
            ? "This route becomes useful once an owned assistant runtime exists and exposes channel state through the control plane."
            : "The assistant overview is unavailable or malformed, so the dashboard cannot verify that this workspace has no channel bindings."
        }
      />
    );
  }

  return (
    <div className="space-y-4">
      <LiveKpiGrid>
        <LiveStatCard
          label="Configured"
          value={
            payload.summary.configuredChannels === null
              ? "Unknown"
              : String(payload.summary.configuredChannels)
          }
          detail={
            payload.summary.enabledChannels === null
              ? `Channel inventory coverage is incomplete for ${payload.assistant.name}.`
              : `${payload.summary.enabledChannels} channels currently enabled for ${payload.assistant.name}.`
          }
          status={
            payload.summary.enabledChannels === null
              ? "warning"
              : payload.summary.enabledChannels > 0
                ? "success"
                : "idle"
          }
        />
        <LiveStatCard
          label="Live channels"
          value={
            payload.summary.liveChannels === null
              ? "Unknown"
              : String(payload.summary.liveChannels)
          }
          detail={
            payload.summary.activeSessions === null
              ? "Session coverage is incomplete; live channel totals are not verified."
              : `${payload.summary.activeSessions} active sessions are currently mapped back to channels.`
          }
          status={
            payload.summary.liveChannels === null
              ? "warning"
              : payload.summary.liveChannels > 0
                ? "running"
                : "idle"
          }
        />
        <LiveStatCard
          label="Gateway"
          value={payload.assistant.gatewayStatus}
          detail={payload.assistant.gatewayUrl ?? payload.assistant.doctorSummary}
          status={
            payload.assistant.gatewayStatus.toLowerCase().includes("healthy")
              ? "success"
              : payload.assistant.gatewayStatus.toLowerCase().includes("running")
                ? "running"
                : "warning"
          }
        />
        <LiveStatCard
          label="Sources"
          value={payload.summary.sources === null ? "Unknown" : String(payload.summary.sources)}
          detail="Distinct session sources currently represented in the channel feed."
          status={
            payload.summary.sources === null
              ? "warning"
              : payload.summary.sources > 0
                ? "success"
                : "idle"
          }
        />
      </LiveKpiGrid>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.15fr)_minmax(320px,0.85fr)]">
        <LivePanel title="Channel registry" meta={`${payload.channels.length} channels`}>
          {payload.channels.length === 0 ? (
            <LiveEmptyState
              title={
                payload.sourceStatus.channels === "ok"
                  ? "No channels configured"
                  : "Channel registry coverage is incomplete"
              }
              message={
                payload.sourceStatus.channels === "ok"
                  ? "Assistant channel entries will show up here once the runtime publishes them."
                  : "The channel feed is unavailable or malformed, so this empty registry is not a verified zero."
              }
            />
          ) : (
            <div className="space-y-3">
              {payload.channels.map((channel) => (
                <div
                  key={channel.id}
                  className="rounded-2xl border border-white/10 bg-white/[0.03] p-4"
                >
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-white">{channel.label}</p>
                      <p className="mt-1 text-sm text-slate-400">
                        {channel.mode} mode
                        {channel.allowFrom.length > 0
                          ? ` · allow ${channel.allowFrom.join(", ")}`
                          : " · no allow-list published"}
                      </p>
                    </div>
                    <StatusBadge
                      status={channel.enabled ? "success" : "idle"}
                      label={channel.enabled ? "enabled" : "disabled"}
                    />
                  </div>

                  <div className="mt-3 grid gap-2 sm:grid-cols-3">
                    <div className="rounded-xl border border-white/10 bg-black/20 px-3 py-2">
                      <p className="text-[10px] uppercase tracking-[0.18em] text-slate-500">
                        Sessions
                      </p>
                      <p className="mt-2 text-sm text-white">{channel.sessionCount}</p>
                    </div>
                    <div className="rounded-xl border border-white/10 bg-black/20 px-3 py-2">
                      <p className="text-[10px] uppercase tracking-[0.18em] text-slate-500">
                        Active
                      </p>
                      <p className="mt-2 text-sm text-white">{channel.activeSessions}</p>
                    </div>
                    <div className="rounded-xl border border-white/10 bg-black/20 px-3 py-2">
                      <p className="text-[10px] uppercase tracking-[0.18em] text-slate-500">
                        Last activity
                      </p>
                      <p className="mt-2 text-sm text-white">
                        {channel.latestActivity ? formatRelativeTime(channel.latestActivity) : "Not seen"}
                      </p>
                    </div>
                  </div>

                  <p className="mt-3 text-xs text-slate-500">
                    {channel.sources.length > 0
                      ? `Sources: ${channel.sources.join(", ")}`
                      : "No live session source has been mapped to this channel yet."}
                  </p>
                </div>
              ))}
            </div>
          )}
        </LivePanel>

        <div className="space-y-4">
          <LivePanel title="Gateway posture" meta={payload.assistant.workspace}>
            <LiveMiniStatGrid columns={2}>
              <LiveMiniStat
                label="Assistant"
                value={payload.assistant.name}
                detail={payload.assistant.workspace}
                icon={MessagesSquare}
              />
              <LiveMiniStat
                label="Gateway"
                value={payload.assistant.gatewayStatus}
                detail={payload.assistant.gatewayUrl ?? "No gateway URL published"}
                icon={Radio}
              />
              <LiveMiniStat
                label="Wakeups"
                value={String(payload.assistant.wakeups.length)}
                detail={
                  payload.assistant.wakeups.length > 0
                    ? payload.assistant.wakeups
                        .map((wakeup) => wakeup.label ?? wakeup.schedule ?? "scheduled")
                        .join(", ")
                    : "No wakeup schedules published"
                }
              />
              <LiveMiniStat
                label="Sources"
                value={String(payload.sessionSources.length)}
                detail="Distinct session sources contributing to this surface."
                icon={Globe2}
              />
            </LiveMiniStatGrid>

            <p className="mt-4 text-sm leading-6 text-slate-300">
              {payload.assistant.doctorSummary}
            </p>
          </LivePanel>

          <LivePanel title="Coverage notes" meta={`${payload.partials.length} notes`}>
            {payload.partials.length === 0 ? (
              <LiveEmptyState
                title="Full channel coverage"
                message="Assistant overview, channel state, and session telemetry were all available for this operator."
              />
            ) : (
              <div className="space-y-3">
                {payload.partials.map((note) => (
                  <div
                    key={note}
                    className="rounded-2xl border border-white/10 bg-white/[0.03] px-4 py-3"
                  >
                    <p className="text-sm leading-6 text-slate-300">{note}</p>
                  </div>
                ))}
              </div>
            )}
          </LivePanel>
        </div>
      </div>
    </div>
  );
}
