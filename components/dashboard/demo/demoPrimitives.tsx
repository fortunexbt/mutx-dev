import Link from "next/link";
import { useId, useMemo, useState, type ReactNode } from "react";
import type { LucideIcon } from "lucide-react";
import {
  Activity,
  AlertTriangle,
  ArrowUpRight,
  CheckCircle2,
  Clock3,
  Search,
  ShieldAlert,
} from "lucide-react";

import { dashboardTokens } from "@/components/dashboard/tokens";
import { cn } from "@/lib/utils";

import type {
  AgentCard,
  ConnectorCard,
  DeploymentRow,
  MatrixRow,
  Metric,
  QuickAction,
  Tone,
} from "@/components/dashboard/demo/demoContent";
import {
  NAV_ITEMS,
  SECTION_META,
  buildArea,
  buildPath,
  toneBadgeClasses,
  toneDotClasses,
  toneTextClasses,
} from "@/components/dashboard/demo/demoContent";

const PANEL_CHROME =
  "relative overflow-hidden rounded-[6px] border border-[#2b2b26] bg-[#11120f] shadow-[0_1px_0_rgba(255,255,255,0.025)]";
const FOCUS_RING =
  "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#ff9a72]";

export function SectionPill({ label, tone = "neutral" }: { label: string; tone?: Tone }) {
  return (
    <span
      className={cn(
        "inline-flex min-h-7 items-center rounded-[3px] border px-2 py-1 font-[family:var(--font-mono)] text-[11px] font-semibold uppercase tracking-[0.12em]",
        toneBadgeClasses(tone),
      )}
    >
      {label}
    </span>
  );
}

export function StatusBadge({ label, tone }: { label: string; tone: Tone }) {
  return (
    <span
      className={cn(
        "inline-flex min-h-6 items-center gap-1.5 rounded-[3px] border px-2 py-0.5 font-[family:var(--font-mono)] text-[11px] font-semibold uppercase tracking-[0.1em]",
        toneBadgeClasses(tone),
      )}
    >
      <span className={cn("h-1.5 w-1.5 rounded-full", toneDotClasses(tone))} aria-hidden="true" />
      {label}
    </span>
  );
}

export function SurfacePanel({
  title,
  meta,
  action,
  className,
  bodyClassName,
  children,
}: {
  title: string;
  meta?: string;
  action?: ReactNode;
  className?: string;
  bodyClassName?: string;
  children: ReactNode;
}) {
  return (
    <section className={cn(PANEL_CHROME, "flex h-auto min-h-0 flex-col", className)}>
      <span className="absolute start-0 top-0 h-px w-16 bg-[#ff571c]" aria-hidden="true" />
      <div className="flex min-h-12 shrink-0 items-center justify-between gap-3 border-b border-[#2b2b26] bg-[#0c0d0b] px-3.5 py-2.5">
        <div className="flex min-w-0 items-center gap-2.5">
          <span className="hidden font-[family:var(--font-mono)] text-[11px] font-semibold uppercase tracking-[0.12em] text-[#ff6a32] sm:inline" aria-hidden="true">
            REC
          </span>
          <h2 className="truncate text-[13px] font-semibold tracking-[-0.01em] text-[#eee9dc]">
            {title}
          </h2>
        </div>
        <div className="flex items-center gap-2">
          {meta ? (
            <span className="hidden border-s border-[#3b3a33] ps-2.5 font-[family:var(--font-mono)] text-[11px] font-medium uppercase tracking-[0.1em] text-[#8d867a] sm:inline">
              {meta}
            </span>
          ) : null}
          {action}
        </div>
      </div>
      <div className={cn("min-h-0 flex-1 overflow-visible p-3 lg:overflow-hidden", bodyClassName)}>
        {children}
      </div>
    </section>
  );
}

export function MetricCard({ metric }: { metric: Metric }) {
  return (
    <div className="relative flex min-h-[92px] min-w-0 flex-col justify-between overflow-hidden rounded-[4px] border border-[#34342e] bg-[#11120f] px-3 py-3">
      <span className="absolute start-0 top-0 h-full w-px bg-[#ff571c]" aria-hidden="true" />
      <div className="font-[family:var(--font-mono)] text-[11px] font-semibold uppercase tracking-[0.12em] text-[#8d867a]">
        {metric.label}
      </div>
      <div className="mt-3 font-[family:var(--font-mono)] text-[1.75rem] font-medium leading-none tracking-[-0.055em] text-[#eee9dc]">
        {metric.value}
      </div>
      <div className={cn("mt-2 text-[11px] font-medium", toneTextClasses(metric.tone ?? "neutral"))}>
        {metric.meta}
      </div>
    </div>
  );
}

