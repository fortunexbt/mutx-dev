'use client'

import { type ChangeEvent, startTransition, useEffect, useState } from 'react'
import { useLocale, useTranslations } from 'next-intl'
import { useRouter } from 'next/navigation'

import {
  getPicoDirection,
  isPicoLocale,
  PICO_AUTH_LOCALE_COOKIE,
  PICO_LANGUAGE_OPTIONS,
  PICO_LOCALE_COOKIE,
  resolvePicoLocale,
  type PicoLocale,
} from '@/lib/pico/locale'

export function PicoLangSwitcher() {
  const router = useRouter()
  const t = useTranslations('pico.localeSwitcher')
  const locale = resolvePicoLocale(useLocale())
  const [ready, setReady] = useState(false)
  const [selectedLocale, setSelectedLocale] = useState<PicoLocale>(locale)
  const [announcement, setAnnouncement] = useState('')

  useEffect(() => {
    setReady(true)
  }, [])

  useEffect(() => {
    setSelectedLocale(locale)
  }, [locale])

  function handleSelect(event: ChangeEvent<HTMLSelectElement>) {
    const code = event.target.value
    if (!isPicoLocale(code) || code === selectedLocale) {
      return
    }

    const option = PICO_LANGUAGE_OPTIONS.find((item) => item.code === code)
    const cookieAttributes = `path=/; max-age=${60 * 60 * 24 * 365}; SameSite=Lax${window.location.protocol === 'https:' ? '; Secure' : ''}`

    document.cookie = `${PICO_LOCALE_COOKIE}=${code}; ${cookieAttributes}`
    document.cookie = `${PICO_AUTH_LOCALE_COOKIE}=${code}; ${cookieAttributes}`
    document.documentElement.lang = code
    document.documentElement.dir = getPicoDirection(code)
    setSelectedLocale(code)
    setAnnouncement(t('changedTo', { language: option?.label ?? code }))

    startTransition(() => {
      router.refresh()
    })
  }

  return (
    <div className="relative inline-flex min-w-0 max-w-full" data-testid="pico-language-switcher">
      <label htmlFor="pico-interface-language" className="sr-only">
        {t('listLabel')}
      </label>
      <select
        id="pico-interface-language"
        value={selectedLocale}
        onChange={handleSelect}
        disabled={!ready}
        aria-label={`${t('listLabel')}. ${t('currentLanguage')}: ${PICO_LANGUAGE_OPTIONS.find((item) => item.code === selectedLocale)?.label ?? selectedLocale}`}
        className="min-h-11 w-[8.75rem] max-w-full cursor-pointer appearance-none truncate border border-[color:var(--pico-border)] bg-[#0a0a09] py-2 pe-9 ps-3 text-sm font-semibold text-[color:var(--pico-text)] outline-none transition duration-200 hover:border-[color:var(--pico-accent)] focus-visible:border-[color:var(--pico-accent)] focus-visible:ring-2 focus-visible:ring-[color:var(--pico-accent)] disabled:cursor-wait disabled:opacity-70 sm:w-[11rem]"
      >
        {PICO_LANGUAGE_OPTIONS.map((item) => (
          <option key={item.code} value={item.code}>
            {item.flag} {item.label}
          </option>
        ))}
      </select>
      <span
        aria-hidden="true"
        className="pointer-events-none absolute inset-y-0 end-3 inline-flex items-center text-[0.68rem] text-[color:var(--pico-text-muted)]"
      >
        ▾
      </span>
      <span className="sr-only" role="status" aria-live="polite" aria-atomic="true">
        {announcement}
      </span>
    </div>
  )
}
