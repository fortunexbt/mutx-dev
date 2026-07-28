"use client";

import { History, RotateCcw, Loader2 } from "lucide-react";
import { useState, useEffect } from "react";
import { Surface as Card } from "@/components/dashboard/livePrimitives";
import { extractApiErrorMessage, normalizeCollection } from "@/components/app/http";
import { type components } from "@/app/types/api";

type DeploymentVersion = components["schemas"]["DeploymentVersionResponse"];

interface VersionHistoryResponse {
  deployment_id: string;
  items: DeploymentVersion[];
  total: number;
}

function formatDate(value?: string | null) {
  if (!value) return "N/A";
  return new Date(value).toLocaleString();
}

function parseConfigSnapshot(snapshot: string | Record<string, unknown> | null | undefined): Record<string, unknown> {
  if (snapshot && typeof snapshot === "object") return snapshot;
  if (typeof snapshot !== "string") return {};
  try {
    return JSON.parse(snapshot);
  } catch {
    return {};
  }
}

function VersionItem({ version, onRollback }: { version: DeploymentVersion; onRollback: () => void }) {
  const isCurrent = version.status === "current";
  const config = parseConfigSnapshot(version.config_snapshot);
  const runtimeVersion = typeof config.version === "string" ? config.version : null;
  const replicas = typeof config.replicas === "number" ? config.replicas : null;
  const metadata = [formatDate(version.created_at)];
  if (runtimeVersion) {
    metadata.push(`runtime ${runtimeVersion}`);
  }
  if (replicas !== null) {
    metadata.push(`${replicas} replica${replicas === 1 ? "" : "s"}`);
  }
  if (version.rolled_back_at) {
    metadata.push(`rolled back ${formatDate(version.rolled_back_at)}`);
  }

  return (
    <div className={`flex items-center justify-between rounded-lg border p-3 ${isCurrent ? "border-emerald-400/30 bg-emerald-400/5" : "border-white/5 bg-white/[0.02]"}`}>
      <div className="flex items-center gap-3">
        <div className={`flex h-8 w-8 items-center justify-center rounded-full text-xs font-medium ${isCurrent ? "bg-emerald-400/20 text-emerald-300" : "bg-white/10 text-slate-400"}`}>
          v{version.version}
        </div>
        <div>
          <p className="text-sm font-medium text-white">
            {isCurrent ? "Current Version" : `Version ${version.version}`}
          </p>
          <p className="text-xs text-slate-500">{metadata.join(" • ")}</p>
        </div>
      </div>
      {!isCurrent && (
        <button
          onClick={onRollback}
          className="inline-flex items-center gap-1.5 rounded-lg border border-white/10 bg-white/5 px-2.5 py-1.5 text-xs font-medium text-white transition hover:bg-white/10"
        >
          <RotateCcw className="h-3 w-3" />
          Rollback
        </button>
      )}
    </div>
  );
}

interface DeploymentHistoryProps {
  deploymentId: string;
  buttonLabel?: string;
  buttonClassName?: string;
  onRollbackComplete?: () => void | Promise<void>;
}

const defaultButtonClassName =
  "inline-flex items-center gap-2 rounded-lg border border-white/10 bg-white/5 px-3 py-1.5 text-xs font-medium text-white transition hover:bg-white/10";

export function DeploymentHistory({
  deploymentId,
  buttonLabel = "Versions",
  buttonClassName = defaultButtonClassName,
  onRollbackComplete,
}: DeploymentHistoryProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [versions, setVersions] = useState<DeploymentVersion[]>([]);
  const [loading, setLoading] = useState(false);
  const [rollingBack, setRollingBack] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (isOpen && versions.length === 0) {
      setLoading(true);
      fetch(`/api/dashboard/deployments/${deploymentId}?path=versions`, {
        cache: "no-store",
      })
        .then(async (res) => {
          const payload = await res.json().catch(() => ({}));
          if (!res.ok) {
            throw new Error(extractApiErrorMessage(payload, "Failed to load version history"));
          }
          return payload;
        })
        .then((data: VersionHistoryResponse | unknown) => {
          setVersions(normalizeCollection<DeploymentVersion>(data, ["items", "versions", "data"]));
          setError("");
        })
        .catch((err) => {
          setError("Failed to load version history");
          console.error("Version history error:", err);
        })
        .finally(() => setLoading(false));
    }
  }, [isOpen, deploymentId, versions.length]);

  const handleRollback = async (version: number) => {
    setRollingBack(true);
    setError("");
    try {
      const response = await fetch(
        `/api/dashboard/deployments/${deploymentId}?action=rollback`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ version }),
          cache: "no-store",
        }
      );

      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(extractApiErrorMessage(data, "Rollback failed"));
      }

      if (onRollbackComplete) {
        await onRollbackComplete();
      }
      setVersions([]);
      setIsOpen(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Rollback failed");
    } finally {
      setRollingBack(false);
    }
  };

  return (
    <>
      <button
        onClick={() => setIsOpen(true)}
        className={buttonClassName}
      >
        <History className="h-3.5 w-3.5" />
        {buttonLabel}
      </button>

      {isOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
          <Card className="w-full max-w-md border border-white/10 bg-[#0a0a0a] p-5">
            <div className="mb-4 flex items-center justify-between">
              <h3 className="text-lg font-semibold text-white">Version History</h3>
              <button
                onClick={() => {
                  setIsOpen(false);
                  setVersions([]);
                }}
                className="text-sm text-slate-500 hover:text-white"
              >
                Close
              </button>
            </div>
            <p className="mb-4 text-sm text-slate-400">
              Deployment: <span className="font-mono text-white">{deploymentId}</span>
            </p>
            {loading ? (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="h-5 w-5 text-slate-500 motion-safe:animate-spin motion-reduce:animate-none" />
              </div>
            ) : error ? (
              <p className="text-sm text-rose-400">{error}</p>
            ) : versions.length === 0 ? (
              <p className="text-sm text-slate-500">No version history available</p>
            ) : (
              <div className="space-y-2">
                {versions.map((version) => (
                  <VersionItem
                    key={version.id}
                    version={version}
                    onRollback={() => handleRollback(version.version)}
                  />
                ))}
              </div>
            )}
            {rollingBack && (
              <p className="mt-4 text-center text-sm text-emerald-400 flex items-center justify-center gap-2">
                <Loader2 className="h-4 w-4 motion-safe:animate-spin motion-reduce:animate-none" />
                Rolling back...
              </p>
            )}
          </Card>
        </div>
      )}
    </>
  );
}
