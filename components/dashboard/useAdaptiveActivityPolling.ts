'use client'

import { useCallback, useEffect, useRef, useState } from 'react'

export const VISIBLE_ACTIVITY_POLL_MS = 5_000
export const HIDDEN_ACTIVITY_POLL_MS = 30_000

export type ActivityPollingState = {
  active: boolean
  online: boolean
  visibilityState: DocumentVisibilityState
}

const TERMINAL_RUN_STATUSES = new Set([
  'cancelled',
  'canceled',
  'completed',
  'error',
  'failed',
  'stopped',
  'succeeded',
  'success',
  'timed_out',
  'timeout',
])

export function hasNonterminalRunActivity(
  runs: Array<{ status?: string | null; completed_at?: string | null }>,
): boolean {
  return runs.some((run) => {
    if (run.completed_at) return false
    return !TERMINAL_RUN_STATUSES.has((run.status ?? '').trim().toLowerCase())
  })
}

export function getActivityPollDelay({
  active,
  online,
  visibilityState,
}: ActivityPollingState): number | null {
  if (!active || !online) return null
  return visibilityState === 'visible' ? VISIBLE_ACTIVITY_POLL_MS : HIDDEN_ACTIVITY_POLL_MS
}

function readBrowserEnvironment() {
  return {
    online: typeof navigator === 'undefined' ? true : navigator.onLine,
    visibilityState:
      typeof document === 'undefined' ? ('visible' as const) : document.visibilityState,
  }
}

export function useAdaptiveActivityPolling({
  active,
  poll,
}: {
  active: boolean
  poll: () => Promise<void>
}) {
  const pollRef = useRef(poll)
  const [environment, setEnvironment] = useState(readBrowserEnvironment)

  useEffect(() => {
    pollRef.current = poll
  }, [poll])

  const syncEnvironment = useCallback(() => {
    setEnvironment(readBrowserEnvironment())
  }, [])

  useEffect(() => {
    if (typeof window === 'undefined' || typeof document === 'undefined') return

    window.addEventListener('online', syncEnvironment)
    window.addEventListener('offline', syncEnvironment)
    document.addEventListener('visibilitychange', syncEnvironment)

    return () => {
      window.removeEventListener('online', syncEnvironment)
      window.removeEventListener('offline', syncEnvironment)
      document.removeEventListener('visibilitychange', syncEnvironment)
    }
  }, [syncEnvironment])

  useEffect(() => {
    const delay = getActivityPollDelay({ active, ...environment })
    if (delay === null) return

    let cancelled = false
    let timeoutId: number | null = null

    const schedule = () => {
      timeoutId = window.setTimeout(() => {
        void pollRef.current()
          .catch(() => undefined)
          .finally(() => {
            if (!cancelled) schedule()
          })
      }, delay)
    }

    schedule()

    return () => {
      cancelled = true
      if (timeoutId !== null) window.clearTimeout(timeoutId)
    }
  }, [active, environment])

  return {
    isOnline: environment.online,
    isVisible: environment.visibilityState === 'visible',
    polling: getActivityPollDelay({ active, ...environment }) !== null,
  }
}
