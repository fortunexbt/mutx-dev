import type { Metadata } from "next";
import "./globals.css";
import { NextIntlClientProvider } from "next-intl";
import { getLocale, getMessages } from "next-intl/server";

import { appFontVariables } from "@/app/fonts/app";
import { getLocaleDirection, normalizeLocale } from "@/i18n/locale";
import {
  buildPageMetadata,
  getSiteUrl,
} from "@/lib/seo";

const siteUrl = getSiteUrl();
const rootSocialMetadata = buildPageMetadata({
  title: "MUTX | Governed Runtime and Control Plane for AI Agents",
  description:
    "Record submitted runtime evidence, evaluate registered tool calls before execution, and operate approvals, audit, and control workflows.",
  path: "/",
  socialDescription:
    "MUTX links governed runtime decisions, submitted evidence, and operator workflows for AI agents.",
  twitterDescription:
    "Record governed runtime decisions and keep the operator evidence attached.",
});

export const viewport = {
  width: 'device-width',
  initialScale: 1,
  maximumScale: 5,
  themeColor: '#0a0a09',
} as const

export const metadata: Metadata = {
  metadataBase: new URL(siteUrl),
  ...rootSocialMetadata,
  title: "MUTX | Governed Runtime and Control Plane for AI Agents",
  description:
    "Record submitted runtime evidence, evaluate registered tool calls before execution, and operate approvals, audit, and control workflows.",
  applicationName: "MUTX",
  category: "developer tools",
  keywords: [
    "AI agent flight recorder",
    "agent control plane",
    "agent audit trail",
    "agent deployments",
    "operator dashboard",
    "webhooks",
    "traces",
    "runtime operations",
    "AI agent infrastructure",
    "deployment control plane",
  ],
  authors: [{ name: "MUTX" }],
  creator: "MUTX",
  publisher: "MUTX",
  manifest: "/manifest.webmanifest",
  robots: {
    index: true,
    follow: true,
    googleBot: {
      index: true,
      follow: true,
      "max-image-preview": "large",
      "max-snippet": -1,
      "max-video-preview": -1,
    },
  },
  icons: {
    icon: [
      { url: "/favicon.ico" },
      { url: "/favicon-32x32.png", sizes: "32x32", type: "image/png" },
      { url: "/favicon-16x16.png", sizes: "16x16", type: "image/png" },
    ],
    apple: "/apple-touch-icon.png",
  },
};

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const locale = normalizeLocale(await getLocale())
  const direction = getLocaleDirection(locale)
  const messages = await getMessages()

  return (
    <html lang={locale} dir={direction} className="h-full" suppressHydrationWarning>
      <head>
        <link rel="preconnect" href="https://calendly.com" />
        <link rel="dns-prefetch" href="https://calendly.com" />
        <link rel="preconnect" href="https://challenges.cloudflare.com" />
        <meta name="theme-color" content="#0a0a09" />
      </head>
      <body className={`${appFontVariables} h-full min-h-screen antialiased`}>
        <a href="#main-content" className="skip-link">Skip to main content</a>
        <NextIntlClientProvider locale={locale} messages={messages}>
          {children}
        </NextIntlClientProvider>
      </body>
    </html>
  );
}
