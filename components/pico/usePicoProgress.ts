'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import {
  applyLessonCompleted,
  applyLessonStarted,
  applyMilestone,
  createDefaultPicoProgress,
  derivePicoProgress,
  markProjectShared,
  markSupportRequest,
  markTutorQuestion,
  mergePicoProgress,
  normalizePicoProgress,
  selectTrack,
  updateAutopilotSettings,
  updateLessonWorkspace,
  updatePlatformPreferences,
  type PicoProgressState,
} from '@/lib/pico/academy'

const STORAGE_KEY = 'pico.progress.v1'

export type PicoProgressSyncState =
  | 'loading'
  | 'saving'
  | 'synced'
  | 'offline'
  | 'error'

export type PicoProgressRemoteWriteResult =
  | {
      ok: true
      progress: PicoProgressState
    }
  | {
      ok: false
      syncState: 'offline' | 'error'
    }

type QueuedProgressWrite = {
  progress: PicoProgressState
  revision: number
}

type PicoProgressSyncCoordinatorOptions = {
  send: (
    progress: PicoProgressState,
    signal: AbortSignal,
  ) => Promise<PicoProgressRemoteWriteResult>
  onAccepted: (progress: PicoProgressState, revision: number) => void
  onSyncState: (syncState: PicoProgressSyncState) => void
}

function readLocalProgress() {
  if (typeof window === 'undefined') {
    return createDefaultPicoProgress()
  }

  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (!raw) {
      return createDefaultPicoProgress()
    }

    return normalizePicoProgress(JSON.parse(raw))
  } catch {
    return createDefaultPicoProgress()
  }
}

function writeLocalProgress(progress: PicoProgressState) {
  if (typeof window === 'undefined') return

  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(progress))
  } catch {
    // In-memory progress remains usable when storage is unavailable or full.
  }
}

function picoProgressValuesMatch(left: PicoProgressState, right: PicoProgressState) {
  return JSON.stringify(normalizePicoProgress(left)) === JSON.stringify(normalizePicoProgress(right))
}

export function createPicoProgressSyncCoordinator(
  options: PicoProgressSyncCoordinatorOptions,
) {
  let active = false
  let activeController: AbortController | null = null
  let disposed = false
  let latestRevision = -1
  let pending: QueuedProgressWrite | null = null

  async function drain() {
    if (active || disposed || !pending) return

    const request = pending
    pending = null
    active = true
    activeController = new AbortController()

    try {
      const result = await options.send(request.progress, activeController.signal)

      if (disposed || pending || request.revision < latestRevision) {
        return
      }

      if (result.ok) {
        options.onAccepted(result.progress, request.revision)
        options.onSyncState('synced')
      } else {
        options.onSyncState(result.syncState)
      }
    } catch {
      if (!disposed && !pending && request.revision === latestRevision) {
        options.onSyncState('offline')
      }
    } finally {
      active = false
      activeController = null

      if (!disposed && pending) {
        void drain()
      }
    }
  }

  return {
    enqueue(progress: PicoProgressState, revision: number) {
      if (disposed || revision < latestRevision) return

      latestRevision = revision
      pending = { progress, revision }
      options.onSyncState('saving')
      void drain()
    },
    dispose() {
      disposed = true
      pending = null
      activeController?.abort()
      activeController = null
    },
  }
}

export function shouldSyncHydratedProgress(
  remoteValue: PicoProgressState,
  mergedValue: PicoProgressState,
) {
  return !picoProgressValuesMatch(remoteValue, mergedValue)
}

export function resolveHydratedPicoProgress(
  remoteValue: PicoProgressState,
  currentLocalValue: PicoProgressState,
  localRevisionIsNewer = false,
) {
  if (localRevisionIsNewer) {
    return normalizePicoProgress(currentLocalValue)
  }

  return mergePicoProgress(currentLocalValue, remoteValue)
}

