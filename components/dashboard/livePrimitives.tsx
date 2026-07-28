import { createElement, useId } from "react";
import type {
  ButtonHTMLAttributes,
  HTMLAttributes,
  InputHTMLAttributes,
  ReactNode,
} from "react";
import type { LucideIcon } from "lucide-react";
import { AlertTriangle, Lock, Sparkles } from "lucide-react";
import Link from "next/link";

import { cn } from "@/lib/utils";

import { EmptyState } from "@/components/dashboard/EmptyState";
import { LoadingState } from "@/components/dashboard/LoadingState";
import { StatusBadge } from "@/components/dashboard/StatusBadge";
import { getDashboardAccessLinks } from "@/components/dashboard/dashboardAccess";
import { dashboardTokens } from "@/components/dashboard/tokens";
import type { DashboardStatus } from "@/components/dashboard/types";

export type SurfaceElement = "article" | "div" | "section";

export interface SurfaceProps extends HTMLAttributes<HTMLElement> {
  as?: SurfaceElement;
  inset?: boolean;
}

/** Carbon/bone container used by every live operator surface. */
export function Surface({
  as = "section",
  children,
  className,
  inset = false,
  style,
  ...props
}: SurfaceProps) {
  return createElement(
    as,
    {
      "data-dashboard-ui": "surface",
      ...props,
      className: cn("min-w-0 rounded-[6px] border", className),
      style: {
        borderColor: dashboardTokens.borderSubtle,
        backgroundColor: inset ? dashboardTokens.bgInset : dashboardTokens.bgSurface,
        boxShadow: dashboardTokens.shadowSm,
        ...style,
      },
    },
    children,
  );
}

export interface PanelProps extends SurfaceProps {
  title: string;
  meta?: string;
  action?: ReactNode;
}

/** Titled operational region. REC is intentionally reserved for RouteHeader. */
export function Panel({
  title,
  meta,
  action,
  className,
  children,
  ...props
}: PanelProps) {
  return (
    <Surface
      {...props}
      className={cn("dashboard-entry relative overflow-hidden", className)}
      data-dashboard-ui="panel"
    >
      <span
        className="absolute start-0 top-0 z-10 h-px w-16"
        style={{ backgroundColor: dashboardTokens.brand }}
        aria-hidden="true"
      />
      <header
        className="flex min-h-12 flex-wrap items-center justify-between gap-3 border-b px-4 py-3 sm:px-5"
        style={{
          borderColor: dashboardTokens.borderSubtle,
          backgroundColor: dashboardTokens.bgInset,
        }}
      >
        <div className="flex min-w-0 items-center gap-3">
          <span
            className="font-[family:var(--font-mono)] text-[11px] font-semibold uppercase tracking-[0.14em]"
            style={{ color: dashboardTokens.textLabel }}
            aria-hidden="true"
          >
            LOG
          </span>
          <span
            className="h-4 w-px"
            style={{ backgroundColor: dashboardTokens.borderStrong }}
            aria-hidden="true"
          />
          <h2
            className="min-w-0 break-words text-[13px] font-medium tracking-[-0.01em]"
            style={{ color: dashboardTokens.textPrimary }}
          >
            {title}
          </h2>
        </div>
        <div className="flex min-w-0 flex-wrap items-center justify-end gap-3">
          {meta ? (
            <span
              className="break-words border-s ps-3 font-[family:var(--font-mono)] text-[11px] font-medium uppercase tracking-[0.12em]"
              style={{ borderColor: dashboardTokens.borderStrong, color: dashboardTokens.textMuted }}
            >
              {meta}
            </span>
          ) : null}
          {action}
        </div>
      </header>
      <div className="min-w-0 p-4 sm:p-5">{children}</div>
    </Surface>
  );
}

