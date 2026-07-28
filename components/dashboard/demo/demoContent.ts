import type { LucideIcon } from "lucide-react";
import {
  Bot,
  Globe,
  KeyRound,
  Layers3,
  Play,
  Settings2,
  ShieldCheck,
  Wallet,
  Webhook,
  Workflow,
} from "lucide-react";

import {
  getDemoSectionHref,
  type DemoSection,
} from "@/components/dashboard/demo/demoSections";

export type Tone = "healthy" | "warning" | "critical" | "focus" | "neutral";

export type DemoNavItem = {
  key: DemoSection;
  label: string;
  href: string;
  icon: LucideIcon;
};

export type DemoHeroStat = {
  label: string;
  value: string;
  detail: string;
};

export type DemoSectionMeta = {
  eyebrow: string;
  title: string;
  detail: string;
  chips: string[];
  heroStats: DemoHeroStat[];
  command: string;
  narrative: string[];
};

export type Metric = {
  label: string;
  value: string;
  meta: string;
  tone?: Tone;
};

export type SignalItem = {
  title: string;
  detail: string;
  tone: Tone;
  stamp: string;
};

export type AuditItem = {
  title: string;
  resource: string;
  actor: string;
  role: string;
  stamp: string;
};

export type MatrixCell = {
  value: string;
  detail: string;
  stamp: string;
  tone: Tone;
  badge: string;
};

export type MatrixRow = {
  label: string;
  meta: string;
  cells: MatrixCell[];
};

export type DeploymentRow = {
  agent: string;
  runtime: string;
  environment: string;
  version: string;
  region: string;
  health: string;
  tone: Tone;
  rollout: string;
};

export type AgentCard = {
  name: string;
  role: string;
  model: string;
  env: string;
  status: string;
  tone: Tone;
  lastSeen: string;
  load: string;
};

export type ConnectorCard = {
  name: string;
  detail: string;
  status: string;
  tone: Tone;
  stamp: string;
};

export type QuickAction = {
  label: string;
  detail: string;
};

export const NAV_ITEMS: DemoNavItem[] = [
  { key: "overview", label: "Overview", href: getDemoSectionHref("overview"), icon: ShieldCheck },
  { key: "agents", label: "Agents", href: getDemoSectionHref("agents"), icon: Bot },
  { key: "deployments", label: "Deployments", href: getDemoSectionHref("deployments"), icon: Layers3 },
  { key: "runs", label: "Runs", href: getDemoSectionHref("runs"), icon: Play },
  { key: "environments", label: "Environments", href: getDemoSectionHref("environments"), icon: Globe },
  { key: "access", label: "Access", href: getDemoSectionHref("access"), icon: KeyRound },
  { key: "connectors", label: "Connectors", href: getDemoSectionHref("connectors"), icon: Webhook },
  { key: "audit", label: "Audit", href: getDemoSectionHref("audit"), icon: Workflow },
  { key: "usage", label: "Usage", href: getDemoSectionHref("usage"), icon: Wallet },
  { key: "settings", label: "Settings", href: getDemoSectionHref("settings"), icon: Settings2 },
];

