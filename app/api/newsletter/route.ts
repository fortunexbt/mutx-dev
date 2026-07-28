import { NextResponse } from 'next/server'
import { Resend } from 'resend'
import sql from '@/lib/db'
import { validateData, schemas } from '@/app/api/_lib/validation'
import { withErrorHandling, badRequest } from '@/app/api/_lib/errors'
import { routing, type Locale } from '@/i18n/routing'

export const dynamic = 'force-dynamic'

const TURNSTILE_VERIFY_URL = 'https://challenges.cloudflare.com/turnstile/v0/siteverify'

type TurnstileVerificationResult = {
  success: boolean
  action?: string
  ['error-codes']?: string[]
}

const resendApiKey = process.env.RESEND_API_KEY?.trim()
const resendFromEmail = process.env.RESEND_FROM_EMAIL?.trim() || 'MUTX <waitlist@mutx.dev>'
const resend = resendApiKey ? new Resend(resendApiKey) : null
const waitlistTemplateIdsByLocale = Object.fromEntries(
  routing.locales.map((locale) => [
    locale,
    process.env[`RESEND_WAITLIST_TEMPLATE_ID_${locale.toUpperCase()}`]?.trim(),
  ]),
) as Record<Locale, string | undefined>
const defaultWaitlistTemplateId =
  process.env.RESEND_WAITLIST_TEMPLATE_ID_EN?.trim()
  || process.env.RESEND_WAITLIST_TEMPLATE_ID?.trim()
  || 'waitlist'

const waitlistMessages = {
  en: {
    invalidInput: 'Invalid input',
    invalidEmail: 'Invalid email format',
    verificationRequired: 'Please complete the verification challenge.',
    verificationFailed: 'Verification failed. Please try again.',
    alreadyJoined: "You're already on the list!",
    success: "You're on the list!",
    successCheckInbox: "You're on the list. Check your inbox.",
  },
  ar: {
    invalidInput: 'إدخال غير صالح',
    invalidEmail: 'تنسيق البريد الإلكتروني غير صالح',
    verificationRequired: 'يرجى إكمال تحدي التحقق.',
    verificationFailed: 'فشل التحقق. يرجى المحاولة مرة أخرى.',
    alreadyJoined: 'أنت بالفعل على القائمة!',
    success: 'لقد انضممت إلى القائمة!',
    successCheckInbox: 'لقد انضممت إلى القائمة. تحقق من بريدك الوارد.',
  },
  de: {
    invalidInput: 'Ungültige Eingabe',
    invalidEmail: 'Ungültiges E-Mail-Format',
    verificationRequired: 'Bitte schließen Sie die Verifizierungsprüfung ab.',
    verificationFailed: 'Verifizierung fehlgeschlagen. Bitte versuchen Sie es erneut.',
    alreadyJoined: 'Sie stehen bereits auf der Liste!',
    success: 'Sie stehen auf der Liste!',
    successCheckInbox: 'Sie stehen auf der Liste. Prüfen Sie Ihren Posteingang.',
  },
  es: {
    invalidInput: 'Entrada no válida',
    invalidEmail: 'Formato de correo electrónico no válido',
    verificationRequired: 'Por favor completa el desafío de verificación.',
    verificationFailed: 'La verificación ha fallado. Inténtalo de nuevo.',
    alreadyJoined: '¡Ya estás en la lista!',
    success: '¡Estás en la lista!',
    successCheckInbox: '¡Estás en la lista! Revisa tu bandeja de entrada.',
  },
  fr: {
    invalidInput: 'Entrée non valide',
    invalidEmail: 'Format d’adresse e-mail invalide',
    verificationRequired: 'Veuillez terminer la vérification.',
    verificationFailed: 'Échec de la vérification. Veuillez réessayer.',
    alreadyJoined: 'Vous êtes déjà sur la liste !',
    success: 'Vous êtes sur la liste !',
    successCheckInbox: 'Vous êtes sur la liste. Vérifiez votre boîte de réception.',
  },
  it: {
    invalidInput: 'Input non valido',
    invalidEmail: 'Formato email non valido',
    verificationRequired: 'Completa la verifica.',
    verificationFailed: 'Verifica non riuscita. Riprova.',
    alreadyJoined: 'Sei già nella lista!',
    success: 'Sei nella lista!',
    successCheckInbox: 'Sei nella lista. Controlla la tua casella di posta.',
  },
  ja: {
    invalidInput: '無効な入力です',
    invalidEmail: 'メールアドレスの形式が正しくありません',
    verificationRequired: '認証チャレンジを完了してください。',
    verificationFailed: '認証に失敗しました。もう一度お試しください。',
    alreadyJoined: 'すでにリストに登録されています！',
    success: 'リストに登録されました！',
    successCheckInbox: 'リストに登録されました。受信トレイをご確認ください。',
  },
  ko: {
    invalidInput: '잘못된 입력입니다',
    invalidEmail: '유효하지 않은 이메일 형식입니다',
    verificationRequired: '인증 확인을 완료해 주세요.',
    verificationFailed: '인증에 실패했습니다. 다시 시도해 주세요.',
    alreadyJoined: '이미 대기자 명단에 등록되어 있습니다!',
    success: '대기자 명단에 등록되었습니다!',
    successCheckInbox: '대기자 명단에 등록되었습니다. 받은편지함을 확인해 주세요.',
  },
  pt: {
    invalidInput: 'Entrada inválida',
    invalidEmail: 'Formato de e-mail inválido',
    verificationRequired: 'Conclua o desafio de verificação.',
    verificationFailed: 'A verificação falhou. Tente novamente.',
    alreadyJoined: 'Você já está na lista!',
    success: 'Você está na lista!',
    successCheckInbox: 'Você está na lista. Verifique sua caixa de entrada.',
  },
  zh: {
    invalidInput: '输入无效',
    invalidEmail: '电子邮件格式无效',
    verificationRequired: '请完成验证挑战。',
    verificationFailed: '验证失败，请重试。',
    alreadyJoined: '你已经在名单中了！',
    success: '你已加入名单！',
    successCheckInbox: '你已加入名单。请检查收件箱。',
  },
} as const satisfies Record<Locale, {
  invalidInput: string
  invalidEmail: string
  verificationRequired: string
  verificationFailed: string
  alreadyJoined: string
  success: string
  successCheckInbox: string
}>

