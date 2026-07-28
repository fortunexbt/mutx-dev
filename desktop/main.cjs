const { app, BrowserWindow, shell, Menu, Notification, ipcMain, globalShortcut } = require("electron");

const serverManager = require("./main/serverManager.cjs");
const bridgeManager = require("./main/bridgeManager.cjs");
const runtimeContext = require("./main/runtimeContext.cjs");
const trayManager = require("./main/trayManager.cjs");
const statusStore = require("./main/statusStore.cjs");
const statusPoll = require("./main/statusPoll.cjs");
const windowManager = require("./main/windowManager.cjs");

const hasExternalDesktopUrl = Boolean(process.env.MUTX_DESKTOP_URL);
const smokeExitAfterReady =
  process.argv.includes("--smoke-exit-after-ready") ||
  process.env.MUTX_DESKTOP_SMOKE === "1";
const gotSingleInstanceLock = smokeExitAfterReady ? true : app.requestSingleInstanceLock();

let isQuitting = false;
let bridgeReady = false;
let statusPollInterval = null;
let statusPollInFlight = false;

if (!gotSingleInstanceLock) {
  app.quit();
}

async function getDesktopUrl() {
  if (process.env.MUTX_DESKTOP_URL) {
    return process.env.MUTX_DESKTOP_URL;
  }

  const serverUrl = serverManager.getServerUrl();
  if (serverUrl) {
    return serverUrl;
  }

  return "http://127.0.0.1:18900";
}

function createTray() {
  trayManager.createTray("icon.png");

  trayManager.setTrayCallbacks({
    onToggleWindow: () => {
      void windowManager.focusWindow("workspace");
    },
    onOpenDashboard: () => {
      void windowManager.openWindow("workspace", { pane: "overview" });
    },
    onOpenSetup: () => {
      void windowManager.openWindow("settings", { pane: "runtime" });
    },
    onOpenTUI: async () => {
      try {
        await bridgeManager.runtimeOpenSurface("tui");
      } catch (e) {
        console.error("[Main] Failed to open TUI:", e);
      }
    },
    onRunDoctor: async () => {
      try {
        const result = await bridgeManager.doctorRun();
        windowManager.broadcast("desktop-doctor-result", result);
        await windowManager.focusWindow("workspace");
      } catch (e) {
        console.error("[Main] Failed to run doctor:", e);
      }
    },
    onQuit: () => {
      isQuitting = true;
      app.quit();
    },
  });
}

