import type { Metadata } from "next";

import { RebrandHomePage } from "@/components/site/marketing/RebrandHomePage";
import { PublicFooter } from "@/components/site/PublicFooter";
import { PublicSurface } from "@/components/site/PublicSurface";
import { DEFAULT_X_HANDLE, buildPageMetadata, getSiteUrl } from "@/lib/seo";

const homeTitle = "MUTX | Governed Runtime Records for AI Agents";
const homeDescription =
  "MUTX records submitted runtime evidence, evaluates registered tool calls before execution, and exposes operator workflows for approvals, audit, and control.";

export const metadata: Metadata = {
  title: homeTitle,
  description: homeDescription,
  ...buildPageMetadata({
    title: homeTitle,
    description: homeDescription,
    path: "/",
  }),
};

const homepageStructuredData = {
  "@context": "https://schema.org",
  "@graph": [
    {
      "@type": "Organization",
      "@id": `${getSiteUrl()}/#organization`,
      name: "MUTX",
      url: getSiteUrl(),
      logo: `${getSiteUrl()}/logo.png`,
      sameAs: [
        "https://github.com/mutx-dev/mutx-dev",
        `https://x.com/${DEFAULT_X_HANDLE.replace("@", "")}`,
      ],
    },
    {
      "@type": "SoftwareApplication",
      name: "MUTX",
      applicationCategory: "DeveloperApplication",
      operatingSystem: "macOS",
      description: homeDescription,
      url: getSiteUrl(),
      downloadUrl: `${getSiteUrl()}/download`,
      publisher: {
        "@id": `${getSiteUrl()}/#organization`,
      },
      offers: {
        "@type": "Offer",
        price: "0",
        priceCurrency: "USD",
      },
    },
    {
      "@type": "WebSite",
      name: "MUTX",
      url: getSiteUrl(),
      description: homeDescription,
      publisher: {
        "@id": `${getSiteUrl()}/#organization`,
      },
    },
  ],
};

export default function HomePage() {
  return (
    <PublicSurface>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(homepageStructuredData) }}
      />
      <RebrandHomePage />
      <PublicFooter showCallout={false} />
    </PublicSurface>
  );
}
