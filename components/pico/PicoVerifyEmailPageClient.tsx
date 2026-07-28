'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import Link from 'next/link'
import { useTranslations } from 'next-intl'
import { useSearchParams } from 'next/navigation'
import {
  AlertCircle,
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  Loader2,
  Mail,
} from 'lucide-react'

import { AuthSurface } from '@/components/site/AuthSurface'
import styles from '@/components/site/marketing/MarketingCore.module.css'
import { resolveRedirectPath } from '@/lib/auth/redirects'

type PicoVerifyEmailPageClientProps = {
  fallbackPath: string
  hostVariant: 'default' | 'pico'
}

type VerifyEmailStatus = 'pending' | 'loading' | 'success' | 'error'

export function PicoVerifyEmailPageClient({
  fallbackPath,
  hostVariant,
}: PicoVerifyEmailPageClientProps) {
  const searchParams = useSearchParams()
  const token = searchParams.get('token')
  const email = searchParams.get('email')
  const deliveryFailed = searchParams.get('delivery') === 'failed'
  const requestedNextPath = resolveRedirectPath(searchParams.get('next'), fallbackPath)
  const t = useTranslations('pico.authRecovery.verifyEmail')
  const errorRef = useRef<HTMLDivElement>(null)
  const [status, setStatus] = useState<VerifyEmailStatus>(
    token ? 'loading' : email && !deliveryFailed ? 'pending' : 'error',
  )
  const [message, setMessage] = useState(
    token
      ? t('verifying')
      : email && deliveryFailed
        ? t('resendFailure')
        : email
          ? t('sentTo', { email })
          : t('missingContext'),
  )
  const [resending, setResending] = useState(false)
  const [verifiedReturnPath, setVerifiedReturnPath] = useState<string | null>(null)
  const nextPath = token
    ? verifiedReturnPath ?? fallbackPath
    : requestedNextPath
  const authSurfaceProps = {
    eyebrow: t('eyebrow'),
    title: t('title'),
    description: t('description'),
    asideEyebrow: t('asideEyebrow'),
    asideTitle: t('asideTitle'),
    asideBody: t('asideBody'),
    highlights: t.raw('highlights') as string[],
  }
  const loginHref = useMemo(() => {
    const params = new URLSearchParams({ next: nextPath })
    if (email) {
      params.set('email', email)
    }
    return `/login?${params.toString()}`
  }, [email, nextPath])

  useEffect(() => {
    if (status === 'error') {
      errorRef.current?.focus()
    }
  }, [status, message])

  useEffect(() => {
    if (!token) {
      return
    }

    const controller = new AbortController()

    async function verify() {
      setStatus('loading')
      setMessage(t('verifying'))

      try {
        const response = await fetch('/api/auth/verify-email', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ token }),
          signal: controller.signal,
        })
        const payload = await response.json().catch(() => null)

        if (!response.ok) {
          throw new Error(
            hostVariant === 'default' && typeof payload?.detail === 'string' && payload.detail
              ? payload.detail
              : t('verifyFailure'),
          )
        }

        setStatus('success')
        setVerifiedReturnPath(
          resolveRedirectPath(
            typeof payload?.return_path === 'string' ? payload.return_path : null,
            fallbackPath,
          ),
        )
        setMessage(
          hostVariant === 'default' && typeof payload?.message === 'string' && payload.message
            ? payload.message
            : t('verifySuccess'),
        )
      } catch (error) {
        if (controller.signal.aborted) {
          return
        }
        setStatus('error')
        setMessage(error instanceof Error ? error.message : t('verifyFailure'))
      }
    }

    void verify()
    return () => controller.abort()
  }, [fallbackPath, hostVariant, t, token])

  async function handleResend() {
    if (!email) {
      setStatus('error')
      setMessage(t('resendNeedsEmail'))
      return
    }

    setResending(true)

    try {
      const response = await fetch('/api/auth/resend-verification', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, return_path: nextPath }),
      })
      const payload = await response.json().catch(() => null)

      if (!response.ok) {
        throw new Error(
          hostVariant === 'default' && typeof payload?.detail === 'string' && payload.detail
            ? payload.detail
            : t('resendFailure'),
        )
      }

      setStatus('pending')
      setMessage(t('resendSent', { email }))
    } catch (error) {
      setStatus('error')
      setMessage(error instanceof Error ? error.message : t('resendFailure'))
    } finally {
      setResending(false)
    }
  }

  return (
    <AuthSurface
      {...authSurfaceProps}
      variant="recovery"
      hostVariant={hostVariant}
    >
      <div className={styles.formWrap} aria-busy={resending || status === 'loading'}>
        {status === 'loading' ? (
          <div className={styles.success} role="status" aria-live="polite" aria-atomic="true">
            <Loader2 className="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden="true" />
            {message}
          </div>
        ) : null}

        {status === 'success' ? (
          <>
            <div className={styles.success} role="status" aria-live="polite" aria-atomic="true">
              <CheckCircle2 className="h-4 w-4" aria-hidden="true" />
              {message}
            </div>
            <div>
              <h2 className={styles.sectionTitle}>{t('verificationComplete')}</h2>
              <p className={styles.bodyText}>{t('verificationCompleteBody')}</p>
            </div>
            <div className={styles.ctaRow}>
              <Link href={loginHref} className={styles.buttonPrimary}>
                {t('signIn')}
                <ArrowRight className="rtl-directional-icon h-4 w-4" aria-hidden="true" />
              </Link>
            </div>
          </>
        ) : null}

        {status === 'pending' ? (
          <>
            <div className={styles.success} role="status" aria-live="polite" aria-atomic="true">
              <Mail className="h-4 w-4" aria-hidden="true" />
              {message}
            </div>
            <div>
              <h2 className={styles.sectionTitle}>{t('checkInbox')}</h2>
              <p className={styles.bodyText}>{t('checkInboxBody')}</p>
            </div>
            <div className={styles.ctaRow}>
              <button
                type="button"
                onClick={() => void handleResend()}
                disabled={resending}
                className={styles.buttonPrimary}
              >
                {resending ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden="true" />
                    {t('resendSending')}
                  </>
                ) : (
                  <>
                    {t('resend')}
                    <ArrowRight className="rtl-directional-icon h-4 w-4" aria-hidden="true" />
                  </>
                )}
              </button>
              <Link href={loginHref} className={styles.buttonSecondary}>
                {t('signIn')}
                <ArrowLeft className="rtl-directional-icon h-4 w-4" aria-hidden="true" />
              </Link>
            </div>
          </>
        ) : null}

        {status === 'error' ? (
          <>
            <div
              ref={errorRef}
              className={styles.error}
              role="alert"
              aria-live="assertive"
              aria-atomic="true"
              tabIndex={-1}
            >
              <AlertCircle className="h-4 w-4" aria-hidden="true" />
              {message}
            </div>
            <div>
              <h2 className={styles.sectionTitle}>{t('verificationFailed')}</h2>
              <p className={styles.bodyText}>{t('verificationFailedBody')}</p>
            </div>
            <div className={styles.ctaRow}>
              {email ? (
                <button
                  type="button"
                  onClick={() => void handleResend()}
                  disabled={resending}
                  className={styles.buttonPrimary}
                >
                  {resending ? (
                    <>
                      <Loader2 className="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden="true" />
                      {t('resendSending')}
                    </>
                  ) : (
                    <>
                      {t('resend')}
                      <ArrowRight className="rtl-directional-icon h-4 w-4" aria-hidden="true" />
                    </>
                  )}
                </button>
              ) : null}
              <Link href={loginHref} className={styles.buttonSecondary}>
                {t('signIn')}
                <ArrowLeft className="rtl-directional-icon h-4 w-4" aria-hidden="true" />
              </Link>
            </div>
          </>
        ) : null}
      </div>
    </AuthSurface>
  )
}
