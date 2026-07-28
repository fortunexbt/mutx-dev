import { expect, test, type Page } from '@playwright/test';

const ONE_BY_ONE_PNG = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wn8nWsAAAAASUVORK5CYII=',
  'base64'
);

const mockedAgents = [
  {
    id: 'agent_alpha',
    name: 'alpha-agent',
    status: 'running',
    description: 'Primary smoke-test agent',
    created_at: '2025-03-21T08:00:00Z',
    updated_at: '2025-03-21T08:05:00Z',
  },
  {
    id: 'agent_beta',
    name: 'beta-agent',
    status: 'healthy',
    description: 'Secondary smoke-test agent',
    created_at: '2025-03-20T08:00:00Z',
    updated_at: '2025-03-21T07:45:00Z',
  },
];

const mockedDeployments = [
  {
    id: 'deploy_alpha',
    agent_id: 'agent_alpha',
    status: 'running',
    replicas: 2,
    started_at: '2025-03-21T07:00:00Z',
    ended_at: '2025-03-21T07:45:00Z',
  },
  {
    id: 'deploy_beta',
    agent_id: 'agent_beta',
    status: 'healthy',
    replicas: 1,
    started_at: '2025-03-21T06:15:00Z',
    ended_at: '2025-03-21T07:10:00Z',
  },
];

const mockedRuns = [
  {
    id: 'run_alpha',
    agent_id: 'agent_alpha',
    status: 'completed',
    input_text: 'Promote latest deployment',
    output_text: 'Promotion completed without dropped traces.',
    error_message: null,
    metadata: {},
    started_at: '2025-03-21T07:50:00Z',
    completed_at: '2025-03-21T07:54:00Z',
    created_at: '2025-03-21T07:49:00Z',
    trace_count: 4,
  },
  {
    id: 'run_beta',
    agent_id: 'agent_beta',
    status: 'running',
    input_text: 'Inspect staging rollout',
    output_text: null,
    error_message: null,
    metadata: {},
    started_at: '2025-03-21T08:05:00Z',
    completed_at: null,
    created_at: '2025-03-21T08:04:00Z',
    trace_count: 3,
  },
];

const mockedRunTraces = [
  {
    id: 'trace_alpha_1',
    run_id: 'run_alpha',
    event_type: 'request.received',
    message: 'Ingress accepted by governed operator surface.',
    payload: {},
    sequence: 1,
    timestamp: '2025-03-21T07:50:01Z',
  },
  {
    id: 'trace_alpha_2',
    run_id: 'run_alpha',
    event_type: 'deployment.promoted',
    message: 'Production deployment promoted with receipts.',
    payload: {},
    sequence: 2,
    timestamp: '2025-03-21T07:53:00Z',
  },
];

const mockedAlerts = [
  {
    id: 'alert_alpha',
    agent_id: 'agent_alpha',
    type: 'deployment_failed',
    message: 'Staging rollback was requested after a transient health dip.',
    resolved: false,
    created_at: '2025-03-21T08:12:00Z',
    resolved_at: null,
  },
  {
    id: 'alert_beta',
    agent_id: 'agent_beta',
    type: 'cpu_high',
    message: 'Background run pressure breached the soft queue watermark.',
    resolved: true,
    created_at: '2025-03-21T07:40:00Z',
    resolved_at: '2025-03-21T07:44:00Z',
  },
];

const mockedBudget = {
  user_id: '11111111-1111-1111-1111-111111111111',
  plan: 'operator',
  credits_total: 5000,
  credits_used: 1420,
  credits_remaining: 3580,
  reset_date: '2025-04-01T00:00:00Z',
  usage_percentage: 28,
};

const mockedUsageBreakdown = {
  total_credits_used: 1420,
  credits_remaining: 3580,
  credits_total: 5000,
  period_start: '2025-03-01T00:00:00Z',
  period_end: '2025-03-31T23:59:59Z',
  usage_by_agent: [
    { agent_id: 'agent_alpha', agent_name: 'alpha-agent', credits_used: 840, event_count: 28 },
    { agent_id: 'agent_beta', agent_name: 'beta-agent', credits_used: 580, event_count: 18 },
  ],
  usage_by_type: [
    { event_type: 'run.completed', credits_used: 900, event_count: 24 },
    { event_type: 'webhook.replay', credits_used: 520, event_count: 22 },
  ],
};

const mockedAnalyticsSummary = {
  total_agents: 2,
  active_agents: 2,
  total_deployments: 2,
  active_deployments: 2,
  total_runs: 11,
  successful_runs: 9,
  failed_runs: 2,
  total_api_calls: 324,
  avg_latency_ms: 184,
  period_start: '2025-03-01T00:00:00Z',
  period_end: '2025-03-31T23:59:59Z',
};

