const { spawn } = require("child_process");
const path = require("path");
const fs = require("fs");
const { version: mutxVersion } = require("../../package.json");

const BRIDGE_REQUEST_TIMEOUT_MS = 60000;
const BRIDGE_START_TIMEOUT_MS = 15000;
const BRIDGE_RESTART_DELAY_MS = 1000;
const BRIDGE_READ_CACHE_TTL_MS = 15000;

let bridgeProcess = null;
let bridgeReady = false;
let pendingRequests = new Map();
let inflightRequests = new Map();
let cachedRequests = new Map();
let requestId = 0;
let stoppingBridge = false;
let startPromise = null;
const listeners = new Set();
let bridgeState = {
  ready: false,
  state: "stopped",
  pythonCommand: null,
  scriptPath: null,
  lastError: null,
  lastExitCode: null,
};

function notifyListeners() {
  const snapshot = getBridgeState();
  listeners.forEach((listener) => {
    try {
      listener(snapshot);
    } catch (error) {
      console.error("[BridgeManager] Listener error:", error);
    }
  });
}

function updateBridgeState(updates) {
  bridgeState = {
    ...bridgeState,
    ...updates,
  };
  notifyListeners();
}

function getBridgeState() {
  return { ...bridgeState };
}

function addStateListener(listener) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function getBridgeScript() {
  const candidates = [
    path.join(process.resourcesPath || "", "app.asar.unpacked", "cli", "desktop_bridge.py"),
    path.join(process.resourcesPath || "", "cli", "desktop_bridge.py"),
    path.join(__dirname, "..", "..", "cli", "desktop_bridge.py"),
  ];

  for (const candidate of candidates) {
    if (candidate && fs.existsSync(candidate)) {
      return candidate;
    }
  }
  return null;
}

function getPythonCommand() {
  const candidates = [
    process.env.MUTX_PYTHON,
    path.join(process.env.HOMEBREW_PREFIX || "", "bin", "python3"),
    "/opt/homebrew/bin/python3",
    "/usr/local/bin/python3",
    "python3",
    "python",
  ].filter(Boolean);

  for (const candidate of candidates) {
    if (candidate === "python3" || candidate === "python") {
      return candidate;
    }

    if (fs.existsSync(candidate)) {
      return candidate;
    }
  }

  return process.platform === "darwin" ? "python3" : "python";
}

function clearPendingRequests(error) {
  pendingRequests.forEach((pending) => {
    clearTimeout(pending.timeoutId);
    pending.reject(error);
  });
  pendingRequests.clear();
  inflightRequests.clear();
  cachedRequests.clear();
}

function getInflightKey(method, params = {}) {
  return `${method}:${JSON.stringify(params || {})}`;
}

function getCachedRequest(method, params = {}) {
  const key = getInflightKey(method, params);
  const cached = cachedRequests.get(key);
  if (!cached) {
    return null;
  }

  if (cached.expiresAt <= Date.now()) {
    cachedRequests.delete(key);
    return null;
  }

  return cached.value;
}

function setCachedRequest(method, params = {}, value, cacheMs = BRIDGE_READ_CACHE_TTL_MS) {
  const key = getInflightKey(method, params);
  cachedRequests.set(key, {
    value,
    expiresAt: Date.now() + cacheMs,
  });
}

function clearCachedRequests() {
  cachedRequests.clear();
}

function asRecord(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : null;
}

function normalizePathArgument(value, { label, optional = false }) {
  if (value === undefined || value === null) {
    if (optional) {
      return undefined;
    }
    throw new TypeError(`${label} must be a non-empty string.`);
  }

  if (typeof value !== "string" || value.trim().length === 0) {
    throw new TypeError(`${label} must be a non-empty string.`);
  }

  if (value.includes("\0")) {
    throw new TypeError(`${label} contains an unsupported null character.`);
  }

  return value;
}

function requireSuccessfulAction(result, actionLabel) {
  const record = asRecord(result);
  if (!record || typeof record.success !== "boolean") {
    throw new Error(`${actionLabel} returned an invalid response.`);
  }

  if (!record.success) {
    const message =
      typeof record.error === "string" && record.error.trim().length > 0
        ? record.error
        : `${actionLabel} failed.`;
    throw new Error(message);
  }

  return record;
}

function pickString(value, keys) {
  const record = asRecord(value);
  if (!record) {
    return null;
  }

  for (const key of keys) {
    const candidate = record[key];
    if (typeof candidate === "string" && candidate.trim().length > 0) {
      return candidate;
    }
  }

  return null;
}