export function usePicoProgress(remoteSyncEnabled = true) {
  const initialProgress = useMemo(() => createDefaultPicoProgress(), [])
  const [progress, setProgress] = useState<PicoProgressState>(initialProgress)
  const [ready, setReady] = useState(false)
  const [syncState, setSyncState] = useState<PicoProgressSyncState>('loading')
  const coordinatorRef = useRef<ReturnType<typeof createPicoProgressSyncCoordinator> | null>(null)
  const mountedRef = useRef(false)
  const pendingSyncRef = useRef<QueuedProgressWrite | null>(null)
  const progressRef = useRef(initialProgress)
  const revisionRef = useRef(0)

  useEffect(() => {
    mountedRef.current = true

    return () => {
      mountedRef.current = false
    }
  }, [])

  useEffect(() => {
    let active = true
    const hydrationController = new AbortController()
    const local = readLocalProgress()

    progressRef.current = local
    setProgress(local)
    writeLocalProgress(local)
    setReady(false)

    if (!remoteSyncEnabled) {
      pendingSyncRef.current = null
      setSyncState('offline')
      setReady(true)

      return () => {
        active = false
        hydrationController.abort()
      }
    }

    setSyncState('loading')

    const coordinator = createPicoProgressSyncCoordinator({
      async send(nextProgress, signal) {
        const response = await fetch('/api/pico/progress', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          credentials: 'include',
          body: JSON.stringify(nextProgress),
          signal,
        })

        if (!response.ok) {
          return {
            ok: false,
            syncState: response.status === 401 ? 'offline' : 'error',
          }
        }

        return {
          ok: true,
          progress: normalizePicoProgress(await response.json()),
        }
      },
      onAccepted(remoteProgress, acceptedRevision) {
        if (!active || !mountedRef.current || acceptedRevision !== revisionRef.current) {
          return
        }

        const merged = resolveHydratedPicoProgress(remoteProgress, progressRef.current)
        if (picoProgressValuesMatch(merged, progressRef.current)) {
          return
        }

        progressRef.current = merged
        writeLocalProgress(merged)
        setProgress(merged)
      },
      onSyncState(nextSyncState) {
        if (active && mountedRef.current) {
          setSyncState(nextSyncState)
        }
      },
    })

    coordinatorRef.current = coordinator

    if (pendingSyncRef.current) {
      coordinator.enqueue(
        pendingSyncRef.current.progress,
        pendingSyncRef.current.revision,
      )
      pendingSyncRef.current = null
    }

    const hydrationRevision = revisionRef.current

    async function hydrate() {
      try {
        const response = await fetch('/api/pico/progress', {
          credentials: 'include',
          cache: 'no-store',
          signal: hydrationController.signal,
        })

        if (!active || !mountedRef.current) return

        if (!response.ok) {
          if (revisionRef.current === hydrationRevision) {
            setSyncState(response.status === 401 ? 'offline' : 'error')
          }
          return
        }

        const remote = normalizePicoProgress(await response.json())
        if (!active || !mountedRef.current) return

        const revisionBeforeMerge = revisionRef.current
        const merged = resolveHydratedPicoProgress(
          remote,
          progressRef.current,
          revisionBeforeMerge !== hydrationRevision,
        )
        const localChanged = !picoProgressValuesMatch(merged, progressRef.current)

        if (localChanged) {
          revisionRef.current += 1
          progressRef.current = merged
          writeLocalProgress(merged)
          setProgress(merged)
        }

        if (shouldSyncHydratedProgress(remote, merged)) {
          if (!localChanged) {
            revisionRef.current += 1
          }
          coordinator.enqueue(merged, revisionRef.current)
        } else if (revisionBeforeMerge === hydrationRevision) {
          setSyncState('synced')
        }
      } catch {
        if (
          active &&
          mountedRef.current &&
          !hydrationController.signal.aborted &&
          revisionRef.current === hydrationRevision
        ) {
          setSyncState('offline')
        }
      } finally {
        if (active && mountedRef.current) {
          setReady(true)
        }
      }
    }

    void hydrate()

    return () => {
      active = false
      hydrationController.abort()
      coordinator.dispose()
      if (coordinatorRef.current === coordinator) {
        coordinatorRef.current = null
      }
    }
  }, [remoteSyncEnabled])

  const storeAndSync = useCallback(
    (nextProgress: PicoProgressState) => {
      const next = normalizePicoProgress(nextProgress)
      revisionRef.current += 1
      progressRef.current = next
      writeLocalProgress(next)
      setProgress(next)

      if (!remoteSyncEnabled) {
        setSyncState('offline')
        return
      }

      const queued = {
        progress: next,
        revision: revisionRef.current,
      }
      const coordinator = coordinatorRef.current

      if (coordinator) {
        coordinator.enqueue(queued.progress, queued.revision)
      } else {
        pendingSyncRef.current = queued
        setSyncState('saving')
      }
    },
    [remoteSyncEnabled],
  )

  const update = useCallback(
    (updater: (current: PicoProgressState) => PicoProgressState) => {
      storeAndSync(updater(progressRef.current))
    },
    [storeAndSync],
  )

  const actions = useMemo(
    () => ({
      startLesson: (lessonSlug: string) => update((current) => applyLessonStarted(current, lessonSlug)),
      completeLesson: (lessonSlug: string) =>
        update((current) => applyLessonCompleted(current, lessonSlug)),
      unlockMilestone: (eventId: string) => update((current) => applyMilestone(current, eventId)),
      pickTrack: (trackSlug: string) => update((current) => selectTrack(current, trackSlug)),
      recordTutorQuestion: () => update((current) => markTutorQuestion(current)),
      recordSupportRequest: () => update((current) => markSupportRequest(current)),
      shareProject: (projectId: string) => update((current) => markProjectShared(current, projectId)),
      setLessonWorkspace: (
        lessonSlug: string,
        workspace: PicoProgressState['lessonWorkspaces'][string],
      ) => update((current) => updateLessonWorkspace(current, lessonSlug, workspace)),
      setPlatform: (patch: Partial<PicoProgressState['platform']>) =>
        update((current) => updatePlatformPreferences(current, patch)),
      setAutopilot: (patch: Partial<PicoProgressState['autopilot']>) =>
        update((current) => updateAutopilotSettings(current, patch)),
      reset: () => storeAndSync(createDefaultPicoProgress()),
    }),
    [storeAndSync, update],
  )

  const derived = useMemo(() => derivePicoProgress(progress), [progress])

  return {
    ready,
    syncState,
    progress,
    derived,
    actions,
  }
}