function createAppMenu() {
  const template = [
    {
      label: "MUTX",
      submenu: [
        { label: "About MUTX", role: "about" },
        { type: "separator" },
        {
          label: "Workspace",
          accelerator: "CmdOrCtrl+1",
          click: () => {
            void windowManager.openWindow("workspace", { pane: "overview" });
          },
        },
        {
          label: "Sessions",
          accelerator: "CmdOrCtrl+2",
          click: () => {
            void windowManager.openWindow("sessions");
          },
        },
        {
          label: "Traces",
          accelerator: "CmdOrCtrl+3",
          click: () => {
            void windowManager.openWindow("traces");
          },
        },
        {
          label: "Settings…",
          accelerator: "CmdOrCtrl+,",
          click: () => {
            void windowManager.openWindow("settings", { pane: "account" });
          },
        },
        { type: "separator" },
        { label: "Hide MUTX", role: "hide" },
        { label: "Hide Others", role: "hideOthers" },
        { label: "Show All", role: "unhide" },
        { type: "separator" },
        { label: "Quit MUTX", accelerator: "Cmd+Q", click: () => { isQuitting = true; app.quit(); } },
      ],
    },
    {
      label: "File",
      submenu: [
        { type: "separator" },
        {
          label: "Close Window",
          accelerator: "Cmd+W",
          role: "close",
        },
      ],
    },
    {
      label: "Edit",
      submenu: [
        { label: "Undo", role: "undo" },
        { label: "Redo", role: "redo" },
        { type: "separator" },
        { label: "Cut", role: "cut" },
        { label: "Copy", role: "copy" },
        { label: "Paste", role: "paste" },
        { label: "Select All", role: "selectAll" },
      ],
    },
    {
      label: "View",
      submenu: [
        { label: "Reload", accelerator: "Cmd+R", role: "reload" },
        { label: "Force Reload", accelerator: "Cmd+Shift+R", role: "forceReload" },
        { label: "Toggle DevTools", accelerator: "Cmd+Option+I", role: "toggleDevTools" },
        { type: "separator" },
        { label: "Actual Size", accelerator: "Cmd+0", role: "resetZoom" },
        { label: "Zoom In", accelerator: "Cmd+Plus", role: "zoomIn" },
        { label: "Zoom Out", accelerator: "Cmd+-", role: "zoomOut" },
        { type: "separator" },
        { label: "Toggle Full Screen", accelerator: "Ctrl+Cmd+F", role: "togglefullscreen" },
      ],
    },
    {
      label: "Window",
      submenu: [
        { label: "Minimize", role: "minimize" },
        { label: "Zoom", role: "zoom" },
        { type: "separator" },
        { label: "Bring All to Front", role: "front" },
      ],
    },
    {
      label: "Help",
      submenu: [
        {
          label: "Documentation",
          click: () => {
            shell.openExternal("https://mutx.dev/docs");
          },
        },
        {
          label: "Report Issue",
          click: () => {
            shell.openExternal("https://github.com/mutx-dev/mutx-dev/issues");
          },
        },
        { type: "separator" },
        {
          label: "About",
          click: () => {
            void windowManager.openWindow("workspace", { pane: "overview" }, { route: "/dashboard" });
          },
        },
      ],
    },
  ];

  const menu = Menu.buildFromTemplate(template);
  Menu.setApplicationMenu(menu);
}

function registerGlobalShortcuts() {
  globalShortcut.register("Cmd+Shift+M", () => {
    void windowManager.focusWindow("workspace");
  });

  globalShortcut.register("Cmd+1", () => void windowManager.focusWindow("workspace"));
  globalShortcut.register("Cmd+2", () => void windowManager.openWindow("sessions"));
  globalShortcut.register("Cmd+3", () => void windowManager.openWindow("traces"));
  globalShortcut.register("Cmd+,", () => void windowManager.openWindow("settings", { pane: "account" }));

  globalShortcut.register("Cmd+Shift+T", async () => {
    try {
      await bridgeManager.runtimeOpenSurface("tui");
    } catch (e) {
      console.error("[Main] Failed to open TUI:", e);
    }
  });
}

async function pollStatus() {
  if (!bridgeReady || statusPollInFlight) {
    return;
  }

  statusPollInFlight = true;

  try {
    const { observedAt, results } = await statusPoll.collectStatusSources({
      context: () => runtimeContext.readRuntimeContext(),
      auth: () => bridgeManager.authStatus(),
      runtime: () => bridgeManager.runtimeInspect(),
      governance: () => bridgeManager.governanceStatus(),
      sessions: () => bridgeManager.assistantSessions(),
      controlPlane: () => bridgeManager.controlPlaneStatus(),
    });
    const snapshot = statusPoll.buildDesktopStatusSnapshot({
      observedAt,
      results,
      serverState: hasExternalDesktopUrl
        ? statusStore.getState().uiServer
        : serverManager.getServerState(),
      bridgeState: bridgeManager.getBridgeState(),
      appVersion: app.getVersion(),
    });

    statusStore.applyPollSnapshot(snapshot);

    trayManager.setTrayStatus({
      mode: statusStore.getState().mode,
      apiHealth: statusStore.getState().apiHealth,
      gatewayHealth: statusStore.getState().openclaw?.health,
      farameshHealth: statusStore.getState().faramesh?.health,
      authenticated: statusStore.getState().authenticated,
      assistantName: statusStore.getState().assistant?.name,
    });

  } catch (e) {
    const bridgeState = bridgeManager.getBridgeState();
    const transientBridgeRestart =
      (bridgeState.state === "starting" || bridgeState.state === "restarting") &&
      bridgeState.lastExitCode === 0 &&
      !bridgeState.lastError;

    if (transientBridgeRestart) {
      console.warn("[Main] Status poll paused while bridge restarts cleanly");
      statusStore.updateBridge({
        ...bridgeState,
        ready: false,
        state: bridgeState.state,
        lastError: null,
      });
      statusStore.updateRuntime({
        state: bridgeState.state,
        lastError: null,
      });
    } else {
      console.error("[Main] Status poll error:", e);
      statusStore.updateBridge(bridgeState);
      statusStore.updateRuntime({
        state: "error",
        lastError: "Desktop status refresh failed. Retry from Desktop Settings.",
      });
    }
  } finally {
    statusPollInFlight = false;
  }
}

