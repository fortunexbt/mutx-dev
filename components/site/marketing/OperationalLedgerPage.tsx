import Link from 'next/link'
import type { CSSProperties } from 'react'

import { PublicFooter } from '@/components/site/PublicFooter'
import { PublicNav } from '@/components/site/PublicNav'
import { PublicSurface } from '@/components/site/PublicSurface'

import styles from './OperationalLedgerPage.module.css'
import {
  buildOperationalStoryStructuredData,
  type OperationalStory,
  type OperationalStoryAction,
  type OperationalStoryItem,
} from './operationalStories'

const workflowStates = ['DEFINED', 'ENFORCED', 'RECORDED', 'REVIEWABLE'] as const

type ArtifactTone = 'live' | 'muted' | 'signal' | 'trace'

type StoryArtifactConfig = {
  readonly caption: string
  readonly kind: string
  readonly metric: string
  readonly metricLabel: string
  readonly rows: readonly {
    readonly detail: string
    readonly label: string
    readonly level: number
    readonly tone: ArtifactTone
  }[]
  readonly stamp: string
}

const STORY_ARTIFACTS = {
  '/ai-agent-approvals': {
    kind: 'gate',
    caption: 'Approval gate / live decision envelope',
    metric: '01',
    metricLabel: 'operator decision pending',
    stamp: 'AUTH ROUTE / P1',
    rows: [
      { label: 'Scope match', detail: 'prod.release', level: 100, tone: 'live' },
      { label: 'Policy threshold', detail: 'human required', level: 86, tone: 'signal' },
      { label: 'Operator route', detail: 'on-call / platform', level: 68, tone: 'trace' },
      { label: 'Execution', detail: 'held at boundary', level: 6, tone: 'muted' },
    ],
  },
  '/ai-agent-audit-logs': {
    kind: 'chain',
    caption: 'Evidence chain / sealed execution record',
    metric: '4/4',
    metricLabel: 'hash links verified',
    stamp: 'EXPORT / SOC2',
    rows: [
      { label: 'Intent', detail: 'b91e…0a4c', level: 100, tone: 'trace' },
      { label: 'Policy', detail: '294a…b910', level: 92, tone: 'signal' },
      { label: 'Operator', detail: 'a014…71df', level: 84, tone: 'live' },
      { label: 'Outcome', detail: 'e772…cc03', level: 76, tone: 'trace' },
    ],
  },
  '/ai-agent-control-plane': {
    kind: 'topology',
    caption: 'Control plane / runtime visibility map',
    metric: '12',
    metricLabel: 'agents reporting',
    stamp: 'PLANE / HEALTHY',
    rows: [
      { label: 'Ingress', detail: '3 active channels', level: 92, tone: 'trace' },
      { label: 'Policy plane', detail: '24 rules loaded', level: 78, tone: 'signal' },
      { label: 'Runtime fleet', detail: '12 / 12 online', level: 100, tone: 'live' },
      { label: 'Evidence sink', detail: 'continuity 100%', level: 100, tone: 'trace' },
    ],
  },
  '/ai-agent-cost': {
    kind: 'spend',
    caption: 'Run economics / attributed spend profile',
    metric: '$18.42',
    metricLabel: 'run cost attributed',
    stamp: 'BUDGET / 72% LEFT',
    rows: [
      { label: 'Model', detail: '$12.08', level: 66, tone: 'signal' },
      { label: 'Tools', detail: '$4.70', level: 26, tone: 'trace' },
      { label: 'Storage', detail: '$1.64', level: 9, tone: 'muted' },
      { label: 'Unattributed', detail: '$0.00', level: 2, tone: 'live' },
    ],
  },
  '/ai-agent-deployment': {
    kind: 'rollout',
    caption: 'Deployment wave / progressive health proof',
    metric: '3/3',
    metricLabel: 'targets healthy',
    stamp: 'ROLLBACK / ARMED',
    rows: [
      { label: 'Canary', detail: 'healthy · 8m', level: 100, tone: 'live' },
      { label: 'Wave 01', detail: 'healthy · 5m', level: 100, tone: 'live' },
      { label: 'Wave 02', detail: 'healthy · 2m', level: 100, tone: 'live' },
      { label: 'Previous', detail: 'retained · 1.3.9', level: 42, tone: 'muted' },
    ],
  },
  '/ai-agent-governance': {
    kind: 'policy',
    caption: 'Policy evaluation / effective ruleset',
    metric: 'v24',
    metricLabel: 'policy bundle active',
    stamp: 'SIGNED / 09:42 UTC',
    rows: [
      { label: 'Identity', detail: 'role matched', level: 100, tone: 'live' },
      { label: 'Environment', detail: 'production', level: 84, tone: 'trace' },
      { label: 'Data scope', detail: 'internal only', level: 68, tone: 'signal' },
      { label: 'Decision', detail: 'approval required', level: 48, tone: 'signal' },
    ],
  },
  '/ai-agent-guardrails': {
    kind: 'boundary',
    caption: 'Boundary check / proposed action envelope',
    metric: '0',
    metricLabel: 'prohibited writes executed',
    stamp: 'BOUNDARY / HELD',
    rows: [
      { label: 'Requested scope', detail: 'team.internal', level: 58, tone: 'trace' },
      { label: 'Proposed scope', detail: '+23 external', level: 94, tone: 'signal' },
      { label: 'Allowed scope', detail: 'internal only', level: 58, tone: 'live' },
      { label: 'Action state', detail: 'not executed', level: 4, tone: 'muted' },
    ],
  },
  '/ai-agent-infrastructure': {
    kind: 'topology',
    caption: 'Runtime topology / resolved infrastructure',
    metric: '03',
    metricLabel: 'execution zones visible',
    stamp: 'EU-WEST / ONLINE',
    rows: [
      { label: 'Control', detail: 'mutx-core-01', level: 88, tone: 'signal' },
      { label: 'Runtime', detail: '12 workers', level: 100, tone: 'live' },
      { label: 'Telemetry', detail: 'OTLP connected', level: 92, tone: 'trace' },
      { label: 'Evidence', detail: 'object lock on', level: 76, tone: 'muted' },
    ],
  },
  '/ai-agent-monitoring': {
    kind: 'trace',
    caption: 'Trace waterfall / one complete tool path',
    metric: '1.24s',
    metricLabel: 'end-to-end duration',
    stamp: 'TRACE / 7F2A91',
    rows: [
      { label: 'Plan', detail: '118ms', level: 18, tone: 'trace' },
      { label: 'Policy', detail: '76ms', level: 10, tone: 'signal' },
      { label: 'Tool call', detail: '814ms', level: 72, tone: 'live' },
      { label: 'Receipt', detail: '232ms', level: 28, tone: 'trace' },
    ],
  },
  '/ai-agent-reliability': {
    kind: 'health',
    caption: 'Readiness envelope / failure containment',
    metric: '99.98%',
    metricLabel: 'readiness window',
    stamp: 'SLO / WITHIN BUDGET',
    rows: [
      { label: 'Runtime', detail: 'healthy', level: 100, tone: 'live' },
      { label: 'Dependencies', detail: '8 / 8 ready', level: 100, tone: 'live' },
      { label: 'Retry budget', detail: '91% remains', level: 91, tone: 'trace' },
      { label: 'Open circuit', detail: 'none', level: 3, tone: 'muted' },
    ],
  },
} as const satisfies Record<string, StoryArtifactConfig>

