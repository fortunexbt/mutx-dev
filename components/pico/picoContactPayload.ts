export type PicoContactPayloadInput = {
  email: string
  name: string
  company: string
  message: string
  interest: string
  locale: string
  source: string
  honeypot: string
  productUpdatesConsent: boolean
}

export function buildPicoContactPayload(input: PicoContactPayloadInput) {
  return {
    email: input.email,
    name: input.name,
    company: input.company,
    message: input.message,
    tier: input.interest,
    interest: input.interest,
    locale: input.locale,
    source: input.source,
    honeypot: input.honeypot,
    productUpdatesConsent: input.productUpdatesConsent,
  }
}
