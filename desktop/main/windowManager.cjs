const { BrowserWindow, Menu, app, clipboard } = require("electron");
const fs = require("fs");
const path = require("path");

const WINDOW_ROLES = ["workspace", "sessions", "traces", "settings"];
const PAYLOAD_KEYS = [
  "pane",
  "tab",
  "agentId",
  "deploymentId",
  "runId",
  "sessionId",
];

const WINDOW_LABELS = {
  workspace: "Workspace",
  sessions: "Sessions",
  traces: "Traces",
  settings: "Settings",
};

function _getBaseRouteForRole(role) {
  if (role === "sessions") {
    return "/dashboard/sessions";
  }

  if (role === "traces") {
    return "/dashboard/traces";
  }

  if (role === "settings") {
    return "/dashboard/control";
  }

  return "/dashboard";
}

const DEFAULT_WINDOW_STATE = {
  workspace: {
    route: "/dashboard",
    payload: { pane: "overview" },
    visible: true,
    maximized: false,
    bounds: { width: 1520, height: 980 },
  },
  sessions: {
    route: "/dashboard/sessions",
    payload: { tab: "live" },
    visible: false,
    maximized: false,
    bounds: { width: 1340, height: 920 },
  },
  traces: {
    route: "/dashboard/traces",
    payload: { tab: "timeline" },
    visible: false,
    maximized: false,
    bounds: { width: 1400, height: 960 },
  },
  settings: {
    route: "/dashboard/control",
    payload: { pane: "account" },
    visible: false,
    maximized: false,
    bounds: { width: 1080, height: 820 },
  },
};

const WINDOWS_STATE_FILE = "desktop-window-state.json";

let getDesktopUrl = async () => "http://127.0.0.1:18900";
let isQuitting = () => false;
let onStateChanged = () => {};
let windowsState = null;
let activeRole = "workspace";

const windows = new Map();

function ensureStateLoaded() {
  if (windowsState) {
    return windowsState;
  }

  const filePath = path.join(app.getPath("userData"), WINDOWS_STATE_FILE);
  let parsed = {};

  try {
    if (fs.existsSync(filePath)) {
      parsed = JSON.parse(fs.readFileSync(filePath, "utf8"));
    }
  } catch (error) {
    console.error("[WindowManager] Failed to read persisted window state:", error);
  }

  windowsState = {};
  for (const role of WINDOW_ROLES) {
    const nextState = parsed?.[role] || {};
    windowsState[role] = {
      ...DEFAULT_WINDOW_STATE[role],
      ...nextState,
      payload: {
        ...DEFAULT_WINDOW_STATE[role].payload,
        ...sanitizePayload(nextState.payload),
      },
      bounds: {
        ...DEFAULT_WINDOW_STATE[role].bounds,
        ...(nextState.bounds || {}),
      },
    };
  }

  return windowsState;
}

function saveState() {
  ensureStateLoaded();

  const filePath = path.join(app.getPath("userData"), WINDOWS_STATE_FILE);

  try {
    fs.writeFileSync(filePath, JSON.stringify(windowsState, null, 2));
  } catch (error) {
    console.error("[WindowManager] Failed to persist window state:", error);
  }
}

function sanitizePayload(payload) {
  const safePayload = {};
  for (const key of PAYLOAD_KEYS) {
    const value = payload?.[key];
    if (typeof value === "string" && value.trim().length > 0) {
      safePayload[key] = value.trim();
    }
  }
  return safePayload;
}

function resolveWorkspaceRouteFromPayload(payload) {
  switch (payload?.pane) {
    case "fleet":
      return "/dashboard/agents";
    case "rollouts":
      return "/dashboard/deployments";
    case "operations":
      return "/dashboard/runs";
    case "monitoring":
      return "/dashboard/monitoring";
    case "sessions":
      return "/dashboard/sessions";
    case "api-keys":
      return "/dashboard/api-keys";
    case "budgets":
      return "/dashboard/budgets";
    case "analytics":
      return "/dashboard/analytics";
    case "webhooks":
      return "/dashboard/webhooks";
    case "security":
      return "/dashboard/security";
    case "automation":
      return "/dashboard/orchestration";
    case "memory":
      return "/dashboard/memory";
    case "swarm":
      return "/dashboard/swarm";
    case "channels":
      return "/dashboard/channels";
    case "history":
      return "/dashboard/history";
    case "skills":
      return "/dashboard/skills";
    case "spawn":
      return "/dashboard/spawn";
    case "logs":
      return "/dashboard/logs";
    default:
      return "/dashboard";
  }
}

