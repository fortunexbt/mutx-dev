import type { HTMLAttributes, ReactNode } from "react";
import Link from "next/link";
import { Inbox } from "lucide-react";

import { cn } from "@/lib/utils";

import { dashboardTokens } from "./tokens";

export interface EmptyStateProps extends HTMLAttributes<HTMLDivElement> {
  title: string;
  message: string;
  icon?: ReactNode;
  ctaLabel?: string;
  ctaHref?: string;
  onCtaClick?: () => void;
  cta?: ReactNode;
}

export function EmptyState({
  title,
  message,
  icon,
  ctaLabel,
  ctaHref,
  onCtaClick,
  cta,
  className,
  style,
  ...props
}: EmptyStateProps) {
  return (
    <div
      className={cn(
        "dashboard-entry relative flex flex-col items-center justify-center overflow-hidden rounded-[6px] border px-6 py-12 text-center",
        className,
      )}
      style={{
        borderColor: dashboardTokens.borderSubtle,
        background: dashboardTokens.panelGradient,
        color: dashboardTokens.textPrimary,
        boxShadow: dashboardTokens.shadowSm,
        ...style,
      }}
      {...props}
    >
      <span className="absolute start-0 top-0 h-px w-20" style={{ backgroundColor: dashboardTokens.brand }} aria-hidden="true" />
      <p
        className="mb-4 font-[family:var(--font-mono)] text-[11px] font-semibold uppercase tracking-[0.14em]"
        style={{ color: dashboardTokens.textLabel }}
        aria-hidden="true"
      >
        NO DATA / awaiting record
      </p>
      <div
        className="flex h-12 w-12 items-center justify-center rounded-[4px] border"
        style={{
          borderColor: dashboardTokens.borderStrong,
          backgroundColor: dashboardTokens.bgInset,
          color: dashboardTokens.brand,
        }}
      >
        {icon ?? <Inbox className="h-7 w-7" />}
      </div>
      <h3 className="mt-4 font-[family:var(--font-site-display)] text-xl font-medium tracking-[-0.035em]">{title}</h3>
      <p className="mt-2 max-w-md text-[13px] leading-6" style={{ color: dashboardTokens.textSubtle }}>
        {message}
      </p>

      {cta ? <div className="mt-5">{cta}</div> : null}
      {!cta && ctaLabel && ctaHref ? (
        <Link
          href={ctaHref}
          className="mt-5 inline-flex min-h-11 items-center rounded-[4px] border border-transparent px-5 text-xs font-semibold transition-colors hover:bg-[#ff7545]"
          style={{
            backgroundColor: dashboardTokens.brand,
            color: dashboardTokens.bgCanvas,
          }}
        >
          {ctaLabel}
        </Link>
      ) : null}
      {!cta && ctaLabel && !ctaHref && onCtaClick ? (
        <button
          type="button"
          onClick={onCtaClick}
          className="mt-5 inline-flex min-h-11 items-center rounded-[4px] border border-transparent px-5 text-xs font-semibold transition-colors hover:bg-[#ff7545]"
          style={{
            backgroundColor: dashboardTokens.brand,
            color: dashboardTokens.bgCanvas,
          }}
        >
          {ctaLabel}
        </button>
      ) : null}
    </div>
  );
}
