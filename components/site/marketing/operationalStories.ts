import type { Metadata } from 'next'

import {
  DEFAULT_X_HANDLE,
  buildPageMetadata,
  getCanonicalUrl,
  getSiteUrl,
} from '@/lib/seo'

export type OperationalStoryAction = {
  readonly href: string
  readonly label: string
}

export type OperationalStoryItem = {
  readonly body: string
  readonly href?: string
  readonly title: string
}

export type OperationalStorySection = {
  readonly body: string
  readonly eyebrow: string
  readonly items: readonly [
    OperationalStoryItem,
    OperationalStoryItem,
    OperationalStoryItem,
    OperationalStoryItem,
  ]
  readonly title: string
}

export type OperationalStory = {
  readonly breadcrumbLabel?: string
  readonly cta: {
    readonly actions: readonly [OperationalStoryAction, OperationalStoryAction]
    readonly body: string
    readonly eyebrow: string
    readonly title: string
  }
  readonly evidence: OperationalStorySection
  readonly hero: {
    readonly actions: readonly [OperationalStoryAction, OperationalStoryAction]
    readonly body: string
    readonly eyebrow: string
    readonly title: string
  }
  readonly index: string
  readonly path: `/${string}`
  readonly record: {
    readonly id: string
    readonly operation: string
    readonly status: string
  }
  readonly seo: {
    readonly description: string
    readonly keywords?: readonly string[]
    readonly socialDescription: string
    readonly title: string
    readonly twitterDescription: string
    readonly twitterTitle: string
    readonly webPageDescription: string
    readonly webPageName: string
  }
  readonly workflow: OperationalStorySection
}

const githubAction = {
  href: 'https://github.com/mutx-dev/mutx-dev',
  label: 'View on GitHub',
} as const

const downloadAction = { href: '/download', label: 'Check Mac availability' } as const

