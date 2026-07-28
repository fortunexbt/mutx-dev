import type { Metadata } from "next";

import { appFontVariables } from "@/app/fonts/app";

export const metadata: Metadata = {
  title: "Setup handoff | MUTX",
  description:
    "Continue MUTX setup in the browser dashboard or use the native operator cockpit in MUTX.app.",
  alternates: {
    canonical: null,
  },
  openGraph: null,
  twitter: null,
  robots: {
    index: false,
    follow: false,
    nocache: true,
  },
};

export default function OnboardingLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className={`${appFontVariables} min-h-screen font-[family:var(--font-site-body)]`}>
      {children}
    </div>
  );
}