export const SECTION_META: Record<DemoSection, DemoSectionMeta> = {
  overview: {
    eyebrow: "Control Plane",
    title: "Mission briefing for governed agent infrastructure",
    detail: "Lead with posture, risk, and recovery so the demo immediately reads like an operator-grade surface rather than a generic dashboard.",
    chips: ["Production narrative", "Governed actions", "BYOK aware"],
    heroStats: [
      { label: "Governed lanes", value: "03", detail: "prod, staging, development" },
      { label: "Live operator score", value: "99.2%", detail: "control plane confidence" },
      { label: "Recovery budget", value: "17s", detail: "median self-heal window" },
    ],
    command: "Walk the audience through posture first, then move into the operating lanes that prove actionability.",
    narrative: [
      "Open with the environment matrix because it frames risk, ownership, and readiness in one read.",
      "Use live signals to show the surface is tuned for operating decisions, not vanity analytics.",
      "Point out the split between infra cost, model spend, and governance so the product feels credible.",
    ],
  },
  agents: {
    eyebrow: "Agent Registry",
    title: "A fleet board that feels owned, staffed, and alive",
    detail: "Show the operating fleet as named assets with clear role, pressure, sync state, and command backlog.",
    chips: ["56 agents", "12 heartbeats", "4 approvals"],
    heroStats: [
      { label: "Fleet coverage", value: "56", detail: "named operating agents" },
      { label: "Wake queue", value: "04", detail: "pending assignments" },
      { label: "Command debt", value: "38%", detail: "review + orchestration pressure" },
    ],
    command: "Tell the story of ownership: who is live, who is syncing, and who still needs operator judgment.",
    narrative: [
      "Use the registry to make the fleet feel like a staffed system, not just rows of metadata.",
      "Draw attention to load and last-seen signals to reinforce operational trust.",
      "Close on the command queue so the audience sees the next action, not just current state.",
    ],
  },
  deployments: {
    eyebrow: "Rollout Surface",
    title: "Release posture with real rollout tension and rollback confidence",
    detail: "The demo should feel like operators are making shipping decisions here, with regional capacity and watch items in sight.",
    chips: ["24 versions", "3 rollout lanes", "2 watch items"],
    heroStats: [
      { label: "Rollout lanes", value: "03", detail: "promotion windows active" },
      { label: "Rollback cover", value: "2.4m", detail: "average rollback window" },
      { label: "Regional load", value: "81%", detail: "ap-south at highest pressure" },
    ],
    command: "Frame deployments as a release-control story: promotion, rollback, region pressure, and policy watch all in one lane.",
    narrative: [
      "Lead with the release table so the audience sees the breadth of active runtime posture.",
      "Use the rollout lane to call out decisions still in flight.",
      "Finish with regional capacity to prove the demo understands operational consequences, not just versions.",
    ],
  },
  runs: {
    eyebrow: "Run Control",
    title: "Execution pressure, failed work, and seal decisions in one lane",
    detail: "This section should feel like the place an operator goes when throughput, failure, and approval debt collide.",
    chips: ["187 runs", "94.7% success", "7 recoveries"],
    heroStats: [
      { label: "Live queue", value: "86", detail: "current active runs" },
      { label: "Failure lane", value: "04", detail: "operator interventions open" },
      { label: "Seal debt", value: "02", detail: "approval gates waiting" },
    ],
    command: "Explain that this surface keeps queue pressure, recovery work, and privileged decisions visible together.",
    narrative: [
      "Start with throughput and recovery because that is where demos usually feel most real.",
      "Use queue pressure to give the section motion and operating context.",
      "Close on seal decisions so governance never feels disconnected from execution.",
    ],
  },
  environments: {
    eyebrow: "Environment Posture",
    title: "Bounded systems, not three tabs pretending to be environments",
    detail: "Production, staging, and development should read as materially different operating conditions with their own rules and readiness.",
    chips: ["Prod isolated", "Staging warm", "Dev sandboxed"],
    heroStats: [
      { label: "Dedicated zones", value: "03", detail: "bounded operating envelopes" },
      { label: "Readiness spread", value: "74-98%", detail: "across current environments" },
      { label: "Shared gateways", value: "01", detail: "development-only default" },
    ],
    command: "Use this tab to prove the product understands isolation, ownership, and readiness as separate ideas.",
    narrative: [
      "Show that production is governed differently, not just labeled differently.",
      "Use the matrix to compare policy, keys, and network posture side by side.",
      "Keep the environment cards narrative-heavy so the demo lands quickly for non-operators too.",
    ],
  },
  access: {
    eyebrow: "Access Surface",
    title: "Credential lifecycle with anomalies, approvals, and BYOK posture",
    detail: "Make trust boundaries legible: which keys are healthy, which requests look wrong, and where human approval still matters.",
    chips: ["14 keys", "2 BYOK tenants", "1 watch item"],
    heroStats: [
      { label: "Healthy keys", value: "14", detail: "governed credentials live" },
      { label: "Open anomalies", value: "03", detail: "watch list events" },
      { label: "Rotation cover", value: "91%", detail: "policy compliance" },
    ],
    command: "Anchor the conversation on trust boundaries, not just key counts.",
    narrative: [
      "The registry proves there is a real ledger, not a fake access wall.",
      "Anomalies and policy posture make the section feel active and accountable.",
      "Keep the BYOK note visible so enterprise buyers see their model ownership reflected.",
    ],
  },
  connectors: {
    eyebrow: "Connector Plane",
    title: "Delivery health, retry posture, and contract ownership",
    detail: "This should feel like a real integration control room, with queue stress, retry history, and contract isolation visible at a glance.",
    chips: ["12 connectors", "2 retries", "1 delayed lane"],
    heroStats: [
      { label: "Active contracts", value: "12", detail: "signed delivery surfaces" },
      { label: "Retry pressure", value: "24%", detail: "current exception load" },
      { label: "Dead letters", value: "00", detail: "recovered backlog" },
    ],
    command: "Use connectors to show operational detail beyond core runtime control.",
    narrative: [
      "Start with the connector grid so the audience sees breadth immediately.",
      "Then move into exceptions to prove the product handles ugly real-world delivery cases.",
      "Finish on contracts so the integrations feel governed instead of bolted on.",
    ],
  },
  audit: {
    eyebrow: "Governance Record",
    title: "A reviewable timeline of who changed what and why",
    detail: "The audit tab should read like evidence: attributable actions, ownership shifts, and policy changes that survive scrutiny.",
    chips: ["73 events", "4 transfers", "0 missing actors"],
    heroStats: [
      { label: "Timeline depth", value: "73", detail: "structured events in view" },
      { label: "Ownership shifts", value: "04", detail: "recent control transfers" },
      { label: "Missing actors", value: "00", detail: "every record attributed" },
    ],
    command: "This is where you prove the control plane leaves receipts.",
    narrative: [
      "Use the timeline to show that actions are attributable, not just logged.",
      "Ownership changes give the section human stakes and organizational realism.",
      "Policy records make governance feel operational, not ceremonial.",
    ],
  },
  usage: {
    eyebrow: "Usage Split",
    title: "Spend posture with infra, model, and queue pressure separated cleanly",
    detail: "The demo should make budget and capacity feel legible, with enough narrative to explain what is climbing and why.",
    chips: ["$1.7k infra", "$970 model", "57% headroom"],
    heroStats: [
      { label: "Infra envelope", value: "$1.7k", detail: "control plane overhead today" },
      { label: "Model envelope", value: "$970", detail: "BYOK + shared spend" },
      { label: "Headroom", value: "57%", detail: "remaining daily capacity" },
    ],
    command: "Use usage to show discipline: not just how much, but what kind of spend is growing.",
    narrative: [
      "Keep infra and model cost visually distinct so the product feels mature.",
      "Use the trend chart as atmospheric proof of ongoing runtime activity.",
      "The budget posture panel should give operators a decision, not just a number.",
    ],
  },
  settings: {
    eyebrow: "Control Settings",
    title: "Defaults, policy packs, and runtime contracts that shape the whole surface",
    detail: "This tab should feel like the command center behind the command center: the rules, routes, and defaults that keep the rest coherent.",
    chips: ["2 policy packs", "Dedicated envs", "Guardrails on"],
    heroStats: [
      { label: "Policy packs", value: "02", detail: "enforced + simulate lanes" },
      { label: "Webhook isolation", value: "92%", detail: "delivery boundary coverage" },
      { label: "Approval fallback", value: "100%", detail: "manual safety path intact" },
    ],
    command: "Describe settings as runtime design, not admin clutter.",
    narrative: [
      "Policy packs connect every other tab back to a coherent operating model.",
      "Environment defaults and notification rules make the product feel configured for scale.",
      "Runtime contracts close the loop by showing what must be true before production moves.",
    ],
  },
};

