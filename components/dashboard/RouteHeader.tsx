import type { LucideIcon } from "lucide-react";

import { FeatureHint, type FeatureHintProps } from "@/components/dashboard/FeatureHint";
import { cn } from "@/lib/utils";

interface RouteHeaderStat {
  label: string;
  value: string;
  tone?: "neutral" | "success" | "warning" | "danger";
}

interface RouteHeaderProps {
  title: string;
  description: string;
  icon: LucideIcon;
  iconTone?: string;
  badge?: string;
  stats?: RouteHeaderStat[];
  className?: string;
  hint?: FeatureHintProps;
}

const STAT_TONES: Record<NonNullable<RouteHeaderStat["tone"]>, string> = {
  neutral: "text-[#c8c0b0]",
  success: "text-[#78e3b4]",
  warning: "text-[#f4cc82]",
  danger: "text-[#ff9b96]",
};

export function RouteHeader({
  title,
  description,
  icon: Icon,
  badge,
  stats = [],
  className,
  hint,
}: RouteHeaderProps) {
  return (
    <header
      data-dashboard-ui="route-header"
      className={cn(
        "dashboard-entry relative grid min-w-0 gap-5 border-b border-[#34342e] pb-5 md:grid-cols-[minmax(0,1fr)_auto] md:items-end md:gap-6 lg:pb-6",
        className,
      )}
    >
      <span className="absolute -bottom-px start-0 h-px w-20 bg-[#ff571c]" aria-hidden="true" />
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2.5">
          <span
            className="flex h-7 w-7 items-center justify-center rounded-[4px] border border-[#663619] bg-[#21150f] text-[#ff8355]"
          >
            <Icon className="h-3.5 w-3.5" aria-hidden="true" />
          </span>
          <p className="font-[family:var(--font-mono)] text-[11px] font-semibold uppercase tracking-[0.16em] text-[#8d867a]">
            <span className="text-[#ff7545]">REC /</span> {badge || "Operator workspace"}
          </p>
          {hint ? (
            <FeatureHint
              {...hint}
              align="start"
              className={cn(hint.className, "[&_summary]:text-[11px]")}
            />
          ) : null}
          <span className="hidden font-[family:var(--font-mono)] text-[11px] uppercase tracking-[0.14em] text-[#8d867a] sm:inline" aria-hidden="true">
            Frame 001
          </span>
        </div>
        <h1 className="mt-3 max-w-[20ch] font-[family:var(--font-site-display)] text-[clamp(2rem,4vw,3.75rem)] font-medium leading-[0.95] tracking-[-0.055em] text-[#eee9dc]">
          {title}
        </h1>
        <p className="mt-3 max-w-2xl text-[13px] leading-6 text-[#999284] sm:text-[14px]">
          {description}
        </p>
      </div>

      {stats.length > 0 ? (
        <dl className="grid min-w-0 w-full grid-cols-1 gap-x-6 gap-y-3 border-t border-[#34342e] pt-4 min-[384px]:grid-cols-2 md:w-auto md:border-s md:border-t-0 md:ps-5 md:pt-0">
          {stats.map((stat, index) => (
            <div key={`${stat.label}-${stat.value}`} className="relative py-1">
              <dt className="font-[family:var(--font-mono)] text-[11px] font-semibold uppercase leading-4 tracking-[0.14em] text-[#918b80]">
                <span className="me-2 text-[#ff6a32]" aria-hidden="true">
                  {String(index + 1).padStart(2, "0")}
                </span>
                {stat.label}
              </dt>
              <dd
                dir="auto"
                className={cn(
                  "mt-1.5 break-words font-[family:var(--font-mono)] text-[12px] font-medium tabular-nums",
                  STAT_TONES[stat.tone || "neutral"],
                )}
              >
                {stat.value}
              </dd>
            </div>
          ))}
        </dl>
      ) : null}
    </header>
  );
}
