import type { HTMLAttributes } from "react";

import { cn } from "@/lib/utils";

import { statusTokens, dashboardTokens } from "./tokens";
import type { DashboardStatus } from "./types";

export interface StatusBadgeProps extends HTMLAttributes<HTMLSpanElement> {
  status: DashboardStatus;
  label?: string;
}

export function StatusBadge({ status, label, className, style, ...props }: StatusBadgeProps) {
  const tone = statusTokens[status];

  return (
    <span
      className={cn(
        "inline-flex min-h-6 items-center gap-1.5 rounded-[4px] border px-2 py-1 font-[family:var(--font-mono)] text-[11px] font-semibold uppercase tracking-[0.1em] tabular-nums",
        className,
      )}
      data-status={status}
      style={{
        backgroundColor: tone.bg,
        borderColor: tone.border,
        color: tone.text,
        fontFamily: dashboardTokens.fontMono,
        ...style,
      }}
      {...props}
    >
      <span
        aria-hidden
        className={cn(
          "h-1.5 w-1.5 rounded-full",
          status === "running" && "dashboard-live-dot",
        )}
        style={{ backgroundColor: tone.dot }}
      />
      {label ?? status}
    </span>
  );
}
