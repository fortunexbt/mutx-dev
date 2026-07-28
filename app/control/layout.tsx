import type { Metadata } from "next";
import { NextIntlClientProvider } from "next-intl";
import { getLocale, getMessages } from "next-intl/server";

import { appFontVariables } from "@/app/fonts/app";
import { ErrorBoundary } from "@/components/app/ErrorBoundary";
import { DemoViewportLock } from "@/components/dashboard/demo/DemoViewportLock";
import { buildPageMetadata, getAppUrl } from "@/lib/seo";

export const metadata: Metadata = {
  metadataBase: new URL(getAppUrl()),
  ...buildPageMetadata({
    title: "MUTX Simulated Control Demo",
    description: "A sample-data walkthrough of the MUTX operator flight recorder. No live workspace or write controls are connected.",
    path: "/control",
    host: getAppUrl(),
    siteName: "MUTX App",
    badge: "CONTROL PLANE",
  }),
  robots: {
    index: true,
    follow: true,
    nocache: false,
  },
  title: "MUTX Simulated Control Demo",
  description: "A sample-data walkthrough of the MUTX operator flight recorder. No live workspace or write controls are connected.",
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

export default async function AppDemoLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const locale = await getLocale();
  const messages = await getMessages();

  return (
    <NextIntlClientProvider locale={locale} messages={messages}>
      <ErrorBoundary>
        <DemoViewportLock>
          <div className={`${appFontVariables} h-full overflow-hidden font-[family:var(--font-site-body)]`}>
            {children}
          </div>
        </DemoViewportLock>
      </ErrorBoundary>
    </NextIntlClientProvider>
  );
}
