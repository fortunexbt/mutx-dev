import type { ReactNode } from "react";

import { AuthNav } from "@/components/AuthNav";
import { PicoFooter } from "@/components/pico/PicoFooter";
import { PublicFooter } from "@/components/site/PublicFooter";
import { PublicSurface } from "@/components/site/PublicSurface";

import styles from "./AuthSurface.module.css";

type AuthSurfaceProps = {
  eyebrow: string;
  title: string;
  description: string;
  asideEyebrow: string;
  asideTitle: string;
  asideBody: string;
  highlights: readonly string[];
  children: ReactNode;
  variant?: "access" | "recovery";
  hostVariant?: "default" | "pico";
};

export function AuthSurface({
  eyebrow,
  title,
  description,
  asideEyebrow,
  asideTitle,
  asideBody,
  highlights,
  children,
  variant = "access",
  hostVariant = "default",
}: AuthSurfaceProps) {
  const ledgerEntries = highlights.slice(0, 3);

  return (
    <PublicSurface>
      <AuthNav hostVariant={hostVariant} />

      <main id="main-content" tabIndex={-1} className={styles.main} data-auth-variant={variant} data-auth-host={hostVariant}>
        <section className={styles.stage}>
          <aside className={styles.visual}>
            <div className={styles.visualMeta}>
              <span>{hostVariant === "pico" ? "PicoMUTX" : "Identity ledger"}</span>
              <span className={styles.secureState}><i /> {hostVariant === "pico" ? "TLS" : "Secure channel"}</span>
            </div>

            <div className={styles.visualContent}>
              <p className={styles.eyebrow}>{eyebrow}</p>
              <h1 className={styles.title}>{title}</h1>
              <p className={styles.description}>{description}</p>
            </div>

            <ol className={styles.ledger} aria-label={hostVariant === "pico" ? eyebrow : "Account access sequence"}>
              {ledgerEntries.map((entry, index) => (
                <li key={entry}>
                  <span>{`0${index + 1}`}</span>
                  <i aria-hidden="true" />
                  <p>{entry}</p>
                  <strong aria-hidden={hostVariant === "pico" ? "true" : undefined}>
                    {hostVariant === "pico" ? "✓" : index === ledgerEntries.length - 1 ? "ready" : "verified"}
                  </strong>
                </li>
              ))}
            </ol>

            <div className={styles.receipt}>
              <p>{asideEyebrow}</p>
              <strong>{asideTitle}</strong>
              <span>{asideBody}</span>
            </div>
          </aside>

          <div className={styles.formPanel}>
            <div className={styles.formMeta} aria-hidden="true">
              <span>{hostVariant === "pico" ? "PICO / AUTH" : variant === "recovery" ? "RECOVERY / 01" : "ACCESS / 01"}</span>
              <span>{hostVariant === "pico" ? "PicoMUTX" : "MUTX CONTROL PLANE"}</span>
            </div>
            <div className={styles.formInner}>
              {children}
            </div>
          </div>
        </section>
      </main>

      {hostVariant === "pico" ? <PicoFooter /> : <PublicFooter showCallout={false} />}
    </PublicSurface>
  );
}