function normalizeLocale(locale?: string): Locale {
  const normalizedLocale = locale?.trim().toLowerCase()
  if (!normalizedLocale) return routing.defaultLocale

  const primaryLocale = normalizedLocale.split('-')[0]
  return routing.locales.includes(primaryLocale as Locale)
    ? (primaryLocale as Locale)
    : routing.defaultLocale
}

function getWaitlistTemplateId(locale?: string) {
  const normalizedLocale = normalizeLocale(locale)
  return waitlistTemplateIdsByLocale[normalizedLocale] || defaultWaitlistTemplateId
}

function getWaitlistMessages(locale?: string) {
  return waitlistMessages[normalizeLocale(locale)]
}

function isEmailDeliveryConfigured() {
  return Boolean(resend && resendFromEmail && defaultWaitlistTemplateId)
}

async function sendWaitlistConfirmationEmail(to: string, locale?: string) {
  if (!resend) {
    throw new Error('RESEND_API_KEY is not configured')
  }

  const result = await resend.emails.send({
    from: resendFromEmail,
    to: [to],
    template: {
      id: getWaitlistTemplateId(locale),
      variables: {},
    },
  })

  if (result.error) {
    throw new Error(result.error.message || 'Resend email send failed')
  }

  return result
}

async function ensureTableExists() {
  if (!sql) return
  await sql`
    CREATE TABLE IF NOT EXISTS waitlist_emails (
      email TEXT PRIMARY KEY,
      source TEXT NOT NULL,
      created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
    );
  `
}

function getClientIp(request: Request) {
  const cfConnectingIp = request.headers.get('cf-connecting-ip')?.trim()
  if (cfConnectingIp) {
    return cfConnectingIp
  }

  const forwardedFor = request.headers.get('x-forwarded-for')
  if (forwardedFor) {
    return forwardedFor.split(',')[0]?.trim()
  }

  return request.headers.get('x-real-ip')?.trim() ?? undefined
}

async function verifyTurnstileToken(request: Request, token: string) {
  const secretKey = process.env.TURNSTILE_SECRET_KEY?.trim()

  if (!secretKey) {
    throw new Error('TURNSTILE_SECRET_KEY is not configured')
  }

  const payload = new URLSearchParams({
    secret: secretKey,
    response: token,
  })

  const clientIp = getClientIp(request)
  if (clientIp) {
    payload.set('remoteip', clientIp)
  }

  const response = await fetch(TURNSTILE_VERIFY_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: payload,
    cache: 'no-store',
  })

  if (!response.ok) {
    throw new Error(`Turnstile siteverify request failed with status ${response.status}`)
  }

  const result = (await response.json()) as TurnstileVerificationResult

  if (!result.success) {
    console.error('Turnstile verification failed', result['error-codes'] ?? [])
    return false
  }

  if (result.action && result.action !== 'waitlist') {
    console.error('Turnstile verification action mismatch', result.action)
    return false
  }

  return true
}