const mockedAnalyticsRunTrend = [
  { timestamp: '2025-03-17T00:00:00Z', value: 2, label: 'Mar 17' },
  { timestamp: '2025-03-18T00:00:00Z', value: 4, label: 'Mar 18' },
  { timestamp: '2025-03-19T00:00:00Z', value: 6, label: 'Mar 19' },
  { timestamp: '2025-03-20T00:00:00Z', value: 3, label: 'Mar 20' },
  { timestamp: '2025-03-21T00:00:00Z', value: 5, label: 'Mar 21' },
];

const mockedAnalyticsLatencyTrend = [
  { timestamp: '2025-03-17T00:00:00Z', value: 140, label: 'Mar 17' },
  { timestamp: '2025-03-18T00:00:00Z', value: 164, label: 'Mar 18' },
  { timestamp: '2025-03-19T00:00:00Z', value: 188, label: 'Mar 19' },
  { timestamp: '2025-03-20T00:00:00Z', value: 176, label: 'Mar 20' },
  { timestamp: '2025-03-21T00:00:00Z', value: 184, label: 'Mar 21' },
];

const mockedCostSummary = {
  total_credits_used: 1420,
  credits_remaining: 3580,
  credits_total: 5000,
  usage_by_event_type: {
    'run.completed': 900,
    'webhook.replay': 520,
  },
  usage_by_agent: {
    agent_alpha: 840,
    agent_beta: 580,
  },
  period_start: '2025-03-01T00:00:00Z',
  period_end: '2025-03-31T23:59:59Z',
};

const mockedUsageEvents = [
  {
    id: 'usage_alpha',
    event_type: 'run.completed',
    user_id: '11111111-1111-1111-1111-111111111111',
    resource_id: 'run_alpha',
    event_metadata: '{"credits_used":45}',
    created_at: '2025-03-21T08:01:00Z',
    metadata: {},
  },
  {
    id: 'usage_beta',
    event_type: 'webhook.replay',
    user_id: '11111111-1111-1111-1111-111111111111',
    resource_id: 'wh_alpha',
    event_metadata: '{"credits_used":12}',
    created_at: '2025-03-21T08:09:00Z',
    metadata: {},
  },
];

const mockedSwarms = [
  {
    id: 'swarm_alpha',
    name: 'Revenue Swarm',
    description: 'Grouped promotion lane for revenue-facing agents',
    agent_ids: ['agent_alpha', 'agent_beta'],
    min_replicas: 1,
    max_replicas: 4,
    created_at: '2025-03-18T09:00:00Z',
    updated_at: '2025-03-21T08:08:00Z',
    agents: [
      { agent_id: 'agent_alpha', agent_name: 'alpha-agent', status: 'running', replicas: 2 },
      { agent_id: 'agent_beta', agent_name: 'beta-agent', status: 'healthy', replicas: 1 },
    ],
  },
];

const mockedWebhooks = [
  {
    id: 'wh_alpha',
    url: 'https://hooks.example.com/mutx/alpha',
    events: ['agent.started', 'deployment.completed'],
    is_active: true,
    created_at: '2025-03-20T10:00:00Z',
  },
  {
    id: 'wh_beta',
    url: 'https://hooks.example.com/mutx/beta',
    events: ['run.failed'],
    is_active: false,
    created_at: '2025-03-19T12:00:00Z',
  },
];

const mockedWebhookDeliveries = [
  {
    id: 'whd_alpha',
    event: 'agent.started',
    payload: '{"agent_id":"agent_alpha"}',
    status_code: 200,
    success: true,
    error_message: null,
    attempts: 1,
    created_at: '2025-03-21T08:10:00Z',
    delivered_at: '2025-03-21T08:10:02Z',
  },
  {
    id: 'whd_beta',
    event: 'run.failed',
    payload: '{"run_id":"run_beta"}',
    status_code: 502,
    success: false,
    error_message: 'Upstream timeout',
    attempts: 3,
    created_at: '2025-03-21T08:12:00Z',
    delivered_at: null,
  },
];

const mockedApiKeys = [
  {
    id: 'key_alpha',
    name: 'alpha key',
    created_at: '2025-03-18T09:00:00Z',
    last_used: '2025-03-21T08:00:00Z',
    expires_at: null,
  },
  {
    id: 'key_beta',
    name: 'beta key',
    created_at: '2025-03-17T09:00:00Z',
    last_used: null,
    expires_at: '2025-04-17T09:00:00Z',
  },
];

const mockedSessions = [
  {
    id: 'session_alpha',
    key: 'session_alpha',
    agent: 'OpenClaw Operator',
    kind: 'pairing',
    age: '18m',
    model: 'openai/gpt-5',
    tokens: '12.4k',
    channel: 'webchat',
    flags: ['web', 'paired'],
    active: true,
    start_time: 1742547000,
    last_activity: 1742548200,
    source: 'gateway',
  },
  {
    id: 'session_beta',
    key: 'session_beta',
    agent: 'OpenClaw Operator',
    kind: 'handoff',
    age: '54m',
    model: 'openai/gpt-5-mini',
    tokens: '3.2k',
    channel: 'telegram',
    flags: ['idle'],
    active: false,
    start_time: 1742543400,
    last_activity: 1742545200,
    source: 'gateway',
  },
];