function resolveWorkspacePaneFromRoute(route) {
  switch (route) {
    case "/dashboard/agents":
      return "fleet";
    case "/dashboard/deployments":
      return "rollouts";
    case "/dashboard/runs":
      return "operations";
    case "/dashboard/monitoring":
      return "monitoring";
    case "/dashboard/api-keys":
      return "api-keys";
    case "/dashboard/budgets":
      return "budgets";
    case "/dashboard/analytics":
      return "analytics";
    case "/dashboard/webhooks":
      return "webhooks";
    case "/dashboard/security":
      return "security";
    case "/dashboard/orchestration":
      return "automation";
    case "/dashboard/memory":
      return "memory";
    case "/dashboard/swarm":
      return "swarm";
    case "/dashboard/channels":
      return "channels";
    case "/dashboard/history":
      return "history";
    case "/dashboard/skills":
      return "skills";
    case "/dashboard/spawn":
      return "spawn";
    case "/dashboard/logs":
      return "logs";
    default:
      return "overview";
  }
}

function resolvePayloadForRole(role, route, payload = {}) {
  const safePayload = {
    ...sanitizePayload(payload),
  };

  if (role === "workspace") {
    return {
      ...safePayload,
      pane: safePayload.pane || resolveWorkspacePaneFromRoute(route),
    };
  }

  if (role === "traces") {
    return {
      ...safePayload,
      tab: safePayload.tab || (route === "/dashboard/logs" ? "logs" : "timeline"),
    };
  }

  if (role === "settings") {
    return {
      ...safePayload,
      pane: safePayload.pane || "account",
    };
  }

  return safePayload;
}

function resolveRouteForRole(role, payload, route) {
  if (typeof route === "string" && route.startsWith("/dashboard")) {
    return route;
  }

  if (role === "workspace") {
    return resolveWorkspaceRouteFromPayload(payload || {});
  }

  if (role === "sessions") {
    return "/dashboard/sessions";
  }

  if (role === "traces") {
    return "/dashboard/traces";
  }

  return "/dashboard/control";
}

function buildUrl(baseUrl, role, route, payload) {
  const url = new URL(route, `${baseUrl}/`);
  url.searchParams.set("desktopWindowRole", role);

  const safePayload = sanitizePayload(payload);
  for (const [key, value] of Object.entries(safePayload)) {
    url.searchParams.set(key, value);
  }

  return url.toString();
}

function buildRendererRoute(route, payload) {
  const url = new URL(route, "https://desktop.mutx.local");
  const safePayload = sanitizePayload(payload);

  for (const [key, value] of Object.entries(safePayload)) {
    url.searchParams.set(key, value);
  }

  return `${url.pathname}${url.search}${url.hash}`;
}

