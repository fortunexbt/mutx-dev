"use client";

import { useEffect, useRef, type RefObject } from "react";

const FOCUSABLE_SELECTOR = [
  "a[href]",
  "button:not([disabled])",
  "input:not([disabled])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  "[tabindex]:not([tabindex='-1'])",
].join(",");

export function useDesktopDialog<
  TDialog extends HTMLElement = HTMLDivElement,
  TInitial extends HTMLElement = HTMLElement,
>(
  open: boolean,
  onClose: () => void,
  initialFocusRef?: RefObject<TInitial | null>,
) {
  const dialogRef = useRef<TDialog>(null);
  const previousFocusRef = useRef<HTMLElement | null>(null);
  const onCloseRef = useRef(onClose);

  useEffect(() => {
    onCloseRef.current = onClose;
  }, [onClose]);

  useEffect(() => {
    if (!open) {
      return;
    }

    previousFocusRef.current =
      document.activeElement instanceof HTMLElement ? document.activeElement : null;

    const focusDialog = window.requestAnimationFrame(() => {
      const initialTarget =
        initialFocusRef?.current ??
        dialogRef.current?.querySelector<HTMLElement>(FOCUSABLE_SELECTOR) ??
        dialogRef.current;
      initialTarget?.focus();
    });

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        event.stopPropagation();
        onCloseRef.current();
        return;
      }

      if (event.key !== "Tab" || !dialogRef.current) {
        return;
      }

      const focusable = Array.from(
        dialogRef.current.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR),
      ).filter((element) => !element.hasAttribute("hidden") && element.tabIndex !== -1);

      if (focusable.length === 0) {
        event.preventDefault();
        dialogRef.current.focus();
        return;
      }

      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      const activeElement = document.activeElement;
      const focusIsOutsideDialog = !dialogRef.current.contains(activeElement);
      if (event.shiftKey && (activeElement === first || focusIsOutsideDialog)) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && (activeElement === last || focusIsOutsideDialog)) {
        event.preventDefault();
        first.focus();
      }
    };

    document.addEventListener("keydown", handleKeyDown, true);

    return () => {
      window.cancelAnimationFrame(focusDialog);
      document.removeEventListener("keydown", handleKeyDown, true);
      const previousFocus = previousFocusRef.current;
      if (previousFocus?.isConnected) {
        previousFocus.focus();
      }
      previousFocusRef.current = null;
    };
  }, [initialFocusRef, open]);

  return dialogRef;
}
