import Link from 'next/link'
import { ArrowRight, ArrowUpRight } from 'lucide-react'

import { PublicNav } from '@/components/site/PublicNav'
import styles from './RebrandHomePage.module.css'

const RUN_EVENTS = [
  {
    time: '09:42:03.184',
    type: 'intent',
    title: 'Request accepted',
    detail: 'Promote release 1.4.0 to production',
    state: 'recorded',
    gated: false,
  },
  {
    time: '09:42:04.907',
    type: 'tool',
    title: 'Deployment record prepared',
    detail: 'desired replicas · 3 targets',
    state: 'observed',
    gated: false,
  },
  {
    time: '09:42:05.116',
    type: 'policy',
    title: 'Production boundary matched',
    detail: 'policy.prod-change · approval required',
    state: 'held',
    gated: true,
  },
  {
    time: '09:43:11.402',
    type: 'approval',
    title: 'Approved by A. Rivera',
    detail: 'scope unchanged · expires in 10m',
    state: 'released',
    gated: false,
  },
  {
    time: '09:43:18.620',
    type: 'result',
    title: 'Lifecycle record updated',
    detail: 'status ready · provider check external',
    state: 'recorded',
    gated: false,
  },
] as const

const CONTROL_LOOP = [
  {
    number: '01',
    label: 'Observe',
    title: 'Read the run as it unfolds.',
    href: '/ai-agent-monitoring',
  },
  {
    number: '02',
    label: 'Bound',
    title: 'Match governed moves to policy.',
    href: '/ai-agent-guardrails',
  },
  {
    number: '03',
    label: 'Approve',
    title: 'Put a human at the hard edge.',
    href: '/ai-agent-approvals',
  },
  {
    number: '04',
    label: 'Execute',
    title: 'Ship inside the agreed scope.',
    href: '/ai-agent-deployment',
  },
  {
    number: '05',
    label: 'Prove',
    title: 'Keep the evidence that survives review.',
    href: '/ai-agent-audit-logs',
  },
] as const

const PREVIEW_RUNS = [
  { id: 'run_4812', task: 'Promote release 1.4.0', status: 'Approval', tone: 'hold' },
  { id: 'run_4811', task: 'Reconcile webhook delivery', status: 'Running', tone: 'live' },
  { id: 'run_4810', task: 'Rotate staging credential', status: 'Complete', tone: 'done' },
] as const

const SETUP_STEPS = [
  { number: '01', label: 'Install', value: 'Check macOS availability' },
  { number: '02', label: 'Connect', value: 'mutx setup' },
  { number: '03', label: 'Operate', value: 'Open the dashboard' },
] as const