export function OverviewCounter({ metric }: { metric: Metric }) {
  return (
    <div className="flex h-full min-w-0 flex-col justify-between rounded-[4px] border border-[#34342e] bg-[#0c0d0b] px-3 py-3">
      <div className="font-[family:var(--font-mono)] text-[11px] font-semibold uppercase tracking-[0.12em] text-[#8d867a]">
        {metric.label}
      </div>
      <div className="font-[family:var(--font-mono)] text-[1.45rem] font-medium leading-none tracking-[-0.04em] text-[#eee9dc]">
        {metric.value}
      </div>
      <div className={cn("text-[11px] font-medium", toneTextClasses(metric.tone ?? "neutral"))}>
        {metric.meta}
      </div>
    </div>
  );
}

export function TopControl({
  label,
  icon: Icon,
  compact,
}: {
  label: string;
  icon?: LucideIcon;
  compact?: boolean;
}) {
  return (
    <div
      aria-label={`${label}. Fixed value in this simulated demo.`}
      title="Fixed value in this simulated demo"
      className={cn(
        "inline-flex items-center gap-2 rounded-[4px] border border-[#34342e] bg-[#11120f] text-[12px] text-[#c8c0b0]",
        compact ? "h-10 px-3" : "h-11 px-3.5",
      )}
    >
      {Icon ? <Icon className="h-3.5 w-3.5 text-[#8d867a]" aria-hidden="true" /> : null}
      <span className="whitespace-nowrap">{label}</span>
      <span className="font-[family:var(--font-mono)] text-[11px] uppercase tracking-[0.1em] text-[#737067]">
        fixed
      </span>
    </div>
  );
}

export function SearchBar() {
  const [query, setQuery] = useState("");
  const resultsId = useId();
  const resultsLabelId = useId();
  const hintId = useId();
  const normalizedQuery = query.trim().toLowerCase();
  const matches = useMemo(() => {
    if (!normalizedQuery) {
      return [];
    }

    return NAV_ITEMS.filter((item) => {
      const meta = SECTION_META[item.key];
      return [item.label, meta.eyebrow, meta.title, meta.detail]
        .join(" ")
        .toLowerCase()
        .includes(normalizedQuery);
    });
  }, [normalizedQuery]);

  return (
    <div className="relative flex h-11 min-w-0 flex-1 items-center gap-2.5 rounded-[4px] border border-[#3b3a33] bg-[#0c0d0b] px-3 focus-within:border-[#ff6a32] focus-within:outline focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-[#ff9a72]">
      <Search className="h-4 w-4 shrink-0 text-[#8d867a]" aria-hidden="true" />
      <input
        type="search"
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Escape") {
            setQuery("");
            event.currentTarget.blur();
          }
        }}
        placeholder="Find a demo surface..."
        aria-label="Search simulated control plane"
        aria-describedby={hintId}
        aria-controls={normalizedQuery ? resultsId : undefined}
        role="searchbox"
        className="min-w-0 flex-1 bg-transparent text-sm text-[#eee9dc] outline-none placeholder:text-[#737067]"
      />
      <span id={hintId} className="sr-only">
        Search sample routes only. Results stay inside the simulated control demo. Press Escape to clear.
      </span>
      <kbd className="hidden rounded-[3px] border border-[#3b3a33] bg-[#090a08] px-1.5 py-0.5 font-[family:var(--font-mono)] text-[11px] text-[#8d867a] sm:inline">
        /
      </kbd>
      {normalizedQuery ? (
        <div
          id={resultsId}
          role="region"
          data-testid="control-demo-search-results"
          aria-labelledby={resultsLabelId}
          className="absolute inset-x-0 top-[calc(100%+6px)] z-50 overflow-hidden rounded-[4px] border border-[#48463e] bg-[#0c0d0b] p-1.5 shadow-[0_20px_48px_rgba(0,0,0,0.52)]"
        >
          <div id={resultsLabelId} className="px-2 py-1.5 font-[family:var(--font-mono)] text-[11px] font-semibold uppercase tracking-[0.12em] text-[#ff8355]">
            Sample routes · no live data
          </div>
          <p className="sr-only" role="status" aria-live="polite">
            {matches.length} simulated control plane {matches.length === 1 ? "result" : "results"}.
          </p>
          {matches.length > 0 ? (
            <div className="mt-1 grid gap-1">
              {matches.map((item) => (
                <Link
                  key={item.key}
                  href={item.href}
                  onClick={() => setQuery("")}
                  className={cn(
                    "flex min-h-11 items-center justify-between gap-3 rounded-[3px] border border-transparent px-3 py-2 text-start text-[#c8c0b0] hover:border-[#34342e] hover:bg-[#151612] hover:text-[#eee9dc]",
                    FOCUS_RING,
                  )}
                >
                  <span className="text-sm font-semibold">{item.label}</span>
                  <span className="font-[family:var(--font-mono)] text-[11px] font-semibold uppercase tracking-[0.1em] text-[#8d867a]">
                    {SECTION_META[item.key].eyebrow}
                  </span>
                </Link>
              ))}
            </div>
          ) : (
            <div className="px-2 py-3 text-sm text-[#999284]">No sample route matches “{query.trim()}”.</div>
          )}
        </div>
      ) : null}
    </div>
  );
}

