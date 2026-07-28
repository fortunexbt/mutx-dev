import { EventEmitter } from "node:events";
import httpModule from "node:http";

import * as serverManagerModule from "../../desktop/main/serverManager.cjs";

jest.mock("electron", () => ({
  app: {
    isPackaged: false,
  },
}));

type MockGet = (url: URL, onResponse: (response: EventEmitter) => void) => MockRequest;

const getMock = jest.spyOn(httpModule, "get") as unknown as jest.MockedFunction<MockGet>;
const {
  probeServerReadiness,
  waitForServer,
}: {
  probeServerReadiness: (url: string, timeoutMs?: number) => Promise<unknown>;
  waitForServer: (url: string, childProcess: null, timeoutMs?: number) => Promise<void>;
} = serverManagerModule;

type ResponsePlan =
  | { kind: "response"; statusCode: number; payload: unknown }
  | { kind: "timeout" }
  | { kind: "network-error" };

interface MockRequest extends EventEmitter {
  setTimeout: jest.Mock<MockRequest, [number, () => void]>;
  destroy: jest.Mock<void, []>;
}

function installHttpPlans(...plans: ResponsePlan[]) {
  const requestedUrls: string[] = [];
  let attempt = 0;

  getMock.mockImplementation((url: URL, onResponse: (response: EventEmitter) => void) => {
    requestedUrls.push(String(url));
    const plan = plans[Math.min(attempt, plans.length - 1)];
    attempt += 1;
    const request = new EventEmitter() as MockRequest;
    request.setTimeout = jest.fn(
      (_timeoutMs: number, onTimeout: () => void): MockRequest => {
        if (plan.kind === "timeout") {
          queueMicrotask(onTimeout);
        }
        return request;
      },
    );
    request.destroy = jest.fn(() => {
      queueMicrotask(() => request.emit("error", new Error("request destroyed")));
    });

    if (plan.kind === "network-error") {
      queueMicrotask(() => request.emit("error", new Error("connect ECONNREFUSED /private")));
    } else if (plan.kind === "response") {
      queueMicrotask(() => {
        const response = Object.assign(new EventEmitter(), {
          statusCode: plan.statusCode,
          setEncoding: jest.fn(),
        });
        onResponse(response);
        response.emit("data", JSON.stringify(plan.payload));
        response.emit("end");
      });
    }

    return request;
  });

  return { requestedUrls, attempts: () => attempt };
}

describe("desktop UI readiness probing", () => {
  beforeEach(() => {
    getMock.mockReset();
  });

  afterAll(() => {
    getMock.mockRestore();
  });

  it("accepts only the canonical 200 healthy and ready contract", async () => {
    const requests = installHttpPlans({
      kind: "response",
      statusCode: 200,
      payload: { status: "healthy", database: "ready" },
    });

    await expect(probeServerReadiness("http://127.0.0.1:18900", 200)).resolves.toEqual({
      health: "healthy",
      readiness: "ready",
    });
    expect(requests.requestedUrls).toEqual([
      "http://127.0.0.1:18900/api/dashboard/health",
    ]);
  });

  it.each([
    [{ status: "degraded", database: "ready" }, "health: degraded; readiness: ready"],
    [{ status: "healthy", database: "initializing" }, "health: healthy; readiness: initializing"],
  ])("rejects a 200 response with unhealthy or not-ready truth", async (payload, reason) => {
    installHttpPlans({ kind: "response", statusCode: 200, payload });

    await expect(probeServerReadiness("http://127.0.0.1:18900", 200)).rejects.toThrow(reason);
  });

  it.each([404, 500])("rejects HTTP %i instead of treating it as ready", async (statusCode) => {
    installHttpPlans({
      kind: "response",
      statusCode,
      payload: { status: "healthy", database: "ready" },
    });

    await expect(probeServerReadiness("http://127.0.0.1:18900", 200)).rejects.toThrow(
      `health endpoint returned HTTP ${statusCode}`,
    );
  });

  it("times out a hung health response with an actionable reason", async () => {
    installHttpPlans({ kind: "timeout" });

    await expect(probeServerReadiness("http://127.0.0.1:18900", 40)).rejects.toThrow(
      "health check timed out",
    );
  });

  it("retries a transient not-ready response and recovers", async () => {
    const requests = installHttpPlans(
      {
        kind: "response",
        statusCode: 200,
        payload: { status: "healthy", database: "initializing" },
      },
      {
        kind: "response",
        statusCode: 200,
        payload: { status: "healthy", database: "ready" },
      },
    );

    await expect(
      waitForServer("http://127.0.0.1:18900/private/path", null, 1000),
    ).resolves.toBeUndefined();
    expect(requests.attempts()).toBe(2);
  });

  it("reports the last failed contract without exposing the host URL or path", async () => {
    installHttpPlans({
      kind: "response",
      statusCode: 200,
      payload: { status: "degraded", database: "initializing" },
    });

    let failure: Error | null = null;
    try {
      await waitForServer("http://127.0.0.1:18900/private/path", null, 20);
    } catch (error) {
      failure = error instanceof Error ? error : new Error("unknown failure");
    }

    expect(failure?.message).toContain(
      "Restart MUTX; if it persists, reinstall the application.",
    );
    expect(failure?.message).not.toContain("127.0.0.1");
    expect(failure?.message).not.toContain("/private/path");
  });
});
