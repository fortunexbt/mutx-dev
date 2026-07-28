'use client'

import { useCallback, useEffect, useRef, useState } from 'react'

export type PicoSetupStep = {
  id: string
  title: string
  completed: boolean
}

export type PicoProviderOption = {
  id: string
  label: string
  summary: string
  enabled: boolean
  cue?: string
}

export type PicoOnboardingState = {
  provider: string
  status: string
  current_step: string
  completed_steps: string[]
  failed_step?: string | null
  last_error?: string | null
  checklist_dismissed?: boolean
  assistant_name?: string | null
  assistant_id?: string | null
  workspace?: string | null
  gateway_url?: string | null
  updated_at?: string | null
  steps: PicoSetupStep[]
  providers?: PicoProviderOption[]
}

export type PicoRuntimeBinding = {
  assistant_id?: string | null
  assistant_name?: string | null
  workspace?: string | null
  model?: string | null
}

export type PicoRuntimeGateway = {
  status?: string | null
  doctor_summary?: string | null
  [key: string]: unknown
}

export type PicoRuntimeSnapshot = {
  provider: string
  label: string
  status: string
  cue?: string | null
  install_method?: string | null
  runtime_key?: string | null
  gateway_url?: string | null
  gateway?: PicoRuntimeGateway
  current_binding?: PicoRuntimeBinding | null
  version?: string | null
  binary_path?: string | null
  config_path?: string | null
  state_dir?: string | null
  home_path?: string | null
  provider_root?: string | null
  last_seen_at?: string | null
  last_synced_at?: string | null
  stale: boolean
  stale_after_seconds?: number
  binding_count: number
  bindings: PicoRuntimeBinding[]
}

export type PicoCoachOnboardingState = {
  stack?: string | null
  os?: string | null
  provider?: string | null
  hardware?: string | null
  channels: string[]
  networking?: string | null
  skill_level?: string | null
  goal?: string | null
  ready: boolean
}

export type PicoCoachMessage = {
  role: 'user' | 'assistant'
  content: string
  onboarding_state?: PicoCoachOnboardingState | null
}

export type PicoCoachSession = {
  session_id: string
  history: PicoCoachMessage[]
  onboarding_state: PicoCoachOnboardingState
  ready_for_package: boolean
  created_at: string
  updated_at: string
  expires_at: string
}

type PicoSetupState = {
  loading: boolean
  error: string | null
  pendingAction: string | null
  onboarding: PicoOnboardingState | null
  runtime: PicoRuntimeSnapshot | null
  coachLoading: boolean
  coachError: string | null
  coachExpired: boolean
  coachAuthRequired: boolean
  coachPending: boolean
  coachSession: PicoCoachSession | null
  packagePending: boolean
  packageError: string | null
  packageUpgradeRequired: boolean
  refresh: () => Promise<void>
  refreshCoachSession: (sessionId?: string) => Promise<void>
  sendCoachMessage: (message: string) => Promise<boolean>
  startNewCoachSession: () => Promise<boolean>
  downloadPackage: () => Promise<boolean>
  completeCurrentStep: () => Promise<void>
  dismissChecklist: () => Promise<void>
  completeAll: () => Promise<void>
  resetWizard: () => Promise<void>
  updateRuntimeSnapshot: (payload: Partial<PicoRuntimeSnapshot>) => Promise<void>
}

export type PicoCoachRetryRequest = {
  message: string
  requestId: string
  sessionId: string | null
}

const PICO_COACH_RETRY_STORAGE_KEY = 'mutx:pico:coach-retry:v1'
const PICO_COACH_REQUEST_ID_PATTERN = /^[A-Za-z0-9_-]{1,64}$/
const PICO_COACH_SESSION_ID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/

export function resolvePicoCoachRetryRequest(
  pending: PicoCoachRetryRequest | null,
  message: string,
  sessionId: string | null,
  createRequestId: () => string,
): PicoCoachRetryRequest {
  if (pending?.message === message) {
    return pending
  }

  return {
    message,
    requestId: createRequestId(),
    sessionId,
  }
}

