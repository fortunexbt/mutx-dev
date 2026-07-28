const { app } = require("electron");
const { spawn, spawnSync } = require("child_process");
const http = require("http");
const path = require("path");
const fs = require("fs");

const UI_PORT_RANGE = { min: 18900, max: 18999 };
const UI_SERVER_START_TIMEOUT_MS = 15000;
const UI_SERVER_START_ATTEMPTS = 3;
const UI_SERVER_BACKOFF_MS = [750, 1500, 3000];
const UI_SERVER_HEALTH_PATH = "/api/dashboard/health";
const UI_SERVER_PROBE_TIMEOUT_MS = 2000;
const UI_SERVER_PROBE_INTERVAL_MS = 250;
const UI_SERVER_MAX_PROBE_BYTES = 64 * 1024;
const UI_HEALTH_VALUES = new Set(["healthy", "degraded", "unhealthy", "unknown"]);
const UI_READINESS_VALUES = new Set([
  "ready",
  "not_ready",
  "initializing",
  "unavailable",
  "unknown",
]);

let serverProcess = null;
let serverUrl = null;
let startPromise = null;
let stoppingServer = false;
const listeners = new Set();
let serverState = {
  ready: false,
  state: "stopped",
  url: null,
  port: null,
  lastError: null,
  lastExitCode: null,
  attempt: 0,
  observedAt: null,
};

function notifyListeners() {
  const snapshot = getServerState();
  listeners.forEach((listener) => {
    try {
      listener(snapshot);
    } catch (error) {
      console.error("[ServerManager] Listener error:", error);
    }
  });
}

function updateServerState(updates) {
  serverState = {
    ...serverState,
    ...updates,
    observedAt: new Date().toISOString(),
  };
  notifyListeners();
}

function getServerState() {
  return { ...serverState };
}

function addStateListener(listener) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function getDevelopmentRootDir() {
  return path.join(__dirname, "..", "..");
}

function getStandaloneWrapper(rootDir) {
  const wrapperPath = path.join(rootDir, "scripts", "start-standalone.mjs");
  if (!fs.existsSync(wrapperPath)) {
    return null;
  }

  return {
    scriptPath: wrapperPath,
    cwd: rootDir,
  };
}

function getPackagedStandaloneScript() {
  const resourcesPath = process.resourcesPath || "";
  const unpackedRoot = path.join(resourcesPath, "app.asar.unpacked");
  const extraResourcesRoot = resourcesPath;
  const unpackedWrapper = getStandaloneWrapper(unpackedRoot);
  const extraResourcesWrapper = getStandaloneWrapper(extraResourcesRoot);
  const unpackedScript = path.join(
    resourcesPath,
    "app.asar.unpacked",
    ".next",
    "standalone",
    "server.js",
  );
  const extraResourcesScript = path.join(resourcesPath, ".next", "standalone", "server.js");
  const packedScript = path.join(resourcesPath, "app.asar", ".next", "standalone", "server.js");

  if (unpackedWrapper) {
    return unpackedWrapper;
  }

  if (extraResourcesWrapper) {
    return extraResourcesWrapper;
  }

  if (fs.existsSync(unpackedScript)) {
    return {
      scriptPath: unpackedScript,
      cwd: path.dirname(unpackedScript),
    };
  }

  if (fs.existsSync(extraResourcesScript)) {
    return {
      scriptPath: extraResourcesScript,
      cwd: path.dirname(extraResourcesScript),
    };
  }

  if (fs.existsSync(packedScript)) {
    throw new Error(
      "Standalone Next.js server is packaged inside app.asar. Unpack `.next/standalone/**/*` so Next can chdir into its runtime directory.",
    );
  }

  return null;
}

function isPortAvailable(port) {
  const net = require("net");
  return new Promise((resolve) => {
    const server = net.createServer();
    server.once("error", () => resolve(false));
    server.once("listening", () => {
      server.close();
      resolve(true);
    });
    server.listen(port, "127.0.0.1");
  });
}

async function findAvailablePort() {
  for (let port = UI_PORT_RANGE.min; port <= UI_PORT_RANGE.max; port += 1) {
    if (await isPortAvailable(port)) {
      return port;
    }
  }
  throw new Error("No available port in range");
}

