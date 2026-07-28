import type { ReactNode } from 'react'

jest.mock('../../app/fonts/app', () => ({ appFontVariables: 'font-vars' }))
jest.mock('next-intl', () => ({
  NextIntlClientProvider: ({ children }: { children: ReactNode }) => children,
}))
jest.mock('next-intl/server', () => ({
  getLocale: jest.fn(async () => 'en'),
  getMessages: jest.fn(async () => ({})),
  getTranslations: jest.fn(async (namespace: string) =>
    (key: string) => `${namespace}.${key}`,
  ),
}))

import { metadata as dashboardMetadata } from '../../app/dashboard/layout'
import { generateMetadata as generateForgotPasswordMetadata } from '../../app/forgot-password/layout'
import { metadata as loginMetadata } from '../../app/login/layout'
import { metadata as onboardingMetadata } from '../../app/onboarding/layout'
import { metadata as registerMetadata } from '../../app/register/layout'
import { generateMetadata as generateResetPasswordMetadata } from '../../app/reset-password/layout'
import { generateMetadata as generateVerifyEmailMetadata } from '../../app/verify-email/layout'

const noindexLayouts = [
  ['dashboard', dashboardMetadata],
  ['login', loginMetadata],
  ['onboarding', onboardingMetadata],
  ['register', registerMetadata],
] as const

const localizedNoindexLayouts = [
  ['forgot-password', generateForgotPasswordMetadata],
  ['reset-password', generateResetPasswordMetadata],
  ['verify-email', generateVerifyEmailMetadata],
] as const

describe('noindex metadata boundaries', () => {
  it.each(noindexLayouts)('%s stays out of the index', (_label, metadata) => {
    expect(metadata.robots).toMatchObject({
      index: false,
      follow: false,
      nocache: true,
    })
  })

  it.each(localizedNoindexLayouts)('%s stays localized and out of the index', async (
    _label,
    generateMetadata,
  ) => {
    const metadata = await generateMetadata()

    expect(metadata.robots).toMatchObject({
      index: false,
      follow: false,
      nocache: true,
    })
    expect(metadata.title).toMatch(/pico\.authRecovery\..+\.eyebrow \| MUTX/)
    expect(metadata.description).toMatch(/pico\.authRecovery\..+\.description/)
  })

  it.each([
    ['login', loginMetadata, 'Sign in | MUTX', 'Sign in to continue to your MUTX operator workspace.'],
    ['register', registerMetadata, 'Create account | MUTX', 'Create a MUTX operator account for your hosted workspace.'],
  ])('%s replaces homepage metadata without advertising an auth landing page', (
    _label,
    metadata,
    title,
    description,
  ) => {
    expect(metadata).toMatchObject({
      title,
      description,
      alternates: { canonical: null },
      openGraph: null,
      twitter: null,
    })
  })
})