export const BASE_SIGNALS: Array<Omit<SignalItem, "stamp">> = [
  {
    title: "Deployment succeeded",
    detail: "Sales Ops Assistant promoted to production on OpenClaw with no dropped runs.",
    tone: "healthy",
  },
  {
    title: "Webhook retry succeeded",
    detail: "Stripe delivery recovered after a transient 502; backlog drained.",
    tone: "healthy",
  },
  {
    title: "Policy block",
    detail: "Unauthorized tool action stopped before egress crossed the tenant boundary.",
    tone: "warning",
  },
  {
    title: "Self-heal restart",
    detail: "Research Automator replaced a hot replica and returned to ready in 17 seconds.",
    tone: "focus",
  },
  {
    title: "Budget threshold warning",
    detail: "Model spend crossed 78% of the daily envelope; infra cost remains inside target.",
    tone: "warning",
  },
  {
    title: "API key rotated",
    detail: "Operator credential rotated without invalidating governed webhook deliveries.",
    tone: "focus",
  },
];

export const QUICK_ACTIONS: QuickAction[] = [
  { label: "Deploy new version", detail: "Promote rollout" },
  { label: "Rotate key", detail: "Refresh access" },
  { label: "Inspect failed run", detail: "Open recovery" },
  { label: "Provision environment", detail: "Create environment" },
  { label: "Create webhook", detail: "Add connector" },
];

