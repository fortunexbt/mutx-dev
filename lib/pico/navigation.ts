'use client'

import { useCallback, useMemo } from 'react'
import { usePathname } from 'next/navigation'

export function picoHref(pathname: string, target: string) {
  const normalizedTarget = target === '/' ? '' : target
  if (!pathname.startsWith('/pico')) {
    return target
  }

  return normalizedTarget ? `/pico${normalizedTarget}` : '/pico'
}

export function normalizePicoPathname(pathname: string) {
  if (pathname === '/pico') {
    return '/'
  }

  if (pathname.startsWith('/pico/')) {
    return pathname.slice('/pico'.length)
  }

  return pathname
}

export function isPicoRouteActive(pathname: string, target: string) {
  const normalizedPathname = normalizePicoPathname(pathname)
  return normalizedPathname === target || normalizedPathname.startsWith(`${target}/`)
}

export function picoEntryHref(pathname: string) {
  return pathname.startsWith('/pico') ? '/pico/onboarding' : '/start'
}

export function usePicoHref() {
  const pathname = usePathname()

  return useCallback(
    (target: string) => picoHref(pathname, target),
    [pathname],
  )
}

export function usePicoEntryHref() {
  const pathname = usePathname()

  return useMemo(() => picoEntryHref(pathname), [pathname])
}