function setupIpcHandlers() {
  ipcMain.handle("get-app-version", () => {
    return app.getVersion();
  });

  ipcMain.handle("get-platform", () => {
    return process.platform;
  });

  ipcMain.handle("get-user-data-path", () => {
    return app.getPath("userData");
  });

  ipcMain.handle("get-desktop-status", () => {
    return statusStore.getState();
  });

  ipcMain.handle("get-runtime-context", () => {
    return runtimeContext.readRuntimeContext();
  });

  ipcMain.handle("set-runtime-context", (event, updates) => {
    return runtimeContext.writeRuntimeContext(updates || {});
  });

  ipcMain.handle("open-external", async (event, url) => {
    await shell.openExternal(url);
  });

  ipcMain.handle("show-notification", async (event, { title, body }) => {
    if (Notification.isSupported()) {
      new Notification({ title, body }).show();
      return true;
    }
    return false;
  });

  ipcMain.handle("minimize-window", (event) => {
    const win = BrowserWindow.fromWebContents(event.sender);
    if (win) win.minimize();
  });

  ipcMain.handle("maximize-window", (event) => {
    const win = BrowserWindow.fromWebContents(event.sender);
    if (win) {
      if (win.isMaximized()) {
        win.unmaximize();
      } else {
        win.maximize();
      }
    }
  });

  ipcMain.handle("close-window", (event) => {
    const win = BrowserWindow.fromWebContents(event.sender);
    if (win) win.close();
  });

  ipcMain.handle("is-window-maximized", (event) => {
    const win = BrowserWindow.fromWebContents(event.sender);
    return win ? win.isMaximized() : false;
  });

  ipcMain.on("navigate", (event, route) => {
    const win = BrowserWindow.fromWebContents(event.sender);
    if (win) {
      win.webContents.send("navigate", route);
    }
  });

  ipcMain.on("open-onboarding", () => {
    void windowManager.openWindow("workspace", { pane: "overview" });
  });

  ipcMain.on("show-main-window", () => {
    void windowManager.focusWindow("workspace");
  });

  ipcMain.handle("desktop-window-open", async (event, { role, payload, route }) => {
    await windowManager.openWindow(role, payload, { route });
    return windowManager.getWindowsState();
  });

  ipcMain.handle("desktop-window-focus", async (event, { role }) => {
    await windowManager.focusWindow(role);
    return windowManager.getWindowsState();
  });

  ipcMain.handle("desktop-window-close", (event, { role }) => {
    windowManager.closeWindow(role);
    return windowManager.getWindowsState();
  });

  ipcMain.handle("desktop-window-get-state", () => {
    return windowManager.getWindowsState();
  });

  ipcMain.handle("desktop-window-get-current", (event) => {
    return windowManager.getCurrentWindowSnapshot(event.sender);
  });

  ipcMain.handle("desktop-window-update-state", (event, updates) => {
    return windowManager.updateCurrentWindowState(event.sender, updates);
  });

  ipcMain.handle("app-open-preferences", async (event, { pane }) => {
    await windowManager.openWindow("settings", { pane: pane || "account" });
    return windowManager.getWindowsState();
  });

  ipcMain.handle("desktop-ui-show-context-menu", async (event, { items }) => {
    return windowManager.showContextMenu(event.sender, items || []);
  });

  ipcMain.handle("bridge-call", async (event, { method, params }) => {
    if (!bridgeManager.getBridgeState().ready) {
      return { error: "Bridge not ready" };
    }
    try {
      return await bridgeManager.callBridge(method, params);
    } catch (e) {
      return { error: e.message };
    }
  });

  ipcMain.handle("bridge.systemInfo", async () => {
    return bridgeManager.systemInfo();
  });

  ipcMain.handle("bridge.authStatus", async () => {
    return bridgeManager.authStatus();
  });

  ipcMain.handle("bridge.authLogin", async (event, { email, password }) => {
    return bridgeManager.authLogin(email, password);
  });

  ipcMain.handle("bridge.authRegister", async (event, { name, email, password }) => {
    return bridgeManager.authRegister(name, email, password);
  });

  ipcMain.handle("bridge.authLocalBootstrap", async (event, { name }) => {
    return bridgeManager.authLocalBootstrap(name);
  });

  ipcMain.handle("bridge.authStoreTokens", async (event, { accessToken, refreshToken, apiUrl }) => {
    return bridgeManager.authStoreTokens(accessToken, refreshToken, apiUrl);
  });

  ipcMain.handle("bridge.authLogout", async () => {
    return bridgeManager.authLogout();
  });

  ipcMain.handle("bridge.doctorRun", async () => {
    return bridgeManager.doctorRun();
  });

  ipcMain.handle("bridge.setupInspectEnvironment", async () => {
    return bridgeManager.setupInspectEnvironment();
  });

  ipcMain.handle("bridge.setupStart", async (event, { mode, assistantName, actionType, openclawInstallMethod }) => {
    return bridgeManager.setupStart(mode, assistantName, actionType, openclawInstallMethod);
  });

  ipcMain.handle("bridge.setupGetState", async () => {
    return bridgeManager.setupGetState();
  });

  ipcMain.handle("bridge.runtimeInspect", async () => {
    return bridgeManager.runtimeInspect();
  });

  ipcMain.handle("bridge.runtimeResync", async () => {
    return bridgeManager.runtimeResync();
  });

  ipcMain.handle("bridge.runtimeOpenSurface", async (event, { surface }) => {
    return bridgeManager.runtimeOpenSurface(surface);
  });

  ipcMain.handle("bridge.controlPlaneStatus", async () => {
    return bridgeManager.controlPlaneStatus();
  });

  ipcMain.handle("bridge.controlPlaneStart", async () => {
    return bridgeManager.controlPlaneStart();
  });

  ipcMain.handle("bridge.controlPlaneStop", async () => {
    return bridgeManager.controlPlaneStop();
  });

  ipcMain.handle("bridge.assistantOverview", async () => {
    return bridgeManager.assistantOverview();
  });

  ipcMain.handle("bridge.assistantSessions", async () => {
    return bridgeManager.assistantSessions();
  });

  ipcMain.handle("bridge.agentsList", async () => {
    return bridgeManager.agentsList();
  });

  ipcMain.handle("bridge.agentsCreate", async (event, { name, description, agentType }) => {
    return bridgeManager.agentsCreate(name, description, agentType);
  });

  ipcMain.handle("bridge.agentsStop", async (event, { agentId }) => {
    return bridgeManager.agentsStop(agentId);
  });

  ipcMain.handle("bridge.governanceStatus", async () => {
    return bridgeManager.governanceStatus();
  });

  ipcMain.handle("bridge.governanceRestart", async () => {
    return bridgeManager.governanceRestart();
  });

  ipcMain.handle("bridge.finderReveal", async (event, { filePath }) => {
    return bridgeManager.finderReveal(filePath);
  });

  ipcMain.handle("bridge.shellOpenTerminal", async (event, { cwd }) => {
    return bridgeManager.shellOpenTerminal(cwd);
  });

  ipcMain.handle("bridge.dialogChooseWorkspace", async () => {
    return bridgeManager.dialogChooseWorkspace();
  });
}