function StoryArtifact({ story }: { story: OperationalStory }) {
  const config = STORY_ARTIFACTS[story.path as keyof typeof STORY_ARTIFACTS]
    ?? STORY_ARTIFACTS['/ai-agent-control-plane']

  return (
    <figure className={styles.storyArtifact} data-kind={config.kind}>
      <figcaption className={styles.artifactCaption}>
        <span>{config.caption}</span>
        <strong>SAMPLE / {config.stamp}</strong>
      </figcaption>
      <div className={styles.artifactMetric}>
        <strong>{config.metric}</strong>
        <span>{config.metricLabel}</span>
      </div>
      <ol className={styles.artifactRows}>
        {config.rows.map((row) => (
          <li key={row.label} data-tone={row.tone}>
            <div className={styles.artifactRowCopy}>
              <span>{row.label}</span>
              <code>{row.detail}</code>
            </div>
            <span className={styles.artifactTrack} aria-hidden="true">
              <i
                style={{ '--artifact-level': `${row.level}%` } as CSSProperties}
              />
            </span>
          </li>
        ))}
      </ol>
    </figure>
  )
}

function StoryAction({ action, primary = false }: {
  action: OperationalStoryAction
  primary?: boolean
}) {
  const className = primary ? styles.primaryAction : styles.secondaryAction

  if (action.href.startsWith('http')) {
    return (
      <a href={action.href} className={className} target="_blank" rel="noopener noreferrer">
        {action.label}
        <span aria-hidden="true">↗</span>
        <span className={styles.srOnly}> (opens in a new tab)</span>
      </a>
    )
  }

  return (
    <Link href={action.href} className={className}>
      {action.label}
      <span aria-hidden="true">→</span>
    </Link>
  )
}

function EvidenceTitle({ item }: { item: OperationalStoryItem }) {
  if (!item.href) {
    return <h3 className={styles.evidenceTitle}>{item.title}</h3>
  }

  return (
    <h3 className={styles.evidenceTitle}>
      <Link href={item.href}>
        {item.title}
        <span aria-hidden="true">↗</span>
      </Link>
    </h3>
  )
}