function getServerScript() {
  const developmentWrapper = getStandaloneWrapper(getDevelopmentRootDir());

  if (app.isPackaged) {
    return getPackagedStandaloneScript();
  }

  if (developmentWrapper) {
    return developmentWrapper;
  }

  const scriptPath = path.join(getDevelopmentRootDir(), ".next", "standalone", "server.js");
  if (fs.existsSync(scriptPath)) {
    return {
      scriptPath,
      cwd: path.dirname(scriptPath),
    };
  }
  return null;
}

function ensureStandaloneAssets() {
  if (app.isPackaged) {
    return;
  }

  const rootDir = getDevelopmentRootDir();
  const standaloneDir = path.join(rootDir, ".next", "standalone");
  const standaloneStaticDir = path.join(standaloneDir, ".next", "static");
  const standalonePublicDir = path.join(standaloneDir, "public");
  const prepareScript = path.join(rootDir, "scripts", "prepare-standalone.mjs");

  const hasStatic = fs.existsSync(standaloneStaticDir);
  const hasPublic = fs.existsSync(standalonePublicDir);
  if ((hasStatic && hasPublic) || !fs.existsSync(prepareScript)) {
    return;
  }

  const result = spawnSync(process.execPath, [prepareScript], {
    cwd: rootDir,
    stdio: "inherit",
    env: process.env,
  });

  if (result.status !== 0) {
    throw new Error("Could not prepare standalone assets for desktop UI");
  }
}

function formatProbeFailure(error) {
  if (error instanceof Error && error.message.trim()) {
    return error.message.trim();
  }
  return "Desktop UI health check is unavailable.";
}

function publicStartupError(error) {
  const message = error instanceof Error ? error.message.toLowerCase() : "";

  if (message.includes("did not become ready") || message.includes("health check")) {
    return error.message;
  }
  if (message.includes("no available port") || message.includes("address already in use")) {
    return "No local port is available for the desktop UI. Close other MUTX instances and retry.";
  }
  if (message.includes("standalone") && message.includes("not found")) {
    return "Desktop UI files are missing. Reinstall MUTX or rebuild the desktop application.";
  }
  if (message.includes("exited before it became ready")) {
    return "Desktop UI exited during startup. Restart MUTX; if it persists, reinstall the application.";
  }

  return "Desktop UI could not start. Restart MUTX; if it persists, reinstall the application.";
}

function contractValue(value, allowedValues) {
  if (typeof value !== "string") {
    return "unknown";
  }
  const normalized = value.trim().toLowerCase();
  return allowedValues.has(normalized) ? normalized : "unknown";
}

function probeServerReadiness(url, timeoutMs = UI_SERVER_PROBE_TIMEOUT_MS) {
  return new Promise((resolve, reject) => {
    let settled = false;
    let timedOut = false;
    const healthUrl = new URL(UI_SERVER_HEALTH_PATH, `${url.replace(/\/$/, "")}/`);

    const settle = (callback, value) => {
      if (settled) {
        return;
      }
      settled = true;
      callback(value);
    };

    const request = http.get(healthUrl, (response) => {
      let body = "";

      response.setEncoding("utf8");
      response.on("data", (chunk) => {
        if (body.length >= UI_SERVER_MAX_PROBE_BYTES) {
          return;
        }
        body += chunk.slice(0, UI_SERVER_MAX_PROBE_BYTES - body.length);
      });
      response.on("error", () => {
        settle(reject, new Error("Desktop UI health response could not be read."));
      });
      response.on("end", () => {
        if (response.statusCode !== 200) {
          settle(
            reject,
            new Error(`Desktop UI health endpoint returned HTTP ${response.statusCode || "unknown"}.`),
          );
          return;
        }

        let payload;
        try {
          payload = JSON.parse(body);
        } catch {
          settle(reject, new Error("Desktop UI health endpoint returned an invalid response."));
          return;
        }

        const health = contractValue(payload?.status, UI_HEALTH_VALUES);
        const readiness = contractValue(payload?.database, UI_READINESS_VALUES);
        if (health !== "healthy" || readiness !== "ready") {
          settle(
            reject,
            new Error(`Desktop UI is not ready (health: ${health}; readiness: ${readiness}).`),
          );
          return;
        }

        settle(resolve, { health, readiness });
      });
    });

    request.setTimeout(Math.max(1, timeoutMs), () => {
      timedOut = true;
      request.destroy();
    });
    request.on("error", () => {
      settle(
        reject,
        new Error(
          timedOut
            ? "Desktop UI health check timed out."
            : "Desktop UI health endpoint is unreachable.",
        ),
      );
    });
  });
}