export function RecordRow({ className, children, style, ...props }: HTMLAttributes<HTMLElement>) {
  return (
    <article
      data-dashboard-ui="record-row"
      className={cn(
        "min-w-0 rounded-[4px] border px-3 py-3 sm:px-4",
        className,
      )}
      style={{
        borderColor: dashboardTokens.borderSubtle,
        backgroundColor: dashboardTokens.bgInset,
        ...style,
      }}
      {...props}
    >
      {children}
    </article>
  );
}

export type ActionTone = "primary" | "secondary" | "danger";

const ACTION_TONES: Record<ActionTone, string> = {
  primary: "border-[#ff6a32] bg-[#ff571c] text-[#090a08] hover:bg-[#ff7545]",
  secondary: "border-[#48463e] bg-[#11120f] text-[#eee9dc] hover:border-[#777268]",
  danger: "border-[#66302e] bg-[#241312] text-[#ff9b96] hover:border-[#ff6d66]",
};

export interface ActionProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  tone?: ActionTone;
}

export function Action({ tone = "secondary", className, type = "button", ...props }: ActionProps) {
  return (
    <button
      {...props}
      type={type}
      data-dashboard-ui="action"
      className={cn(
        "inline-flex min-h-11 min-w-11 items-center justify-center gap-2 rounded-[4px] border px-3 text-[12px] font-semibold transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#58aaff] disabled:cursor-not-allowed disabled:opacity-50 motion-reduce:transition-none",
        ACTION_TONES[tone],
        className,
      )}
    />
  );
}

export interface FieldProps extends Omit<InputHTMLAttributes<HTMLInputElement>, "id"> {
  id?: string;
  label: string;
  hint?: string;
  error?: string;
}

export function Field({ id, label, hint, error, className, style, ...props }: FieldProps) {
  const generatedId = useId();
  const fieldId = id ?? generatedId;
  const descriptionId = hint || error ? `${fieldId}-description` : undefined;

  return (
    <label htmlFor={fieldId} className="block min-w-0" data-dashboard-ui="field">
      <span
        className="font-[family:var(--font-mono)] text-[11px] font-semibold uppercase tracking-[0.12em]"
        style={{ color: dashboardTokens.textSecondary }}
      >
        {label}
      </span>
      <input
        {...props}
        id={fieldId}
        aria-invalid={error ? true : props["aria-invalid"]}
        aria-describedby={descriptionId}
        className={cn(
          "mt-2 min-h-11 w-full min-w-0 rounded-[4px] border bg-[#0c0d0b] px-3 text-[13px] text-[#eee9dc] outline-none placeholder:text-[#8d867a] focus:border-[#58aaff]",
          className,
        )}
        style={{ borderColor: error ? dashboardTokens.danger : dashboardTokens.borderStrong, ...style }}
      />
      {descriptionId ? (
        <span
          id={descriptionId}
          className="mt-1.5 block text-[11px] leading-5"
          style={{ color: error ? dashboardTokens.danger : dashboardTokens.textMuted }}
        >
          {error ?? hint}
        </span>
      ) : null}
    </label>
  );
}

export function Badge({
  status = "idle",
  label,
  className,
}: {
  status?: DashboardStatus;
  label: string;
  className?: string;
}) {
  return <StatusBadge status={status} label={label} className={className} data-dashboard-ui="badge" />;
}

export type NoticeTone = "info" | "success" | "warning" | "danger";

export function Notice({
  tone = "info",
  title,
  children,
  className,
}: {
  tone?: NoticeTone;
  title: string;
  children?: ReactNode;
  className?: string;
}) {
  const tones = {
    info: [dashboardTokens.traceSoft, dashboardTokens.trace, dashboardTokens.trace],
    success: [dashboardTokens.successSoft, dashboardTokens.success, dashboardTokens.success],
    warning: [dashboardTokens.warnSoft, dashboardTokens.warn, dashboardTokens.warn],
    danger: [dashboardTokens.dangerSoft, dashboardTokens.danger, dashboardTokens.danger],
  } as const;
  const [backgroundColor, borderColor, color] = tones[tone];

  return (
    <div
      role={tone === "danger" ? "alert" : "status"}
      data-dashboard-ui="notice"
      className={cn("min-w-0 rounded-[4px] border px-4 py-3", className)}
      style={{ backgroundColor, borderColor }}
    >
      <p className="font-[family:var(--font-mono)] text-[11px] font-semibold uppercase tracking-[0.12em]" style={{ color }}>
        {title}
      </p>
      {children ? (
        <div className="mt-1.5 break-words text-[12px] leading-5" style={{ color: dashboardTokens.textSecondary }}>
          {children}
        </div>
      ) : null}
    </div>
  );
}

