import {
  applyLessonCompleted,
  createDefaultPicoProgress,
  updateLessonWorkspace,
  updatePlatformPreferences,
} from '../../lib/pico/academy'
import {
  createPicoProgressSyncCoordinator,
  resolveHydratedPicoProgress,
  shouldSyncHydratedProgress,
  type PicoProgressRemoteWriteResult,
} from '../../components/pico/usePicoProgress'

function createDeferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise
    reject = rejectPromise
  })

  return { promise, reject, resolve }
}

async function flushPromises() {
  await Promise.resolve()
  await Promise.resolve()
}

function createCompletedInstallProgress() {
  const withCheckpoint = updateLessonWorkspace(
    createDefaultPicoProgress(),
    'install-hermes-locally',
    {
      activeStepIndex: 2,
      completedStepIndexes: [0, 1, 2],
      notes: '',
      evidence: 'Hermes opened successfully from a fresh shell.',
      updatedAt: '2026-04-12T10:00:00.000Z',
    },
  )

  return applyLessonCompleted(withCheckpoint, 'install-hermes-locally')
}

describe('pico progress hydration sync', () => {
  it('syncs merged local progress back to the backend when remote progress is stale', () => {
    const remote = createDefaultPicoProgress()
    const merged = createCompletedInstallProgress()

    expect(shouldSyncHydratedProgress(remote, merged)).toBe(true)
  })

  it('does not resync when the merged progress already matches the backend', () => {
    const remote = createCompletedInstallProgress()

    expect(shouldSyncHydratedProgress(remote, remote)).toBe(false)
  })

  it('resyncs when platform or lesson workspace preferences change locally', () => {
    const remote = createDefaultPicoProgress()
    const withPlatform = updatePlatformPreferences(remote, {
      activeSurface: 'academy',
      lastOpenedLessonSlug: 'install-hermes-locally',
      railCollapsed: true,
      helpLaneOpen: true,
    })
    const withWorkspace = updateLessonWorkspace(withPlatform, 'install-hermes-locally', {
      activeStepIndex: 1,
      completedStepIndexes: [0],
      notes: 'save this',
      evidence: 'proof',
      updatedAt: new Date().toISOString(),
    })

    expect(shouldSyncHydratedProgress(remote, withWorkspace)).toBe(true)
  })

  it('keeps newer local state when a remote hydration request arrives late', () => {
    const remote = createCompletedInstallProgress()
    const currentLocal = updatePlatformPreferences(createDefaultPicoProgress(), {
      activeSurface: 'academy',
      railCollapsed: true,
      helpLaneOpen: false,
    })

    const merged = resolveHydratedPicoProgress(remote, currentLocal, true)

    expect(merged.platform.activeSurface).toBe('academy')
    expect(merged.platform.railCollapsed).toBe(true)
    expect(merged.completedLessons).not.toContain('install-hermes-locally')
  })

  it('serializes writes, coalesces overlap, and ignores the older response', async () => {
    const firstWrite = createDeferred<PicoProgressRemoteWriteResult>()
    const latestWrite = createDeferred<{
      ok: true
      progress: ReturnType<typeof createDefaultPicoProgress>
    }>()
    const send = jest
      .fn()
      .mockImplementationOnce(() => firstWrite.promise)
      .mockImplementationOnce(() => latestWrite.promise)
    const onAccepted = jest.fn()
    const onSyncState = jest.fn()
    const coordinator = createPicoProgressSyncCoordinator({
      send,
      onAccepted,
      onSyncState,
    })
    const first = updatePlatformPreferences(createDefaultPicoProgress(), {
      activeSurface: 'academy',
    })
    const skipped = updatePlatformPreferences(first, {
      railCollapsed: true,
    })
    const latest = updatePlatformPreferences(skipped, {
      helpLaneOpen: true,
    })

    coordinator.enqueue(first, 1)
    coordinator.enqueue(skipped, 2)
    coordinator.enqueue(latest, 3)

    expect(send).toHaveBeenCalledTimes(1)

    firstWrite.resolve({ ok: false, syncState: 'error' })
    await flushPromises()

    expect(onAccepted).not.toHaveBeenCalled()
    expect(onSyncState).not.toHaveBeenCalledWith('error')
    expect(send).toHaveBeenCalledTimes(2)
    expect(send.mock.calls[1][0]).toEqual(latest)

    latestWrite.resolve({ ok: true, progress: latest })
    await flushPromises()

    expect(onAccepted).toHaveBeenCalledTimes(1)
    expect(onAccepted).toHaveBeenCalledWith(latest, 3)
    expect(onSyncState).toHaveBeenLastCalledWith('synced')
  })

  it('aborts the active write and suppresses callbacks after disposal', async () => {
    const write = createDeferred<{
      ok: true
      progress: ReturnType<typeof createDefaultPicoProgress>
    }>()
    let requestSignal: AbortSignal | null = null
    const onAccepted = jest.fn()
    const onSyncState = jest.fn()
    const coordinator = createPicoProgressSyncCoordinator({
      send: (_progress, signal) => {
        requestSignal = signal
        return write.promise
      },
      onAccepted,
      onSyncState,
    })
    const progress = updatePlatformPreferences(createDefaultPicoProgress(), {
      activeSurface: 'academy',
    })

    coordinator.enqueue(progress, 1)
    coordinator.dispose()
    write.resolve({ ok: true, progress })
    await flushPromises()

    expect((requestSignal as AbortSignal | null)?.aborted).toBe(true)
    expect(onAccepted).not.toHaveBeenCalled()
    expect(onSyncState).not.toHaveBeenCalledWith('synced')
  })
})