function getWindowOptions(role, bounds) {
  const defaults = {
    width: bounds?.width || 1280,
    height: bounds?.height || 860,
    x: typeof bounds?.x === "number" ? bounds.x : undefined,
    y: typeof bounds?.y === "number" ? bounds.y : undefined,
    show: false,
    backgroundColor: "#0c1014",
    titleBarStyle: process.platform === "darwin" ? "hiddenInset" : "default",
    trafficLightPosition: process.platform === "darwin" ? { x: 18, y: 16 } : undefined,
    vibrancy: process.platform === "darwin" ? "under-window" : undefined,
    minWidth: role === "settings" ? 900 : 1100,
    minHeight: role === "settings" ? 700 : 760,
    webPreferences: {
      preload: path.join(__dirname, "..", "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
    },
  };

  if (role === "settings") {
    return {
      ...defaults,
      width: bounds?.width || 1080,
      height: bounds?.height || 820,
      title: "MUTX Settings",
      minimizable: true,
      maximizable: false,
    };
  }

  return {
    ...defaults,
    title: `MUTX ${WINDOW_LABELS[role]}`,
  };
}

function getWindowEntry(role) {
  const entry = windows.get(role);
  if (!entry || entry.window.isDestroyed()) {
    windows.delete(role);
    return null;
  }
  return entry;
}

function updateRoleState(role, updates = {}) {
  ensureStateLoaded();

  windowsState[role] = {
    ...windowsState[role],
    ...updates,
    payload: updates.payload
      ? {
          ...windowsState[role].payload,
          ...sanitizePayload(updates.payload),
        }
      : windowsState[role].payload,
    bounds: updates.bounds
      ? {
          ...windowsState[role].bounds,
          ...updates.bounds,
        }
      : windowsState[role].bounds,
  };

  saveState();
}

function getSnapshotForRole(role) {
  const entry = getWindowEntry(role);
  const state = ensureStateLoaded()[role];

  return {
    role,
    title: WINDOW_LABELS[role],
    route: state.route,
    payload: state.payload,
    visible: entry ? entry.window.isVisible() : Boolean(state.visible),
    focused: entry ? entry.window.isFocused() : false,
    maximized: entry ? entry.window.isMaximized() : Boolean(state.maximized),
  };
}

function getWindowsState() {
  ensureStateLoaded();

  return {
    activeRole,
    windows: {
      workspace: getSnapshotForRole("workspace"),
      sessions: getSnapshotForRole("sessions"),
      traces: getSnapshotForRole("traces"),
      settings: getSnapshotForRole("settings"),
    },
  };
}

function emitStateChange() {
  const nextState = getWindowsState();
  onStateChanged(nextState);

  for (const role of WINDOW_ROLES) {
    const entry = getWindowEntry(role);
    if (entry) {
      entry.window.webContents.send("desktop-window-state-changed", nextState);
    }
  }
}

function trackWindowState(role, window) {
  const persistWindowState = () => {
    if (window.isDestroyed()) {
      return;
    }

    const bounds = window.getBounds();
    updateRoleState(role, {
      bounds,
      visible: window.isVisible(),
      maximized: window.isMaximized(),
    });
    emitStateChange();
  };

  window.on("move", persistWindowState);
  window.on("resize", persistWindowState);
  window.on("maximize", persistWindowState);
  window.on("unmaximize", persistWindowState);
  window.on("show", persistWindowState);
  window.on("hide", persistWindowState);
  window.on("focus", () => {
    activeRole = role;
    emitStateChange();
  });
  window.on("blur", () => {
    emitStateChange();
  });
}

async function createWindow(role) {
  const state = ensureStateLoaded()[role];
  const baseUrl = await getDesktopUrl();
  const route = resolveRouteForRole(role, state.payload, state.route);
  const window = new BrowserWindow(getWindowOptions(role, state.bounds));
  const url = buildUrl(baseUrl, role, route, state.payload);

  windows.set(role, { role, window });

  trackWindowState(role, window);

  window.once("ready-to-show", () => {
    if (!window.isDestroyed()) {
      window.show();
      if (state.maximized && role !== "settings") {
        window.maximize();
      }
      activeRole = role;
      emitStateChange();
    }
  });

  window.on("close", (event) => {
    if (role === "workspace" && !isQuitting()) {
      event.preventDefault();
      window.hide();
      updateRoleState(role, { visible: false });
      emitStateChange();
    }
  });

  window.on("closed", () => {
    windows.delete(role);
    updateRoleState(role, { visible: false });
    emitStateChange();
  });

  function isSafeExternalUrl(url) {
    try {
      const parsedUrl = new URL(url);
      return parsedUrl.protocol === "https:" || parsedUrl.protocol === "http:";
    } catch {
      return false;
    }
  }

  window.webContents.setWindowOpenHandler(({ url: targetUrl }) => {
    if (isSafeExternalUrl(targetUrl)) {
      require("electron").shell.openExternal(targetUrl);
    }
    return { action: "deny" };
  });

  await window.loadURL(url);
  updateRoleState(role, { route, visible: true });

  return window;
}

function configure(options) {
  getDesktopUrl = options.getDesktopUrl || getDesktopUrl;
  isQuitting = options.isQuitting || isQuitting;
  onStateChanged = options.onStateChanged || onStateChanged;
  ensureStateLoaded();
}

async function openWindow(role, payload = {}, options = {}) {
  const currentState = ensureStateLoaded()[role];
  const candidatePayload = {
    ...currentState.payload,
    ...sanitizePayload(payload),
  };
  const nextRoute = resolveRouteForRole(role, candidatePayload, options.route || currentState.route);
  const nextPayload = resolvePayloadForRole(role, nextRoute, candidatePayload);

  const existing = getWindowEntry(role);

  if (existing) {
    updateRoleState(role, {
      route: nextRoute,
      payload: nextPayload,
      visible: true,
    });
    if (existing.window.isMinimized()) {
      existing.window.restore();
    }
    existing.window.show();
    existing.window.focus();
    existing.window.webContents.send(
      "navigate",
      buildRendererRoute(nextRoute, nextPayload),
    );
    activeRole = role;
    emitStateChange();
    return existing.window;
  }

  updateRoleState(role, {
    route: nextRoute,
    payload: nextPayload,
    visible: true,
  });

  return createWindow(role);
}

async function restoreVisibleWindows() {
  ensureStateLoaded();

  for (const role of WINDOW_ROLES) {
    if (role === "workspace") {
      continue;
    }

    if (windowsState[role].visible) {
      await openWindow(role, windowsState[role].payload, { route: windowsState[role].route });
    }
  }
}

function focusWindow(role) {
  const entry = getWindowEntry(role);
  if (!entry) {
    return openWindow(role);
  }

  if (entry.window.isMinimized()) {
    entry.window.restore();
  }
  entry.window.show();
  entry.window.focus();
  activeRole = role;
  emitStateChange();
  return Promise.resolve(entry.window);
}

function closeWindow(role) {
  const entry = getWindowEntry(role);
  if (!entry) {
    updateRoleState(role, { visible: false });
    emitStateChange();
    return;
  }

  entry.window.close();
}

function getCurrentWindowRole(webContents) {
  const currentWindow = BrowserWindow.fromWebContents(webContents);
  if (!currentWindow) {
    return "workspace";
  }

  for (const [role, entry] of windows.entries()) {
    if (entry.window.id === currentWindow.id) {
      return role;
    }
  }

  return "workspace";
}

function getCurrentWindowSnapshot(webContents) {
  const role = getCurrentWindowRole(webContents);

  return {
    currentRole: role,
    currentWindow: getSnapshotForRole(role),
    state: getWindowsState(),
  };
}

function updateCurrentWindowState(webContents, updates = {}) {
  const role = getCurrentWindowRole(webContents);
  const currentState = ensureStateLoaded()[role];
  const candidatePayload = updates.payload
    ? {
        ...currentState.payload,
        ...sanitizePayload(updates.payload),
      }
    : currentState.payload;
  const nextRoute = typeof updates.route === "string" ? updates.route : currentState.route;
  const nextPayload = resolvePayloadForRole(role, nextRoute, candidatePayload);

  updateRoleState(role, {
    route: nextRoute,
    payload: nextPayload,
  });
  emitStateChange();

  return getCurrentWindowSnapshot(webContents);
}

function broadcast(channel, payload) {
  for (const role of WINDOW_ROLES) {
    const entry = getWindowEntry(role);
    if (entry) {
      entry.window.webContents.send(channel, payload);
    }
  }
}

async function showContextMenu(webContents, items = []) {
  const win = BrowserWindow.fromWebContents(webContents);
  if (!win) {
    return { success: false, error: "No active window" };
  }

  const menu = Menu.buildFromTemplate(
    items.map((item) => ({
      label: item.label,
      enabled: item.enabled !== false,
      type: item.type === "separator" ? "separator" : "normal",
      click: async () => {
        const action = item.action || {};
        if (action.type === "window.open" && action.role) {
          await openWindow(action.role, action.payload || {}, { route: action.route });
        } else if (action.type === "window.focus" && action.role) {
          await focusWindow(action.role);
        } else if (action.type === "window.close" && action.role) {
          closeWindow(action.role);
        } else if (action.type === "clipboard.copy" && typeof action.value === "string") {
          clipboard.writeText(action.value);
        } else if (action.type === "navigate.current" && typeof action.route === "string") {
          const snapshot = updateCurrentWindowState(webContents, {
            route: action.route,
            payload: action.payload || {},
          });
          webContents.send(
            "navigate",
            buildRendererRoute(
              snapshot.currentWindow.route,
              snapshot.currentWindow.payload,
            ),
          );
        } else if (action.type === "settings.open") {
          await openWindow("settings", { pane: action.pane || "account" });
        }
      },
    })),
  );

  menu.popup({ window: win });
  return { success: true };
}

module.exports = {
  configure,
  openWindow,
  focusWindow,
  closeWindow,
  restoreVisibleWindows,
  getWindowsState,
  getCurrentWindowSnapshot,
  updateCurrentWindowState,
  getCurrentWindowRole,
  broadcast,
  showContextMenu,
};
