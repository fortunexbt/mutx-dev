import type { Metadata } from "next";
import Link from "next/link";
import { ArrowRight, BookOpenText, ShieldCheck } from "lucide-react";

import { PublicNav } from "@/components/site/PublicNav";
import { PublicFooter } from "@/components/site/PublicFooter";
import { PublicSurface } from "@/components/site/PublicSurface";
import { OperationalVisual } from "@/components/site/marketing/OperationalVisual";
import styles from "@/components/site/marketing/MarketingCore.module.css";
import {
  MUTX_GITHUB_RELEASES_URL,
  MUTX_RELEASE_NOTES_URL,
  buildReleaseNotesUrl,
  fetchLatestStableDesktopRelease,
} from "@/lib/desktopRelease";
import { buildPageMetadata, buildWebPageStructuredData } from "@/lib/seo";

export const revalidate = 900;

export const metadata: Metadata = {
  title: "Download for macOS | MUTX",
  description:
    "Check MUTX desktop availability for Apple Silicon and Intel, with release notes and verification details.",
  ...buildPageMetadata({
    title: "Download for macOS | MUTX",
    description:
      "Check MUTX desktop availability for Apple Silicon and Intel, with release notes and verification details.",
    path: "/download/macos",
  }),
};

const structuredData = buildWebPageStructuredData({
  name: "Download for macOS | MUTX",
  path: "/download/macos",
  description: "Check MUTX desktop availability for Apple Silicon and Intel, with release notes and verification details.",
});

