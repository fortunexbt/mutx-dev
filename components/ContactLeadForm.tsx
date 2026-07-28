'use client'

import { type FormEvent, useId, useRef, useState } from 'react'
import { AlertCircle, CheckCircle2, Loader2, Send } from 'lucide-react'

import { cn } from '@/lib/utils'
import marketing from '@/components/site/marketing/MarketingCore.module.css'

type ContactLeadFormProps = {
  source?: string
  className?: string
}

const INQUIRY_TYPES = [
  { value: 'demo-hosted-access', label: 'Hosted evaluation' },
  { value: 'ideas', label: 'Design partner / workflow' },
  { value: 'partnerships', label: 'Partnership / infrastructure' },
  { value: 'contributions', label: 'Contributions' },
  { value: 'funding', label: 'Strategic / funding' },
  { value: 'general', label: 'General' },
] as const

const MESSAGE_PLACEHOLDERS: Record<string, string> = {
  funding: 'What kind of financing conversation is relevant, what stage are you evaluating, and what part of the MUTX roadmap matters most?',
  partnerships: 'Describe the partnership, infrastructure, integration, or distribution angle you want to explore.',
  contributions: 'Tell us what you want to contribute: code, docs, design, infrastructure, GTM support, or ecosystem work.',
  ideas: 'Share the workflow, feature gap, or design-partner use case you think MUTX should support.',
  'demo-hosted-access': 'Tell us what you need to validate in a hosted evaluation and which deployment, auth, or runtime workflow matters most.',
  general: 'Summarize the context, what you need, and how MUTX can help.',
}

type ContactSubmissionAttempt = { content: string; key: string }

export function resolveContactSubmissionAttempt(
  current: ContactSubmissionAttempt | null,
  content: string,
  createKey = () => window.crypto.randomUUID(),
): ContactSubmissionAttempt {
  return current?.content === content ? current : { content, key: createKey() }
}