const mockedAssistantOverview = {
  has_assistant: true,
  recommended_template_id: 'personal_assistant',
  assistant: {
    agent_id: '11111111-1111-1111-1111-111111111111',
    name: 'OpenClaw Operator',
    description: 'Tracked OpenClaw assistant',
    runtime: 'personal_assistant',
    template_id: 'personal_assistant',
    status: 'running',
    onboarding_status: 'completed',
    assistant_id: 'openclaw-demo',
    workspace: 'operator-workspace',
    last_activity: '2025-03-21T08:14:00Z',
    session_count: 2,
    installed_skills: [],
    channels: [
      { id: 'webchat', label: 'WebChat', enabled: true, mode: 'pairing', allow_from: [] },
      { id: 'telegram', label: 'Telegram', enabled: false, mode: 'pairing', allow_from: [] },
    ],
    wakeups: [],
    gateway: {
      status: 'healthy',
      cli_available: true,
      gateway_configured: true,
      gateway_reachable: true,
      gateway_port: 18789,
      gateway_url: 'http://127.0.0.1:18789',
      credential_detected: true,
      config_path: '/tmp/openclaw/config.json',
      state_dir: '/tmp/openclaw',
      doctor_summary: 'Gateway reachable from the operator host.',
    },
    deployments: [],
    config: {
      runtime: 'personal_assistant',
      template: 'personal_assistant',
      assistant_id: 'openclaw-demo',
      workspace: 'operator-workspace',
      model: 'openai/gpt-5',
      safety_mode: 'pairing',
      channels: {},
      skills: [],
      wakeups: [],
      metadata: {},
      gateway: {
        port: 18789,
        auth_mode: 'token',
        dashboard_allowed_origins: [],
      },
    },
  },
};

const mockedOnboarding = {
  provider: 'openclaw',
  status: 'completed',
  action_type: 'import_existing_runtime',
  current_step: 'complete',
  completed_steps: ['detect', 'bind', 'complete'],
  assistant_name: 'OpenClaw Operator',
  assistant_id: 'openclaw-demo',
  workspace: 'operator-workspace',
  gateway_url: 'http://127.0.0.1:18789',
  updated_at: '2025-03-21T08:15:00Z',
  steps: [
    { id: 'detect', title: 'Detect OpenClaw runtime', completed: true },
    { id: 'bind', title: 'Bind assistant workspace', completed: true },
    { id: 'complete', title: 'Complete operator sync', completed: true },
  ],
  providers: [
    { id: 'openclaw', label: 'OpenClaw', summary: 'Tracked assistant runtime', enabled: true, cue: 'First' },
    { id: 'codex', label: 'Codex', summary: 'Future provider surface', enabled: false, cue: 'Next' },
  ],
};

const mockedRuntimeSnapshot = {
  provider: 'openclaw',
  label: 'OpenClaw',
  status: 'healthy',
  install_method: 'import_existing_runtime',
  binary_path: '/usr/local/bin/openclaw',
  gateway_url: 'http://127.0.0.1:18789',
  version: '0.4.2',
  home_path: '/tmp/openclaw',
  tracking_mode: 'import_existing_runtime',
  adopted_existing_runtime: true,
  privacy_summary: 'Keys stay local and the dashboard reflects synced metadata only.',
  keys_remain_local: true,
  last_action_type: 'import',
  config_path: '/tmp/openclaw/config.json',
  state_dir: '/tmp/openclaw/state',
  last_seen_at: '2025-03-21T08:15:00Z',
  last_synced_at: '2025-03-21T08:15:00Z',
  stale: false,
  binding_count: 1,
  bindings: [
    {
      assistant_id: 'openclaw-demo',
      assistant_name: 'OpenClaw Operator',
      workspace: 'operator-workspace',
      model: 'openai/gpt-5',
    },
  ],
};

type RouteSpec = {
  path: string;
  heading: RegExp;
  primaryText: RegExp;
  afterLoad?: (page: Page) => Promise<void>;
};

