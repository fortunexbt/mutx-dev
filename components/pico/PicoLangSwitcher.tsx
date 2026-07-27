'use client'

import { type ChangeEvent, useEffect, useState } from 'react'
import { useLocale } from 'next-intl'

const LOCALES = [
  { code: 'en', flag: '🇺🇸', label: 'English' },
  { code: 'es', flag: '🇪🇸', label: 'Español' },
  { code: 'fr', flag: '🇫🇷', label: 'Français' },
  { code: 'de', flag: '🇩🇪', label: 'Deutsch' },
  { code: 'it', flag: '🇮🇹', label: 'Italiano' },
  { code: 'pt', flag: '🇧🇷', label: 'Português' },
  { code: 'ja', flag: '🇯🇵', label: '日本語' },
  { code: 'ko', flag: '🇰🇷', label: '한국어' },
  { code: 'zh', flag: '🇨🇳', label: '中文' },
  { code: 'ar', flag: '🇸🇦', label: 'العربية' },
] as const

export function PicoLangSwitcher() {
  const locale = useLocale()
  const [ready, setReady] = useState(false)

  useEffect(() => {
    setReady(true)
  }, [])

  function handleSelect(event: ChangeEvent<HTMLSelectElement>) {
    const code = event.target.value
    document.cookie = `NEXT_LOCALE=${code}; path=/; max-age=${60 * 60 * 24 * 365}; SameSite=Lax`
    window.location.reload()
  }

  return (
    <div className="relative inline-flex">
      <label htmlFor="pico-interface-language" className="sr-only">
        Interface language
      </label>
      <select
        id="pico-interface-language"
        value={locale}
        onChange={handleSelect}
        disabled={!ready}
        className="min-h-11 cursor-pointer appearance-none border border-[color:var(--pico-border)] bg-[#0a0a09] py-2 pl-3 pr-9 text-sm font-semibold text-[color:var(--pico-text)] outline-none transition duration-200 hover:border-[color:var(--pico-accent)] focus-visible:border-[color:var(--pico-accent)] focus-visible:ring-2 focus-visible:ring-[color:var(--pico-accent)]"
      >
        {LOCALES.map((item) => (
          <option key={item.code} value={item.code}>
            {item.flag} {item.label}
          </option>
        ))}
      </select>
      <span
        aria-hidden="true"
        className="pointer-events-none absolute inset-y-0 right-3 inline-flex items-center text-[0.68rem] text-[color:var(--pico-text-muted)]"
      >
        ▾
      </span>
    </div>
  )
}
