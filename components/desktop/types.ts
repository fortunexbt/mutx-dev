declare global {
  interface Window {
    mutxDesktop?: MutxDesktopAPI;
  }
}

export interface MutxDesktopAPI {
  platform: string;
  isDesktop: boolean;

  getAppVersion(): Promise<string>;
  getPlatform(): Promise<string>;
  getUserDataPath(): Promise<string>;
  getDesktopStatus(): Promise<DesktopStatus>;
  getRuntimeContext(): Promise<DesktopRuntimeContext>;
  setRuntimeContext(updates: Partial<DesktopRuntimeContext>): Promise<DesktopRuntimeContext>;

  openExternal(url: string): Promise<void>;
  showNotification(options: { title: string; body: string }): Promise<boolean>;

  minimizeWindow(): Promise<void>;
  maximizeWindow(): Promise<void>;
  closeWindow(): Promise<void>;
  isWindowMaximized(): Promise<boolean>;

  app: {
    openPreferences(pane?: string): Promise<DesktopWindowsState>;
  };

  windows: DesktopWindowsAPI;

  ui: {
    showContextMenu(items: DesktopContextMenuItem[]): Promise<{ success: boolean; error?: string }>;
  };

  navigate(route: string): void;
  openOnboarding(): void;
  showMainWindow(): void;

  onNavigate(callback: (route: string) => void): () => void;
  onDesktopStatusChanged(callback: (status: DesktopStatus) => void): () => void;
  onWindowStateChanged(callback: (state: DesktopWindowsState) => void): () => void;
  onDoctorResult(callback: (result: DoctorResult) => void): () => void;
  removeNavigateListener(): void;
  removeDesktopStatusListener(): void;
  removeWindowStateListener(): void;
  removeDoctorResultListener(): void;

  bridge: BridgeAPI;
}

export interface BridgeAPI {
  call(method: string, params?: Record<string, unknown>): Promise<unknown>;

  systemInfo(): Promise<SystemInfo>;

  auth: AuthBridgeAPI;
  doctor: DoctorBridgeAPI;
  setup: SetupBridgeAPI;
  runtime: RuntimeBridgeAPI;
  controlPlane: ControlPlaneBridgeAPI;
  assistant: AssistantBridgeAPI;
  agents: AgentsBridgeAPI;
  governance: GovernanceBridgeAPI;
  system: SystemBridgeAPI;
}

export type DesktopWindowRole = "workspace" | "sessions" | "traces" | "settings";

export interface DesktopWindowPayload {
  pane?: string;
  tab?: string;
  agentId?: string;
  deploymentId?: string;
  runId?: string;
  sessionId?: string;
}

export interface DesktopWindowSnapshot {
  role: DesktopWindowRole;
  title: string;
  route: string;
  payload: DesktopWindowPayload;
  visible: boolean;
  focused: boolean;
  maximized: boolean;
}

export interface DesktopWindowsState {
  activeRole: DesktopWindowRole;
  windows: Record<DesktopWindowRole, DesktopWindowSnapshot>;
}

export interface DesktopCurrentWindowState {
  currentRole: DesktopWindowRole;
  currentWindow: DesktopWindowSnapshot;
  state: DesktopWindowsState;
}

export interface DesktopWindowsAPI {
  open(role: DesktopWindowRole, payload?: DesktopWindowPayload, route?: string): Promise<DesktopWindowsState>;
  focus(role: DesktopWindowRole): Promise<DesktopWindowsState>;
  close(role: DesktopWindowRole): Promise<DesktopWindowsState>;
  getState(): Promise<DesktopWindowsState>;
  getCurrent(): Promise<DesktopCurrentWindowState>;
  setState(
    updates: Partial<{
      route: string;
      payload: DesktopWindowPayload;
    }>,
  ): Promise<DesktopCurrentWindowState>;
}

export interface DesktopContextMenuItem {
  label: string;
  enabled?: boolean;
  type?: "normal" | "separator";
  action?: {
    type:
      | "window.open"
      | "window.focus"
      | "window.close"
      | "clipboard.copy"
      | "navigate.current"
      | "settings.open";
    role?: DesktopWindowRole;
    payload?: DesktopWindowPayload;
    route?: string;
    value?: string;
    pane?: string;
  };
}