export function SignalToneIcon({ tone }: { tone: Tone }) {
  if (tone === "healthy") {
    return <CheckCircle2 className="h-4 w-4 shrink-0 text-[#4bd69b]" aria-hidden="true" />;
  }

  if (tone === "warning") {
    return <AlertTriangle className="h-4 w-4 shrink-0 text-[#efb654]" aria-hidden="true" />;
  }

  if (tone === "critical") {
    return <ShieldAlert className="h-4 w-4 shrink-0 text-[#ff6d66]" aria-hidden="true" />;
  }

  if (tone === "focus") {
    return <Activity className="h-4 w-4 shrink-0 text-[#58aaff]" aria-hidden="true" />;
  }

  return <Clock3 className="h-4 w-4 shrink-0 text-[#8d867a]" aria-hidden="true" />;
}

export function QuickActionButton({
  action,
  active,
}: {
  action: QuickAction;
  active: boolean;
}) {
  const [simulated, setSimulated] = useState(false);
  const statusId = useId();

  return (
    <div>
      <button
        type="button"
        onClick={() => setSimulated(true)}
        aria-describedby={statusId}
        className={cn(
          "group flex min-h-11 w-full items-center justify-between rounded-[4px] border px-3 py-2 text-start",
          FOCUS_RING,
          active || simulated
            ? "border-[#ff6a32] bg-[#28140d] text-[#eee9dc]"
            : "border-[#34342e] bg-[#11120f] text-[#c8c0b0] hover:border-[#5a3a2d] hover:bg-[#151612] hover:text-[#eee9dc]",
        )}
      >
        <div className="min-w-0">
          <div className="truncate text-[13px] font-semibold">{action.label}</div>
          <div className="truncate font-[family:var(--font-mono)] text-[11px] uppercase tracking-[0.1em] text-[#999284]">
            {simulated ? "Simulated locally" : `${action.detail} · demo only`}
          </div>
        </div>
        <ArrowUpRight className="h-4 w-4 shrink-0 text-[#ff6a32]" aria-hidden="true" />
      </button>
      <span id={statusId} data-testid="control-demo-action-status" className="sr-only" aria-live="polite">
        {simulated
          ? `${action.label} simulated locally. No live system was changed.`
          : `${action.label} changes only this simulated demo.`}
      </span>
    </div>
  );
}

export function Sparkline({
  points,
  strokeClassName = "stroke-[#ff6a32]",
  fillClassName = "fill-[#ff571c]/10",
}: {
  points: number[];
  strokeClassName?: string;
  fillClassName?: string;
}) {
  const linePath = buildPath(points, 420, 132);
  const areaPath = buildArea(points, 420, 132);

  return (
    <svg viewBox="0 0 420 132" className="h-full w-full" aria-hidden="true">
      <path d={areaPath} className={fillClassName} />
      {[24, 66, 108].map((y) => (
        <path key={y} d={`M 0 ${y} L 420 ${y}`} className="stroke-[#2b2b26] stroke-[1]" />
      ))}
      <path d={linePath} className={cn("fill-none stroke-[2]", strokeClassName)} />
    </svg>
  );
}

