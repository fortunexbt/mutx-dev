'use client'

import type { ReactNode } from 'react'
import { useEffect, useState } from 'react'
import { usePathname } from 'next/navigation'
import { AlertTriangle, Loader2, RefreshCw } from 'lucide-react'

import {
  DashboardAccessError,
  resolveDashboardAccess,
} from '@/components/dashboard/dashboardAccess'
import { LiveAuthRequired, LiveForbidden, LivePanel } from '@/components/dashboard/livePrimitives'
import visualContract from '@/components/dashboard/dashboardVisualContract.module.css'
import { useDesktopStatus } from '@/components/desktop/useDesktopStatus'
import { useMissionControl } from '@/lib/store'
import { cn } from '@/lib/utils'

type AccessState =
  | { status: 'checking' }
  | { status: 'authenticated' }
  | { status: 'unauthenticated'; reason: 'missing_session' | 'expired_session' | 'access_denied' }
  | { status: 'error'; message: string }

function DashboardAccessFrame({ children }: { children: ReactNode }) {
  return (
    <div
      className={cn(
        'dashboard-app min-h-screen bg-[#090a08] px-4 py-10 text-[#eee9dc] sm:px-6 lg:px-8 lg:py-16',
        visualContract.visualContract,
      )}
      data-dashboard-theme='flight-recorder'
    >
      <main id='main-content' tabIndex={-1} className='mx-auto w-full max-w-4xl'>
        {children}
      </main>
    </div>
  )
}

function DashboardAccessLoading({ platformReady }: { platformReady: boolean }) {
  return (
    <DashboardAccessFrame>
      <LivePanel title='Dashboard access' meta='checking'>
        <div role='status' aria-live='polite' aria-busy='true' className='flex items-start gap-4 py-4'>
          <Loader2
            className='mt-0.5 h-5 w-5 shrink-0 animate-spin text-[#58aaff] motion-reduce:animate-none'
            aria-hidden='true'
          />
          <div>
            <h1 className='font-[family:var(--font-site-display)] text-2xl font-medium tracking-[-0.045em] text-[#eee9dc]'>
              {platformReady ? 'Verifying your operator session' : 'Resolving dashboard runtime'}
            </h1>
            <p className='mt-2 max-w-2xl text-sm leading-6 text-[#aaa397]'>
              Workspace records stay hidden until MUTX confirms which dashboard surface and account
              are available.
            </p>
          </div>
        </div>
      </LivePanel>
    </DashboardAccessFrame>
  )
}

function DashboardAccessFailure({ message, retry }: { message: string; retry: () => void }) {
  return (
    <DashboardAccessFrame>
      <LivePanel title='Dashboard access' meta='unavailable'>
        <div role='alert' className='flex items-start gap-4 py-4'>
          <AlertTriangle className='mt-0.5 h-5 w-5 shrink-0 text-[#ff9b96]' aria-hidden='true' />
          <div>
            <h1 className='font-[family:var(--font-site-display)] text-2xl font-medium tracking-[-0.045em] text-[#eee9dc]'>
              Dashboard access could not be verified
            </h1>
            <p className='mt-2 max-w-2xl text-sm leading-6 text-[#aaa397]'>{message}</p>
            <button
              type='button'
              onClick={retry}
              className='mt-5 inline-flex min-h-11 items-center gap-2 rounded-[4px] border border-[#ff6a32] bg-[#ff571c] px-4 text-sm font-semibold text-[#090a08] transition-colors hover:bg-[#ff7545] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-[#ff9a72] motion-reduce:transition-none'
            >
              <RefreshCw className='h-4 w-4' aria-hidden='true' />
              Retry access check
            </button>
          </div>
        </div>
      </LivePanel>
    </DashboardAccessFrame>
  )
}

export function DashboardAuthBoundary({ children }: { children: ReactNode }) {
  const pathname = usePathname()
  const { isDesktop, platformReady } = useDesktopStatus()
  const setCurrentUser = useMissionControl((state) => state.setCurrentUser)
  const [attempt, setAttempt] = useState(0)
  const [access, setAccess] = useState<AccessState>({ status: 'checking' })

  useEffect(() => {
    if (!platformReady || isDesktop) return

    const controller = new AbortController()
    setAccess({ status: 'checking' })

    void resolveDashboardAccess(fetch, controller.signal)
      .then((result) => {
        if (controller.signal.aborted) return

        if (result.authenticated) {
          setCurrentUser(result.user)
          setAccess({ status: 'authenticated' })
          return
        }

        setCurrentUser(null)
        setAccess({ status: 'unauthenticated', reason: result.reason })
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return

        setCurrentUser(null)
        setAccess({
          status: 'error',
          message:
            error instanceof DashboardAccessError
              ? error.message
              : 'The access service did not return a usable response. Your workspace data remains hidden.',
        })
      })

    return () => controller.abort()
  }, [attempt, isDesktop, platformReady, setCurrentUser])

  if (platformReady && isDesktop) {
    return <>{children}</>
  }

  if (!platformReady || access.status === 'checking') {
    return <DashboardAccessLoading platformReady={platformReady} />
  }

  if (access.status === 'authenticated') {
    return <>{children}</>
  }

  if (access.status === 'unauthenticated') {
    const search = typeof window === 'undefined' ? '' : window.location.search
    const nextPath = `${pathname}${search}`
    if (access.reason === 'access_denied') {
      return (
        <DashboardAccessFrame>
          <LiveForbidden
            title='Dashboard permission required'
            message='Authentication succeeded, but this account does not have permission to open the private dashboard. Ask a workspace administrator to grant an approved dashboard role.'
          />
        </DashboardAccessFrame>
      )
    }
    const message =
      access.reason === 'expired_session'
          ? 'Your previous session expired. Sign in again to load workspace records, or recover your password if you cannot continue.'
          : 'Sign in to load private workspace records. If you cannot access your account, use password recovery to continue.'

    return (
      <DashboardAccessFrame>
        <LiveAuthRequired
          title='Sign in to open the dashboard'
          message={message}
          nextPath={nextPath}
        />
      </DashboardAccessFrame>
    )
  }

  return <DashboardAccessFailure message={access.message} retry={() => setAttempt((value) => value + 1)} />
}