export function OperationalLedgerPage({ story }: { story: OperationalStory }) {
  const structuredData = buildOperationalStoryStructuredData(story)
  const heroTitleId = `story-${story.index}-title`
  const workflowTitleId = `story-${story.index}-workflow`
  const evidenceTitleId = `story-${story.index}-evidence`

  return (
    <PublicSurface className={styles.surface}>
      <PublicNav />
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(structuredData) }}
      />
      <main id="main-content" className={styles.main}>
        <section className={styles.hero} aria-labelledby={heroTitleId}>
          <div className={`${styles.shell} ${styles.heroGrid}`}>
            <div className={styles.heroCopy}>
              <div className={styles.heroFolio} aria-label={`Product story ${story.index} of 10`}>
                <span>Operational ledger</span>
                <span>{story.index} / 10</span>
              </div>
              <p className={styles.eyebrow}>{story.hero.eyebrow}</p>
              <h1 id={heroTitleId} className={styles.heroTitle}>
                {story.hero.title}
              </h1>
              <p className={styles.heroBody}>{story.hero.body}</p>
              <div className={styles.heroActions}>
                <StoryAction action={story.hero.actions[0]} primary />
                <StoryAction action={story.hero.actions[1]} />
              </div>
            </div>

            <aside className={styles.recorder} aria-label={`${story.hero.eyebrow} illustrative flight recorder`}>
              <div className={styles.recorderMast}>
                <div>
                  <p>Illustrative flight recorder</p>
                  <strong>{story.record.id}</strong>
                </div>
                <span className={styles.liveState}>
                  <span aria-hidden="true" /> Product example
                </span>
              </div>

              <dl className={styles.recordFacts}>
                <div>
                  <dt>Operation</dt>
                  <dd>{story.record.operation}</dd>
                </div>
                <div>
                  <dt>Disposition</dt>
                  <dd>{story.record.status}</dd>
                </div>
              </dl>

              <StoryArtifact story={story} />

              <div className={styles.recorderFoot}>
                <span>Example integrity field</span>
                <strong>SHA-256 / SAMPLE</strong>
              </div>
            </aside>
          </div>
        </section>

        <section className={styles.workflow} aria-labelledby={workflowTitleId}>
          <div className={styles.shell}>
            <header className={styles.sectionHeader}>
              <p className={styles.sectionCode}>{story.workflow.eyebrow} / 01</p>
              <h2 id={workflowTitleId} className={styles.sectionTitle}>
                {story.workflow.title}
              </h2>
              <p className={styles.sectionBody}>{story.workflow.body}</p>
            </header>

            <div className={styles.ledger}>
              {story.workflow.items.map((item, index) => (
                <article key={item.title} className={styles.ledgerRow}>
                  <p className={styles.rowIndex}>{String(index + 1).padStart(2, '0')}</p>
                  <div className={styles.rowCopy}>
                    <h3>{item.title}</h3>
                    <p>{item.body}</p>
                  </div>
                  <p className={styles.rowState}>
                    <span aria-hidden="true" /> {workflowStates[index]}
                  </p>
                </article>
              ))}
            </div>
          </div>
        </section>

        <section className={styles.evidence} aria-labelledby={evidenceTitleId}>
          <div className={styles.shell}>
            <header className={styles.sectionHeader}>
              <p className={styles.sectionCode}>{story.evidence.eyebrow} / 02</p>
              <h2 id={evidenceTitleId} className={styles.sectionTitle}>
                {story.evidence.title}
              </h2>
              <p className={styles.sectionBody}>{story.evidence.body}</p>
            </header>

            <div className={styles.evidenceList}>
              {story.evidence.items.map((item, index) => (
                <article key={item.title} className={styles.evidenceRow}>
                  <p className={styles.evidenceCode}>E-{String(index + 1).padStart(3, '0')}</p>
                  <EvidenceTitle item={item} />
                  <p className={styles.evidenceBody}>{item.body}</p>
                  <p className={styles.attachedState}>
                    <span aria-hidden="true">●</span> Attached
                  </p>
                </article>
              ))}
            </div>
          </div>
        </section>

        <section className={styles.cta} aria-labelledby={`story-${story.index}-cta`}>
          <div className={`${styles.shell} ${styles.ctaGrid}`}>
            <p className={styles.ctaCode}>{story.cta.eyebrow} / END OF RECORD</p>
            <h2 id={`story-${story.index}-cta`} className={styles.ctaTitle}>
              {story.cta.title}
            </h2>
            <div className={styles.ctaAside}>
              <p>{story.cta.body}</p>
              <div className={styles.ctaActions}>
                <StoryAction action={story.cta.actions[0]} primary />
                <StoryAction action={story.cta.actions[1]} />
              </div>
            </div>
          </div>
        </section>
      </main>
      <PublicFooter showCallout={false} />
    </PublicSurface>
  )
}