export const operationalStories = {
  approvals: {
    index: '01',
    path: '/ai-agent-approvals',
    breadcrumbLabel: 'AI Agent Approvals',
    record: {
      id: 'AUTH-0142',
      operation: 'approval.request',
      status: 'WAITING ON OPERATOR',
    },
    seo: {
      title:
        'AI Agent Approval Workflows — Human-in-the-Loop Gates & Operator Authorization | MUTX',
      description:
        'Put a durable human decision around selected operations. Unbound runtime DEFER fails closed before the handler, while the approvals API keeps an assigned decision record.',
      keywords: [
        'ai agent approvals',
        'human in the loop ai agents',
        'ai agent approval workflow',
        'operator authorization',
        'approval gates for ai agents',
      ],
      socialDescription:
        'DEFER stops selected MUTX runtime tool calls before their registered handler runs.',
      twitterTitle: 'AI Agent Approval Workflows | MUTX',
      twitterDescription:
        'Human-in-the-loop records and pre-handler DEFER verdicts for the governed MUTX runtime path.',
      webPageName: 'AI Agent Approval Workflows | MUTX',
      webPageDescription:
        'Human-in-the-loop records, owner-scoped decisions, and pre-handler DEFER verdicts for MUTX-governed tool execution.',
    },
    hero: {
      eyebrow: 'AI Agent Approvals',
      title: 'Real gates,\nnot rubber stamps.',
      body:
        'You can’t review every operation, but you can put a human decision at selected boundaries. In the MUTX runtime, an unbound DEFER verdict fails closed before the registered handler runs; the separate approvals API persists who was assigned, who decided, and why.',
      actions: [downloadAction, { href: '/ai-agent-governance', label: 'Governance' }],
    },
    workflow: {
      eyebrow: 'How approvals work',
      title: 'Approvals with\nhonest boundaries.',
      body:
        'MUTX separates the gate from the inbox. Governed runtime calls can stop at a DEFER verdict before execution, while owner-scoped approval records give operators a durable review workflow.',
      items: [
        {
          title: 'Human-in-the-loop workflows',
          body:
            'Policy rules can return DEFER for tool calls that pass through the MUTX runtime handler. Without a durable serialized continuation, the handler is not invoked and no misleading resumable approval is emitted.',
        },
        {
          title: 'Operator authorization records',
          body:
            'The approvals API records owner, assigned reviewer, approver, status, comment, action type, agent, and session identifiers, and computes whether the current caller can resolve.',
        },
        {
          title: 'Escalation paths',
          body:
            'Pending records can be filtered by status and agent. An optional webhook can notify an operator system when a request is created.',
        },
        {
          title: 'Autonomous vs. approved',
          body:
            'Governed runtime receipts distinguish PERMIT, DENY, and DEFER. Approval records remain a separate control-plane contract until a caller links them to its resume path.',
        },
      ],
    },
    evidence: {
      eyebrow: 'Common approval gates',
      title: 'Where teams put\na human in the loop.',
      body:
        'The first approval workflows are usually obvious: destructive operations, privileged access, policy exceptions, or actions expensive enough that they shouldn’t run without a second pair of eyes.',
      items: [
        {
          title: 'Production changes',
          body:
            'Deployments, config mutations, and other production-facing actions. Usually the first place teams add approval gates because the risk is obvious and the review path is clear.',
        },
        {
          title: 'Credential and access changes',
          body:
            'Requests that touch secrets, credentials, or privileged scopes are easier to reason about when the authorization event is explicit and lives in the same system as the action.',
        },
        {
          title: 'High-cost actions',
          body:
            'Some actions aren’t dangerous — they’re expensive. Approval workflows slow down high-cost runs before they burn through budget.',
        },
        {
          title: 'Policy exceptions',
          body:
            'When an agent hits a guardrail or policy boundary, the next step should be a deliberate operator workflow — not a silent fallback or a buried log line.',
        },
      ],
    },
    cta: {
      eyebrow: 'Get started',
      title: 'Define an approval gate.\nWatch it block.',
      body:
        'Start with the runtime policy examples and approvals API. Put DEFER on one registered tool, inspect the fail-closed evidence, and bind canonical approval to a durable idempotent continuation before presenting the operation as resumable.',
      actions: [downloadAction, githubAction],
    },
  },
  auditLogs: {
    index: '02',
    path: '/ai-agent-audit-logs',
    record: {
      id: 'AUDIT-7781',
      operation: 'trace.seal',
      status: 'EVIDENCE ATTACHED',
    },
    seo: {
      title:
        'AI Agent Audit Logs — Decision Records, Policy Traces, Compliance Exports | MUTX',
      description:
        'Hash-chained evidence for tool calls executed through the governed MUTX runtime, plus APIs for caller-submitted runs, traces, logs, and adapter events.',
      socialDescription:
        'Hash-chained governed-operation evidence and caller-submitted run traces built for operator investigation.',
      twitterTitle: 'AI Agent Audit Logs | MUTX',
      twitterDescription:
        'Hash-chained evidence for governed tool calls, with query and verification exports for authorized operators.',
      webPageName: 'AI Agent Audit Logs | MUTX',
      webPageDescription:
        'Hash-chained governed-operation evidence and caller-submitted trace records for operator investigation.',
    },
    hero: {
      eyebrow: 'AI Agent Audit Logs',
      title: 'A record of what\nyour agents decided.',
      body:
        'When a review asks what happened, a generic success message is not enough. MUTX preserves policy decisions and outcomes for its governed runtime path, and accepts structured traces from instrumented callers.',
      actions: [downloadAction, { href: '/ai-agent-monitoring', label: 'Monitoring' }],
    },
    workflow: {
      eyebrow: 'Audit log properties',
      title: 'Logs built for answers,\nnot just retention.',
      body:
        'MUTX governed-operation events carry actor, run, session, policy, approval, outcome, and integrity fields. Trace depth still depends on what the runtime or adapter instruments and submits.',
      items: [
        {
          title: 'Decision records',
          body:
            'Tool calls routed through the MUTX runtime record authorization before an allowed handler runs, then append the observed outcome to the evidence chain.',
        },
        {
          title: 'Policy evaluation traces',
          body:
            'Governed-operation events include policy and rule references, the normalized tool name, the verdict, the reason, and a linked receipt hash.',
        },
        {
          title: 'Operator accountability',
          body:
            'Approval records identify requester and approver. Governed runtime evidence can also carry actor identity when the caller supplies it.',
        },
        {
          title: 'Compliance export',
          body:
            'Authorized audit roles can query by agent, session, run, time range, or event type and export a SHA-256 chain with an explicit verification result.',
        },
      ],
    },
    evidence: {
      eyebrow: 'Connected surfaces',
      title: 'Everything feeds\nthe audit log.',
      body:
        'MUTX exposes two evidence paths: hash-chained events for governed runtime operations, and structured run or adapter records submitted through authenticated APIs. Instrumentation determines coverage.',
      items: [
        {
          title: 'Governance',
          href: '/ai-agent-governance',
          body:
            'Policy decisions made in the governed runtime are linked to receipts and hash-chained audit events before allowed handlers execute.',
        },
        {
          title: 'Monitoring',
          href: '/ai-agent-monitoring',
          body:
            'Run trace endpoints preserve the ordered events an authenticated caller submits; SDK adapters report the lifecycle callbacks they observe.',
        },
        {
          title: 'Approvals',
          href: '/ai-agent-approvals',
          body:
            'Approval requests and resolutions are durable owner-scoped records. They are not automatically evidence for an external runtime unless that integration links them.',
        },
        {
          title: 'Guardrails',
          href: '/ai-agent-guardrails',
          body:
            'Denied and deferred MUTX runtime tool calls produce receipts and policy-check events. SDK text guardrails report locally unless the caller submits them.',
        },
      ],
    },
    cta: {
      eyebrow: 'Get started',
      title: 'Answer the question\nbefore compliance asks it.',
      body:
        'Run one tool through the governed runtime or submit an instrumented run. Then inspect exactly which events were captured and verify the exported evidence chain.',
      actions: [
        downloadAction,
        { href: '/ai-agent-approvals', label: 'Approval workflows' },
      ],
    },
  },
  controlPlane: {
    index: '03',
    path: '/ai-agent-control-plane',
    record: {
      id: 'PLANE-0001',
      operation: 'agent.execute',
      status: 'RUNTIME VISIBLE',
    },
    seo: {
      title: 'AI Agent Control Plane - Runtime Traces, Lifecycle, Agent Setup | MUTX',
      description:
        'MUTX brings authenticated agent records, lifecycle history, submitted traces, usage, and governed runtime evidence into one control plane.',
      socialDescription:
        'Authenticated lifecycle records, submitted traces, and governed runtime evidence in one operator control plane.',
      twitterTitle: 'AI Agent Control Plane | MUTX',
      twitterDescription:
        'Runtime traces, lifecycle records, and review dashboards for agents from setup to daily use.',
      webPageName: 'AI Agent Control Plane | MUTX',
      webPageDescription:
        'Authenticated lifecycle records, submitted traces, and governed runtime evidence in one operator control plane.',
    },
    hero: {
      eyebrow: 'AI Agent Control Plane',
      title: 'The control plane\nis the product.',
      body:
        'Most agent tooling treats the control plane as an afterthought. MUTX makes it the place where setup, runtime visibility, and daily review all come together.',
      actions: [downloadAction, { href: '/ai-agent-deployment', label: 'Deployment' }],
    },
    workflow: {
      eyebrow: 'Control plane properties',
      title: 'Read the runtime.\nKeep context clear.',
      body:
        'When something changes in production, you need to see what happened, which tools ran, and which settings were active. MUTX keeps that context easy to read.',
      items: [
        {
          title: 'Runtime visibility',
          body:
            'Inspect run traces and adapter events that your runtime instruments and submits, alongside governed tool-call evidence from the MUTX runtime.',
        },
        {
          title: 'Agent lifecycle',
          body:
            'Agent records carry authenticated ownership, type, configuration, status, versions, heartbeats, and lifecycle timestamps.',
        },
        {
          title: 'Agent setup',
          body:
            'Set up agents, review their actions, and keep the important details visible without digging through logs.',
        },
        {
          title: 'Consistent settings',
          body:
            'Version agent configuration records so operators can compare and restore control-plane state across revisions.',
        },
      ],
    },
    evidence: {
      eyebrow: 'Cross-cutting concerns',
      title: 'One plane.\nEvery concern.',
      body:
        'Governance, recorded usage, deployment lifecycle, and observability share control-plane identifiers. External runtimes and hosting providers still need deliberate integration.',
      items: [
        {
          title: 'Governance',
          href: '/ai-agent-governance',
          body:
            'Authenticated routes enforce user ownership or explicit roles. Tool policy enforcement applies to calls routed through the MUTX governed runtime.',
        },
        {
          title: 'Cost Management',
          href: '/ai-agent-cost',
          body:
            'Usage and budget endpoints summarize recorded credits. Runtime spend cutoffs are not implied by the reporting surface.',
        },
        {
          title: 'Monitoring',
          href: '/ai-agent-monitoring',
          body:
            'Authenticated ingestion, run, log, and metric endpoints tie submitted telemetry to owned agent records.',
        },
        {
          title: 'Deployment',
          href: '/ai-agent-deployment',
          body:
            'Deployment records expose desired replicas, status, versions, events, logs, and metrics. Provider rollout remains an operator integration.',
        },
      ],
    },
    cta: {
      eyebrow: 'Get started',
      title: 'See what your agents\nare actually doing.',
      body:
        'Check the Mac release lane or use the API, then review the traces, settings, and setup details your integration reports.',
      actions: [
        downloadAction,
        { href: '/docs/architecture/overview', label: 'Architecture overview' },
      ],
    },
  },
  cost: {
    index: '04',
    path: '/ai-agent-cost',
    breadcrumbLabel: 'AI Agent Cost Management',
    record: {
      id: 'COST-4200',
      operation: 'budget.evaluate',
      status: 'SPEND ATTRIBUTED',
    },
    seo: {
      title: 'AI Agent Cost Management — Per-Run Spend Tracking, Budgets, Attribution | MUTX',
      description:
        'See credits and usage events recorded by MUTX endpoints, with authenticated breakdowns by agent and event type. Runtime budget cutoffs remain an integration concern.',
      keywords: [
        'ai agent cost management',
        'llm cost tracking',
        'agent spend attribution',
        'ai agent budget controls',
        'runaway agent costs',
      ],
      socialDescription:
        'Owner-scoped usage records and monthly credit summaries in the MUTX control plane.',
      twitterTitle: 'AI Agent Cost Management | MUTX',
      twitterDescription:
        'Inspect recorded credits and usage by agent and event type before the billing review.',
      webPageName: 'AI Agent Cost Management | MUTX',
      webPageDescription:
        'Inspect recorded usage credits by agent and event type, with monthly plan totals and remaining-credit summaries.',
    },
    hero: {
      eyebrow: 'AI Agent Cost Management',
      title: 'Know what your AI\nagents cost — per run.',
      body:
        'Provider invoices rarely explain which control-plane operation consumed the budget. MUTX keeps authenticated usage events and agent-scoped resource records so operators can investigate what was reported and where.',
      actions: [downloadAction, { href: '/ai-agent-monitoring', label: 'Monitoring' }],
    },
    workflow: {
      eyebrow: 'Cost properties',
      title: 'Cost is a control\nplane concern.',
      body:
        'Cost visibility starts with honest inputs. MUTX reports the credits and resource usage its endpoints or integrated runtimes record; it does not turn that report into an automatic model-call cutoff.',
      items: [
        {
          title: 'AI agent spend tracking',
          body:
            'Query recorded credits by agent and event type, or submit agent resource usage with token, API-call, model, and cost fields.',
        },
        {
          title: 'Per-run attribution',
          body:
            'Agent resource-usage records carry a reporting period and authenticated agent ownership, making submitted costs easier to trace than a shared API key.',
        },
        {
          title: 'Budget reporting',
          body:
            'Monthly budget endpoints calculate plan credits used, remaining, and reset date from recorded events. Enforcement before a provider call must be wired by the runtime operator.',
        },
        {
          title: 'Model and provider visibility',
          body:
            'Model and custom metadata can travel with submitted agent resource-usage records. The fidelity of provider attribution depends on the reporting integration.',
        },
      ],
    },
    evidence: {
      eyebrow: 'Failure modes',
      title: 'Catch expensive failures\nwhile the runtime is live.',
      body:
        'Agent cost management isn’t a finance dashboard. It’s a way to catch retry storms, stale workers, and runaway workflows before the billing cycle closes.',
      items: [
        {
          title: 'Runaway retry loops',
          body:
            'Repeated usage events can expose a retry pattern when the runtime reports them. Operators can then inspect the related run and stop the agent through its lifecycle controls.',
        },
        {
          title: 'Background worker drift',
          body:
            'Periodic resource-usage records keep token, call, and cost reports attached to an owned agent across a defined time window.',
        },
        {
          title: 'Approval-aware budgets',
          body:
            'Approval and usage surfaces share agent and session identifiers when the caller supplies them, giving integrations a clean way to link high-cost review paths.',
        },
        {
          title: 'Trace-linked investigations',
          body:
            'Runs, usage records, and governed-operation evidence are queryable in the same control plane; correlation depends on the identifiers reported by the integration.',
        },
      ],
    },
    cta: {
      eyebrow: 'Get started',
      title: 'Set a budget before\nyour agents set one for you.',
      body:
        'Connect usage reporting for one agent, then inspect the monthly credit summary and agent breakdown before deciding where a runtime cutoff belongs.',
      actions: [downloadAction, githubAction],
    },
  },
  deployment: {
    index: '05',
    path: '/ai-agent-deployment',
    record: {
      id: 'DEPLOY-0317',
      operation: 'release.promote',
      status: 'ROLLBACK READY',
    },
    seo: {
      title: 'AI Agent Deployment — Repeatable Envs, Audit Trails, Rollback | MUTX',
      description:
        'Track deployment desired state, lifecycle events, versions, logs, metrics, and record-level rollback. Provider rollout remains operator-owned.',
      socialDescription:
        'Deployment lifecycle records, version history, and explicit record rollback in the control plane.',
      twitterTitle: 'AI Agent Deployment | MUTX',
      twitterDescription:
        'Versioned deployment records and lifecycle history, with provider execution left explicit.',
      webPageName: 'AI Agent Deployment | MUTX',
      webPageDescription:
        'Deployment desired state, lifecycle events, version history, logs, metrics, and record-level rollback in the control plane.',
    },
    hero: {
      eyebrow: 'AI Agent Deployment',
      title: 'Ship agents\nlike services.',
      body:
        'MUTX makes deployment state inspectable: desired replicas, status, lifecycle events, versions, logs, and metrics live on an authenticated record. The operator still owns the provider action that makes that record real.',
      actions: [downloadAction, { href: '/ai-agent-control-plane', label: 'Control Plane' }],
    },
    workflow: {
      eyebrow: 'Deployment properties',
      title: 'Deployment is a record.\nNot a prayer.',
      body:
        'A durable deployment record gives operators one place to inspect lifecycle state and history. MUTX can change that record through start, stop, scale, restart, terminate, and rollback APIs; it does not silently deploy a hosting provider.',
      items: [
        {
          title: 'Explicit desired state',
          body:
            'Record the owned agent, desired replica count, version label, status, and node assignment instead of hiding them inside a provider script.',
        },
        {
          title: 'Deployment records',
          body:
            'Create, start, stop, scale, restart, terminate, heartbeat, and rollback transitions append lifecycle events to the deployment record.',
        },
        {
          title: 'Rollback paths',
          body:
            'The rollback API restores a stored control-plane snapshot and records the transition. Applying that state to Railway, Kubernetes, or another provider remains the deployment integration’s job.',
        },
        {
          title: 'Provider boundary',
          body:
            'MUTX keeps desired state and provider execution separate. Operators can verify what the control plane recorded without mistaking a successful API response for a completed rollout.',
        },
      ],
    },
    evidence: {
      eyebrow: 'Connected surfaces',
      title: 'Everything flows from\nthe deployment record.',
      body:
        'Lifecycle events, agent logs, and agent metrics can be read from the deployment surface. Governance and usage remain separate records unless an integration supplies shared identifiers.',
      items: [
        {
          title: 'Governance',
          href: '/ai-agent-governance',
          body:
            'Deployment routes enforce authenticated ownership. Tool policies are enforced only when execution passes through the governed MUTX runtime.',
        },
        {
          title: 'Cost Management',
          href: '/ai-agent-cost',
          body:
            'Deployment actions emit usage events, so recorded control-plane activity can appear in budget and usage breakdowns.',
        },
        {
          title: 'Monitoring',
          href: '/ai-agent-monitoring',
          body:
            'Deployment endpoints expose lifecycle events plus the owned agent’s submitted logs and metrics. Run traces remain a separate instrumented surface.',
        },
        {
          title: 'Reliability',
          href: '/ai-agent-reliability',
          body:
            'Agent heartbeats can promote the latest deployment record to running. Infrastructure readiness probes validate the MUTX services, not arbitrary external agent instances.',
        },
      ],
    },
    cta: {
      eyebrow: 'Get started',
      title: 'Deploy an agent.\nSee the record.',
      body:
        'Create a deployment record, inspect its event and version history, then connect the provider action explicitly so recorded state and deployed state can be verified separately.',
      actions: [
        downloadAction,
        { href: '/docs/deployment/quickstart', label: 'Deployment quickstart' },
      ],
    },
  },
  governance: {
    index: '06',
    path: '/ai-agent-governance',
    record: {
      id: 'GOV-2104',
      operation: 'policy.evaluate',
      status: 'RUNTIME BOUNDARY',
    },
    seo: {
      title:
        'AI Agent Governance — Auth Boundaries, Access Control & Audit Compliance | MUTX',
      description:
        'MUTX enforces authentication, ownership, and role checks on control-plane paths, and evaluates tool policy for calls routed through its governed runtime handler.',
      socialDescription:
        'Auth boundaries, operator access controls, and compliance audit trails baked into the control plane. No implicit permissions.',
      twitterTitle: 'AI Agent Governance | MUTX',
      twitterDescription:
        'Auth boundaries and compliance guardrails baked into the control plane. Agent access stays explicit and auditable.',
      webPageName: 'AI Agent Governance | MUTX',
      webPageDescription:
        'Auth boundaries, operator access controls, and compliance audit trails baked into the control plane. No implicit permissions, no undocumented access.',
    },
    hero: {
      eyebrow: 'AI Agent Governance',
      title: 'Lock down what\nevery agent can touch.',
      body:
        'Implicit access is hard to review. MUTX makes control-plane ownership and roles explicit, then adds pre-execution policy decisions for tools registered with the governed MUTX runtime.',
      actions: [downloadAction, { href: '/ai-agent-control-plane', label: 'Control Plane' }],
    },
    workflow: {
      eyebrow: 'How governance works',
      title: 'Policies that follow\nthe agent.',
      body:
        'MUTX governance has a precise boundary: API routes protect owned resources, and the MUTX runtime evaluates normalized tool calls before invoking registered handlers. External runtimes need their own adapter or Faramesh integration.',
      items: [
        {
          title: 'Auth boundaries',
          body:
            'The default MUTX runtime policy allows known low-risk built-ins and denies unconfigured custom tools. Additional policy sets can scope matching tool and agent patterns.',
        },
        {
          title: 'Operator access control',
          body:
            'Authenticated route dependencies enforce ownership for user resources and explicit roles for internal, audit, and privileged operations.',
        },
        {
          title: 'Compliance guardrails',
          body:
            'Governed runtime decisions create receipts and hash-chained evidence. That evidence supports review; compliance suitability still depends on deployment, retention, and organizational controls.',
        },
        {
          title: 'Policy-as-code',
          body:
            'Policy sets and rules are deterministic runtime objects. Faramesh FPL support is a separate preview path that depends on an operator-managed local daemon.',
        },
      ],
    },
    evidence: {
      eyebrow: 'Where governance applies',
      title: 'Governance isn’t a bolt-on.\nIt’s the foundation.',
      body:
        'Governance is strongest when the boundary is explicit. MUTX protects control-plane resources and governed runtime tool dispatch; it does not claim to intercept actions taken by an uninstrumented external agent.',
      items: [
        {
          title: 'Control Plane',
          href: '/ai-agent-control-plane',
          body:
            'User-scoped API routes require authentication and ownership. Privileged surfaces add role checks where the route declares them.',
        },
        {
          title: 'Deployment',
          href: '/ai-agent-deployment',
          body:
            'Deployment records are owner-scoped desired state. Provider execution and policy attachment must be connected and verified by the operator integration.',
        },
        {
          title: 'Monitoring',
          href: '/ai-agent-monitoring',
          body:
            'Governed runtime DENY and DEFER verdicts produce receipts and telemetry; visibility for external runtimes depends on their instrumentation.',
        },
        {
          title: 'Audit Logs',
          href: '/ai-agent-audit-logs',
          body:
            'Policy authorization is persisted before an allowed MUTX runtime handler executes. Post-execution evidence describes only the outcomes the handler can report.',
        },
      ],
    },
    cta: {
      eyebrow: 'Get started',
      title: 'Ship your first\nagent auth boundary.',
      body:
        'Start with one governed MUTX runtime tool, inspect its policy receipt, then add adapters deliberately for any external runtime that must share the boundary.',
      actions: [
        downloadAction,
        { href: '/ai-agent-approvals', label: 'Approval workflows' },
      ],
    },
  },
  guardrails: {
    index: '07',
    path: '/ai-agent-guardrails',
    record: {
      id: 'GUARD-9880',
      operation: 'boundary.check',
      status: 'POLICY EVALUATED',
    },
    seo: {
      title: 'AI Agent Guardrails — Runtime Policy Enforcement & Safety Boundaries | MUTX',
      description:
        'Apply deterministic policy to governed MUTX runtime tools, or opt into SDK input and output guardrails for supported integrations.',
      socialDescription:
        'Pre-handler policy decisions for the MUTX runtime and opt-in SDK text guardrails.',
      twitterTitle: 'AI Agent Guardrails | MUTX',
      twitterDescription:
        'Deterministic tool policy inside the governed MUTX runtime, plus opt-in SDK text checks.',
      webPageName: 'AI Agent Guardrails | MUTX',
      webPageDescription:
        'Deterministic tool policy inside the governed MUTX runtime and opt-in SDK input/output checks.',
    },
    hero: {
      eyebrow: 'AI Agent Guardrails',
      title: 'Draw the line on\nwhat agents can’t do.',
      body:
        'MUTX offers two guardrail layers with different scope: pre-handler policy for tools dispatched by its runtime, and optional SDK middleware for text entering or leaving an integrated agent.',
      actions: [downloadAction, { href: '/ai-agent-governance', label: 'Governance' }],
    },
    workflow: {
      eyebrow: 'How guardrails work',
      title: 'Safety policies,\nnot safety theater.',
      body:
        'A guardrail is only real where code invokes it. MUTX runtime DENY and DEFER verdicts stop registered handlers; SDK text checks block only when the caller enables and runs the middleware.',
      items: [
        {
          title: 'Runtime policy enforcement',
          body:
            'Policy rules match normalized tool, agent, and session identifiers before a registered MUTX runtime handler runs.',
        },
        {
          title: 'Safety boundaries',
          body:
            'Built-in command constraints block known dangerous shell patterns. Custom policy rules can deny or defer additional registered tools.',
        },
        {
          title: 'Violation visibility',
          body:
            'Denied and deferred governed calls return a reason, receipt identifier, and integrity hash. SDK text guardrails raise a local exception unless the caller reports it.',
        },
        {
          title: 'Policy versioning',
          body:
            'Governed audit events carry policy and rule references. Policy lifecycle is not automatically coupled to deployment or agent-version records.',
        },
      ],
    },
    evidence: {
      eyebrow: 'How guardrails connect',
      title: 'Guardrails are\ngovernance, enforced.',
      body:
        'Governed runtime policy decisions generate receipts, audit evidence, and security telemetry. SDK text guardrails remain local unless an integration forwards their results.',
      items: [
        {
          title: 'Governance',
          href: '/ai-agent-governance',
          body:
            'The governed MUTX runtime turns configured tool rules into ALLOW, DENY, MODIFY, or DEFER decisions before dispatch.',
        },
        {
          title: 'Monitoring',
          href: '/ai-agent-monitoring',
          body:
            'Security telemetry is emitted for governed runtime decisions. External backends receive it only when telemetry export is configured.',
        },
        {
          title: 'Reliability',
          href: '/ai-agent-reliability',
          body:
            'Policy verdicts do not automatically trip agent failover. Webhook delivery has its own circuit breaker, and operators can build additional responses from emitted events.',
        },
        {
          title: 'Audit Logs',
          href: '/ai-agent-audit-logs',
          body:
            'Governed runtime denials and deferrals are hash-chained with policy references and normalized action context for authorized review.',
        },
      ],
    },
    cta: {
      eyebrow: 'Get started',
      title: 'Write a policy.\nBreak it on purpose.',
      body:
        'Write one tool policy, trigger it through the MUTX runtime handler, and inspect the verdict and receipt. For SDK text checks, enable middleware explicitly and test the blocked input locally.',
      actions: [downloadAction, githubAction],
    },
  },
  infrastructure: {
    index: '08',
    path: '/ai-agent-infrastructure',
    record: {
      id: 'INFRA-6032',
      operation: 'runtime.resolve',
      status: 'TOPOLOGY VISIBLE',
    },
    seo: {
      title: 'AI Agent Infrastructure — Compute, Secrets, Storage, Network | MUTX',
      description:
        'Make agent configuration, reported resource use, deployment state, and service health visible without pretending MUTX owns the underlying provider.',
      socialDescription:
        'Agent configuration, reported resource use, deployment state, and service health in one control plane.',
      twitterTitle: 'AI Agent Infrastructure | MUTX',
      twitterDescription:
        'Inspect agent config, reported CPU and memory, deployment state, and control-plane health.',
      webPageName: 'AI Agent Infrastructure | MUTX',
      webPageDescription:
        'Inspect agent configuration, reported resource use, deployment state, and control-plane service health.',
    },
    hero: {
      eyebrow: 'AI Agent Infrastructure',
      title: 'Infrastructure you\ncan actually see.',
      body:
        'MUTX records agent configuration, desired deployment state, heartbeats, logs, and submitted CPU or memory metrics. Hosting, secret storage, network policy, and provider rollout remain explicit operator responsibilities.',
      actions: [downloadAction, { href: '/ai-agent-control-plane', label: 'Control Plane' }],
    },
    workflow: {
      eyebrow: 'Infrastructure properties',
      title: 'Know what’s running.\nOwn why.',
      body:
        'The control plane gives infrastructure a readable interface without claiming to replace it. Use MUTX for owned records and reported signals; use Terraform, Helm, Railway, or your provider to apply the underlying resources.',
      items: [
        {
          title: 'Compute management',
          body:
            'Deployment records expose desired replicas, region, node identifier, version, and status. Applying replica changes to real compute requires a provider integration.',
        },
        {
          title: 'Secrets management',
          body:
            'MUTX manages its own user and agent API credentials and exposes governance credential-broker contracts. External secret backends remain configuration-dependent.',
        },
        {
          title: 'Storage layer',
          body:
            'The API persists agent, run, deployment, event, log, metric, and workflow records. It does not inventory arbitrary storage used by an external agent.',
        },
        {
          title: 'Network topology',
          body:
            'Repository Helm, Docker, and Terraform assets define MUTX service networking. Per-agent network reachability is not automatically enforced by the control-plane record.',
        },
      ],
    },
    evidence: {
      eyebrow: 'Connected surfaces',
      title: 'Infra isn’t a side quest.\nIt’s the foundation.',
      body:
        'MUTX connects owned agent identifiers to deployment records, submitted metrics, logs, and usage. Reconciliation with provider resources remains part of the operator integration.',
      items: [
        {
          title: 'Governance',
          href: '/ai-agent-governance',
          body:
            'Control-plane routes protect stored resources, and the governed runtime protects its registered tools. Infrastructure permissions still come from the deployed environment.',
        },
        {
          title: 'Deployment',
          href: '/ai-agent-deployment',
          body:
            'Deployment records retain desired replicas and version snapshots. Provider-specific compute and storage changes must be applied and verified separately.',
        },
        {
          title: 'Cost Management',
          href: '/ai-agent-cost',
          body:
            'Agent resource-usage records can carry CPU, memory, token, call, model, and cost reports when an integration submits them.',
        },
        {
          title: 'Guardrails',
          href: '/ai-agent-guardrails',
          body:
            'SDK guardrails and governed tool policy do not replace network policy. Use infrastructure controls for network isolation and report relevant events back to MUTX when needed.',
        },
      ],
    },
    cta: {
      eyebrow: 'Get started',
      title: 'See your infra.\nAll of it.',
      body:
        'Register an agent, submit heartbeats and resource metrics, and inspect the deployment record. Then verify the corresponding provider resources with the operator tooling that owns them.',
      actions: [
        downloadAction,
        { href: '/docs/architecture/overview', label: 'Architecture overview' },
      ],
    },
  },
  monitoring: {
    index: '09',
    path: '/ai-agent-monitoring',
    record: {
      id: 'TRACE-1187',
      operation: 'tool.invoke',
      status: 'OUTCOME RECORDED',
    },
    seo: {
      title:
        'AI Agent Monitoring — Execution Traces, Tool Call History, Outcome Records | MUTX',
      description:
        'Inspect ordered run traces, adapter events, logs, metrics, and governed tool-call evidence reported to MUTX by instrumented runtimes.',
      socialDescription:
        'Ordered traces and runtime signals reported by instrumented agents, plus governed MUTX runtime evidence.',
      twitterTitle: 'AI Agent Monitoring | MUTX',
      twitterDescription:
        'Inspect the traces, callbacks, logs, and metrics your integrated runtime actually reports.',
      webPageName: 'AI Agent Monitoring | MUTX',
      webPageDescription:
        'Inspect ordered traces, adapter callbacks, logs, metrics, and governed tool-call evidence reported to MUTX.',
    },
    hero: {
      eyebrow: 'AI Agent Monitoring',
      title: 'See what agents\nactually did.',
      body:
        'When something breaks, operators need reported execution evidence rather than a model summary. MUTX stores ordered trace events and adapter callbacks from instrumented callers, with stronger receipts for its governed runtime path.',
      actions: [downloadAction, { href: '/ai-agent-control-plane', label: 'Control Plane' }],
    },
    workflow: {
      eyebrow: 'Observability properties',
      title: 'Traces, not tail outputs.',
      body:
        'MUTX preserves the event sequence a caller submits. It does not manufacture missing model calls, tool invocations, context changes, or outcomes when an integration does not observe them.',
      items: [
        {
          title: 'Execution traces',
          body:
            'Run trace records retain event type, message, payload, timestamp, and deterministic sequence for the events the caller submits.',
        },
        {
          title: 'Tool call history',
          body:
            'SDK adapters emit the lifecycle callbacks they observe. The governed MUTX runtime also records normalized tool authorization and handler outcomes.',
        },
        {
          title: 'Outcome records',
          body:
            'Run and governed-operation records can carry output or error context. Coverage is bounded by the runtime’s instrumentation and redaction choices.',
        },
        {
          title: 'Alert routing',
          body:
            'Owned alert records can be filtered and resolved through the monitoring API. Notification routing depends on configured webhooks or operator integrations.',
        },
      ],
    },
    evidence: {
      eyebrow: 'Connected surfaces',
      title: 'Monitoring is the payoff\nfor good control.',
      body:
        'Runs, governed decisions, deployment events, and usage records share control-plane identifiers when integrations provide them. They are not automatically fused into one complete trace.',
      items: [
        {
          title: 'Governance',
          href: '/ai-agent-governance',
          body:
            'Governed MUTX runtime decisions emit receipts, audit events, and security telemetry. External auth failures need explicit reporting.',
        },
        {
          title: 'Deployment',
          href: '/ai-agent-deployment',
          body:
            'Deployment lifecycle events, logs, and metrics are queryable alongside runs. Direct trace-to-deployment correlation depends on submitted metadata.',
        },
        {
          title: 'Cost Management',
          href: '/ai-agent-cost',
          body:
            'Recorded usage and runs can be compared by agent and time window. Exact cost-to-trace attribution requires the integration to submit shared identifiers.',
        },
        {
          title: 'Audit Logs',
          href: '/ai-agent-audit-logs',
          body:
            'Governed runtime evidence is hash-chained. General run traces remain authenticated caller-submitted records with their own retention contract.',
        },
      ],
    },
    cta: {
      eyebrow: 'Get started',
      title: 'Watch the runtime\ndo something real.',
      body:
        'Instrument one runtime, submit a run, and inspect the resulting event sequence. Missing events should stay visibly missing instead of being inferred by the UI.',
      actions: [
        downloadAction,
        { href: '/ai-agent-cost', label: 'Cost management' },
      ],
    },
  },
  reliability: {
    index: '10',
    path: '/ai-agent-reliability',
    record: {
      id: 'HEALTH-0042',
      operation: 'probe.readiness',
      status: 'CIRCUIT HEALTHY',
    },
    seo: {
      title: 'AI Agent Reliability — Health Checks, Circuit Breakers, Failover | MUTX',
      description:
        'Monitor agent heartbeats, create stale-agent alerts, inspect service readiness, and contain failing webhook delivery with a circuit breaker.',
      socialDescription:
        'Heartbeat state, stale-agent alerts, service readiness, and webhook delivery containment.',
      twitterTitle: 'AI Agent Reliability | MUTX',
      twitterDescription:
        'Heartbeat monitoring, readiness signals, alerts, and a webhook delivery circuit breaker.',
      webPageName: 'AI Agent Reliability | MUTX',
      webPageDescription:
        'Heartbeat monitoring, stale-agent alerts, service readiness, and webhook delivery containment in the control plane.',
    },
    hero: {
      eyebrow: 'AI Agent Reliability',
      title: 'Agents that\nsurvive production.',
      body:
        'MUTX turns reported heartbeats into operator state: stale agents can be marked failed, alerts and lifecycle events are recorded, and service probes distinguish liveness from database readiness.',
      actions: [downloadAction, { href: '/ai-agent-monitoring', label: 'Monitoring' }],
    },
    workflow: {
      eyebrow: 'Reliability properties',
      title: 'Reliability is a control\nplane property.',
      body:
        'Reliability starts with signals that say exactly what they measure. MUTX monitors control-plane and reported agent health; it does not claim provider-level traffic failover for external agent instances.',
      items: [
        {
          title: 'Health checks',
          body:
            'The control plane tracks agent heartbeats and submitted CPU or memory metrics. Its root probes report API liveness and database-aware readiness.',
        },
        {
          title: 'Readiness probes',
          body:
            'The `/ready` probe confirms MUTX database availability. Helm wires it to the API workload; it does not attest an external agent’s context or tools.',
        },
        {
          title: 'Circuit breakers',
          body:
            'Webhook delivery tracks consecutive failures and opens a delivery circuit breaker. This breaker does not govern arbitrary model or tool traffic.',
        },
        {
          title: 'Recovery boundary',
          body:
            'The background monitor can update control-plane status and invoke configured recovery handlers. The default handler restores records; provider restart and traffic failover require an external integration.',
        },
      ],
    },
    evidence: {
      eyebrow: 'Connected surfaces',
      title: 'Reliability connects to\nthe rest of the plane.',
      body:
        'Heartbeat failures, alerts, deployment lifecycle events, and webhook delivery state are visible to operators. Provider recovery and spend enforcement remain separate concerns.',
      items: [
        {
          title: 'Cost Management',
          href: '/ai-agent-cost',
          body:
            'Budget endpoints report recorded credits. They do not automatically throttle an agent when a threshold is reached.',
        },
        {
          title: 'Deployment',
          href: '/ai-agent-deployment',
          body:
            'Heartbeats can update the latest deployment record, and monitor failures append deployment events. Provider rollout health must be verified separately.',
        },
        {
          title: 'Monitoring',
          href: '/ai-agent-monitoring',
          body:
            'Owned alerts and submitted metrics appear in monitoring views; webhook delivery state is available through webhook APIs.',
        },
        {
          title: 'Guardrails',
          href: '/ai-agent-guardrails',
          body:
            'Guardrail verdicts and webhook circuit breakers are separate mechanisms. Operators can correlate them only when integrations report shared context.',
        },
      ],
    },
    cta: {
      eyebrow: 'Get started',
      title: 'Ship an agent. Watch the\nhealth surface respond.',
      body:
        'Connect one agent heartbeat, inspect the stale-state transition and alert contract, then test webhook failure containment without confusing it with provider failover.',
      actions: [downloadAction, { href: '/docs/quickstart', label: 'Read quickstart' }],
    },
  },
} as const satisfies Record<string, OperationalStory>

