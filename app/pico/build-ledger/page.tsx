import type { Metadata } from 'next'
import { getLocale, getTranslations } from 'next-intl/server'

import s from './page.module.css'
import {
  PicoBuildLedgerLink,
  PicoBuildLedgerReturn,
} from '@/components/pico/PicoBuildLedgerReturn'
import { PICO_LIVE_BUILD_LEDGER } from '@/lib/pico/liveBuildLedger'

const ledger = PICO_LIVE_BUILD_LEDGER

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations('pico.buildLedger.meta')

  return {
    title: t('title'),
    description: t('description'),
    alternates: {
      canonical: 'https://pico.mutx.dev/build-ledger',
    },
    robots: {
      index: false,
      follow: false,
      nocache: true,
    },
  }
}

function formatDate(value: string | null | undefined, locale: string, unavailable: string) {
  if (!value) return unavailable

  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return unavailable

  return new Intl.DateTimeFormat(locale, {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    timeZone: 'UTC',
  }).format(parsed)
}

function formatNumber(value: number | null | undefined, locale: string) {
  return typeof value === 'number' ? new Intl.NumberFormat(locale).format(value) : '—'
}

export default async function PicoBuildLedgerPage() {
  const locale = await getLocale()
  const t = await getTranslations('pico.buildLedger')
  const contentT = await getTranslations('pico.content')
  const unavailable = t('snapshotUnavailable')

  return (
    <div className={s.root} data-testid="pico-build-ledger">
      <header className={s.header}>
        <PicoBuildLedgerLink href="/" className={s.brand}>
          PicoMUTX <span>{t('brandSuffix')}</span>
        </PicoBuildLedgerLink>
        <nav aria-label={t('navigationLabel')} className={s.nav}>
          <PicoBuildLedgerLink href="/academy">{t('navigation.academy')}</PicoBuildLedgerLink>
          <PicoBuildLedgerLink href="/onboarding">{t('navigation.onboarding')}</PicoBuildLedgerLink>
        </nav>
      </header>

      <main id="main-content" className={s.main}>
        <section className={s.hero} aria-labelledby="ledger-title">
          <div className={s.heroCopy}>
            <p className={s.kicker}>{t('hero.sourceStatus', { date: formatDate(ledger.refreshedAt, locale, unavailable) })}</p>
            <h1 id="ledger-title" className={s.title}>
              {t('hero.title')}
            </h1>
            <p className={s.subtitle}>{t('hero.subtitle')}</p>
            <div className={s.actions}>
              <PicoBuildLedgerReturn className={s.primaryLink} label={t('actions.continueOnboarding')} />
              <PicoBuildLedgerLink href="/academy" className={s.secondaryLink}>
                {t('actions.inspectAcademy')}
              </PicoBuildLedgerLink>
            </div>
          </div>

          <aside className={s.heroAside} aria-label={t('remote.postureLabel')}>
            <p className={s.asideIndex}>{t('remote.kicker')}</p>
            <h2>{t('remote.title')}</h2>
            <p>{t('remote.body')}</p>
            <ol>
              {ledger.remoteAccess.decisionDefaults.map((decision, index) => (
                <li key={decision}>{t(`remote.defaults.${index}`)}</li>
              ))}
            </ol>
            {ledger.remoteAccess.docsUrl ? (
              <a href={ledger.remoteAccess.docsUrl}>
                {t('remote.readSource')} <span aria-hidden="true">↗</span>
              </a>
            ) : (
              <span className={s.disabledSource} aria-disabled="true">
                {t('remote.readSource')} · {unavailable}
              </span>
            )}
          </aside>
        </section>

        <section className={s.metrics} aria-label={t('metrics.label')}>
          <article>
            <strong>{ledger.packDocs.length}</strong>
            <span>{t('metrics.packDocs')}</span>
          </article>
          <article>
            <strong>{ledger.academy.lessons.length}</strong>
            <span>{t('metrics.lessons')}</span>
          </article>
          <article>
            <strong>{ledger.academy.totalMinutes}</strong>
            <span>{t('metrics.minutes')}</span>
          </article>
          <article>
            <strong>{ledger.stacks.length}</strong>
            <span>{t('metrics.stacks')}</span>
          </article>
        </section>

        <section id="stack-notes" className={s.section} data-testid="pico-stack-notes">
          <div className={s.sectionHeading}>
            <div>
              <p className={s.kicker}>{t('stacks.kicker')}</p>
              <h2>{t('stacks.title')}</h2>
            </div>
            <p>
              {t('stacks.body')}
            </p>
          </div>

          <div className={s.stackGrid}>
            {ledger.stacks.map((stack) => (
              <article key={stack.id} className={s.stackCard}>
                <div className={s.stackTopline}>
                  <span>{stack.name}</span>
                  <span>{stack.live?.latestRef?.label ?? t('stacks.repositorySnapshot')}</span>
                </div>
                <h3>{t(`stacks.items.${stack.id}.strength`)}</h3>
                <p>{t(`stacks.items.${stack.id}.profile`)}</p>
                <div className={s.snapshot}>
                  <span>{t('stacks.stars', { count: formatNumber(stack.live?.stars, locale) })}</span>
                  <span>{t('stacks.openIssues', { count: formatNumber(stack.live?.openIssues, locale) })}</span>
                  <span>{formatDate(stack.live?.pushedAt, locale, unavailable)}</span>
                </div>
                <p className={s.installNote}>
                  <strong>{t('stacks.installNote')}</strong>
                  {t(`stacks.items.${stack.id}.installReality`)}
                </p>
                <div className={s.sourceLinks}>
                  {stack.repoUrl ? (
                    <a href={stack.repoUrl}>
                      {t('stacks.repository')} ↗
                    </a>
                  ) : null}
                  {stack.docsUrl ? (
                    <a href={stack.docsUrl}>
                      {t('stacks.officialDocs')} ↗
                    </a>
                  ) : null}
                  {stack.live?.latestRef?.url ? (
                    <a href={stack.live.latestRef.url}>
                      {t('stacks.snapshotRef')} ↗
                    </a>
                  ) : null}
                </div>
              </article>
            ))}
          </div>
        </section>

        <section id="academy-ledger" className={s.section}>
          <div className={s.sectionHeading}>
            <div>
              <p className={s.kicker}>{t('academy.kicker')}</p>
              <h2>{t('academy.title')}</h2>
            </div>
            <p>
              {t('academy.body')}
            </p>
          </div>

          <div className={s.trackStrip}>
            {ledger.academy.tracks.map((track, index) => (
              <article key={track.slug}>
                <span>{String(index + 1).padStart(2, '0')}</span>
                <h3>{contentT(`tracks.${track.slug}.title`)}</h3>
                <p>{contentT(`tracks.${track.slug}.outcome`)}</p>
                <small>{t('academy.lessonCount', { count: track.lessonCount })}</small>
              </article>
            ))}
          </div>

          <div className={s.lessonList}>
            {ledger.academy.lessons.map((lesson, index) => (
              <PicoBuildLedgerLink key={lesson.slug} href={`/academy/${lesson.slug}`} className={s.lessonRow}>
                <span className={s.lessonIndex}>{String(index + 1).padStart(2, '0')}</span>
                <span>
                  <strong>{contentT(`lessons.${lesson.slug}.title`)}</strong>
                  <small>{contentT(`lessons.${lesson.slug}.summary`)}</small>
                </span>
                <span className={s.lessonMeta}>
                  {t('academy.lessonMeta', { difficulty: t(`academy.difficulty.${lesson.difficulty}`), minutes: lesson.estimatedMinutes })}
                </span>
              </PicoBuildLedgerLink>
            ))}
          </div>
        </section>

        <section id="builder-pack" className={s.section}>
          <div className={s.sectionHeading}>
            <div>
              <p className={s.kicker}>{t('pack.kicker')}</p>
              <h2>{t('pack.title')}</h2>
            </div>
            <p>
              {t('pack.body')}
            </p>
          </div>

          <div className={s.docGrid}>
            {ledger.packDocs.map((document, index) => (
              <article key={document.id}>
                <span>{String(index + 1).padStart(2, '0')}</span>
                <strong>{document.filename}</strong>
                <small>{document.topics.map((topic) => t(`topics.${topic}`)).join(' / ')}</small>
              </article>
            ))}
          </div>
        </section>

        <section id="remote-access" className={s.remoteSection}>
          <div>
            <p className={s.kicker}>{t('access.kicker')}</p>
            <h2>{t('access.title')}</h2>
          </div>
          <p>
            {t('access.body')}
          </p>
          <div className={s.actions}>
            <PicoBuildLedgerReturn className={s.primaryLink} label={t('actions.continueOnboarding')} />
            {ledger.remoteAccess.docsUrl ? (
              <a href={ledger.remoteAccess.docsUrl} className={s.secondaryLink}>
                {t('access.verifySource')} ↗
              </a>
            ) : (
              <span className={s.secondaryLink} aria-disabled="true">
                {t('access.verifySource')} · {unavailable}
              </span>
            )}
          </div>
        </section>
      </main>

      <footer className={s.footer}>
        <span>{t('footer.generated', { date: formatDate(ledger.generatedAt, locale, unavailable) })}</span>
        <span>{t('footer.sourceGrounded')}</span>
      </footer>
    </div>
  )
}
