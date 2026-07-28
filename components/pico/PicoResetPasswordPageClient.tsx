'use client'

import { useEffect, useRef, useState } from 'react'
import Link from 'next/link'
import { useTranslations } from 'next-intl'
import { useSearchParams } from 'next/navigation'
import { AlertCircle, ArrowLeft, ArrowRight, Loader2, Lock } from 'lucide-react'

import { extractApiErrorMessage } from '@/components/app/http'
import { AuthSurface } from '@/components/site/AuthSurface'
import styles from '@/components/site/marketing/MarketingCore.module.css'
import { resolveRedirectPath } from '@/lib/auth/redirects'

type PicoResetPasswordPageClientProps = {
  fallbackPath: string
  hostVariant: 'default' | 'pico'
}

type ResetErrorTarget = 'password' | 'confirmPassword' | 'form' | null

export function PicoResetPasswordPageClient({
  fallbackPath,
  hostVariant,
}: PicoResetPasswordPageClientProps) {
  const searchParams = useSearchParams()
  const token = searchParams.get('token')
  const t = useTranslations('pico.authRecovery.resetPassword')
  const errorId = 'reset-password-error'
  const errorRef = useRef<HTMLDivElement>(null)
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [errorTarget, setErrorTarget] = useState<ResetErrorTarget>(null)
  const [success, setSuccess] = useState(false)
  const [verifiedReturnPath, setVerifiedReturnPath] = useState(fallbackPath)
  const loginHref = `/login?${new URLSearchParams({ next: verifiedReturnPath }).toString()}`
  const forgotPasswordHref = `/forgot-password?${new URLSearchParams({ next: fallbackPath }).toString()}`
  const authSurfaceProps = {
    eyebrow: t('eyebrow'),
    title: t('title'),
    description: t('description'),
    asideEyebrow: t('asideEyebrow'),
    asideTitle: t('asideTitle'),
    asideBody: t('asideBody'),
    highlights: t.raw('highlights') as string[],
  }

  useEffect(() => {
    if (!token || error) {
      errorRef.current?.focus()
    }
  }, [error, token])

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault()
    setError('')
    setErrorTarget(null)

    if (password !== confirmPassword) {
      setError(t('passwordsMismatch'))
      setErrorTarget('confirmPassword')
      return
    }

    if (password.length < 8) {
      setError(t('passwordTooShort'))
      setErrorTarget('password')
      return
    }

    setLoading(true)
    let failureMessage = t('invalidBody')

    try {
      const response = await fetch('/api/auth/reset-password', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token, new_password: password }),
      })
      const payload = await response.json().catch(() => null)

      if (!response.ok) {
        if (hostVariant === 'default') {
          failureMessage = extractApiErrorMessage(payload, failureMessage)
        }
        throw new Error(failureMessage)
      }

      setVerifiedReturnPath(
        resolveRedirectPath(
          typeof payload?.return_path === 'string' ? payload.return_path : null,
          fallbackPath,
        ),
      )
      setSuccess(true)
    } catch {
      setErrorTarget('form')
      setError(failureMessage)
    } finally {
      setLoading(false)
    }
  }

  if (!token) {
    return (
      <AuthSurface {...authSurfaceProps} variant="recovery" hostVariant={hostVariant}>
        <div className={styles.formWrap}>
          <div className="inline-flex h-14 w-14 items-center justify-center rounded-full border border-rose-400/20 bg-rose-400/10">
            <AlertCircle className="h-7 w-7 text-rose-300" aria-hidden="true" />
          </div>

          <div>
            <h2 className={styles.sectionTitle}>{t('invalidTitle')}</h2>
            <p
              ref={errorRef}
              className={styles.error}
              role="alert"
              aria-live="assertive"
              aria-atomic="true"
              tabIndex={-1}
            >
              {t('invalidBody')}
            </p>
          </div>

          <div className={styles.ctaRow}>
            <Link href={forgotPasswordHref} className={styles.buttonPrimary}>
              {t('requestNewLink')}
              <ArrowRight className="rtl-directional-icon h-4 w-4" aria-hidden="true" />
            </Link>
            <Link href={loginHref} className={styles.buttonSecondary}>
              {t('backToSignIn')}
              <ArrowLeft className="rtl-directional-icon h-4 w-4" aria-hidden="true" />
            </Link>
          </div>
        </div>
      </AuthSurface>
    )
  }

  if (success) {
    return (
      <AuthSurface {...authSurfaceProps} variant="recovery" hostVariant={hostVariant}>
        <div className={styles.formWrap}>
          <div className="inline-flex h-14 w-14 items-center justify-center rounded-full border border-emerald-400/20 bg-emerald-400/10">
            <Lock className="h-7 w-7 text-emerald-300" aria-hidden="true" />
          </div>

          <div>
            <h2 className={styles.sectionTitle}>{t('completeTitle')}</h2>
            <p className={styles.success} role="status" aria-live="polite" aria-atomic="true">
              {t('completeBody')}
            </p>
          </div>

          <Link href={loginHref} className={styles.buttonPrimary}>
            {t('signIn')}
            <ArrowRight className="rtl-directional-icon h-4 w-4" aria-hidden="true" />
          </Link>
        </div>
      </AuthSurface>
    )
  }

  return (
    <AuthSurface {...authSurfaceProps} variant="recovery" hostVariant={hostVariant}>
      <div className={styles.formWrap}>
        <div>
          <h2 className={styles.sectionTitle}>{t('formTitle')}</h2>
          <p className={styles.bodyText}>{t('formBody')}</p>
        </div>

        <form
          onSubmit={handleSubmit}
          className={styles.formWrap}
          aria-describedby={error && errorTarget === 'form' ? errorId : undefined}
          aria-busy={loading}
        >
          <div className={styles.field}>
            <label htmlFor="reset-password" className={styles.fieldLabel}>
              {t('newPassword')}
            </label>
            <input
              id="reset-password"
              type="password"
              value={password}
              onChange={(event) => {
                setPassword(event.target.value)
                setError('')
                setErrorTarget(null)
              }}
              placeholder="••••••••"
              autoComplete="new-password"
              required
              minLength={8}
              aria-invalid={error && errorTarget === 'password' ? true : undefined}
              aria-describedby={error && errorTarget === 'password' ? errorId : undefined}
              className={styles.input}
            />
          </div>

          <div className={styles.field}>
            <label htmlFor="reset-password-confirmation" className={styles.fieldLabel}>
              {t('confirmPassword')}
            </label>
            <input
              id="reset-password-confirmation"
              type="password"
              value={confirmPassword}
              onChange={(event) => {
                setConfirmPassword(event.target.value)
                setError('')
                setErrorTarget(null)
              }}
              placeholder="••••••••"
              autoComplete="new-password"
              required
              minLength={8}
              aria-invalid={error && errorTarget === 'confirmPassword' ? true : undefined}
              aria-describedby={error && errorTarget === 'confirmPassword' ? errorId : undefined}
              className={styles.input}
            />
          </div>

          {error ? (
            <div
              ref={errorRef}
              id={errorId}
              className={styles.error}
              role="alert"
              aria-live="assertive"
              aria-atomic="true"
              tabIndex={-1}
            >
              <AlertCircle className="h-4 w-4" aria-hidden="true" />
              {error}
            </div>
          ) : null}

          <button
            type="submit"
            disabled={loading}
            className={`${styles.buttonPrimary} w-full disabled:cursor-not-allowed disabled:opacity-60`}
          >
            {loading ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden="true" />
                {t('resetting')}
              </>
            ) : (
              <>
                {t('resetPassword')}
                <ArrowRight className="rtl-directional-icon h-4 w-4" aria-hidden="true" />
              </>
            )}
          </button>
        </form>

        <Link href={loginHref} className={styles.inlineLink}>
          <ArrowLeft className="rtl-directional-icon h-4 w-4" aria-hidden="true" />
          {t('backToSignIn')}
        </Link>
      </div>
    </AuthSurface>
  )
}
