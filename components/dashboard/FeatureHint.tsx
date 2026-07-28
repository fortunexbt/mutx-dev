import { CircleGauge, ShieldAlert } from "lucide-react";

import { cn } from "@/lib/utils";

export type FeatureHintTone = "status" | "boundary";

export interface FeatureHintProps {
  tone?: FeatureHintTone;
  label?: string;
  title?: string;
  detail: string;
  align?: "start" | "end";
  className?: string;
}

function getFeatureHintCopy(tone: FeatureHintTone) {
  if (tone === "boundary") {
    return {
      label: "Boundary",
      title: "Current boundary",
      icon: ShieldAlert,
      summaryClassName:
        "border-amber-400/28 bg-amber-400/10 text-amber-100 hover:border-amber-300/40",
      detailClassName: "border-amber-400/28 bg-[#120d08] text-amber-100",
      detailTextClassName: "text-amber-50/80",
    };
  }

  return {
    label: "Status",
    title: "Current status",
    icon: CircleGauge,
    summaryClassName:
      "border-sky-400/28 bg-sky-400/10 text-sky-100 hover:border-sky-300/40",
    detailClassName: "border-sky-400/28 bg-[#09111c] text-sky-100",
    detailTextClassName: "text-sky-50/80",
  };
}

export function FeatureHint({
  tone = "status",
  label,
  title,
  detail,
  align = "end",
  className,
}: FeatureHintProps) {
  const copy = getFeatureHintCopy(tone);
  const Icon = copy.icon;

  return (
    <details className={cn("group relative max-sm:w-full", className)}>
      <summary
        className={cn(
          "inline-flex min-h-11 list-none cursor-pointer items-center gap-1.5 rounded-full border px-3 py-1 text-[10px] font-semibold uppercase tracking-[0.18em] transition-colors [&::-webkit-details-marker]:hidden",
          copy.summaryClassName,
        )}
      >
        <Icon className="h-3.5 w-3.5" />
        {label || copy.label}
      </summary>

      <div
        className={cn(
          "z-30 mt-2 hidden w-full rounded-[18px] border p-4 shadow-[0_20px_50px_rgba(2,2,5,0.34)] group-open:block sm:absolute sm:top-[calc(100%+0.5rem)] sm:mt-0 sm:w-[min(20rem,calc(100vw-2rem))]",
          align === "start" ? "start-0" : "end-0",
          copy.detailClassName,
        )}
      >
        <div className="flex items-start gap-2.5">
          <span className="mt-0.5 inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-white/10 bg-white/[0.06]">
            <Icon className="h-4 w-4" />
          </span>
          <div className="min-w-0">
            <p className="text-[11px] font-semibold uppercase tracking-[0.18em]">
              {title || copy.title}
            </p>
            <p className={cn("mt-2 text-sm leading-6", copy.detailTextClassName)}>{detail}</p>
          </div>
        </div>
      </div>
    </details>
  );
}
