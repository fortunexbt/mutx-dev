import type { Metadata } from "next";
import { NextIntlClientProvider } from "next-intl";
import { getLocale, getMessages } from "next-intl/server";

import { appFontVariables } from "@/app/fonts/app";
import { ErrorBoundary } from "@/components/app/ErrorBoundary";
import { DesktopJobProvider } from "@/components/desktop/useDesktopJob";
import { DesktopRouteListener } from "@/components/desktop/DesktopRouteListener";
import { DesktopStatusProvider } from "@/components/desktop/useDesktopStatus";
import { DesktopWindowProvider } from "@/components/desktop/useDesktopWindow";
import { DashboardAuthBoundary } from "@/components/dashboard/DashboardAuthBoundary";
import { DashboardRouteSurface } from "@/components/dashboard/DashboardRouteSurface";
import { DashboardShell } from "@/components/dashboard/DashboardShell";
import { buildPageMetadata, getAppUrl } from "@/lib/seo";

export const metadata: Metadata = {
  metadataBase: new URL(getAppUrl()),
  ...buildPageMetadata({
    title: "Dashboard - MUTX",
    description: "Dashboard for agents, deployments, runs, budgets, webhooks, and governance.",
    path: "/dashboard",
    host: getAppUrl(),
    siteName: "MUTX App",
    badge: "APP",
  }),
  robots: {
    index: false,
    follow: false,
    nocache: true,
  },
  title: "Dashboard - MUTX",
  description: "Dashboard for agents, deployments, runs, budgets, webhooks, and governance.",
  keywords: [
    "agent control plane",
    "agent deployments",
    "agent environments",
    "agent governance",
    "webhooks",
    "api keys",
    "runs",
    "audit trail",
  ],
};

export default async function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const locale = await getLocale();
  const messages = await getMessages();
  const spaShellEnabled = process.env.NEXT_PUBLIC_SPA_SHELL === "true";

  return (
    <NextIntlClientProvider locale={locale} messages={messages}>
      <div className={`${appFontVariables} h-full font-[family:var(--font-site-body)]`}>
        <ErrorBoundary>
          <DesktopStatusProvider>
            <DesktopWindowProvider>
              <DesktopJobProvider>
                <DesktopRouteListener />
                <DashboardAuthBoundary>
                  <DashboardShell spaShellEnabled={spaShellEnabled}>
                    <DashboardRouteSurface spaShellEnabled={spaShellEnabled}>
                      {children}
                    </DashboardRouteSurface>
                  </DashboardShell>
                </DashboardAuthBoundary>
              </DesktopJobProvider>
            </DesktopWindowProvider>
          </DesktopStatusProvider>
        </ErrorBoundary>
      </div>
    </NextIntlClientProvider>
  );
}
