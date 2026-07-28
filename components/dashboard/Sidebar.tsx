import type { ComponentType, ReactNode } from "react";
import Link from "next/link";

import { cn } from "@/lib/utils";

import { dashboardTokens } from "./tokens";

export interface SidebarItem {
  label: string;
  href?: string;
  icon?: ComponentType<{ className?: string }>;
  badge?: ReactNode;
  active?: boolean;
  disabled?: boolean;
  onClick?: () => void;
}

export interface SidebarGroup {
  label?: string;
  items: SidebarItem[];
}

export interface SidebarProps {
  groups: SidebarGroup[];
  header?: ReactNode;
  footer?: ReactNode;
  className?: string;
  width?: number;
}

export function Sidebar({
  groups,
  header,
  footer,
  className,
  width = 272,
}: SidebarProps) {
  return (
    <aside
      className={cn("flex h-full shrink-0 flex-col border-e px-4 py-5", className)}
      style={{
        width,
        background: dashboardTokens.shellGradient,
        borderColor: dashboardTokens.borderSubtle,
        color: dashboardTokens.textPrimary,
        fontFamily: dashboardTokens.fontSans,
      }}
    >
      {header ? <div className="px-2 pb-4">{header}</div> : null}

      <nav className="flex-1 space-y-5 overflow-y-auto" aria-label="Sidebar navigation">
        {groups.map((group, groupIndex) => (
          <div key={`${group.label ?? "group"}-${groupIndex}`} className="space-y-1.5">
            {group.label ? (
              <p
                className="px-2 text-[11px] font-medium uppercase tracking-[0.14em]"
                style={{ color: dashboardTokens.textMuted }}
              >
                {group.label}
              </p>
            ) : null}

            {group.items.map((item) => {
              const itemContent = (
                <>
                  {item.icon ? (
                    <item.icon className="h-4 w-4 shrink-0" />
                  ) : (
                    <span className="h-4 w-4 shrink-0" aria-hidden />
                  )}
                  <span className="truncate text-sm">{item.label}</span>
                  {item.badge ? (
                    <span
                      className="ms-auto rounded-full border px-2 py-0.5 text-[11px]"
                      style={{
                        borderColor: dashboardTokens.borderStrong,
                        color: dashboardTokens.textSubtle,
                        fontFamily: dashboardTokens.fontMono,
                      }}
                    >
                      {item.badge}
                    </span>
                  ) : null}
                </>
              );

              const sharedClassName = cn(
                "flex w-full items-center gap-3 rounded-full border px-3 py-2.5 text-start transition-colors",
                item.disabled ? "cursor-not-allowed opacity-50" : undefined,
              );

              const sharedStyle = {
                backgroundColor: item.active ? dashboardTokens.bgSubtle : "transparent",
                borderColor: item.active ? dashboardTokens.borderStrong : "transparent",
                color: item.active ? dashboardTokens.textPrimary : dashboardTokens.textSubtle,
              };

              if (item.href && !item.disabled) {
                return (
                  <Link
                    key={`${item.label}-${item.href}`}
                    href={item.href}
                    className={sharedClassName}
                    style={sharedStyle}
                    aria-current={item.active ? "page" : undefined}
                  >
                    {itemContent}
                  </Link>
                );
              }

              return (
                <button
                  key={`${item.label}-${groupIndex}`}
                  type="button"
                  className={sharedClassName}
                  style={sharedStyle}
                  onClick={item.onClick}
                  disabled={item.disabled}
                  aria-current={item.active ? "page" : undefined}
                >
                  {itemContent}
                </button>
              );
            })}
          </div>
        ))}
      </nav>

      {footer ? (
        <div className="mt-4 border-t px-2 pt-4" style={{ borderColor: dashboardTokens.borderSubtle }}>
          {footer}
        </div>
      ) : null}
    </aside>
  );
}
