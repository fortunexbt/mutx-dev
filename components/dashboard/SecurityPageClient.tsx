"use client";

import { useEffect, useState } from "react";
import { KeyRound, Lock, ShieldCheck } from "lucide-react";

import { normalizeCollection, readJson } from "@/components/app/http";
import {
  dashboardRequestErrorMessage,
  getDashboardRequestAccessFailure,
} from "@/components/dashboard/dashboardRequestAccess";
import {
  LiveAuthRequired,
  LiveErrorState,
  LiveForbidden,
  LiveKpiGrid,
  LiveLoading,
  LivePanel,
  LiveStatCard,
  asDashboardStatus,
  formatDateTime,
  formatRelativeTime,
} from "@/components/dashboard/livePrimitives";
import { StatusBadge } from "@/components/dashboard/StatusBadge";

import type { components } from "@/app/types/api";

type ApiKeyRecord = components["schemas"]["APIKeyResponse"];

export function SecurityPageClient() {
  const [loading, setLoading] = useState(true);
  const [authRequired, setAuthRequired] = useState(false);
  const [permissionDenied, setPermissionDenied] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [keys, setKeys] = useState<ApiKeyRecord[]>([]);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setLoading(true);
      setError(null);
      setAuthRequired(false);
      setPermissionDenied(false);

      try {
        const response = await readJson<unknown>("/api/api-keys");
        if (!cancelled) {
          setKeys(normalizeCollection<ApiKeyRecord>(response, ["keys", "api_keys", "items", "data"]));
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
            setError(dashboardRequestErrorMessage(loadError, "Failed to load security state"));
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

  if (loading) return <LiveLoading title="Security" />;
  if (authRequired) {
    return (
      <LiveAuthRequired
        title="Operator session required"
        message="Sign in to inspect API keys, auth posture, and credential lifecycle."
      />
    );
  }
  if (permissionDenied) {
    return <LiveForbidden title="Security permission required" message="Your account cannot inspect API-key or credential lifecycle state." />;
  }
  if (error) return <LiveErrorState title="Security surface unavailable" message={error} />;

  const liveKeys = keys.filter(
    (key) => key.is_active && (!key.expires_at || new Date(key.expires_at).getTime() > Date.now()),
  );

  return (
    <div className="space-y-4">
      <LiveKpiGrid>
        <LiveStatCard
          label="Credentials"
          value={String(keys.length)}
          detail={`${liveKeys.length} active and unexpired.`}
          status={asDashboardStatus(liveKeys.length > 0 ? "healthy" : "idle")}
        />
        <LiveStatCard
          label="Boundary"
          value="Operator owned"
          detail="Auth and key state are held inside the product, not in a disconnected admin wall."
          status="success"
        />
      </LiveKpiGrid>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.1fr)_minmax(320px,0.9fr)]">
        <LivePanel title="Credential inventory" meta={`${keys.length} keys`}>
          <div className="space-y-3">
            {keys.length === 0 ? (
              <div className="rounded-xl border border-dashed border-white/10 bg-white/[0.02] p-6 text-sm text-slate-400">
                No API keys returned yet. Once operator credentials exist, rotation posture will show up here.
              </div>
            ) : (
              keys.map((key) => (
                <div key={key.id} className="rounded-xl border border-white/10 bg-white/[0.02] p-4">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-white">{key.name}</p>
                      <p className="mt-1 break-all font-mono text-xs text-slate-500">{key.id}</p>
                    </div>
                    <StatusBadge
                      status={key.is_active ? "success" : "idle"}
                      label={key.is_active ? "active" : "revoked"}
                    />
                  </div>
                  <div className="mt-3 grid gap-2 text-xs text-slate-500 sm:grid-cols-2">
                    <div>created {formatDateTime(key.created_at)}</div>
                    <div>last used {key.last_used ? formatRelativeTime(key.last_used) : "never"}</div>
                    <div>expires {key.expires_at ? formatDateTime(key.expires_at) : "no expiry"}</div>
                    <div>lifecycle {key.is_active ? "enabled" : "revoked"}</div>
                  </div>
                </div>
              ))
            )}
          </div>
        </LivePanel>

        <LivePanel title="Security posture" meta="workspace trust">
          <div className="space-y-3">
            <div className="rounded-xl border border-white/10 bg-white/[0.02] p-4">
              <div className="flex items-center gap-2 text-slate-300">
                <ShieldCheck className="h-4 w-4 text-cyan-300" />
                <span className="text-sm font-medium">Owned credentials</span>
              </div>
              <p className="mt-3 text-sm leading-6 text-slate-400">
                MUTX keeps API keys and deployment actions in the same governance surface so rotation, ownership, and actionability stay connected.
              </p>
            </div>
            <div className="rounded-xl border border-white/10 bg-white/[0.02] p-4">
              <div className="flex items-center gap-2 text-slate-300">
                <Lock className="h-4 w-4 text-cyan-300" />
                <span className="text-sm font-medium">Auth boundary</span>
              </div>
              <p className="mt-3 text-sm leading-6 text-slate-400">
                Dashboard surfaces now fail honestly into auth-required state instead of rendering dead-end product shells.
              </p>
            </div>
            <div className="rounded-xl border border-white/10 bg-white/[0.02] p-4">
              <div className="flex items-center gap-2 text-slate-300">
                <KeyRound className="h-4 w-4 text-cyan-300" />
                <span className="text-sm font-medium">Rotation posture</span>
              </div>
              <p className="mt-3 text-sm leading-6 text-slate-400">
                Keys should rotate from the same product area teams use to deploy, replay, and recover.
              </p>
            </div>
          </div>
        </LivePanel>
      </div>
    </div>
  );
}
