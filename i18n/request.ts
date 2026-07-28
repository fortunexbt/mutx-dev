import { cookies, headers } from 'next/headers'
import { getRequestConfig } from 'next-intl/server'

import { routing } from './routing'
import { loadPicoMessages } from '@/lib/pico/messages'

export default getRequestConfig(async ({ requestLocale }) => {
  let locale = await requestLocale

  if (!locale) {
    locale = (await headers()).get('x-mutx-locale') ?? undefined
  }

  if (!locale) {
    const cookieStore = await cookies()
    const cookieLocale = cookieStore.get('NEXT_LOCALE')?.value
    if (cookieLocale && routing.locales.includes(cookieLocale as (typeof routing.locales)[number])) {
      locale = cookieLocale
    }
  }

  if (!locale || !routing.locales.includes(locale as (typeof routing.locales)[number])) {
    locale = routing.defaultLocale
  }

  const loaded = await loadPicoMessages(locale)

  return {
    locale: loaded.locale,
    messages: loaded.messages,
  }
})