function pickBinding(runtimeInfo) {
  const openclaw = asRecord(runtimeInfo?.openclaw);
  const currentBinding = asRecord(openclaw?.current_binding);
  if (currentBinding) {
    return currentBinding;
  }

  const bindings = Array.isArray(openclaw?.bindings) ? openclaw.bindings : [];
  for (const binding of bindings) {
    const record = asRecord(binding);
    if (record) {
      return record;
    }
  }

  return null;
}

function setBridgeProcess(nextProcess) {
  bridgeProcess = nextProcess;
}

function handleResponse(response) {
  const { id, result, error } = response;
  if (id === undefined) {
    return;
  }

  const pending = pendingRequests.get(id);
  if (!pending) {
    return;
  }

  clearTimeout(pending.timeoutId);
  pendingRequests.delete(id);

  if (error) {
    updateBridgeState({
      lastError: "A desktop status source failed. The bridge will retry automatically.",
      ready: bridgeReady,
      state: bridgeReady ? "degraded" : "error",
    });
    pending.reject(new Error(error));
    return;
  }

  bridgeReady = true;
  updateBridgeState({
    ready: true,
    state: "ready",
    lastError: null,
  });
  pending.resolve(result);
}

function sendBridgeRequest(method, params = {}, options = {}) {
  const { timeoutMs = BRIDGE_REQUEST_TIMEOUT_MS, allowWhileStarting = false } = options;

  return new Promise((resolve, reject) => {
    if (!bridgeProcess || bridgeProcess.exitCode !== null) {
      updateBridgeState({
        ready: false,
        state: "error",
        lastError: "Bridge not running",
      });
      reject(new Error("Bridge not running"));
      return;
    }

    if (!bridgeReady && !allowWhileStarting) {
      const message = "Bridge not ready";
      updateBridgeState({
        ready: false,
        state: bridgeState.state === "starting" ? "starting" : "error",
        lastError: bridgeState.state === "starting" ? null : message,
      });
      reject(new Error(message));
      return;
    }

    const id = ++requestId;
    const timeoutId = setTimeout(() => {
      if (!pendingRequests.has(id)) {
        return;
      }

      pendingRequests.delete(id);
      updateBridgeState({
        ready: bridgeReady,
        state: bridgeReady ? "degraded" : "error",
        lastError: "Desktop bridge request timed out. Retry from Desktop Settings.",
      });
      reject(new Error(`Bridge request timeout: ${method}`));
    }, timeoutMs);

    pendingRequests.set(id, { resolve, reject, timeoutId });

    try {
      bridgeProcess.stdin.write(JSON.stringify({ id, method, params }) + "\n");
    } catch (error) {
      clearTimeout(timeoutId);
      pendingRequests.delete(id);
      const message =
        error instanceof Error ? error.message : "Failed to write to desktop bridge";
      updateBridgeState({
        ready: false,
        state: "error",
        lastError: "Desktop bridge could not send a request. Restart MUTX if it does not recover.",
      });
      reject(new Error(message));
    }
  });
}

function attachBridgeListeners(processHandle) {
  let buffer = "";

  processHandle.stdout.on("data", (data) => {
    buffer += data.toString();
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";

    for (const line of lines) {
      if (!line.trim()) {
        continue;
      }
      try {
        const response = JSON.parse(line);
        handleResponse(response);
      } catch {
        console.error("[BridgeManager] Failed to parse response:", line);
      }
    }
  });

  processHandle.stderr.on("data", (data) => {
    const message = data.toString().trim();
    if (!message) {
      return;
    }
    updateBridgeState({
      lastError: "Desktop bridge reported an error. Restart MUTX if it does not recover.",
    });
    console.error("[BridgeManager] Bridge stderr:", message);
  });

  processHandle.on("error", (error) => {
    console.error("[BridgeManager] Bridge error:", error);
    if (bridgeProcess === processHandle) {
      setBridgeProcess(null);
    }
    bridgeReady = false;
    updateBridgeState({
      ready: false,
      state: "error",
      lastError: "Desktop bridge failed. Restart MUTX if it does not recover.",
    });
  });

  processHandle.on("exit", (code) => {
    const cleanExit = code === 0;
    const hadPendingRequests = pendingRequests.size > 0;
    const exitedIdle = cleanExit && !hadPendingRequests && !stoppingBridge;
    const shouldRestart = !stoppingBridge && (!cleanExit || hadPendingRequests);
    const error = new Error(
      code === null ? "Bridge exited unexpectedly" : `Bridge exited with code: ${code}`,
    );

    if (!exitedIdle) {
      console.log("[BridgeManager] Bridge exited with code:", code);
    }

    clearPendingRequests(error);
    bridgeReady = false;
    if (bridgeProcess === processHandle) {
      setBridgeProcess(null);
    }

    updateBridgeState({
      ready: false,
      state: exitedIdle ? "idle" : shouldRestart ? (cleanExit ? "restarting" : "degraded") : "stopped",
      lastExitCode: code ?? null,
      lastError:
        exitedIdle
          ? null
          : cleanExit && shouldRestart
            ? null
            : bridgeState.lastError ||
              (code === null ? "Bridge exited unexpectedly" : `Bridge exited with code: ${code}`),
    });

    if (shouldRestart) {
      setTimeout(() => {
        if (!bridgeProcess && !bridgeReady && !stoppingBridge) {
          startBridge().catch((restartError) => {
            console.error("[BridgeManager] Failed to restart bridge:", restartError);
          });
        }
      }, BRIDGE_RESTART_DELAY_MS);
    }
  });
}