function readPicoCoachRetryRequest(): PicoCoachRetryRequest | null {
  if (typeof window === 'undefined') return null

  try {
    const raw = window.sessionStorage.getItem(PICO_COACH_RETRY_STORAGE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as Partial<PicoCoachRetryRequest>
    const sessionId = parsed.sessionId ?? null
    if (
      typeof parsed.message !== 'string' ||
      !parsed.message ||
      parsed.message.length > 6000 ||
      typeof parsed.requestId !== 'string' ||
      !PICO_COACH_REQUEST_ID_PATTERN.test(parsed.requestId) ||
      (sessionId !== null && !PICO_COACH_SESSION_ID_PATTERN.test(sessionId))
    ) {
      window.sessionStorage.removeItem(PICO_COACH_RETRY_STORAGE_KEY)
      return null
    }
    return { message: parsed.message, requestId: parsed.requestId, sessionId }
  } catch {
    return null
  }
}

function writePicoCoachRetryRequest(request: PicoCoachRetryRequest) {
  if (typeof window === 'undefined') return
  try {
    window.sessionStorage.setItem(PICO_COACH_RETRY_STORAGE_KEY, JSON.stringify(request))
  } catch {
    // Session storage is a continuity aid; the backend idempotency contract still protects this tab.
  }
}

function clearPicoCoachRetryRequest() {
  if (typeof window === 'undefined') return
  try {
    window.sessionStorage.removeItem(PICO_COACH_RETRY_STORAGE_KEY)
  } catch {
    // Storage can be unavailable in hardened browser contexts.
  }
}

async function readJsonOrNull(response: Response) {
  return response.json().catch(() => null)
}

export function picoApiErrorMessage(payload: unknown, fallback: string) {
  if (!payload || typeof payload !== 'object') return fallback
  const body = payload as {
    detail?: unknown
    error?: { message?: unknown }
  }
  if (typeof body.detail === 'string' && body.detail) return body.detail
  if (typeof body.error?.message === 'string' && body.error.message) {
    return body.error.message
  }
  return fallback
}

export function picoPackageFilename(contentDisposition: string | null) {
  const encoded = contentDisposition?.match(/filename\*=UTF-8''([^;]+)/i)?.[1]
  const plain = contentDisposition?.match(/filename="?([^";]+)"?/i)?.[1]
  let candidate = encoded ?? plain ?? ''
  if (encoded) {
    try {
      candidate = decodeURIComponent(encoded)
    } catch {
      candidate = ''
    }
  }
  const basename = candidate.trim().replaceAll('\\', '/').split('/').pop() ?? ''
  const safe = basename
    .replace(/[^A-Za-z0-9._-]+/g, '-')
    .replace(/^[.-]+|[.-]+$/g, '')
    .slice(0, 120)
  if (!safe) return 'pico-agent-package.zip'
  return safe.toLowerCase().endsWith('.zip') ? safe : `${safe}.zip`
}

