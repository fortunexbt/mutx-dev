"use client";

import Link from "next/link";
import { ArrowRight, ArrowUpRight, Menu, X } from "lucide-react";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

import styles from "./PublicNav.module.css";

const NAV_ITEMS = [
  { label: "Product", href: "/ai-agent-control-plane", external: false },
  { label: "Docs", href: "/docs", external: false },
  { label: "GitHub", href: "https://github.com/mutx-dev/mutx-dev", external: true },
  { label: "Dashboard", href: "/dashboard", external: false },
] as const;

export function PublicNav({ overlay = false }: { overlay?: boolean }) {
  const pathname = usePathname() ?? "/";
  const [mobileOpen, setMobileOpen] = useState(false);
  const menuButtonRef = useRef<HTMLButtonElement>(null);
  const mobileMenuRef = useRef<HTMLElement>(null);
  const mobileLayerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setMobileOpen(false);
  }, [pathname]);

  useEffect(() => {
    const desktopQuery = window.matchMedia("(min-width: 901px)");
    const closeAtDesktop = (event: MediaQueryListEvent) => {
      if (event.matches) setMobileOpen(false);
    };

    desktopQuery.addEventListener("change", closeAtDesktop);
    return () => desktopQuery.removeEventListener("change", closeAtDesktop);
  }, []);

  useEffect(() => {
    if (!mobileOpen) return;

    const previousOverflow = document.body.style.overflow;
    const isolatedElements = Array.from(document.body.children)
      .filter((element): element is HTMLElement =>
        element instanceof HTMLElement && element !== mobileLayerRef.current,
      )
      .map((element) => ({
        element,
        ariaHidden: element.getAttribute("aria-hidden"),
        inert: element.inert,
      }));

    document.body.style.overflow = "hidden";

    isolatedElements.forEach(({ element }) => {
      element.setAttribute("aria-hidden", "true");
      element.inert = true;
    });

    const focusFrame = window.requestAnimationFrame(() => {
      mobileMenuRef.current
        ?.querySelector<HTMLElement>('button:not([disabled]), a[href]')
        ?.focus();
    });

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setMobileOpen(false);
        menuButtonRef.current?.focus();
        return;
      }

      if (event.key !== "Tab") return;

      const focusable = mobileMenuRef.current?.querySelectorAll<HTMLElement>(
        'a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])',
      );
      if (!focusable?.length) return;

      const first = focusable[0];
      const last = focusable[focusable.length - 1];

      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.cancelAnimationFrame(focusFrame);
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", handleKeyDown);
      isolatedElements.reverse().forEach(({ element, ariaHidden, inert }) => {
        if (ariaHidden === null) {
          element.removeAttribute("aria-hidden");
        } else {
          element.setAttribute("aria-hidden", ariaHidden);
        }
        element.inert = inert;
      });
      if (menuButtonRef.current?.isConnected) menuButtonRef.current.focus();
    };
  }, [mobileOpen]);

  return (
    <header data-testid="public-nav" className={`${styles.nav} ${overlay ? styles.overlay : ""}`}>
      <div className={styles.navInner}>
        <Link href="/" className={styles.brand} aria-label="MUTX home">
          <span className={styles.brandMark} aria-hidden="true">MX</span>
          <span className={styles.brandCopy}>
            <strong>MUTX</strong>
            <small>Agent operations</small>
          </span>
        </Link>

        <nav className={styles.navLinks} aria-label="Primary navigation">
          {NAV_ITEMS.map((item) => {
            const productActive = item.label === "Product" && pathname.startsWith("/ai-agent-");
            const active = !item.external && (productActive || pathname === item.href || pathname.startsWith(`${item.href}/`));

            return item.external ? (
              <a key={item.href} href={item.href} target="_blank" rel="noopener noreferrer">
                {item.label} <ArrowUpRight aria-hidden="true" />
                <span className={styles.visuallyHidden}> (opens in a new tab)</span>
              </a>
            ) : (
              <Link key={item.href} href={item.href} className={active ? styles.active : undefined} aria-current={active ? "page" : undefined}>
                {item.label}
              </Link>
            );
          })}
        </nav>

        <div className={styles.actions}>
          <a href="https://pico.mutx.dev" target="_blank" rel="noopener noreferrer" className={styles.pico}>
            Pico <ArrowUpRight aria-hidden="true" /><span className={styles.visuallyHidden}> (opens in a new tab)</span>
          </a>
          <Link href="/download" className={styles.download}>
            Download <ArrowRight aria-hidden="true" />
          </Link>
          <button
            ref={menuButtonRef}
            type="button"
            className={styles.menuButton}
            aria-label={mobileOpen ? "Close navigation" : "Open navigation"}
            aria-expanded={mobileOpen}
            aria-controls="public-mobile-navigation"
            onClick={() => setMobileOpen((open) => !open)}
          >
            {mobileOpen ? <X aria-hidden="true" /> : <Menu aria-hidden="true" />}
          </button>
        </div>
      </div>

      {mobileOpen && typeof document !== "undefined" ? createPortal(
        <div ref={mobileLayerRef} className={styles.mobileLayer}>
          <div className={styles.mobileBackdrop} aria-hidden="true" />
          <nav
            ref={mobileMenuRef}
            id="public-mobile-navigation"
            className={styles.mobileMenu}
            role="dialog"
            aria-modal="true"
            aria-labelledby="public-mobile-navigation-title"
          >
            <div className={styles.mobileMenuHeader}>
              <p id="public-mobile-navigation-title">
                <span aria-hidden="true" /> Control plane navigation
              </p>
              <button
                type="button"
                className={styles.mobileClose}
                aria-label="Close navigation"
                onClick={() => setMobileOpen(false)}
              >
                <X aria-hidden="true" />
              </button>
            </div>
            {NAV_ITEMS.map((item, index) => {
              const productActive = item.label === "Product" && pathname.startsWith("/ai-agent-");
              const active = !item.external && (productActive || pathname === item.href || pathname.startsWith(`${item.href}/`));

              return item.external ? (
                <a key={item.href} href={item.href} target="_blank" rel="noopener noreferrer">
                  <span>{String(index + 1).padStart(2, "0")}</span>{item.label}<ArrowUpRight aria-hidden="true" />
                  <span className={styles.visuallyHidden}> (opens in a new tab)</span>
                </a>
              ) : (
                <Link key={item.href} href={item.href} onClick={() => setMobileOpen(false)} aria-current={active ? "page" : undefined}>
                  <span>{String(index + 1).padStart(2, "0")}</span>{item.label}
                </Link>
              );
            })}
            <Link href="/download" onClick={() => setMobileOpen(false)} className={styles.mobileDownload}>
              <span>05</span>Download<ArrowRight aria-hidden="true" />
            </Link>
            <a href="https://pico.mutx.dev" target="_blank" rel="noopener noreferrer">
              <span>06</span>Pico<ArrowUpRight aria-hidden="true" />
              <span className={styles.visuallyHidden}> (opens in a new tab)</span>
            </a>
          </nav>
        </div>,
        document.body,
      ) : null}
    </header>
  );
}
