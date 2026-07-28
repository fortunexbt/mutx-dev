import type { Metadata } from "next";
import { ArrowRight, PhoneCall } from "lucide-react";

import { ContactLeadForm } from "@/components/ContactLeadForm";
import { PublicNav } from "@/components/site/PublicNav";
import { CalendlyPopupButton } from "@/components/site/CalendlyPopupButton";
import { PublicFooter } from "@/components/site/PublicFooter";
import { PublicSurface } from "@/components/site/PublicSurface";
import { OperationalVisual } from "@/components/site/marketing/OperationalVisual";
import styles from "@/components/site/marketing/MarketingCore.module.css";
import { buildPageMetadata, getCanonicalUrl, getSiteUrl } from "@/lib/seo";

const CONTACT_EMAIL = "hello@mutx.dev";
const contactTitle = "Contact | MUTX";
const contactDescription =
  "Contact MUTX for evaluation, rollout review, or a concrete operator issue.";

export const metadata: Metadata = {
  title: contactTitle,
  description: contactDescription,
  ...buildPageMetadata({
    title: contactTitle,
    description: contactDescription,
    path: "/contact",
  }),
};

const contactStructuredData = {
  "@context": "https://schema.org",
  "@type": "ContactPage",
  name: contactTitle,
  description: contactDescription,
  url: getCanonicalUrl("/contact"),
  mainEntity: {
    "@type": "Organization",
    name: "MUTX",
    url: getSiteUrl(),
    email: CONTACT_EMAIL,
    contactPoint: {
      "@type": "ContactPoint",
      contactType: "sales",
      email: CONTACT_EMAIL,
      availableLanguage: ["en"],
    },
  },
};

export default function ContactPage() {
  return (
    <PublicSurface className={`${styles.page} ${styles.publicPage}`}>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(contactStructuredData) }}
      />
      <PublicNav />

      <main id="main-content" tabIndex={-1} className={styles.main}>
        <section className={styles.routeDarkSection} data-route-surface="dark">
          <div className={`${styles.shell} ${styles.routeHeroNarrow}`}>
            <div className={styles.contactHeroStage}>
              <div className={styles.contactHeroCopy}>
                <div className={styles.intro}>
                  <p className={`${styles.eyebrow} ${styles.eyebrowOnDark}`}>Contact MUTX</p>
                  <h1 className={`${styles.displayTitle} ${styles.darkText} ${styles.contactHeroTitle}`}>
                    Talk to MUTX.
                  </h1>
                  <p className={`${styles.bodyText} ${styles.bodyTextOnDark} ${styles.contactHeroBody}`}>
                    Evaluation. Rollout. Operator issues.
                  </p>
                </div>

                <div className={styles.ctaRow}>
                  <CalendlyPopupButton className={styles.buttonPrimary}>
                    Book a call
                    <PhoneCall className="h-4 w-4" />
                  </CalendlyPopupButton>
                  <a href={`mailto:${CONTACT_EMAIL}`} className={styles.buttonGhost}>
                    Email MUTX
                    <ArrowRight className="h-4 w-4" />
                  </a>
                </div>
              </div>

              <div className={styles.contactHeroImageWrap}>
                <OperationalVisual variant="contact" />
              </div>
            </div>
          </div>
        </section>

        <section className={styles.routeLightSection} data-route-surface="light">
          <div className={`${styles.shell} ${styles.routeSingleColumn}`}>
            <ContactLeadForm className={styles.routeFormPanel} />
          </div>
        </section>
      </main>

      <PublicFooter />
    </PublicSurface>
  );
}
