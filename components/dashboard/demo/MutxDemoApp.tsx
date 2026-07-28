"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { useReducedMotion } from "framer-motion";
import {
  ChevronRight,
  Clock3,
  GitBranch,
  Globe,
  Presentation,
  Settings2,
  X,
} from "lucide-react";

import { cn } from "@/lib/utils";
import {
  BASE_SIGNALS,
  NAV_ITEMS,
  QUICK_ACTIONS,
  SECTION_META,
  relativeStamp,
  rotate,
} from "@/components/dashboard/demo/demoContent";
import type { AuditItem, SignalItem } from "@/components/dashboard/demo/demoContent";
import {
  QuickActionButton,
  RailSection,
  SearchBar,
  SignalToneIcon,
  StatusBadge,
  TopControl,
} from "@/components/dashboard/demo/demoPrimitives";
import {
  AgentsSection,
  DeploymentsSection,
  EnvironmentsSection,
  OverviewSection,
  PlaceholderSection,
  RunsSection,
} from "@/components/dashboard/demo/routeSections";
import type { DemoSection } from "@/components/dashboard/demo/demoSections";

const FOCUSABLE_SELECTOR =
  'a[href], button:not([disabled]), input:not([disabled]), [tabindex]:not([tabindex="-1"])';

function DemoMark() {
  return (
    <span
      className="grid h-8 w-8 shrink-0 grid-cols-[5px_1fr] overflow-hidden rounded-[3px] border border-[#48463e] bg-[#11120f]"
      aria-hidden="true"
    >
      <span className="bg-[#ff571c]" />
      <span className="grid grid-cols-2 gap-[3px] p-[5px]">
        <span className="bg-[#eee9dc]" />
        <span className="bg-[#5d5a52]" />
        <span className="bg-[#5d5a52]" />
        <span className="bg-[#58aaff]" />
      </span>
    </span>
  );
}

function DemoStageHeader({ section, tick }: { section: DemoSection; tick: number }) {
  const meta = SECTION_META[section];
  const pulseStamp = relativeStamp(2 + (tick % 5));

  return (
    <section
      data-testid="control-demo-stage"
      className="relative shrink-0 overflow-hidden rounded-[6px] border border-[#2b2b26] bg-[#11120f]"
    >
      <span className="absolute start-0 top-0 h-px w-28 bg-[#ff571c]" aria-hidden="true" />
      <div className="grid gap-4 px-4 py-4 sm:px-5 xl:grid-cols-[minmax(0,1fr)_minmax(390px,0.74fr)] xl:items-end">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2 font-[family:var(--font-mono)] text-[11px] font-semibold uppercase tracking-[0.14em]">
            <span className="rounded-[3px] border border-[#ff6a32] bg-[#28140d] px-2 py-1 text-[#ff9a72]">
              REC / {meta.eyebrow}
            </span>
            <span className="text-[#8d867a]">Sample record · /control only</span>
          </div>
          <h1 className="mt-3 max-w-4xl text-[1.85rem] font-semibold leading-[1.02] tracking-[-0.045em] text-[#eee9dc] sm:text-[2.2rem]">
            {meta.title}
          </h1>
          <p className="mt-2 max-w-3xl text-[13px] leading-6 text-[#aaa397] sm:text-sm">
            {meta.detail}
          </p>
          <div className="mt-3 flex flex-wrap gap-1.5">
            {meta.chips.map((chip) => (
              <span
                key={`${section}-${chip}`}
                className="rounded-[3px] border border-[#34342e] bg-[#171813] px-2 py-1 font-[family:var(--font-mono)] text-[11px] uppercase tracking-[0.12em] text-[#b6afa2]"
              >
                {chip}
              </span>
            ))}
          </div>
        </div>

        <div className="flex gap-2 overflow-x-auto pb-1 sm:grid sm:grid-cols-3 sm:overflow-visible sm:pb-0">
          {meta.heroStats.map((item) => (
            <div
              key={`${section}-${item.label}`}
              className="min-w-[9rem] rounded-[4px] border border-[#34342e] bg-[#0c0d0b] px-3 py-2.5 sm:min-w-0"
            >
              <div className="font-[family:var(--font-mono)] text-[11px] font-semibold uppercase tracking-[0.12em] text-[#8d867a]">
                {item.label}
              </div>
              <div className="mt-2 font-[family:var(--font-mono)] text-[1.45rem] font-medium leading-none tracking-[-0.04em] text-[#eee9dc]">
                {item.value}
              </div>
              <div className="mt-2 text-[11px] leading-4 text-[#999284]">{item.detail}</div>
            </div>
          ))}
        </div>
      </div>
      <div className="flex min-h-9 items-center justify-between gap-3 border-t border-[#2b2b26] bg-[#0c0d0b] px-4 py-2 font-[family:var(--font-mono)] text-[11px] uppercase tracking-[0.12em] text-[#8d867a] sm:px-5">
        <span>Recorded state · {pulseStamp}</span>
        <StatusBadge label="Simulated pulse" tone="focus" />
      </div>
    </section>
  );
}

