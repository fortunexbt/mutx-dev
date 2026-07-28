import { execSync, execFileSync } from "child_process";
import http from "http";
import https from "https";
import fs from "fs";
import path from "path";
import { getDocSitemapRoutes } from "./docs";

// ── Types ──────────────────────────────────────────────

export interface SyncResult {
  success: boolean;
  pulled: boolean;
  commit: string | null;
  changedFiles: string[];
  docRoutes: string[];
  error?: string;
}

export interface SyncLogEntry {
  timestamp: string;
  trigger: "webhook" | "cron" | "manual";
  beforeCommit: string | null;
  afterCommit: string | null;
  pulled: boolean;
  changedFiles: string[];
  docRoutes: string[];
  durationMs: number;
  error?: string;
}

// ── Git availability check ─────────────────────────────

let _hasGit: boolean | null = null;

export function hasGit(): boolean {
  if (_hasGit !== null) return _hasGit;
  try {
    execSync("git --version", { stdio: "ignore", timeout: 3000 });
    _hasGit = true;
  } catch {
    _hasGit = false;
  }
  return _hasGit;
}

// ── Rate limiting ──────────────────────────────────────

const SYNC_RATE_LIMIT_WINDOW_MS = 60_000; // 1 minute
const SYNC_RATE_LIMIT_MAX = 10; // 10 syncs per minute
const syncTimestamps: number[] = [];

function checkRateLimit(): boolean {
  const now = Date.now();
  // Prune timestamps outside the window
  while (syncTimestamps.length > 0 && syncTimestamps[0] < now - SYNC_RATE_LIMIT_WINDOW_MS) {
    syncTimestamps.shift();
  }
  if (syncTimestamps.length >= SYNC_RATE_LIMIT_MAX) {
    return false; // rate limited
  }
  syncTimestamps.push(now);
  return true;
}

// ── Mutex + Dedup ──────────────────────────────────────

let syncLock = false;
let lastSyncedCommit: string | null = null;
let consecutiveFailures = 0;
const MAX_CONSECUTIVE_FAILURES = 3;

// Circular buffer of recent sync logs (last 50)
const syncLog: SyncLogEntry[] = [];
const MAX_LOG_ENTRIES = 50;

// SSE broadcaster — set lazily by the events route
let broadcastFn: ((files: string[]) => void) | null = null;

export function setBroadcaster(fn: (files: string[]) => void) {
  broadcastFn = fn;
}

// ── Git helpers ────────────────────────────────────────
// Uses execFileSync for commands with arguments to avoid shell injection.
// execFileSync passes args as an array — no shell parsing, no interpolation.

function getHeadCommit(): string | null {
  try {
    const out = execFileSync("git", ["rev-parse", "HEAD"], {
      encoding: "utf-8",
      timeout: 5_000,
    }).trim();
    return out || null;
  } catch {
    return null;
  }
}

function getBranch(): string | null {
  try {
    const out = execFileSync("git", ["rev-parse", "--abbrev-ref", "HEAD"], {
      encoding: "utf-8",
      timeout: 5_000,
    }).trim();
    return out || null;
  } catch {
    return null;
  }
}

function gitPull(): {
  pulled: boolean;
  changedFiles: string[];
  error?: string;
} {
  const before = getHeadCommit();

  try {
    const output = execFileSync("git", ["pull", "--ff-only"], {
      encoding: "utf-8",
      timeout: 30_000,
    }).trim();

    if (output.includes("Already up to date")) {
      return { pulled: false, changedFiles: [] };
    }

    const after = getHeadCommit();

    if (before && after && before !== after) {
      // Safe: before and after are verified 40-char hex from git rev-parse
      const diffOutput = execFileSync(
        "git",
        ["diff", "--name-only", `${before}..${after}`],
        { encoding: "utf-8", timeout: 10_000 }
      ).trim();
      const changedFiles = diffOutput.split("\n").filter(Boolean);
      return { pulled: true, changedFiles };
    }

    return { pulled: true, changedFiles: ["unknown"] };
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    return { pulled: false, changedFiles: [], error: msg };
  }
}

// ── Change detection ───────────────────────────────────

const DOC_PREFIXES = ["docs/", "agents/"];
const DOC_EXACT_FILES = ["SUMMARY.md"];

function filterDocChanges(files: string[]): string[] {
  return files.filter((f) => {
    if (DOC_EXACT_FILES.includes(f)) return true;
    for (const prefix of DOC_PREFIXES) {
      if (f.startsWith(prefix)) return true;
    }
    return false;
  });
}

// ── Logging ────────────────────────────────────────────

function log(entry: SyncLogEntry) {
  syncLog.push(entry);
  if (syncLog.length > MAX_LOG_ENTRIES) syncLog.shift();

  const level = entry.error ? "ERROR" : entry.pulled ? "INFO" : "DEBUG";
  console.log(
    `[docs-sync] ${level} trigger=${entry.trigger} ` +
      `before=${entry.beforeCommit?.slice(0, 7) ?? "none"} ` +
      `after=${entry.afterCommit?.slice(0, 7) ?? "none"} ` +
      `pulled=${entry.pulled} files=${entry.changedFiles.length} ` +
      `routes=${entry.docRoutes.length} dur=${entry.durationMs}ms` +
      (entry.error ? ` err=${entry.error}` : "")
  );
}

// ── Alerting ───────────────────────────────────────────
// Uses Node's built-in https module instead of shelling out to curl.

