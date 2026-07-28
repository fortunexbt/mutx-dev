'use client'

import { useEffect, useId, useMemo, useRef, useState } from 'react'
import { useTranslations } from 'next-intl'

import {
  picoClasses,
  picoCodex,
  picoCodexFrame,
  picoCodexInset,
  picoCodexNote,
} from '@/components/pico/picoTheme'
import { cn } from '@/lib/utils'

export type PicoWelcomeTourNavItem = {
  href: string
  label: string
  chapter: string
  note: string
}

type PicoWelcomeTourProps = {
  open: boolean
  onClose: () => void
  currentItem: PicoWelcomeTourNavItem
  previousItem: PicoWelcomeTourNavItem | null
  nextItem: PicoWelcomeTourNavItem | null
  pageTitle: string
}

type TourStep = {
  eyebrow: string
  title: string
  body: string
  bullets: string[]
}

const FOCUSABLE_SELECTOR = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(',')

function getFocusableElements(container: HTMLElement) {
  return Array.from(container.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)).filter(
    (element) => element.getAttribute('aria-hidden') !== 'true' && element.tabIndex >= 0,
  )
}

function isolateBackground(root: HTMLElement) {
  const isolatedElements: Array<{
    element: HTMLElement
    ariaHidden: string | null
    inert: boolean
  }> = []
  let current: HTMLElement = root

  while (current !== document.body) {
    const parentElement: HTMLElement | null = current.parentElement
    if (!parentElement) break

    for (const sibling of Array.from(parentElement.children)) {
      if (sibling === current || !(sibling instanceof HTMLElement)) continue

      isolatedElements.push({
        element: sibling,
        ariaHidden: sibling.getAttribute('aria-hidden'),
        inert: sibling.inert,
      })
      sibling.setAttribute('aria-hidden', 'true')
      sibling.inert = true
    }

    current = parentElement
  }

  return () => {
    for (const { element, ariaHidden, inert } of isolatedElements.reverse()) {
      if (ariaHidden === null) {
        element.removeAttribute('aria-hidden')
      } else {
        element.setAttribute('aria-hidden', ariaHidden)
      }
      element.inert = inert
    }
  }
}

function getRouteKey(href: string) {
  if (href === '/academy') return 'academy'
  if (href === '/tutor') return 'tutor'
  if (href === '/autopilot') return 'autopilot'
  if (href === '/support') return 'support'
  return 'onboarding'
}