function DemoBriefRail({ section }: { section: DemoSection }) {
  const meta = SECTION_META[section];

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-y-auto px-4 py-4 sm:px-5">
      <div className="rounded-[4px] border border-[#5a3a2d] bg-[#21140f] px-3 py-3">
        <div className="font-[family:var(--font-mono)] text-[11px] font-semibold uppercase tracking-[0.14em] text-[#ff8355]">
          Opening line
        </div>
        <div data-technical-value className="mt-2 text-sm leading-6 text-[#eee9dc]">{meta.command}</div>
      </div>
      <ol className="mt-3 grid gap-2">
        {meta.narrative.map((item, index) => (
          <li
            key={`${section}-narrative-${index}`}
            className="grid grid-cols-[2rem_minmax(0,1fr)] gap-3 rounded-[4px] border border-[#34342e] bg-[#11120f] px-3 py-3"
          >
            <span className="font-[family:var(--font-mono)] text-[11px] font-semibold tabular-nums text-[#ff6a32]">
              {String(index + 1).padStart(2, "0")}
            </span>
            <span className="text-[13px] leading-5 text-[#c8c0b0]">{item}</span>
          </li>
        ))}
      </ol>
    </div>
  );
}

function PresenterDialog({
  section,
  dialogRef,
  closeRef,
  onClose,
}: {
  section: DemoSection;
  dialogRef: React.RefObject<HTMLElement | null>;
  closeRef: React.RefObject<HTMLButtonElement | null>;
  onClose: () => void;
}) {
  return (
    <div className="fixed inset-0 z-[80] flex justify-end bg-black/75 p-2 sm:p-4" data-testid="control-presenter-overlay">
      <aside
        id="control-presenter-panel"
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="control-presenter-title"
        className="flex h-full w-full max-w-[25rem] flex-col overflow-hidden rounded-[6px] border border-[#48463e] bg-[#090a08] shadow-[0_24px_64px_rgba(0,0,0,0.58)]"
      >
        <header className="flex min-h-16 items-center justify-between gap-3 border-b border-[#34342e] bg-[#0d0e0c] px-4 sm:px-5">
          <div className="min-w-0">
            <p className="font-[family:var(--font-mono)] text-[11px] font-semibold uppercase tracking-[0.14em] text-[#ff6a32]">
              Presenter mode / on
            </p>
            <h2 id="control-presenter-title" className="mt-1 truncate text-sm font-semibold text-[#eee9dc]">
              Demo Script · talk track
            </h2>
          </div>
          <button
            ref={closeRef}
            type="button"
            onClick={onClose}
            className="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-[4px] border border-[#48463e] bg-[#151612] text-[#c8c0b0] hover:border-[#ff6a32] hover:text-[#eee9dc] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#ff9a72]"
            aria-label="Close presenter mode"
          >
            <X className="h-4 w-4" aria-hidden="true" />
          </button>
        </header>
        <DemoBriefRail section={section} />
        <footer className="border-t border-[#34342e] px-4 py-3 font-[family:var(--font-mono)] text-[11px] leading-5 text-[#8d867a] sm:px-5">
          Guidance is local to this demo. Escape closes this rail and returns focus to the presenter toggle.
        </footer>
      </aside>
    </div>
  );
}

