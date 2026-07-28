import {
  getGovernancePresentation,
} from "../../components/desktop/DesktopStatusRow";
import type {
  DesktopStatus,
  GovernanceRuntimeState,
} from "../../components/desktop/types";
import { markStaleDesktopSources } from "../../components/desktop/useDesktopStatus";
import * as statusPollModule from "../../desktop/main/statusPoll.cjs";
import * as statusStoreModule from "../../desktop/main/statusStore.cjs";

jest.mock("electron", () => ({
  app: {
    getPath: () => "/tmp/mutx-desktop-status-test",
  },
}));

interface StatusPollModule {
  buildDesktopStatusSnapshot: (input: Record<string, unknown>) => Record<string, unknown>;
  collectStatusSources: (
    requests: Record<string, () => unknown>,
    observedAt?: string,
  ) => Promise<{
    observedAt: string;
    results: Record<string, { ok: boolean; value: unknown; error: string | null }>;
  }>;
  mapGovernanceState: (payload: unknown) => {
    available: boolean;
    health: GovernanceRuntimeState;
    socketPath: null;
  };
}

interface StatusStoreModule {
  applyPollSnapshot: (snapshot: Record<string, unknown>) => void;
  getState: (nowMs?: number) => DesktopStatus;
  updateSource: (sourceName: string, update: Record<string, unknown>) => void;
  STATUS_SOURCE_STALE_AFTER_MS: number;
}

const {
  buildDesktopStatusSnapshot,
  collectStatusSources,
  mapGovernanceState,
} = statusPollModule as unknown as StatusPollModule;
const statusStore = statusStoreModule as unknown as StatusStoreModule;

const READY_SERVER = {
  ready: true,
  state: "ready",
  url: "http://127.0.0.1:18900",
  port: 18900,
  lastError: null,
  lastExitCode: null,
  attempt: 1,
  observedAt: "2026-07-28T10:00:00.000Z",
};

const READY_BRIDGE = {
  ready: true,
  state: "ready",
  pythonCommand: "python3",
  scriptPath: "desktop_bridge.py",
  lastError: null,
  lastExitCode: null,
};

function sourceRequests(overrides: Record<string, () => unknown> = {}) {
  return {
    context: () => ({ mode: "local", apiUrl: "http://127.0.0.1:8000" }),
    auth: () => ({ authenticated: true, api_url: "https://api.mutx.dev", user: { name: "Ada" } }),
    runtime: () => ({
      openclaw: {
        binary_path: "/Users/private/.local/bin/openclaw",
        gateway: { status: "healthy", gateway_url: "http://127.0.0.1:18789/private" },
        current_binding: {
          assistant_id: "assistant-1",
          assistant_name: "Local Operator",
          workspace: "/Users/private/workspace",
        },
      },
    }),
    governance: () => ({ status: "running" }),
    sessions: () => [{ id: "session-1" }],
    controlPlane: () => ({ ready: true, exists: true, path: "/Users/private/mutx" }),
    ...overrides,
  };
}

async function buildSnapshot(overrides: Record<string, () => unknown> = {}) {
  const polled = await collectStatusSources(
    sourceRequests(overrides),
    "2026-07-28T10:00:00.000Z",
  );
  return buildDesktopStatusSnapshot({
    ...polled,
    serverState: READY_SERVER,
    bridgeState: READY_BRIDGE,
    appVersion: "1.4.0",
  });
}

