import type { ReactNode } from 'react'

import styles from './SystemState.module.css'

type SystemStateProps = {
  code: string
  eyebrow: string
  title: string
  description: string
  detail?: string
  actions?: ReactNode
  compact?: boolean
  live?: boolean
  role?: 'alert' | 'status'
}

export function SystemState({
  code,
  eyebrow,
  title,
  description,
  detail,
  actions,
  compact = false,
  live = false,
  role,
}: SystemStateProps) {
  const Tag = compact ? 'section' : 'main'

  return (
    <Tag
      id={compact ? undefined : 'main-content'}
      tabIndex={compact ? undefined : -1}
      className={`${styles.page} ${compact ? styles.compact : ''}`}
      role={role}
      aria-live={role === 'alert' ? 'assertive' : role === 'status' ? 'polite' : undefined}
    >
      <div className={styles.frame}>
        <header className={styles.topline}>
          <span>MUTX / system record</span>
          <span>{code}</span>
        </header>

        <div className={styles.body}>
          <div className={styles.copy}>
            <p className={styles.eyebrow}>{eyebrow}</p>
            <h1>{title}</h1>
            <p className={styles.description}>{description}</p>
            {actions ? <div className={styles.actions}>{actions}</div> : null}
          </div>

          <div className={styles.rail} aria-hidden="true">
            <span />
            <i className={live ? styles.live : ''} />
            <span />
            <span />
          </div>

          <aside className={styles.receipt}>
            <p>Record status</p>
            <strong>{live ? 'Resolving route' : code}</strong>
            <span>{detail || 'The system kept enough context to choose a safe next step.'}</span>
          </aside>
        </div>
      </div>
    </Tag>
  )
}