export function MutxDemoApp({ section }: { section: DemoSection }) {
  const [tick, setTick] = useState(0);
  const [demoNotice, setDemoNotice] = useState("Sample data is active. No live system is connected.");
  const [presenterOpen, setPresenterOpen] = useState(false);
  const prefersReducedMotion = useReducedMotion() ?? false;
  const sectionMeta = SECTION_META[section];
  const appContentRef = useRef<HTMLDivElement>(null);
  const presenterTriggerRef = useRef<HTMLButtonElement>(null);
  const presenterDialogRef = useRef<HTMLElement>(null);
  const presenterCloseRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (prefersReducedMotion) {
      return;
    }

    const interval = window.setInterval(() => {
      setTick((current) => current + 1);
    }, 2200);

    return () => window.clearInterval(interval);
  }, [prefersReducedMotion]);

  useEffect(() => {
    if (!presenterOpen) {
      return;
    }

    const previousFocus = document.activeElement instanceof HTMLElement
      ? document.activeElement
      : presenterTriggerRef.current;
    appContentRef.current?.setAttribute("inert", "");
    window.requestAnimationFrame(() => presenterCloseRef.current?.focus());

    const handlePresenterKeys = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        setPresenterOpen(false);
        return;
      }

      if (event.key !== "Tab" || !presenterDialogRef.current) {
        return;
      }

      const focusable = Array.from(
        presenterDialogRef.current.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR),
      ).filter((element) => element.getClientRects().length > 0);
      if (focusable.length === 0) {
        return;
      }

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

    window.addEventListener("keydown", handlePresenterKeys);
    return () => {
      window.removeEventListener("keydown", handlePresenterKeys);
      appContentRef.current?.removeAttribute("inert");
      (previousFocus?.isConnected ? previousFocus : presenterTriggerRef.current)?.focus({
        preventScroll: true,
      });
    };
  }, [presenterOpen]);

  const signals = rotate(BASE_SIGNALS, tick).map((signal, index) => ({
    ...signal,
    stamp: relativeStamp(1 + index * 8 + ((tick + index) % 4)),
  }));
  const activeAction = tick % QUICK_ACTIONS.length;

  const auditItems: AuditItem[] = [
    { title: "Rotate API key", resource: "External operator credential", actor: "Creator", role: "operator", stamp: relativeStamp(8 + (tick % 4)) },
    { title: "Deployment promoted", resource: "Sales Ops Assistant v1.4.x", actor: "Release Bot", role: "automation", stamp: relativeStamp(16 + (tick % 5)) },
    { title: "Webhook updated", resource: "Stripe outbound delivery", actor: "Integrator", role: "platform", stamp: relativeStamp(26 + (tick % 6)) },
  ];

  const openPresenter = () => {
    setDemoNotice("Presenter mode on. Demo Script and talk track are available.");
    setPresenterOpen(true);
  };
  const closePresenter = () => {
    setDemoNotice("Presenter mode off. Demo Script and talk track are hidden.");
    setPresenterOpen(false);
  };

  return (
    <div
      aria-label="MUTX simulated control plane demo"
      data-testid="control-demo-root"
      data-demo-tick={tick}
      data-motion={prefersReducedMotion ? "reduced" : "full"}
      data-control-visual-system="flight-recorder"
      data-no-live-writes="true"
      className="relative h-[100dvh] w-full overflow-hidden bg-[#090a08] text-[#eee9dc]"
    >
      <p id="control-demo-boundary" className="sr-only">
        This is a simulated interactive demo with sample data. Controls cannot contact live systems.
      </p>
      <p className="sr-only" role="status" aria-live="polite">
        {demoNotice}
      </p>

      <div ref={appContentRef} className="flex h-full flex-col overflow-hidden">
        <header className="shrink-0 border-b border-[#2b2b26] bg-[#0d0e0c]">
          <div className="flex min-h-16 items-center gap-3 px-3 sm:px-4 lg:px-5">
            <Link
              href="/control"
              className="flex min-h-11 shrink-0 items-center gap-2.5 rounded-[4px] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#ff9a72]"
              aria-label="MUTX control demo overview"
            >
              <DemoMark />
              <span className="hidden sm:block">
                <span className="block text-[15px] font-semibold leading-none tracking-[-0.035em]">MUTX</span>
                <span className="mt-1 block font-[family:var(--font-mono)] text-[11px] uppercase leading-none tracking-[0.12em] text-[#8d867a]">
                  Control demo
                </span>
              </span>
            </Link>

            <div className="hidden min-w-0 flex-1 md:block md:max-w-xl">
              <SearchBar />
            </div>

            <div className="ms-auto flex items-center gap-1.5 sm:gap-2">
              <div className="hidden items-center gap-2 xl:flex">
                <TopControl label="Acme Corp" icon={GitBranch} compact />
                <TopControl label={sectionMeta.eyebrow} icon={Globe} compact />
                <TopControl label="Last 24h" icon={Clock3} compact />
              </div>
              <button
                ref={presenterTriggerRef}
                type="button"
                onClick={openPresenter}
                aria-expanded={presenterOpen}
                aria-controls="control-presenter-panel"
                className="inline-flex min-h-11 items-center gap-2 rounded-[4px] border border-[#48463e] bg-[#151612] px-2.5 font-[family:var(--font-mono)] text-[11px] font-semibold uppercase tracking-[0.08em] text-[#c8c0b0] hover:border-[#ff6a32] hover:text-[#eee9dc] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#ff9a72] sm:px-3"
              >
                <Presentation className="h-4 w-4 text-[#ff6a32]" aria-hidden="true" />
                <span>Presenter</span>
              </button>
              <Link
                href="/control/settings"
                aria-label="Open simulated settings"
                className="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-[4px] border border-[#ff6a32] bg-[#ff571c] text-[#090a08] hover:bg-[#ff7545] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#ff9a72]"
              >
                <Settings2 className="h-4 w-4" aria-hidden="true" />
              </Link>
            </div>
          </div>
          <div className="border-t border-[#252620] px-3 py-2 md:hidden">
            <SearchBar />
          </div>
        </header>

        <div
          data-testid="control-demo-label"
          className="flex min-h-9 shrink-0 items-center justify-center border-b border-[#5a3a2d] bg-[#21140f] px-3 py-2 text-center font-[family:var(--font-mono)] text-[11px] font-semibold uppercase tracking-[0.11em] text-[#ff9a72]"
        >
          Simulated interactive demo · sample data · actions stay local
        </div>

        <div className="shrink-0 border-b border-[#2b2b26] bg-[#0c0d0b] px-2 py-2 lg:hidden">
          <nav className="flex gap-1.5 overflow-x-auto pb-1" aria-label="Control demo sections">
            {NAV_ITEMS.map((item, index) => {
              const active = item.key === section;
              return (
                <Link
                  key={item.key}
                  href={item.href}
                  aria-current={active ? "page" : undefined}
                  className={cn(
                    "inline-flex min-h-11 shrink-0 items-center gap-2 rounded-[4px] border px-3 text-[12px] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#ff9a72]",
                    active
                      ? "dashboard-active-rail border-[#48463e] bg-[#171813] text-[#eee9dc]"
                      : "border-[#2b2b26] bg-[#11120f] text-[#aaa397] hover:border-[#48463e] hover:text-[#eee9dc]",
                  )}
                >
                  <span className="font-[family:var(--font-mono)] text-[11px] tabular-nums text-[#ff8355]">
                    {String(index + 1).padStart(2, "0")}
                  </span>
                  <item.icon className="h-3.5 w-3.5 text-[#8d867a]" aria-hidden="true" />
                  <span className="font-medium">{item.label}</span>
                </Link>
              );
            })}
          </nav>
        </div>

        <div className="grid min-h-0 flex-1 grid-cols-1 overflow-hidden lg:grid-cols-[248px_minmax(0,1fr)] 2xl:grid-cols-[256px_minmax(0,1fr)_292px]">
          <aside className="hidden min-h-0 flex-col border-e border-[#2b2b26] bg-[#080907] lg:flex">
            <div className="min-h-0 flex-1 overflow-y-auto px-3 py-4">
              <p className="mb-2 flex items-center gap-2 border-b border-[#292a25] px-2 pb-2 font-[family:var(--font-mono)] text-[11px] font-semibold uppercase tracking-[0.14em] text-[#8d867a]">
                <span className="text-[#ff6a32]">REC</span>
                Flight recorder
              </p>
              <nav className="space-y-1" aria-label="Control demo navigation">
                {NAV_ITEMS.map((item, index) => {
                  const active = item.key === section;
                  return (
                    <Link
                      key={item.key}
                      href={item.href}
                      aria-current={active ? "page" : undefined}
                      className={cn(
                        "group flex min-h-11 items-center gap-2.5 rounded-[4px] border px-2.5 py-2 text-[12px] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#ff9a72]",
                        active
                          ? "dashboard-active-rail border-[#34342e] bg-[#171813] font-medium text-[#eee9dc]"
                          : "border-transparent text-[#aaa397] hover:border-[#2b2b26] hover:bg-[#12130f] hover:text-[#eee9dc]",
                      )}
                    >
                      <span className="w-5 shrink-0 font-[family:var(--font-mono)] text-[11px] tabular-nums text-[#8d867a]">
                        {String(index + 1).padStart(2, "0")}
                      </span>
                      <item.icon className={cn("h-3.5 w-3.5 shrink-0", active ? "text-[#ff6a32]" : "text-[#737067]")} aria-hidden="true" />
                      <span className="truncate">{item.label}</span>
                      {active ? <ChevronRight className="rtl-directional-icon ms-auto h-3.5 w-3.5 text-[#58aaff]" aria-hidden="true" /> : null}
                    </Link>
                  );
                })}
              </nav>
            </div>
            <div className="border-t border-[#2b2b26] px-4 py-3">
              <div className="flex items-center justify-between font-[family:var(--font-mono)] text-[11px] uppercase tracking-[0.12em] text-[#8d867a]">
                <span>Channel / demo</span>
                <StatusBadge label="Sample" tone="neutral" />
              </div>
              <p className="mt-2 text-[11px] leading-5 text-[#999284]">
                No bearer token, live workspace, or write endpoint is connected.
              </p>
            </div>
          </aside>

          <main id="main-content" className="min-h-0 overflow-y-auto overflow-x-hidden p-2.5 sm:p-3 lg:p-4">
            <div className="flex min-h-full flex-col gap-3">
              <DemoStageHeader section={section} tick={tick} />
              <div className="min-h-0 flex-1">
                {section === "overview" ? (
                  <OverviewSection
                    tick={tick}
                    signals={signals}
                    auditItems={auditItems}
                    activeAction={activeAction}
                  />
                ) : null}
                {section === "agents" ? <AgentsSection tick={tick} /> : null}
                {section === "deployments" ? <DeploymentsSection tick={tick} /> : null}
                {section === "runs" ? <RunsSection tick={tick} /> : null}
                {section === "environments" ? <EnvironmentsSection tick={tick} /> : null}
                {section === "access" || section === "connectors" || section === "audit" || section === "usage" || section === "settings" ? (
                  <PlaceholderSection section={section} tick={tick} />
                ) : null}
              </div>
            </div>
          </main>

          <aside className="hidden min-h-0 overflow-hidden border-s border-[#2b2b26] bg-[#080907] p-3 2xl:block">
            <div className="grid h-full min-h-0 grid-rows-[minmax(0,1fr)_auto] gap-3 overflow-hidden">
              <RailSection title="Signal ledger" meta={`${signals.length} records`}>
                <div className="flex h-full min-h-0 flex-col gap-2 overflow-y-auto">
                  {signals.map((signal: SignalItem) => (
                    <div key={`${signal.title}-${signal.stamp}`} className="rounded-[4px] border border-[#34342e] bg-[#11120f] p-3">
                      <div className="flex items-start gap-3">
                        <SignalToneIcon tone={signal.tone} />
                        <div className="min-w-0">
                          <div className="flex items-start justify-between gap-2">
                            <div className="text-[13px] font-semibold text-[#eee9dc]">{signal.title}</div>
                            <div className="shrink-0 font-[family:var(--font-mono)] text-[11px] text-[#8d867a]">
                              {signal.stamp}
                            </div>
                          </div>
                          <div className="mt-1 text-[12px] leading-5 text-[#aaa397]">{signal.detail}</div>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </RailSection>

              <RailSection title="Interventions" meta="local simulation">
                <div className="grid gap-2">
                  {QUICK_ACTIONS.slice(0, 3).map((action, index) => (
                    <QuickActionButton key={action.label} action={action} active={index === activeAction} />
                  ))}
                </div>
              </RailSection>
            </div>
          </aside>
        </div>
      </div>

      {presenterOpen ? (
        <PresenterDialog
          section={section}
          dialogRef={presenterDialogRef}
          closeRef={presenterCloseRef}
          onClose={closePresenter}
        />
      ) : null}
    </div>
  );
}