export function formatRelativeTime(value?: string | null) {
  if (!value) return "Not recorded";

  const then = new Date(value).getTime();
  if (Number.isNaN(then)) return "Invalid timestamp";

  const diffMs = then - Date.now();
  const minutes = Math.round(diffMs / 60000);
  const formatter = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });

  if (Math.abs(minutes) < 60) {
    return formatter.format(minutes, "minute");
  }

  const hours = Math.round(minutes / 60);
  if (Math.abs(hours) < 48) {
    return formatter.format(hours, "hour");
  }

  const days = Math.round(hours / 24);
  return formatter.format(days, "day");
}

export function formatDateTime(value?: string | null) {
  if (!value) return "N/A";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "Invalid timestamp";
  return parsed.toLocaleString();
}

export function formatCurrency(value?: number | null) {
  const safeValue = Number.isFinite(value ?? NaN) ? Number(value) : 0;
  return new Intl.NumberFormat(undefined, {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: safeValue < 100 ? 2 : 0,
  }).format(safeValue);
}

export function asDashboardStatus(value?: string | null): DashboardStatus {
  const normalized = (value ?? "").toLowerCase();

  if (
    normalized.includes("healthy") ||
    normalized.includes("success") ||
    normalized.includes("ready") ||
    normalized.includes("completed") ||
    normalized.includes("active")
  ) {
    return "success";
  }

  if (
    normalized.includes("running") ||
    normalized.includes("sync") ||
    normalized.includes("warm")
  ) {
    return "running";
  }

  if (
    normalized.includes("warn") ||
    normalized.includes("retry") ||
    normalized.includes("queued") ||
    normalized.includes("pending") ||
    normalized.includes("awaiting")
  ) {
    return "warning";
  }

  if (
    normalized.includes("fail") ||
    normalized.includes("error") ||
    normalized.includes("blocked") ||
    normalized.includes("denied")
  ) {
    return "error";
  }

  return "idle";
}

export function LivePanel({
  title,
  meta,
  action,
  className,
  children,
}: {
  title: string;
  meta?: string;
  action?: ReactNode;
  className?: string;
  children: ReactNode;
}) {
  return <Panel title={title} meta={meta} action={action} className={className}>{children}</Panel>;
}

export function LiveStatCard({
  label,
  value,
  detail,
  status,
}: {
  label: string;
  value: string;
  detail: string;
  status?: DashboardStatus;
}) {
  return (
    <article
      className="dashboard-entry relative overflow-hidden rounded-[4px] border p-4 sm:p-5"
      style={{
        borderColor: dashboardTokens.borderSubtle,
        background: dashboardTokens.panelGradientStrong,
        boxShadow: dashboardTokens.shadowSm,
      }}
    >
      <span className="absolute start-0 top-0 h-full w-px" style={{ backgroundColor: dashboardTokens.borderInteractive }} aria-hidden="true" />
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="font-[family:var(--font-mono)] text-[11px] font-semibold uppercase tracking-[0.14em]" style={{ color: dashboardTokens.textMuted }}>
            <span className="me-2 text-[#ff7545]" aria-hidden="true">SIG /</span>
            {label}
          </p>
          <p
            className="mt-3 truncate font-[family:var(--font-mono)] text-[2rem] font-medium leading-none tracking-[-0.055em] tabular-nums sm:text-[2.2rem]"
            style={{ color: dashboardTokens.textPrimary }}
          >
            {value}
          </p>
        </div>
        {status ? <StatusBadge status={status} /> : null}
      </div>
      <p className="mt-4 border-t pt-3 text-[11px] leading-5" style={{ borderColor: dashboardTokens.borderSubtle, color: dashboardTokens.textSubtle }}>
        {detail}
      </p>
    </article>
  );
}

