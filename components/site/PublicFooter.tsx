import Link from "next/link";
import { ArrowRight, ArrowUpRight } from "lucide-react";

import { cn } from "@/lib/utils";

import styles from "./PublicFooter.module.css";

type PublicFooterProps = { className?: string; showCallout?: boolean };

const FOOTER_GROUPS = [
  {
    title: "Product",
    links: [
      { label: "Control plane", href: "/ai-agent-control-plane", external: false },
      { label: "Monitoring", href: "/ai-agent-monitoring", external: false },
      { label: "Guardrails", href: "/ai-agent-guardrails", external: false },
      { label: "Approvals", href: "/ai-agent-approvals", external: false },
    ],
  },
  {
    title: "Operate",
    links: [
      { label: "Dashboard", href: "/dashboard", external: false },
      { label: "Documentation", href: "/docs", external: false },
      { label: "Download", href: "/download", external: false },
      { label: "Releases", href: "/releases", external: false },
    ],
  },
  {
    title: "Ecosystem",
    links: [
      { label: "GitHub", href: "https://github.com/mutx-dev/mutx-dev", external: true },
      { label: "Pico", href: "https://pico.mutx.dev", external: true },
      { label: "Contact", href: "/contact", external: false },
      { label: "Security", href: "/security", external: false },
    ],
  },
] as const;

export function PublicFooter({ className, showCallout = true }: PublicFooterProps) {
  return (
    <footer className={cn(styles.footer, className)}>
      {showCallout ? (
        <div className={styles.callout}>
          <div>
            <p>Next run / 001</p>
            <h2>See the move before the aftermath.</h2>
          </div>
          <div className={styles.calloutAction}>
            <p>Start on your Mac, then bring the control plane to your own runtime.</p>
            <Link href="/download">
              Download MUTX <ArrowRight className={styles.directionalIcon} aria-hidden="true" />
            </Link>
          </div>
        </div>
      ) : null}

      <div className={styles.footerMain}>
        <div className={styles.identity}>
          <Link href="/" className={styles.brand} aria-label="MUTX home">
            <span aria-hidden="true">MX</span>
            <strong>MUTX</strong>
          </Link>
          <p>
            The source-available control plane for observable, governed agent work.
          </p>
          <span className={styles.availability}>
            <i aria-hidden="true" /> macOS · API · CLI
          </span>
        </div>

        <div className={styles.linkGrid}>
          {FOOTER_GROUPS.map((group) => (
            <nav key={group.title} aria-label={`${group.title} footer navigation`}>
              <p>{group.title}</p>
              {group.links.map((link) => link.external ? (
                <a key={link.label} href={link.href} target="_blank" rel="noopener noreferrer">
                  {link.label} <ArrowUpRight aria-hidden="true" />
                  <span className={styles.visuallyHidden}> (opens in a new tab)</span>
                </a>
              ) : (
                <Link key={link.label} href={link.href}>{link.label}</Link>
              ))}
            </nav>
          ))}
        </div>
      </div>

      <div className={styles.footerBottom}>
        <p>© MUTX 2026 / Source available</p>
        <nav aria-label="Legal navigation">
          <Link href="/privacy-policy">Privacy</Link>
          <Link href="/security">Security</Link>
        </nav>
        <p>Observe → Bound → Approve → Execute → Prove</p>
      </div>
    </footer>
  );
}
