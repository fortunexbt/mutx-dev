const { app } = require("electron");
const path = require("path");
const fs = require("fs");

const STATUS_SOURCE_STALE_AFTER_MS = 90000;
const SOURCE_NAMES = [
  "uiServer",
  "bridge",
  "context",
  "auth",
  "runtime",
  "governance",
  "sessions",
  "controlPlane",
];

function createSourceState() {
  return {
    freshness: "unavailable",
    observedAt: null,
    lastSuccessAt: null,
    lastError: null,
  };
}

function createSources() {
  return Object.fromEntries(SOURCE_NAMES.map((sourceName) => [sourceName, createSourceState()]));
}

let state = {
  mode: "unknown",
  apiUrl: null,
  apiHealth: "unknown",
  authenticated: false,
  user: null,
  openclaw: {
    binaryPath: null,
    health: "unknown",
    gatewayUrl: null,
  },
  faramesh: {
    available: false,
    socketPath: null,
    health: "unknown",
  },
  uiServer: {
    ready: false,
    state: "unknown",
    url: null,
    port: null,
    lastError: null,
    lastExitCode: null,
    attempt: 0,
    observedAt: null,
  },
  localControlPlane: {
    ready: false,
    path: null,
    state: "unknown",
    exists: null,
    lastError: null,
  },
  runtime: {
    state: "unknown",
    lastError: null,
  },
  assistant: {
    found: false,
    name: null,
    agentId: null,
    workspace: null,
    gatewayStatus: null,
    sessionCount: 0,
    state: "unknown",
    lastError: null,
  },
  bridge: {
    ready: false,
    state: "unknown",
    pythonCommand: null,
    scriptPath: null,
    lastError: null,
    lastExitCode: null,
  },
  cliAvailable: false,
  mutxVersion: null,
  sources: createSources(),
  lastUpdated: null,
};

let listeners = new Set();

function sourceSnapshot(source, nowMs) {
  const lastSuccessMs = source.lastSuccessAt ? Date.parse(source.lastSuccessAt) : Number.NaN;
  const stale =
    source.freshness === "fresh" &&
    Number.isFinite(lastSuccessMs) &&
    nowMs - lastSuccessMs > STATUS_SOURCE_STALE_AFTER_MS;

  return {
    ...source,
    freshness: stale ? "stale" : source.freshness,
  };
}

function getState(nowMs = Date.now()) {
  return {
    ...state,
    openclaw: { ...state.openclaw },
    faramesh: { ...state.faramesh },
    uiServer: { ...state.uiServer },
    localControlPlane: { ...state.localControlPlane },
    runtime: { ...state.runtime },
    assistant: { ...state.assistant },
    bridge: { ...state.bridge },
    sources: Object.fromEntries(
      Object.entries(state.sources).map(([sourceName, source]) => [
        sourceName,
        sourceSnapshot(source, nowMs),
      ]),
    ),
  };
}

function nextSourceState(current, update) {
  const observedAt = update.observedAt || new Date().toISOString();
  const available = Boolean(update.available);
  return {
    freshness: update.freshness || (available ? "fresh" : "unavailable"),
    observedAt,
    lastSuccessAt: available ? observedAt : current.lastSuccessAt,
    lastError: update.lastError || null,
  };
}

function setSource(sources, sourceName, update) {
  if (!sources[sourceName]) {
    return sources;
  }
  return {
    ...sources,
    [sourceName]: nextSourceState(sources[sourceName], update),
  };
}

function lifecycleSourceUpdate(updates) {
  const lifecycleState = updates.state || "unknown";
  const checking = lifecycleState === "starting" || lifecycleState === "restarting";
  return {
    available: Boolean(updates.ready),
    freshness: checking ? "checking" : undefined,
    observedAt: updates.observedAt,
    lastError: updates.lastError,
  };
}

function updateState(updates) {
  state = { ...state, ...updates, lastUpdated: new Date().toISOString() };
  notifyListeners();
}

