'use client'

import { useLocale, useTranslations } from 'next-intl'
import { useState, useCallback, useEffect, useId, useRef, type FormEvent } from 'react'
import { motion, AnimatePresence, useReducedMotion } from 'framer-motion'
import * as Select from '@radix-ui/react-select'
import { X, ArrowRight, Check, ChevronDown } from 'lucide-react'

import { getPicoDirection } from '@/lib/pico/locale'

import s from './PicoContactForm.module.css'
import { buildPicoContactPayload } from './picoContactPayload'

const FOCUSABLE_SELECTOR = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled]):not([type="hidden"]):not([tabindex="-1"])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(',')

function getFocusableElements(container: HTMLElement) {
  return Array.from(container.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)).filter(
    (element) => element.getClientRects().length > 0 && !element.closest('[aria-hidden="true"]'),
  )
}

type PicoContactFormOption = {
  value: string
  label: string
}

type PicoContactFormCopy = {
  title?: string
  subtitle?: string
  interestLabel?: string
  messageLabel?: string
  messageOptional?: string
  messagePlaceholder?: string
  submit?: string
  submitting?: string
  disclaimer?: string
  successTitle?: string
  successBody?: string
  successBack?: string
}

type PicoContactFormProps = {
  open: boolean
  onClose: () => void
  defaultInterest?: string
  defaultMessage?: string
  source?: string
  onSuccess?: () => void
  copy?: PicoContactFormCopy
  interestOptions?: ReadonlyArray<PicoContactFormOption>
}

type ContactSubmissionResponse = {
  success?: unknown
  status?: unknown
  persisted?: unknown
  detail?: unknown
  error?: {
    message?: unknown
  }
}

type PicoContactSubmissionAttempt = { content: string; key: string }

export function resolvePicoContactSubmissionAttempt(
  current: PicoContactSubmissionAttempt | null,
  content: string,
  createKey = () => window.crypto.randomUUID(),
): PicoContactSubmissionAttempt {
  return current?.content === content ? current : { content, key: createKey() }
}

function isContactSubmissionResponse(value: unknown): value is ContactSubmissionResponse {
  return typeof value === 'object' && value !== null
}

export function getContactSubmissionError(value: unknown, fallback: string): string {
  if (!isContactSubmissionResponse(value)) return fallback
  if (typeof value.error?.message === 'string' && value.error.message.trim()) {
    return value.error.message
  }
  return typeof value.detail === 'string' && value.detail.trim() ? value.detail : fallback
}

export function wasContactSubmissionAccepted(
  value: unknown,
): value is ContactSubmissionResponse {
  return (
    isContactSubmissionResponse(value) &&
    value.success === true &&
    value.status === 'accepted' &&
    value.persisted === true
  )
}