export function buildOperationalStoryMetadata(story: OperationalStory): Metadata {
  return {
    title: story.seo.title,
    description: story.seo.description,
    ...(story.seo.keywords ? { keywords: [...story.seo.keywords] } : {}),
    ...buildPageMetadata({
      title: story.seo.title,
      description: story.seo.description,
      path: story.path,
      socialDescription: story.seo.socialDescription,
      twitterTitle: story.seo.twitterTitle,
      twitterDescription: story.seo.twitterDescription,
    }),
  }
}

export function buildOperationalStoryStructuredData(story: OperationalStory) {
  const siteUrl = getSiteUrl()
  const graph: Array<Record<string, unknown>> = [
    {
      '@type': 'Organization',
      '@id': `${siteUrl}/#organization`,
      name: 'MUTX',
      url: siteUrl,
      sameAs: [`https://x.com/${DEFAULT_X_HANDLE.replace('@', '')}`],
    },
    {
      '@type': 'SoftwareApplication',
      name: 'MUTX',
      applicationCategory: 'DeveloperApplication',
      description:
        'Source-available control plane for AI agent governance, deployment, and observability.',
      downloadUrl: `${siteUrl}/download`,
      offers: { '@type': 'Offer', price: '0', priceCurrency: 'USD' },
    },
    {
      '@type': 'WebPage',
      name: story.seo.webPageName,
      url: getCanonicalUrl(story.path),
      description: story.seo.webPageDescription,
      isPartOf: { '@type': 'WebSite', name: 'MUTX', url: siteUrl },
    },
  ]

  if (story.breadcrumbLabel) {
    graph.push({
      '@type': 'BreadcrumbList',
      itemListElement: [
        {
          '@type': 'ListItem',
          position: 1,
          name: 'MUTX',
          item: siteUrl,
        },
        {
          '@type': 'ListItem',
          position: 2,
          name: story.breadcrumbLabel,
          item: getCanonicalUrl(story.path),
        },
      ],
    })
  }

  return { '@context': 'https://schema.org', '@graph': graph }
}
