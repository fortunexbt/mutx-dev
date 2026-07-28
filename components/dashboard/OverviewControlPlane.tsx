"use client";

import Link from "next/link";
import type { LucideIcon } from "lucide-react";

import { cn } from "@/lib/utils";

type Tone = "good" | "warn" | "bad" | "info";
type IncidentLevel = "info" | "warning" | "error";

export interface OverviewSignal {
  label: string;
  value: string;
  tone: Tone;
}

export interface OverviewKpi {
  title: string;
  value: string;
  subtitle: string;
  detail?: string;
  tone: "gateway" | "blue" | "green" | "violet" | "slate";
  icon: LucideIcon;
}

export interface OverviewHealthRow {
  label: string;
  value: string;
  tone: Tone;
  bar?: number | null;
}

export interface OverviewRouterEntry {
  id: string;
  primary: string;
  secondary: string;
  statusLabel: string;
  statusTone: Tone;
  meta: string;
  ageLabel: string;
}

export interface OverviewIncident {
  id: string;
  title: string;
  detail: string;
  source: string;
  occurredAt: string;
  level: IncidentLevel;
}

export interface OverviewMetricRow {
  label: string;
  value: string;
  tone?: Tone;
}

interface ControlPlaneOverviewProps {
  title: string;
  subtitle: string;
  signals: OverviewSignal[];
  kpis: OverviewKpi[];
  healthRows: OverviewHealthRow[];
  routerEntries: OverviewRouterEntry[];
  incidents: OverviewIncident[];
  incidentsNote?: string | null;
  taskRows: OverviewMetricRow[];
  taskFootnote?: string;
  securityRows: OverviewMetricRow[];
  securityTag?: string;
  securityHref: string;
  securityHrefLabel: string;
}

function toneTextClass(tone: Tone) {
  if (tone === "good") return "text-emerald-300";
  if (tone === "warn") return "text-amber-300";
  if (tone === "bad") return "text-rose-300";
  return "text-slate-300";
}

function toneDotClass(tone: Tone) {
  if (tone === "good") return "bg-emerald-400";
  if (tone === "warn") return "bg-amber-400";
  if (tone === "bad") return "bg-rose-400";
  return "bg-slate-500";
}

function signalToneClass(tone: Tone) {
  if (tone === "good") return "border-emerald-400/20 bg-emerald-400/10 text-emerald-200";
  if (tone === "warn") return "border-amber-400/20 bg-amber-400/10 text-amber-200";
  if (tone === "bad") return "border-rose-400/20 bg-rose-400/10 text-rose-200";
  return "border-[#213252] bg-[#0d1a31] text-slate-200";
}

function incidentLevelClass(level: IncidentLevel) {
  if (level === "error") return "bg-rose-400";
  if (level === "warning") return "bg-amber-400";
  return "bg-cyan-400";
}

const KPI_TONE_CLASS: Record<OverviewKpi["tone"], string> = {
  gateway: "border-emerald-500/25 bg-emerald-500/10",
  blue: "border-sky-400/20 bg-sky-500/[0.08]",
  green: "border-emerald-400/20 bg-emerald-500/[0.08]",
  violet: "border-violet-400/20 bg-violet-500/[0.08]",
  slate: "border-[#203252] bg-[#0d1a31]",
};

function PanelFrame({
  title,
  meta,
  tag,
  className,
  children,
}: {
  title: string;
  meta?: string;
  tag?: string;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <section className={cn("overflow-hidden rounded-xl border border-[#1a2943] bg-[#060f21]", className)}>
      <header className="flex items-center justify-between border-b border-[#16263f] px-4 py-3">
        <h3 className="text-sm font-semibold text-slate-100">{title}</h3>
        {tag ? (
          <span className="rounded-md border border-amber-400/25 bg-amber-400/10 px-2 py-0.5 text-[10px] font-medium text-amber-200">
            {tag}
          </span>
        ) : (
          <span className="text-[10px] font-medium uppercase tracking-[0.16em] text-slate-500">{meta}</span>
        )}
      </header>
      <div className="p-4">{children}</div>
    </section>
  );
}

