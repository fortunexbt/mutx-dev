import type { Metadata } from "next";
import Link from "next/link";
import {
  AppWindow,
  ArrowRight,
  BookOpenText,
  ShieldCheck,
} from "lucide-react";

import { PublicNav } from "@/components/site/PublicNav";
import { PublicFooter } from "@/components/site/PublicFooter";
import { PublicSurface } from "@/components/site/PublicSurface";
import { OperationalVisual } from "@/components/site/marketing/OperationalVisual";
import styles from "@/components/site/marketing/MarketingCore.module.css";
import {
  MUTX_GITHUB_RELEASES_URL,
  MUTX_RELEASE_NOTES_URL,
  buildDesktopArtifactName,
  buildReleaseNotesUrl,
  fetchLatestStableDesktopRelease,
} from "@/lib/desktopRelease";
import { buildPageMetadata, buildWebPageStructuredData } from "@/lib/seo";

export const metadata: Metadata = {
  title: "Releases | MUTX",
  description:
    "Current MUTX desktop availability, GitHub releases, verification details, and docs-backed release notes.",
  ...buildPageMetadata({
    title: "Releases | MUTX",
    description:
      "Current MUTX desktop availability, GitHub releases, verification details, and docs-backed release notes.",
    path: "/releases",
  }),
};

export const revalidate = 900;

type ReleaseCard = {
  title: string;
  body: string;
  href: string;
  label: string;
  icon: typeof AppWindow;
  external?: boolean;
};

const structuredData = buildWebPageStructuredData({
  name: "Releases | MUTX",
  path: "/releases",
  description: "Current MUTX desktop availability, GitHub releases, verification details, and docs-backed release notes.",
});

