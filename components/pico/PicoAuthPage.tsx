'use client'

import { useEffect, useRef, useState } from 'react'
import Link from 'next/link'
import { useLocale, useTranslations } from 'next-intl'
import { useRouter } from 'next/navigation'

import { extractApiErrorMessage } from '@/components/app/http'
import { buildOAuthStartHref, oauthProviders } from '@/lib/auth/oauth'
import { resolveRedirectPath } from '@/lib/auth/redirects'
import { getPicoDirection } from '@/lib/pico/locale'

/* ------------------------------------------------------------------ */
/*  Constants                                                          */
/* ------------------------------------------------------------------ */

type PicoAuthPageProps = {
  mode: 'login' | 'register'
  nextPath?: string | null
  fallbackPath?: string
  initialError?: string | null
  initialEmail?: string | null
}

type PicoAuthErrorTarget =
  | 'email'
  | 'password'
  | 'confirmPassword'
  | 'credentials'
  | 'form'
  | null

/* ---- Pico design tokens (hardcoded so this page works anywhere) ---- */

const c = {
  bg: '#0a0a09',
  bgGrad: '#0a0a09',
  panelBg: '#11110f',
  panelShadow: 'none',
  text: '#f3f0e8',
  text2: 'rgba(243,240,232,0.8)',
  muted: 'rgba(243,240,232,0.58)',
  dividerText: '#a7a39b',
  dividerLine: '#6d6a63',
  accent: '#ff4d00',
  accentRgb: '255,77,0',
  accentContrast: '#0a0a09',
  border: 'rgba(243,240,232,0.18)',
  borderHover: 'rgba(255,77,0,0.72)',
  inputBg: '#0a0a09',
  red: '#ff8c72',
  radius: '1.2rem',
  radiusSm: '0.75rem',
  radiusFull: '999px',
  fontMono: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
  fontDisplay: 'ui-serif, Georgia, Cambria, Times New Roman, serif',
}

/* ---- OAuth provider SVG icons ---- */

function GoogleIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24">
      <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z" fill="#4285F4"/>
      <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/>
      <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"/>
      <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/>
    </svg>
  )
}

function GitHubIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
      <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0 0 24 12c0-6.63-5.37-12-12-12z"/>
    </svg>
  )
}

function DiscordIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
      <path d="M20.317 4.37a19.791 19.791 0 0 0-4.885-1.515.074.074 0 0 0-.079.037c-.21.375-.444.864-.608 1.25a18.27 18.27 0 0 0-5.487 0 12.64 12.64 0 0 0-.617-1.25.077.077 0 0 0-.079-.037A19.736 19.736 0 0 0 3.677 4.37a.07.07 0 0 0-.032.027C.533 9.046-.32 13.58.099 18.057a.082.082 0 0 0 .031.057 19.9 19.9 0 0 0 5.993 3.03.078.078 0 0 0 .084-.028c.462-.63.874-1.295 1.226-1.994a.076.076 0 0 0-.041-.106 13.107 13.107 0 0 1-1.872-.892.077.077 0 0 1-.008-.128 10.2 10.2 0 0 0 .372-.292.074.074 0 0 1 .077-.01c3.928 1.793 8.18 1.793 12.062 0a.074.074 0 0 1 .078.01c.12.098.246.198.373.292a.077.077 0 0 1-.006.127 12.299 12.299 0 0 1-1.873.892.077.077 0 0 0-.041.107c.36.698.772 1.362 1.225 1.993a.076.076 0 0 0 .084.028 19.839 19.839 0 0 0 6.002-3.03.077.077 0 0 0 .032-.054c.5-5.177-.838-9.674-3.549-13.66a.061.061 0 0 0-.031-.03zM8.02 15.33c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.956-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.956 2.418-2.157 2.418zm7.975 0c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.955-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.946 2.418-2.157 2.418z"/>
    </svg>
  )
}

function AppleIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
      <path d="M17.05 20.28c-.98.95-2.05.88-3.08.4-1.09-.5-2.08-.48-3.24 0-1.44.62-2.2.44-3.06-.4C2.79 15.25 3.51 7.59 9.05 7.31c1.35.07 2.29.74 3.08.8 1.18-.24 2.31-.93 3.57-.84 1.51.12 2.65.72 3.4 1.8-3.12 1.87-2.38 5.98.48 7.13-.57 1.5-1.31 2.99-2.54 4.09zM12.03 7.25c-.15-2.23 1.66-4.07 3.74-4.25.29 2.58-2.34 4.5-3.74 4.25z"/>
    </svg>
  )
}