function EmptyPanelState({ title, description }: { title: string; description: string }) {
  return (
    <div className="rounded-lg border border-dashed border-[#203252] bg-[#07142a]/40 px-4 py-8 text-center">
      <p className="text-sm text-slate-300">{title}</p>
      <p className="mt-1 text-xs text-slate-500">{description}</p>
    </div>
  );
}

export function ControlPlaneOverview({
  title,
  subtitle,
  signals,
  kpis,
  healthRows,
  routerEntries,
  incidents,
  incidentsNote,
  taskRows,
  taskFootnote,
  securityRows,
  securityTag,
  securityHref,
  securityHrefLabel,
}: ControlPlaneOverviewProps) {
  return (
    <section className="space-y-3">
      <div className="rounded-xl border border-[#1a2943] bg-[#07132a] p-4 sm:p-5">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-500">Overview</p>
            <h1 className="mt-2 text-2xl font-semibold text-slate-100">{title}</h1>
            <p className="mt-1 text-sm text-slate-400">{subtitle}</p>
          </div>

          <div className="grid grid-cols-2 gap-2 sm:min-w-[240px]">
            {signals.map((signal) => (
              <div
                key={signal.label}
                className={cn("rounded-lg border px-2.5 py-2", signalToneClass(signal.tone))}
              >
                <p className="text-[10px] font-medium uppercase tracking-[0.16em] opacity-80">{signal.label}</p>
                <p className="mt-1 text-xs font-semibold">{signal.value}</p>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
        {kpis.map((kpi) => (
          <article
            key={kpi.title}
            className={cn("rounded-xl border p-4", KPI_TONE_CLASS[kpi.tone])}
          >
            <div className="flex items-start justify-between gap-2">
              <div>
                <p className="text-xs font-semibold text-slate-300">{kpi.title}</p>
                <p className="mt-2 font-mono text-3xl font-semibold leading-none text-slate-100">{kpi.value}</p>
              </div>
              <kpi.icon className="h-4 w-4 text-slate-500" />
            </div>
            <p className="mt-2 text-[11px] uppercase tracking-[0.14em] text-slate-500">{kpi.subtitle}</p>
            {kpi.detail ? <p className="mt-1 text-xs text-slate-400">{kpi.detail}</p> : null}
          </article>
        ))}
      </div>

      <div className="grid gap-3 xl:grid-cols-12">
        <PanelFrame title="Gateway Health + Golden Signals" className="xl:col-span-4">
          <div className="space-y-3">
            {healthRows.map((row) => (
              <div key={row.label} className="space-y-1">
                <div className="flex items-center justify-between gap-3">
                  <p className="text-xs text-slate-400">{row.label}</p>
                  <p className={cn("text-xs font-medium", toneTextClass(row.tone))}>{row.value}</p>
                </div>
                {typeof row.bar === "number" ? (
                  <div className="h-1 overflow-hidden rounded-full bg-[#111f36]">
                    <div
                      className={cn("h-full rounded-full", toneDotClass(row.tone))}
                      style={{ width: `${Math.max(0, Math.min(100, row.bar))}%` }}
                    />
                  </div>
                ) : null}
              </div>
            ))}
          </div>
        </PanelFrame>

        <PanelFrame title="Session Router" meta={String(routerEntries.length)} className="xl:col-span-4">
          {routerEntries.length === 0 ? (
            <EmptyPanelState
              title="No routable sessions yet"
              description="Deployments appear here once agents are running."
            />
          ) : (
            <div className="max-h-[268px] divide-y divide-[#152640] overflow-y-auto">
              {routerEntries.map((route) => (
                <div key={route.id} className="flex items-start gap-3 py-2.5 first:pt-0 last:pb-0">
                  <span className={cn("mt-1.5 h-2 w-2 shrink-0 rounded-full", toneDotClass(route.statusTone))} />
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-mono text-xs text-slate-100">{route.primary}</p>
                    <p className="truncate text-[11px] text-slate-500">{route.secondary}</p>
                  </div>
                  <div className="shrink-0 text-right">
                    <p className={cn("text-[11px] font-medium", toneTextClass(route.statusTone))}>{route.statusLabel}</p>
                    <p className="text-[10px] text-slate-500">{route.meta}</p>
                    <p className="text-[10px] text-slate-500">{route.ageLabel}</p>
                  </div>
                </div>
              ))}
            </div>
          )}
        </PanelFrame>

        <PanelFrame title="Incident Stream" meta={`${incidents.length} items`} className="xl:col-span-4">
          {incidentsNote ? (
            <div className="mb-3 rounded-md border border-[#24395c] bg-[#0d1a31] px-3 py-2 text-xs text-slate-300">
              {incidentsNote}
            </div>
          ) : null}

          {incidents.length === 0 ? (
            <EmptyPanelState
              title="No incidents yet"
              description="Gateway incidents and warnings stream here."
            />
          ) : (
            <div className="max-h-[268px] divide-y divide-[#152640] overflow-y-auto">
              {incidents.map((incident) => (
                <div key={incident.id} className="py-2.5 first:pt-0 last:pb-0">
                  <div className="flex items-start gap-2">
                    <span
                      className={cn("mt-1.5 h-2 w-2 shrink-0 rounded-full", incidentLevelClass(incident.level))}
                    />
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-xs font-medium text-slate-100">{incident.title}</p>
                      <p className="mt-0.5 line-clamp-2 text-[11px] text-slate-400">{incident.detail}</p>
                      <p className="mt-1 text-[10px] uppercase tracking-[0.12em] text-slate-500">
                        {incident.source} · {incident.occurredAt}
                      </p>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </PanelFrame>

        <PanelFrame title="Task Flow" className="xl:col-span-6">
          <div className="grid gap-2 sm:grid-cols-2">
            {taskRows.map((row) => (
              <div key={row.label} className="flex items-center justify-between rounded-md bg-[#0b1730]/60 px-3 py-2">
                <span className="text-xs text-slate-400">{row.label}</span>
                <span className={cn("text-xs font-medium", toneTextClass(row.tone ?? "info"))}>{row.value}</span>
              </div>
            ))}
          </div>
          {taskFootnote ? <p className="mt-3 text-xs text-slate-500">{taskFootnote}</p> : null}
        </PanelFrame>

        <PanelFrame title="Security + Audit" tag={securityTag} className="xl:col-span-6">
          <div className="space-y-2">
            {securityRows.map((row) => (
              <div key={row.label} className="flex items-center justify-between gap-3">
                <p className="text-xs text-slate-400">{row.label}</p>
                <p className={cn("text-xs font-medium", toneTextClass(row.tone ?? "info"))}>{row.value}</p>
              </div>
            ))}
          </div>
          <Link
            href={securityHref}
            className="mt-4 inline-flex items-center gap-1 text-xs font-medium text-cyan-300 transition hover:text-cyan-200"
          >
            {securityHrefLabel}
          </Link>
        </PanelFrame>
      </div>
    </section>
  );
}

export function ControlPlaneOverviewSkeleton() {
  return (
    <section className="space-y-3 motion-safe:animate-pulse motion-reduce:animate-none">
      <div className="h-28 rounded-xl border border-[#1a2943] bg-[#07132a]" />
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
        {Array.from({ length: 5 }).map((_, index) => (
          <div key={index} className="h-24 rounded-xl border border-[#1a2943] bg-[#060f21]" />
        ))}
      </div>
      <div className="grid gap-3 xl:grid-cols-12">
        <div className="h-64 rounded-xl border border-[#1a2943] bg-[#060f21] xl:col-span-4" />
        <div className="h-64 rounded-xl border border-[#1a2943] bg-[#060f21] xl:col-span-4" />
        <div className="h-64 rounded-xl border border-[#1a2943] bg-[#060f21] xl:col-span-4" />
        <div className="h-40 rounded-xl border border-[#1a2943] bg-[#060f21] xl:col-span-6" />
        <div className="h-40 rounded-xl border border-[#1a2943] bg-[#060f21] xl:col-span-6" />
      </div>
    </section>
  );
}
