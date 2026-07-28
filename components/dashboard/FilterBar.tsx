"use client";

import type { HTMLAttributes, ReactNode, RefObject } from "react";
import { Search, SlidersHorizontal, X } from "lucide-react";

import { cn } from "@/lib/utils";

import { dashboardTokens } from "./tokens";

export interface FilterOption {
  label: string;
  value: string;
}

export interface FilterControl {
  id: string;
  label: string;
  value: string;
  options: FilterOption[];
  onChange: (nextValue: string) => void;
}

export interface FilterBarProps extends Omit<HTMLAttributes<HTMLDivElement>, "onChange"> {
  searchValue: string;
  onSearchChange: (nextValue: string) => void;
  searchInputRef?: RefObject<HTMLInputElement | null>;
  searchPlaceholder?: string;
  filters?: FilterControl[];
  trailing?: ReactNode;
  onReset?: () => void;
}

export function FilterBar({
  searchValue,
  onSearchChange,
  searchInputRef,
  searchPlaceholder = "Search...",
  filters = [],
  trailing,
  onReset,
  className,
  style,
  ...props
}: FilterBarProps) {
  const canReset = Boolean(onReset) && (searchValue.length > 0 || filters.some((filter) => filter.value.length > 0));

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Escape" && searchValue) {
      onSearchChange("");
      onReset?.();
    }
  };

  return (
    <section
      className={cn("dashboard-entry min-w-0 rounded-[6px] border p-3.5", className)}
      style={{
        borderColor: dashboardTokens.borderSubtle,
        background: dashboardTokens.panelGradient,
        boxShadow: dashboardTokens.shadowSm,
        ...style,
      }}
      {...props}
    >
      <div className="flex min-w-0 flex-col gap-2.5 sm:flex-row sm:flex-wrap sm:items-center">
        <div
          className="flex min-h-11 min-w-0 flex-1 items-center gap-2 rounded-[4px] border px-3.5 sm:min-w-[240px]"
          style={{
            borderColor: dashboardTokens.borderStrong,
            backgroundColor: dashboardTokens.bgInset,
            color: dashboardTokens.textSubtle,
          }}
        >
          <Search className="h-4 w-4 shrink-0" style={{ color: dashboardTokens.textMuted }} aria-hidden="true" />
          <label htmlFor="filterbar-search" className="sr-only">
            {searchPlaceholder}
          </label>
          <input
            id="filterbar-search"
            ref={searchInputRef}
            value={searchValue}
            onChange={(event) => onSearchChange(event.currentTarget.value)}
            onKeyDown={handleKeyDown}
            placeholder={searchPlaceholder}
            className="w-full border-0 bg-transparent text-sm outline-none"
            style={{ color: dashboardTokens.textPrimary }}
          />
        </div>

        {filters.length > 0 ? (
          <div className="flex min-w-0 flex-wrap items-center gap-2">
            <span
              className="inline-flex items-center gap-1 text-xs uppercase tracking-[0.14em]"
              style={{ color: dashboardTokens.textMuted }}
            >
              <SlidersHorizontal className="h-3.5 w-3.5" />
              Filters
            </span>
            {filters.map((filter) => (
              <label
                key={filter.id}
                className="flex min-h-11 min-w-0 items-center gap-2 rounded-[4px] border px-3 py-2 text-sm"
                style={{
                  borderColor: dashboardTokens.borderSubtle,
                  backgroundColor: dashboardTokens.bgInset,
                  color: dashboardTokens.textSubtle,
                }}
              >
                <span className="text-xs" style={{ color: dashboardTokens.textMuted }}>
                  {filter.label}
                </span>
                <select
                  value={filter.value}
                  onChange={(event) => filter.onChange(event.currentTarget.value)}
                  className="rounded border-0 bg-transparent text-sm outline-none"
                  style={{ color: dashboardTokens.textPrimary }}
                  aria-label={filter.label}
                >
                  {filter.options.map((option) => (
                    <option key={`${filter.id}-${option.value}`} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </label>
            ))}
          </div>
        ) : null}

        {canReset ? (
          <button
            type="button"
            onClick={onReset}
            className="inline-flex min-h-11 items-center gap-1 rounded-[4px] border px-3 text-sm"
            style={{
              borderColor: dashboardTokens.borderSubtle,
              backgroundColor: dashboardTokens.bgInset,
              color: dashboardTokens.textSubtle,
            }}
          >
            <X className="h-4 w-4" />
            Reset
          </button>
        ) : null}

        {trailing ? <div className="min-w-0 sm:ms-auto">{trailing}</div> : null}
      </div>
    </section>
  );
}