export function PicoWelcomeTour({
  open,
  onClose,
  currentItem,
  previousItem,
  nextItem,
  pageTitle,
}: PicoWelcomeTourProps) {
  const t = useTranslations('pico.welcomeTour')
  const [stepIndex, setStepIndex] = useState(0)
  const dialogRef = useRef<HTMLElement>(null)
  const initialFocusRef = useRef<HTMLButtonElement>(null)
  const onCloseRef = useRef(onClose)
  const previousFocusRef = useRef<HTMLElement | null>(null)
  const titleId = useId()
  const stepDescriptionId = useId()

  useEffect(() => {
    onCloseRef.current = onClose
  }, [onClose])

  useEffect(() => {
    if (open) {
      setStepIndex(0)
    }
  }, [open])

  useEffect(() => {
    if (!open) return

    const dialog = dialogRef.current
    if (!dialog) return

    previousFocusRef.current =
      document.activeElement instanceof HTMLElement ? document.activeElement : null
    const previousBodyOverflow = document.body.style.overflow
    const restoreBackground = isolateBackground(dialog)
    document.body.style.overflow = 'hidden'

    const focusFrame = window.requestAnimationFrame(() => {
      initialFocusRef.current?.focus()
    })

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        event.preventDefault()
        onCloseRef.current()
        return
      }

      if (event.key !== 'Tab') return

      const currentDialog = dialogRef.current
      if (!currentDialog) return

      const focusableElements = getFocusableElements(currentDialog)
      if (focusableElements.length === 0) {
        event.preventDefault()
        currentDialog.focus()
        return
      }

      const firstElement = focusableElements[0]
      const lastElement = focusableElements[focusableElements.length - 1]
      const activeElement = document.activeElement

      if (event.shiftKey && (activeElement === firstElement || !currentDialog.contains(activeElement))) {
        event.preventDefault()
        lastElement.focus()
      } else if (
        !event.shiftKey &&
        (activeElement === lastElement || !currentDialog.contains(activeElement))
      ) {
        event.preventDefault()
        firstElement.focus()
      }
    }

    document.addEventListener('keydown', handleKeyDown)

    return () => {
      window.cancelAnimationFrame(focusFrame)
      document.removeEventListener('keydown', handleKeyDown)
      document.body.style.overflow = previousBodyOverflow
      restoreBackground()

      const previousFocus = previousFocusRef.current
      if (previousFocus?.isConnected) {
        previousFocus.focus()
      }
      previousFocusRef.current = null
    }
  }, [open])

  const steps = useMemo<TourStep[]>(
    () => {
      const routeKey = getRouteKey(currentItem.href)
      return [
        {
          eyebrow: t('page.eyebrow'),
          title: t('page.title'),
          body: t('page.body'),
          bullets: [
            t('page.current', { chapter: currentItem.chapter, label: currentItem.label }),
            previousItem ? t('page.back', { label: previousItem.label }) : t('page.backOnboarding'),
            nextItem ? t('page.next', { label: nextItem.label }) : t('page.nextSupport'),
          ],
        },
        {
          eyebrow: t(`routes.${routeKey}.eyebrow`),
          title: t(`routes.${routeKey}.title`),
          body: t(`routes.${routeKey}.body`),
          bullets: [
            t(`routes.${routeKey}.bullets.0`),
            t(`routes.${routeKey}.bullets.1`),
            t('routes.currentPage', { pageTitle }),
          ],
        },
        {
          eyebrow: t('output.eyebrow'),
          title: t('output.title'),
          body: t('output.body'),
          bullets: ([0, 1, 2] as const).map((index) => t(`output.bullets.${index}`)),
        },
      ]
    },
    [currentItem, nextItem, pageTitle, previousItem, t],
  )

  const step = steps[stepIndex]

  if (!open) {
    return null
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-end bg-black/20 p-4 pb-24 sm:p-6"
      data-testid="pico-welcome-tour"
    >
      <section
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={stepDescriptionId}
        tabIndex={-1}
        className={picoCodexFrame('flex max-h-full w-full max-w-[26rem] flex-col overflow-hidden p-0')}
      >
        <div className="border-b border-[color:var(--pico-border)] px-5 py-4 sm:px-6">
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className={picoClasses.label}>{t('dialog.label')}</p>
              <h2
                id={titleId}
                className="mt-2 font-[family:var(--font-site-display)] text-3xl tracking-[-0.06em] text-[color:var(--pico-text)]"
              >
                {t('dialog.title')}
              </h2>
            </div>
            <button
              type="button"
              ref={initialFocusRef}
              onClick={onClose}
              className={picoClasses.tertiaryButton}
              aria-label={t('dialog.closeLabel')}
            >
              {t('dialog.close')}
            </button>
          </div>
        </div>

        <div className="grid min-h-0 gap-5 overflow-y-auto px-5 py-5 sm:px-6 sm:py-6">
          <div className={picoCodexNote('p-4')}>
            <p
              className={picoClasses.label}
              role="status"
              aria-live="polite"
              aria-atomic="true"
            >
              {t('dialog.step', { current: stepIndex + 1, total: steps.length, eyebrow: step.eyebrow })}
            </p>
            <h3 className="mt-3 font-[family:var(--font-site-display)] text-3xl tracking-[-0.05em] text-[color:var(--pico-text)]">
              {step.title}
            </h3>
            <p
              id={stepDescriptionId}
              className="mt-3 text-sm leading-6 text-[color:var(--pico-text-secondary)]"
            >
              {step.body}
            </p>
          </div>

          <div className="grid gap-3">
            {step.bullets.map((bullet) => (
              <div key={bullet} className={picoCodexInset('grid grid-cols-[0.8rem,1fr] items-start gap-3 px-4 py-4')}>
                <span className="mt-1.5 h-2.5 w-2.5 rounded-full bg-[color:var(--pico-accent)]" />
                <p className="text-sm leading-6 text-[color:var(--pico-text-secondary)]">{bullet}</p>
              </div>
            ))}
          </div>

          <div className={cn(picoCodexInset('flex items-center justify-between gap-4 p-4'), picoCodex.parchment)}>
            <div className="flex items-center gap-2">
              {steps.map((tourStep, index) => (
                <span
                  key={tourStep.eyebrow}
                  aria-hidden="true"
                  className={cn(
                    'h-2.5 rounded-full transition',
                    stepIndex === index
                      ? 'w-7 bg-[color:var(--pico-accent)]'
                      : 'w-2.5 bg-[color:var(--pico-border)]',
                  )}
                />
              ))}
            </div>

            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => setStepIndex((current) => Math.max(current - 1, 0))}
                className={picoClasses.tertiaryButton}
                disabled={stepIndex === 0}
              >
                {t('dialog.back')}
              </button>
              {stepIndex === steps.length - 1 ? (
                <button type="button" onClick={onClose} className={picoClasses.primaryButton}>
                  {t('dialog.finish')}
                </button>
              ) : (
                <button
                  type="button"
                  onClick={() => setStepIndex((current) => Math.min(current + 1, steps.length - 1))}
                  className={picoClasses.primaryButton}
                >
                  {t('dialog.next')}
                </button>
              )}
            </div>
          </div>
        </div>
      </section>
    </div>
  )
}