export default async function ReleasesPage() {
  const release = await fetchLatestStableDesktopRelease();
  const version = release?.version;
  const releaseLabel = version ? `v${version}` : "Desktop unavailable";
  const docsReleaseNotesHref = version
    ? buildReleaseNotesUrl(version)
    : MUTX_RELEASE_NOTES_URL;
  const releaseHref = release?.htmlUrl ?? MUTX_GITHUB_RELEASES_URL;
  const cards: ReadonlyArray<ReleaseCard> = release
    ? [
        {
          title: "Apple Silicon DMG",
          body: `${buildDesktopArtifactName(release.version, "arm64-dmg")} for M-series Macs.`,
          href: release.assets.arm64Dmg,
          label: "Download arm64",
          icon: AppWindow,
          external: true,
        },
        {
          title: "Intel Mac DMG",
          body: `${buildDesktopArtifactName(release.version, "x64-dmg")} for supported Intel Macs.`,
          href: release.assets.x64Dmg,
          label: "Download x64",
          icon: AppWindow,
          external: true,
        },
        {
          title: "Checksums",
          body: `${buildDesktopArtifactName(release.version, "checksums")} lists exactly the four packages from this tag.`,
          href: release.assets.checksums,
          label: "Open SHA-256 manifest",
          icon: ShieldCheck,
          external: true,
        },
        {
          title: "Docs notes",
          body: "Docs-backed notes for the current desktop release.",
          href: docsReleaseNotesHref,
          label: "Read notes",
          icon: BookOpenText,
          external: true,
        },
      ]
    : [
        {
          title: "Desktop availability",
          body: "No complete desktop artifact set is currently published.",
          href: "/download/macos",
          label: "View availability",
          icon: AppWindow,
        },
        {
          title: "GitHub release notes",
          body: "Source release notes remain available independently of desktop downloads.",
          href: MUTX_GITHUB_RELEASES_URL,
          label: "View GitHub releases",
          icon: BookOpenText,
          external: true,
        },
        {
          title: "Docs release notes",
          body: "Read product notes while the desktop artifact set is incomplete.",
          href: docsReleaseNotesHref,
          label: "Read docs notes",
          icon: BookOpenText,
          external: true,
        },
      ];

  const artifactRows = release ? [
    {
      label: "Apple Silicon DMG",
      value: buildDesktopArtifactName(release.version, "arm64-dmg"),
      href: release.assets.arm64Dmg,
    },
    {
      label: "Intel Mac DMG",
      value: buildDesktopArtifactName(release.version, "x64-dmg"),
      href: release.assets.x64Dmg,
    },
    {
      label: "Apple Silicon ZIP",
      value: buildDesktopArtifactName(release.version, "arm64-zip"),
      href: release.assets.arm64Zip,
    },
    {
      label: "Intel Mac ZIP",
      value: buildDesktopArtifactName(release.version, "x64-zip"),
      href: release.assets.x64Zip,
    },
    {
      label: "SHA-256 manifest",
      value: buildDesktopArtifactName(release.version, "checksums"),
      href: release.assets.checksums,
    },
  ] as const : [];

  const shippedSurfaces = release
    ? [
        "Published Mac release for Apple Silicon and Intel.",
        "The exact four-package checksum manifest comes from the same GitHub tag.",
        "Preview surfaces stay out of the primary release lane.",
      ]
    : [
        "Desktop downloads stay disabled until every expected artifact is present.",
        "GitHub release notes remain available separately.",
        "Draft, prerelease, malformed, and partial releases stay out of the stable lane.",
      ];

  return (
    <PublicSurface className={`${styles.page} ${styles.publicPage} ${styles.releasesPage}`}>
      <PublicNav />
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(structuredData) }}
      />

      <main id="main-content" tabIndex={-1} className={styles.main}>
        <section className={styles.routeDarkSection} data-route-surface="dark">
          <div className={styles.shell}>
            <div className={styles.routeDownloadStage}>
              <div className={`${styles.routeHeroMain} ${styles.routeDownloadCopy}`}>
                <div className={styles.intro}>
                  <p className={`${styles.eyebrow} ${styles.eyebrowOnDark}`}>Release lane</p>
                  <h1 className={`${styles.displayTitle} ${styles.darkText}`}>
                    MUTX <span className={styles.releaseVersion}>{releaseLabel}</span>
                    <span className={styles.displayAccent}>
                      {release ? "Complete desktop release." : "No desktop download is offered."}
                    </span>
                  </h1>
                  <p className={`${styles.bodyText} ${styles.bodyTextOnDark}`}>
                    {release
                      ? "Current Mac release, checksums, docs notes, and GitHub tag."
                      : "The published releases do not currently contain one complete desktop artifact set. GitHub release notes remain available."}
                  </p>
                </div>

                <div className={styles.ctaRow}>
                  <Link href="/download" className={styles.buttonPrimary}>
                    {release ? "Open Mac downloads" : "View desktop availability"}
                    <ArrowRight className="h-4 w-4" />
                  </Link>
                  <a href={releaseHref} target="_blank" rel="noopener noreferrer" className={styles.buttonGhost}>
                    GitHub release notes
                    <span className="sr-only"> (opens in a new tab)</span>
                  </a>
                </div>

                <div className={styles.routeDownloadMeta}>
                  <p
                    className={styles.routeDownloadMetaItem}
                    role={release ? undefined : "status"}
                    data-testid={release ? undefined : "desktop-release-unavailable"}
                  >
                    {release ? "Current stable desktop release: " : "Desktop downloads: "}
                    <span>{release ? releaseLabel : "Unavailable"}</span>
                  </p>
                  <Link href="/download" className={styles.inlineLink}>
                    Download lane
                  </Link>
                  <a href={docsReleaseNotesHref} target="_blank" rel="noopener noreferrer" className={styles.inlineLink}>
                    Docs notes
                    <span className="sr-only"> (opens in a new tab)</span>
                  </a>
                  <a href={releaseHref} target="_blank" rel="noopener noreferrer" className={styles.inlineLink}>
                    GitHub release notes
                    <span className="sr-only"> (opens in a new tab)</span>
                  </a>
                </div>
              </div>

              <div className={styles.routeVisualFrame}>
                <OperationalVisual variant="release" />
              </div>
            </div>

            <div className={`${styles.routeReleaseBand} ${styles.routeHeroPanel}`}>
              <div className={styles.routeReleaseBandCopy}>
                <div className={styles.intro}>
                  <p className={styles.eyebrow}>{release ? "What ships now" : "Release status"}</p>
                  <h2 className={styles.sectionTitle}>
                    {release ? "One release lane." : "Artifact set incomplete."}
                  </h2>
                  <p className={styles.bodyText}>
                    {release
                      ? "All five uploaded files are non-empty, and the manifest names exactly the four packages from this GitHub tag."
                      : "Desktop downloads return only when both architectures, both archive formats, and checksums are published together."}
                  </p>
                </div>
              </div>

              <div className={styles.routeReleaseSignalGrid}>
                {shippedSurfaces.map((item) => (
                  <p key={item} className={`${styles.surfaceListItem} ${styles.surfaceListItemDark}`}>
                    {item}
                  </p>
                ))}
              </div>

              <div className={styles.utilityLinks}>
                <Link href="/dashboard" className={styles.inlineLink}>
                  Open dashboard
                </Link>
                <a href={docsReleaseNotesHref} target="_blank" rel="noopener noreferrer" className={styles.inlineLink}>
                  Docs notes
                  <span className="sr-only"> (opens in a new tab)</span>
                </a>
                <a href={releaseHref} target="_blank" rel="noopener noreferrer" className={styles.inlineLink}>
                  GitHub release notes
                  <span className="sr-only"> (opens in a new tab)</span>
                </a>
                <a href={MUTX_GITHUB_RELEASES_URL} target="_blank" rel="noopener noreferrer" className={styles.inlineLink}>
                  All releases
                  <span className="sr-only"> (opens in a new tab)</span>
                </a>
              </div>
            </div>

            <div className={`${styles.routeDownloadCards} ${styles.routeReleaseCards}`} data-testid="releases-download-cards">
                {cards.map((card) => {
                  const cardClassName = `${styles.panel} ${styles.panelDark} ${styles.panelPadded} ${styles.routeCard} ${styles.routeDownloadCard}`;
                  const cardContent = <>
                    <div className={styles.routeCardIcon}>
                      <card.icon className="h-4 w-4" />
                    </div>
                    <h3 className={styles.routeCardTitle}>{card.title}</h3>
                    <p className={styles.bodyText}>{card.body}</p>
                    <span className={styles.inlineLink}>
                      {card.label}
                      <ArrowRight className="h-4 w-4" />
                      {card.external ? <span className="sr-only"> (opens in a new tab)</span> : null}
                    </span>
                  </>;

                  return card.external ? (
                    <a
                      key={card.title}
                      href={card.href}
                      target="_blank"
                      rel="noopener noreferrer"
                      className={cardClassName}
                    >
                      {cardContent}
                    </a>
                  ) : (
                    <Link key={card.title} href={card.href} className={cardClassName}>
                      {cardContent}
                    </Link>
                  );
                })}
            </div>

            <div className={styles.routeReleaseArtifactRow}>
              <aside className={`${styles.panel} ${styles.panelDark} ${styles.panelPadded} ${styles.routeArtifactPanel}`}>
                <div className={styles.intro}>
                  <p className={styles.eyebrow}>Artifact contract</p>
                  <h2 className={styles.sectionTitle}>
                    {release ? "Release files" : "No release files advertised"}
                  </h2>
                  <p className={styles.bodyText}>
                    {release
                      ? `DMGs, ZIPs, and the validated checksum manifest are exact assets from ${release.tagName}. Open any filename below to retrieve that asset.`
                      : "An incomplete release is not presented as a desktop release, and placeholder filenames are not shown."}
                  </p>
                </div>

                {release ? (
                  <div className={`${styles.routeMetaList} ${styles.routeArtifactList}`}>
                    {artifactRows.map((row) => (
                      <div key={row.label} className={styles.routeMetaItem}>
                        <p className={styles.routeMetaLabel}>{row.label}</p>
                        <a
                          href={row.href}
                          target="_blank"
                          rel="noopener noreferrer"
                          className={`${styles.routeMetaValue} ${styles.inlineLink}`}
                          data-testid={row.label === "SHA-256 manifest" ? "desktop-release-manifest" : undefined}
                        >
                          {row.value}
                          <span className="sr-only"> (opens in a new tab)</span>
                        </a>
                      </div>
                    ))}
                  </div>
                ) : null}
              </aside>
            </div>
          </div>
        </section>
      </main>

      <PublicFooter showCallout={false} />
    </PublicSurface>
  );
}