function updateOpenclaw(updates) {
  state.openclaw = { ...state.openclaw, ...updates };
  state.lastUpdated = new Date().toISOString();
  notifyListeners();
}

function updateFaramesh(updates) {
  state.faramesh = { ...state.faramesh, ...updates };
  state.lastUpdated = new Date().toISOString();
  notifyListeners();
}

function updateUiServer(updates) {
  const observedAt = updates.observedAt || new Date().toISOString();
  const nextUpdates = { ...updates, observedAt };
  state.uiServer = { ...state.uiServer, ...nextUpdates };
  state.sources = setSource(state.sources, "uiServer", lifecycleSourceUpdate(nextUpdates));
  state.lastUpdated = observedAt;
  notifyListeners();
}

function updateAssistant(updates) {
  state.assistant = { ...state.assistant, ...updates };
  state.lastUpdated = new Date().toISOString();
  notifyListeners();
}

function updateLocalControlPlane(updates) {
  state.localControlPlane = { ...state.localControlPlane, ...updates };
  state.lastUpdated = new Date().toISOString();
  notifyListeners();
}

function updateRuntime(updates) {
  state.runtime = { ...state.runtime, ...updates };
  state.lastUpdated = new Date().toISOString();
  notifyListeners();
}

function updateAuth(authData) {
  state.authenticated = authData.authenticated;
  state.user = authData.user;
  state.sources = setSource(state.sources, "auth", {
    available: true,
    lastError: null,
  });
  state.lastUpdated = new Date().toISOString();
  notifyListeners();
}

function updateBridge(updates) {
  state.bridge = { ...state.bridge, ...updates };
  state.sources = setSource(state.sources, "bridge", lifecycleSourceUpdate(updates));
  state.lastUpdated = new Date().toISOString();
  notifyListeners();
}

function updateSource(sourceName, update) {
  state.sources = setSource(state.sources, sourceName, update);
  state.lastUpdated = update.observedAt || new Date().toISOString();
  notifyListeners();
}

function applyPollSnapshot(snapshot) {
  const { sourceUpdates = {}, ...statusSnapshot } = snapshot;
  let sources = state.sources;

  sources = setSource(sources, "uiServer", lifecycleSourceUpdate(statusSnapshot.uiServer));
  sources = setSource(sources, "bridge", lifecycleSourceUpdate(statusSnapshot.bridge));
  Object.entries(sourceUpdates).forEach(([sourceName, update]) => {
    sources = setSource(sources, sourceName, update);
  });

  state = {
    ...state,
    ...statusSnapshot,
    sources,
    lastUpdated: new Date().toISOString(),
  };
  notifyListeners();
}

function notifyListeners() {
  const snapshot = getState();
  listeners.forEach((listener) => {
    try {
      listener(snapshot);
    } catch (e) {
      console.error("[StatusStore] Listener error:", e);
    }
  });
}

function addListener(listener) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function getPrefsPath() {
  return path.join(app.getPath("userData"), "desktop-prefs.json");
}

function loadPrefs() {
  const prefsPath = getPrefsPath();
  try {
    if (fs.existsSync(prefsPath)) {
      const data = fs.readFileSync(prefsPath, "utf8");
      return JSON.parse(data);
    }
  } catch (e) {
    console.error("[StatusStore] Failed to load prefs:", e);
  }
  return {};
}

function savePrefs(prefs) {
  const prefsPath = getPrefsPath();
  try {
    fs.writeFileSync(prefsPath, JSON.stringify(prefs, null, 2), "utf8");
  } catch (e) {
    console.error("[StatusStore] Failed to save prefs:", e);
  }
}

module.exports = {
  getState,
  updateState,
  updateOpenclaw,
  updateFaramesh,
  updateUiServer,
  updateAssistant,
  updateLocalControlPlane,
  updateRuntime,
  updateAuth,
  updateBridge,
  updateSource,
  applyPollSnapshot,
  addListener,
  loadPrefs,
  savePrefs,
  STATUS_SOURCE_STALE_AFTER_MS,
};
