"use client";

import { AlertTriangle, CheckCircle2, Loader2, X } from "lucide-react";

import type { Job } from "@/components/desktop/useDesktopJob";
import { DESKTOP_FOCUS_CLASS } from "@/components/desktop/desktopVisualContract";
import { cn } from "@/lib/utils";

const JOB_LABELS: Record<string, string> = {
  setup: "Setup Wizard",
  doctor: "Desktop Doctor",
  controlPlaneStart: "Start Local Stack",
  controlPlaneStop: "Stop Local Stack",
  runtimeResync: "Runtime Resync",
  governanceRestart: "Governance Restart",
};

function getJobLabel(jobId: string) {
  return JOB_LABELS[jobId] || jobId.replace(/([a-z0-9])([A-Z])/g, "$1 $2").replace(/[-_]+/g, " ");
}

export function DesktopJobNotice({
  job,
  onDismiss,
  tone = "dark",
}: {
  job: Job;
  onDismiss?: () => void;
  tone?: "dark" | "light";
}) {
  if (!job.id || job.status === "idle") {
    return null;
  }

  const running = job.status === "running" || job.status === "pending";
  const completed = job.status === "completed";
  const failed = job.status === "failed";
  const title = failed
    ? `${getJobLabel(job.id)} failed`
    : completed
      ? `${getJobLabel(job.id)} completed`
      : `${getJobLabel(job.id)} in progress`;
  const summary =
    job.error ||
    job.message ||
    (completed ? "Completed successfully." : "Working through the desktop action.");
  const percent = Math.max(8, Math.min(job.progress || (completed ? 100 : 24), 100));

  return (
    <div
      role={failed ? "alert" : "status"}
      aria-live={failed ? "assertive" : "polite"}
      data-desktop-job-tone={tone}
      className={cn(
        "rounded-[6px] border px-4 py-3.5",
        failed
          ? "border-[#66302e] bg-[#241312]"
          : completed
            ? "border-[#285a43] bg-[#0f2018]"
            : "border-[#294d6c] bg-[#101c26]",
      )}
    >
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            {running ? (
              <Loader2
                className="h-4 w-4 text-[#8ac7ff] motion-safe:animate-spin motion-reduce:animate-none"
                aria-hidden="true"
              />
            ) : completed ? (
              <CheckCircle2
                className="h-4 w-4 text-[#78e3b4]"
                aria-hidden="true"
              />
            ) : (
              <AlertTriangle
                className="h-4 w-4 text-[#ff9b96]"
                aria-hidden="true"
              />
            )}
            <p
              className="text-[12.5px] font-semibold tracking-[-0.01em] text-[#eee9dc]"
            >
              {title}
            </p>
          </div>
          <p
            className="mt-2 text-[12px] leading-5 text-[#c8c0b0]"
          >
            {summary}
          </p>
        </div>

        {onDismiss ? (
          <button
            type="button"
            onClick={onDismiss}
            aria-label={`Dismiss ${getJobLabel(job.id)} status`}
            className={cn("inline-flex items-center gap-1 rounded-[4px] border border-[#48463e] bg-[#11120f] px-2 py-1 text-[11px] text-[#c8c0b0] transition-colors hover:text-[#eee9dc]", DESKTOP_FOCUS_CLASS)}
          >
            <X className="h-3.5 w-3.5" aria-hidden="true" />
            Dismiss
          </button>
        ) : null}
      </div>

      <div
        className="mt-3 overflow-hidden rounded-[4px] bg-[#090a08]"
        role="progressbar"
        aria-label={`${getJobLabel(job.id)} progress`}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={percent}
      >
        <div
          className={cn(
            "h-1.5 rounded-[4px] motion-safe:transition-[width] motion-safe:duration-300 motion-reduce:transition-none",
            failed
              ? "bg-[#ff6d66]"
              : completed
                ? "bg-[#4bd69b]"
                : "bg-[#58aaff]",
          )}
          style={{ width: `${percent}%` }}
        />
      </div>
    </div>
  );
}
