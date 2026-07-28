'use client'

import Link from 'next/link'
import { useTranslations } from 'next-intl'
import { usePathname } from 'next/navigation'
import { useEffect, useMemo, useState } from 'react'

import { PicoContactForm } from '@/components/pico/PicoContactForm'
import {
  classifyPicoSessionRuntime,
  PicoSessionBanner,
} from '@/components/pico/PicoSessionBanner'
import { PicoShell } from '@/components/pico/PicoShell'
import { PicoSignalDiagram } from '@/components/pico/PicoSignalDiagram'
import { PicoSurfaceCompass } from '@/components/pico/PicoSurfaceCompass'
import {
  picoClasses,
  picoEmber,
  picoInset,
  picoPanel,
  picoSoft,
} from '@/components/pico/picoTheme'
import { usePicoLessonWorkspace } from '@/components/pico/usePicoLessonWorkspace'
import { usePicoProgress } from '@/components/pico/usePicoProgress'
import { usePicoSession } from '@/components/pico/usePicoSession'
import { usePicoSetupState } from '@/components/pico/usePicoSetupState'
import { localizePicoLesson } from '@/lib/pico/content'
import { usePicoHref } from '@/lib/pico/navigation'
import { cn } from '@/lib/utils'

export function PicoSupportPageClient() {
  const pathname = usePathname()
  const t = useTranslations('pico.supportPage')
  const contentT = useTranslations('pico.content')
  const session = usePicoSession()
  const setup = usePicoSetupState(session.status === 'authenticated')
  const {
    ready: progressReady,
    actions,
    progress,
    derived,
    syncState,
  } = usePicoProgress(session.status === 'authenticated')
  const toHref = usePicoHref()
  const [interactiveReady, setInteractiveReady] = useState(false)
  const [formOpen, setFormOpen] = useState(false)
  const [interest, setInterest] = useState<string | undefined>()
  const [copied, setCopied] = useState(false)
  const supportOptions = ([0, 1] as const).map((index) => ({
    id: index === 0 ? 'fixing-existing' : 'other',
    title: t(`desk.lanes.${index}.title`),
    body: t(`desk.lanes.${index}.body`),
    cta: t(`desk.lanes.${index}.cta`),
  }))
  const supportStandards = ([0, 1, 2] as const).map((index) => ({
    label: t(`standards.cards.${index}.label`),
    title: t(`standards.cards.${index}.title`),
    body: t(`standards.cards.${index}.body`),
  }))
  const supportInterestOptions = [
    { value: 'fixing-existing', label: t('contact.interest.lessonBlocker') },
    { value: 'runtime-hosting', label: t('contact.interest.runtimeMismatch') },
    { value: 'hosted-session', label: t('contact.interest.sessionMismatch') },
    { value: 'billing-or-plan', label: t('contact.interest.billingPlan') },
    { value: 'other', label: t('contact.interest.officeHours') },
  ]
  const supportContactCopy = {
    title: t('contact.title'),
    subtitle: t('contact.subtitle'),
    interestLabel: t('contact.interestLabel'),
    messageLabel: t('contact.messageLabel'),
    messageOptional: t('contact.messageOptional'),
    messagePlaceholder: t('contact.messagePlaceholder'),
    submit: t('contact.submit'),
    submitting: t('contact.submitting'),
    disclaimer: t('contact.disclaimer'),
    successTitle: t('contact.successTitle'),
    successBody: t('contact.successBody'),
    successBack: t('contact.successBack'),
  }
  const recoveryLesson = derived.nextLesson
    ? localizePicoLesson(derived.nextLesson, contentT)
    : undefined
  const recoveryWorkspace = usePicoLessonWorkspace(recoveryLesson?.slug ?? 'support', recoveryLesson?.steps.length ?? 0, {
    progress,
    persistRemote: recoveryLesson
      ? (lessonSlug, workspace) => actions.setLessonWorkspace(lessonSlug, workspace)
      : undefined,
  })
  const recoveryFocusedStep =
    recoveryLesson && recoveryWorkspace.workspace.activeStepIndex >= 0
      ? recoveryLesson.steps[recoveryWorkspace.workspace.activeStepIndex]?.title ?? t('shared.stepNotSet')
      : t('shared.stepNotSet')
  const runtimeSignal =
    session.status !== 'authenticated'
      ? t('shared.runtime.localOnly')
      : setup.loading
        ? t('shared.runtime.checking')
        : setup.runtime?.status ?? t('shared.runtime.notAttached')
  const runtimeBannerState = classifyPicoSessionRuntime({
    loading: setup.loading,
    error: setup.error,
    status: setup.runtime?.status,
    stale: setup.runtime?.stale,
  })
  const packetState = copied
    ? t('shared.packetState.copied')
    : recoveryWorkspace.workspace.evidence.trim()
      ? t('shared.packetState.proofAttached')
      : session.status === 'authenticated'
        ? t('shared.packetState.contextReady')
        : t('shared.packetState.needsProof')
  const returnRouteLabel = recoveryLesson?.title ?? t('shared.returnAcademy')
  const packetPreview = [
    `${t('packet.preview.route')} ${pathname}`,
    `${t('packet.preview.runtime')} ${runtimeSignal}`,
    `${t('packet.preview.return')} ${returnRouteLabel}`,
    `${t('packet.preview.packet')} ${packetState}`,
  ].join('\n')
  const supportControlsReady = interactiveReady && progressReady && recoveryWorkspace.ready
  const disabledControlClassName = !supportControlsReady
    ? 'disabled:cursor-not-allowed disabled:opacity-60'
    : undefined

  useEffect(() => {
    setInteractiveReady(true)
  }, [])

  useEffect(() => {
    if (progress.platform.activeSurface !== 'support') {
      actions.setPlatform({ activeSurface: 'support' })
    }
  }, [actions, progress.platform.activeSurface])

  const diagnosticPacket = useMemo(
    () =>
      [
        t('packet.diagnostic.title'),
        `${t('packet.diagnostic.route')} ${pathname}`,
        `${t('packet.diagnostic.hostedSession')} ${session.status}`,
        `${t('packet.diagnostic.hostedPlan')} ${session.status === 'authenticated' ? session.user.plan ?? t('packet.diagnostic.values.unknown') : t('packet.diagnostic.values.na')}`,
        `${t('packet.diagnostic.selectedTrack')} ${progress.selectedTrack ?? t('packet.diagnostic.values.none')}`,
        `${t('packet.diagnostic.completedLessons')} ${progress.completedLessons.length}`,
        `${t('packet.diagnostic.nextLesson')} ${recoveryLesson?.title ?? t('packet.diagnostic.values.none')}`,
        `${t('packet.diagnostic.recoveryWorkspace')} ${recoveryWorkspace.completedStepCount}/${recoveryLesson?.steps.length ?? 0}`,
        `${t('packet.diagnostic.recoveryFocusedStep')} ${recoveryFocusedStep}`,
        `${t('packet.diagnostic.recoveryProof')} ${recoveryWorkspace.workspace.evidence.trim() ? t('packet.diagnostic.values.captured') : t('packet.diagnostic.values.missing')}`,
        `${t('packet.diagnostic.activeSurface')} ${progress.platform.activeSurface ?? t('packet.diagnostic.values.none')}`,
        `${t('packet.diagnostic.lastOpenedLesson')} ${progress.platform.lastOpenedLessonSlug ?? t('packet.diagnostic.values.none')}`,
        `${t('packet.diagnostic.railCollapsed')} ${progress.platform.railCollapsed ? t('packet.diagnostic.values.yes') : t('packet.diagnostic.values.no')}`,
        `${t('packet.diagnostic.helpLaneOpen')} ${progress.platform.helpLaneOpen ? t('packet.diagnostic.values.yes') : t('packet.diagnostic.values.no')}`,
        `${t('packet.diagnostic.supportRequestsSent')} ${progress.supportRequests}`,
        `${t('packet.diagnostic.tutorQuestionsAsked')} ${progress.tutorQuestions}`,
        `${t('packet.diagnostic.hostedOnboardingStatus')} ${setup.onboarding?.status ?? t('packet.diagnostic.values.notAvailable')}`,
        `${t('packet.diagnostic.hostedOnboardingStep')} ${setup.onboarding?.current_step ?? t('packet.diagnostic.values.notAvailable')}`,
        `${t('packet.diagnostic.hostedWorkspace')} ${setup.onboarding?.workspace ?? t('packet.diagnostic.values.notAvailable')}`,
        `${t('packet.diagnostic.runtimeStatus')} ${setup.runtime?.status ?? t('packet.diagnostic.values.notAvailable')}`,
        `${t('packet.diagnostic.gatewayUrl')} ${setup.runtime?.gateway_url ?? t('packet.diagnostic.values.notAvailable')}`,
        `${t('packet.diagnostic.runtimeBindings')} ${setup.runtime?.binding_count ?? 0}`,
      ].join('\n'),
    [
      pathname,
      progress.completedLessons.length,
      progress.selectedTrack,
      progress.supportRequests,
      progress.tutorQuestions,
      progress.platform.activeSurface,
      progress.platform.helpLaneOpen,
      progress.platform.lastOpenedLessonSlug,
      progress.platform.railCollapsed,
      recoveryFocusedStep,
      recoveryLesson?.title,
      recoveryLesson?.steps.length,
      recoveryWorkspace.completedStepCount,
      recoveryWorkspace.workspace.evidence,
      session.status,
      setup.onboarding?.current_step,
      setup.onboarding?.status,
      setup.onboarding?.workspace,
      setup.runtime?.binding_count,
      setup.runtime?.gateway_url,
      setup.runtime?.status,
    ],
  )

  const defaultSupportMessage = `${diagnosticPacket}\n\n${t('packet.problemLabel')}\n`

  function openEscalation(defaultInterest: string) {
    if (!supportControlsReady) {
      return
    }

    setInterest(defaultInterest)
    setFormOpen(true)
  }

  async function copyDiagnosticPacket() {
    if (!supportControlsReady) {
      return
    }

    try {
      await navigator.clipboard.writeText(diagnosticPacket)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 2000)
    } catch {
      setCopied(false)
    }
  }

  return (
    <>
      <PicoContactForm
        open={formOpen}
        onClose={() => setFormOpen(false)}
        defaultInterest={interest}
        defaultMessage={defaultSupportMessage}
        source={interest === 'other' ? 'pico-office-hours' : 'pico-support'}
        onSuccess={() => actions.recordSupportRequest()}
        copy={supportContactCopy}
        interestOptions={supportInterestOptions}
      />
      <PicoShell
        eyebrow={t('shell.eyebrow')}
        title={t('shell.title')}
        description={t('shell.description')}
        heroContent={
          <div
            className="relative overflow-hidden border border-[color:var(--pico-border-hover)] bg-[color:var(--pico-bg-panel)] p-5 sm:p-6"
            data-testid="pico-support-hero-signal"
          >
            <div
              aria-hidden="true"
              className="pointer-events-none absolute inset-x-0 top-0 h-px bg-[color:var(--pico-accent)]"
            />
            <div
              aria-hidden="true"
              className="hidden"
            />
            <div
              aria-hidden="true"
              className="hidden"
            />
            <div className="relative grid gap-5 xl:grid-cols-[minmax(0,1fr),18rem]">
              <div className="grid gap-5">
                <div className="flex flex-wrap items-center gap-2">
                  <span className={picoClasses.chip}>{t('hero.badge')}</span>
                  <span className="inline-flex rounded-full border border-[color:var(--pico-border)] bg-[rgba(255,255,255,0.03)] px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-[color:var(--pico-text-secondary)]">
                    {formOpen ? t('hero.mode.open') : t('hero.mode.triage')}
                  </span>
                </div>
                <h2 className="font-[family:var(--font-site-display)] text-[clamp(1.9rem,4vw,2.9rem)] leading-[0.94] tracking-[-0.06em] text-[color:var(--pico-text)]">
                  {t('hero.title')}
                </h2>
                <p className="max-w-2xl text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                  {t('hero.body')}
                </p>

                <div className="grid gap-3 sm:grid-cols-3">
                  <div className={picoSoft('p-4')}>
                    <p className={picoClasses.label}>{t('hero.packetState.label')}</p>
                    <p className="mt-2 font-[family:var(--font-site-display)] text-3xl tracking-[-0.05em] text-[color:var(--pico-text)]">
                      {packetState}
                    </p>
                    <p className="mt-2 text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                      {copied ? t('hero.packetState.readyToPaste') : t('hero.packetState.routeAndEvidenceFirst')}
                    </p>
                  </div>

                  <div className={picoSoft('p-4')}>
                    <p className={picoClasses.label}>{t('hero.runtimeTruth.label')}</p>
                    <p className="mt-2 font-[family:var(--font-site-display)] text-3xl tracking-[-0.05em] text-[color:var(--pico-text)]">
                      {runtimeSignal}
                    </p>
                    <p className="mt-2 text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                      {setup.runtime?.gateway_url ? t('hero.runtimeTruth.gatewayAttached') : t('hero.runtimeTruth.attachSignal')}
                    </p>
                  </div>

                  <div className={picoSoft('p-4')}>
                    <p className={picoClasses.label}>{t('hero.returnLane.label')}</p>
                    <p className="mt-2 font-[family:var(--font-site-display)] text-3xl tracking-[-0.05em] text-[color:var(--pico-text)]">
                      {returnRouteLabel}
                    </p>
                    <p className="mt-2 text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                      {recoveryFocusedStep}
                    </p>
                  </div>
                </div>

                <div className={picoInset('grid gap-3 p-4 sm:grid-cols-[auto,minmax(0,1fr)] sm:items-center')}>
                  <div className="flex h-14 w-14 items-center justify-center rounded-[20px] border border-[rgba(var(--pico-accent-rgb),0.24)] bg-[linear-gradient(180deg,rgba(var(--pico-accent-rgb),0.18),rgba(7,13,8,0.5))] shadow-[0_18px_40px_rgba(var(--pico-accent-rgb),0.12)]">
                    <span className="h-3 w-3 rounded-full bg-[color:var(--pico-accent-bright)] shadow-[0_0_18px_rgba(var(--pico-accent-rgb),0.5)]" />
                  </div>
                  <div className="min-w-0">
                    <p className={picoClasses.label}>{t('hero.handoff.label')}</p>
                    <p className="mt-2 font-[family:var(--font-site-display)] text-2xl tracking-[-0.05em] text-[color:var(--pico-text)]">
                      {recoveryLesson ? t('shared.resumeLesson', { lessonTitle: recoveryLesson.title }) : t('hero.handoff.returnAcademy')}
                    </p>
                    <p className="mt-2 text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                      {recoveryLesson
                        ? t('shared.stepsClear', { completed: recoveryWorkspace.completedStepCount, total: recoveryLesson.steps.length })
                        : t('hero.handoff.sequenceFallback')}
                    </p>
                  </div>
                </div>
              </div>

              <div className={picoInset('grid gap-4 overflow-hidden border-[color:rgba(var(--pico-accent-rgb),0.24)] bg-[radial-gradient(circle_at_50%_20%,rgba(var(--pico-accent-rgb),0.16),rgba(6,11,7,0.94)_54%,rgba(3,5,3,0.98)_100%)] p-4')}>
                <PicoSignalDiagram
                  index="05"
                  label={t('standards.packetPosture.label')}
                  title={t('standards.packetPosture.label')}
                  caption={t('standards.packetPosture.body')}
                  compact
                />

                <div className={picoSoft('p-4')}>
                  <p className={picoClasses.label}>{t('hero.packetPreview.label')}</p>
                  <pre className="mt-3 whitespace-pre-wrap text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                    <code>{packetPreview}</code>
                  </pre>
                </div>
              </div>
            </div>
          </div>
        }
        railCollapsed={progress.platform.railCollapsed}
        helpLaneOpen={progress.platform.helpLaneOpen}
        onToggleRail={() =>
          actions.setPlatform({ railCollapsed: !progress.platform.railCollapsed })
        }
        onToggleHelpLane={() =>
          actions.setPlatform({ helpLaneOpen: !progress.platform.helpLaneOpen })
        }
        actions={
          <div className="grid gap-3 sm:flex sm:flex-wrap">
            <button
              type="button"
              onClick={() => openEscalation('fixing-existing')}
              disabled={!supportControlsReady}
              className={cn(picoClasses.primaryButton, disabledControlClassName)}
            >
              {t('actions.getHumanHelp')}
            </button>
            <button
              type="button"
              onClick={() => void copyDiagnosticPacket()}
              disabled={!supportControlsReady}
              className={cn(picoClasses.secondaryButton, disabledControlClassName)}
            >
              {copied ? t('actions.copiedPacket') : t('actions.copyPacket')}
            </button>
            <button
              type="button"
              onClick={() => openEscalation('other')}
              disabled={!supportControlsReady}
              className={cn(picoClasses.tertiaryButton, disabledControlClassName)}
            >
              {t('actions.requestOfficeHours')}
            </button>
          </div>
        }
      >
        <PicoSessionBanner
          session={session}
          nextPath={pathname}
          progressSyncState={syncState}
          runtimeSignal={{ label: runtimeSignal, state: runtimeBannerState }}
        />
        <PicoSurfaceCompass
          title={t('compass.title')}
          body={t('compass.body')}
          status={formOpen ? t('compass.status.open') : t('compass.status.standby')}
          aside={t('compass.aside')}
          items={[
            {
              href: recoveryLesson ? toHref(`/academy/${recoveryLesson.slug}`) : toHref('/academy'),
              label: recoveryLesson ? t('shared.resumeLesson', { lessonTitle: recoveryLesson.title }) : t('compass.academy.return'),
              caption: t('compass.academy.caption'),
              note: t('compass.academy.note'),
              tone: 'primary',
            },
            {
              href: toHref('/tutor'),
              label: t('compass.tutor.label'),
              caption: t('compass.tutor.caption'),
              note: t('compass.tutor.note'),
            },
            {
              href: toHref('/autopilot'),
              label: t('compass.autopilot.label'),
              caption: t('compass.autopilot.caption'),
              note: t('compass.autopilot.note'),
              tone: 'soft',
            },
          ]}
        />

        <section className={picoPanel('p-6 sm:p-7')} data-testid="pico-support-escalation-standards">
          <div className="grid gap-6 lg:grid-cols-[minmax(0,1.08fr),20rem]">
            <div>
              <div className="flex flex-wrap items-center justify-between gap-4">
                <div>
                  <p className={picoClasses.label}>{t('standards.label')}</p>
                  <h2 className="mt-3 font-[family:var(--font-site-display)] text-4xl tracking-[-0.06em] text-[color:var(--pico-text)]">
                    {t('standards.title')}
                  </h2>
                </div>
                <span className={picoClasses.chip}>{t('standards.chip')}</span>
              </div>

              <div className="mt-6 grid gap-4 xl:grid-cols-3">
                {supportStandards.map((item) => (
                  <article key={item.label} className={picoInset('flex h-full flex-col p-5')}>
                    <p className={picoClasses.label}>{item.label}</p>
                    <h3 className="mt-5 font-[family:var(--font-site-display)] text-3xl tracking-[-0.05em] text-[color:var(--pico-text)]">
                      {item.title}
                    </h3>
                    <p className="mt-4 text-sm leading-7 text-[color:var(--pico-text-secondary)]">
                      {item.body}
                    </p>
                  </article>
                ))}
              </div>
            </div>

            <div className="grid gap-4">
              <div className={picoEmber('p-5')}>
                <p className={picoClasses.label}>{t('standards.packetPosture.label')}</p>
                <p className="mt-3 text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                  {t('standards.packetPosture.body')}
                </p>
              </div>
              <PicoSignalDiagram
                index="05"
                label={t('standards.deskTone.label')}
                title={t('standards.deskTone.label')}
                caption={t('standards.deskTone.body')}
                compact
              />
              <div className={picoInset('p-5')}>
                <p className={picoClasses.label}>{t('standards.bestFirstMove.label')}</p>
                <p className="mt-3 text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                  {t('standards.bestFirstMove.body')}
                </p>
              </div>
            </div>
          </div>
        </section>

        <section className="grid gap-6 xl:grid-cols-[minmax(0,1.08fr),22rem]">
          <div className={picoPanel('overflow-hidden p-0')}>
            <div className="grid gap-0 border-b border-[color:var(--pico-border)] lg:grid-cols-[minmax(0,1fr),18rem]">
              <div className="p-6 sm:p-7">
                <p className={picoClasses.label}>{t('desk.label')}</p>
                <h2 className="mt-3 font-[family:var(--font-site-display)] text-4xl tracking-[-0.06em] text-[color:var(--pico-text)] sm:text-5xl">
                  {t('desk.title')}
                </h2>
                <p className="mt-4 max-w-3xl text-sm leading-7 text-[color:var(--pico-text-secondary)] sm:text-base">
                  {t('desk.body')}
                </p>

                <div className={picoEmber('mt-6 p-5')}>
                  <p className="font-medium text-[color:var(--pico-text)]">
                    {t('desk.callout.title')}
                  </p>
                  <p className="mt-2 text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                    {t('desk.callout.body')}
                  </p>
                </div>

                <div className="mt-6 grid gap-4 lg:grid-cols-2">
                  {supportOptions.map((option) => (
                    <article key={option.id} className={picoInset('grid gap-4 p-5')}>
                      <div>
                        <h3 className="font-[family:var(--font-site-display)] text-3xl tracking-[-0.05em] text-[color:var(--pico-text)]">
                          {option.title}
                        </h3>
                        <p className="mt-3 text-sm leading-6 text-[color:var(--pico-text-secondary)]">{option.body}</p>
                      </div>
                      <button
                        type="button"
                        onClick={() => openEscalation(option.id)}
                        disabled={!supportControlsReady}
                        className={cn(
                          option.id === 'fixing-existing' ? picoClasses.primaryButton : picoClasses.secondaryButton,
                          disabledControlClassName,
                        )}
                      >
                        {option.cta}
                      </button>
                    </article>
                  ))}
                </div>
              </div>

              <div className="border-t border-[color:var(--pico-border)] bg-[color:var(--pico-bg-surface)] p-6 lg:border-s lg:border-t-0">
                <p className={picoClasses.label}>{t('rail.label')}</p>
                <div className="mt-4 grid gap-3">
                  <div className={picoSoft('p-4')}>
                    <p className="text-sm text-[color:var(--pico-text-muted)]">{t('rail.supportRequests')}</p>
                    <p className="mt-1 text-2xl font-semibold text-[color:var(--pico-text)]">{progress.supportRequests}</p>
                  </div>
                <div className={picoSoft('p-4')}>
                  <p className="text-sm text-[color:var(--pico-text-muted)]">{t('rail.tutorQuestions')}</p>
                  <p className="mt-1 text-2xl font-semibold text-[color:var(--pico-text)]">{progress.tutorQuestions}</p>
                </div>
                <div className={picoSoft('p-4')}>
                  <p className="text-sm text-[color:var(--pico-text-muted)]">{t('rail.plan.label')}</p>
                  <p className="mt-1 text-lg font-medium text-[color:var(--pico-text)]">
                    {session.status === 'authenticated' ? session.user.plan ?? t('rail.plan.unknown') : t('rail.plan.signIn')}
                  </p>
                </div>
                <div className={picoSoft('p-4')}>
                  <p className="text-sm text-[color:var(--pico-text-muted)]">{t('rail.activeSurface.label')}</p>
                  <p className="mt-1 text-lg font-medium text-[color:var(--pico-text)]">
                    {progress.platform.activeSurface ?? t('rail.activeSurface.none')}
                  </p>
                </div>
              </div>

                <div className={picoInset('mt-4 p-4')}>
                  <p className={picoClasses.label}>{t('rail.tryTheseFirst')}</p>
                  <div className="mt-3 grid gap-2">
                    <Link href={toHref('/tutor')} className={picoClasses.secondaryButton}>
                      {t('rail.tryTutorFirst')}
                    </Link>
                    <Link
                      href={recoveryLesson ? toHref(`/academy/${recoveryLesson.slug}`) : toHref('/academy')}
                      className={picoClasses.tertiaryButton}
                    >
                      {recoveryLesson ? t('shared.openLesson', { lessonTitle: recoveryLesson.title }) : t('rail.returnAcademy')}
                    </Link>
                    <Link href={toHref('/autopilot')} className={picoClasses.tertiaryButton}>
                      {t('rail.openAutopilot')}
                    </Link>
                  </div>
                </div>

                <div className={picoInset('mt-4 p-4')}>
                  <p className={picoClasses.label}>{t('rail.directLine')}</p>
                  <a href="mailto:hello@mutx.dev" className={cn(picoClasses.link, 'mt-3 inline-flex')}>
                    hello@mutx.dev
                  </a>
                </div>
              </div>
            </div>
          </div>

          <aside className="space-y-6 xl:sticky xl:top-6 xl:self-start">
            <section className={picoPanel('p-5')}>
              <div className="flex items-start justify-between gap-4">
                <div>
                  <p className={picoClasses.label}>{t('packet.label')}</p>
                  <h2 className="mt-3 font-[family:var(--font-site-display)] text-3xl tracking-[-0.05em] text-[color:var(--pico-text)]">
                    {t('packet.title')}
                  </h2>
                </div>
                <span className={picoClasses.chip}>{t('packet.chip')}</span>
              </div>

              <div className={picoSoft('mt-4 p-5')}>
                <pre className="overflow-x-auto whitespace-pre-wrap text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                  <code>{diagnosticPacket}</code>
                </pre>
              </div>

              <div className="mt-4 flex flex-wrap gap-3">
                <button
                  type="button"
                  onClick={() => void copyDiagnosticPacket()}
                  disabled={!supportControlsReady}
                  className={cn(picoClasses.secondaryButton, disabledControlClassName)}
                >
                  {copied ? t('actions.copiedPacket') : t('actions.copyPacket')}
                </button>
                <button
                  type="button"
                  onClick={() => openEscalation('fixing-existing')}
                  disabled={!supportControlsReady}
                  className={cn(picoClasses.primaryButton, disabledControlClassName)}
                >
                  {t('packet.openFormWithPacket')}
                </button>
              </div>
            </section>

            <section className={picoPanel('p-5')}>
              <p className={picoClasses.label}>{t('state.label')}</p>
              <div className="mt-4 grid gap-3">
                <div className={picoInset('p-4')}>
                  <p className="text-sm text-[color:var(--pico-text-muted)]">{t('state.hostedOnboarding')}</p>
                  <p className="mt-1 text-lg font-medium text-[color:var(--pico-text)]">
                    {setup.onboarding?.status ?? t('shared.runtime.notAttached')}
                  </p>
                </div>
                <div className={picoInset('p-4')}>
                  <p className="text-sm text-[color:var(--pico-text-muted)]">{t('state.runtimeStatus')}</p>
                  <p className="mt-1 text-lg font-medium text-[color:var(--pico-text)]">
                    {setup.runtime?.status ?? t('shared.runtime.notAttached')}
                  </p>
                </div>
                <div className={picoInset('p-4')}>
                  <p className="text-sm text-[color:var(--pico-text-muted)]">{t('state.currentTrack')}</p>
                  <p className="mt-1 text-lg font-medium text-[color:var(--pico-text)]">
                    {progress.selectedTrack ?? t('state.currentTrackNotChosenYet')}
                  </p>
                </div>
                <div className={picoInset('p-4')}>
                  <p className="text-sm text-[color:var(--pico-text-muted)]">{t('state.nextLesson')}</p>
                  <p className="mt-1 text-lg font-medium text-[color:var(--pico-text)]">
                    {derived.nextLesson?.title ?? t('state.nextLessonNone')}
                  </p>
                </div>
                {recoveryLesson ? (
                  <>
                    <div className={picoInset('p-4')}>
                      <p className="text-sm text-[color:var(--pico-text-muted)]">{t('state.lessonWorkspace')}</p>
                      <p className="mt-1 text-lg font-medium text-[color:var(--pico-text)]">
                        {recoveryWorkspace.completedStepCount}/{recoveryLesson.steps.length}
                      </p>
                    </div>
                    <div className={picoInset('p-4')}>
                      <p className="text-sm text-[color:var(--pico-text-muted)]">{t('state.focusedStep')}</p>
                      <p className="mt-1 text-lg font-medium text-[color:var(--pico-text)]">{recoveryFocusedStep}</p>
                    </div>
                  </>
                ) : null}
              </div>
            </section>
          </aside>
        </section>

        <section className={picoPanel('p-6 sm:p-7')} data-testid="pico-support-return-map">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <p className={picoClasses.label}>{t('returnMap.label')}</p>
              <h2 className="mt-3 font-[family:var(--font-site-display)] text-3xl tracking-[-0.05em] text-[color:var(--pico-text)] sm:text-4xl">
                {t('returnMap.title')}
              </h2>
            </div>
            <span className={picoClasses.chip}>{t('returnMap.chip')}</span>
          </div>

          <div className="mt-6 grid gap-6 xl:grid-cols-[minmax(0,0.92fr),minmax(0,1.08fr)]">
            <div className="grid gap-4">
              <article className={picoInset('grid gap-4 p-5')}>
                <p className={picoClasses.label}>{t('returnMap.model.label')}</p>
                <div className="grid gap-3">
                  <div className={picoSoft('p-4')}>
                    <p className="font-[family:var(--font-site-display)] text-2xl tracking-[-0.05em] text-[color:var(--pico-text)]">
                      {t('returnMap.model.cards.0.title')}
                    </p>
                    <p className="mt-2 text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                      {t('returnMap.model.cards.0.body')}
                    </p>
                  </div>
                  <div className={picoSoft('p-4')}>
                    <p className="font-[family:var(--font-site-display)] text-2xl tracking-[-0.05em] text-[color:var(--pico-text)]">
                      {t('returnMap.model.cards.1.title')}
                    </p>
                    <p className="mt-2 text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                      {t('returnMap.model.cards.1.body')}
                    </p>
                  </div>
                  <div className={picoSoft('p-4')}>
                    <p className="font-[family:var(--font-site-display)] text-2xl tracking-[-0.05em] text-[color:var(--pico-text)]">
                      {t('returnMap.model.cards.2.title')}
                    </p>
                    <p className="mt-2 text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                      {t('returnMap.model.cards.2.body')}
                    </p>
                  </div>
                </div>
              </article>

              <article className={picoInset('grid gap-4 p-5')}>
                <div>
                  <p className={picoClasses.label}>{t('returnMap.anatomy.label')}</p>
                  <p className="mt-3 text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                    {t('returnMap.anatomy.body')}
                  </p>
                </div>
                <div className="grid gap-3 md:grid-cols-3">
                  <div className={picoSoft('p-4')}>
                    <p className="font-medium text-[color:var(--pico-text)]">{t('returnMap.anatomy.cards.0.title')}</p>
                    <p className="mt-2 text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                      {t('returnMap.anatomy.cards.0.body')}
                    </p>
                  </div>
                  <div className={picoSoft('p-4')}>
                    <p className="font-medium text-[color:var(--pico-text)]">{t('returnMap.anatomy.cards.1.title')}</p>
                    <p className="mt-2 text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                      {t('returnMap.anatomy.cards.1.body')}
                    </p>
                  </div>
                  <div className={picoSoft('p-4')}>
                    <p className="font-medium text-[color:var(--pico-text)]">{t('returnMap.anatomy.cards.2.title')}</p>
                    <p className="mt-2 text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                      {t('returnMap.anatomy.cards.2.body')}
                    </p>
                  </div>
                </div>
              </article>
            </div>

            <div className="grid gap-4 md:grid-cols-3 xl:grid-cols-1">
              <article className={picoInset('grid gap-4 p-5')}>
                <div>
                  <p className={picoClasses.label}>{t('returnMap.paths.lesson.label')}</p>
                  <h3 className="mt-3 font-[family:var(--font-site-display)] text-2xl tracking-[-0.05em] text-[color:var(--pico-text)]">
                    {t('returnMap.paths.lesson.title')}
                  </h3>
                  <p className="mt-3 text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                    {t('returnMap.paths.lesson.body')}
                  </p>
                </div>
                <Link
                  href={recoveryLesson ? toHref(`/academy/${recoveryLesson.slug}`) : toHref('/academy')}
                  className={picoClasses.secondaryButton}
                >
                  {recoveryLesson ? t('shared.openLesson', { lessonTitle: recoveryLesson.title }) : t('rail.returnAcademy')}
                </Link>
              </article>

              <article className={picoInset('grid gap-4 p-5')}>
                <div>
                  <p className={picoClasses.label}>{t('returnMap.paths.tutor.label')}</p>
                  <h3 className="mt-3 font-[family:var(--font-site-display)] text-2xl tracking-[-0.05em] text-[color:var(--pico-text)]">
                    {t('returnMap.paths.tutor.title')}
                  </h3>
                  <p className="mt-3 text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                    {t('returnMap.paths.tutor.body')}
                  </p>
                </div>
                <Link href={toHref('/tutor')} className={picoClasses.tertiaryButton}>
                  {t('returnMap.paths.tutor.cta')}
                </Link>
              </article>

              <article className={picoInset('grid gap-4 p-5')}>
                <div>
                  <p className={picoClasses.label}>{t('returnMap.paths.autopilot.label')}</p>
                  <h3 className="mt-3 font-[family:var(--font-site-display)] text-2xl tracking-[-0.05em] text-[color:var(--pico-text)]">
                    {t('returnMap.paths.autopilot.title')}
                  </h3>
                  <p className="mt-3 text-sm leading-6 text-[color:var(--pico-text-secondary)]">
                    {t('returnMap.paths.autopilot.body')}
                  </p>
                </div>
                <Link href={toHref('/autopilot')} className={picoClasses.tertiaryButton}>
                  {t('returnMap.paths.autopilot.cta')}
                </Link>
              </article>
            </div>
          </div>
        </section>
      </PicoShell>
    </>
  )
}