export function LiveKpiGrid({ children }: { children: ReactNode }) {
  return <div className="grid gap-2.5 md:grid-cols-2 xl:grid-cols-4">{children}</div>;
}

export function LiveMiniStatGrid({
  children,
  columns = 2,
}: {
  children: ReactNode;
  columns?: 2 | 3;
}) {
  return <div className={cn("grid gap-2.5", columns === 3 ? "sm:grid-cols-3" : "sm:grid-cols-2")}>{children}</div>;
}

export function LiveMiniStat({
  label,
  value,
  detail,
  icon: Icon,
}: {
  label: string;
  value: string;
  detail?: string;
  icon?: LucideIcon;
}) {
  return (
    <div
      className="rounded-[4px] border p-4"
      style={{
        borderColor: dashboardTokens.borderSubtle,
        backgroundColor: dashboardTokens.bgInset,
      }}
    >
      <div className="flex items-center gap-2 font-[family:var(--font-mono)] text-[11px] font-semibold uppercase tracking-[0.12em]" style={{ color: dashboardTokens.textMuted }}>
        <span className="text-[#58aaff]" aria-hidden="true">CH /</span>
        {Icon ? <Icon className="h-3.5 w-3.5" aria-hidden="true" /> : null}
        <span>{label}</span>
      </div>
      <p className="mt-2 font-[family:var(--font-mono)] text-[13px] font-medium tabular-nums" style={{ color: dashboardTokens.textPrimary }}>
        {value}
      </p>
      {detail ? (
        <p className="mt-1 text-[11px] leading-5" style={{ color: dashboardTokens.textMuted }}>
          {detail}
        </p>
      ) : null}
    </div>
  );
}

export function LiveLoading({ title }: { title: string }) {
  return (
    <LivePanel title={title} meta="loading">
      <LoadingState variant="cards" count={3} />
    </LivePanel>
  );
}