export function ProgressRow({
  label,
  value,
  tone = "focus",
}: {
  label: string;
  value: number;
  tone?: Tone;
}) {
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between gap-3 text-[13px]">
        <span className="text-[#aaa397]">{label}</span>
        <span className={cn("font-[family:var(--font-mono)] font-semibold", toneTextClasses(tone))}>
          {value}%
        </span>
      </div>
      <div className="h-2 overflow-hidden rounded-[2px] bg-[#252620]">
        <div
          className={cn(
            "h-2 rounded-[2px]",
            tone === "healthy"
              ? "bg-[#4bd69b]"
              : tone === "warning"
                ? "bg-[#efb654]"
                : tone === "critical"
                  ? "bg-[#ff6d66]"
                  : "bg-[#58aaff]",
          )}
          style={{ width: `${value}%` }}
        />
      </div>
    </div>
  );
}

export function EnvironmentMatrix({
  rows,
  showMeta = false,
}: {
  rows: MatrixRow[];
  showMeta?: boolean;
}) {
  return (
    <div className="h-full min-h-0 overflow-x-auto overflow-y-hidden">
      <div className="min-w-[720px] overflow-hidden rounded-[4px] border border-[#34342e] bg-[#0c0d0b]">
        <div className="grid grid-cols-[140px_repeat(3,minmax(0,1fr))] border-b border-[#34342e] bg-[#151612]">
          <div className="h-10 border-e border-[#34342e]" />
          {["Production", "Staging", "Development"].map((column) => (
            <div
              key={column}
              className="flex h-10 items-center border-e border-[#34342e] px-3 font-[family:var(--font-mono)] text-[11px] font-semibold uppercase tracking-[0.11em] text-[#c8c0b0] last:border-e-0"
            >
              {column}
            </div>
          ))}
        </div>
        <div className="grid grid-rows-6">
          {rows.map((row) => (
            <div
              key={row.label}
              className="grid min-h-[56px] grid-cols-[140px_repeat(3,minmax(0,1fr))] border-b border-[#292a25] bg-[#0c0d0b] last:border-b-0"
            >
              <div className="flex flex-col justify-center border-e border-[#34342e] px-3 py-2">
                <div className="truncate text-[11px] font-semibold uppercase tracking-[0.1em] text-[#eee9dc]">{row.label}</div>
                {showMeta ? (
                  <div className="truncate text-[11px] text-[#8d867a]">{row.meta}</div>
                ) : null}
              </div>
              {row.cells.map((cell, index) => (
                <div
                  key={`${row.label}-${index}`}
                  className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-2 border-e border-[#34342e] px-3 py-2 last:border-e-0"
                >
                  <div className="min-w-0">
                    <div className="truncate text-[12px] font-semibold text-[#eee9dc]">{cell.value}</div>
                    <div className="truncate text-[11px] text-[#999284]">{cell.detail}</div>
                  </div>
                  <div className="flex flex-col items-end gap-1">
                    <StatusBadge label={cell.badge} tone={cell.tone} />
                    <div className="font-[family:var(--font-mono)] text-[11px] text-[#737067]">{cell.stamp}</div>
                  </div>
                </div>
              ))}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export function EnvironmentCardsMobile({ rows }: { rows: MatrixRow[] }) {
  const environments = ["Production", "Staging", "Development"];

  return (
    <div className="grid gap-2 md:hidden">
      {environments.map((environment, envIndex) => (
        <div key={environment} className={cn(PANEL_CHROME, "overflow-hidden")}>
          <div className="flex min-h-11 items-center justify-between border-b border-[#34342e] bg-[#0c0d0b] px-3 py-2">
            <div className="font-[family:var(--font-mono)] text-[11px] font-semibold uppercase tracking-[0.11em] text-[#eee9dc]">
              {environment}
            </div>
            <span className="rounded-[3px] border border-[#34342e] px-2 py-1 font-[family:var(--font-mono)] text-[11px] uppercase tracking-[0.1em] text-[#8d867a]">
              snapshot
            </span>
          </div>
          <div>
            {rows.slice(0, 5).map((row) => {
              const cell = row.cells[envIndex];

              return (
                <div
                  key={`${environment}-${row.label}`}
                  className="grid grid-cols-[minmax(0,0.8fr)_minmax(0,1.2fr)] gap-3 border-b border-[#292a25] px-3 py-3 last:border-b-0"
                >
                  <div className="min-w-0">
                    <div className="text-[11px] font-semibold uppercase tracking-[0.1em] text-[#999284]">{row.label}</div>
                    <div className="mt-1 text-[11px] leading-4 text-[#8d867a]">{row.meta}</div>
                  </div>
                  <div className="min-w-0">
                    <div className="text-[12px] font-semibold text-[#eee9dc]">{cell.value}</div>
                    <div className="mt-1 text-[11px] leading-4 text-[#999284]">{cell.detail}</div>
                    <div className="mt-2 flex flex-wrap items-center gap-2">
                      <StatusBadge label={cell.badge} tone={cell.tone} />
                      <span className="font-[family:var(--font-mono)] text-[11px] text-[#737067]">{cell.stamp}</span>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}

export function DeploymentsTable({ rows }: { rows: DeploymentRow[] }) {
  return (
    <div className="flex h-full min-h-0 flex-col overflow-x-auto overflow-y-hidden">
      <div className="min-w-[780px]">
        <div className="grid min-h-11 shrink-0 grid-cols-[1.45fr_0.88fr_0.88fr_0.72fr_0.72fr_0.86fr_0.72fr] items-center border-b border-[#34342e] bg-[#0c0d0b] px-4 font-[family:var(--font-mono)] text-[11px] font-semibold uppercase tracking-[0.1em] text-[#8d867a]">
          {["Agent", "Runtime", "Environment", "Version", "Region", "Health", "Rollout"].map((heading) => (
            <div key={heading}>{heading}</div>
          ))}
        </div>
        <div className="min-h-0 flex-1 overflow-auto overscroll-contain">
          {rows.map((row) => (
            <div
              key={`${row.agent}-${row.version}`}
              className="grid min-h-[52px] grid-cols-[1.45fr_0.88fr_0.88fr_0.72fr_0.72fr_0.86fr_0.72fr] items-center border-b border-[#292a25] px-4 text-[12px] hover:bg-[#151612] last:border-b-0"
            >
              <div className="truncate font-semibold text-[#eee9dc]">{row.agent}</div>
              <div className="truncate text-[#aaa397]">{row.runtime}</div>
              <div className="truncate text-[#aaa397]">{row.environment}</div>
              <div className="truncate text-[#aaa397]">{row.version}</div>
              <div className="truncate text-[#aaa397]">{row.region}</div>
              <div className="truncate">
                <StatusBadge label={row.health} tone={row.tone} />
              </div>
              <div className="truncate font-[family:var(--font-mono)] text-[11px] text-[#8d867a]">{row.rollout}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export function RecordStack({
  items,
}: {
  items: Array<{ title: string; detail: string; meta: string; tone: Tone }>;
}) {
  return (
    <div className="flex h-full min-h-0 flex-col gap-2 overflow-visible lg:overflow-auto lg:overscroll-contain">
      {items.map((item) => (
        <div
          key={item.title}
          className="relative overflow-hidden rounded-[4px] border border-[#34342e] bg-[#0c0d0b] p-3"
        >
          <div
            className={cn(
              "absolute inset-y-0 start-0 w-[2px]",
              item.tone === "healthy"
                ? "bg-[#4bd69b]"
                : item.tone === "warning"
                  ? "bg-[#efb654]"
                  : item.tone === "critical"
                    ? "bg-[#ff6d66]"
                    : item.tone === "focus"
                      ? "bg-[#58aaff]"
                      : "bg-[#77766d]",
            )}
            aria-hidden="true"
          />
          <div className="flex items-start gap-2.5">
            <span className={cn("mt-1.5 h-2 w-2 shrink-0 rounded-full", toneDotClasses(item.tone))} aria-hidden="true" />
            <div className="min-w-0">
              <div className="text-[14px] font-semibold text-[#eee9dc]">{item.title}</div>
              <div className="mt-1 text-[12px] leading-5 text-[#aaa397]">{item.detail}</div>
              <div className={cn("mt-2 font-[family:var(--font-mono)] text-[11px] font-semibold uppercase tracking-[0.1em]", toneTextClasses(item.tone))}>
                {item.meta}
              </div>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

export function ConnectorGrid({ connectors }: { connectors: ConnectorCard[] }) {
  return (
    <div className="grid h-full min-h-0 grid-cols-1 gap-2 sm:grid-cols-2">
      {connectors.map((connector) => (
        <div
          key={connector.name}
          className="relative flex min-h-0 flex-col justify-between overflow-hidden rounded-[4px] border border-[#34342e] bg-[#0c0d0b] p-3"
        >
          <span className="absolute start-0 top-0 h-px w-12 bg-[#ff571c]" aria-hidden="true" />
          <div>
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="text-[15px] font-semibold text-[#eee9dc]">{connector.name}</div>
                <div className="mt-1 font-[family:var(--font-mono)] text-[11px] uppercase tracking-[0.1em] text-[#8d867a]">
                  integration contract
                </div>
              </div>
              <StatusBadge label={connector.status} tone={connector.tone} />
            </div>
            <div className="mt-3 text-[12px] leading-5 text-[#aaa397]">{connector.detail}</div>
          </div>
          <div className="mt-4 w-fit border-s border-[#48463e] ps-2 font-[family:var(--font-mono)] text-[11px] uppercase tracking-[0.1em] text-[#8d867a]">
            {connector.stamp}
          </div>
        </div>
      ))}
    </div>
  );
}

export function AgentRegistryCard({ card }: { card: AgentCard }) {
  return (
    <div className="relative flex min-h-[132px] flex-col overflow-hidden rounded-[4px] border border-[#34342e] bg-[#0c0d0b] p-3">
      <span className="absolute start-0 top-0 h-px w-12 bg-[#ff571c]" aria-hidden="true" />
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-[15px] font-semibold tracking-[-0.02em] text-[#eee9dc]">{card.name}</div>
          <div className="mt-1 font-[family:var(--font-mono)] text-[11px] font-semibold uppercase tracking-[0.1em] text-[#8d867a]">
            {card.role}
          </div>
        </div>
        <StatusBadge label={card.status} tone={card.tone} />
      </div>
      <div className="mt-3 grid grid-cols-2 gap-2 font-[family:var(--font-mono)] text-[11px] uppercase tracking-[0.1em] text-[#8d867a]">
        <div className="rounded-[3px] border border-[#2b2b26] bg-[#11120f] px-2.5 py-2">
          <div>model</div>
          <div className="mt-1 truncate font-[family:var(--font-site-body)] text-[12px] normal-case tracking-normal text-[#c8c0b0]">{card.model}</div>
        </div>
        <div className="rounded-[3px] border border-[#2b2b26] bg-[#11120f] px-2.5 py-2">
          <div>load</div>
          <div className="mt-1 font-[family:var(--font-site-body)] text-[12px] normal-case tracking-normal text-[#c8c0b0]">{card.load}</div>
        </div>
      </div>
      <div className="mt-auto flex items-center justify-between pt-3 font-[family:var(--font-mono)] text-[11px] uppercase tracking-[0.1em] text-[#8d867a]">
        <span>{card.env}</span>
        <span>{card.lastSeen}</span>
      </div>
    </div>
  );
}

export function RailSection({
  title,
  meta,
  children,
}: {
  title: string;
  meta?: string;
  children: ReactNode;
}) {
  return (
    <section className={cn(PANEL_CHROME, "flex min-h-0 flex-col")} style={{ boxShadow: dashboardTokens.shadowSm }}>
      <div className="flex min-h-11 shrink-0 items-center justify-between gap-3 border-b border-[#2b2b26] bg-[#0c0d0b] px-3 py-2">
        <h2 className="text-[13px] font-semibold text-[#eee9dc]">{title}</h2>
        {meta ? (
          <span className="hidden font-[family:var(--font-mono)] text-[11px] uppercase tracking-[0.1em] text-[#8d867a] sm:inline">
            {meta}
          </span>
        ) : null}
      </div>
      <div className="min-h-0 flex-1 overflow-visible p-3 lg:overflow-hidden">{children}</div>
    </section>
  );
}

export function SectionIntroBar({
  label,
  detail,
  children,
}: {
  label: string;
  detail: string;
  children?: ReactNode;
}) {
  return (
    <section className="relative overflow-hidden rounded-[6px] border border-[#2b2b26] bg-[#11120f] px-4 py-4">
      <span className="absolute start-0 top-0 h-px w-20 bg-[#ff571c]" aria-hidden="true" />
      <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2 font-[family:var(--font-mono)] text-[11px] font-semibold uppercase tracking-[0.11em]">
            <span className="rounded-[3px] border border-[#ff6a32] bg-[#28140d] px-2 py-1 text-[#ff9a72]">
              REC / {label}
            </span>
            <span className="text-[#8d867a]">operator record</span>
          </div>
          <div className="mt-3 max-w-4xl text-[1.45rem] font-semibold leading-[1.05] tracking-[-0.04em] text-[#eee9dc] sm:text-[1.75rem]">
            {detail}
          </div>
        </div>
        {children ? (
          <div className="flex flex-wrap items-center gap-1.5 lg:max-w-[42%] lg:justify-end">{children}</div>
        ) : null}
      </div>
    </section>
  );
}