/**
 * NEXTJS WAITLIST API (SOURCE OF TRUTH)
 * This is the primary endpoint for web-based waitlist submissions.
 * It handles captcha verification, honeypot checks, and direct DB insertion.
 * Backend python API may eventually proxy here or share the same DB.
 */
export async function POST(request: Request): Promise<NextResponse> {
  return withErrorHandling(async (_req: Request) => {
    if (!sql) {
      throw new Error('Database not configured')
    }

    const body = await request.json().catch(() => ({}))
    const { email: _email, source, locale, captchaToken, honeypot } = body
    const messages = getWaitlistMessages(locale)

    // 1. Honeypot check
    if (honeypot) {
      return badRequest(messages.invalidInput)
    }

    // 2. Validate email with schema
    const validation = await validateData(schemas.newsletter, body)
    if (!validation.success) {
      const validationBody = await validation.response.json()
      if (validationBody?.error?.message === 'Invalid email format') {
        return badRequest(messages.invalidEmail)
      }

      return validation.response
    }

    // 3. Validate captcha token
    if (typeof captchaToken !== 'string' || !captchaToken.trim()) {
      return badRequest(messages.verificationRequired)
    }

    const isValidCaptcha = await verifyTurnstileToken(request, captchaToken)
    if (!isValidCaptcha) {
      return badRequest(messages.verificationFailed)
    }

    const normalizedEmail = validation.data.email.toLowerCase().trim()
    const normalizedSource = String(source || 'coming-soon').trim().slice(0, 120) || 'coming-soon'

    await ensureTableExists()

    const result = await sql`
      INSERT INTO waitlist_emails (email, source)
      VALUES (${normalizedEmail}, ${normalizedSource})
      ON CONFLICT (email) DO NOTHING
      RETURNING *;
    `

    if (result.length === 0) {
      return NextResponse.json({ success: true, message: messages.alreadyJoined, emailSent: false, alreadyJoined: true })
    }

    let emailSent = false
    let message: string = messages.success

    if (isEmailDeliveryConfigured()) {
      try {
        await sendWaitlistConfirmationEmail(normalizedEmail, locale)
        emailSent = true
        message = messages.successCheckInbox
      } catch (emailError) {
        console.error('Waitlist confirmation email failed:', emailError)
      }
    } else {
      console.warn('Waitlist email delivery skipped: Resend waitlist email is not fully configured')
    }

    return NextResponse.json({
      success: true,
      message,
      emailSent,
      alreadyJoined: false,
    })
  })(request)
}

const newsletterCountResponseHeaders = {
  'Cache-Control': 'no-store',
}

function unavailableNewsletterCount() {
  return NextResponse.json(
    {
      status: 'unavailable',
      error: {
        code: 'COUNT_UNAVAILABLE',
        message: 'Subscriber count is unavailable',
      },
    },
    { status: 503, headers: newsletterCountResponseHeaders },
  )
}

function parseNewsletterCount(result: unknown): number | null {
  if (!Array.isArray(result) || result.length !== 1) return null

  const row = result[0]
  if (!row || typeof row !== 'object' || !('count' in row)) return null

  const rawCount = (row as { count: unknown }).count
  if (
    typeof rawCount !== 'number'
    && typeof rawCount !== 'string'
    && typeof rawCount !== 'bigint'
  ) {
    return null
  }

  if (typeof rawCount === 'string' && !/^(0|[1-9][0-9]*)$/.test(rawCount)) {
    return null
  }

  const count = Number(rawCount)
  return Number.isSafeInteger(count) && count >= 0 ? count : null
}

export async function GET(): Promise<NextResponse> {
  if (!sql) return unavailableNewsletterCount()

  try {
    await ensureTableExists()
    const result = await sql`SELECT COUNT(*) as count FROM waitlist_emails`
    const count = parseNewsletterCount(result)

    if (count === null) return unavailableNewsletterCount()

    return NextResponse.json(
      { count },
      { headers: newsletterCountResponseHeaders },
    )
  } catch {
    console.error('Newsletter subscriber count provider is unavailable')
    return unavailableNewsletterCount()
  }
}