export function LiveAuthRequired({
  title,
  message,
  nextPath = "/dashboard",
}: {
  title: string;
  message: string;
  nextPath?: string;
}) {
  const displayTitle = title.replace(/^Operator session/i, "Sign-in");
  const accessLinks = getDashboardAccessLinks(nextPath);

  return (
    <LivePanel title={title} meta="auth required">
      <div className="grid gap-8 lg:grid-cols-[minmax(0,1.2fr)_minmax(260px,0.8fr)] lg:items-center">
        <div className="flex items-start gap-4">
          <div
            className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[4px] border"
            style={{
              borderColor: dashboardTokens.borderStrong,
              backgroundColor: dashboardTokens.brandSoft,
              color: dashboardTokens.brand,
            }}
          >
            <Lock className="h-4 w-4" aria-hidden="true" />
          </div>
          <div className="min-w-0">
            <p className="font-[family:var(--font-mono)] text-[11px] font-semibold uppercase tracking-[0.14em]" style={{ color: dashboardTokens.textLabel }}>
              Access ledger / private workspace
            </p>
            <p className="mt-2 font-[family:var(--font-site-display)] text-2xl font-medium tracking-[-0.045em]" style={{ color: dashboardTokens.textPrimary }}>
              {displayTitle}
            </p>
            <p className="mt-2 max-w-xl text-[13px] leading-6" style={{ color: dashboardTokens.textSubtle }}>
              {message}
            </p>
            <div className="mt-5 flex flex-wrap gap-2">
              <Link
                href={accessLinks.login}
                className="inline-flex min-h-10 items-center justify-center rounded-[4px] border border-[#ff7545] bg-[#ff571c] px-4 text-xs font-semibold text-[#090a08] transition hover:bg-[#ff7545]"
              >
                Sign in
              </Link>
              <Link
                href={accessLinks.register}
                className="inline-flex min-h-10 items-center justify-center rounded-[4px] border border-[#48463e] bg-[#151612] px-4 text-xs font-semibold text-[#d8d1c4] transition hover:border-[#777268] hover:text-white"
              >
                Create account
              </Link>
              <Link
                href={accessLinks.recovery}
                className="inline-flex min-h-10 items-center justify-center px-2 text-xs font-semibold text-[#aaa397] underline decoration-[#59564d] underline-offset-4 transition-colors hover:text-[#eee9dc]"
              >
                Recover access
              </Link>
            </div>
          </div>
        </div>

        <ul className="border-s ps-5" style={{ borderColor: dashboardTokens.borderStrong }}>
          {[
            "Fleet health and current deployment state.",
            "Recent runs, alerts, and budget pressure.",
            "The permissions attached to your account.",
          ].map((note, index) => (
            <li
              key={note}
              className="flex items-start gap-3 border-b py-3 first:pt-0 last:border-0 last:pb-0"
              style={{ borderColor: dashboardTokens.borderSubtle }}
            >
              <span className="font-[family:var(--font-mono)] text-[9px] text-[#ff7545]">
                {String(index + 1).padStart(2, "0")}
              </span>
              <p className="text-[12px] leading-5" style={{ color: dashboardTokens.textSubtle }}>{note}</p>
            </li>
          ))}
        </ul>
      </div>
    </LivePanel>
  );
}

export function LiveForbidden({
  title = "Permission required",
  message = "Your signed-in account does not have permission to use this dashboard surface. Ask a workspace administrator to grant the required role.",
}: {
  title?: string;
  message?: string;
}) {
  return (
    <EmptyState
      role="alert"
      aria-live="assertive"
      title={title}
      message={message}
      icon={<Lock className="h-7 w-7" />}
      className="py-16"
      data-dashboard-access="forbidden"
    />
  );
}

export function LiveErrorState({
  title,
  message,
}: {
  title: string;
  message: string;
}) {
  return (
    <EmptyState
      role="alert"
      aria-live="assertive"
      title={title}
      message={message}
      icon={<AlertTriangle className="h-7 w-7" />}
      className="py-16"
    />
  );
}

export function LiveEmptyState({
  title,
  message,
}: {
  title: string;
  message: string;
}) {
  return (
    <EmptyState
      title={title}
      message={message}
      icon={<Sparkles className="h-7 w-7" />}
      className="py-16"
    />
  );
}

export type BriefingBarStatus = "healthy" | "degraded" | "critical" | "unknown";

export type BriefingBarEntry = {
  label: string;
  value: string;
  status: BriefingBarStatus;
};

export function SignalPill({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone: "success" | "warning" | "info";
}) {
  const toneStyles = {
    success: {
      backgroundColor: dashboardTokens.successSoft,
      borderColor: "var(--mutx-dashboard-status-success-border)",
      color: dashboardTokens.success,
    },
    warning: {
      backgroundColor: dashboardTokens.warnSoft,
      borderColor: "var(--mutx-dashboard-status-warning-border)",
      color: dashboardTokens.warn,
    },
    info: {
      backgroundColor: dashboardTokens.traceSoft,
      borderColor: "var(--mutx-dashboard-status-running-border)",
      color: dashboardTokens.trace,
    },
  };

  return (
    <div className="rounded-[4px] border px-2.5 py-2" style={toneStyles[tone]}>
      <div className="font-[family:var(--font-mono)] text-[11px] font-semibold uppercase tracking-[0.12em] opacity-80">
        SIG / {label}
      </div>
      <div className="mt-0.5 truncate font-[family:var(--font-mono)] text-[11px] font-semibold tabular-nums">
        {value}
      </div>
    </div>
  );
}

