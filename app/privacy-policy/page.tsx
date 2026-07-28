import type { Metadata } from "next";
import Link from "next/link";

import { PublicNav } from "@/components/site/PublicNav";
import { PublicFooter } from "@/components/site/PublicFooter";
import { PublicSurface } from "@/components/site/PublicSurface";
import styles from "@/components/site/marketing/MarketingCore.module.css";
import { buildPageMetadata, buildWebPageStructuredData } from "@/lib/seo";

export const metadata: Metadata = {
  title: "Privacy Policy | MUTX",
  description:
    "How MUTX handles data across the site, downloads, docs, and support surfaces.",
  ...buildPageMetadata({
    title: "Privacy Policy | MUTX",
    description:
      "How MUTX handles data across the site, downloads, docs, and support surfaces.",
    path: "/privacy-policy",
  }),
};

const sections = [
  {
    title: "Information we collect",
    body: [
      "We may collect information you provide directly to us, such as when you contact us, request updates, download MUTX, or interact with the MUTX website or app.",
      "We may also collect limited technical data required to operate the service, improve reliability, detect abuse, and understand how the product is being used.",
    ],
  },
  {
    title: "How we use information",
    body: [
      "We use collected information to operate MUTX, respond to requests, send updates you asked for, improve the product, secure the platform, and support release readiness and debugging.",
      "We do not sell personal information. We use information only to run, improve, and communicate about MUTX and closely related services.",
    ],
  },
  {
    title: "Email and product communications",
    body: [
      "When you submit a contact or support request, we use your email to deliver the request, acknowledge it, and reply about that request. A contact, support, or waitlist submission does not by itself enroll you in product marketing.",
      "We send occasional product and release updates only when you separately choose the optional product-updates checkbox. Consent is unchecked by default, does not affect delivery of your request, and can be withdrawn at any time by contacting us or using an unsubscribe option when provided.",
    ],
  },
  {
    title: "Cookies and analytics",
    body: [
      "MUTX may use cookies, logs, and similar technologies to maintain sessions, secure the platform, measure usage, and improve the site and app experience.",
      "Where analytics or third-party infrastructure are used, they are used in support of operating and improving MUTX, not for unrelated advertising resale.",
    ],
  },
  {
    title: "Sharing and disclosures",
    body: [
      "We may share information with infrastructure, hosting, email, analytics, and security providers strictly as needed to operate MUTX.",
      "We may also disclose information when required by law, to enforce our terms, or to protect users, infrastructure, or the service from abuse or security threats.",
    ],
  },
  {
    title: "Data retention",
    body: [
      "We retain information for as long as reasonably necessary to operate MUTX, comply with legal obligations, resolve disputes, and maintain security and operational records.",
      "Retention periods may vary depending on the type of data and the operational purpose it serves.",
    ],
  },
  {
    title: "Security",
    body: [
      "We take reasonable technical and organizational measures to protect information, but no system can guarantee absolute security.",
      "If you believe there is a privacy or security issue involving MUTX, contact us promptly so we can investigate.",
    ],
  },
  {
    title: "Your choices",
    body: [
      "You may contact us to request access, correction, deletion, or removal from communications, subject to legal and operational limitations.",
      "If you no longer want product emails, contact us and we will handle the request as reasonably possible.",
    ],
  },
  {
    title: "Contact",
    body: [
      "For privacy-related questions or requests, contact the MUTX team through the project website, GitHub repository, or the primary contact methods published at mutx.dev.",
    ],
  },
  {
    title: "Changes to this policy",
    body: [
      "We may update this Privacy Policy from time to time as MUTX evolves. When we do, we will update the effective date on this page.",
    ],
  },
] as const;

const structuredData = buildWebPageStructuredData({
  name: "Privacy Policy | MUTX",
  path: "/privacy-policy",
  description: "How MUTX handles data across the site, downloads, docs, and support surfaces.",
});

export default function PrivacyPolicyPage() {
  return (
    <PublicSurface className={`${styles.page} ${styles.publicPage}`}>
      <PublicNav />
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(structuredData) }}
      />

      <main id="main-content" tabIndex={-1} className={styles.main}>
        <section className={styles.routeDarkSection} data-route-surface="dark">
          <div className={`${styles.shell} ${styles.routeHeroCopy} ${styles.routeHeroNarrow} ${styles.routeHeroNarrowCopy}`}>
            <div className={styles.intro}>
              <p className={`${styles.eyebrow} ${styles.eyebrowOnDark}`}>Legal</p>
              <h1 className={`${styles.displayTitle} ${styles.darkText}`}>Privacy policy</h1>
              <p className={`${styles.bodyText} ${styles.bodyTextOnDark}`}>
                Effective date: July 28, 2026. How MUTX handles site, download,
                docs, and support data.
              </p>
            </div>
          </div>
        </section>

        <section className={styles.routeLightSection} data-route-surface="light">
          <div className={`${styles.shell} ${styles.routeLegalGrid}`}>
            <div className={styles.prosePanel}>
              {sections.map((section) => (
                <section key={section.title} className={styles.proseSection}>
                  <h2>{section.title}</h2>
                  {section.body.map((paragraph) => (
                    <p key={paragraph}>{paragraph}</p>
                  ))}
                </section>
              ))}
            </div>

            <aside className={`${styles.panel} ${styles.panelPadded} ${styles.routeMetaPanel}`}>
              <div className={styles.intro}>
                <p className={styles.eyebrow}>Legal scope</p>
                <h2 className={styles.sectionTitle}>Site policy.</h2>
                <p className={styles.bodyText}>
                  Covers mutx.dev, downloads, docs, and support communication.
                </p>
              </div>

              <div className={styles.routeMetaList}>
                <div className={styles.routeMetaItem}>
                  <p className={styles.routeMetaLabel}>Effective date</p>
                  <p className={styles.routeMetaValue}>July 28, 2026</p>
                </div>
                <div className={styles.routeMetaItem}>
                  <p className={styles.routeMetaLabel}>Contact</p>
                  <p className={styles.routeMetaValue}>
                    <a href="mailto:hello@mutx.dev" className={styles.inlineLink}>
                      hello@mutx.dev
                    </a>
                  </p>
                </div>
                <div className={styles.routeMetaItem}>
                  <p className={styles.routeMetaLabel}>Related links</p>
                  <p className={styles.routeMetaValue}>
                    <Link href="/" className={styles.inlineLink}>
                      mutx.dev
                    </Link>
                  </p>
                  <p className={styles.routeMetaValue}>
                    <Link href="/docs" className={styles.inlineLink}>
                      mutx.dev/docs
                    </Link>
                  </p>
                </div>
              </div>
            </aside>
          </div>
        </section>
      </main>

      <PublicFooter />
    </PublicSurface>
  );
}
