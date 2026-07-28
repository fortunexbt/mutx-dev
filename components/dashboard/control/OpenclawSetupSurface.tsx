"use client";

import { useEffect, useMemo, useState } from "react";
import { Check, Copy, ExternalLink, RefreshCcw } from "lucide-react";

import { ApiRequestError, extractApiErrorMessage } from "@/components/app/http";
import {
  dashboardRequestErrorMessage,
  getDashboardRequestAccessFailure,
} from "@/components/dashboard/dashboardRequestAccess";
import { LiveAuthRequired, LiveForbidden } from "@/components/dashboard/livePrimitives";
import { TopBar } from "@/components/dashboard/TopBar";
import { dashboardTokens } from "@/components/dashboard/tokens";

interface ProviderOption {
  id: string;
  label: string;
  summary: string;
  enabled: boolean;
  cue?: string | null;
}

interface WizardStep {
  id: string;
  title: string;
  completed: boolean;
}

interface OnboardingState {
  provider: string;
  status: string;
  action_type?: string | null;
  import_source?: Record<string, string | null | undefined>;
  current_step: string;
  completed_steps: string[];
  failed_step?: string | null;
  last_error?: string | null;
  checklist_dismissed?: boolean;
  assistant_name?: string | null;
  assistant_id?: string | null;
  workspace?: string | null;
  gateway_url?: string | null;
  updated_at?: string | null;
  steps: WizardStep[];
  providers: ProviderOption[];
}

interface RuntimeBinding {
  assistant_id?: string | null;
  assistant_name?: string | null;
  workspace?: string | null;
  model?: string | null;
}

interface RuntimeSnapshot {
  provider: string;
  label: string;
  status: string;
  install_method?: string | null;
  binary_path?: string | null;
  gateway_url?: string | null;
  version?: string | null;
  home_path?: string | null;
  tracking_mode?: string | null;
  adopted_existing_runtime?: boolean;
  privacy_summary?: string | null;
  keys_remain_local?: boolean;
  last_action_type?: string | null;
  import_source?: Record<string, string | null | undefined>;
  config_path?: string | null;
  state_dir?: string | null;
  last_seen_at?: string | null;
  last_synced_at?: string | null;
  stale: boolean;
  binding_count: number;
  bindings: RuntimeBinding[];
}

function toneStyles(tone: "good" | "warn" | "bad" | "info") {
  if (tone === "good") return "border-emerald-400/20 bg-emerald-400/10 text-emerald-200";
  if (tone === "warn") return "border-amber-400/20 bg-amber-400/10 text-amber-200";
  if (tone === "bad") return "border-rose-400/20 bg-rose-400/10 text-rose-200";
  return "border-sky-400/20 bg-sky-400/10 text-sky-200";
}

function statusTone(status: string): "good" | "warn" | "bad" | "info" {
  if (status === "completed" || status === "healthy") return "good";
  if (status === "failed" || status === "missing") return "bad";
  if (status === "in_progress" || status === "degraded" || status === "stale") return "warn";
  return "info";
}

