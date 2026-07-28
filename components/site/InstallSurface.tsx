"use client";

import Link from "next/link";
import { useState } from "react";
import { ArrowRight } from "lucide-react";

import { CommandCopyButton } from "@/components/site/CommandCopyButton";
import { cn } from "@/lib/utils";

const CLI_COMMAND = "curl -fsSL https://mutx.dev/install.sh | bash";
const GITHUB_RELEASES_URL = "https://github.com/mutx-dev/mutx-dev/releases";

type InstallLane = "mac" | "cli";

const installLanes: Array<{ id: InstallLane; label: string }> = [
  { id: "mac", label: "Mac App" },
  { id: "cli", label: "CLI" },
];

export function InstallSurface() {
  const [activeLane, setActiveLane] = useState<InstallLane>("mac");
  const showingMacLane = activeLane === "mac";

  return (
    <article
      id="install"
      className="site-command-card site-command-card-hero scroll-mt-28"
    >
      <div className="site-command-card-head site-command-card-head-hero">
        <div>
          <p>Install lane</p>
          <p>{showingMacLane ? "Conditional desktop release" : "CLI bootstrap lane"}</p>
        </div>
        <div className="site-command-card-actions">
          {showingMacLane ? (
            <Link href="/releases" className="site-command-copy">
              Release page
            </Link>
          ) : (
            <CommandCopyButton value={CLI_COMMAND} />
          )}
        </div>
      </div>

      <div className="border-b border-white/[0.08] px-3 py-3 sm:px-4">
        <div
          role="tablist"
          aria-label="Choose an install lane"
          className="inline-flex rounded-full border border-white/10 bg-white/[0.04] p-1"
        >
          {installLanes.map((lane) => {
            const selected = lane.id === activeLane;

            return (
              <button
                key={lane.id}
                id={`install-tab-${lane.id}`}
                type="button"
                role="tab"
                aria-selected={selected}
                aria-controls={`install-panel-${lane.id}`}
                onClick={() => setActiveLane(lane.id)}
                className={cn(
                  "rounded-full px-4 py-2 text-sm font-semibold transition",
                  selected
                    ? "bg-white text-slate-950 shadow-[0_10px_24px_rgba(255,255,255,0.12)]"
                    : "text-[color:var(--site-text-soft)] hover:text-white",
                )}
              >
                {lane.label}
              </button>
            );
          })}
        </div>
      </div>

      {showingMacLane ? (
        <div
          id="install-panel-mac"
          role="tabpanel"
          aria-labelledby="install-tab-mac"
          className="site-command-card-body"
        >
          <div className="space-y-5">
            <div>
              <p className="font-mono text-[0.68rem] font-semibold uppercase tracking-[0.18em] text-[color:var(--site-text-muted)]">
                Desktop operator app
              </p>
              <h3 className="mt-3 text-2xl font-semibold tracking-[-0.05em] text-white">
                Check the current macOS release.
              </h3>
              <p className="mt-3 text-sm leading-7 text-[color:var(--site-text-soft)]">
                The download lane opens only when MUTX resolves the complete expected
                desktop asset set. Confirm publisher signing and notarization evidence
                in the linked release before installation.
              </p>
            </div>

            <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap">
              <Link href="/download/macos/arm64" className="site-button-primary w-full sm:w-auto">
                Apple Silicon
                <ArrowRight className="rtl-directional-icon h-4 w-4" />
              </Link>
              <Link href="/download/macos/intel" className="site-button-secondary w-full sm:w-auto">
                Intel Mac
              </Link>
            </div>

            <div className="flex flex-wrap gap-3 text-sm text-[color:var(--site-text-muted)]">
              <Link href="/releases" className="site-inline-link">
                Release page
              </Link>
              <Link href="/download" className="site-inline-link">
                Choose a build
              </Link>
              <a
                href={GITHUB_RELEASES_URL}
                className="site-inline-link"
              >
                GitHub releases
              </a>
            </div>
          </div>

          <div className="rounded-[1.2rem] border border-white/10 bg-white/[0.04] p-4 sm:p-5">
            <p className="font-mono text-[0.68rem] font-semibold uppercase tracking-[0.18em] text-[color:var(--site-text-muted)]">
              Release posture
            </p>
            <div className="mt-4 flex flex-wrap gap-2">
              <span className="site-route-pill">complete asset set required</span>
              <span className="site-route-pill">checksums when published</span>
              <span className="site-route-pill">manual download</span>
            </div>
              <p className="mt-4 text-sm leading-7 text-[color:var(--site-text-soft)]">
              Apple Silicon is the primary lane. Intel stays available for
              compatibility, and the first-party download routes hand off to the
              current stable GitHub release assets while the public release page and
              docs notes stay in sync.
            </p>
          </div>
        </div>
      ) : (
        <div
          id="install-panel-cli"
          role="tabpanel"
          aria-labelledby="install-tab-cli"
          className="site-command-card-body"
        >
          <pre className="site-command-card-hero-pre">{CLI_COMMAND}</pre>
          <p className="site-command-card-note">
            The installer stays in the same terminal, recommends{" "}
            <span className="font-semibold text-white">Hosted</span>, installs or
            imports OpenClaw, and opens the operator TUI for you.
          </p>
        </div>
      )}
    </article>
  );
}
