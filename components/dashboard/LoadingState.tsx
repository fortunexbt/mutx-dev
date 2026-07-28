import type { HTMLAttributes } from "react";

import { cn } from "@/lib/utils";

import { dashboardTokens } from "./tokens";

export interface LoadingStateProps extends HTMLAttributes<HTMLDivElement> {
  variant?: "cards" | "rows" | "detail";
  count?: number;
}

function SkeletonBlock({ className }: { className?: string }) {
  return (
    <div
      className={cn("rounded-[3px] motion-safe:animate-pulse motion-reduce:animate-none", className)}
      aria-hidden="true"
      style={{ backgroundColor: dashboardTokens.bgSubtle }}
    />
  );
}

function CardSkeleton() {
  return (
    <div
      className="rounded-[6px] border p-4"
      style={{
        borderColor: dashboardTokens.borderSubtle,
        background: dashboardTokens.panelGradient,
        boxShadow: dashboardTokens.shadowSm,
      }}
    >
      <div className="flex items-center justify-between gap-3">
        <SkeletonBlock className="h-4 w-36" />
        <SkeletonBlock className="h-5 w-20" />
      </div>
      <div className="mt-4 space-y-2">
        <SkeletonBlock className="h-3 w-full" />
        <SkeletonBlock className="h-3 w-11/12" />
      </div>
    </div>
  );
}

function RowSkeleton() {
  return (
    <div
      className="flex items-center gap-3 rounded-[4px] border px-3 py-3"
      style={{
        borderColor: dashboardTokens.borderSubtle,
        backgroundColor: dashboardTokens.bgSurface,
      }}
    >
      <SkeletonBlock className="h-8 w-8 rounded-md" />
      <div className="min-w-0 flex-1 space-y-2">
        <SkeletonBlock className="h-3.5 w-40" />
        <SkeletonBlock className="h-3 w-52" />
      </div>
      <SkeletonBlock className="h-5 w-16" />
    </div>
  );
}

function DetailSkeleton() {
  return (
    <div
      className="rounded-[6px] border p-4"
      style={{
        borderColor: dashboardTokens.borderSubtle,
        background: dashboardTokens.panelGradient,
        boxShadow: dashboardTokens.shadowSm,
      }}
    >
      <SkeletonBlock className="h-5 w-48" />
      <div className="mt-4 grid gap-2">
        <SkeletonBlock className="h-4 w-full" />
        <SkeletonBlock className="h-4 w-5/6" />
        <SkeletonBlock className="h-4 w-2/3" />
      </div>
    </div>
  );
}

export function LoadingState({
  variant = "cards",
  count = 3,
  className,
  style,
  ...props
}: LoadingStateProps) {
  const items = Array.from({ length: count });

  return (
    <div
      role="status"
      aria-live="polite"
      aria-busy="true"
      className={cn("space-y-3", className)}
      style={style}
      {...props}
    >
      <span className="sr-only">Loading dashboard content</span>
      <div
        className="mb-3 flex items-center gap-2 font-[family:var(--font-mono)] text-[11px] uppercase tracking-[0.12em]"
        style={{ color: dashboardTokens.textMuted }}
        aria-hidden="true"
      >
        <span className="h-px w-5" style={{ backgroundColor: dashboardTokens.brand }} />
        BUFFER / loading records
      </div>
      {items.map((_, index) => {
        if (variant === "rows") {
          return <RowSkeleton key={`row-${index}`} />;
        }

        if (variant === "detail") {
          return <DetailSkeleton key={`detail-${index}`} />;
        }

        return <CardSkeleton key={`card-${index}`} />;
      })}
    </div>
  );
}