async function initializeDesktop() {
  console.log("[Main] Initializing desktop...");

  runtimeContext.ensureRuntimeContext();
  windowManager.configure({
    getDesktopUrl,
    isQuitting: () => isQuitting,
    onStateChanged: () => {},
  });
  statusStore.updateUiServer(serverManager.getServerState());
  statusStore.updateBridge(bridgeManager.getBridgeState());
  statusStore.updateRuntime({
    state: "starting",
    lastError: null,
  });

  if (!hasExternalDesktopUrl) {
    console.log("[Main] Starting UI server...");
    try {
      await serverManager.startUIServer({
        runtimeContextPath: runtimeContext.getRuntimeContextPath(),
      });
      console.log("[Main] UI server started");
    } catch (e) {
      console.error("[Main] Failed to start UI server:", e);
      statusStore.updateUiServer({
        ...serverManager.getServerState(),
        ready: false,
        state: "error",
        lastError: e instanceof Error ? e.message : "Failed to start UI server",
      });
      statusStore.updateRuntime({
        state: "error",
        lastError: e instanceof Error ? e.message : "Failed to start UI server",
      });
    }
  } else {
    statusStore.updateUiServer({
      ready: true,
      state: "ready",
      url: process.env.MUTX_DESKTOP_URL,
      port: null,
      lastError: null,
      lastExitCode: null,
      attempt: 0,
    });
  }

  console.log("[Main] Starting bridge...");
  try {
    await bridgeManager.startBridge();
    bridgeReady = true;
    statusStore.updateBridge(bridgeManager.getBridgeState());
    const currentUiServerState = hasExternalDesktopUrl
      ? statusStore.getState().uiServer
      : serverManager.getServerState();
    statusStore.updateRuntime({
      state: currentUiServerState.ready ? "degraded" : "error",
      lastError: currentUiServerState.ready
        ? "Desktop bridge is ready but runtime inspection has not completed yet"
        : currentUiServerState.lastError,
    });
    console.log("[Main] Bridge started");
  } catch (e) {
    console.error("[Main] Failed to start bridge:", e);
    bridgeReady = false;
    statusStore.updateBridge({
      ...bridgeManager.getBridgeState(),
      ready: false,
      state: "error",
      lastError: "Desktop bridge could not start. Restart MUTX or reinstall the application.",
    });
    statusStore.updateRuntime({
      state: "error",
      lastError: "Desktop bridge could not start. Restart MUTX or reinstall the application.",
    });
  }

  if (bridgeReady) {
    void pollStatus();
    statusPollInterval = setInterval(() => {
      void pollStatus();
    }, 30000);
  }
}