function startBridge() {
  if (bridgeReady && bridgeProcess) {
    return Promise.resolve();
  }

  if (startPromise) {
    return startPromise;
  }

  startPromise = new Promise((resolve, reject) => {
    const scriptPath = getBridgeScript();
    if (!scriptPath) {
      updateBridgeState({
        ready: false,
        state: "error",
        scriptPath: null,
        lastError: "Desktop bridge not found",
        lastExitCode: null,
      });
      reject(new Error("Desktop bridge not found"));
      return;
    }

    const pythonCmd = getPythonCommand();
    stoppingBridge = false;
    bridgeReady = false;
    updateBridgeState({
      ready: false,
      state:
        bridgeState.state === "restarting" || bridgeState.state === "degraded"
          ? "restarting"
          : "starting",
      pythonCommand: path.basename(pythonCmd),
      scriptPath: path.basename(scriptPath),
      lastError: null,
      lastExitCode: null,
    });

    console.log("[BridgeManager] Starting bridge with Python:", pythonCmd);
    console.log("[BridgeManager] Bridge script:", scriptPath);

    const processHandle = spawn(pythonCmd, [scriptPath], {
      stdio: ["pipe", "pipe", "pipe"],
      env: {
        ...process.env,
        PYTHONDONTWRITEBYTECODE: "1",
      },
    });

    setBridgeProcess(processHandle);
    attachBridgeListeners(processHandle);

    sendBridgeRequest("controlPlane.status", {}, {
      allowWhileStarting: true,
      timeoutMs: BRIDGE_START_TIMEOUT_MS,
    })
      .then(() => {
        bridgeReady = true;
        updateBridgeState({
          ready: true,
          state: "ready",
          lastError: null,
        });
        resolve();
      })
      .catch((error) => {
        bridgeReady = false;
        updateBridgeState({
          ready: false,
          state: "error",
          lastError: "Desktop bridge could not start. Restart MUTX or reinstall the application.",
        });

        if (bridgeProcess === processHandle) {
          try {
            processHandle.kill("SIGTERM");
          } catch {
            // process already exited
          }
        }

        reject(error);
      });
  }).finally(() => {
    startPromise = null;
  });

  return startPromise;
}

async function callBridge(method, params = {}, options = {}) {
  if (!bridgeProcess || !bridgeReady) {
    await startBridge();
  }

  if (options.cacheMs) {
    const cached = getCachedRequest(method, params);
    if (cached !== null) {
      return cached;
    }
  }

  if (!options.dedupe) {
    const result = await sendBridgeRequest(method, params, options);
    if (options.cacheMs) {
      setCachedRequest(method, params, result, options.cacheMs);
    }
    if (options.clearCache) {
      clearCachedRequests();
    }
    return result;
  }

  const key = getInflightKey(method, params);
  const existing = inflightRequests.get(key);
  if (existing) {
    return existing;
  }

  const request = sendBridgeRequest(method, params, options)
    .then((result) => {
      if (options.cacheMs) {
        setCachedRequest(method, params, result, options.cacheMs);
      }
      if (options.clearCache) {
        clearCachedRequests();
      }
      return result;
    })
    .finally(() => {
      if (inflightRequests.get(key) === request) {
        inflightRequests.delete(key);
      }
    });

  inflightRequests.set(key, request);
  return request;
}