describe("desktop runtime status mapping", () => {
  it.each([
    ["running", true, "Running", "good"],
    ["stopped", false, "Stopped", "warn"],
    ["degraded", false, "Degraded", "warn"],
    ["not_installed", false, "Not installed", "default"],
    ["error", false, "Error", "bad"],
  ])(
    "maps governance %s without Boolean(object) optimism",
    (state, available, label, tone) => {
      expect(mapGovernanceState({ status: state })).toEqual({
        available,
        health: state,
        socketPath: null,
      });
      expect(getGovernancePresentation(state as GovernanceRuntimeState)).toMatchObject({
        label,
        tone,
      });
    },
  );

  it("settles sources independently when one source fails", async () => {
    const polled = await collectStatusSources(
      sourceRequests({ runtime: () => Promise.reject(new Error("/Users/private exploded")) }),
      "2026-07-28T10:00:00.000Z",
    );

    expect(polled.results.auth.ok).toBe(true);
    expect(polled.results.governance.ok).toBe(true);
    expect(polled.results.runtime).toEqual({
      ok: false,
      value: null,
      error: "Runtime inspection is unavailable. Retry from Desktop Settings.",
    });
    expect(polled.results.runtime.error).not.toContain("/Users/private");
  });

  it("clears failed-source fields atomically instead of retaining prior values", async () => {
    const healthy = await buildSnapshot();
    statusStore.applyPollSnapshot(healthy);
    expect(statusStore.getState().openclaw).toMatchObject({
      binaryPath: "openclaw",
      health: "healthy",
    });
    expect(statusStore.getState().assistant).toMatchObject({
      found: true,
      sessionCount: 1,
    });

    const partial = await buildSnapshot({
      runtime: () => Promise.reject(new Error("runtime failed at /Users/private/workspace")),
    });
    statusStore.applyPollSnapshot(partial);
    const failedState = statusStore.getState();

    expect(failedState.authenticated).toBe(true);
    expect(failedState.faramesh.health).toBe("running");
    expect(failedState.openclaw).toEqual({
      binaryPath: null,
      health: "unavailable",
      gatewayUrl: null,
    });
    expect(failedState.assistant).toMatchObject({
      found: false,
      name: null,
      sessionCount: null,
      state: "error",
    });
    expect(failedState.sources.runtime.freshness).toBe("unavailable");
    expect(failedState.runtime.lastError).not.toContain("/Users/private");
  });

  it("recovers an unavailable source to fresh state and current fields", async () => {
    const failed = await buildSnapshot({
      governance: () => Promise.reject(new Error("socket /Users/private/faramesh.sock failed")),
    });
    statusStore.applyPollSnapshot(failed);
    expect(statusStore.getState().faramesh).toMatchObject({ available: false, health: "error" });
    expect(statusStore.getState().sources.governance.freshness).toBe("unavailable");

    const recovered = await buildSnapshot({ governance: () => ({ status: "degraded" }) });
    statusStore.applyPollSnapshot(recovered);
    const recoveredState = statusStore.getState(Date.parse("2026-07-28T10:00:00.000Z"));
    expect(recoveredState.faramesh).toMatchObject({ available: false, health: "degraded" });
    expect(recoveredState.sources.governance).toMatchObject({
      freshness: "fresh",
      lastError: null,
    });
  });

  it("transitions a once-fresh source to stale and then recovers", () => {
    const observedAt = "2026-07-28T10:00:00.000Z";
    const observedAtMs = Date.parse(observedAt);
    statusStore.updateSource("runtime", { available: true, observedAt, lastError: null });

    const freshState = statusStore.getState(observedAtMs);
    expect(freshState.sources.runtime.freshness).toBe("fresh");
    expect(
      markStaleDesktopSources(
        freshState,
        observedAtMs + statusStore.STATUS_SOURCE_STALE_AFTER_MS + 1,
      ).sources.runtime.freshness,
    ).toBe("stale");
    expect(
      statusStore.getState(observedAtMs + statusStore.STATUS_SOURCE_STALE_AFTER_MS + 1).sources
        .runtime.freshness,
    ).toBe("stale");

    const recoveredAt = "2026-07-28T10:05:00.000Z";
    statusStore.updateSource("runtime", {
      available: true,
      observedAt: recoveredAt,
      lastError: null,
    });
    expect(statusStore.getState(Date.parse(recoveredAt)).sources.runtime).toMatchObject({
      freshness: "fresh",
      observedAt: recoveredAt,
      lastSuccessAt: recoveredAt,
      lastError: null,
    });
  });
});