if (gotSingleInstanceLock) {
  app.on("second-instance", async () => {
    try {
      await windowManager.focusWindow("workspace");
    } catch (error) {
      console.error("[Main] Failed to create window for second instance:", error);
    }
  });
}

app.whenReady().then(async () => {
  console.log("[Main] App ready");

  serverManager.addStateListener((state) => {
    statusStore.updateUiServer(state);
  });
  bridgeManager.addStateListener((state) => {
    bridgeReady = state.ready;
    statusStore.updateBridge(state);
  });

  createAppMenu();
  await initializeDesktop();
  if (!smokeExitAfterReady) {
    createTray();
  }
  setupIpcHandlers();
  if (!smokeExitAfterReady) {
    registerGlobalShortcuts();
  }
  await windowManager.openWindow("workspace", { pane: "overview" });
  await windowManager.restoreVisibleWindows();

  statusStore.addListener((state) => {
    windowManager.broadcast("desktop-status-changed", state);
  });

  if (smokeExitAfterReady) {
    setTimeout(() => {
      console.log("[Main] Smoke launch verified");
      isQuitting = true;
      app.exit(0);
    }, 2500);
  }
});

app.on("activate", () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    void windowManager.openWindow("workspace", { pane: "overview" });
  } else {
    void windowManager.focusWindow("workspace");
  }
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
  }
});

app.on("before-quit", () => {
  isQuitting = true;
  if (statusPollInterval) {
    clearInterval(statusPollInterval);
  }
  serverManager.stopUIServer();
  bridgeManager.stopBridge();
  trayManager.destroyTray();
});

app.on("will-quit", () => {
  globalShortcut.unregisterAll();
});
