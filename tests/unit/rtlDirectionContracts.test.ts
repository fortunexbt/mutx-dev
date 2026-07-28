import { readFileSync } from 'node:fs'
import { join } from 'node:path'

import { getLocaleDirection, normalizeLocale } from '@/i18n/locale'

function readSource(relativePath: string) {
  return readFileSync(join(process.cwd(), relativePath), 'utf8')
}

const sharedCssFiles = [
  'app/docs/docs.css',
  'components/AuthNav.module.css',
  'components/site/AuthSurface.module.css',
  'components/site/PublicFooter.module.css',
  'components/site/PublicNav.module.css',
  'components/site/SystemState.module.css',
  'components/site/marketing/MarketingCore.module.css',
] as const

const sharedComponentFiles = [
  'components/dashboard/DashboardCommandPalette.tsx',
  'components/dashboard/DashboardShell.tsx',
  'components/dashboard/EmptyState.tsx',
  'components/dashboard/FeatureHint.tsx',
  'components/dashboard/FilterBar.tsx',
  'components/dashboard/KebabMenu.tsx',
  'components/dashboard/RouteHeader.tsx',
  'components/dashboard/Sidebar.tsx',
  'components/dashboard/TopBar.tsx',
  'components/dashboard/livePrimitives.tsx',
  'components/dashboard/demo/MutxDemoApp.tsx',
  'components/dashboard/demo/demoPrimitives.tsx',
  'components/site/docs/DocsLayout.tsx',
] as const

describe('global RTL direction contracts', () => {
  it('normalizes supported locale variants and derives document direction', () => {
    expect(normalizeLocale(' AR-eg ')).toBe('ar')
    expect(normalizeLocale('en-US')).toBe('en')
    expect(normalizeLocale('unknown')).toBe('en')
    expect(getLocaleDirection('ar')).toBe('rtl')
    expect(getLocaleDirection('ar-SA')).toBe('rtl')
    expect(getLocaleDirection('en')).toBe('ltr')
  })

  it('sets root language and direction from the same canonical locale', () => {
    const source = readSource('app/layout.tsx')

    expect(source).toContain('const locale = normalizeLocale(await getLocale())')
    expect(source).toContain('const direction = getLocaleDirection(locale)')
    expect(source).toContain('<html lang={locale} dir={direction}')
  })

  it.each(sharedCssFiles)('%s avoids physical inline geometry', (relativePath) => {
    const source = readSource(relativePath)
    const physicalDeclaration = /(?:^|[;{]\s*)(?:left|right|margin-left|margin-right|padding-left|padding-right|border-left|border-right)\s*:/m

    expect(source).not.toMatch(physicalDeclaration)
  })

  it.each(sharedComponentFiles)('%s uses logical Tailwind geometry', (relativePath) => {
    const source = readSource(relativePath)
    const physicalUtility = /(?:^|[\s"'`])(?:left|right|ml|mr|pl|pr|border-l|border-r|text-left|text-right)(?:-|(?=[\s"'`]))/

    expect(source).not.toMatch(physicalUtility)
  })

  it('isolates technical output and mirrors only opted-in directional icons', () => {
    const css = readSource('app/globals.css')

    expect(css).toContain("[data-technical-value]")
    expect(css).toMatch(/direction:\s*ltr;[\s\S]*?unicode-bidi:\s*isolate;[\s\S]*?text-align:\s*left;/)
    expect(css).toContain(':dir(rtl) .rtl-directional-icon')
    expect(css).not.toMatch(/:dir\(rtl\)\s+(?:svg|img|video|canvas)\b/)
  })

  it('mirrors the homepage event rail with logical inline geometry', () => {
    const source = readSource('components/site/marketing/RebrandHomePage.module.css')
    const eventRail = source.slice(source.indexOf('.eventRail {'), source.indexOf('.receipt {'))

    expect(eventRail).toContain('inset-inline-start:')
    expect(eventRail).toContain('margin-inline-start:')
    expect(eventRail).toContain('padding-inline-start:')
    expect(eventRail).not.toMatch(/(?:^|[;{]\s*)(?:left|right|margin-left|margin-right|padding-left|padding-right)\s*:/m)
  })

  it('announces shared auth errors and associates field-level failures', () => {
    const authPage = readSource('components/auth/AuthPage.tsx')
    const forgotPassword = readSource('components/pico/PicoForgotPasswordPageClient.tsx')
    const resetPassword = readSource('components/pico/PicoResetPasswordPageClient.tsx')

    for (const source of [authPage, forgotPassword, resetPassword]) {
      expect(source).toContain('aria-live="assertive"')
      expect(source).toContain('aria-atomic="true"')
      expect(source).toContain('aria-describedby=')
      expect(source).toContain('aria-invalid=')
    }
  })

  it('keeps Pico-host auth under the root direction contract without changing Pico files', () => {
    const loginPage = readSource('app/login/page.tsx')

    expect(loginPage).toContain('if (isPicoHost(host))')
    expect(loginPage).toContain('<PicoAuthPage')
    expect(readSource('app/layout.tsx')).toContain('dir={direction}')
  })
})