function stopBridge() {
  if (bridgeProcess) {
    stoppingBridge = true;
    try {
      bridgeProcess.stdin.write("exit\n");
    } catch {
      // ignore broken pipes during shutdown
    }
    setTimeout(() => {
      if (bridgeProcess) {
        bridgeProcess.kill("SIGTERM");
      }
      setBridgeProcess(null);
      bridgeReady = false;
      updateBridgeState({
        ready: false,
        state: "stopped",
        lastError: null,
      });
    }, 1000);
  }
}

function isBridgeReady() {
  return bridgeReady && bridgeProcess !== null;
}

async function systemInfo() {
  const [authInfo, runtimeInfo, governanceInfo, controlPlaneInfo] = await Promise.all([
    authStatus(),
    runtimeInspect(),
    governanceStatus(),
    controlPlaneStatus(),
  ]);
  const openclaw = asRecord(runtimeInfo?.openclaw) || {};
  const gateway = asRecord(openclaw.gateway) || {};

  return {
    mutx_version: mutxVersion,
    api_url: authInfo?.api_url || null,
    api_url_source: authInfo?.api_url ? "config" : "unknown",
    authenticated: Boolean(authInfo?.authenticated),
    user: authInfo?.user || null,
    config_path: pickString(openclaw, ["config_path"]),
    mutx_home: pickString(openclaw, ["home_path"]),
    local_control_plane: {
      path: controlPlaneInfo?.path || "",
      ready: Boolean(controlPlaneInfo?.ready),
    },
    openclaw: {
      binary_path: pickString(openclaw, ["binary_path"]),
      health: {
        status: pickString(gateway, ["status"]) || "unknown",
        cli_available: Boolean(openclaw.binary_path),
        installed: Boolean(openclaw.binary_path),
        onboarded: Boolean(pickString(openclaw, ["config_path"])),
        gateway_configured: Boolean(pickString(gateway, ["gateway_url"])),
        gateway_reachable: pickString(gateway, ["status"]) === "healthy",
        gateway_port:
          typeof gateway.gateway_port === "number" ? gateway.gateway_port : null,
        gateway_url: pickString(gateway, ["gateway_url"]),
        credential_detected: false,
        config_path: pickString(openclaw, ["config_path"]),
        state_dir: pickString(openclaw, ["state_dir"]),
        doctor_summary: pickString(gateway, ["doctor_summary"]),
      },
      manifest: openclaw,
      bindings: Array.isArray(openclaw.bindings) ? openclaw.bindings : [],
    },
    faramesh: {
      available: Boolean(governanceInfo),
      socket_path: null,
      health: {
        daemon_reachable: governanceInfo?.status === "running",
        socket_reachable: governanceInfo?.status === "running",
        policy_loaded: false,
        policy_name: null,
        policy_path: null,
        decisions_total: governanceInfo?.decisions_total || 0,
        pending_approvals: governanceInfo?.pending_approvals || 0,
        denied_today: governanceInfo?.denies_today || 0,
        deferred_today: governanceInfo?.defers_today || 0,
        uptime_seconds: 0,
        version: governanceInfo?.version || null,
        doctor_summary: null,
      },
      policy_path: null,
    },
    cli_available: Boolean(openclaw.binary_path),
  };
}

async function authStatus() {
  return callBridge("auth.status", {}, { dedupe: true, cacheMs: BRIDGE_READ_CACHE_TTL_MS });
}

async function authLogin(email, password) {
  return callBridge("auth.login", { email, password }, { clearCache: true });
}

async function authRegister(name, email, password) {
  return callBridge("auth.register", { name, email, password }, { clearCache: true });
}

async function authLocalBootstrap(name) {
  return callBridge("auth.localBootstrap", { name }, { clearCache: true });
}

async function authLogout() {
  return callBridge("auth.logout", {}, { clearCache: true });
}

async function authStoreTokens(accessToken, refreshToken, apiUrl) {
  return callBridge("auth.storeTokens", {
    access_token: accessToken,
    refresh_token: refreshToken,
    api_url: apiUrl,
  }, { clearCache: true });
}

async function doctorRun() {
  return callBridge("doctor.run");
}

async function setupInspectEnvironment() {
  return systemInfo();
}