export interface AuthBridgeAPI {
  status(): Promise<AuthStatus>;
  login(email: string, password: string): Promise<AuthResult>;
  register(name: string, email: string, password: string): Promise<AuthResult>;
  localBootstrap(name: string): Promise<AuthResult>;
  storeTokens(accessToken: string, refreshToken?: string, apiUrl?: string): Promise<AuthResult>;
  logout(): Promise<{ success: boolean }>;
}

export interface DesktopRuntimeContext {
  mode: "local" | "hosted" | "unknown";
  apiUrl: string;
  updatedAt: string | null;
}

export type DesktopLifecycleState =
  | "unknown"
  | "idle"
  | "starting"
  | "ready"
  | "degraded"
  | "restarting"
  | "error"
  | "stopped";

export type DesktopStatusSourceFreshness =
  | "checking"
  | "fresh"
  | "stale"
  | "unavailable";

export interface DesktopStatusSource {
  freshness: DesktopStatusSourceFreshness;
  observedAt: string | null;
  lastSuccessAt: string | null;
  lastError: string | null;
}

export type GovernanceRuntimeState =
  | "running"
  | "stopped"
  | "degraded"
  | "not_installed"
  | "error"
  | "unknown"
  | "unavailable";

export interface DoctorBridgeAPI {
  run(): Promise<DoctorResult>;
}

export interface SetupBridgeAPI {
  inspectEnvironment(): Promise<SystemInfo>;
  start(mode: string, assistantName: string, actionType?: string, openclawInstallMethod?: string): Promise<SetupResult>;
  getState(): Promise<WizardState>;
}

export interface RuntimeBridgeAPI {
  inspect(): Promise<RuntimeInfo>;
  resync(): Promise<{ success: boolean; result?: unknown; error?: string }>;
  openSurface(surface: string): Promise<{ success: boolean; error?: string }>;
}

export interface ControlPlaneBridgeAPI {
  status(): Promise<{ ready: boolean; path: string; exists: boolean }>;
  start(): Promise<{ success: boolean; ready?: boolean; error?: string }>;
  stop(): Promise<{ success: boolean; message?: string; error?: string }>;
}

export interface AssistantBridgeAPI {
  overview(): Promise<AssistantOverview | { found: false; error?: string }>;
  sessions(): Promise<LocalSession[]>;
}

export interface AgentsBridgeAPI {
  list(): Promise<AgentInfo[]>;
  create(name: string, description?: string, agentType?: string): Promise<AgentCreateResult>;
  stop(agentId: string): Promise<{ success: boolean; error?: string }>;
}

export interface GovernanceBridgeAPI {
  status(): Promise<GovernanceStatus>;
  restart(): Promise<{ success: boolean; socketPath?: string; error?: string }>;
}

export interface SystemBridgeAPI {
  revealInFinder(filePath: string): Promise<{ success: boolean; error?: string }>;
  openTerminal(cwd?: string): Promise<{ success: boolean; cwd?: string }>;
  chooseWorkspace(): Promise<{ success: boolean; path?: string; error?: string }>;
}

export interface DesktopStatus {
  mode: "local" | "hosted" | "unknown";
  apiUrl: string | null;
  apiHealth: string;
  authenticated: boolean;
  user: {
    email: string;
    name: string;
    plan: string;
  } | null;
  openclaw: {
    binaryPath: string | null;
    health: string;
    gatewayUrl: string | null;
  };
  faramesh: {
    available: boolean;
    socketPath: string | null;
    health: GovernanceRuntimeState;
  };
  uiServer: {
    ready: boolean;
    state: DesktopLifecycleState;
    url: string | null;
    port: number | null;
    lastError: string | null;
    lastExitCode: number | null;
    attempt: number;
    observedAt: string | null;
  };
  localControlPlane: {
    ready: boolean;
    path: string | null;
    state: DesktopLifecycleState;
    exists: boolean | null;
    lastError: string | null;
  };
  runtime: {
    state: DesktopLifecycleState;
    lastError: string | null;
  };
  assistant: {
    found: boolean;
    name: string | null;
    agentId: string | null;
    workspace: string | null;
    gatewayStatus: string | null;
    sessionCount: number | null;
    state: DesktopLifecycleState;
    lastError: string | null;
  };
  bridge: {
    ready: boolean;
    state: DesktopLifecycleState;
    pythonCommand: string | null;
    scriptPath: string | null;
    lastError: string | null;
    lastExitCode: number | null;
  };
  cliAvailable: boolean;
  mutxVersion: string | null;
  sources: {
    uiServer: DesktopStatusSource;
    bridge: DesktopStatusSource;
    context: DesktopStatusSource;
    auth: DesktopStatusSource;
    runtime: DesktopStatusSource;
    governance: DesktopStatusSource;
    sessions: DesktopStatusSource;
    controlPlane: DesktopStatusSource;
  };
  lastUpdated: string | null;
}