function waitForServer(url, childProcess, timeoutMs = UI_SERVER_START_TIMEOUT_MS) {
  const start = Date.now();
  return new Promise((resolve, reject) => {
    let settled = false;
    let retryTimer = null;
    let lastFailure = null;

    const cleanup = () => {
      if (retryTimer) {
        clearTimeout(retryTimer);
        retryTimer = null;
      }
      if (childProcess) {
        childProcess.removeListener("error", onError);
        childProcess.removeListener("exit", onExit);
      }
    };

    const settle = (callback, value) => {
      if (settled) {
        return;
      }
      settled = true;
      cleanup();
      callback(value);
    };

    const onError = (error) => {
      settle(reject, error);
    };

    const onExit = (code, signal) => {
      settle(
        reject,
        new Error(`UI server exited before it became ready (code=${code}, signal=${signal || "none"})`),
      );
    };

    if (childProcess) {
      childProcess.once("error", onError);
      childProcess.once("exit", onExit);
    }

    const check = () => {
      if (settled) {
        return;
      }

      const elapsedMs = Date.now() - start;
      const remainingMs = timeoutMs - elapsedMs;
      if (remainingMs <= 0) {
        const reason = lastFailure
          ? ` Last check: ${formatProbeFailure(lastFailure)}`
          : "";
        settle(
          reject,
          new Error(
            `Desktop UI did not become ready.${reason} Restart MUTX; if it persists, reinstall the application.`,
          ),
        );
        return;
      }

      void probeServerReadiness(url, Math.min(UI_SERVER_PROBE_TIMEOUT_MS, remainingMs))
        .then(() => {
          settle(resolve);
        })
        .catch((error) => {
          lastFailure = error;
          if (Date.now() - start >= timeoutMs) {
            check();
            return;
          }
          const retryDelayMs = Math.min(
            UI_SERVER_PROBE_INTERVAL_MS,
            Math.max(1, timeoutMs - (Date.now() - start)),
          );
          retryTimer = setTimeout(check, retryDelayMs);
        });
    };

    check();
  });
}

function resetRunningServer() {
  serverProcess = null;
  serverUrl = null;
}

function terminateServerProcess() {
  if (!serverProcess) {
    return;
  }

  const processToStop = serverProcess;
  serverProcess = null;
  serverUrl = null;
  try {
    processToStop.kill("SIGTERM");
  } catch (error) {
    console.error("[ServerManager] Failed to stop UI server:", error);
  }
}

function attachServerListeners(childProcess, url) {
  childProcess.stdout.on("data", (data) => {
    const line = data.toString().trim();
    if (!line) {
      return;
    }
    if (line.includes("Ready") || line.includes("listening") || line.includes("started")) {
      console.log("[ServerManager] UI server ready:", url);
    }
  });

  childProcess.stderr.on("data", (data) => {
    const message = data.toString().trim();
    if (!message) {
      return;
    }
    updateServerState({
      lastError: "Desktop UI reported a startup error. Restart MUTX if startup does not recover.",
    });
    console.error("[ServerManager] Server stderr:", message);
  });

  childProcess.on("error", (error) => {
    console.error("[ServerManager] Server error:", error);
    if (serverProcess === childProcess) {
      resetRunningServer();
    }
    updateServerState({
      ready: false,
      state: "error",
      url: null,
      port: null,
      lastError: publicStartupError(error),
    });
  });

  childProcess.on("exit", (code, signal) => {
    if (serverProcess === childProcess) {
      resetRunningServer();
    }

    const intentionalStop = stoppingServer;
    const exitMessage =
      code === null
        ? `UI server exited unexpectedly (signal=${signal || "none"})`
        : `UI server exited with code ${code}`;

    updateServerState({
      ready: false,
      state: intentionalStop ? "stopped" : "degraded",
      url: null,
      port: null,
      lastExitCode: code ?? null,
      lastError: intentionalStop ? null : exitMessage,
    });
  });
}