async function setupStart(mode, assistantName, actionType, openclawInstallMethod) {
  return callBridge("setup.start", {
    mode,
    assistant_name: assistantName,
    action_type: actionType,
    openclaw_install_method: openclawInstallMethod || "npm",
  }, { clearCache: true });
}

async function setupGetState() {
  return callBridge("setup.getState", {}, { dedupe: true, cacheMs: BRIDGE_READ_CACHE_TTL_MS });
}

async function runtimeInspect() {
  return callBridge("runtime.inspect", {}, { dedupe: true, cacheMs: BRIDGE_READ_CACHE_TTL_MS });
}

async function runtimeResync() {
  return callBridge("runtime.resync", {}, { clearCache: true });
}

async function runtimeOpenSurface(surface) {
  return callBridge("runtime.openSurface", { surface });
}

async function controlPlaneStatus() {
  return callBridge("controlPlane.status", {}, { dedupe: true, cacheMs: BRIDGE_READ_CACHE_TTL_MS });
}

async function controlPlaneStart() {
  return callBridge("controlPlane.start", {}, { clearCache: true });
}

async function controlPlaneStop() {
  return callBridge("controlPlane.stop", {}, { clearCache: true });
}

async function assistantOverview() {
  const [runtimeInfo, sessions] = await Promise.all([runtimeInspect(), assistantSessions()]);
  const binding = pickBinding(runtimeInfo);
  const openclaw = asRecord(runtimeInfo?.openclaw);
  const gateway = asRecord(openclaw?.gateway);

  if (!binding) {
    return { found: false };
  }

  const assistantId = pickString(binding, ["assistant_id", "agent_id", "id"]);
  return {
    found: true,
    agent_id: assistantId,
    name: pickString(binding, ["assistant_name", "name"]) || "Assistant",
    status: Array.isArray(sessions) && sessions.length > 0 ? "running" : "ready",
    onboarding_status: "local-bound",
    assistant_id: assistantId,
    workspace: pickString(binding, ["workspace"]),
    session_count: Array.isArray(sessions) ? sessions.length : 0,
    gateway: {
      status: pickString(gateway, ["status"]) || "unknown",
      gateway_url: pickString(gateway, ["gateway_url"]),
    },
    deployments: [],
    installed_skills: [],
  };
}

async function assistantSessions() {
  return callBridge("assistant.sessions", {}, { dedupe: true, cacheMs: BRIDGE_READ_CACHE_TTL_MS });
}

async function agentsList() {
  return callBridge("agents.list");
}

async function agentsCreate(name, description, agentType) {
  return callBridge("agents.create", {
    name,
    description,
    agent_type: agentType,
  }, { clearCache: true });
}

async function agentsStop(agentId) {
  return callBridge("agents.stop", { agent_id: agentId }, { clearCache: true });
}

async function governanceStatus() {
  return callBridge("governance.status", {}, { dedupe: true, cacheMs: BRIDGE_READ_CACHE_TTL_MS });
}

async function governanceRestart() {
  return callBridge("governance.restart", {}, { clearCache: true });
}

async function finderReveal(filePath) {
  const pathValue = normalizePathArgument(filePath, { label: "Finder path" });
  const result = await callBridge("finder.reveal", { path: pathValue });
  return requireSuccessfulAction(result, "Reveal in Finder");
}

async function shellOpenTerminal(cwd) {
  const cwdValue = normalizePathArgument(cwd, {
    label: "Terminal working directory",
    optional: true,
  });
  const params = cwdValue === undefined ? {} : { cwd: cwdValue };
  const result = await callBridge("shell.openTerminal", params);
  return requireSuccessfulAction(result, "Open Terminal");
}

async function dialogChooseWorkspace() {
  return callBridge("system.chooseWorkspace");
}

module.exports = {
  addStateListener,
  startBridge,
  stopBridge,
  isBridgeReady,
  getBridgeState,
  callBridge,
  systemInfo,
  authStatus,
  authLogin,
  authRegister,
  authLocalBootstrap,
  authLogout,
  authStoreTokens,
  doctorRun,
  setupInspectEnvironment,
  setupStart,
  setupGetState,
  runtimeInspect,
  runtimeResync,
  runtimeOpenSurface,
  controlPlaneStatus,
  controlPlaneStart,
  controlPlaneStop,
  assistantOverview,
  assistantSessions,
  agentsList,
  agentsCreate,
  agentsStop,
  governanceStatus,
  governanceRestart,
  finderReveal,
  shellOpenTerminal,
  dialogChooseWorkspace,
};
