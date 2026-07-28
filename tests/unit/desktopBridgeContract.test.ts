import { spawn } from "child_process";
import { EventEmitter } from "events";
import * as bridgeManagerModule from "../../desktop/main/bridgeManager.cjs";

jest.mock("child_process", () => ({
  spawn: jest.fn(),
}));

interface BridgeRequest {
  id: number;
  method: string;
  params: Record<string, unknown>;
}

interface BridgeReply {
  result?: unknown;
  error?: string;
}

interface BridgeManagerModule {
  startBridge(): Promise<void>;
  finderReveal(filePath: unknown): Promise<Record<string, unknown>>;
  shellOpenTerminal(cwd?: unknown): Promise<Record<string, unknown>>;
}

class FakeBridgeProcess extends EventEmitter {
  exitCode: number | null = null;
  readonly stdout = new EventEmitter();
  readonly stderr = new EventEmitter();
  readonly requests: BridgeRequest[] = [];
  responder: (request: BridgeRequest) => BridgeReply = () => ({ result: { success: true } });

  readonly stdin = {
    write: jest.fn((chunk: string | Buffer) => {
      const line = chunk.toString().trim();
      if (line === "exit") {
        return true;
      }

      const request = JSON.parse(line) as BridgeRequest;
      this.requests.push(request);
      const reply = this.responder(request);
      queueMicrotask(() => {
        this.stdout.emit(
          "data",
          Buffer.from(`${JSON.stringify({ id: request.id, ...reply })}\n`),
        );
      });
      return true;
    }),
  };

  readonly kill = jest.fn(() => {
    this.exitCode = 0;
    this.emit("exit", 0);
    return true;
  });
}

const bridgeManager = bridgeManagerModule as unknown as BridgeManagerModule;
const spawnMock = spawn as jest.MockedFunction<typeof spawn>;
const bridgeProcess = new FakeBridgeProcess();

describe("desktop native bridge action contract", () => {
  beforeAll(async () => {
    spawnMock.mockReturnValue(bridgeProcess as never);
    bridgeProcess.responder = (request) =>
      request.method === "controlPlane.status"
        ? { result: { ready: true } }
        : { result: { success: true } };
    await bridgeManager.startBridge();
  });

  beforeEach(() => {
    bridgeProcess.requests.length = 0;
    bridgeProcess.responder = () => ({ result: { success: true } });
  });

  afterAll(() => {
    bridgeProcess.exitCode = 0;
    bridgeProcess.emit("exit", 0);
  });

  it("reveals through the exact registered method and payload", async () => {
    await expect(bridgeManager.finderReveal("/tmp/MUTX workspace")).resolves.toEqual({
      success: true,
    });

    expect(bridgeProcess.requests).toEqual([
      {
        id: expect.any(Number),
        method: "finder.reveal",
        params: { path: "/tmp/MUTX workspace" },
      },
    ]);
  });

  it("opens Terminal through the exact registered method with optional cwd payloads", async () => {
    await expect(bridgeManager.shellOpenTerminal("/tmp/MUTX workspace")).resolves.toEqual({
      success: true,
    });
    await expect(bridgeManager.shellOpenTerminal()).resolves.toEqual({ success: true });

    expect(bridgeProcess.requests).toEqual([
      {
        id: expect.any(Number),
        method: "shell.openTerminal",
        params: { cwd: "/tmp/MUTX workspace" },
      },
      {
        id: expect.any(Number),
        method: "shell.openTerminal",
        params: {},
      },
    ]);
  });

  it("rejects an application-level failure even when transport succeeds", async () => {
    bridgeProcess.responder = () => ({
      result: { success: false, error: "Workspace no longer exists" },
    });

    await expect(bridgeManager.finderReveal("/tmp/missing")).rejects.toThrow(
      "Workspace no longer exists",
    );
    expect(bridgeProcess.requests[0]).toMatchObject({
      method: "finder.reveal",
      params: { path: "/tmp/missing" },
    });
  });

  it("rejects malformed paths before sending them across the process boundary", async () => {
    await expect(bridgeManager.finderReveal("  ")).rejects.toThrow(
      "Finder path must be a non-empty string",
    );
    await expect(bridgeManager.finderReveal("bad\0path")).rejects.toThrow(
      "Finder path contains an unsupported null character",
    );
    await expect(bridgeManager.shellOpenTerminal("")).rejects.toThrow(
      "Terminal working directory must be a non-empty string",
    );

    expect(bridgeProcess.requests).toEqual([]);
  });
});