export const AGENT_NAMES = [
  "dogfood",
  "jarv",
  "research",
  "ops",
  "security",
  "kb-manager",
  "automation-architect",
  "sales-assistant",
  "data-processor",
  "crawler",
  "council-ada",
  "council-aristotle",
];

export function relativeStamp(totalMinutes: number) {
  if (totalMinutes < 60) {
    return `${totalMinutes}m ago`;
  }

  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  return minutes === 0 ? `${hours}h ago` : `${hours}h ${minutes}m ago`;
}

export function rotate<T>(items: T[], offset: number) {
  if (items.length === 0) {
    return items;
  }

  const normalized = ((offset % items.length) + items.length) % items.length;
  return [...items.slice(normalized), ...items.slice(0, normalized)];
}

export function toneBadgeClasses(tone: Tone) {
  switch (tone) {
    case "healthy":
      return "border-[#285a43] bg-[#0f2018] text-[#78e3b4]";
    case "warning":
      return "border-[#65502b] bg-[#211a0e] text-[#f4cc82]";
    case "critical":
      return "border-[#66302e] bg-[#241312] text-[#ff9b96]";
    case "focus":
      return "border-[#294d6c] bg-[#101c26] text-[#8ac7ff]";
    default:
      return "border-[#34342e] bg-[#171813] text-[#aaa397]";
  }
}

export function toneTextClasses(tone: Tone) {
  switch (tone) {
    case "healthy":
      return "text-[#78e3b4]";
    case "warning":
      return "text-[#f4cc82]";
    case "critical":
      return "text-[#ff9b96]";
    case "focus":
      return "text-[#8ac7ff]";
    default:
      return "text-[#aaa397]";
  }
}

export function toneDotClasses(tone: Tone) {
  switch (tone) {
    case "healthy":
      return "bg-[#4bd69b]";
    case "warning":
      return "bg-[#efb654]";
    case "critical":
      return "bg-[#ff6d66]";
    case "focus":
      return "bg-[#58aaff]";
    default:
      return "bg-[#77766d]";
  }
}

export function formatCurrency(value: number) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: value >= 1000 ? 0 : 1,
  }).format(value);
}

export function buildPath(points: number[], width: number, height: number) {
  const max = Math.max(...points);
  const min = Math.min(...points);
  const range = max - min || 1;

  return points
    .map((point, index) => {
      const x = (index / (points.length - 1)) * width;
      const y = height - ((point - min) / range) * height;
      return `${index === 0 ? "M" : "L"} ${x.toFixed(2)} ${y.toFixed(2)}`;
    })
    .join(" ");
}

export function buildArea(points: number[], width: number, height: number) {
  return `${buildPath(points, width, height)} L ${width} ${height} L 0 ${height} Z`;
}