const controlRoutes: RouteSpec[] = [
  {
    path: '/control',
    heading: /environment matrix/i,
    primaryText: /active deployments/i,
  },
  {
    path: '/control/agents',
    heading: /agent registry/i,
    primaryText: /command queue/i,
  },
  {
    path: '/control/deployments',
    heading: /active deployments/i,
    primaryText: /rollout lane/i,
  },
  {
    path: '/control/runs',
    heading: /queue pressure/i,
    primaryText: /active run board/i,
  },
  {
    path: '/control/environments',
    heading: /environment matrix/i,
    primaryText: /readiness signals/i,
  },
  {
    path: '/control/access',
    heading: /credential registry/i,
    primaryText: /auth anomalies/i,
  },
  {
    path: '/control/connectors',
    heading: /connector grid/i,
    primaryText: /delivery exceptions/i,
  },
  {
    path: '/control/audit',
    heading: /audit timeline/i,
    primaryText: /ownership changes/i,
  },
  {
    path: '/control/usage',
    heading: /spend split/i,
    primaryText: /budget posture/i,
  },
  {
    path: '/control/settings',
    heading: /policy packs/i,
    primaryText: /runtime contracts/i,
  },
];

const dashboardRoutes: RouteSpec[] = [
  {
    path: '/dashboard',
    heading: /overview/i,
    primaryText: /operator posture/i,
  },
  {
    path: '/dashboard/agents',
    heading: /agents/i,
    primaryText: /create agent/i,
  },
  {
    path: '/dashboard/agents/agent_alpha',
    heading: /agent-alpha/i,
    primaryText: /configuration snapshot/i,
    afterLoad: async (page) => {
      await expect(page.getByRole('button', { name: /copy id/i })).toBeVisible();
      await expect(page.getByText(/configured execution profile/i)).toBeVisible();
    },
  },
  {
    path: '/dashboard/deployments',
    heading: /deployments/i,
    primaryText: /deployment registry/i,
  },
  {
    path: '/dashboard/deployments/deploy_alpha',
    heading: /deployment deploy_alpha/i,
    primaryText: /recent events/i,
    afterLoad: async (page) => {
      await expect(page.getByRole('link', { name: /view logs/i })).toHaveAttribute(
        'href',
        '/dashboard/logs?deploymentId=deploy_alpha',
      );
      await expect(page.getByText(/deploy\.active/i)).toBeVisible();
    },
  },
  {
    path: '/dashboard/runs',
    heading: /runs/i,
    primaryText: /execution timeline/i,
  },
  {
    path: '/dashboard/traces',
    heading: /traces/i,
    primaryText: /trace stream/i,
  },
  {
    path: '/dashboard/monitoring',
    heading: /monitoring/i,
    primaryText: /alert rail/i,
  },
  {
    path: '/dashboard/observability',
    heading: /observability/i,
    primaryText: /agent runs/i,
  },
  {
    path: '/dashboard/analytics',
    heading: /analytics/i,
    primaryText: /trend lane/i,
  },
  {
    path: '/dashboard/sessions',
    heading: /sessions/i,
    primaryText: /session registry/i,
  },
  {
    path: '/dashboard/api-keys',
    heading: /api keys/i,
    primaryText: /key registry/i,
  },
  {
    path: '/dashboard/budgets',
    heading: /budgets/i,
    primaryText: /usage by agent/i,
  },
  {
    path: '/dashboard/webhooks',
    heading: /webhooks/i,
    primaryText: /add webhook/i,
  },
  {
    path: '/dashboard/security',
    heading: /security/i,
    primaryText: /credential inventory/i,
  },
  {
    path: '/dashboard/memory',
    heading: /memory/i,
    primaryText: /memory surface/i,
  },
  {
    path: '/dashboard/orchestration',
    heading: /orchestration/i,
    primaryText: /orchestration surface/i,
  },
  {
    path: '/dashboard/swarm',
    heading: /swarm/i,
    primaryText: /swarm topology/i,
  },
  {
    path: '/dashboard/control',
    heading: /setup/i,
    primaryText: /provider wizard/i,
  },
  {
    path: '/dashboard/documents',
    heading: /documents/i,
    primaryText: /document workflows/i,
  },
  {
    path: '/dashboard/reasoning',
    heading: /reasoning/i,
    primaryText: /blind judging/i,
  },
  {
    path: '/dashboard/approvals',
    heading: /approval queue/i,
    primaryText: /requester intent/i,
  },
  {
    path: '/dashboard/audit',
    heading: /audit evidence/i,
    primaryText: /attributable control-plane events/i,
  },
  {
    path: '/dashboard/autonomy',
    heading: /autonomy/i,
    primaryText: /live autonomy daemon/i,
  },
  {
    path: '/dashboard/channels',
    heading: /channels/i,
    primaryText: /channel bindings/i,
  },
  {
    path: '/dashboard/templates',
    heading: /templates/i,
    primaryText: /browse, clone, and deploy/i,
  },
  {
    path: '/dashboard/notifications',
    heading: /notifications/i,
    primaryText: /focused inbox/i,
  },
  {
    path: '/dashboard/standup',
    heading: /standup/i,
    primaryText: /read-only brief/i,
  },
  {
    path: '/dashboard/skills',
    heading: /skills/i,
    primaryText: /runtime-ready skill inventory/i,
  },
  {
    path: '/dashboard/history',
    heading: /history/i,
    primaryText: /recent control-plane runs/i,
  },
  {
    path: '/dashboard/logs',
    heading: /logs/i,
    primaryText: /trace events/i,
  },
];