async function launchServerAttempt(serverScript, options, attempt) {
  const port = await findAvailablePort();
  const url = `http://127.0.0.1:${port}`;

  const env = {
    ...process.env,
    PORT: String(port),
    HOSTNAME: "127.0.0.1",
    NODE_ENV: "production",
    MUTX_DESKTOP_MODE: "true",
    MUTX_DESKTOP_RUNTIME_CONTEXT_PATH: options.runtimeContextPath || "",
    NEXT_TELEMETRY_DISABLED: "1",
    ELECTRON_RUN_AS_NODE: "1",
  };

  stoppingServer = false;
  updateServerState({
    ready: false,
    state: attempt === 1 ? "starting" : "restarting",
    url,
    port,
    attempt,
    lastError: null,
    lastExitCode: null,
  });

  console.log("[ServerManager] Launching UI server:", serverScript.scriptPath);

  const childProcess = spawn(process.execPath, [serverScript.scriptPath], {
    cwd: serverScript.cwd,
    env,
    stdio: ["ignore", "pipe", "pipe"],
    detached: false,
  });

  serverProcess = childProcess;
  serverUrl = url;
  attachServerListeners(childProcess, url);

  await waitForServer(url, childProcess);

  updateServerState({
    ready: true,
    state: "ready",
    url,
    port,
    attempt,
    lastError: null,
    lastExitCode: null,
  });

  return url;
}

async function startUIServer(options = {}) {
  if (isServerRunning() && serverUrl) {
    return serverUrl;
  }

  if (startPromise) {
    return startPromise;
  }

  startPromise = (async () => {
    let serverScript;
    try {
      ensureStandaloneAssets();
      serverScript = getServerScript();
    } catch (error) {
      const message = publicStartupError(error);
      updateServerState({
        ready: false,
        state: "error",
        url: null,
        port: null,
        lastError: message,
      });
      throw new Error(message, { cause: error });
    }

    if (!serverScript) {
      const message = "Desktop UI files are missing. Reinstall MUTX or rebuild the desktop application.";
      updateServerState({
        ready: false,
        state: "error",
        lastError: message,
      });
      throw new Error(message);
    }

    let lastError = null;

    for (let attempt = 1; attempt <= UI_SERVER_START_ATTEMPTS; attempt += 1) {
      try {
        return await launchServerAttempt(serverScript, options, attempt);
      } catch (error) {
        const message = publicStartupError(error);
        lastError = new Error(message);

        console.error("[ServerManager] UI server startup failed:", message);
        terminateServerProcess();
        updateServerState({
          ready: false,
          state: attempt < UI_SERVER_START_ATTEMPTS ? "restarting" : "error",
          url: null,
          port: null,
          attempt,
          lastError: message,
        });

        if (attempt < UI_SERVER_START_ATTEMPTS) {
          const backoffMs =
            UI_SERVER_BACKOFF_MS[Math.min(attempt - 1, UI_SERVER_BACKOFF_MS.length - 1)];
          await new Promise((resolve) => setTimeout(resolve, backoffMs));
        }
      }
    }

    throw lastError instanceof Error ? lastError : new Error("UI server failed to start");
  })().finally(() => {
    startPromise = null;
  });

  return startPromise;
}

function stopUIServer() {
  stoppingServer = true;
  terminateServerProcess();
  updateServerState({
    ready: false,
    state: "stopped",
    url: null,
    port: null,
    lastError: null,
  });
}

function getServerUrl() {
  return serverUrl;
}

function isServerRunning() {
  return serverProcess !== null && serverProcess.exitCode === null;
}

module.exports = {
  addStateListener,
  getServerState,
  probeServerReadiness,
  waitForServer,
  startUIServer,
  stopUIServer,
  getServerUrl,
  isServerRunning,
};