export interface SystemInfo {
  mutx_version: string;
  api_url: string;
  api_url_source: string;
  authenticated: boolean;
  config_path: string;
  mutx_home: string;
  local_control_plane: {
    path: string;
    ready: boolean;
  };
  openclaw: {
    binary_path: string | null;
    health: OpenClawHealth;
    manifest: Record<string, unknown>;
    bindings: unknown[];
  };
  faramesh: {
    available: boolean;
    socket_path: string;
    health: FarameshHealth;
    policy_path: string | null;
  };
  cli_available: boolean;
}

export interface OpenClawHealth {
  status: string;
  cli_available: boolean;
  installed: boolean;
  onboarded: boolean;
  gateway_configured: boolean;
  gateway_reachable: boolean;
  gateway_port: number | null;
  gateway_url: string | null;
  credential_detected: boolean;
  config_path: string | null;
  state_dir: string | null;
  doctor_summary: string;
}

export interface FarameshHealth {
  daemon_reachable: boolean;
  socket_reachable: boolean;
  policy_loaded: boolean;
  policy_name: string | null;
  policy_path: string | null;
  decisions_total: number;
  pending_approvals: number;
  denied_today: number;
  deferred_today: number;
  uptime_seconds: number;
  version: string | null;
  doctor_summary: string | null;
}

export interface AuthStatus {
  authenticated: boolean;
  api_url: string;
  user: { email: string; name: string; plan: string } | null;
}

export interface AuthResult {
  success: boolean;
  authenticated?: boolean;
  error?: string;
  user?: { email: string; name: string; plan: string };
}

export interface DoctorResult {
  api_url: string;
  api_url_source: string;
  config_path: string;
  authenticated: boolean;
  api_health: string;
  openclaw: OpenClawHealth;
  runtime_snapshot: Record<string, unknown>;
  faramesh: Record<string, unknown>;
  user: { email: string; name: string; plan: string } | null;
  assistant: {
    name: string;
    status: string;
    onboarding_status: string;
    assistant_id: string;
    workspace: string;
    session_count: number;
    gateway_status: string;
  } | null;
}

export interface WizardState {
  provider: string;
  status: string;
  current_step: string;
  completed_steps: string[];
  failed_step: string | null;
  last_error: string | null;
  steps: Array<{ id: string; title: string; completed: boolean }>;
  providers: Array<{ id: string; label: string; summary: string; enabled: boolean }>;
}

export interface SetupResult {
  success: boolean;
  mode?: string;
  assistant_id?: string;
  workspace?: string;
  deployment?: unknown;
  error?: string;
}

export interface RuntimeInfo {
  openclaw: Record<string, unknown>;
  faramesh: Record<string, unknown>;
  local_control_plane: {
    ready: boolean;
    path: string;
  };
}

export interface AssistantOverview {
  found: true;
  agent_id: string;
  name: string;
  status: string;
  onboarding_status: string;
  assistant_id: string;
  workspace: string;
  session_count: number;
  gateway: { status: string; gateway_url: string | null };
  deployments: Array<{ id: string; status: string }>;
  installed_skills: Array<{ id: string; name: string }>;
}

export interface LocalSession {
  id: string;
  agent: string;
  kind: string;
  age: string;
  model: string;
  tokens: string;
  channel: string;
  active: boolean;
}

export interface AgentInfo {
  id: string;
  name: string;
  type: string;
  status: string;
  description: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface AgentCreateResult {
  success: boolean;
  id?: string;
  name?: string;
  type?: string;
  status?: string;
  error?: string;
}

export interface GovernanceStatus {
  provider: string;
  status: string;
  version: string | null;
  decisions_total: number;
  permits_today: number;
  denies_today: number;
  defers_today: number;
  pending_approvals: number;
  last_decision_at: string | null;
}