export function ContactLeadForm({ source = 'contact-page', className }: ContactLeadFormProps) {
  const emailErrorId = useId()
  const messageErrorId = useId()
  const submissionErrorId = useId()
  const [inquiryType, setInquiryType] = useState('general')
  const [email, setEmail] = useState('')
  const [name, setName] = useState('')
  const [organization, setOrganization] = useState('')
  const [message, setMessage] = useState('')
  const [honeypot, setHoneypot] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [emailInvalid, setEmailInvalid] = useState(false)
  const [messageInvalid, setMessageInvalid] = useState(false)
  const messageRef = useRef<HTMLTextAreaElement>(null)
  const submissionAttemptRef = useRef<{ content: string; key: string } | null>(null)

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setError('')
    setSuccess('')

    const normalizedMessage = message.trim()
    if (!normalizedMessage) {
      setMessageInvalid(true)
      messageRef.current?.focus()
      return
    }

    setLoading(true)

    try {
      const requestPayload = {
        email,
        name,
        company: organization,
        message: normalizedMessage,
        source,
        interest: inquiryType,
        honeypot,
        productUpdatesConsent: false,
      }
      const canonicalContent = JSON.stringify(requestPayload)
      submissionAttemptRef.current = resolveContactSubmissionAttempt(
        submissionAttemptRef.current,
        canonicalContent,
      )

      const response = await fetch('/api/leads', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Idempotency-Key': submissionAttemptRef.current.key,
        },
        body: canonicalContent,
      })

      const payload = await response.json().catch(() => ({}))
      const errorMessage =
        payload?.error?.message ||
        payload?.detail ||
        (typeof payload?.error === 'string' ? payload.error : null) ||
        'Failed to send contact request'

      if (!response.ok || payload?.persisted !== true) {
        throw new Error(errorMessage)
      }

      submissionAttemptRef.current = null
      setInquiryType('general')
      setEmail('')
      setName('')
      setOrganization('')
      setMessage('')
      setEmailInvalid(false)
      setMessageInvalid(false)
      setSuccess(
        payload?.message_to_submitter ||
          'Your message was saved. Automated confirmation and team notification are best-effort.',
      )
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to send contact request')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div data-testid="contact-lead-form" className={cn(marketing.panel, marketing.panelPadded, className)}>
      {success ? (
        <div className={marketing.formWrap}>
          <div className={marketing.success} role="status" aria-live="polite" aria-atomic="true">
            <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0" />
            <div>
              <p className="font-medium">{success}</p>
              <p className="mt-1 text-sm">Your inquiry is complete and can be submitted again if needed.</p>
            </div>
          </div>
          <div className={marketing.utilityLinks}>
            <button type="button" onClick={() => setSuccess('')} className={marketing.inlineLink}>
              Send another inquiry
            </button>
            <a href="mailto:hello@mutx.dev" className={marketing.inlineLink}>
              Email hello@mutx.dev
            </a>
          </div>
        </div>
      ) : (
        <form onSubmit={handleSubmit} className={marketing.formWrap} aria-busy={loading}>
          <input
            type="text"
            name="company_website"
            value={honeypot}
            onChange={(event) => setHoneypot(event.target.value)}
            tabIndex={-1}
            autoComplete="off"
            className="hidden"
          />

          <label className={marketing.field}>
            <span className={marketing.fieldLabel}>Inquiry type (required)</span>
            <select
              name="interest"
              required
              value={inquiryType}
              onChange={(event) => setInquiryType(event.target.value)}
              className={marketing.select}
            >
              {INQUIRY_TYPES.map((item) => (
                <option key={item.value} value={item.value}>
                  {item.label}
                </option>
              ))}
            </select>
          </label>

          <div className="grid gap-4 sm:grid-cols-2">
            <label className={marketing.field}>
              <span className={marketing.fieldLabel}>Name (optional)</span>
              <input
                name="name"
                value={name}
                onChange={(event) => setName(event.target.value)}
                autoComplete="name"
                maxLength={100}
                placeholder="Your name"
                className={marketing.input}
              />
            </label>

            <label className={marketing.field}>
              <span className={marketing.fieldLabel}>Work email (required)</span>
              <input
                name="email"
                type="email"
                required
                value={email}
                onChange={(event) => {
                  setEmail(event.target.value)
                  setEmailInvalid(false)
                }}
                onInvalid={() => setEmailInvalid(true)}
                autoComplete="email"
                maxLength={255}
                dir="ltr"
                aria-invalid={emailInvalid || undefined}
                aria-describedby={emailInvalid ? emailErrorId : undefined}
                placeholder="you@company.com"
                className={marketing.input}
              />
              {emailInvalid ? (
                <span id={emailErrorId} className="sr-only">
                  Enter a valid work email address.
                </span>
              ) : null}
            </label>
          </div>

          <label className={marketing.field}>
            <span className={marketing.fieldLabel}>Organization (optional)</span>
            <input
              name="company"
              value={organization}
              onChange={(event) => setOrganization(event.target.value)}
              autoComplete="organization"
              maxLength={200}
              placeholder="Firm, company, studio, or fund"
              className={marketing.input}
            />
          </label>

          <label className={marketing.field}>
            <span className={marketing.fieldLabel}>Message (required)</span>
            <textarea
              ref={messageRef}
              name="message"
              required
              value={message}
              onChange={(event) => {
                setMessage(event.target.value)
                setMessageInvalid(false)
              }}
              onInvalid={() => setMessageInvalid(true)}
              aria-invalid={messageInvalid || undefined}
              aria-describedby={messageInvalid ? messageErrorId : undefined}
              placeholder={MESSAGE_PLACEHOLDERS[inquiryType]}
              maxLength={2000}
              rows={6}
              className={marketing.textarea}
            />
            {messageInvalid ? (
              <span id={messageErrorId} className="sr-only">
                Enter a message.
              </span>
            ) : null}
          </label>

          {error ? (
            <div id={submissionErrorId} className={marketing.error} role="alert">
              <AlertCircle className="mt-0.5 h-5 w-5 shrink-0" />
              <p>{error}</p>
            </div>
          ) : null}

          <button
            type="submit"
            disabled={loading}
            aria-describedby={error ? submissionErrorId : undefined}
            className={`${marketing.buttonPrimary} disabled:cursor-not-allowed disabled:opacity-50`}
          >
            {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
            {loading ? 'Sending…' : 'Send inquiry'}
          </button>
        </form>
      )}
    </div>
  )
}
