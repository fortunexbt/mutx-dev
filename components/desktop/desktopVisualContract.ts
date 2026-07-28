import { dashboardTokens } from '@/components/dashboard/tokens'

export type DesktopSemanticTone = 'neutral' | 'running' | 'success' | 'warning' | 'danger'

export const DESKTOP_VISUAL_CONTRACT = {
  palette: {
    canvas: dashboardTokens.bgCanvas,
    canvasRaised: dashboardTokens.bgCanvasRaised,
    surface: dashboardTokens.bgSurface,
    surfaceStrong: dashboardTokens.bgSurfaceStrong,
    inset: dashboardTokens.bgInset,
    bone: dashboardTokens.textPrimary,
    boneMuted: dashboardTokens.textSubtle,
    signal: dashboardTokens.brand,
    signalStrong: dashboardTokens.brandStrong,
    trace: dashboardTokens.trace,
    success: dashboardTokens.success,
    warning: dashboardTokens.warn,
    danger: dashboardTokens.danger,
  },
  geometry: {
    square: 0,
    control: 4,
    panel: 6,
    dialog: 8,
    compactStatus: 9999,
  },
  typography: {
    body: dashboardTokens.fontSans,
    display: 'var(--font-site-display, var(--font-display))',
    data: dashboardTokens.fontMono,
  },
} as const

export const DESKTOP_FOCUS_CLASS =
  'focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#ff7847]'

export const DESKTOP_ACTION_CLASS =
  `min-h-10 rounded-[4px] border text-xs font-semibold transition-colors ${DESKTOP_FOCUS_CLASS} disabled:cursor-not-allowed disabled:opacity-50`

export const DESKTOP_SOURCE_TONE_CLASS: Record<DesktopSemanticTone, string> = {
  neutral: 'border-[#34342e] bg-[#171813] text-[#aaa397]',
  running: 'border-[#294d6c] bg-[#101c26] text-[#8ac7ff]',
  success: 'border-[#285a43] bg-[#0f2018] text-[#78e3b4]',
  warning: 'border-[#65502b] bg-[#211a0e] text-[#f4cc82]',
  danger: 'border-[#66302e] bg-[#241312] text-[#ff9b96]',
}

export function getDesktopStateTone(state: string | null | undefined): DesktopSemanticTone {
  switch ((state || '').toLowerCase()) {
    case 'ready':
    case 'healthy':
    case 'active':
    case 'completed':
    case 'running':
      return 'success'
    case 'starting':
    case 'restarting':
    case 'checking':
      return 'running'
    case 'degraded':
    case 'warning':
    case 'stale':
    case 'stopped':
    case 'pending':
      return 'warning'
    case 'error':
    case 'failed':
    case 'unavailable':
      return 'danger'
    default:
      return 'neutral'
  }
}

export function getDesktopFreshnessPresentation(
  freshness: 'fresh' | 'checking' | 'stale' | 'unavailable',
): { label: 'Live' | 'Checking' | 'Stale' | 'Unavailable'; tone: DesktopSemanticTone } {
  switch (freshness) {
    case 'fresh':
      return { label: 'Live', tone: 'success' }
    case 'checking':
      return { label: 'Checking', tone: 'running' }
    case 'stale':
      return { label: 'Stale', tone: 'warning' }
    case 'unavailable':
      return { label: 'Unavailable', tone: 'danger' }
  }
}