export function PicoContactForm({
  open,
  onClose,
  defaultInterest,
  defaultMessage,
  source = 'pico-landing',
  onSuccess,
  copy,
  interestOptions,
}: PicoContactFormProps) {
  const t = useTranslations('pico.contactForm')
  const locale = useLocale()
  const prefersReducedMotion = useReducedMotion()
  const [state, setState] = useState<'idle' | 'submitting' | 'success' | 'error'>('idle')
  const [errorMsg, setErrorMsg] = useState('')
  const overlayRef = useRef<HTMLDivElement>(null)
  const modalRef = useRef<HTMLDivElement>(null)
  const emailRef = useRef<HTMLInputElement>(null)
  const successTitleRef = useRef<HTMLHeadingElement>(null)
  const honeypotRef = useRef<HTMLInputElement>(null)
  const submissionIdRef = useRef(0)
  const submissionAttemptRef = useRef<{ content: string; key: string } | null>(null)
  const titleId = useId()
  const interestLabelId = useId()
  const usesStructuredIntake =
    t.has('interestOptions.build') &&
    t.has('interestOptions.fix') &&
    t.has('interestOptions.control')

  const defaultInterestOptions: PicoContactFormOption[] = usesStructuredIntake
    ? [
        { value: 'build', label: t('interestOptions.build') },
        { value: 'fix', label: t('interestOptions.fix') },
        { value: 'control', label: t('interestOptions.control') },
        { value: 'other', label: t('interestOptions.other') },
      ]
    : [
        { value: 'building-first', label: t('interestOptions.building-first') },
        { value: 'fixing-existing', label: t('interestOptions.fixing-existing') },
        { value: 'evaluating', label: t('interestOptions.evaluating') },
        { value: 'spent-money', label: t('interestOptions.spent-money') },
        { value: 'other', label: t('interestOptions.other') },
      ]
  const resolvedInterestOptions =
    interestOptions && interestOptions.length > 0 ? [...interestOptions] : defaultInterestOptions
  const resolvedDefaultInterest =
    defaultInterest && resolvedInterestOptions.some((option) => option.value === defaultInterest)
      ? defaultInterest
      : resolvedInterestOptions[0]?.value ?? (usesStructuredIntake ? 'build' : 'building-first')
  const resolvedCopy = {
    title: copy?.title ?? t('title'),
    subtitle: copy?.subtitle ?? t('subtitle'),
    interestLabel: copy?.interestLabel ?? t('interestLabel'),
    messageLabel: copy?.messageLabel ?? t('messageLabel'),
    messageOptional: copy?.messageOptional ?? t('messageOptional'),
    messagePlaceholder: copy?.messagePlaceholder ?? t('messagePlaceholder'),
    submit: copy?.submit ?? t('submit'),
    submitting: copy?.submitting ?? t('submitting'),
    disclaimer: copy?.disclaimer ?? t('disclaimer'),
    successTitle: copy?.successTitle ?? t('successTitle'),
    successBody: copy?.successBody ?? t('successBody'),
    successBack: copy?.successBack ?? t('successBack'),
  }
  const [interest, setInterest] = useState(resolvedDefaultInterest)

  useEffect(() => {
    if (open) {
      setInterest(resolvedDefaultInterest)
    }
  }, [open, resolvedDefaultInterest])

  const handleSubmit = useCallback(
    async (e: FormEvent<HTMLFormElement>) => {
      e.preventDefault()
      if (state === 'submitting') return

      if (honeypotRef.current?.value) return

      const submissionId = submissionIdRef.current + 1
      submissionIdRef.current = submissionId
      setState('submitting')
      setErrorMsg('')

      const form = new FormData(e.currentTarget)
      const payload = buildPicoContactPayload({
        email: form.get('email') as string,
        name: form.get('name') as string,
        company: form.get('company') as string,
        message: form.get('message') as string,
        interest,
        locale,
        source,
        honeypot: honeypotRef.current?.value || '',
        productUpdatesConsent: form.get('productUpdatesConsent') === 'on',
      })
      const canonicalContent = JSON.stringify(payload)
      submissionAttemptRef.current = resolvePicoContactSubmissionAttempt(
        submissionAttemptRef.current,
        canonicalContent,
      )

      try {
        const res = await fetch('/api/contact', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Idempotency-Key': submissionAttemptRef.current.key,
          },
          body: canonicalContent,
        })

        const data: unknown = await res.json()
        if (submissionId !== submissionIdRef.current) return

        if (!res.ok || !wasContactSubmissionAccepted(data)) {
          setErrorMsg(getContactSubmissionError(data, t('errorFallback')))
          setState('error')
          return
        }

        submissionAttemptRef.current = null
        setState('success')
        onSuccess?.()
      } catch {
        if (submissionId !== submissionIdRef.current) return
        setErrorMsg(t('networkError'))
        setState('error')
      }
    },
    [interest, locale, onSuccess, source, state, t],
  )

  const handleClose = useCallback(() => {
    submissionIdRef.current += 1
    setState('idle')
    setErrorMsg('')
    onClose()
  }, [onClose])

  useEffect(() => {
    if (!open) return

    const previouslyFocused =
      document.activeElement instanceof HTMLElement ? document.activeElement : null
    const overlay = overlayRef.current
    const inertedElements = new Map<HTMLElement, boolean>()
    const previousOverflow = document.body.style.overflow

    // Keep the mounted modal branch interactive while making every sibling
    // background branch unavailable to pointer, keyboard, and assistive tech.
    let activeBranch: HTMLElement | null = overlay
    while (activeBranch && activeBranch !== document.body) {
      const parent = activeBranch.parentElement
      if (!parent) break

      for (const sibling of Array.from(parent.children)) {
        if (sibling !== activeBranch && sibling instanceof HTMLElement) {
          inertedElements.set(sibling, sibling.hasAttribute('inert'))
          sibling.setAttribute('inert', '')
        }
      }

      activeBranch = parent
    }

    document.body.style.overflow = 'hidden'
    const focusFrame = window.requestAnimationFrame(() => emailRef.current?.focus({ preventScroll: true }))

    return () => {
      window.cancelAnimationFrame(focusFrame)
      document.body.style.overflow = previousOverflow
      for (const [element, wasInert] of inertedElements) {
        if (!wasInert) element.removeAttribute('inert')
      }
      previouslyFocused?.focus({ preventScroll: true })
    }
  }, [open])

  useEffect(() => {
    if (!open) return

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.defaultPrevented) return

      if (event.key === 'Escape') {
        event.preventDefault()
        handleClose()
        return
      }

      if (event.key !== 'Tab' || !modalRef.current) return

      const activeElement = document.activeElement
      if (
        activeElement instanceof HTMLElement &&
        activeElement.closest('[data-pico-contact-select-content]')
      ) {
        return
      }

      const focusableElements = getFocusableElements(modalRef.current)
      const first = focusableElements[0]
      const last = focusableElements.at(-1)
      if (!first || !last) {
        event.preventDefault()
        modalRef.current.focus({ preventScroll: true })
        return
      }

      if (!modalRef.current.contains(activeElement)) {
        event.preventDefault()
        const focusTarget = event.shiftKey ? last : first
        focusTarget.focus()
      } else if (event.shiftKey && activeElement === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [handleClose, open])

  useEffect(() => {
    if (!open || state !== 'success') return
    successTitleRef.current?.focus({ preventScroll: true })
  }, [open, state])

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          ref={overlayRef}
          className={s.overlay}
          initial={prefersReducedMotion ? undefined : { opacity: 0 }}
          animate={prefersReducedMotion ? undefined : { opacity: 1 }}
          exit={prefersReducedMotion ? undefined : { opacity: 0 }}
          transition={{ duration: 0.2 }}
          onClick={(e) => {
            if (e.target === e.currentTarget) handleClose()
          }}
        >
          <motion.div
            ref={modalRef}
            className={s.modal}
            initial={prefersReducedMotion ? undefined : { opacity: 0, y: 24, scale: 0.97 }}
            animate={prefersReducedMotion ? undefined : { opacity: 1, y: 0, scale: 1 }}
            exit={prefersReducedMotion ? undefined : { opacity: 0, y: 12, scale: 0.98 }}
            transition={{ duration: 0.28, ease: [0.16, 1, 0.3, 1] }}
            role='dialog'
            aria-modal='true'
            aria-labelledby={titleId}
            tabIndex={-1}
          >
            <button
              className={s.closeBtn}
              onClick={handleClose}
              aria-label={t('closeLabel')}
              type='button'
            >
              <X className='h-4 w-4' aria-hidden='true' />
            </button>

            {state === 'success' ? (
              <div
                className={s.successState}
                role='status'
                aria-live='polite'
                aria-atomic='true'
              >
                <span className={s.successIcon}>
                  <Check className='h-6 w-6' aria-hidden='true' />
                </span>
                <h2
                  ref={successTitleRef}
                  id={titleId}
                  className={s.successTitle}
                  tabIndex={-1}
                >
                  {resolvedCopy.successTitle}
                </h2>
                <p className={s.successBody}>{resolvedCopy.successBody}</p>
                <button className={s.successBtn} onClick={handleClose} type='button'>
                  {resolvedCopy.successBack}
                </button>
              </div>
            ) : (
              <>
                <div className={s.header}>
                  <h2 id={titleId} className={s.title}>
                    {resolvedCopy.title}
                  </h2>
                  <p className={s.subtitle}>{resolvedCopy.subtitle}</p>
                </div>

                <form
                  className={s.form}
                  onSubmit={handleSubmit}
                  aria-busy={state === 'submitting'}
                >
                  <input
                    ref={honeypotRef}
                    name='website'
                    type='text'
                    autoComplete='off'
                    tabIndex={-1}
                    aria-hidden='true'
                    className={s.honeypot}
                  />

                  <div className={s.row}>
                    <label className={s.label} htmlFor='pico-email'>
                      <span className={s.labelText}>{t('emailLabel')}</span>
                      <input
                        ref={emailRef}
                        id='pico-email'
                        name='email'
                        type='email'
                        required
                        placeholder={t('emailPlaceholder')}
                        className={s.input}
                        autoComplete='email'
                        inputMode='email'
                        spellCheck={false}
                        autoCapitalize='none'
                        autoCorrect='off'
                        dir='ltr'
                      />
                    </label>
                  </div>

                  <div className={s.row2}>
                    <label className={s.label} htmlFor='pico-name'>
                      <span className={s.labelText}>{t('nameLabel')}</span>
                      <input
                        id='pico-name'
                        name='name'
                        type='text'
                        placeholder={t('namePlaceholder')}
                        className={s.input}
                        autoComplete='name'
                      />
                    </label>
                    <label className={s.label} htmlFor='pico-company'>
                      <span className={s.labelText}>{t('companyLabel')}</span>
                      <input
                        id='pico-company'
                        name='company'
                        type='text'
                        placeholder={t('companyPlaceholder')}
                        className={s.input}
                        autoComplete='organization'
                      />
                    </label>
                  </div>

                  <div className={s.label}>
                    <span id={interestLabelId} className={s.labelText}>
                      {resolvedCopy.interestLabel}
                    </span>
                    <Select.Root
                      value={interest}
                      onValueChange={setInterest}
                      dir={getPicoDirection(locale)}
                    >
                      <Select.Trigger
                        className={s.selectTrigger}
                        aria-labelledby={interestLabelId}
                      >
                        <Select.Value />
                        <Select.Icon className={s.selectIcon}>
                          <ChevronDown className='h-3.5 w-3.5' aria-hidden='true' />
                        </Select.Icon>
                      </Select.Trigger>
                      <Select.Portal>
                        <Select.Content
                          data-pico-contact-select-content
                          className={s.selectContent}
                          position='popper'
                          sideOffset={4}
                          align='start'
                        >
                          <Select.ScrollUpButton className={s.selectScroll} />
                          <Select.Viewport className={s.selectViewport}>
                            {resolvedInterestOptions.map((option) => (
                              <Select.Item key={option.value} value={option.value} className={s.selectItem}>
                                <Select.ItemText>{option.label}</Select.ItemText>
                                <Select.ItemIndicator className={s.selectIndicator}>
                                  <Check className='h-3 w-3' aria-hidden='true' />
                                </Select.ItemIndicator>
                              </Select.Item>
                            ))}
                          </Select.Viewport>
                          <Select.ScrollDownButton className={s.selectScroll} />
                        </Select.Content>
                      </Select.Portal>
                    </Select.Root>
                  </div>

                  <label className={s.label} htmlFor='pico-message'>
                    <span className={s.labelText}>
                      {resolvedCopy.messageLabel} <span className={s.optional}>{resolvedCopy.messageOptional}</span>
                    </span>
                    <textarea
                      id='pico-message'
                      name='message'
                      rows={3}
                      defaultValue={defaultMessage}
                      placeholder={resolvedCopy.messagePlaceholder}
                      className={s.textarea}
                    />
                  </label>

                  <label className={s.consent} htmlFor='pico-product-updates'>
                    <input
                      id='pico-product-updates'
                      name='productUpdatesConsent'
                      type='checkbox'
                      className={s.checkbox}
                    />
                    <span className={s.consentCopy}>
                      <span className={s.consentLabel}>{t('productUpdatesLabel')}</span>
                      <span className={s.consentHint}>{t('productUpdatesHint')}</span>
                    </span>
                  </label>

                  {errorMsg && (
                    <p className={s.error} role='alert' aria-live='assertive' aria-atomic='true'>
                      {errorMsg}
                    </p>
                  )}

                  <button
                    type='submit'
                    className={s.submit}
                    disabled={state === 'submitting'}
                  >
                    {state === 'submitting' ? (
                      resolvedCopy.submitting
                    ) : (
                      <>
                        {resolvedCopy.submit}
                        <ArrowRight className='rtl-directional-icon h-4 w-4' aria-hidden='true' />
                      </>
                    )}
                  </button>

                  <p className={s.disclaimer}>{resolvedCopy.disclaimer}</p>
                </form>
              </>
            )}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