export function usePicoSetupState(enabled: boolean): PicoSetupState {
  const [loading, setLoading] = useState(enabled)
  const [error, setError] = useState<string | null>(null)
  const [pendingAction, setPendingAction] = useState<string | null>(null)
  const [onboarding, setOnboarding] = useState<PicoOnboardingState | null>(null)
  const [runtime, setRuntime] = useState<PicoRuntimeSnapshot | null>(null)
  const [coachLoading, setCoachLoading] = useState(enabled)
  const [coachError, setCoachError] = useState<string | null>(null)
  const [coachExpired, setCoachExpired] = useState(false)
  const [coachAuthRequired, setCoachAuthRequired] = useState(false)
  const [coachPending, setCoachPending] = useState(false)
  const [coachSession, setCoachSession] = useState<PicoCoachSession | null>(null)
  const [packagePending, setPackagePending] = useState(false)
  const [packageError, setPackageError] = useState<string | null>(null)
  const [packageUpgradeRequired, setPackageUpgradeRequired] = useState(false)
  const setupRefreshVersion = useRef(0)
  const coachRefreshVersion = useRef(0)
  const setupActionInFlight = useRef(false)
  const coachActionInFlight = useRef(false)
  const coachRetryRequest = useRef<PicoCoachRetryRequest | null>(null)

  useEffect(() => {
    if (enabled) {
      coachRetryRequest.current = readPicoCoachRetryRequest()
      return
    }

    coachRetryRequest.current = null
    clearPicoCoachRetryRequest()
  }, [enabled])

  const refresh = useCallback(async () => {
    const refreshVersion = ++setupRefreshVersion.current
    if (!enabled) {
      setLoading(false)
      setError(null)
      setPendingAction(null)
      setOnboarding(null)
      setRuntime(null)
      return
    }

    setLoading(true)
    setError(null)

    try {
      const [onboardingResponse, runtimeResponse] = await Promise.all([
        fetch('/api/pico/onboarding?provider=openclaw', { credentials: 'include', cache: 'no-store' }),
        fetch('/api/pico/runtime/openclaw', { credentials: 'include', cache: 'no-store' }),
      ])

      if (!onboardingResponse.ok) {
        const payload = await readJsonOrNull(onboardingResponse)
        throw new Error(
          typeof payload?.detail === 'string' && payload.detail
            ? payload.detail
            : 'Failed to load Pico onboarding state',
        )
      }

      if (!runtimeResponse.ok) {
        const payload = await readJsonOrNull(runtimeResponse)
        throw new Error(
          typeof payload?.detail === 'string' && payload.detail
            ? payload.detail
            : 'Failed to load Pico runtime state',
        )
      }

      const [onboardingPayload, runtimePayload] = await Promise.all([
        onboardingResponse.json(),
        runtimeResponse.json(),
      ])

      if (refreshVersion === setupRefreshVersion.current) {
        setOnboarding(onboardingPayload as PicoOnboardingState)
        setRuntime(runtimePayload as PicoRuntimeSnapshot)
      }
    } catch (loadError) {
      if (refreshVersion === setupRefreshVersion.current) {
        setOnboarding(null)
        setRuntime(null)
        setError(loadError instanceof Error ? loadError.message : 'Failed to load Pico setup state')
      }
    } finally {
      if (refreshVersion === setupRefreshVersion.current) {
        setLoading(false)
      }
    }
  }, [enabled])

  const refreshCoachSession = useCallback(async (sessionId?: string) => {
    const refreshVersion = ++coachRefreshVersion.current
    if (!enabled) {
      setCoachLoading(false)
      setCoachError(null)
      setCoachExpired(false)
      setCoachAuthRequired(false)
      setCoachPending(false)
      setCoachSession(null)
      setPackagePending(false)
      setPackageError(null)
      setPackageUpgradeRequired(false)
      return
    }

    setCoachLoading(true)
    setCoachError(null)
    setCoachAuthRequired(false)

    try {
      const query = new URLSearchParams({ view: 'coach_session' })
      if (sessionId) query.set('session_id', sessionId)
      const response = await fetch(`/api/pico/onboarding?${query.toString()}`, {
        credentials: 'include',
        cache: 'no-store',
      })

      if (refreshVersion !== coachRefreshVersion.current) return
      if (response.status === 204) {
        setCoachSession(null)
        setCoachExpired(false)
        return
      }

      const payload = await readJsonOrNull(response)
      if (!response.ok) {
        setCoachAuthRequired(response.status === 401)
        setCoachExpired(response.status === 410)
        if (response.status === 410) setCoachSession(null)
        throw new Error(picoApiErrorMessage(payload, 'Failed to resume Pico onboarding session'))
      }

      setCoachSession(payload as PicoCoachSession)
      setCoachExpired(false)
    } catch (loadError) {
      if (refreshVersion === coachRefreshVersion.current) {
        setCoachError(
          loadError instanceof Error
            ? loadError.message
            : 'Failed to resume Pico onboarding session',
        )
      }
    } finally {
      if (refreshVersion === coachRefreshVersion.current) {
        setCoachLoading(false)
      }
    }
  }, [enabled])

  const sendCoachMessage = useCallback(async (message: string) => {
    const normalizedMessage = message.trim()
    if (!enabled || !normalizedMessage || coachActionInFlight.current) {
      return false
    }

    coachActionInFlight.current = true
    setCoachPending(true)
    setCoachError(null)
    setCoachAuthRequired(false)
    setPackageError(null)

    const retryRequest = resolvePicoCoachRetryRequest(
      coachRetryRequest.current ?? readPicoCoachRetryRequest(),
      normalizedMessage,
      coachSession?.session_id ?? null,
      () => crypto.randomUUID(),
    )
    coachRetryRequest.current = retryRequest
    writePicoCoachRetryRequest(retryRequest)

    try {
      const response = await fetch('/api/pico/onboarding', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action: 'coach_message',
          message: normalizedMessage,
          session_id: retryRequest.sessionId ?? undefined,
          request_id: retryRequest.requestId,
        }),
      })
      const payload = await readJsonOrNull(response)
      if (!response.ok) {
        setCoachAuthRequired(response.status === 401)
        setCoachExpired(response.status === 410)
        if (response.status === 410) setCoachSession(null)
        throw new Error(picoApiErrorMessage(payload, 'Pico onboarding coach request failed'))
      }

      const sessionId = typeof payload?.session_id === 'string' ? payload.session_id : null
      if (!sessionId || payload?.session_persisted !== true) {
        throw new Error('Pico could not persist this onboarding session')
      }
      coachRetryRequest.current = null
      clearPicoCoachRetryRequest()
      await refreshCoachSession(sessionId)
      return true
    } catch (sendError) {
      setCoachError(
        sendError instanceof Error ? sendError.message : 'Pico onboarding coach request failed',
      )
      return false
    } finally {
      coachActionInFlight.current = false
      setCoachPending(false)
    }
  }, [coachSession?.session_id, enabled, refreshCoachSession])

  const startNewCoachSession = useCallback(async () => {
    if (!enabled || coachActionInFlight.current) return false

    coachActionInFlight.current = true
    setCoachPending(true)
    setCoachError(null)
    setCoachAuthRequired(false)

    try {
      const response = await fetch('/api/pico/onboarding', {
        method: 'DELETE',
        credentials: 'include',
        cache: 'no-store',
      })
      if (!response.ok) {
        const payload = await readJsonOrNull(response)
        setCoachAuthRequired(response.status === 401)
        throw new Error(picoApiErrorMessage(payload, 'Failed to reset Pico onboarding session'))
      }

      ++coachRefreshVersion.current
      coachRetryRequest.current = null
      clearPicoCoachRetryRequest()
      setCoachSession(null)
      setCoachError(null)
      setCoachExpired(false)
      setCoachAuthRequired(false)
      setPackageError(null)
      setPackageUpgradeRequired(false)
      setCoachLoading(false)
      return true
    } catch (resetError) {
      setCoachError(
        resetError instanceof Error
          ? resetError.message
          : 'Failed to reset Pico onboarding session',
      )
      return false
    } finally {
      coachActionInFlight.current = false
      setCoachPending(false)
    }
  }, [enabled])

  const downloadPackage = useCallback(async () => {
    if (!enabled || !coachSession?.session_id || coachActionInFlight.current) {
      return false
    }

    coachActionInFlight.current = true
    setPackagePending(true)
    setPackageError(null)
    setPackageUpgradeRequired(false)
    setCoachAuthRequired(false)

    try {
      const response = await fetch('/api/pico/package', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: coachSession.session_id }),
      })

      if (!response.ok) {
        const payload = await readJsonOrNull(response)
        setPackageUpgradeRequired(response.status === 402)
        setCoachAuthRequired(response.status === 401)
        setCoachExpired(response.status === 410)
        if (response.status === 410) setCoachSession(null)
        throw new Error(picoApiErrorMessage(payload, 'Failed to generate Pico package'))
      }

      const blob = await response.blob()
      const objectUrl = URL.createObjectURL(blob)
      try {
        const anchor = document.createElement('a')
        anchor.href = objectUrl
        anchor.download = picoPackageFilename(response.headers.get('content-disposition'))
        anchor.rel = 'noopener'
        document.body.appendChild(anchor)
        anchor.click()
        anchor.remove()
      } finally {
        URL.revokeObjectURL(objectUrl)
      }
      return true
    } catch (downloadError) {
      setPackageError(
        downloadError instanceof Error ? downloadError.message : 'Failed to generate Pico package',
      )
      return false
    } finally {
      coachActionInFlight.current = false
      setPackagePending(false)
    }
  }, [coachSession?.session_id, enabled])

  const runOnboardingAction = useCallback(
    async (
      action: 'complete_step' | 'dismiss_checklist' | 'complete' | 'reset',
      options?: {
        step?: string
        payload?: Record<string, unknown>
      },
    ) => {
      if (!enabled) {
        return
      }
      if (setupActionInFlight.current) {
        return
      }

      setupActionInFlight.current = true
      setPendingAction(action)
      setError(null)

      try {
        const response = await fetch('/api/pico/onboarding', {
          method: 'POST',
          credentials: 'include',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            action,
            provider: onboarding?.provider ?? 'openclaw',
            step: options?.step,
            payload: options?.payload,
          }),
        })

        if (!response.ok) {
          const payload = await readJsonOrNull(response)
          throw new Error(
            typeof payload?.detail === 'string' && payload.detail
              ? payload.detail
              : 'Failed to update Pico onboarding state',
          )
        }

        await refresh()
      } catch (updateError) {
        setError(updateError instanceof Error ? updateError.message : 'Failed to update Pico setup state')
      } finally {
        setupActionInFlight.current = false
        setPendingAction(null)
      }
    },
    [enabled, onboarding?.provider, refresh],
  )

  const completeCurrentStep = useCallback(async () => {
    if (!onboarding?.current_step) {
      return
    }

    await runOnboardingAction('complete_step', {
      step: onboarding.current_step,
    })
  }, [onboarding?.current_step, runOnboardingAction])

  const dismissChecklist = useCallback(async () => {
    await runOnboardingAction('dismiss_checklist')
  }, [runOnboardingAction])

  const completeAll = useCallback(async () => {
    await runOnboardingAction('complete')
  }, [runOnboardingAction])

  const resetWizard = useCallback(async () => {
    await runOnboardingAction('reset')
  }, [runOnboardingAction])

  const updateRuntimeSnapshot = useCallback(
    async (payload: Partial<PicoRuntimeSnapshot>) => {
      if (!enabled) {
        return
      }
      if (setupActionInFlight.current) {
        return
      }

      setupActionInFlight.current = true
      setPendingAction('runtime')
      setError(null)

      const provider = payload.provider ?? runtime?.provider ?? onboarding?.provider ?? 'openclaw'

      const nextBindings =
        payload.bindings ??
        runtime?.bindings ??
        []

      const body = {
        provider,
        runtime_key: payload.runtime_key ?? runtime?.runtime_key ?? provider,
        label: payload.label ?? runtime?.label ?? 'OpenClaw',
        cue: payload.cue ?? runtime?.cue ?? null,
        status: payload.status ?? runtime?.status ?? 'unknown',
        install_method: payload.install_method ?? runtime?.install_method ?? null,
        gateway: payload.gateway ?? runtime?.gateway ?? {},
        gateway_url: payload.gateway_url ?? runtime?.gateway_url ?? null,
        current_binding: payload.current_binding ?? runtime?.current_binding ?? null,
        binding_count:
          typeof payload.binding_count === 'number'
            ? payload.binding_count
            : Array.isArray(nextBindings)
              ? nextBindings.length
              : runtime?.binding_count ?? 0,
        bindings: nextBindings,
        binary_path: payload.binary_path ?? runtime?.binary_path ?? null,
        config_path: payload.config_path ?? runtime?.config_path ?? null,
        state_dir: payload.state_dir ?? runtime?.state_dir ?? null,
        home_path: payload.home_path ?? runtime?.home_path ?? null,
        provider_root: payload.provider_root ?? runtime?.provider_root ?? null,
        version: payload.version ?? runtime?.version ?? null,
        last_seen_at: payload.last_seen_at ?? runtime?.last_seen_at ?? null,
      }

      try {
        const response = await fetch(`/api/pico/runtime/${encodeURIComponent(provider)}`, {
          method: 'PUT',
          credentials: 'include',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify(body),
        })

        if (!response.ok) {
          const responsePayload = await readJsonOrNull(response)
          throw new Error(
            typeof responsePayload?.detail === 'string' && responsePayload.detail
              ? responsePayload.detail
              : 'Failed to update Pico runtime state',
          )
        }

        const responsePayload = (await response.json()) as PicoRuntimeSnapshot
        setRuntime(responsePayload)
      } catch (updateError) {
        setError(updateError instanceof Error ? updateError.message : 'Failed to update Pico runtime state')
      } finally {
        setupActionInFlight.current = false
        setPendingAction(null)
      }
    },
    [enabled, onboarding?.provider, runtime],
  )

  useEffect(() => {
    void refresh()
  }, [refresh])

  useEffect(() => {
    void refreshCoachSession()
  }, [refreshCoachSession])

  return {
    loading,
    error,
    pendingAction,
    onboarding,
    runtime,
    coachLoading,
    coachError,
    coachExpired,
    coachAuthRequired,
    coachPending,
    coachSession,
    packagePending,
    packageError,
    packageUpgradeRequired,
    refresh,
    refreshCoachSession,
    sendCoachMessage,
    startNewCoachSession,
    downloadPackage,
    completeCurrentStep,
    dismissChecklist,
    completeAll,
    resetWizard,
    updateRuntimeSnapshot,
  }
}
