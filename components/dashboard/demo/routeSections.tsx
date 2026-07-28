import {
  Server,
  Wallet,
} from "lucide-react";

import type { DemoSection } from "@/components/dashboard/demo/demoSections";
import {
  AGENT_NAMES,
  formatCurrency,
  QUICK_ACTIONS,
  relativeStamp,
} from "@/components/dashboard/demo/demoContent";
import type {
  AgentCard,
  AuditItem,
  ConnectorCard,
  DeploymentRow,
  MatrixRow,
  Metric,
  SignalItem,
  Tone,
} from "@/components/dashboard/demo/demoContent";
import {
  AgentRegistryCard,
  ConnectorGrid,
  DeploymentsTable,
  EnvironmentCardsMobile,
  EnvironmentMatrix,
  MetricCard,
  ProgressRow,
  RailSection,
  RecordStack,
  QuickActionButton,
  SectionIntroBar,
  SectionPill,
  SignalToneIcon,
  Sparkline,
  StatusBadge,
  SurfacePanel,
} from "@/components/dashboard/demo/demoPrimitives";

function OverviewSection({
  tick,
  signals,
  auditItems,
  activeAction,
}: {
  tick: number;
  signals: SignalItem[];
  auditItems: AuditItem[];
  activeAction: number;
}) {
  const cycle = tick % 6;
  const metrics: Metric[] = [
    { label: "Agents", value: `${56 + (tick % 3)}`, meta: "fleet", tone: "focus" },
    { label: "Deployments", value: `${24 + (tick % 2)}`, meta: "active", tone: "neutral" },
    { label: "Runs (24h)", value: `${187 + ((tick * 7) % 18)}`, meta: "throughput", tone: "healthy" },
    { label: "Success rate", value: `${(94.7 + Math.sin(tick / 2.4) * 0.4).toFixed(1)}%`, meta: "success", tone: "focus" },
    { label: "Infra cost", value: formatCurrency(2.3 + ((tick % 5) * 0.2)), meta: "today", tone: "focus" },
    { label: "Incidents", value: `${2 + (tick % 2)}`, meta: "open", tone: cycle === 1 ? "warning" : "neutral" },
  ];

  const rows: MatrixRow[] = [
    {
      label: "Deployments",
      meta: "runtime mix",
      cells: [
        { value: `${12 + (tick % 2)} active`, detail: "OpenClaw + LangChain", stamp: relativeStamp(2 + cycle), tone: "healthy", badge: "OK" },
        { value: `${7 + ((tick + 1) % 2)} active`, detail: "candidate rollouts", stamp: relativeStamp(6 + cycle), tone: "focus", badge: "Active" },
        { value: `${5 + (tick % 3)} sandboxes`, detail: "n8n + OpenClaw", stamp: relativeStamp(3 + cycle), tone: "neutral", badge: "Ready" },
      ],
    },
    {
      label: "Active runs",
      meta: "queue pressure",
      cells: [
        { value: `${86 + (tick % 7)} live`, detail: "queue steady", stamp: relativeStamp(1), tone: "healthy", badge: "OK" },
        { value: `${19 + (tick % 4)} live`, detail: "replay window", stamp: relativeStamp(4), tone: cycle === 2 ? "warning" : "focus", badge: cycle === 2 ? "Watch" : "Active" },
        { value: `${14 + (tick % 5)} live`, detail: "bursting", stamp: relativeStamp(2), tone: cycle === 4 ? "warning" : "neutral", badge: cycle === 4 ? "Watch" : "Ready" },
      ],
    },
    {
      label: "Policy state",
      meta: "guardrails",
      cells: [
        { value: cycle === 3 ? "2 blocks" : "1 block", detail: "tool egress denied", stamp: relativeStamp(10 + cycle), tone: "warning", badge: "Watch" },
        { value: "simulate mode", detail: "candidate rules", stamp: relativeStamp(12 + cycle), tone: "focus", badge: "Active" },
        { value: "learning", detail: "signal capture", stamp: relativeStamp(7 + cycle), tone: "neutral", badge: "Ready" },
      ],
    },
    {
      label: "Keys / secrets",
      meta: "access hygiene",
      cells: [
        { value: `${14 + (tick % 2)} healthy`, detail: cycle === 1 ? "1 rotation due" : "inside rotation window", stamp: relativeStamp(8 + cycle), tone: cycle === 1 ? "warning" : "healthy", badge: cycle === 1 ? "Watch" : "OK" },
        { value: "6 rotated", detail: "staged credentials current", stamp: relativeStamp(18 + cycle), tone: "healthy", badge: "OK" },
        { value: "4 ephemeral", detail: "sandbox scoped", stamp: relativeStamp(5 + cycle), tone: "focus", badge: "Active" },
      ],
    },
    {
      label: "Network posture",
      meta: "traffic stance",
      cells: [
        { value: "private mesh", detail: "egress pinned", stamp: relativeStamp(1 + cycle), tone: "healthy", badge: "OK" },
        { value: "relay warm", detail: "regional failover armed", stamp: relativeStamp(7 + cycle), tone: "focus", badge: "Active" },
        { value: "shared gateway", detail: "tool fanout enabled", stamp: relativeStamp(3 + cycle), tone: "neutral", badge: "Ready" },
      ],
    },
    {
      label: "Health / readiness",
      meta: "service probes",
      cells: [
        { value: `${(99.94 + Math.sin(tick / 3.4) * 0.03).toFixed(2)}%`, detail: "ready / healthy", stamp: relativeStamp(1), tone: "healthy", badge: "OK" },
        { value: cycle === 5 ? "warming" : "ready", detail: cycle === 5 ? "one replica catching up" : "fleet responsive", stamp: relativeStamp(2 + cycle), tone: cycle === 5 ? "warning" : "healthy", badge: cycle === 5 ? "Watch" : "OK" },
        { value: "ready", detail: "sandbox probes green", stamp: relativeStamp(2 + cycle), tone: "healthy", badge: "OK" },
      ],
    },
  ];

  const deployments: DeploymentRow[] = [
    { agent: "Sales Ops Assistant", runtime: "OpenClaw", environment: "Production", version: `v1.4.${tick % 2}`, region: "EU-West", health: "Healthy", tone: "healthy", rollout: relativeStamp(4 + (tick % 4)) },
    { agent: "Data Processor", runtime: "LangChain", environment: "Staging", version: "v1.6.1", region: "US-East", health: tick % 5 === 0 ? "Policy Watch" : "Healthy", tone: tick % 5 === 0 ? "warning" : "healthy", rollout: relativeStamp(12 + (tick % 5)) },
    { agent: "Autonomous Crawler", runtime: "n8n", environment: "Development", version: `v0.9.${2 + (tick % 3)}`, region: "EU-West", health: "Healthy", tone: "healthy", rollout: relativeStamp(28 + (tick % 6)) },
    { agent: "Research Automator", runtime: "OpenClaw", environment: "Production", version: "v2.0.4", region: "US-West", health: tick % 6 === 3 ? "Self-healing" : "Healthy", tone: tick % 6 === 3 ? "focus" : "healthy", rollout: relativeStamp(34 + (tick % 7)) },
    { agent: "Billing Resolver", runtime: "LangChain", environment: "Staging", version: "v1.2.7", region: "US-East", health: "Healthy", tone: "healthy", rollout: relativeStamp(41 + (tick % 9)) },
    { agent: "Support Router", runtime: "OpenClaw", environment: "Production", version: "v1.8.3", region: "AP-South", health: tick % 4 === 1 ? "Policy Watch" : "Healthy", tone: tick % 4 === 1 ? "warning" : "healthy", rollout: relativeStamp(19 + (tick % 5)) },
    { agent: "Retrieval Indexer", runtime: "LangChain", environment: "Staging", version: "v0.8.9", region: "EU-Central", health: "Healthy", tone: "healthy", rollout: relativeStamp(52 + (tick % 7)) },
  ];

  const governance = [
    {
      title: "Policy block: Unauthorized tool action",
      detail: "Outbound connector call stopped before side effects escaped the boundary.",
      meta: `Production · ${relativeStamp(2 + (tick % 4))}`,
      tone: "warning" as Tone,
    },
    {
      title: "Seal decision: Human approval required",
      detail: "Privileged export held after ownership boundary and policy scope disagreed.",
      meta: `Staging · ${relativeStamp(11 + (tick % 6))}`,
      tone: tick % 3 === 0 ? ("critical" as Tone) : ("warning" as Tone),
    },
    {
      title: "API key hygiene warning",
      detail: "External operator credential is nearing rotation threshold with no recent successful use.",
      meta: `Access · ${relativeStamp(34 + (tick % 6))}`,
      tone: "warning" as Tone,
    },
    {
      title: "Ownership transfer recorded",
      detail: "Revenue Infra accepted the production rollout contract after the latest governed promotion.",
      meta: `Audit · ${relativeStamp(47 + (tick % 6))}`,
      tone: "focus" as Tone,
    },
  ];

  const connectors: ConnectorCard[] = [
    { name: "GitHub", detail: "Deploy hooks and release metadata", status: tick % 4 === 0 ? "Watch" : "Healthy", tone: tick % 4 === 0 ? "warning" : "healthy", stamp: relativeStamp(3 + (tick % 4)) },
    { name: "Stripe", detail: "Billing events on governed fanout", status: "Healthy", tone: "healthy", stamp: relativeStamp(1 + (tick % 3)) },
    { name: "Twilio", detail: "Outbound comms webhook delivery", status: tick % 5 === 2 ? "Retrying" : "Healthy", tone: tick % 5 === 2 ? "warning" : "healthy", stamp: relativeStamp(2 + (tick % 5)) },
    { name: "HubSpot", detail: "CRM sync and ownership projection", status: tick % 6 === 1 ? "Delayed" : "Healthy", tone: tick % 6 === 1 ? "warning" : "focus", stamp: relativeStamp(12 + (tick % 6)) },
  ];

  const queuePressure = 38 + ((tick * 3) % 21);
  const cpuLoad = 55 + (tick % 18);
  const memoryLoad = 47 + ((tick * 2) % 22);

  return (
    <div className="flex min-h-0 flex-col gap-2.5 overflow-visible lg:h-full lg:overflow-hidden">
      <div className="shrink-0 overflow-hidden rounded-[4px] border border-[#2b2b26] bg-[#0c0d0b]">
        <div className="grid grid-cols-2 gap-px bg-[#2b2b26] sm:grid-cols-3 lg:grid-cols-6">
          {metrics.map((metric) => (
            <div key={metric.label} className="bg-[#0c0d0b]">
              <MetricCard metric={metric} />
            </div>
          ))}
        </div>
      </div>

      <section className="flex shrink-0 flex-col overflow-hidden rounded-[6px] border border-[#34342e] bg-[#11120f] p-3 lg:h-[min(328px,34dvh)] xl:h-[min(336px,35dvh)]">
        <div className="grid shrink-0 gap-3 lg:grid-cols-[minmax(0,1fr)_164px] lg:items-start">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-[11px] font-semibold tracking-[0.14em] text-[#ff8355]">Overview</span>
              <span className="hidden h-4 w-px bg-[#34342e] lg:block" />
              <SectionPill label="Production lane" />
              <SectionPill label="Governed rollout" tone="healthy" />
              <SectionPill label="BYOK aware" />
            </div>
            <h2 className="mt-2 text-[30px] font-semibold leading-none tracking-[-0.06em] text-[#eee9dc] sm:text-[34px] lg:text-[38px]">
              Environment Matrix
            </h2>
            <p className="mt-1.5 max-w-3xl text-[12px] leading-5 text-[#aaa397] sm:text-[13px] sm:leading-5">
              Deployments, runs, policy, secrets, network posture, and readiness across production, staging, and development.
            </p>
          </div>

          <div className="grid grid-cols-2 gap-2 lg:grid-cols-1">
            <div className="rounded-[4px] border border-[#2b2b26] bg-[#151612] px-2.5 py-1.5">
              <div className="text-[11px] font-medium tracking-[0.12em] text-[#8d867a]">Change window</div>
              <div className="mt-1 text-[12px] font-medium leading-5 text-[#eee9dc]">Governed rollout lane active</div>
            </div>
            <div className="rounded-[4px] border border-[#2b2b26] bg-[#151612] px-2.5 py-1.5">
              <div className="text-[11px] font-medium tracking-[0.12em] text-[#8d867a]">Ownership</div>
              <div className="mt-1 text-[12px] font-medium leading-5 text-[#eee9dc]">Acme Corp / Revenue Infra</div>
            </div>
          </div>
        </div>

        <div className="mt-3 min-h-0 flex-1 overflow-hidden">
          <EnvironmentCardsMobile rows={rows} />
          <div className="hidden h-full md:block">
            <EnvironmentMatrix rows={rows} />
          </div>
        </div>
      </section>

      <div className="grid min-h-0 flex-1 grid-cols-1 gap-3 overflow-visible lg:grid-cols-[minmax(0,1.16fr)_minmax(336px,0.84fr)] lg:overflow-hidden xl:grid-cols-[minmax(0,1.12fr)_minmax(360px,0.88fr)]">
        <div className="grid min-h-0 grid-cols-1 gap-3 overflow-visible lg:grid-rows-[minmax(0,1.16fr)_minmax(132px,0.56fr)] lg:overflow-hidden">
          <SurfacePanel title="Active Deployments" meta="fleet surface" bodyClassName="p-0 lg:p-0">
            <DeploymentsTable rows={deployments} />
          </SurfacePanel>

          <SurfacePanel title="Guardrails & Governance" meta="operator tension">
            <RecordStack items={governance} />
          </SurfacePanel>
        </div>

        <div className="grid min-h-0 grid-cols-1 gap-3 overflow-visible lg:grid-rows-[minmax(0,1.08fr)_minmax(152px,0.68fr)] lg:overflow-hidden">
          <SurfacePanel title="Cost & Capacity" meta="infra vs model">
            <div className="flex h-full min-h-0 flex-col gap-3">
              <div className="grid shrink-0 grid-cols-1 gap-3 sm:grid-cols-2">
                <div className="rounded-[4px] border border-[#34342e] bg-[#11120f] p-2.5">
                  <div className="flex items-center gap-2 text-[#999284]">
                    <Server className="h-4 w-4 text-[#58aaff]" />
                    <span className="text-[11px] font-medium uppercase tracking-[0.18em]">Infra spend</span>
                  </div>
                  <div className="mt-1.5 text-[21px] font-semibold tracking-[-0.04em] text-[#eee9dc]">{formatCurrency(1730 + tick * 26)}</div>
                  <div className="mt-1 text-[11px] text-[#999284]">control plane / queues / env overhead</div>
                </div>
                <div className="rounded-[4px] border border-[#34342e] bg-[#11120f] p-2.5">
                  <div className="flex items-center gap-2 text-[#999284]">
                    <Wallet className="h-4 w-4 text-[#58aaff]" />
                    <span className="text-[11px] font-medium uppercase tracking-[0.18em]">Model spend</span>
                  </div>
                  <div className="mt-1.5 text-[21px] font-semibold tracking-[-0.04em] text-[#eee9dc]">{formatCurrency(970 + tick * 18)}</div>
                  <div className="mt-1 text-[11px] text-[#999284]">separate BYOK consumption envelope</div>
                </div>
              </div>
              <div className="min-h-0 flex-1 rounded-[4px] border border-[#34342e] bg-[#11120f] p-2.5">
                <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                  <div>
                    <div className="text-[11px] font-medium uppercase tracking-[0.18em] text-[#8d867a]">Load ridge</div>
                    <div className="mt-1 text-[13px] text-[#aaa397]">Queue pressure {queuePressure}%</div>
                  </div>
                  <div className="flex items-center gap-2 sm:block sm:text-right">
                    <div className="text-[11px] text-[#58aaff]">57% headroom</div>
                    <div className="text-[11px] font-medium uppercase tracking-[0.18em] text-[#8d867a]">63 req/s</div>
                  </div>
                </div>
                <div className="mt-3 grid gap-3">
                  <ProgressRow
                    label="Queue pressure"
                    value={queuePressure}
                    tone={queuePressure >= 52 ? "warning" : "focus"}
                  />
                  <div className="grid gap-3 sm:grid-cols-2">
                    <ProgressRow label="CPU" value={cpuLoad} tone={cpuLoad >= 72 ? "warning" : "focus"} />
                    <ProgressRow label="Memory" value={memoryLoad} tone={memoryLoad >= 72 ? "warning" : "focus"} />
                  </div>
                </div>
              </div>
            </div>
          </SurfacePanel>

          <SurfacePanel title="Connectors & Webhooks" meta="delivery plane">
            <ConnectorGrid connectors={connectors} />
          </SurfacePanel>
        </div>
      </div>

      <div className="grid gap-3 2xl:hidden">
        <RailSection title="Live Signals" meta={`${signals.length} items`}>
          <div className="flex h-full min-h-0 flex-col gap-2">
            {signals.slice(0, 4).map((signal) => (
              <div key={`${signal.title}-${signal.stamp}`} className="rounded-[4px] border border-[#2b2b26] bg-[#11120f] p-2.5">
                <div className="flex items-start gap-3">
                  <div className="mt-0.5">
                    <SignalToneIcon tone={signal.tone} />
                  </div>
                  <div className="min-w-0">
                    <div className="flex items-center justify-between gap-3">
                      <div className="truncate text-[13px] font-semibold text-[#eee9dc]">{signal.title}</div>
                      <div className="text-[11px] font-medium tracking-[0.12em] text-[#8d867a]">{signal.stamp}</div>
                    </div>
                    <div className="mt-1 overflow-hidden text-[12px] leading-5 text-[#aaa397] [display:-webkit-box] [-webkit-box-orient:vertical] [-webkit-line-clamp:3]">
                      {signal.detail}
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </RailSection>

        <div className="grid gap-3 sm:grid-cols-2">
          <RailSection title="Audit Trail" meta="operator actions">
            <div className="flex h-full min-h-0 flex-col gap-2">
              {auditItems.map((item) => (
                <div key={`${item.title}-${item.stamp}`} className="rounded-[4px] border border-[#2b2b26] bg-[#11120f] p-2.5">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="text-[13px] font-semibold text-[#eee9dc]">{item.title}</div>
                      <div className="mt-1 text-[12px] text-[#aaa397]">{item.resource}</div>
                      <div className="mt-2 text-[11px] font-medium tracking-[0.12em] text-[#8d867a]">
                        {item.role} · {item.actor}
                      </div>
                    </div>
                    <div className="text-[11px] font-medium tracking-[0.12em] text-[#8d867a]">{item.stamp}</div>
                  </div>
                </div>
              ))}
            </div>
          </RailSection>

          <RailSection title="Quick Actions" meta="operator controls">
            <div className="flex h-full min-h-0 flex-col gap-2.5">
              {QUICK_ACTIONS.map((action, index) => (
                <QuickActionButton key={action.label} action={action} active={index === activeAction} />
              ))}
            </div>
          </RailSection>
        </div>
      </div>
    </div>
  );
}

function AgentsSection({ tick }: { tick: number }) {
  const agents: AgentCard[] = AGENT_NAMES.map((name, index) => {
    const active = (index + tick) % 5;
    const tone = active === 0 ? "healthy" : active === 1 ? "focus" : active === 2 ? "warning" : "neutral";
    return {
      name,
      role:
        index < 4
          ? "operator agent"
          : index < 8
            ? "specialist developer"
            : "governed assistant",
      model: index % 3 === 0 ? "gpt-5.3-codex" : index % 3 === 1 ? "qwen3.5:9b" : "claude-sonnet-4",
      env: index % 2 === 0 ? "production" : "staging",
      status: active === 0 ? "Live" : active === 1 ? "Syncing" : active === 2 ? "Review" : "Standby",
      tone,
      lastSeen: active === 0 ? "heartbeat 9s" : relativeStamp(12 + index * 3 + tick),
      load: `${18 + ((index * 9 + tick * 2) % 64)}%`,
    };
  });

  const commandQueue = [
    { title: "Wake security", detail: "staging · operator request", tone: "focus" as Tone },
    { title: "Spawn research", detail: "development · new workflow lane", tone: "healthy" as Tone },
    { title: "Review jarv output", detail: "production · seal requested", tone: "warning" as Tone },
    { title: "Pause crawler", detail: "development · connector delay", tone: "warning" as Tone },
  ];

  return (
    <div className="flex min-h-0 flex-col gap-3 overflow-visible lg:h-full lg:overflow-hidden">
      <SectionIntroBar label="Agents" detail="Wake, inspect, and coordinate the operating fleet">
        <SectionPill label="56 total" tone="focus" />
        <SectionPill label="12 heartbeats" tone="healthy" />
      </SectionIntroBar>

      <div className="grid min-h-0 flex-1 grid-cols-1 gap-3 overflow-visible lg:grid-cols-[minmax(0,1.18fr)_minmax(320px,0.82fr)] lg:overflow-hidden">
        <SurfacePanel title="Agent Registry" meta="operator control">
          <div className="flex h-full min-h-0 flex-col gap-4">
            <div className="flex shrink-0 flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div className="flex flex-wrap items-center gap-2">
                <SectionPill label="Live" tone="healthy" />
                <SectionPill label="Sync config" tone="focus" />
                <SectionPill label="Needs review" tone="warning" />
              </div>
              <div className="rounded-[4px] border border-[#3b3a33] bg-[#151612] px-3 py-2 text-right">
                <div className="font-[family:var(--font-mono)] text-[11px] font-semibold uppercase tracking-[0.1em] text-[#ff8355]">
                  Write controls unavailable
                </div>
                <div className="mt-1 text-[11px] text-[#8d867a]">Sample registry only</div>
              </div>
            </div>
            <div className="min-h-0 flex-1 overflow-visible pe-0 lg:overflow-auto lg:overscroll-contain lg:pe-1">
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
                {agents.map((agent) => (
                  <AgentRegistryCard key={agent.name} card={agent} />
                ))}
              </div>
            </div>
          </div>
        </SurfacePanel>

        <div className="grid min-h-0 grid-cols-1 gap-3 overflow-visible lg:grid-rows-[minmax(0,0.72fr)_minmax(0,1fr)] lg:overflow-hidden">
          <SurfacePanel title="Fleet posture" meta="signal summary">
            <div className="grid h-full min-h-0 grid-rows-[repeat(4,minmax(0,1fr))] gap-3">
              <div className="rounded-[6px] border border-[#34342e] bg-[#11120f] p-3">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[#8d867a]">Agent capacity</div>
                <div className="mt-2 text-[28px] font-semibold tracking-[-0.04em] text-[#eee9dc]">56</div>
                <div className="mt-1 text-[12px] text-[#999284]">production + staging + development</div>
              </div>
              <div className="rounded-[6px] border border-[#34342e] bg-[#11120f] p-3">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[#8d867a]">Live heartbeats</div>
                <div className="mt-2 text-[28px] font-semibold tracking-[-0.04em] text-[#eee9dc]">{12 + (tick % 4)}</div>
                <div className="mt-1 text-[12px] text-[#999284]">agents reporting inside the watch window</div>
              </div>
              <div className="rounded-[6px] border border-[#34342e] bg-[#11120f] p-3">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[#8d867a]">Wake queue</div>
                <div className="mt-2 text-[28px] font-semibold tracking-[-0.04em] text-[#eee9dc]">{1 + (tick % 3)}</div>
                <div className="mt-1 text-[12px] text-[#999284]">pending spawn or sync actions</div>
              </div>
              <div className="rounded-[6px] border border-[#34342e] bg-[#11120f] p-3">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[#8d867a]">Assignment pressure</div>
                <div className="mt-2 text-[28px] font-semibold tracking-[-0.04em] text-[#eee9dc]">{38 + ((tick * 2) % 18)}%</div>
                <div className="mt-1 text-[12px] text-[#999284]">review lanes + orchestration backlog</div>
              </div>
            </div>
          </SurfacePanel>

          <SurfacePanel title="Command Queue" meta="operator actions">
            <RecordStack
              items={commandQueue.map((item, index) => ({
                ...item,
                meta: `${item.detail} · ${relativeStamp(4 + index * 9 + tick)}`,
              }))}
            />
          </SurfacePanel>
        </div>
      </div>
    </div>
  );
}

function DeploymentsSection({ tick }: { tick: number }) {
  const rows: DeploymentRow[] = [
    { agent: "Sales Ops Assistant", runtime: "OpenClaw", environment: "Production", version: "v1.4.2", region: "EU-West", health: "Healthy", tone: "healthy", rollout: relativeStamp(4 + (tick % 3)) },
    { agent: "Data Processor", runtime: "LangChain", environment: "Staging", version: "v1.6.1", region: "US-East", health: "Healthy", tone: "healthy", rollout: relativeStamp(11 + (tick % 5)) },
    { agent: "Autonomous Crawler", runtime: "n8n", environment: "Development", version: "v0.9.4", region: "EU-West", health: "Healthy", tone: "healthy", rollout: relativeStamp(23 + (tick % 7)) },
    { agent: "Research Automator", runtime: "OpenClaw", environment: "Production", version: "v2.0.4", region: "US-West", health: "Self-healing", tone: "focus", rollout: relativeStamp(29 + (tick % 6)) },
    { agent: "Billing Resolver", runtime: "LangChain", environment: "Staging", version: "v1.2.7", region: "US-East", health: "Healthy", tone: "healthy", rollout: relativeStamp(41 + (tick % 8)) },
    { agent: "Support Router", runtime: "OpenClaw", environment: "Production", version: "v1.9.0", region: "AP-South", health: "Policy Watch", tone: "warning", rollout: relativeStamp(52 + (tick % 10)) },
  ];

  const rolloutLane = [
    { title: "Promote v1.4.3", detail: "Sales Ops Assistant · production", tone: "focus" as Tone },
    { title: "Rollback window open", detail: "Support Router · ap-south", tone: "warning" as Tone },
    { title: "Warm canary complete", detail: "Research Automator · us-west", tone: "healthy" as Tone },
    { title: "Replica drift detected", detail: "Data Processor · staging", tone: "warning" as Tone },
  ];

  return (
    <div className="flex min-h-0 flex-col gap-3 overflow-visible lg:h-full lg:overflow-hidden">
      <SectionIntroBar label="Deployments" detail="Release inventory, regions, rollback windows, and runtime health">
        <SectionPill label="24 active versions" tone="focus" />
        <SectionPill label="2 watch items" tone="warning" />
      </SectionIntroBar>

      <div className="grid min-h-0 flex-1 grid-cols-1 gap-3 overflow-visible lg:grid-cols-[minmax(0,1.2fr)_minmax(320px,0.8fr)] lg:overflow-hidden">
        <SurfacePanel title="Active Deployments" meta="release inventory" bodyClassName="p-0 lg:p-0">
          <DeploymentsTable rows={rows} />
        </SurfacePanel>

        <div className="grid min-h-0 grid-cols-1 gap-3 overflow-visible lg:grid-rows-[minmax(0,0.88fr)_minmax(0,1fr)] lg:overflow-hidden">
          <SurfacePanel title="Rollout Lane" meta="current decisions">
            <RecordStack
              items={rolloutLane.map((item, index) => ({
                ...item,
                meta: `${item.detail} · ${relativeStamp(3 + index * 8 + tick)}`,
              }))}
            />
          </SurfacePanel>
          <SurfacePanel title="Regional Capacity" meta="per region">
            <div className="flex h-full min-h-0 flex-col gap-4 overflow-auto overscroll-contain">
              <ProgressRow label="EU-West" value={74 + ((tick * 2) % 8)} tone="healthy" />
              <ProgressRow label="US-East" value={66 + ((tick * 3) % 10)} tone="focus" />
              <ProgressRow label="US-West" value={58 + ((tick * 2) % 12)} tone="focus" />
              <ProgressRow label="AP-South" value={81 + (tick % 7)} tone="warning" />
              <div className="rounded-[6px] border border-[#34342e] bg-[#11120f] p-3">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[#8d867a]">Version pressure</div>
                <div className="mt-2 text-sm leading-6 text-[#aaa397]">
                  Three rollout candidates are waiting on policy seal before promotion into the production lane.
                </div>
              </div>
            </div>
          </SurfacePanel>
        </div>
      </div>
    </div>
  );
}

function RunsSection({ tick }: { tick: number }) {
  const runItems = [
    { title: "sales_ops:lead_sync", detail: "production · OpenClaw", tone: "healthy" as Tone },
    { title: "crawler:enrichment_batch", detail: "development · n8n", tone: "warning" as Tone },
    { title: "research:pricing_eval", detail: "staging · OpenClaw", tone: "focus" as Tone },
    { title: "billing:reconcile", detail: "production · LangChain", tone: "healthy" as Tone },
    { title: "support:ticket_triage", detail: "production · OpenClaw", tone: "focus" as Tone },
  ];

  const recoveryItems = [
    { title: "Retry failed batch", detail: "Autonomous Crawler · 3 items", tone: "warning" as Tone },
    { title: "Seal pending export", detail: "Research Automator · approval required", tone: "critical" as Tone },
    { title: "Resume delivery lane", detail: "Stripe outbound queue", tone: "healthy" as Tone },
    { title: "Re-issue tool token", detail: "Support Router · access denied", tone: "warning" as Tone },
  ];

  const queuePoints = Array.from({ length: 16 }, (_, index) =>
    Number((22 + index * 1.4 + Math.sin((index + tick) / 2.1) * 3).toFixed(2)),
  );

  return (
    <div className="flex min-h-0 flex-col gap-3 overflow-visible lg:h-full lg:overflow-hidden">
      <SectionIntroBar label="Runs" detail="Execution throughput, failure triage, and recovery decisions">
        <SectionPill label="187 / 24h" tone="focus" />
        <SectionPill label="94.7% success" tone="healthy" />
      </SectionIntroBar>

      <div className="grid min-h-0 flex-1 grid-cols-1 gap-3 overflow-visible lg:grid-cols-[minmax(0,1.1fr)_minmax(320px,0.9fr)] lg:overflow-hidden">
        <div className="grid min-h-0 grid-cols-1 gap-3 overflow-visible lg:grid-rows-[minmax(0,1fr)_minmax(0,0.95fr)] lg:overflow-hidden">
          <SurfacePanel title="Active Run Board" meta="current load">
            <RecordStack
              items={runItems.map((item, index) => ({
                ...item,
                meta: `${item.detail} · ${relativeStamp(2 + index * 5 + tick)}`,
              }))}
            />
          </SurfacePanel>
          <SurfacePanel title="Recovery Queue" meta="operator attention">
            <RecordStack
              items={recoveryItems.map((item, index) => ({
                ...item,
                meta: `${item.detail} · ${relativeStamp(6 + index * 7 + tick)}`,
              }))}
            />
          </SurfacePanel>
        </div>

        <div className="grid min-h-0 grid-cols-1 gap-3 overflow-visible lg:grid-rows-[minmax(0,0.86fr)_minmax(0,1fr)] lg:overflow-hidden">
          <SurfacePanel title="Queue Pressure" meta="load trend">
            <div className="flex h-full min-h-0 flex-col gap-4">
              <div className="grid grid-cols-2 gap-3">
                <MetricCard metric={{ label: "Live", value: `${86 + (tick % 9)}`, meta: "active runs", tone: "healthy" }} />
                <MetricCard metric={{ label: "Pressure", value: `${38 + ((tick * 2) % 18)}%`, meta: "queue", tone: "warning" }} />
              </div>
              <div className="min-h-0 flex-1 rounded-[6px] border border-[#34342e] bg-[#11120f] p-3">
                <div className="flex items-center justify-between">
                  <div>
                    <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[#8d867a]">Run load</div>
                    <div className="mt-1 text-sm text-[#aaa397]">steady with one recovery spike</div>
                  </div>
                  <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[#8d867a]">last 6h</div>
                </div>
                <div className="mt-3 h-[132px]">
                  <Sparkline points={queuePoints} strokeClassName="stroke-amber-300" fillClassName="fill-amber-400/10" />
                </div>
              </div>
            </div>
          </SurfacePanel>
          <SurfacePanel title="Seal Decisions" meta="governance lane">
            <RecordStack
              items={[
                {
                  title: "Human approval required",
                  detail: "Privileged export requested by research:pricing_eval",
                  meta: `Production · ${relativeStamp(9 + tick)}`,
                  tone: "critical",
                },
                {
                  title: "Guardrail simulate hit",
                  detail: "Tool use matched candidate deny rule but remained inside simulate mode.",
                  meta: `Staging · ${relativeStamp(21 + tick)}`,
                  tone: "focus",
                },
                {
                  title: "Recovery allowed",
                  detail: "Retry budget still inside envelope for crawler:enrichment_batch.",
                  meta: `Development · ${relativeStamp(33 + tick)}`,
                  tone: "healthy",
                },
              ]}
            />
          </SurfacePanel>
        </div>
      </div>
    </div>
  );
}

function EnvironmentsSection({ tick }: { tick: number }) {
  const cards = [
    {
      name: "Production",
      detail: "Dedicated environment, private egress, enforced guardrails",
      tone: "healthy" as Tone,
      stats: ["12 deployments", "86 live runs", "99.96% ready"],
    },
    {
      name: "Staging",
      detail: "Warm promotion lane, candidate policies, replay visibility",
      tone: "focus" as Tone,
      stats: ["7 deployments", "19 live runs", "1 watch item"],
    },
    {
      name: "Development",
      detail: "Sandboxed tools, ephemeral keys, shared gateway contracts",
      tone: "warning" as Tone,
      stats: ["5 sandboxes", "14 live runs", "1 delayed connector"],
    },
  ];

  return (
    <div className="flex min-h-0 flex-col gap-3 overflow-visible lg:h-full lg:overflow-hidden">
      <SectionIntroBar
        label="Environments"
        detail="Isolation boundaries, readiness, network stance, and policy posture"
      />

      <div className="grid min-h-0 flex-1 grid-cols-1 gap-3 overflow-visible lg:grid-rows-[168px_minmax(0,1fr)] lg:overflow-hidden">
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
          {cards.map((card) => (
            <div key={card.name} className="flex flex-col justify-between rounded-[6px] border border-[#34342e] bg-[#0c0d0b] p-4">
              <div>
                <div className="flex items-center justify-between gap-3">
                  <div className="text-[22px] font-semibold tracking-[-0.04em] text-[#eee9dc]">{card.name}</div>
                  <StatusBadge label={card.tone === "warning" ? "Watch" : card.tone === "focus" ? "Active" : "OK"} tone={card.tone} />
                </div>
                <div className="mt-2 text-sm leading-6 text-[#aaa397]">{card.detail}</div>
              </div>
              <div className="mt-4 grid grid-cols-1 gap-3 text-[11px] font-semibold uppercase tracking-[0.16em] text-[#8d867a] sm:grid-cols-3">
                {card.stats.map((stat) => (
                  <div key={stat} className="rounded-[4px] border border-[#34342e] bg-[#11120f] px-3 py-2 text-center">
                    {stat}
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>

        <div className="grid min-h-0 grid-cols-1 gap-3 overflow-visible lg:grid-cols-[minmax(0,1.1fr)_minmax(320px,0.9fr)] lg:overflow-hidden">
          <SurfacePanel title="Environment Matrix" meta="bounded posture">
            <EnvironmentMatrix
              rows={[
                {
                  label: "Deployments",
                  meta: "versions",
                  cells: [
                    { value: "12 active", detail: "3 rollout lanes", stamp: relativeStamp(2 + tick), tone: "healthy", badge: "OK" },
                    { value: "7 active", detail: "2 candidates", stamp: relativeStamp(7 + tick), tone: "focus", badge: "Active" },
                    { value: "5 sandboxes", detail: "1 debug lane", stamp: relativeStamp(5 + tick), tone: "neutral", badge: "Ready" },
                  ],
                },
                {
                  label: "Policy",
                  meta: "guardrails",
                  cells: [
                    { value: "enforced", detail: "1 block in window", stamp: relativeStamp(11 + tick), tone: "warning", badge: "Watch" },
                    { value: "simulate", detail: "candidate rules", stamp: relativeStamp(16 + tick), tone: "focus", badge: "Active" },
                    { value: "learning", detail: "signal capture", stamp: relativeStamp(9 + tick), tone: "neutral", badge: "Ready" },
                  ],
                },
                {
                  label: "Keys",
                  meta: "secrets",
                  cells: [
                    { value: "14 healthy", detail: "rotation inside SLA", stamp: relativeStamp(18 + tick), tone: "healthy", badge: "OK" },
                    { value: "6 rotated", detail: "staging current", stamp: relativeStamp(22 + tick), tone: "healthy", badge: "OK" },
                    { value: "4 ephemeral", detail: "sandbox scoped", stamp: relativeStamp(7 + tick), tone: "focus", badge: "Active" },
                  ],
                },
                {
                  label: "Health",
                  meta: "readiness",
                  cells: [
                    { value: "99.96%", detail: "ready / healthy", stamp: relativeStamp(1), tone: "healthy", badge: "OK" },
                    { value: "ready", detail: "fleet responsive", stamp: relativeStamp(2), tone: "healthy", badge: "OK" },
                    { value: "warming", detail: "one sandbox boot", stamp: relativeStamp(4), tone: "warning", badge: "Watch" },
                  ],
                },
                {
                  label: "Network",
                  meta: "egress",
                  cells: [
                    { value: "private mesh", detail: "egress pinned", stamp: relativeStamp(3), tone: "healthy", badge: "OK" },
                    { value: "relay armed", detail: "failover ready", stamp: relativeStamp(6), tone: "focus", badge: "Active" },
                    { value: "shared gateway", detail: "fanout enabled", stamp: relativeStamp(5), tone: "neutral", badge: "Ready" },
                  ],
                },
                {
                  label: "Ownership",
                  meta: "operators",
                  cells: [
                    { value: "Revenue Infra", detail: "production owner", stamp: relativeStamp(31 + tick), tone: "focus", badge: "Current" },
                    { value: "Platform", detail: "staging owner", stamp: relativeStamp(43 + tick), tone: "neutral", badge: "Current" },
                    { value: "Developers", detail: "sandbox owner", stamp: relativeStamp(55 + tick), tone: "neutral", badge: "Current" },
                  ],
                },
              ]}
            />
          </SurfacePanel>

          <SurfacePanel title="Readiness Signals" meta="env health">
            <div className="flex h-full min-h-0 flex-col gap-4 overflow-auto overscroll-contain">
              <ProgressRow label="Production readiness" value={96 + (tick % 3)} tone="healthy" />
              <ProgressRow label="Staging readiness" value={88 + (tick % 7)} tone="focus" />
              <ProgressRow label="Development readiness" value={74 + ((tick * 2) % 11)} tone="warning" />
              <div className="rounded-[6px] border border-[#34342e] bg-[#11120f] p-3">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[#8d867a]">Dedicated environments</div>
                <div className="mt-2 text-sm leading-6 text-[#aaa397]">
                  Production runs on its own isolated boundary. Staging stays warm for promotion, while development keeps sandboxed tool access and shared gateway defaults.
                </div>
              </div>
            </div>
          </SurfacePanel>
        </div>
      </div>
    </div>
  );
}

function AccessSection({ tick }: { tick: number }) {
  const keys = [
    { title: "platform-ops-prod", detail: "Production operator key · scoped", meta: `last used ${relativeStamp(4 + tick)}`, tone: "healthy" as Tone },
    { title: "stripe-delivery", detail: "Connector signing key · webhook lane", meta: `rotated ${relativeStamp(19 + tick)}`, tone: "focus" as Tone },
    { title: "hubspot-import", detail: "Integration key · sandbox", meta: `rotation due ${relativeStamp(43 + tick)}`, tone: "warning" as Tone },
    { title: "research-export", detail: "Privileged export key · approval required", meta: `blocked ${relativeStamp(11 + tick)}`, tone: "critical" as Tone },
  ];

  return (
    <div className="flex min-h-0 flex-col gap-3 overflow-visible lg:h-full lg:overflow-hidden">
      <SectionIntroBar label="Access" detail="Keys, roles, auth anomalies, and BYOK posture" />

      <div className="grid min-h-0 flex-1 grid-cols-1 gap-3 overflow-visible lg:grid-cols-[minmax(0,1.08fr)_minmax(320px,0.92fr)] lg:overflow-hidden">
        <SurfacePanel title="Credential Registry" meta="governed secrets">
          <RecordStack items={keys} />
        </SurfacePanel>

        <div className="grid min-h-0 grid-cols-1 gap-3 overflow-visible lg:grid-rows-[minmax(0,0.8fr)_minmax(0,1fr)] lg:overflow-hidden">
          <SurfacePanel title="Auth Anomalies" meta="watch lane">
            <RecordStack
              items={[
                {
                  title: "Repeated failed login",
                  detail: "Three attempts against platform-ops-prod from an untrusted location.",
                  meta: `Operator auth · ${relativeStamp(7 + tick)}`,
                  tone: "warning",
                },
                {
                  title: "Role expansion requested",
                  detail: "Tenant operator requested export permissions outside the default boundary.",
                  meta: `Role change · ${relativeStamp(28 + tick)}`,
                  tone: "critical",
                },
                {
                  title: "BYOK connector active",
                  detail: "Customer-owned model credentials currently serving production traffic.",
                  meta: `Model access · ${relativeStamp(15 + tick)}`,
                  tone: "focus",
                },
              ]}
            />
          </SurfacePanel>
          <SurfacePanel title="Policy Surface" meta="trust defaults">
            <div className="flex h-full min-h-0 flex-col gap-4 overflow-auto overscroll-contain">
              <ProgressRow label="Rotation compliance" value={91} tone="healthy" />
              <ProgressRow label="Least-privilege coverage" value={84} tone="focus" />
              <ProgressRow label="Approval debt" value={29} tone="warning" />
              <div className="rounded-[6px] border border-[#34342e] bg-[#11120f] p-3">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[#8d867a]">Role note</div>
                <div className="mt-2 text-sm leading-6 text-[#aaa397]">
                  Production export remains human-gated even when the caller owns the agent. That rule is deliberate.
                </div>
              </div>
            </div>
          </SurfacePanel>
        </div>
      </div>
    </div>
  );
}

function ConnectorsSection({ tick }: { tick: number }) {
  const connectors: ConnectorCard[] = [
    { name: "GitHub", detail: "release webhooks · commit metadata", status: "Healthy", tone: "healthy", stamp: relativeStamp(4 + tick) },
    { name: "Stripe", detail: "billing callbacks · outbound queue", status: "Healthy", tone: "healthy", stamp: relativeStamp(2 + tick) },
    { name: "Twilio", detail: "notifications · retry lane armed", status: tick % 4 === 0 ? "Retrying" : "Healthy", tone: tick % 4 === 0 ? "warning" : "focus", stamp: relativeStamp(9 + tick) },
    { name: "HubSpot", detail: "crm projection · owner sync", status: "Delayed", tone: "warning", stamp: relativeStamp(18 + tick) },
  ];

  return (
    <div className="flex min-h-0 flex-col gap-3 overflow-visible lg:h-full lg:overflow-hidden">
      <SectionIntroBar
        label="Connectors"
        detail="Webhook health, delivery retries, and connector contracts"
      />

      <div className="grid min-h-0 flex-1 grid-cols-1 gap-3 overflow-visible lg:grid-cols-[minmax(0,1fr)_minmax(320px,0.9fr)] lg:overflow-hidden">
        <SurfacePanel title="Connector Grid" meta="delivery posture">
          <ConnectorGrid connectors={connectors} />
        </SurfacePanel>
        <div className="grid min-h-0 grid-cols-1 gap-3 overflow-visible lg:grid-rows-[minmax(0,1fr)_minmax(0,0.92fr)] lg:overflow-hidden">
          <SurfacePanel title="Delivery Exceptions" meta="retry lane">
            <RecordStack
              items={[
                {
                  title: "HubSpot sync lag detected",
                  detail: "CRM projection trail is 94 seconds behind the rest of the fanout graph.",
                  meta: `connector delay · ${relativeStamp(11 + tick)}`,
                  tone: "warning",
                },
                {
                  title: "Twilio delivery retry",
                  detail: "Outbound notification retried after temporary upstream 429.",
                  meta: `webhook retry · ${relativeStamp(17 + tick)}`,
                  tone: "focus",
                },
                {
                  title: "Stripe lane recovered",
                  detail: "Previous backlog drained and no messages remain in the dead-letter queue.",
                  meta: `delivery recovery · ${relativeStamp(29 + tick)}`,
                  tone: "healthy",
                },
              ]}
            />
          </SurfacePanel>
          <SurfacePanel title="Contracts" meta="shape of integration">
            <div className="flex h-full min-h-0 flex-col gap-3 overflow-auto overscroll-contain">
              <div className="rounded-[6px] border border-[#34342e] bg-[#11120f] p-3 text-sm text-[#aaa397]">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[#8d867a]">Webhook namespaces</div>
                <div className="mt-2">production / staging / development each maintain isolated delivery credentials and retry counters.</div>
              </div>
              <ProgressRow label="Signed deliveries" value={97} tone="healthy" />
              <ProgressRow label="Retry saturation" value={24} tone="warning" />
            </div>
          </SurfacePanel>
        </div>
      </div>
    </div>
  );
}

function AuditSection({ tick }: { tick: number }) {
  const audit: AuditItem[] = [
    { title: "Rotate API key", resource: "External operator credential", actor: "Creator", role: "operator", stamp: relativeStamp(8 + tick) },
    { title: "Deployment promoted", resource: "Sales Ops Assistant v1.4.x", actor: "Release Bot", role: "automation", stamp: relativeStamp(16 + tick) },
    { title: "Webhook updated", resource: "Stripe outbound delivery", actor: "Integrator", role: "platform", stamp: relativeStamp(26 + tick) },
    { title: "Access granted", resource: "Tenant operator role", actor: "Platform Admin", role: "admin", stamp: relativeStamp(44 + tick) },
    { title: "Policy pack attached", resource: "Production environment", actor: "Security", role: "governance", stamp: relativeStamp(51 + tick) },
    { title: "Ownership changed", resource: "Research Automator", actor: "Platform Admin", role: "admin", stamp: relativeStamp(67 + tick) },
  ];

  return (
    <div className="flex min-h-0 flex-col gap-3 overflow-visible lg:h-full lg:overflow-hidden">
      <SectionIntroBar
        label="Audit"
        detail="Structured record of operator and automation changes"
      />

      <div className="grid min-h-0 flex-1 grid-cols-1 gap-3 overflow-visible lg:grid-cols-[minmax(0,1.08fr)_minmax(320px,0.92fr)] lg:overflow-hidden">
        <SurfacePanel title="Audit Timeline" meta="governed record">
          <div className="flex h-full min-h-0 flex-col overflow-auto overscroll-contain pe-1">
            {audit.map((item) => (
              <div
                key={`${item.title}-${item.stamp}`}
                className="grid min-h-[78px] grid-cols-1 gap-2 border-b border-[#2b2b26] py-3 last:border-b-0 sm:grid-cols-[minmax(0,1fr)_72px] sm:gap-3"
              >
                <div className="min-w-0">
                  <div className="text-[14px] font-semibold text-[#eee9dc]">{item.title}</div>
                  <div className="mt-1 text-[13px] text-[#aaa397]">{item.resource}</div>
                  <div className="mt-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-[#8d867a]">
                    {item.role} · {item.actor}
                  </div>
                </div>
                <div className="text-right text-[11px] font-semibold uppercase tracking-[0.16em] text-[#8d867a]">
                  {item.stamp}
                </div>
              </div>
            ))}
          </div>
        </SurfacePanel>
        <div className="grid min-h-0 grid-cols-1 gap-3 overflow-visible lg:grid-rows-[minmax(0,0.9fr)_minmax(0,0.9fr)] lg:overflow-hidden">
          <SurfacePanel title="Ownership Changes" meta="recent transfers">
            <RecordStack
              items={[
                {
                  title: "Sales Ops Assistant → Revenue Infra",
                  detail: "ownership updated and production deployment contract transferred cleanly.",
                  meta: `transfer · ${relativeStamp(18 + tick)}`,
                  tone: "focus",
                },
                {
                  title: "Research Automator → Platform",
                  detail: "staging control reassigned before policy-pack upgrade.",
                  meta: `transfer · ${relativeStamp(41 + tick)}`,
                  tone: "neutral",
                },
              ]}
            />
          </SurfacePanel>
          <SurfacePanel title="Policy Record" meta="changed contracts">
            <RecordStack
              items={[
                {
                  title: "Production deny rule attached",
                  detail: "new tool egress deny rule added for billing export lane.",
                  meta: `policy change · ${relativeStamp(9 + tick)}`,
                  tone: "warning",
                },
                {
                  title: "Approval window shortened",
                  detail: "seal timeout reduced from 30m to 15m for privileged runs.",
                  meta: `policy change · ${relativeStamp(27 + tick)}`,
                  tone: "focus",
                },
              ]}
            />
          </SurfacePanel>
        </div>
      </div>
    </div>
  );
}

function UsageSection({ tick }: { tick: number }) {
  const points = Array.from({ length: 20 }, (_, index) =>
    Number((18 + index * 2 + Math.sin((index + tick) / 2.2) * 4.4 + (index > 13 ? (index - 13) * 1.2 : 0)).toFixed(2)),
  );

  return (
    <div className="flex min-h-0 flex-col gap-3 overflow-visible lg:h-full lg:overflow-hidden">
      <SectionIntroBar
        label="Usage"
        detail="Separate infra overhead from model spend and queue pressure"
      />

      <div className="grid min-h-0 flex-1 grid-cols-1 gap-3 overflow-visible lg:grid-cols-[minmax(0,1.06fr)_minmax(320px,0.94fr)] lg:overflow-hidden">
        <SurfacePanel title="Spend Split" meta="today">
          <div className="flex h-full min-h-0 flex-col gap-4">
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
              <MetricCard metric={{ label: "Infra", value: formatCurrency(1730 + tick * 26), meta: "control plane", tone: "focus" }} />
              <MetricCard metric={{ label: "Model", value: formatCurrency(970 + tick * 18), meta: "BYOK + shared", tone: "warning" }} />
              <MetricCard metric={{ label: "Headroom", value: "57%", meta: "daily budget", tone: "healthy" }} />
            </div>
            <div className="min-h-0 flex-1 rounded-[6px] border border-[#34342e] bg-[#11120f] p-3">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[#8d867a]">Usage trend</div>
                  <div className="mt-1 text-sm text-[#aaa397]">infra spend rising slower than model spend</div>
                </div>
                <div className="text-right text-[11px] font-semibold uppercase tracking-[0.16em] text-[#8d867a]">last 12h</div>
              </div>
              <div className="mt-4 h-[184px]">
                <Sparkline points={points} />
              </div>
            </div>
          </div>
        </SurfacePanel>
        <div className="grid min-h-0 grid-cols-1 gap-3 overflow-visible lg:grid-rows-[minmax(0,0.86fr)_minmax(0,1fr)] lg:overflow-hidden">
          <SurfacePanel title="Budget Posture" meta="thresholds">
            <div className="flex h-full min-h-0 flex-col gap-4 overflow-auto overscroll-contain">
              <ProgressRow label="Daily infra budget" value={43} tone="healthy" />
              <ProgressRow label="Daily model budget" value={78} tone="warning" />
              <ProgressRow label="Queue saturation" value={38 + ((tick * 3) % 21)} tone="focus" />
              <ProgressRow label="Run retry budget" value={24} tone="healthy" />
            </div>
          </SurfacePanel>
          <SurfacePanel title="Capacity Notes" meta="operating pressure">
            <RecordStack
              items={[
                {
                  title: "Model spend climbing faster than infra",
                  detail: "Customer BYOK lanes are absorbing most of the day-over-day increase.",
                  meta: `usage note · ${relativeStamp(11 + tick)}`,
                  tone: "warning",
                },
                {
                  title: "Queue pressure stable",
                  detail: "No evidence of runaway orchestration despite the latest deployment promotion.",
                  meta: `capacity note · ${relativeStamp(27 + tick)}`,
                  tone: "healthy",
                },
              ]}
            />
          </SurfacePanel>
        </div>
      </div>
    </div>
  );
}

function SettingsSection({ tick }: { tick: number }) {
  return (
    <div className="flex min-h-0 flex-col gap-3 overflow-visible lg:h-full lg:overflow-hidden">
      <SectionIntroBar
        label="Settings"
        detail="Control-plane defaults, policy packs, and runtime knobs"
      />

      <div className="grid min-h-0 flex-1 grid-cols-1 gap-3 overflow-visible lg:grid-cols-2 lg:overflow-hidden">
        <SurfacePanel title="Policy Packs" meta="runtime defaults">
          <RecordStack
            items={[
              {
                title: "Production guardrails",
                detail: "deny external side effects without approval, require scoped credentials, retain audit.",
                meta: `enforced · ${relativeStamp(31 + tick)}`,
                tone: "healthy",
              },
              {
                title: "Staging simulate rules",
                detail: "capture policy hit-rate before promotion into enforced mode.",
                meta: `simulate · ${relativeStamp(22 + tick)}`,
                tone: "focus",
              },
            ]}
          />
        </SurfacePanel>
        <SurfacePanel title="Environment Defaults" meta="topology">
          <div className="flex h-full min-h-0 flex-col gap-4 overflow-auto overscroll-contain">
            <ProgressRow label="Dedicated environment coverage" value={41} tone="focus" />
            <ProgressRow label="Webhook isolation" value={92} tone="healthy" />
            <ProgressRow label="Manual approval fallback" value={100} tone="healthy" />
            <div className="rounded-[6px] border border-[#34342e] bg-[#11120f] p-3">
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[#8d867a]">Operator note</div>
              <div className="mt-2 text-sm leading-6 text-[#aaa397]">
                Production promotion requires scoped credentials, readiness probes, and an open rollback window before traffic can shift.
              </div>
            </div>
          </div>
        </SurfacePanel>
        <SurfacePanel title="Notification Rules" meta="signal routing">
          <RecordStack
            items={[
              {
                title: "Critical incidents → on-call",
                detail: "policy blocks, production outage, or auth anomaly with severity red.",
                meta: `routing · ${relativeStamp(17 + tick)}`,
                tone: "critical",
              },
              {
                title: "Warnings → operator inbox",
                detail: "connector lag, retry pressure, budget threshold, and warming replicas.",
                meta: `routing · ${relativeStamp(26 + tick)}`,
                tone: "warning",
              },
            ]}
          />
        </SurfacePanel>
        <SurfacePanel title="Runtime Contracts" meta="operator defaults">
          <div className="flex h-full min-h-0 flex-col gap-4 overflow-auto overscroll-contain">
            <div className="rounded-[6px] border border-[#34342e] bg-[#11120f] p-4">
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[#8d867a]">Deployment boundary</div>
              <div className="mt-2 text-sm leading-6 text-[#aaa397]">
                Production requires signed releases, bounded egress, and healthy probes before promotion.
              </div>
            </div>
            <div className="rounded-[6px] border border-[#34342e] bg-[#11120f] p-4">
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[#8d867a]">Connector posture</div>
              <div className="mt-2 text-sm leading-6 text-[#aaa397]">
                Signed webhook delivery, retry isolation, and audit retention stay enabled across every environment.
              </div>
            </div>
          </div>
        </SurfacePanel>
      </div>
    </div>
  );
}

export function PlaceholderSection({ section, tick }: { section: DemoSection; tick: number }) {
  if (section === "access") {
    return <AccessSection tick={tick} />;
  }

  if (section === "connectors") {
    return <ConnectorsSection tick={tick} />;
  }

  if (section === "audit") {
    return <AuditSection tick={tick} />;
  }

  if (section === "usage") {
    return <UsageSection tick={tick} />;
  }

  if (section === "settings") {
    return <SettingsSection tick={tick} />;
  }

  return null;
}

export { OverviewSection, AgentsSection, DeploymentsSection, RunsSection, EnvironmentsSection };
