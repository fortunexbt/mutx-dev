'use client'

import { useEffect, useRef, useState } from 'react'
import Link from 'next/link'
import { useTranslations } from 'next-intl'
import { AlertCircle, ArrowLeft, ArrowRight, Loader2, Mail } from 'lucide-react'

import { extractApiErrorMessage } from '@/components/app/http'
import { AuthSurface } from '@/components/site/AuthSurface'
import styles from '@/components/site/marketing/MarketingCore.module.css'

type PicoForgotPasswordPageClientProps = {
  returnPath: string
  hostVariant: 'default' | 'pico'
}

export function PicoForgotPasswordPageClient({
  returnPath,
  hostVariant,
}: PicoForgotPasswordPageClientProps) {
  const t = useTranslations('pico.authRecovery.forgotPassword')
  const errorId = 'forgot-password-error'
  const errorRef = useRef<HTMLDivElement>(null)
  const [email, setEmail] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState(false)
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
    if (error) {
      errorRef.current?.focus()
    }
  }, [error])

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault()
    setLoading(true)
    setError('')
    let failureMessage = t('sendFailed')

    try {
      const response = await fetch('/api/auth/forgot-password', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, return_path: returnPath }),
      })
      const payload = await response.json().catch(() => null)

      if (!response.ok) {
        if (hostVariant === 'default') {
          failureMessage = extractApiErrorMessage(payload, failureMessage)
        }
        throw new Error(failureMessage)
      }

      setSuccess(true)
    } catch {
      setError(failureMessage)
    } finally {
      setLoading(false)
    }
  }

  return (
    <AuthSurface
      {...authSurfaceProps}
      variant="recovery"
      hostVariant={hostVariant}
    >
      {success ? (
        <div className={styles.formWrap}>
          <div className="inline-flex h-14 w-14 items-center justify-center rounded-full border border-emerald-400/20 bg-emerald-400/10">
            <Mail className="h-7 w-7 text-emerald-300" aria-hidden="true" />
          </div>

          <div>
            <h2 className={styles.sectionTitle}>{t('successTitle')}</h2>
            <p className={styles.success} role="status" aria-live="polite" aria-atomic="true">
              {t('successBody', { email })}
            </p>
            <p className={styles.bodyText}>{t('successHint')}</p>
          </div>

          <div className={styles.ctaRow}>
            <Link
              href={`/login?${new URLSearchParams({ next: returnPath }).toString()}`}
              className={styles.buttonPrimary}
            >
              {t('backToSignIn')}
              <ArrowRight className="rtl-directional-icon h-4 w-4" aria-hidden="true" />
            </Link>
            <button type="button" onClick={() => setSuccess(false)} className={styles.buttonSecondary}>
              {t('tryAgain')}
            </button>
          </div>
        </div>
      ) : (
        <div className={styles.formWrap}>
          <div>
            <h2 className={styles.sectionTitle}>{t('sendTitle')}</h2>
            <p className={styles.bodyText}>{t('sendBody')}</p>
          </div>

          <form onSubmit={handleSubmit} className={styles.formWrap} aria-busy={loading}>
            <div className={styles.field}>
              <label htmlFor="forgot-password-email" className={styles.fieldLabel}>
                {t('emailLabel')}
              </label>
              <input
                id="forgot-password-email"
                type="email"
                value={email}
                onChange={(event) => {
                  setEmail(event.target.value)
                  setError('')
                }}
                placeholder={t('emailPlaceholder')}
                autoComplete="email"
                dir="ltr"
                required
                aria-invalid={error ? true : undefined}
                aria-describedby={error ? errorId : undefined}
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
                  {t('sending')}
                </>
              ) : (
                <>
                  {t('sendLink')}
                  <ArrowRight className="rtl-directional-icon h-4 w-4" aria-hidden="true" />
                </>
              )}
            </button>
          </form>

          <Link
            href={`/login?${new URLSearchParams({ next: returnPath }).toString()}`}
            className={styles.inlineLink}
          >
            <ArrowLeft className="rtl-directional-icon h-4 w-4" aria-hidden="true" />
            {t('backToSignIn')}
          </Link>
        </div>
      )}
    </AuthSurface>
  )
}