export default async function MacDownloadPage() {
  const release = await fetchLatestStableDesktopRelease();
  const releaseLabel = release ? `v${release.version}` : "Unavailable";
  const docsReleaseNotesHref = release
    ? buildReleaseNotesUrl(release.version)
    : MUTX_RELEASE_NOTES_URL;
  const githubReleaseHref = release?.htmlUrl ?? MUTX_GITHUB_RELEASES_URL;

  const cards: ReadonlyArray<{
    title: string;
    body: string;
    href: string;
    icon: typeof BookOpenText;
    label: string;
    external?: boolean;
  }> = release
    ? [
        {
          title: "Release summary",
          body: "Current version, public download lane, notes, and checksums in one place.",
          href: "/releases",
          icon: BookOpenText,
          label: "Open release summary",
        },
        {
          title: "Docs notes",
          body: "Docs-backed notes for the current desktop build.",
          href: docsReleaseNotesHref,
          icon: BookOpenText,
          label: "Read docs notes",
          external: true,
        },
        {
          title: "Checksums",
          body: "Exact four-package SHA-256 manifest from the same GitHub release tag.",
          href: release.assets.checksums,
          icon: ShieldCheck,
          label: "View checksums",
          external: true,
        },
      ]
    : [
        {
          title: "Release summary",
          body: "See the current desktop availability status without placeholder downloads.",
          href: "/releases",
          icon: BookOpenText,
          label: "Open release summary",
        },
        {
          title: "Docs release notes",
          body: "Read product notes independently of desktop artifact availability.",
          href: docsReleaseNotesHref,
          icon: BookOpenText,
          label: "Read docs notes",
          external: true,
        },
        {
          title: "GitHub release notes",
          body: "Review published source releases and their notes directly on GitHub.",
          href: MUTX_GITHUB_RELEASES_URL,
          icon: BookOpenText,
          label: "View GitHub releases",
          external: true,
        },
      ];

  return (
    <PublicSurface className={`${styles.page} ${styles.publicPage} ${styles.downloadPage}`}>
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
                  <p className={`${styles.eyebrow} ${styles.eyebrowOnDark}`}>Desktop release</p>
                  <h1 className={`${styles.displayTitle} ${styles.darkText}`}>
                    {release
                      ? "Download MUTX for macOS."
                      : "MUTX desktop for macOS is currently unavailable."}
                  </h1>
                  <p className={`${styles.bodyText} ${styles.bodyTextOnDark}`}>
                    {release
                      ? "Published for Apple Silicon and Intel with DMG and ZIP packages covered by one exact checksum manifest."
                      : "No complete desktop artifact set is published. Downloads remain disabled until both architectures, archives, and checksums are available together."}
                  </p>
                </div>

                <div className={styles.ctaRow}>
                  {release ? (
                    <>
                      <a
                        href={release.assets.arm64Dmg}
                        className={styles.buttonPrimary}
                      >
                        Download for Apple Silicon
                        <ArrowRight className="rtl-directional-icon h-4 w-4" />
                      </a>
                      <a
                        href={release.assets.x64Dmg}
                        className={styles.buttonGhost}
                      >
                        Download for Intel Mac
                      </a>
                    </>
                  ) : (
                    <>
                      <a
                        href={MUTX_GITHUB_RELEASES_URL}
                        target="_blank"
                        rel="noopener noreferrer"
                        className={styles.buttonPrimary}
                      >
                        View GitHub release notes
                        <ArrowRight className="rtl-directional-icon h-4 w-4" />
                        <span className="sr-only"> (opens in a new tab)</span>
                      </a>
                      <a
                        href={docsReleaseNotesHref}
                        target="_blank"
                        rel="noopener noreferrer"
                        className={styles.buttonGhost}
                      >
                        Read docs notes
                        <span className="sr-only"> (opens in a new tab)</span>
                      </a>
                    </>
                  )}
                </div>

                <div className={styles.routeDownloadMeta}>
                  <p
                    className={styles.routeDownloadMetaItem}
                    role={release ? undefined : "status"}
                    data-testid={release ? undefined : "desktop-release-unavailable"}
                  >
                    {release ? "Complete stable release: " : "Desktop downloads: "}
                    <span>{releaseLabel}</span>
                  </p>
                  <Link href="/releases" className={styles.inlineLink}>
                    Release summary
                  </Link>
                  <a href={docsReleaseNotesHref} target="_blank" rel="noopener noreferrer" className={styles.inlineLink}>
                    Docs notes
                    <span className="sr-only"> (opens in a new tab)</span>
                  </a>
                  {release ? (
                    <a
                      href={release.assets.checksums}
                      target="_blank"
                      rel="noopener noreferrer"
                      className={styles.inlineLink}
                      data-testid="desktop-release-manifest"
                    >
                      Checksums
                      <span className="sr-only"> (opens in a new tab)</span>
                    </a>
                  ) : null}
                  <a href={githubReleaseHref} target="_blank" rel="noopener noreferrer" className={styles.inlineLink}>
                    GitHub release notes
                    <span className="sr-only"> (opens in a new tab)</span>
                  </a>
                </div>
              </div>

              <div className={styles.routeVisualFrame}>
                <OperationalVisual variant="download" />
              </div>
            </div>

            <div className={`${styles.routeReleaseBand} ${styles.routeHeroPanel}`}>
              <div className={styles.routeReleaseBandCopy}>
                <div className={styles.intro}>
                  <p className={styles.eyebrow}>{release ? "Stable macOS release" : "Desktop status"}</p>
                  <h2 className={styles.sectionTitle}>{release ? "Mac app first." : "Artifact set incomplete."}</h2>
                  <p className={styles.bodyText}>
                    {release
                      ? "Downloads, notes, and checksums stay in one place."
                      : "Release notes remain accessible while binary downloads are unavailable."}
                  </p>
                </div>
              </div>

              <div className={styles.routeReleaseSignalGrid}>
                <p className={`${styles.surfaceListItem} ${styles.surfaceListItemDark}`}>
                  {release
                    ? "GitHub reports all five expected release files as uploaded and non-empty."
                    : "No architecture download redirects to a generic release page."}
                </p>
                <p className={`${styles.surfaceListItem} ${styles.surfaceListItemDark}`}>
                  {release
                    ? "The checksum manifest names exactly both DMGs and both ZIPs from this tag."
                    : "Partial, draft, and prerelease artifact sets are not offered."}
                </p>
                <p className={`${styles.surfaceListItem} ${styles.surfaceListItemDark}`}>
                  {release
                    ? "Install once, then move into the dashboard."
                    : "GitHub and docs release notes remain available separately."}
                </p>
              </div>

              <div className={styles.utilityLinks}>
                <Link href="/dashboard" className={styles.inlineLink}>
                  Open dashboard
                </Link>
                <Link href="/login" className={styles.inlineLink}>
                  Sign in
                </Link>
                <a href={githubReleaseHref} target="_blank" rel="noopener noreferrer" className={styles.inlineLink}>
                  GitHub release notes
                  <span className="sr-only"> (opens in a new tab)</span>
                </a>
              </div>
            </div>

            <div className={styles.routeDownloadCards}>
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
                    <ArrowRight className="rtl-directional-icon h-4 w-4" />
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
          </div>
        </section>
      </main>

      <PublicFooter showCallout={false} />
    </PublicSurface>
  );
}