async function mockMatrixTraffic(page: Page) {
  await page.route('https://challenges.cloudflare.com/**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/javascript',
      body:
        'window.turnstile={render:(el,opts)=>{setTimeout(()=>opts?.callback?.("ci-test-token"),0);return "widget-id";},reset:()=>{},remove:()=>{}};',
    });
  });

  await page.route('**/_next/image**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'image/png',
      body: ONE_BY_ONE_PNG,
    });
  });

  await page.route('**/api/**', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const { pathname, searchParams } = url;
    const method = request.method();

    if (pathname === '/api/auth/me' && method === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: '11111111-1111-1111-1111-111111111111',
          email: 'operator@example.com',
          name: 'Operator',
        }),
      });
      return;
    }

    if (pathname === '/api/dashboard/overview' && method === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          generatedAt: '2025-03-21T08:15:00Z',
          session: {
            id: 'user_alpha',
            email: 'operator@mutx.dev',
            name: 'Operator',
            plan: 'operator',
          },
          resources: {
            agents: {
              status: 'ok',
              statusCode: 200,
              data: { items: mockedAgents },
              error: null,
            },
            deployments: {
              status: 'ok',
              statusCode: 200,
              data: { items: mockedDeployments },
              error: null,
            },
            runs: {
              status: 'ok',
              statusCode: 200,
              data: { items: mockedRuns },
              error: null,
            },
            alerts: {
              status: 'ok',
              statusCode: 200,
              data: { items: mockedAlerts },
              error: null,
            },
            webhooks: {
              status: 'ok',
              statusCode: 200,
              data: { webhooks: mockedWebhooks },
              error: null,
            },
            budget: {
              status: 'ok',
              statusCode: 200,
              data: mockedBudget,
              error: null,
            },
            health: {
              status: 'ok',
              statusCode: 200,
              data: {
                status: 'ok',
                database: 'ok',
                timestamp: '2025-03-21T08:15:00Z',
                uptime: 98765,
                agents: mockedAgents.length,
                deployments: mockedDeployments.length,
              },
              error: null,
            },
            runtime: {
              status: 'ok',
              statusCode: 200,
              data: mockedRuntimeSnapshot,
              error: null,
            },
            onboarding: {
              status: 'ok',
              statusCode: 200,
              data: mockedOnboarding,
              error: null,
            },
          },
        }),
      });
      return;
    }

    if (pathname === '/api/dashboard/agents' && method === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mockedAgents),
      });
      return;
    }

    if (pathname.startsWith('/api/dashboard/agents/') && method === 'GET') {
      const agentId = decodeURIComponent(pathname.split('/').pop() ?? 'agent_alpha');
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: agentId,
          name: agentId.replace(/_/g, '-'),
          status: 'running',
          type: 'operator',
          description: 'Route matrix detail payload',
          created_at: '2025-03-21T08:00:00Z',
          updated_at: '2025-03-21T08:05:00Z',
          user_id: '11111111-1111-1111-1111-111111111111',
          config_version: 7,
          config: { mode: 'matrix' },
        }),
      });
      return;
    }

    if (pathname === '/api/dashboard/deployments' && method === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mockedDeployments),
      });
      return;
    }

    if (pathname === '/api/dashboard/runs' && method === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          items: mockedRuns,
          total: mockedRuns.length,
          skip: 0,
          limit: Number(searchParams.get('limit') || 24),
          status: null,
          agent_id: null,
        }),
      });
      return;
    }

    if (pathname.startsWith('/api/dashboard/runs/') && pathname.endsWith('/traces') && method === 'GET') {
      const runId = pathname.split('/')[4] ?? 'run_alpha';
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          run_id: runId,
          items: mockedRunTraces.map((trace) => ({ ...trace, run_id: runId })),
          total: mockedRunTraces.length,
          skip: 0,
          limit: Number(searchParams.get('limit') || 64),
          event_type: null,
        }),
      });
      return;
    }

    if (pathname === '/api/dashboard/monitoring/alerts' && method === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          items: mockedAlerts,
          total: mockedAlerts.length,
          unresolved_count: mockedAlerts.filter((alert) => !alert.resolved).length,
        }),
      });
      return;
    }

    if (pathname === '/api/dashboard/budgets' && method === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mockedBudget),
      });
      return;
    }

    if (pathname === '/api/dashboard/budgets/usage' && method === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mockedUsageBreakdown),
      });
      return;
    }

    if (pathname === '/api/dashboard/analytics/summary' && method === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mockedAnalyticsSummary),
      });
      return;
    }

    if (pathname === '/api/dashboard/analytics/timeseries' && method === 'GET') {
      const metric = searchParams.get('metric');
      const data = metric === 'latency' ? mockedAnalyticsLatencyTrend : mockedAnalyticsRunTrend;
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          metric: metric || 'runs',
          interval: searchParams.get('interval') || 'day',
          data,
          period_start: '2025-03-01T00:00:00Z',
          period_end: '2025-03-31T23:59:59Z',
        }),
      });
      return;
    }

    if (pathname === '/api/dashboard/analytics/costs' && method === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mockedCostSummary),
      });
      return;
    }

    if (pathname === '/api/dashboard/usage/events' && method === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          items: mockedUsageEvents,
          total: mockedUsageEvents.length,
          skip: 0,
          limit: Number(searchParams.get('limit') || 12),
        }),
      });
      return;
    }

    if (pathname === '/api/dashboard/swarms' && method === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          items: mockedSwarms,
          total: mockedSwarms.length,
          skip: 0,
          limit: Number(searchParams.get('limit') || 16),
        }),
      });
      return;
    }

    if (pathname === '/api/dashboard/sessions' && method === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ sessions: mockedSessions }),
      });
      return;
    }

    if (pathname === '/api/dashboard/assistant/overview' && method === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mockedAssistantOverview),
      });
      return;
    }

    if (pathname.startsWith('/api/dashboard/deployments/') && method === 'GET') {
      const deploymentId = decodeURIComponent(pathname.split('/').pop() ?? 'deploy_alpha');
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: deploymentId,
          agent_id: 'agent_alpha',
          status: 'running',
          version: '1.3.0-rc.2',
          replicas: 2,
          node_id: 'node-matrix-01',
          started_at: '2025-03-21T07:00:00Z',
          ended_at: '2025-03-21T07:45:00Z',
          error_message: null,
          events: [
            {
              id: 'deploy_event_alpha',
              deployment_id: deploymentId,
              event_type: 'deploy.active',
              status: 'running',
              node_id: 'node-matrix-01',
              error_message: null,
              created_at: '2025-03-21T07:01:00Z',
            },
            {
              id: 'deploy_event_beta',
              deployment_id: deploymentId,
              event_type: 'health.check',
              status: 'healthy',
              node_id: 'node-matrix-01',
              error_message: null,
              created_at: '2025-03-21T07:03:00Z',
            },
          ],
        }),
      });
      return;
    }

    if (pathname === '/api/webhooks' && method === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ webhooks: mockedWebhooks }),
      });
      return;
    }

    if (pathname.startsWith('/api/webhooks/') && pathname.endsWith('/deliveries') && method === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ deliveries: mockedWebhookDeliveries }),
      });
      return;
    }

    if (pathname === '/api/api-keys' && method === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          items: mockedApiKeys.map((key) => ({
            ...key,
            status: 'active',
            last_used_at: key.last_used,
            scopes: ['operator'],
          })),
        }),
      });
      return;
    }

    if (pathname === '/api/dashboard/health' && method === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          status: 'ok',
          database: 'ok',
          timestamp: '2025-03-21T08:15:00Z',
          uptime: 98765,
          agents: mockedAgents.length,
          deployments: mockedDeployments.length,
        }),
      });
      return;
    }

    if (pathname === '/api/dashboard/onboarding' && method === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mockedOnboarding),
      });
      return;
    }

    if (pathname === '/api/dashboard/runtime/providers/openclaw' && method === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mockedRuntimeSnapshot),
      });
      return;
    }

    if (
      (pathname === '/api/dashboard/documents/templates' ||
        pathname === '/api/dashboard/reasoning/templates' ||
        pathname === '/api/dashboard/clawhub/skills' ||
        pathname === '/api/dashboard/clawhub/bundles' ||
        (pathname.startsWith('/api/dashboard/assistant/') && pathname.endsWith('/skills'))) &&
      method === 'GET'
    ) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([]),
      });
      return;
    }

    if (
      (pathname === '/api/dashboard/documents/jobs' ||
        pathname === '/api/dashboard/reasoning/jobs') &&
      method === 'GET'
    ) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ items: [], total: 0 }),
      });
      return;
    }

    if (pathname === '/api/dashboard/approvals' && method === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          items: [],
          total: 0,
          skip: Number(searchParams.get('skip') || 0),
          limit: Number(searchParams.get('limit') || 20),
        }),
      });
      return;
    }

    if (pathname === '/api/dashboard/audit/events' && method === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ events: [], total: 0 }),
      });
      return;
    }

    if (pathname === '/api/dashboard/autonomy' && method === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          status: 'ok',
          scope: 'local-only',
          availability: 'complete',
          generatedAt: '2025-03-21T08:15:00Z',
          freshness: {
            state: 'fresh',
            heartbeatAt: '2025-03-21T08:15:00Z',
            ageSeconds: 0,
            staleAfterSeconds: 1200,
          },
          sources: { available: 4, missing: 0 },
          daemon: {
            reportedStatus: 'idle',
            live: false,
            cycleCount: 0,
            lastCycleCompletedAt: null,
            lastResultStatus: null,
          },
          lanes: [],
          fleet: { roles: [] },
          generatedTasks: [],
          queue: {
            counts: { queued: 0, running: 0, parked: 0, completed: 0, other: 0 },
            queued: [],
            running: [],
            parked: [],
            completed: [],
          },
          activeRunners: [],
          reports: [],
        }),
      });
      return;
    }

    if (pathname === '/api/dashboard/channels' && method === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          generatedAt: '2025-03-21T08:15:00Z',
          hasAssistant: false,
          assistant: null,
          sourceStatus: {
            overview: 'ok',
            channels: 'ok',
            sessions: 'ok',
          },
          summary: {
            configuredChannels: 0,
            enabledChannels: 0,
            liveChannels: 0,
            activeSessions: 0,
            sources: 0,
          },
          channels: [],
          sessionSources: [],
          partials: [],
        }),
      });
      return;
    }

    if (pathname === '/api/dashboard/templates' && method === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([]),
      });
      return;
    }

    if (pathname === '/api/dashboard/templates/state' && method === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          pinned_template_ids: [],
          recent_template_ids: [],
          deployment_count_by_template: {},
        }),
      });
      return;
    }

    if (pathname === '/api/dashboard/notifications' && method === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          generatedAt: '2025-03-21T08:15:00Z',
          summary: {
            alerts: 0,
            approvals: 0,
            webhookFailures: 0,
            runtimeIncidents: 0,
            governancePendingApprovals: null,
          },
          sources: {
            alerts: 'ok',
            approvals: 'ok',
            webhooks: 'ok',
            runtime: 'ok',
            governance: 'partial',
          },
          items: [],
          partials: ['Governance event totals are not exposed by the current contract.'],
        }),
      });
      return;
    }

    if (pathname === '/api/dashboard/standup' && method === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          generatedAt: '2025-03-21T08:15:00Z',
          focus: 'No verified blockers in the mocked source feeds.',
          metrics: {
            openAlerts: 0,
            pendingApprovals: 0,
            failedRuns: 0,
            queuedAutonomy: null,
          },
          sources: {
            alerts: 'ok',
            approvals: 'ok',
            runs: 'ok',
            webhooks: 'ok',
            autonomy: 'partial',
          },
          blockers: [],
          watchlist: [],
          completions: [],
          partials: ['Local autonomy is unavailable in the browser test environment.'],
        }),
      });
      return;
    }

    if (pathname === '/api/dashboard/memory' && method === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          generatedAt: '2025-03-21T08:15:00Z',
          assistant: null,
          sourceStatus: {
            assistant: 'ok',
            sessions: 'ok',
            documents: 'ok',
            reasoning: 'ok',
          },
          summary: {
            sessions: 0,
            activeSessions: 0,
            sources: 0,
            documentJobs: 0,
            documentArtifacts: 0,
            reasoningJobs: 0,
            reasoningArtifacts: 0,
          },
          sessions: [],
          sources: [],
          documents: [],
          reasoning: [],
          partials: ['Memory inventory is read-only.'],
        }),
      });
      return;
    }

    if (pathname === '/api/dashboard/orchestration' && method === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          generatedAt: '2025-03-21T08:15:00Z',
          sourceStatus: {
            approvals: 'ok',
            runs: 'ok',
            sessions: 'ok',
            blueprints: 'ok',
            autonomy: 'partial',
          },
          summary: {
            pendingApprovals: 0,
            recoveryWatch: 0,
            blueprints: 0,
            queuedAutonomy: null,
            runningAutonomy: null,
          },
          approvals: [],
          recoveries: [],
          blueprints: [],
          autonomy: null,
          partials: ['Local autonomy is unavailable in the browser test environment.'],
        }),
      });
      return;
    }

    if (method === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({}),
      });
      return;
    }

    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ ok: true }),
    });
  });
}

