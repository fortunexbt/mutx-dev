"use client";

import { useEffect, useId, useRef, useState, type ComponentType } from "react";
import Link from "next/link";
import { MoreHorizontal } from "lucide-react";

import { cn } from "@/lib/utils";

import { dashboardTokens } from "./tokens";

export interface KebabMenuAction {
  label: string;
  onSelect?: () => void;
  href?: string;
  icon?: ComponentType<{ className?: string }>;
  disabled?: boolean;
  destructive?: boolean;
}

export interface KebabMenuProps {
  actions: KebabMenuAction[];
  align?: "start" | "end";
  className?: string;
}

export function KebabMenu({ actions, align = "end", className }: KebabMenuProps) {
  const [open, setOpen] = useState(false);
  const menuId = useId();
  const containerRef = useRef<HTMLDivElement | null>(null);
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const menuRef = useRef<HTMLDivElement | null>(null);

  const focusMenuItem = (position: "first" | "last") => {
    const items = menuRef.current?.querySelectorAll<HTMLElement>(
      '[role="menuitem"]:not([disabled])',
    );
    if (!items?.length) return;
    items[position === "first" ? 0 : items.length - 1]?.focus();
  };

  useEffect(() => {
    if (!open) return undefined;

    const handleOutsideClick = (event: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    };

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      event.preventDefault();
      setOpen(false);
      triggerRef.current?.focus();
    };

    window.addEventListener("mousedown", handleOutsideClick);
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.removeEventListener("mousedown", handleOutsideClick);
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [open]);

  return (
    <div className={cn("relative inline-flex", className)} ref={containerRef}>
      <button
        ref={triggerRef}
        type="button"
        className="inline-flex h-11 w-11 items-center justify-center rounded-md border transition-colors"
        style={{
          borderColor: dashboardTokens.borderSubtle,
          backgroundColor: dashboardTokens.bgSurfaceStrong,
          color: dashboardTokens.textSubtle,
        }}
        aria-label="Open row actions"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? menuId : undefined}
        onClick={() => setOpen((value) => !value)}
        onKeyDown={(event) => {
          if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
          event.preventDefault();
          setOpen(true);
          window.requestAnimationFrame(() => {
            focusMenuItem(event.key === "ArrowDown" ? "first" : "last");
          });
        }}
      >
        <MoreHorizontal className="h-4 w-4" />
      </button>

      {open ? (
        <div
          id={menuId}
          ref={menuRef}
          role="menu"
          aria-label="Row actions"
          onKeyDown={(event) => {
            const items = Array.from(
              menuRef.current?.querySelectorAll<HTMLElement>(
                '[role="menuitem"]:not([disabled])',
              ) ?? [],
            );
            if (!items.length) return;

            const currentIndex = Math.max(items.indexOf(document.activeElement as HTMLElement), 0);
            let nextIndex: number | null = null;
            if (event.key === "ArrowDown") nextIndex = (currentIndex + 1) % items.length;
            else if (event.key === "ArrowUp") nextIndex = (currentIndex - 1 + items.length) % items.length;
            else if (event.key === "Home") nextIndex = 0;
            else if (event.key === "End") nextIndex = items.length - 1;
            else if (event.key === "Tab") setOpen(false);

            if (nextIndex === null) return;
            event.preventDefault();
            items[nextIndex]?.focus();
          }}
          className={cn(
            "absolute top-full z-50 mt-1.5 min-w-[180px] overflow-hidden rounded-lg border py-1 shadow-2xl",
            align === "end" ? "end-0" : "start-0",
          )}
          style={{
            borderColor: dashboardTokens.borderSubtle,
            backgroundColor: dashboardTokens.bgSurfaceStrong,
            boxShadow: dashboardTokens.shadowLg,
          }}
        >
          {actions.map((action, index) => {
            const color = action.destructive
              ? "var(--swarm-color-status-error-text, #fda4af)"
              : dashboardTokens.textSubtle;

            const rowContent = (
              <>
                {action.icon ? <action.icon className="h-4 w-4 shrink-0" /> : null}
                <span>{action.label}</span>
              </>
            );

            const rowClassName = cn(
              "flex min-h-11 w-full items-center gap-2 px-3 py-2 text-start text-sm transition-colors",
              action.disabled ? "cursor-not-allowed opacity-45" : undefined,
            );

            if (action.href && !action.disabled) {
              return (
                <Link
                  key={`${action.label}-${index}`}
                  href={action.href}
                  className={rowClassName}
                  style={{ color }}
                  onClick={() => setOpen(false)}
                  role="menuitem"
                >
                  {rowContent}
                </Link>
              );
            }

            return (
              <button
                key={`${action.label}-${index}`}
                type="button"
                className={rowClassName}
                style={{ color }}
                disabled={action.disabled}
                role="menuitem"
                onClick={() => {
                  action.onSelect?.();
                  setOpen(false);
                }}
              >
                {rowContent}
              </button>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}