export function BriefingBar({ entries }: { entries: BriefingBarEntry[] }) {
  const statusColors: Record<BriefingBarStatus, string> = {
    healthy: dashboardTokens.success,
    degraded: dashboardTokens.warn,
    critical: dashboardTokens.danger,
    unknown: dashboardTokens.textMuted,
  };

  return (
    <div
      className="flex items-center gap-4 overflow-x-auto border-y px-1 py-3"
      style={{
        borderColor: dashboardTokens.borderSubtle,
        backgroundColor: "transparent",
      }}
    >
      {entries.map((entry, index) => (
        <div key={entry.label} className="flex items-center gap-2 shrink-0">
          {index > 0 && (
            <div
              className="h-4 w-px"
              style={{ backgroundColor: dashboardTokens.borderSubtle }}
            />
          )}
          <div
            className={cn(
              "h-1.5 w-1.5 rounded-full",
              entry.status === "healthy" && "dashboard-live-dot",
            )}
            style={{ backgroundColor: statusColors[entry.status] }}
            aria-hidden="true"
          />
          <span
            className="font-[family:var(--font-mono)] text-[11px] font-semibold uppercase tracking-[0.12em]"
            style={{ color: dashboardTokens.textMuted }}
          >
            {entry.label}
          </span>
          <span
            className="font-[family:var(--font-mono)] text-[10px] font-semibold tabular-nums"
            style={{ color: statusColors[entry.status] }}
          >
            {entry.value}
          </span>
        </div>
      ))}
    </div>
  );
}

export type RunFlowStatus = "pending" | "running" | "completed" | "failed" | "awaiting_owner";

export interface QueueDepthEntry {
  status: RunFlowStatus;
  count: number;
  label: string;
}

export interface FlowStage {
  status: RunFlowStatus;
  count: number;
  maxCount: number;
}