async function alertFailure(entry: SyncLogEntry) {
  const webhookUrl = process.env.DOCS_SYNC_ALERT_WEBHOOK;
  if (!webhookUrl) return;

  try {
    const message = {
      content:
        `[docs-sync] ${consecutiveFailures} consecutive failures. ` +
        `Last error: ${entry.error ?? "unknown"}. ` +
        `Commit: ${entry.afterCommit?.slice(0, 7) ?? "unknown"}`,
    };

    const body = JSON.stringify(message);

    const url = new URL(webhookUrl);
    const options = {
      hostname: url.hostname,
      port: url.port || 443,
      path: url.pathname + url.search,
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Content-Length": Buffer.byteLength(body),
      },
    };

    await new Promise<void>((resolve, reject) => {
      const httpModule = url.protocol === "https:" ? https : http;
      const req = httpModule.request(options, (res: http.IncomingMessage) => {
        res.on("data", () => {}); // drain
        res.on("end", resolve);
      });
      req.on("error", reject);
      req.setTimeout(5_000, () => {
        req.destroy();
        reject(new Error("timeout"));
      });
      req.write(body);
      req.end();
    });
  } catch {
    // Alert delivery is best-effort
  }
}

// ── Search index rebuild ───────────────────────────────

function rebuildSearchIndex() {
  try {
    execFileSync(process.execPath, [
      "--experimental-strip-types",
      "scripts/build-docs-search-index.ts",
    ], {
      encoding: "utf-8",
      timeout: 60_000,
      cwd: process.cwd(),
    });
    console.log("[docs-sync] Search index rebuilt");
  } catch (err) {
    console.error("[docs-sync] Search index rebuild failed:", err);
  }
}

// ── Core sync function ─────────────────────────────────

export async function syncDocsFromGit(
  trigger: "webhook" | "cron" | "manual" = "manual"
): Promise<SyncResult> {
  // Rate limit check
  if (!checkRateLimit()) {
    return {
      success: false,
      pulled: false,
      commit: getHeadCommit(),
      changedFiles: [],
      docRoutes: [],
      error: "rate limited",
    };
  }

  // Mutex — prevent concurrent syncs
  if (syncLock) {
    return {
      success: true,
      pulled: false,
      commit: getHeadCommit(),
      changedFiles: [],
      docRoutes: [],
      error: "sync in progress",
    };
  }

  syncLock = true;
  const startTime = Date.now();

  try {
    const beforeCommit = getHeadCommit();

    // Dedup — if we already synced this exact commit, skip
    if (beforeCommit === lastSyncedCommit && trigger !== "manual") {
      return {
        success: true,
        pulled: false,
        commit: beforeCommit,
        changedFiles: [],
        docRoutes: [],
      };
    }

    const result = gitPull();

    if (result.error) {
      consecutiveFailures++;
      const entry: SyncLogEntry = {
        timestamp: new Date().toISOString(),
        trigger,
        beforeCommit,
        afterCommit: getHeadCommit(),
        pulled: false,
        changedFiles: [],
        docRoutes: [],
        durationMs: Date.now() - startTime,
        error: result.error,
      };
      log(entry);

      if (consecutiveFailures >= MAX_CONSECUTIVE_FAILURES) {
        alertFailure(entry);
      }

      return {
        success: false,
        pulled: false,
        commit: getHeadCommit(),
        changedFiles: [],
        docRoutes: [],
        error: result.error,
      };
    }

    // Reset failure counter on success
    consecutiveFailures = 0;

    if (!result.pulled) {
      lastSyncedCommit = beforeCommit;
      const entry: SyncLogEntry = {
        timestamp: new Date().toISOString(),
        trigger,
        beforeCommit,
        afterCommit: beforeCommit,
        pulled: false,
        changedFiles: [],
        docRoutes: [],
        durationMs: Date.now() - startTime,
      };
      log(entry);

      return {
        success: true,
        pulled: false,
        commit: beforeCommit,
        changedFiles: [],
        docRoutes: [],
      };
    }

    // New commits pulled — detect doc changes
    const afterCommit = getHeadCommit();
    lastSyncedCommit = afterCommit;

    const docChanges = filterDocChanges(result.changedFiles);
    const affectedRoutes =
      docChanges.length > 0 ? getDocSitemapRoutes() : [];

    const entry: SyncLogEntry = {
      timestamp: new Date().toISOString(),
      trigger,
      beforeCommit,
      afterCommit,
      pulled: true,
      changedFiles: result.changedFiles,
      docRoutes: affectedRoutes,
      durationMs: Date.now() - startTime,
    };
    log(entry);

    // Async rebuild search index if docs changed
    if (docChanges.length > 0) {
      setTimeout(() => rebuildSearchIndex(), 100);

      // Notify SSE clients (dev mode)
      if (broadcastFn) {
        broadcastFn(docChanges);
      }
    }

    return {
      success: true,
      pulled: true,
      commit: afterCommit,
      changedFiles: result.changedFiles,
      docRoutes: affectedRoutes,
    };
  } finally {
    syncLock = false;
  }
}

// ── Status ─────────────────────────────────────────────

export function getSyncStatus(): {
  branch: string | null;
  commit: string | null;
  docsCount: number;
  routesCount: number;
  lastSync: SyncLogEntry | null;
  consecutiveFailures: number;
} {
  const routes = getDocSitemapRoutes();
  const docsDir = path.join(process.cwd(), "docs");

  let docsCount = 0;
  try {
    const walkDir = (dir: string) => {
      for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
        const full = path.join(dir, entry.name);
        if (entry.isDirectory()) walkDir(full);
        else if (entry.name.endsWith(".md")) docsCount++;
      }
    };
    walkDir(docsDir);
  } catch {
    // docs dir might not exist
  }

  return {
    branch: getBranch(),
    commit: getHeadCommit(),
    docsCount,
    routesCount: routes.length,
    lastSync: syncLog.length > 0 ? syncLog[syncLog.length - 1] : null,
    consecutiveFailures,
  };
}

export function getSyncLog(): SyncLogEntry[] {
  return [...syncLog];
}