export function RebrandHomePage() {
  return (
    <main id="main-content" tabIndex={-1} className={styles.page}>
      <section className={styles.hero} aria-labelledby="home-title">
        <PublicNav overlay />

        <div className={styles.heroGrid}>
          <div className={styles.heroCopy}>
            <p className={styles.eyebrow}>
              <span className={styles.liveDot} aria-hidden="true" />
              Source-available agent operations
            </p>
            <h1 id="home-title">
              Read the governed path.
              <span>Hold the line.</span>
            </h1>
            <p className={styles.heroLede}>
              MUTX records submitted runtime evidence and evaluates registered tool
              calls before they execute through its governed runtime.
            </p>
            <div className={styles.heroActions}>
              <Link href="/download" className={styles.primaryAction}>
                Check Mac availability <ArrowRight className="rtl-directional-icon" aria-hidden="true" />
              </Link>
              <Link href="/dashboard" className={styles.secondaryAction}>
                Open dashboard <ArrowUpRight aria-hidden="true" />
              </Link>
            </div>
            <p className={styles.heroMeta}>
              <span>macOS</span>
              <span>API</span>
              <span>CLI</span>
              <span>Self-hostable control plane</span>
            </p>
          </div>

          <div className={styles.ledgerWrap}>
            <div className={styles.ledger} aria-label="Example MUTX governed deployment record">
              <header className={styles.ledgerHeader}>
                <div>
                  <p>Run / 4812</p>
                  <strong>Production promotion</strong>
                </div>
                <span className={styles.ledgerStatus}>
                  <i aria-hidden="true" /> Recorded
                </span>
              </header>

              <div className={styles.intentStrip}>
                <span>Intent</span>
                <p>Promote release 1.4.0 without widening its production scope.</p>
              </div>

              <ol className={styles.eventRail}>
                {RUN_EVENTS.map((event) => (
                  <li
                    key={`${event.time}-${event.type}`}
                    className={event.gated ? styles.gatedEvent : undefined}
                  >
                    <span className={styles.eventNode} aria-hidden="true" />
                    <div className={styles.eventMeta}>
                      <time>{event.time}</time>
                      <span>{event.type}</span>
                    </div>
                    <div className={styles.eventCopy}>
                      <strong>{event.title}</strong>
                      <code>{event.detail}</code>
                    </div>
                    <span className={styles.eventState}>{event.state}</span>
                  </li>
                ))}
              </ol>

              <footer className={styles.receipt}>
                <div>
                  <span>Receipt</span>
                  <strong>rcpt_7F2A91</strong>
                </div>
                <p>5 events · 1 policy gate · scope preserved</p>
              </footer>
            </div>
            <p className={styles.ledgerCaption}>
              Representative run record <span>01 / observe → prove</span>
            </p>
          </div>
        </div>
      </section>

      <section id="product" className={styles.controlSection} aria-labelledby="control-title">
        <header className={styles.sectionIntro}>
          <p className={styles.sectionIndex}>01 / Control loop</p>
          <div>
            <h2 id="control-title">One line from intent to evidence.</h2>
            <p>
              For calls routed through the governed MUTX runtime, policy and
              authorization evidence stay linked to the observed handler outcome.
            </p>
          </div>
        </header>

        <ol className={styles.controlRail}>
          {CONTROL_LOOP.map((item) => (
            <li key={item.number}>
              <Link href={item.href}>
                <span className={styles.controlNode} aria-hidden="true" />
                <span className={styles.controlNumber}>{item.number}</span>
                <strong>{item.label}</strong>
                <p>{item.title}</p>
                <ArrowUpRight aria-hidden="true" />
              </Link>
            </li>
          ))}
        </ol>
      </section>

      <section className={styles.productSection} aria-labelledby="surface-title">
        <div className={styles.productLayout}>
          <div className={styles.productCopy}>
            <p className={styles.sectionIndex}>02 / Operator surface</p>
            <h2 id="surface-title">Signal first. Furniture last.</h2>
            <p>
              Fleet health, active work, interventions, spend, and evidence stay in
              one hierarchy—so operators can act before the postmortem.
            </p>
            <ul>
              <li>Submitted run state and trace context</li>
              <li>Policy decisions beside the action</li>
              <li>Receipts for governed runtime decisions</li>
            </ul>
            <div className={styles.textLinks}>
              <Link href="/dashboard">
                Explore the dashboard <ArrowRight className="rtl-directional-icon" aria-hidden="true" />
              </Link>
              <Link href="/docs">
                Read the docs <ArrowUpRight aria-hidden="true" />
              </Link>
            </div>
          </div>

          <figure className={styles.productFrame}>
            <figcaption className={styles.visuallyHidden}>
              Representative MUTX operator overview showing an intervention queue and active runs.
            </figcaption>
            <div className={styles.frameBar} aria-hidden="true">
              <span>MUTX / Operator</span>
              <span>Workspace: production</span>
              <span className={styles.frameLive}>Control plane healthy</span>
            </div>
            <div className={styles.frameBody} aria-hidden="true">
              <div className={styles.previewNav}>
                <strong>MX</strong>
                <span className={styles.previewNavActive}>Overview</span>
                <span>Runs</span>
                <span>Agents</span>
                <span>Approvals</span>
                <span>Audit</span>
                <i />
                <small>prod / eu-west</small>
              </div>
              <div className={styles.previewMain}>
                <header className={styles.previewHeading}>
                  <div>
                    <span>Tuesday · 09:43 UTC</span>
                    <strong>Operator overview</strong>
                  </div>
                  <p><i /> 12 agents reporting</p>
                </header>

                <div className={styles.previewMetrics}>
                  <div><span>Fleet</span><strong>12 / 12</strong><small>healthy</small></div>
                  <div><span>Active runs</span><strong>03</strong><small>1 held</small></div>
                  <div><span>Open alerts</span><strong>02</strong><small>0 critical</small></div>
                  <div><span>Budget</span><strong>72%</strong><small>remaining</small></div>
                </div>

                <div className={styles.interventionRow}>
                  <span className={styles.interventionCount}>01</span>
                  <div>
                    <small>Intervention required</small>
                    <strong>Production promotion is waiting at a policy boundary.</strong>
                  </div>
                  <span>Review approval →</span>
                </div>

                <div className={styles.runTable}>
                  <div className={styles.runTableHead}>
                    <span>Active record</span><span>Task</span><span>State</span>
                  </div>
                  {PREVIEW_RUNS.map((run) => (
                    <div className={styles.runRow} key={run.id}>
                      <code>{run.id}</code>
                      <span>{run.task}</span>
                      <strong data-tone={run.tone}>{run.status}</strong>
                    </div>
                  ))}
                </div>

                <div className={styles.previewFooter}>
                  <span>Latest receipt · rcpt_7F2A91</span>
                  <span>Governed receipt linked</span>
                </div>
              </div>
            </div>
          </figure>
        </div>
      </section>

      <section className={styles.boundarySection} aria-labelledby="boundary-title">
        <header className={styles.boundaryHeader}>
          <p className={styles.sectionIndex}>03 / At the boundary</p>
          <h2 id="boundary-title">Helpful is not the same as permitted.</h2>
          <p>
            When a registered MUTX runtime tool reaches a DENY or DEFER verdict, the
            handler stays uncalled and the decision keeps its action context.
          </p>
        </header>

        <div className={styles.boundarySequence}>
          <div className={styles.requestBlock}>
            <span>09:18:20 / Request</span>
            <blockquote>“Share the quarterly report with the team.”</blockquote>
          </div>
          <div className={styles.attemptBlock}>
            <span>09:18:23 / Proposed action</span>
            <code>share.external</code>
            <p>Destination includes 23 external contractors.</p>
          </div>
          <div className={styles.holdBlock}>
            <span>Policy / data-boundary</span>
            <strong>Held for review</strong>
            <p>No file moved. Scope and destination preserved for the operator.</p>
          </div>
        </div>

        <div className={styles.boundaryFooter}>
          <p><span>Outcome</span> The governed handler stays stopped. Its review context remains.</p>
          <div className={styles.textLinksDark}>
            <Link href="/ai-agent-guardrails">Explore guardrails <ArrowRight className="rtl-directional-icon" aria-hidden="true" /></Link>
            <Link href="/ai-agent-approvals">Approval workflows <ArrowUpRight aria-hidden="true" /></Link>
          </div>
        </div>
      </section>

      <section className={styles.setupSection} aria-labelledby="setup-title">
        <header className={styles.sectionIntro}>
          <p className={styles.sectionIndex}>04 / Start operating</p>
          <div>
            <h2 id="setup-title">From setup to first record.</h2>
            <p>
              Check the Mac release lane or start with the API, then instrument the
              runtime path whose evidence you need to inspect.
            </p>
          </div>
        </header>

        <div className={styles.setupGrid}>
          <ol className={styles.setupSteps}>
            {SETUP_STEPS.map((step) => (
              <li key={step.number}>
                <span>{step.number}</span>
                <small>{step.label}</small>
                {step.label === 'Connect' ? <code>{step.value}</code> : <strong>{step.value}</strong>}
              </li>
            ))}
          </ol>

          <aside className={styles.sourcePanel} aria-label="MUTX ecosystem links">
            <p>Built in the open</p>
            <h3>Inspect the source. Keep control of the plane.</h3>
            <p>
              MUTX is source-available, with public docs and a control plane you can
              run against your own infrastructure.
            </p>
            <a href="https://github.com/mutx-dev/mutx-dev" target="_blank" rel="noopener noreferrer">
              View GitHub <ArrowUpRight aria-hidden="true" />
              <span className={styles.visuallyHidden}> (opens in a new tab)</span>
            </a>
            <a href="https://pico.mutx.dev" target="_blank" rel="noopener noreferrer">
              Pico setup companion <ArrowUpRight aria-hidden="true" />
              <span className={styles.visuallyHidden}> (opens in a new tab)</span>
            </a>
          </aside>
        </div>
      </section>

      <section className={styles.finalSection} aria-labelledby="final-title">
        <p className={styles.sectionIndex}>05 / Your next run</p>
        <div className={styles.finalGrid}>
          <h2 id="final-title">Instrument the run.<br />Keep the evidence.</h2>
          <div>
            <p>Check macOS availability or start with the control-plane documentation.</p>
            <div className={styles.finalActions}>
              <Link href="/download">
                Get MUTX <ArrowRight className="rtl-directional-icon" aria-hidden="true" />
              </Link>
              <Link href="/docs">
                Read the docs <ArrowUpRight aria-hidden="true" />
              </Link>
            </div>
          </div>
        </div>
      </section>
    </main>
  )
}
