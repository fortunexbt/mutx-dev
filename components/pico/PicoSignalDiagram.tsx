'use client'

import { useTranslations } from 'next-intl'

import { cn } from '@/lib/utils'
import { normalizePicoPathname } from '@/lib/pico/navigation'

export type PicoRouteSignal = {
  index: string
  label: string
  title: string
  caption: string
  messageKey?: 'landing' | 'onboarding' | 'academy' | 'tutor' | 'autopilot' | 'support'
}

const routeSignals = {
  landing: {
    index: '00',
    label: 'Launch marker',
    title: 'Start with one working path.',
    caption: 'Keep the landing simple, then let the product pages handle setup.',
    messageKey: 'landing',
  },
  onboarding: {
    index: '01',
    label: 'Guide marker',
    title: 'Install. Run. Record.',
    caption: 'Onboarding keeps one setup step and the agent packet in view.',
    messageKey: 'onboarding',
  },
  academy: {
    index: '02',
    label: 'Lesson marker',
    title: 'Clear one chapter at a time.',
    caption: 'Academy keeps setup moving one lesson at a time.',
    messageKey: 'academy',
  },
  tutor: {
    index: '03',
    label: 'Tutor marker',
    title: 'Name the blocker precisely.',
    caption: 'Tutor answers one blocker and sends you back to setup.',
    messageKey: 'tutor',
  },
  autopilot: {
    index: '04',
    label: 'Runtime marker',
    title: 'Read state before acting.',
    caption: 'Autopilot keeps run state, spend, and approvals close together.',
    messageKey: 'autopilot',
  },
  support: {
    index: '05',
    label: 'Support marker',
    title: 'Bring the shortest useful packet.',
    caption: 'Support handles keys, hosting, integrations, and implementation judgment.',
    messageKey: 'support',
  },
} satisfies Record<string, PicoRouteSignal>

export function getPicoRouteSignal(pathname: string, academyMode = false): PicoRouteSignal {
  const normalizedPathname = normalizePicoPathname(pathname)

  if (academyMode || normalizedPathname.startsWith('/academy')) return routeSignals.academy
  if (normalizedPathname.startsWith('/onboarding')) return routeSignals.onboarding
  if (normalizedPathname.startsWith('/tutor')) return routeSignals.tutor
  if (normalizedPathname.startsWith('/autopilot')) return routeSignals.autopilot
  if (normalizedPathname.startsWith('/support')) return routeSignals.support
  return routeSignals.landing
}

type PicoSignalDiagramProps = PicoRouteSignal & {
  className?: string
  compact?: boolean
}

export function PicoSignalDiagram({
  index,
  label,
  title,
  caption,
  messageKey,
  className,
  compact = false,
}: PicoSignalDiagramProps) {
  const t = useTranslations('pico.signalDiagram')
  const localizedLabel = messageKey ? t(`routes.${messageKey}.label`) : label
  const localizedTitle = messageKey ? t(`routes.${messageKey}.title`) : title
  const localizedCaption = messageKey ? t(`routes.${messageKey}.caption`) : caption

  return (
    <figure
      className={cn(
        'overflow-hidden border border-[#0a0a09] bg-[#f3f0e8] text-[#0a0a09]',
        className,
      )}
    >
      <div className="flex min-h-11 items-center justify-between gap-4 border-b border-[#0a0a09] px-4 font-[family:var(--font-mono)] text-[10px] font-semibold uppercase tracking-[0.16em]">
        <span>{localizedLabel}</span>
        <span className="text-[#c83b00]">{t('signal', { index })}</span>
      </div>

      <div
        aria-hidden="true"
        className={cn(
          'relative grid overflow-hidden border-b border-[#0a0a09] [background-image:linear-gradient(rgba(10,10,9,0.12)_1px,transparent_1px),linear-gradient(90deg,rgba(10,10,9,0.12)_1px,transparent_1px)] [background-size:2rem_2rem]',
          compact ? 'min-h-36' : 'aspect-[4/3] min-h-48',
        )}
      >
        <span className="absolute start-4 top-3 font-[family:var(--font-site-body)] text-[clamp(4rem,10vw,7rem)] font-semibold leading-none tracking-[-0.1em]">
          {index}
        </span>
        <span className="absolute bottom-4 start-4 h-3 w-3 bg-[#ff4d00]" />
        <span className="absolute bottom-[1.35rem] start-7 end-4 h-px bg-[#0a0a09]" />
        <span className="absolute bottom-4 end-4 h-3 w-3 border border-[#0a0a09] bg-[#f3f0e8]" />
        <span className="absolute end-4 top-4 h-12 w-12 border border-[#0a0a09] before:absolute before:start-1/2 before:top-0 before:h-full before:w-px before:bg-[#0a0a09] after:absolute after:start-0 after:top-1/2 after:h-px after:w-full after:bg-[#0a0a09]" />
      </div>

      <figcaption className={compact ? 'p-4' : 'p-5'}>
        <p className="font-[family:var(--font-site-body)] text-2xl font-semibold leading-none tracking-[-0.055em]">
          {localizedTitle}
        </p>
        <p className="mt-3 text-sm leading-6 text-[#4f4d48]">{localizedCaption}</p>
      </figcaption>
    </figure>
  )
}