export function QueueDepthBar({ entries }: { entries: QueueDepthEntry[] }) {
  const statusConfig: Record<RunFlowStatus, { color: string }> = {
    pending: { color: dashboardTokens.textMuted },
    running: { color: dashboardTokens.trace },
    completed: { color: dashboardTokens.success },
    failed: { color: dashboardTokens.danger },
    awaiting_owner: { color: dashboardTokens.warn },
  };

  const total = entries.reduce((sum, e) => sum + e.count, 0);

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between gap-3">
        <span className="font-[family:var(--font-mono)] text-[11px] font-semibold uppercase tracking-[0.12em]" style={{ color: dashboardTokens.textMuted }}>
          Queue depth
        </span>
        <span className="font-[family:var(--font-mono)] text-[10px] font-semibold tabular-nums" style={{ color: dashboardTokens.textPrimary }}>
          {total} total
        </span>
      </div>
      <div className="flex h-1.5 overflow-hidden rounded-[4px]" style={{ backgroundColor: dashboardTokens.bgSurfaceHigher }}>
        {entries.map((entry) => {
          if (entry.count === 0) return null;
          const width = total > 0 ? (entry.count / total) * 100 : 0;
          return (
            <div
              key={entry.status}
              className="h-full transition-[width]"
              style={{ backgroundColor: statusConfig[entry.status].color, width: `${width}%` }}
            />
          );
        })}
      </div>
      <div className="flex flex-wrap gap-3">
        {entries.map((entry) => (
          <div key={entry.status} className="flex items-center gap-1.5">
            <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: statusConfig[entry.status].color }} aria-hidden="true" />
            <span className="font-[family:var(--font-mono)] text-[9px] tabular-nums" style={{ color: statusConfig[entry.status].color }}>
              {entry.label}: {entry.count}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

export function FlowStatusBar({ stages }: { stages: FlowStage[] }) {
  const stageConfig: Record<RunFlowStatus, { color: string; soft: string; label: string }> = {
    pending: {
      color: dashboardTokens.textMuted,
      soft: dashboardTokens.bgSurfaceHigher,
      label: "Pending",
    },
    running: {
      color: dashboardTokens.trace,
      soft: dashboardTokens.traceSoft,
      label: "Running",
    },
    completed: {
      color: dashboardTokens.success,
      soft: dashboardTokens.successSoft,
      label: "Completed",
    },
    failed: {
      color: dashboardTokens.danger,
      soft: dashboardTokens.dangerSoft,
      label: "Failed",
    },
    awaiting_owner: {
      color: dashboardTokens.warn,
      soft: dashboardTokens.warnSoft,
      label: "Awaiting Owner",
    },
  };

  return (
    <div className="flex items-center overflow-x-auto pb-1">
      {stages.map((stage, index) => {
        const config = stageConfig[stage.status];
        const isActive = stage.count > 0;
        return (
          <div key={stage.status} className="flex items-center">
            {index > 0 && (
              <div
                className="h-px w-4 transition-colors"
                style={{
                  backgroundColor:
                    stages[index - 1].count > 0
                      ? dashboardTokens.trace
                      : dashboardTokens.borderStrong,
                }}
              />
            )}
            <div
              className="flex shrink-0 items-center gap-1.5 rounded-[4px] border px-2.5 py-1.5 transition-colors"
              style={{
                backgroundColor: isActive ? config.soft : dashboardTokens.bgInset,
                borderColor: isActive ? config.color : dashboardTokens.borderSubtle,
                color: isActive ? config.color : dashboardTokens.textMuted,
              }}
            >
              <span
                className={cn("h-1.5 w-1.5 rounded-full", isActive && stage.status === "running" && "dashboard-live-dot")}
                style={{ backgroundColor: isActive ? config.color : dashboardTokens.borderStrong }}
                aria-hidden="true"
              />
              <span className="font-[family:var(--font-mono)] text-[11px] font-medium uppercase tracking-[0.1em]">
                {config.label}
              </span>
              <span className="font-[family:var(--font-mono)] text-[9px] font-semibold tabular-nums">
                {stage.count}
              </span>
            </div>
          </div>
        );
      })}
    </div>
  );
}

export interface CapacityIndicatorProps {
  used: number;
  max: number;
  label?: string;
}

export function CapacityIndicator({ used, max, label }: CapacityIndicatorProps) {
  const percentage = max > 0 ? Math.min((used / max) * 100, 100) : 0;
  const isOverCapacity = used > max;
  const isNearCapacity = percentage >= 80 && !isOverCapacity;

  const barColor = isOverCapacity
    ? dashboardTokens.danger
    : isNearCapacity
      ? dashboardTokens.warn
      : dashboardTokens.success;

  return (
    <div className="space-y-1.5">
      {label && (
        <div className="flex items-center justify-between gap-3">
          <span className="font-[family:var(--font-mono)] text-[11px] font-semibold uppercase tracking-[0.12em]" style={{ color: dashboardTokens.textMuted }}>
            {label}
          </span>
          <span
            className="font-[family:var(--font-mono)] text-[9px] font-semibold tabular-nums"
            style={{ color: isOverCapacity ? dashboardTokens.danger : isNearCapacity ? dashboardTokens.warn : dashboardTokens.textSecondary }}
          >
            {used}/{max}
          </span>
        </div>
      )}
      <div className="h-1.5 overflow-hidden rounded-[4px]" style={{ backgroundColor: dashboardTokens.bgSurfaceHigher }}>
        <div
          className="h-full rounded-[4px] transition-[width]"
          style={{ backgroundColor: barColor, width: `${percentage}%` }}
        />
      </div>
    </div>
  );
}

export { DashboardDialog as Dialog } from "@/components/dashboard/DashboardDialog";
export { LiveEmptyState as Empty, LiveErrorState as Error, LiveLoading as Loading };