async function assertNoOverflow(page: Page) {
  const metrics = await page.evaluate(() => {
    const doc = document.documentElement;
    return {
      scrollWidth: doc.scrollWidth,
      clientWidth: doc.clientWidth,
    };
  });

  expect(
    metrics.scrollWidth,
    `expected no horizontal overflow, but scrollWidth=${metrics.scrollWidth} and clientWidth=${metrics.clientWidth}`,
  ).toBeLessThanOrEqual(metrics.clientWidth + 1);
}

async function expectVisibleRouteTitle(page: Page, heading: RegExp) {
  const headingByRole = page.getByRole('heading', { name: heading }).first();

  try {
    await expect(headingByRole).toBeVisible({ timeout: 12000 });
    return;
  } catch {
    // Some demo routes use styled text instead of semantic heading tags.
  }

  await expect(page.getByText(heading).first()).toBeVisible({ timeout: 12000 });
}

async function assertRouteSurface(page: Page, route: RouteSpec) {
  const response = await page.goto(route.path, { waitUntil: 'domcontentloaded' });

  expect(response, `No response returned for ${route.path}`).not.toBeNull();
  expect(response?.status(), `${route.path} returned ${response?.status()}`).toBeLessThan(500);

  await expect(page.getByText(/Internal Server Error/i)).toHaveCount(0);
  await expect(page.getByText(/^Loading\.\.\.$/i)).toHaveCount(0, { timeout: 15000 });
  await expectVisibleRouteTitle(page, route.heading);
  await expect(page.getByText(route.primaryText).first()).toBeVisible({ timeout: 15000 });
  await assertNoOverflow(page);

  if (route.afterLoad) {
    await route.afterLoad(page);
  }
}

