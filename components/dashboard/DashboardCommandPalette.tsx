"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { ArrowRight, Search } from "lucide-react";

import { cn } from "@/lib/utils";

import { DashboardDialog } from "./DashboardDialog";
import {
  ALL_DASHBOARD_NAV_ITEMS,
  getDashboardNavPanel,
  type DashboardNavItem,
} from "./dashboardNav";

interface DashboardCommandPaletteProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  navigateToPanel: (panel: string) => void;
  prefetchPanel: (panel: string) => void;
}

export function DashboardCommandPalette({
  open,
  onOpenChange,
  navigateToPanel,
  prefetchPanel,
}: DashboardCommandPaletteProps) {
  const [query, setQuery] = useState("");
  const [activeIndex, setActiveIndex] = useState(0);
  const resultsRef = useRef<HTMLDivElement>(null);

  const matches = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    if (!normalized) return ALL_DASHBOARD_NAV_ITEMS;
    return ALL_DASHBOARD_NAV_ITEMS.filter((item) =>
      `${item.title} ${item.description} ${item.group}`.toLowerCase().includes(normalized),
    );
  }, [query]);

  useEffect(() => {
    if (!open || !matches[activeIndex]) return;

    resultsRef.current
      ?.querySelector<HTMLElement>(`#dashboard-command-${matches[activeIndex].key}`)
      ?.scrollIntoView({ block: "nearest" });
  }, [activeIndex, matches, open]);

  const selectItem = (item: DashboardNavItem) => {
    const panel = getDashboardNavPanel(item.key);
    prefetchPanel(panel);
    navigateToPanel(panel);
    onOpenChange(false);
    setQuery("");
    setActiveIndex(0);
  };

  return (
    <DashboardDialog
      open={open}
      onOpenChange={(nextOpen) => {
        onOpenChange(nextOpen);
        if (!nextOpen) {
          setQuery("");
          setActiveIndex(0);
        }
      }}
      title="Go anywhere"
      description="Search every operator surface without leaving the keyboard."
      className="max-w-2xl"
    >
      <div className="flex min-h-12 items-center gap-3 rounded-[4px] border border-[#3b3a33] bg-[#0c0d0b] px-3.5 transition-colors focus-within:border-[#ff6a32]">
        <Search className="h-4 w-4 shrink-0 text-[#ff7545]" aria-hidden="true" />
        <input
          data-autofocus
          type="search"
          value={query}
          onChange={(event) => {
            setQuery(event.target.value);
            setActiveIndex(0);
          }}
          onKeyDown={(event) => {
            if (event.key === "ArrowDown") {
              event.preventDefault();
              setActiveIndex((index) => Math.min(index + 1, Math.max(matches.length - 1, 0)));
            } else if (event.key === "ArrowUp") {
              event.preventDefault();
              setActiveIndex((index) => Math.max(index - 1, 0));
            } else if (event.key === "Home") {
              event.preventDefault();
              setActiveIndex(0);
            } else if (event.key === "End") {
              event.preventDefault();
              setActiveIndex(Math.max(matches.length - 1, 0));
            } else if (event.key === "Enter" && matches[activeIndex]) {
              event.preventDefault();
              selectItem(matches[activeIndex]);
            }
          }}
          placeholder="Agents, runs, budgets, security..."
          role="combobox"
          aria-autocomplete="list"
          aria-expanded="true"
          aria-label="Search dashboard surfaces"
          aria-controls="dashboard-command-results"
          aria-activedescendant={
            matches[activeIndex] ? `dashboard-command-${matches[activeIndex].key}` : undefined
          }
          className="min-w-0 flex-1 bg-transparent py-3 text-sm text-[#eee9dc] outline-none placeholder:text-[#8d867a]"
        />
        <kbd className="rounded-[3px] border border-[#3b3a33] bg-[#151612] px-1.5 py-0.5 font-[family:var(--font-mono)] text-[8px] text-[#8d867a]">
          ESC
        </kbd>
      </div>

      <div
        ref={resultsRef}
        id="dashboard-command-results"
        role="listbox"
        aria-label="Dashboard surfaces"
        className="mt-3 max-h-[min(48vh,28rem)] space-y-1 overflow-y-auto pe-1"
      >
        {matches.length ? (
          matches.map((item, index) => {
            const active = index === activeIndex;
            const ItemIcon = item.icon;
            const panel = getDashboardNavPanel(item.key);
            return (
              <button
                id={`dashboard-command-${item.key}`}
                key={item.key}
                type="button"
                role="option"
                aria-selected={active}
                onMouseEnter={() => {
                  setActiveIndex(index);
                  prefetchPanel(panel);
                }}
                onFocus={() => setActiveIndex(index)}
                onClick={() => selectItem(item)}
                className={cn(
                  "group flex min-h-14 w-full items-center gap-3 rounded-[4px] border px-3 text-start transition-colors",
                  active
                    ? "dashboard-active-rail border-[#3b3a33] bg-[#171813] text-[#eee9dc]"
                    : "border-transparent text-[#b8b1a4] hover:border-[#2b2b26] hover:bg-[#11120f]",
                )}
              >
                <span
                  className={cn(
                    "flex h-9 w-9 shrink-0 items-center justify-center rounded-[4px] border",
                    active
                      ? "border-[#56534b] bg-[#0c0d0b] text-[#ff7545]"
                      : "border-[#34342e] bg-[#0c0d0b] text-[#8d867a]",
                  )}
                >
                  <ItemIcon className="h-4 w-4" aria-hidden="true" />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="flex items-center gap-2 text-sm font-medium">
                    <span className="font-[family:var(--font-mono)] text-[8px] text-[#ff6a32]" aria-hidden="true">
                      {String(index + 1).padStart(2, "0")}
                    </span>
                    <span>{item.title}</span>
                  </span>
                  <span
                    className={cn(
                      "mt-0.5 block truncate text-xs",
                      active ? "text-[#aaa397]" : "text-[#8d867a]",
                    )}
                  >
                    {item.description}
                  </span>
                </span>
                <ArrowRight
                  className={cn(
                    "rtl-directional-icon h-4 w-4 shrink-0",
                    active ? "text-[#58aaff]" : "text-[#5f5d55]",
                  )}
                  aria-hidden="true"
                />
              </button>
            );
          })
        ) : (
          <div className="rounded-[4px] border border-dashed border-[#3b3a33] bg-[#0c0d0b] px-4 py-8 text-center text-sm text-[#888278]">
            No surface matches “{query}”.
          </div>
        )}
      </div>
    </DashboardDialog>
  );
}