function formatTimestamp(value?: string | null) {
  if (!value) return "n/a";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

function StepMarker({ step, currentStep, failedStep }: { step: WizardStep; currentStep: string; failedStep?: string | null }) {
  let marker = "·";
  let cls = "text-slate-500";
  if (failedStep && step.id === failedStep) {
    marker = "x";
    cls = "text-rose-300";
  } else if (step.completed) {
    marker = "✓";
    cls = "text-emerald-300";
  } else if (step.id === currentStep) {
    marker = "→";
    cls = "text-amber-300";
  }
  return <span className={`font-mono text-xs ${cls}`}>{marker}</span>;
}

export function OpenclawSetupSurface() {
  const [onboarding, setOnboarding] = useState<OnboardingState | null>(null);
  const [runtime, setRuntime] = useState<RuntimeSnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [authRequired, setAuthRequired] = useState(false);
  const [permissionDenied, setPermissionDenied] = useState(false);
  const [copiedCommand, setCopiedCommand] = useState<string | null>(null);
  const [copyError, setCopyError] = useState<string | null>(null);

  const commands = useMemo(
    () => [
      "mutx setup hosted --import-openclaw",
      "mutx setup local --import-openclaw",
      "mutx setup hosted --install-openclaw",
      "mutx setup local --install-openclaw",
      "mutx runtime open openclaw --surface tui",
      "mutx runtime inspect openclaw",
      "mutx runtime resync openclaw",
    ],
    [],
  );

  const refresh = async () => {
    setLoading(true);
    setError(null);
    setAuthRequired(false);
    setPermissionDenied(false);
    try {
      const [onboardingResponse, runtimeResponse] = await Promise.all([
        fetch("/api/dashboard/onboarding?provider=openclaw", { cache: "no-store" }),
        fetch("/api/dashboard/runtime/providers/openclaw", { cache: "no-store" }),
      ]);
      if (!onboardingResponse.ok) {
        const payload = await onboardingResponse.json().catch(() => null);
        throw new ApiRequestError(
          extractApiErrorMessage(payload, "Failed to load onboarding state."),
          onboardingResponse.status,
        );
      }
      if (!runtimeResponse.ok) {
        const payload = await runtimeResponse.json().catch(() => null);
        throw new ApiRequestError(
          extractApiErrorMessage(payload, "Failed to load runtime snapshot."),
          runtimeResponse.status,
        );
      }
      setOnboarding((await onboardingResponse.json()) as OnboardingState);
      setRuntime((await runtimeResponse.json()) as RuntimeSnapshot);
    } catch (fetchError) {
      const accessFailure = getDashboardRequestAccessFailure(fetchError);
      if (accessFailure === "authentication") setAuthRequired(true);
      else if (accessFailure === "permission") setPermissionDenied(true);
      else setError(dashboardRequestErrorMessage(fetchError, "Failed to load setup state."));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void refresh();
  }, []);

  const currentBinding = runtime?.bindings?.[0];

  const copyCommand = async (command: string) => {
    try {
      if (!navigator.clipboard?.writeText) {
        throw new Error("Clipboard is unavailable in this browser.");
      }

      await navigator.clipboard.writeText(command);
      setCopiedCommand(command);
      setCopyError(null);
      window.setTimeout(() => {
        setCopiedCommand((current) => (current === command ? null : current));
      }, 2000);
    } catch (copyFailure) {
      setCopyError(
        copyFailure instanceof Error ? copyFailure.message : "Failed to copy command.",
      );
    }
  };

  if (authRequired) {
    return <LiveAuthRequired title="Operator session required" message="Sign in to inspect OpenClaw setup and runtime state." />;
  }

  if (permissionDenied) {
    return <LiveForbidden title="Setup permission required" message="Your account cannot inspect OpenClaw setup or runtime state. Refresh and copy controls are unavailable." />;
  }

  return (
    <section
      className="overflow-hidden rounded-[28px] border"
      style={{
        borderColor: dashboardTokens.borderSubtle,
        background:
          "linear-gradient(180deg, rgba(15,23,42,0.94) 0%, rgba(2,6,23,0.98) 100%)",
        boxShadow: dashboardTokens.shadowLg,
      }}
    >
      <TopBar
        breadcrumbs={[
          { label: "Dashboard", href: "/dashboard" },
          { label: "Setup" },
        ]}
        title="Setup"
        subtitle="MUTX owns the onboarding shell. OpenClaw is the first tracked runtime provider and the dashboard shows the last synced local truth."
        hint={{
          tone: "boundary",
          title: "Machine-host security boundary",
          detail:
            "Web access is intentionally read-only. Installation and runtime control stay in the machine-host CLI or TUI so local keys and provider processes remain on the operator host.",
        }}
        actions={(
          <button
            type="button"
            className="inline-flex items-center gap-2 rounded-lg border px-3 py-2 text-sm"
            style={{
              borderColor: dashboardTokens.borderSubtle,
              backgroundColor: dashboardTokens.bgSurfaceStrong,
              color: dashboardTokens.textPrimary,
            }}
            onClick={() => void refresh()}
          >
            <RefreshCcw className="h-4 w-4" />
            Refresh
          </button>
        )}
        className="border-b"
      />

      <div className="grid gap-6 p-6 xl:grid-cols-[minmax(0,1.5fr)_360px]">
        <div className="space-y-6">
          <div className="grid gap-4 lg:grid-cols-3">
            {(onboarding?.providers ?? []).map((provider) => {
              const active = provider.id === "openclaw" && provider.enabled;
              return (
                <article
                  key={provider.id}
                  className="rounded-2xl border p-4"
                  style={{
                    borderColor: active ? "rgba(255, 122, 61, 0.35)" : dashboardTokens.borderSubtle,
                    backgroundColor: active ? "rgba(255, 90, 45, 0.08)" : dashboardTokens.bgSurface,
                  }}
                >
                  <div className="flex items-center justify-between gap-3">
                    <p className="text-sm font-semibold text-slate-100">
                      {provider.cue ? `${provider.cue} ` : ""}{provider.label}
                    </p>
                    <span
                      className={`rounded-full border px-2 py-0.5 text-[11px] font-medium ${toneStyles(active ? "good" : "info")}`}
                    >
                      {provider.enabled ? (active ? "active" : "enabled") : "unavailable"}
                    </span>
                  </div>
                  <p className="mt-3 text-sm text-slate-400">{provider.summary}</p>
                </article>
              );
            })}
          </div>

          <section
            className="rounded-2xl border p-5"
            style={{
              borderColor: dashboardTokens.borderSubtle,
              backgroundColor: dashboardTokens.bgSurface,
            }}
          >
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="text-[11px] font-semibold uppercase tracking-[0.2em]" style={{ color: dashboardTokens.textMuted }}>
                  Provider Wizard
                </p>
                <h2 className="mt-2 text-xl font-semibold text-slate-100">
                  {loading ? "Loading…" : onboarding ? `Status: ${onboarding.status}` : "Unavailable"}
                </h2>
                <p className="mt-1 text-sm text-slate-400">
                  {onboarding?.last_error
                    ? onboarding.last_error
                    : "Checklist progress is synced from the operator host. Web access is intentionally read-only at the machine-host security boundary."}
                </p>
                {onboarding?.action_type ? (
                  <p className="mt-2 text-xs uppercase tracking-[0.2em] text-orange-200/80">
                    action: {onboarding.action_type}
                  </p>
                ) : null}
              </div>
              {onboarding ? (
                <div className={`rounded-full border px-3 py-1 text-xs font-medium ${toneStyles(statusTone(onboarding.status))}`}>
                  current: {onboarding.current_step}
                </div>
              ) : null}
            </div>

            <div className="mt-5 grid gap-3">
              {(onboarding?.steps ?? []).map((step) => (
                <div
                  key={step.id}
                  className="flex items-center justify-between rounded-xl border px-4 py-3"
                  style={{
                    borderColor: dashboardTokens.borderSubtle,
                    backgroundColor: dashboardTokens.bgCanvas,
                  }}
                >
                  <div className="flex items-center gap-3">
                    <StepMarker
                      step={step}
                      currentStep={onboarding?.current_step ?? ""}
                      failedStep={onboarding?.failed_step}
                    />
                    <div>
                      <p className="text-sm font-medium text-slate-100">{step.title}</p>
                      <p className="text-xs text-slate-500">{step.id}</p>
                    </div>
                  </div>
                  <span className="text-xs text-slate-400">
                    {step.completed ? "complete" : onboarding?.current_step === step.id ? "active" : "pending"}
                  </span>
                </div>
              ))}
            </div>
          </section>

          <section
            className="rounded-2xl border p-5"
            style={{
              borderColor: "rgba(255, 122, 61, 0.22)",
              background:
                "linear-gradient(180deg, rgba(255,90,45,0.10) 0%, rgba(15,23,42,0.72) 100%)",
            }}
          >
            <div className="flex items-center justify-between gap-3">
              <div>
                <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-orange-200/75">
                  🦞 Local Import
                </p>
                <h2 className="mt-2 text-xl font-semibold text-slate-100">
                  {runtime?.binary_path ? "Existing OpenClaw detected" : "No local OpenClaw runtime reported"}
                </h2>
                <p className="mt-1 text-sm text-slate-300">
                  {runtime?.privacy_summary ??
                    "MUTX tracks OpenClaw under ~/.mutx/providers/openclaw without relocating the upstream home or uploading local keys."}
                </p>
              </div>
              <div className={`rounded-full border px-3 py-1 text-xs font-medium ${toneStyles(runtime?.keys_remain_local ? "good" : "info")}`}>
                {runtime?.keys_remain_local ? "keys stay local" : "local snapshot"}
              </div>
            </div>

            <div className="mt-4 grid gap-3 md:grid-cols-2">
              <div className="rounded-xl border px-4 py-3" style={{ borderColor: dashboardTokens.borderSubtle, backgroundColor: dashboardTokens.bgCanvas }}>
                <p className="text-xs uppercase tracking-[0.18em] text-slate-500">Binary</p>
                <p data-technical-value className="mt-2 font-mono text-xs text-slate-200">{runtime?.binary_path ?? "Not reported by operator host"}</p>
              </div>
              <div className="rounded-xl border px-4 py-3" style={{ borderColor: dashboardTokens.borderSubtle, backgroundColor: dashboardTokens.bgCanvas }}>
                <p className="text-xs uppercase tracking-[0.18em] text-slate-500">Tracking Mode</p>
                <p data-technical-value className="mt-2 font-mono text-xs text-slate-200">
                  {runtime?.tracking_mode ?? "import_existing_runtime"}
                  {runtime?.adopted_existing_runtime ? " · adopted" : ""}
                </p>
              </div>
            </div>
          </section>

          <section
            className="rounded-2xl border p-5"
            style={{
              borderColor: dashboardTokens.borderSubtle,
              backgroundColor: dashboardTokens.bgSurface,
            }}
          >
            <p className="text-[11px] font-semibold uppercase tracking-[0.2em]" style={{ color: dashboardTokens.textMuted }}>
              Runtime Snapshot
            </p>
            <div className="mt-4 grid gap-3 md:grid-cols-2">
              <div className="rounded-xl border p-4" style={{ borderColor: dashboardTokens.borderSubtle, backgroundColor: dashboardTokens.bgCanvas }}>
                <p className="text-xs text-slate-500">Gateway</p>
                <p className="mt-2 text-lg font-semibold text-slate-100">{runtime?.status ?? "unknown"}</p>
                <p className="mt-1 text-sm text-slate-400">{runtime?.gateway_url ?? "No gateway URL synced yet."}</p>
              </div>
              <div className="rounded-xl border p-4" style={{ borderColor: dashboardTokens.borderSubtle, backgroundColor: dashboardTokens.bgCanvas }}>
                <p className="text-xs text-slate-500">Observed</p>
                <p className="mt-2 text-lg font-semibold text-slate-100">{runtime?.stale ? "stale last-seen" : "fresh last-seen"}</p>
                <p className="mt-1 text-sm text-slate-400">last seen {formatTimestamp(runtime?.last_seen_at)}</p>
              </div>
              <div className="rounded-xl border p-4" style={{ borderColor: dashboardTokens.borderSubtle, backgroundColor: dashboardTokens.bgCanvas }}>
                <p className="text-xs text-slate-500">Install</p>
                <p className="mt-2 text-lg font-semibold text-slate-100">{runtime?.install_method ?? "n/a"}</p>
                <p className="mt-1 text-sm text-slate-400">
                  {runtime?.version ?? "Version not synced yet."}
                  {runtime?.last_action_type ? ` · ${runtime.last_action_type}` : ""}
                </p>
              </div>
              <div className="rounded-xl border p-4" style={{ borderColor: dashboardTokens.borderSubtle, backgroundColor: dashboardTokens.bgCanvas }}>
                <p className="text-xs text-slate-500">Binding</p>
                <p className="mt-2 text-lg font-semibold text-slate-100">{currentBinding?.assistant_id ?? "not bound"}</p>
                <p className="mt-1 text-sm text-slate-400">{currentBinding?.workspace ?? "Workspace not synced yet."}</p>
              </div>
            </div>
          </section>
        </div>

        <aside className="space-y-4">
          <section
            className="rounded-2xl border p-5"
            style={{
              borderColor: dashboardTokens.borderSubtle,
              backgroundColor: dashboardTokens.bgSurface,
            }}
          >
            <p className="text-[11px] font-semibold uppercase tracking-[0.2em]" style={{ color: dashboardTokens.textMuted }}>
              Continue Locally
            </p>
            <p className="mt-3 text-sm leading-6 text-slate-400">
              Local execution stays in the CLI or TUI. Use one of these commands on the operator host to continue or resync the tracked OpenClaw runtime.
            </p>
            <div className="mt-4 space-y-3">
              {commands.map((command) => (
                <button
                  key={command}
                  type="button"
                  className="flex w-full items-center justify-between rounded-xl border px-3 py-3 text-left"
                  style={{
                    borderColor: dashboardTokens.borderSubtle,
                    backgroundColor: dashboardTokens.bgCanvas,
                    color: dashboardTokens.textPrimary,
                  }}
                  onClick={() => void copyCommand(command)}
                >
                  <code className="text-xs text-slate-200">{command}</code>
                  <span className="ms-3 inline-flex items-center gap-2 text-xs text-slate-400">
                    {copiedCommand === command ? (
                      <>
                        <span className="text-emerald-300">Copied</span>
                        <Check className="h-4 w-4 text-emerald-300" />
                      </>
                    ) : (
                      <Copy className="h-4 w-4 text-slate-500" />
                    )}
                  </span>
                </button>
              ))}
            </div>
            {copyError ? (
              <p role="alert" aria-live="assertive" className="mt-3 text-xs text-rose-300">{copyError}</p>
            ) : null}
          </section>

          <section
            className="rounded-2xl border p-5"
            style={{
              borderColor: dashboardTokens.borderSubtle,
              backgroundColor: dashboardTokens.bgSurface,
            }}
          >
            <p className="text-[11px] font-semibold uppercase tracking-[0.2em]" style={{ color: dashboardTokens.textMuted }}>
              Tracked Paths
            </p>
            <div className="mt-3 space-y-3 text-sm text-slate-400">
              <div>
                <p className="text-xs text-slate-500">OpenClaw home</p>
                <p data-technical-value className="mt-1 break-all text-slate-200">{runtime?.home_path ?? "n/a"}</p>
              </div>
              <div>
                <p className="text-xs text-slate-500">Config</p>
                <p data-technical-value className="mt-1 break-all text-slate-200">{runtime?.config_path ?? "n/a"}</p>
              </div>
              <div>
                <p className="text-xs text-slate-500">Import source</p>
                <p data-technical-value className="mt-1 break-all text-slate-200">
                  {runtime?.import_source?.binary_path ?? onboarding?.import_source?.binary_path ?? "n/a"}
                </p>
              </div>
              <div>
                <p className="text-xs text-slate-500">Registry</p>
                <p className="mt-1 break-all text-slate-200">~/.mutx/providers/openclaw</p>
              </div>
            </div>
          </section>

          <section
            className="rounded-2xl border p-5"
            style={{
              borderColor: dashboardTokens.borderSubtle,
              backgroundColor: dashboardTokens.bgSurface,
            }}
          >
            <p className="text-[11px] font-semibold uppercase tracking-[0.2em]" style={{ color: dashboardTokens.textMuted }}>
              Read-only Web
            </p>
            <p className="mt-3 text-sm leading-6 text-slate-400">
              The web dashboard shows synced state only. Installing OpenClaw, onboarding the gateway, and binding assistants still happen in the MUTX CLI or TUI on the operator machine.
            </p>
            <a
              href="https://github.com/openclaw/openclaw"
              className="mt-4 inline-flex items-center gap-2 text-sm text-sky-300"
            >
              OpenClaw upstream
              <ExternalLink className="h-4 w-4" />
            </a>
          </section>

          {error ? (
            <div role="alert" aria-live="assertive" className={`rounded-2xl border p-4 text-sm ${toneStyles("bad")}`}>
              {error}
            </div>
          ) : null}
        </aside>
      </div>
    </section>
  );
}