async function exerciseMobileSidebar(page: Page, heading: RegExp) {
  const openSidebar = page.getByRole('button', { name: /open dashboard sidebar/i });

  if (!(await openSidebar.count())) {
    return;
  }

  if (!(await openSidebar.first().isVisible().catch(() => false))) {
    return;
  }

  await openSidebar.first().click();

  const closeSidebar = page.getByRole('button', { name: /close dashboard sidebar/i });
  await expect(closeSidebar.first()).toBeVisible({ timeout: 5000 });

  await closeSidebar.first().dispatchEvent('click');
  await expectVisibleRouteTitle(page, heading);
  await assertNoOverflow(page);
}

test.describe('Dashboard route matrix', () => {
  test.describe('desktop', () => {
    test.beforeEach(async ({ page }) => {
      await mockMatrixTraffic(page);
    });

    for (const route of controlRoutes) {
      test(`control route renders: ${route.path}`, async ({ page }) => {
        await assertRouteSurface(page, route);
      });
    }

    for (const route of dashboardRoutes) {
      test(`dashboard route renders: ${route.path}`, async ({ page }) => {
        await assertRouteSurface(page, route);
      });
    }

    test('primary navigation exposes stable routes and hides redirect-only aliases', async ({ page }) => {
      await page.goto('/dashboard', { waitUntil: 'domcontentloaded' });

      await expect(page.getByRole('link', { name: /^memory$/i })).toBeVisible();
      await expect(page.getByRole('link', { name: /^orchestration$/i })).toBeVisible();
      await expect(page.getByRole('link', { name: /^channels$/i })).toBeVisible();
      await expect(page.getByRole('link', { name: /^skills$/i })).toBeVisible();
      await expect(page.getByRole('link', { name: /^logs$/i })).toBeVisible();
      await expect(page.getByRole('link', { name: /^history$/i })).toHaveCount(0);
      await expect(page.getByRole('link', { name: /^spawn$/i })).toHaveCount(0);
    });

    test('spawn alias opens the canonical create-agent workflow', async ({ page }) => {
      await page.goto('/dashboard/spawn', { waitUntil: 'domcontentloaded' });

      await expect(page).toHaveURL(/\/dashboard\/agents\?create=1$/);
      await expectVisibleRouteTitle(page, /agents/i);
      await expect(page.getByRole('dialog', { name: /create agent/i })).toBeVisible();
    });

    test('command palette is keyboard accessible', async ({ page }) => {
      await page.goto('/dashboard', { waitUntil: 'domcontentloaded' });

      await expect(page.getByRole('button', { name: /open command palette/i })).toBeEnabled();
      await page.keyboard.press('Control+K');
      const palette = page.getByRole('dialog', { name: /go anywhere/i });
      await expect(palette).toBeVisible();
      const search = page.getByRole('combobox', { name: /search dashboard surfaces/i });
      const options = palette.getByRole('option');
      await expect(search).toBeFocused();

      await page.keyboard.press('End');
      await expect(options.last()).toHaveAttribute('aria-selected', 'true');
      await page.keyboard.press('Home');
      await expect(options.first()).toHaveAttribute('aria-selected', 'true');

      await page.keyboard.press('Escape');
      await expect(palette).toHaveCount(0);
    });
  });

  test.describe('mobile', () => {
    test.use({
      viewport: { width: 390, height: 844 },
      isMobile: true,
      hasTouch: true,
    });

    test.beforeEach(async ({ page }) => {
      await mockMatrixTraffic(page);
    });

    for (const route of controlRoutes) {
      test(`control route renders on mobile: ${route.path}`, async ({ page }) => {
        await assertRouteSurface(page, route);
      });
    }

    for (const route of dashboardRoutes) {
      test(`dashboard route renders on mobile: ${route.path}`, async ({ page }) => {
        await assertRouteSurface(page, route);
        await exerciseMobileSidebar(page, route.heading);
      });
    }
  });
});
