"use client";

import { Toaster as SonnerToaster } from "sonner";
import { useLocale } from "next-intl";

import { getLocaleDirection } from "@/i18n/locale";

export function Toaster() {
  const direction = getLocaleDirection(useLocale());

  return (
    <SonnerToaster
      theme="dark"
      position={direction === "rtl" ? "bottom-left" : "bottom-right"}
      toastOptions={{
        style: {
          background: "#0f0f14",
          border: "1px solid #1e293b",
          color: "#f1f5f9",
        },
      }}
    />
  );
}
