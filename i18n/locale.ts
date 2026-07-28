import {
  getPicoDirection,
  PICO_DEFAULT_LOCALE,
  PICO_LOCALES,
  resolvePicoLocale,
  type PicoLocale,
} from '@/lib/pico/locale'

export type LocaleDirection = 'ltr' | 'rtl'
export type Locale = PicoLocale

export const SUPPORTED_LOCALES = PICO_LOCALES
export const DEFAULT_LOCALE = PICO_DEFAULT_LOCALE

export function normalizeLocale(locale?: string | null): Locale {
  return resolvePicoLocale(locale)
}

export function getLocaleDirection(locale?: string | null): LocaleDirection {
  return getPicoDirection(resolvePicoLocale(locale))
}