const providerIcons: Record<string, () => React.ReactElement> = {
  google: GoogleIcon,
  github: GitHubIcon,
  discord: DiscordIcon,
  apple: AppleIcon,
}

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

export function PicoAuthPage({
  mode,
  nextPath,
  fallbackPath = '/',
  initialError,
  initialEmail,
}: PicoAuthPageProps) {
  const router = useRouter()
  const locale = useLocale()
  const t = useTranslations('pico.auth')
  const isRegister = mode === 'register'
  const modeKey = isRegister ? 'register' : 'login'
  const redirectPath = resolveRedirectPath(nextPath, fallbackPath)

  const [name, setName] = useState('')
  const [email, setEmail] = useState(initialEmail ?? '')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [error, setError] = useState(initialError ?? '')
  const [errorTarget, setErrorTarget] = useState<PicoAuthErrorTarget>(
    initialError ? 'form' : null,
  )
  const [notice, setNotice] = useState('')
  const [loading, setLoading] = useState(false)
  const [resending, setResending] = useState(false)
  const errorSummaryRef = useRef<HTMLDivElement>(null)
  const errorSummaryId = `pico-${mode}-error-summary`

  const verificationError = /verification/i.test(error)

  useEffect(() => {
    if (error) {
      errorSummaryRef.current?.focus()
    }
  }, [error])

  function clearError() {
    setError('')
    setErrorTarget(null)
  }

  /* ---- Submit ---- */

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (isRegister && password !== confirmPassword) {
      setError(t('errors.passwordMismatch'))
      setErrorTarget('confirmPassword')
      return
    }
    if (isRegister && password.length < 8) {
      setError(t('errors.passwordTooShort'))
      setErrorTarget('password')
      return
    }

    setLoading(true)
    clearError()
    setNotice('')

    try {
      const payload = mode === 'login' ? { email, password } : { email, password, name }
      const res = await fetch(mode === 'login' ? '/api/auth/login' : '/api/auth/register', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })

      const data = await res.json().catch(() => ({
        detail: t(`errors.${mode === 'login' ? 'loginFailed' : 'registerFailed'}`),
      }))

      if (!res.ok) {
        throw new Error(extractApiErrorMessage(data, t(`errors.${mode === 'login' ? 'loginFailed' : 'registerFailed'}`)))
      }

      if (isRegister && data.requires_email_verification) {
        const params = new URLSearchParams({ email, next: redirectPath })
        if (data.verification_email_sent === false) params.set('delivery', 'failed')
        router.replace(`/verify-email?${params.toString()}`)
        router.refresh()
        return
      }

      router.replace(redirectPath)
      router.refresh()
    } catch (err) {
      setErrorTarget(mode === 'login' ? 'credentials' : 'form')
      setError(err instanceof Error ? err.message : t(`errors.${mode === 'login' ? 'loginFailed' : 'registerFailed'}`))
    } finally {
      setLoading(false)
    }
  }

  /* ---- Resend ---- */

  async function handleResend() {
    if (!email) {
      setErrorTarget('email')
      setError(t('errors.emailRequired'))
      return
    }
    setResending(true)
    clearError()
    setNotice('')
    try {
      const res = await fetch('/api/auth/resend-verification', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email }),
      })
      const data = await res.json().catch(() => ({ detail: t('errors.resendFailed') }))
      if (!res.ok) throw new Error(extractApiErrorMessage(data, t('errors.resendFailed')))
      setNotice(data.message || t('notice.verificationSent'))
    } catch (err) {
      setErrorTarget('email')
      setError(err instanceof Error ? err.message : t('errors.resendFailed'))
    } finally {
      setResending(false)
    }
  }

  /* ---- Shared inline styles ---- */

  const inputStyle: React.CSSProperties = {
    width: '100%',
    minHeight: '2.75rem',
    padding: '0.7rem 1rem',
    borderRadius: c.radiusSm,
    border: `1px solid ${c.border}`,
    background: c.inputBg,
    color: c.text,
    fontSize: '0.9rem',
    outline: 'none',
    transition: 'border-color 0.2s, box-shadow 0.2s',
  }

  const labelStyle: React.CSSProperties = {
    display: 'block',
    fontFamily: c.fontMono,
    fontSize: '0.7rem',
    fontWeight: 600,
    textTransform: 'uppercase' as const,
    letterSpacing: '0.12em',
    color: c.muted,
    marginBottom: '0.4rem',
  }

  /* ---- Render ---- */

  return (
    <div lang={locale} dir={getPicoDirection(locale)} style={{
      minHeight: '100vh',
      background: c.bgGrad,
      backgroundColor: c.bg,
      color: c.text,
      display: 'flex',
      flexDirection: 'column',
    }}>
      {/* Header */}
      <header style={{ width: '100%', padding: '1.25rem 1.5rem' }}>
        <div style={{ maxWidth: '80rem', margin: '0 auto', display: 'flex', alignItems: 'center' }}>
          <Link href="/" style={{
            display: 'inline-flex',
            minHeight: '2.75rem',
            alignItems: 'center',
            fontFamily: c.fontDisplay,
            fontSize: '1.15rem',
            fontWeight: 700,
            letterSpacing: '-0.04em',
            color: c.text,
            textDecoration: 'none',
            transition: 'color 0.2s',
          }}>
            PicoMUTX
          </Link>
        </div>
      </header>

      {/* Main */}
      <main id="main-content" style={{ flex: 1, display: 'flex', alignItems: 'flex-start', justifyContent: 'center', padding: '2rem 1rem 4rem' }}>
        <div style={{ width: '100%', maxWidth: '420px' }}>
          {/* Title */}
          <div style={{ textAlign: 'center', marginBottom: '2rem' }}>
            <p
              style={{
                fontFamily: c.fontMono,
                fontSize: '0.65rem',
                textTransform: 'uppercase',
                letterSpacing: '0.2em',
                color: c.muted,
                marginBottom: '0.75rem',
              }}
            >
              {t('eyebrow')}
            </p>
            <h1
              style={{
                fontFamily: c.fontDisplay,
                fontSize: 'clamp(1.5rem, 4vw, 2rem)',
                fontWeight: 700,
                lineHeight: 1.2,
                color: c.text,
                marginBottom: '0.5rem',
              }}
            >
              {t(`modes.${modeKey}.title`)}
            </h1>
            <p style={{ color: c.text2, fontSize: '0.9rem', lineHeight: 1.6 }}>
              {t(`modes.${modeKey}.subtitle`)}
            </p>
          </div>

          {/* Panel */}
          <div style={{
            background: c.panelBg,
            borderRadius: c.radius,
            boxShadow: c.panelShadow,
            padding: '1.75rem',
          }}>
            {/* OAuth buttons */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.625rem' }}>
              {oauthProviders.map((provider) => {
                const Icon = providerIcons[provider.id] ?? null
                return (
                  <a
                    key={provider.id}
                    href={buildOAuthStartHref(provider.id, mode, redirectPath)}
                    style={{
                      display: 'flex',
                      minHeight: '2.75rem',
                      alignItems: 'center',
                      justifyContent: 'center',
                      gap: '0.5rem',
                      padding: '0.65rem 0.75rem',
                      borderRadius: c.radiusSm,
                      border: `1px solid ${c.border}`,
                      background: 'transparent',
                      color: c.text2,
                      fontSize: '0.82rem',
                      fontWeight: 500,
                      fontFamily: c.fontMono,
                      textDecoration: 'none',
                      cursor: 'pointer',
                      transition: 'border-color 0.2s, background 0.2s',
                    }}
                    onMouseEnter={(e) => {
                      e.currentTarget.style.borderColor = c.borderHover
                      e.currentTarget.style.background = `rgba(${c.accentRgb}, 0.05)`
                    }}
                    onMouseLeave={(e) => {
                      e.currentTarget.style.borderColor = c.border
                      e.currentTarget.style.background = 'transparent'
                    }}
                  >
                    {Icon && <Icon />}
                    {provider.label}
                  </a>
                )
              })}
            </div>

            {/* Divider */}
            <div
              data-auth-divider="pico"
              style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', margin: '1.5rem 0' }}
            >
              <span data-auth-divider-line style={{ flex: 1, height: '1px', background: c.dividerLine }} />
              <span style={{
                fontFamily: c.fontMono,
                fontSize: '0.6rem',
                textTransform: 'uppercase',
                letterSpacing: '0.18em',
                color: c.dividerText,
              }}>
                {t('orUseEmail')}
              </span>
              <span data-auth-divider-line style={{ flex: 1, height: '1px', background: c.dividerLine }} />
            </div>

            {/* Form */}
            <form
              onSubmit={handleSubmit}
              aria-busy={loading || resending}
              aria-describedby={error && errorTarget === 'form' ? errorSummaryId : undefined}
              style={{ display: 'flex', flexDirection: 'column', gap: '0.875rem' }}
            >
              {isRegister && (
                <div>
                  <label htmlFor="pico-name" style={labelStyle}>{t('fields.name.label')}</label>
                  <input
                    id="pico-name"
                    type="text"
                    value={name}
                    onChange={(e) => {
                      setName(e.target.value)
                      clearError()
                    }}
                    placeholder={t('fields.name.placeholder')}
                    required
                    autoComplete="name"
                    style={inputStyle}
                    onFocus={(e) => { e.target.style.borderColor = c.borderHover; e.target.style.boxShadow = `0 0 0 3px rgba(${c.accentRgb},0.12)` }}
                    onBlur={(e) => { e.target.style.borderColor = c.border; e.target.style.boxShadow = 'none' }}
                  />
                </div>
              )}

              <div>
                <label htmlFor="pico-email" style={labelStyle}>{t('fields.email.label')}</label>
                <input
                  id="pico-email"
                  type="email"
                  value={email}
                  onChange={(e) => {
                    setEmail(e.target.value)
                    clearError()
                  }}
                  placeholder={t('fields.email.placeholder')}
                  required
                  autoComplete="email"
                  dir="ltr"
                  aria-invalid={
                    error && (errorTarget === 'email' || errorTarget === 'credentials')
                      ? true
                      : undefined
                  }
                  aria-describedby={
                    error && (errorTarget === 'email' || errorTarget === 'credentials')
                      ? errorSummaryId
                      : undefined
                  }
                  style={inputStyle}
                  onFocus={(e) => { e.target.style.borderColor = c.borderHover; e.target.style.boxShadow = `0 0 0 3px rgba(${c.accentRgb},0.12)` }}
                  onBlur={(e) => { e.target.style.borderColor = c.border; e.target.style.boxShadow = 'none' }}
                />
              </div>

              <div>
                <label htmlFor="pico-password" style={labelStyle}>{t('fields.password.label')}</label>
                <input
                  id="pico-password"
                  type="password"
                  value={password}
                  onChange={(e) => {
                    setPassword(e.target.value)
                    clearError()
                  }}
                  placeholder={t('fields.password.placeholder')}
                  required
                  autoComplete={isRegister ? 'new-password' : 'current-password'}
                  aria-invalid={
                    error && (errorTarget === 'password' || errorTarget === 'credentials')
                      ? true
                      : undefined
                  }
                  aria-describedby={
                    error && (errorTarget === 'password' || errorTarget === 'credentials')
                      ? errorSummaryId
                      : undefined
                  }
                  style={inputStyle}
                  onFocus={(e) => { e.target.style.borderColor = c.borderHover; e.target.style.boxShadow = `0 0 0 3px rgba(${c.accentRgb},0.12)` }}
                  onBlur={(e) => { e.target.style.borderColor = c.border; e.target.style.boxShadow = 'none' }}
                />
              </div>

              {isRegister && (
                <div>
                  <label htmlFor="pico-confirm" style={labelStyle}>{t('fields.confirmPassword.label')}</label>
                  <input
                    id="pico-confirm"
                    type="password"
                    value={confirmPassword}
                    onChange={(e) => {
                      setConfirmPassword(e.target.value)
                      clearError()
                    }}
                    placeholder={t('fields.confirmPassword.placeholder')}
                    required
                    autoComplete="new-password"
                    aria-invalid={error && errorTarget === 'confirmPassword' ? true : undefined}
                    aria-describedby={error && errorTarget === 'confirmPassword' ? errorSummaryId : undefined}
                    style={inputStyle}
                    onFocus={(e) => { e.target.style.borderColor = c.borderHover; e.target.style.boxShadow = `0 0 0 3px rgba(${c.accentRgb},0.12)` }}
                    onBlur={(e) => { e.target.style.borderColor = c.border; e.target.style.boxShadow = 'none' }}
                  />
                </div>
              )}

              {/* Notice */}
              {notice && (
                <div role="status" aria-live="polite" aria-atomic="true" style={{
                  display: 'flex',
                  alignItems: 'flex-start',
                  gap: '0.5rem',
                  padding: '0.75rem 1rem',
                  borderRadius: c.radiusSm,
                  background: `rgba(${c.accentRgb}, 0.08)`,
                  border: `1px solid rgba(${c.accentRgb}, 0.2)`,
                  color: c.text2,
                  fontSize: '0.85rem',
                  lineHeight: 1.5,
                }}>
                  <span style={{ color: c.accent, flexShrink: 0 }}>&#10003;</span>
                  {notice}
                </div>
              )}

              {/* Error */}
              {error && (
                <div
                  ref={errorSummaryRef}
                  id={errorSummaryId}
                  role="alert"
                  aria-live="assertive"
                  aria-atomic="true"
                  tabIndex={-1}
                  style={{
                    display: 'flex',
                    alignItems: 'flex-start',
                    gap: '0.5rem',
                    padding: '0.75rem 1rem',
                    borderRadius: c.radiusSm,
                    background: 'rgba(255,140,114,0.08)',
                    border: '1px solid rgba(255,140,114,0.2)',
                    color: c.text,
                    fontSize: '0.85rem',
                    lineHeight: 1.5,
                  }}
                >
                  <span style={{ color: c.red, flexShrink: 0 }}>&#9888;</span>
                  {error}
                </div>
              )}

              {/* Submit */}
              <button
                type="submit"
                disabled={loading}
                style={{
                  width: '100%',
                  minHeight: '2.75rem',
                  padding: '0.75rem 1.25rem',
                  borderRadius: c.radiusFull,
                  border: 'none',
                  background: `linear-gradient(135deg, ${c.accent}, ${c.accent}dd)`,
                  color: c.accentContrast,
                  fontFamily: c.fontMono,
                  fontSize: '0.82rem',
                  fontWeight: 700,
                  letterSpacing: '0.04em',
                  cursor: loading ? 'not-allowed' : 'pointer',
                  opacity: loading ? 0.6 : 1,
                  marginTop: '0.25rem',
                  transition: 'opacity 0.2s, transform 0.15s',
                  boxShadow: `0 0 20px rgba(${c.accentRgb}, 0.2)`,
                }}
              >
                {loading ? t(`modes.${modeKey}.loading`) : t(`modes.${modeKey}.submit`)}
              </button>
            </form>

            {/* Utility links */}
            <div style={{
              marginTop: '1.5rem',
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              gap: '0.5rem',
              fontSize: '0.82rem',
              color: c.muted,
            }}>
              {mode === 'login' && (
                <Link href={`/forgot-password?next=${encodeURIComponent(redirectPath)}`} style={{ display: 'inline-flex', minHeight: '2.75rem', alignItems: 'center', color: c.muted, textDecoration: 'none', transition: 'color 0.2s' }}>
                  {t('forgotPassword')}
                </Link>
              )}
              {mode === 'login' && verificationError && (
                <button
                  type="button"
                  onClick={() => void handleResend()}
                  disabled={resending}
                  style={{ minHeight: '2.75rem', background: 'none', border: 'none', color: c.muted, cursor: 'pointer', fontSize: '0.82rem', padding: '0 0.5rem', textDecoration: 'underline' }}
                >
                  {resending ? t('notice.resending') : t('notice.resendVerification')}
                </button>
              )}
              <p style={{ margin: 0 }}>
                {t(`modes.${modeKey}.toggleQuestion`)}{' '}
                <Link
                  href={`/${isRegister ? 'login' : 'register'}?next=${encodeURIComponent(redirectPath)}`}
                  style={{ display: 'inline-flex', minHeight: '2.75rem', alignItems: 'center', color: c.accent, textDecoration: 'none', fontWeight: 600 }}
                >
                  {t(`modes.${modeKey}.toggleAction`)}
                </Link>
              </p>
            </div>
          </div>
        </div>
      </main>
    </div>
  )
}
