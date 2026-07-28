import type { AbstractIntlMessages } from 'next-intl'

import ar from '@/messages/ar.json'
import de from '@/messages/de.json'
import en from '@/messages/en.json'
import es from '@/messages/es.json'
import fr from '@/messages/fr.json'
import it from '@/messages/it.json'
import ja from '@/messages/ja.json'
import ko from '@/messages/ko.json'
import pt from '@/messages/pt.json'
import zh from '@/messages/zh.json'

import { getPicoDefaultMessages } from '@/lib/pico/defaultMessages'
import {
  PICO_DEFAULT_LOCALE,
  type PicoLocale,
  resolvePicoLocale,
} from '@/lib/pico/locale'

type MessageValue = string | number | boolean | null | MessageObject | MessageValue[]

type MessageObject = {
  [key: string]: MessageValue
}

const LOCALE_MESSAGES: Record<PicoLocale, MessageObject> = {
  en: en as MessageObject,
  es: es as MessageObject,
  fr: fr as MessageObject,
  de: de as MessageObject,
  it: it as MessageObject,
  pt: pt as MessageObject,
  ja: ja as MessageObject,
  ko: ko as MessageObject,
  zh: zh as MessageObject,
  ar: ar as MessageObject,
}

const missingLocaleWarnings = new Set<string>()

function isObject(value: unknown): value is MessageObject {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function deepMergeMessages(
  base: MessageObject,
  override: MessageObject | undefined,
  includeUnknownKeys = false,
): MessageObject {
  if (!override) {
    return structuredClone(base)
  }

  const merged: MessageObject = structuredClone(base)

  for (const [key, value] of Object.entries(override)) {
    if (!(key in base)) {
      if (includeUnknownKeys) {
        merged[key] = structuredClone(value)
      }
      continue
    }

    if (Array.isArray(value)) {
      const baseValue = base[key]
      if (!Array.isArray(baseValue)) {
        continue
      }

      merged[key] = Array.from(
        {
          length: includeUnknownKeys
            ? Math.max(baseValue.length, value.length)
            : baseValue.length,
        },
        (_, index) => {
          const baseItem = baseValue[index]
          const overrideItem = value[index]
          if (overrideItem === undefined) {
            return structuredClone(baseItem)
          }
          if (baseItem === undefined) {
            return structuredClone(overrideItem)
          }
          if (isObject(baseItem) && isObject(overrideItem)) {
            return deepMergeMessages(baseItem, overrideItem, includeUnknownKeys)
          }
          return structuredClone(overrideItem)
        },
      )
      continue
    }

    if (isObject(value) && isObject(merged[key])) {
      merged[key] = deepMergeMessages(
        merged[key] as MessageObject,
        value,
        includeUnknownKeys,
      )
      continue
    }

    merged[key] = value
  }

  return merged
}

function collectMissingPaths(
  base: MessageObject,
  override: MessageObject | undefined,
  path: string[] = [],
): string[] {
  const missing: string[] = []

  for (const [key, baseValue] of Object.entries(base)) {
    const nextPath = [...path, key]
    const overrideValue = override?.[key]

    if (overrideValue === undefined) {
      if (isObject(baseValue)) {
        missing.push(...collectMissingPaths(baseValue, undefined, nextPath))
      } else {
        missing.push(nextPath.join('.'))
      }
      continue
    }

    if (isObject(baseValue) && isObject(overrideValue)) {
      missing.push(...collectMissingPaths(baseValue, overrideValue, nextPath))
    }
  }

  return missing
}

function getBaseEnglishMessages() {
  return deepMergeMessages(
    getPicoDefaultMessages() as MessageObject,
    en as MessageObject,
    true,
  )
}

function warnMissingMessages(locale: PicoLocale, messages: MessageObject | undefined, base: MessageObject) {
  if (locale === PICO_DEFAULT_LOCALE || missingLocaleWarnings.has(locale)) {
    return
  }

  const missingPaths = collectMissingPaths(base, messages)
  if (!missingPaths.length) {
    return
  }

  missingLocaleWarnings.add(locale)
  const preview = missingPaths.slice(0, 50).join(', ')
  console.warn(
    `[pico-i18n] Locale "${locale}" is missing ${missingPaths.length} message keys. Falling back to ${PICO_DEFAULT_LOCALE}. Missing: ${preview}`,
  )
}

export async function loadPicoMessages(localeCandidate?: string | null): Promise<{
  locale: PicoLocale
  messages: AbstractIntlMessages
}> {
  const locale = resolvePicoLocale(localeCandidate)
  const baseMessages = getBaseEnglishMessages()
  const localeMessages = LOCALE_MESSAGES[locale]

  warnMissingMessages(locale, localeMessages, baseMessages)

  return {
    locale,
    messages:
      locale === PICO_DEFAULT_LOCALE
        ? (baseMessages as AbstractIntlMessages)
        : (deepMergeMessages(baseMessages, localeMessages) as AbstractIntlMessages),
  }
}
