"use client";

import { useEffect, useId, useRef } from "react";
import type { ReactNode } from "react";
import { X } from "lucide-react";

import { cn } from "@/lib/utils";

import { dashboardTokens } from "./tokens";

interface DashboardDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: string;
  children: ReactNode;
  footer?: ReactNode;
  className?: string;
}

const FOCUSABLE_SELECTOR = [
  "a[href]",
  "button:not([disabled])",
  "input:not([disabled]):not([type='hidden'])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  "[contenteditable='true']",
  "[tabindex]:not([tabindex='-1'])",
].join(",");

function getFocusableElements(container: HTMLElement) {
  return Array.from(container.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)).filter(
    (element) =>
      element.getAttribute("aria-hidden") !== "true" &&
      window.getComputedStyle(element).visibility !== "hidden" &&
      element.getClientRects().length > 0,
  );
}

export function DashboardDialog({
  open,
  onOpenChange,
  title,
  description,
  children,
  footer,
  className,
}: DashboardDialogProps) {
  const titleId = useId();
  const descriptionId = useId();
  const modalRootRef = useRef<HTMLDivElement>(null);
  const dialogRef = useRef<HTMLElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const returnFocusRef = useRef<HTMLElement | null>(null);
  const onOpenChangeRef = useRef(onOpenChange);

  useEffect(() => {
    onOpenChangeRef.current = onOpenChange;
  }, [onOpenChange]);

  useEffect(() => {
    if (!open) return;

    returnFocusRef.current =
      document.activeElement instanceof HTMLElement ? document.activeElement : null;

    const modalRoot = modalRootRef.current;
    const previousOverflow = document.body.style.overflow;
    const isolatedElements: Array<{
      element: HTMLElement;
      inert: boolean;
      ariaHidden: string | null;
    }> = [];
    let isolationPathElement: HTMLElement | null = modalRoot;

    while (isolationPathElement && isolationPathElement !== document.body) {
      const parentElement: HTMLElement | null = isolationPathElement.parentElement;
      if (!parentElement) break;

      Array.from(parentElement.children).forEach((element) => {
        if (!(element instanceof HTMLElement) || element === isolationPathElement) return;
        isolatedElements.push({
          element,
          inert: element.inert,
          ariaHidden: element.getAttribute("aria-hidden"),
        });
      });
      isolationPathElement = parentElement;
    }

    isolatedElements.forEach(({ element }) => {
      element.inert = true;
      element.setAttribute("aria-hidden", "true");
    });

    const focusInitialElement = () => {
      const dialog = dialogRef.current;
      if (!dialog) return;

      const requestedInitialFocus = dialog.querySelector<HTMLElement>("[data-autofocus]");
      const initialFocus =
        requestedInitialFocus ?? getFocusableElements(dialog)[0] ?? closeButtonRef.current ?? dialog;
      initialFocus.focus({ preventScroll: true });
    };

    const animationFrame = window.requestAnimationFrame(focusInitialElement);

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        event.stopPropagation();
        onOpenChangeRef.current(false);
        return;
      }

      if (event.key !== "Tab" || !dialogRef.current) return;

      const focusable = getFocusableElements(dialogRef.current);
      if (focusable.length === 0) {
        event.preventDefault();
        dialogRef.current.focus({ preventScroll: true });
        return;
      }

      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      const activeElement = document.activeElement;

      if (event.shiftKey && (activeElement === first || !dialogRef.current.contains(activeElement))) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && (activeElement === last || !dialogRef.current.contains(activeElement))) {
        event.preventDefault();
        first.focus();
      }
    };

    const handleFocusIn = (event: FocusEvent) => {
      const dialog = dialogRef.current;
      if (!dialog || dialog.contains(event.target as Node)) return;

      (getFocusableElements(dialog)[0] ?? dialog).focus({ preventScroll: true });
    };

    document.body.style.overflow = "hidden";
    document.addEventListener("keydown", handleKeyDown, true);
    document.addEventListener("focusin", handleFocusIn);

    return () => {
      window.cancelAnimationFrame(animationFrame);
      document.body.style.overflow = previousOverflow;
      document.removeEventListener("keydown", handleKeyDown, true);
      document.removeEventListener("focusin", handleFocusIn);
      isolatedElements.forEach(({ element, inert, ariaHidden }) => {
        element.inert = inert;
        if (ariaHidden === null) {
          element.removeAttribute("aria-hidden");
        } else {
          element.setAttribute("aria-hidden", ariaHidden);
        }
      });

      const returnFocus = returnFocusRef.current;
      if (returnFocus?.isConnected) {
        returnFocus.focus({ preventScroll: true });
      }
    };
  }, [open]);

  if (!open) return null;

  return (
    <div
      ref={modalRootRef}
      className="fixed inset-0 z-50 flex items-end justify-center p-0 sm:items-center sm:p-6"
    >
      <button
        type="button"
        aria-label={`Close ${title} dialog`}
        tabIndex={-1}
        className="absolute inset-0 bg-[#040403]/88"
        onClick={() => onOpenChangeRef.current(false)}
      />

      <section
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={description ? descriptionId : undefined}
        tabIndex={-1}
        className={cn(
          "relative z-10 flex max-h-[100dvh] w-full max-w-lg flex-col overflow-hidden rounded-t-[8px] border sm:max-h-[calc(100dvh-3rem)] sm:rounded-[8px]",
          className,
        )}
        style={{
          borderColor: dashboardTokens.borderStrong,
          background: dashboardTokens.panelGradientStrong,
          boxShadow: dashboardTokens.shadowLg,
        }}
      >
        <div
          className="flex items-start justify-between gap-4 border-b px-5 py-4 sm:px-6"
          style={{ borderColor: dashboardTokens.borderSubtle }}
        >
          <div className="min-w-0">
            <p
              className="text-[10px] font-semibold uppercase tracking-[0.18em]"
              style={{ color: dashboardTokens.textMuted }}
            >
              Operator Action
            </p>
            <h2
              id={titleId}
              className="mt-2 text-lg font-semibold tracking-[-0.03em]"
              style={{ color: dashboardTokens.textPrimary }}
            >
              {title}
            </h2>
            {description ? (
              <p
                id={descriptionId}
                className="mt-1 text-sm leading-6"
                style={{ color: dashboardTokens.textSubtle }}
              >
                {description}
              </p>
            ) : null}
          </div>

          <button
            ref={closeButtonRef}
            type="button"
            onClick={() => onOpenChangeRef.current(false)}
            className="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-md border transition hover:opacity-90 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2"
            style={{
              borderColor: dashboardTokens.borderSubtle,
              backgroundColor: dashboardTokens.bgInset,
              color: dashboardTokens.textSubtle,
              outlineColor: dashboardTokens.focusRing,
            }}
            aria-label="Close dialog"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="min-h-0 overflow-y-auto overscroll-contain px-5 py-5 sm:px-6">{children}</div>

        {footer ? (
          <div
            className="flex shrink-0 flex-wrap items-center justify-end gap-3 border-t px-5 py-4 pb-[max(1rem,env(safe-area-inset-bottom))] sm:px-6 sm:pb-4"
            style={{ borderColor: dashboardTokens.borderSubtle }}
          >
            {footer}
          </div>
        ) : null}
      </section>
    </div>
  );
}
